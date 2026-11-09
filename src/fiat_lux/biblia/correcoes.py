"""Correções do corpus: duplicados (automáticas + manuais) e edições de texto (plano §8.1.2)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

from fiat_lux.biblia.modelos import VersoBruto
from fiat_lux.textos import chave


@dataclass(frozen=True, slots=True)
class Correcao:
    traducao: str
    livro: str
    capitulo: int
    versiculo: int
    acao: str
    valor: str
    nota: str


@dataclass(frozen=True, slots=True)
class Decisao:
    """Registro de como um número repetido foi resolvido (vai para o relatório)."""

    livro: str
    capitulo: int
    versiculo: int
    ocorrencias: int
    metodo: str  # manual | identico | copia_espuria | quase_identico | pendente
    detalhe: str


ACOES_VALIDAS = frozenset(
    {
        "manter_ocorrencia",
        "unir_ocorrencias",
        "substituir",
        "texto",
        "dividir",
        "mover",
        "aceitar_lacuna",
    }
)


def carregar_correcoes(caminho: Path, traducao: str | None = None) -> list[Correcao]:
    if not caminho.is_file():
        return []
    saida: list[Correcao] = []
    for n, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        partes = linha.split("\t")
        if len(partes) < 6:
            raise ValueError(f"{caminho.name}:{n}: esperadas ≥ 6 colunas separadas por TAB")
        trad, livro, cap, vers, acao, valor = (p.strip() for p in partes[:6])
        nota = partes[6].strip() if len(partes) > 6 else ""
        if acao not in ACOES_VALIDAS:
            raise ValueError(f"{caminho.name}:{n}: ação desconhecida {acao!r}")
        if traducao and trad != traducao:
            continue
        saida.append(Correcao(trad, livro.upper(), int(cap), int(vers), acao, valor, nota))
    return saida


def _indice(correcoes: list[Correcao], acoes: set[str]) -> dict[tuple[str, int, int], Correcao]:
    return {(c.livro, c.capitulo, c.versiculo): c for c in correcoes if c.acao in acoes}


def resolver_duplicados(
    brutos: list[VersoBruto], correcoes: list[Correcao]
) -> tuple[list[VersoBruto], list[Decisao]]:
    """Garante um único versículo por (livro, cap, vers).

    Ordem das regras: manual > textos idênticos > cópia espúria de outro versículo do mesmo
    livro (ex.: Esd 4,14-22 repetidos dentro de Esd 6) > quase idênticos > pendente (fica a 1ª).
    """
    manuais = _indice(correcoes, {"manter_ocorrencia", "unir_ocorrencias"})
    grupos: dict[tuple[str, int, int], list[VersoBruto]] = defaultdict(list)
    ordem: list[tuple[str, int, int]] = []
    for v in brutos:
        k = (v.livro, v.capitulo, v.versiculo)
        if k not in grupos:
            ordem.append(k)
        grupos[k].append(v)

    # textos normalizados por livro → chaves (para detectar cópias espúrias)
    por_livro: dict[str, dict[str, set[tuple[int, int]]]] = defaultdict(lambda: defaultdict(set))
    for v in brutos:
        por_livro[v.livro][chave(v.texto_bruto)].add((v.capitulo, v.versiculo))

    saida: list[VersoBruto] = []
    decisoes: list[Decisao] = []
    for k in ordem:
        ocs = grupos[k]
        if len(ocs) == 1:
            saida.append(ocs[0])
            continue
        livro, cap, vers = k
        c = manuais.get(k)
        if c is not None:
            if c.acao == "manter_ocorrencia":
                idx = int(c.valor) - 1
                escolhido = ocs[idx]
            else:
                idxs = [int(x) - 1 for x in c.valor.split(",")]
                texto = " ".join(ocs[i].texto_bruto.strip() for i in idxs)
                escolhido = VersoBruto(ocs[0].traducao, livro, cap, vers, texto)
            saida.append(escolhido)
            decisoes.append(Decisao(livro, cap, vers, len(ocs), "manual", c.nota or c.acao))
            continue
        chaves = [chave(o.texto_bruto) for o in ocs]
        if len(set(chaves)) == 1:
            saida.append(ocs[0])
            decisoes.append(Decisao(livro, cap, vers, len(ocs), "identico", "mantida a 1ª"))
            continue
        # cópia espúria: o mesmo texto existe em outro (cap, vers) do livro
        restantes: list[tuple[VersoBruto, set[tuple[int, int]]]] = []
        copias: list[tuple[VersoBruto, set[tuple[int, int]]]] = []
        for o, ch in zip(ocs, chaves, strict=True):
            outros = por_livro[livro][ch] - {(cap, vers)}
            (copias if outros else restantes).append((o, outros))
        if copias and restantes:
            textos_rest = {chave(o.texto_bruto) for o, _ in restantes}
            if len(textos_rest) == 1:
                saida.append(restantes[0][0])
                origem = sorted(next(iter(copias))[1])[0]
                decisoes.append(
                    Decisao(
                        livro,
                        cap,
                        vers,
                        len(ocs),
                        "copia_espuria",
                        f"descartada(s) {len(copias)} cópia(s) de {livro} {origem[0]},{origem[1]}",
                    )
                )
                continue
        if fuzz.ratio(chaves[0], chaves[1]) >= 90:
            saida.append(ocs[0])
            decisoes.append(
                Decisao(livro, cap, vers, len(ocs), "quase_identico", "mantida a 1ª; revisar")
            )
            continue
        saida.append(ocs[0])
        decisoes.append(Decisao(livro, cap, vers, len(ocs), "pendente", "mantida a 1ª; revisar"))
    return saida, decisoes


def aplicar_edicoes(
    brutos: list[VersoBruto], correcoes: list[Correcao]
) -> tuple[list[VersoBruto], list[str]]:
    """Aplica `substituir`, `texto`, `dividir` e `mover` sobre o texto bruto.

    Divisões podem ser encadeadas: o versículo criado por um `dividir` também recebe as
    edições registradas para o seu número (ex.: Eclo 30,21 → 30,22 → 30,23).
    """
    edicoes: dict[tuple[str, int, int], list[Correcao]] = defaultdict(list)
    for c in correcoes:
        if c.acao in {"substituir", "texto", "dividir", "mover"}:
            edicoes[(c.livro, c.capitulo, c.versiculo)].append(c)
    log: list[str] = []
    saida: list[VersoBruto] = []
    fila = list(brutos)
    fila.reverse()
    while fila:
        v = fila.pop()
        lista = edicoes.get((v.livro, v.capitulo, v.versiculo), [])
        if not lista:
            saida.append(v)
            continue
        texto = v.texto_bruto
        cap, vers = v.capitulo, v.versiculo
        extra: VersoBruto | None = None
        for c in lista:
            if c.acao == "substituir":
                de, para = c.valor.split("|", 1)
                if de not in texto:
                    raise ValueError(f"correção {c}: trecho {de!r} não encontrado")
                texto = texto.replace(de, para)
            elif c.acao == "texto":
                texto = c.valor
            elif c.acao == "mover":
                novo_cap, novo_vers = (int(x) for x in c.valor.split(","))
                cap, vers = novo_cap, novo_vers
            elif c.acao == "dividir":
                pos = texto.find(c.valor)
                if pos <= 0:
                    raise ValueError(f"correção {c}: marcador {c.valor!r} não encontrado")
                extra = VersoBruto(v.traducao, v.livro, cap, vers + 1, texto[pos:].strip())
                texto = texto[:pos].strip()
            log.append(f"{v.livro} {v.capitulo},{v.versiculo}: {c.acao} ({c.nota or c.valor})")
        saida.append(VersoBruto(v.traducao, v.livro, cap, vers, texto, v.ocorrencia))
        if extra is not None:
            fila.append(extra)
    saida.sort(key=lambda x: (x.livro, x.capitulo, x.versiculo))
    return saida, log
