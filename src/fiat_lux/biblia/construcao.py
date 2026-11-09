"""Construção do corpus (`fiatlux biblia ingerir`): das fontes fixadas ao `biblia.sqlite`."""

from __future__ import annotations

import datetime as dt
import itertools
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from fiat_lux.biblia import banco
from fiat_lux.biblia.catalogo import LIVROS, por_codigo, por_osis
from fiat_lux.biblia.correcoes import (
    Decisao,
    aplicar_edicoes,
    carregar_correcoes,
    resolver_duplicados,
)
from fiat_lux.biblia.ingestao_blivre import ler_blivre
from fiat_lux.biblia.ingestao_ms import DiffLivro, comparar_arquivos_por_livro, ler_biblia_json
from fiat_lux.biblia.limpeza import Limpador, separar_titulo_salmo
from fiat_lux.biblia.modelos import (
    F_CORRIGIDO_AUTO,
    F_CORRIGIDO_MANUAL,
    F_DEUTERO_TRECHO,
    F_DUPLICADO_RESOLVIDO,
    F_FUNDIDO,
    F_SEM_CORRESPONDENTE,
    F_TITULO_SALMO,
    F_TITULO_SEPARADO,
    TRADUCOES,
    Lacuna,
    Mapeamento,
    Verso,
    VersoBruto,
)
from fiat_lux.biblia.versificacao import (
    ParametrosAlinhamento,
    Ref,
    Versificacao,
    alinhar,
    melhor_divisao,
    ref_str,
)
from fiat_lux.textos import normalizar_para_busca, variantes_ortograficas

CONF_MINIMA_ACEITE = 0.8


@dataclass(slots=True)
class DivisaoAuto:
    livro: str
    capitulo: int
    versiculo: int
    sim1: float
    sim2: float
    aplicada: bool
    trecho2: str


@dataclass(slots=True)
class ResultadoConstrucao:
    contagens_brutas: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    contagens_finais: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    decisoes_duplicados: list[Decisao] = field(default_factory=list)
    log_edicoes: list[str] = field(default_factory=list)
    limpeza: dict[str, Counter[str]] = field(default_factory=dict)
    titulos: Counter[str] = field(default_factory=Counter)
    lacunas: list[Lacuna] = field(default_factory=list)
    divisoes: list[DivisaoAuto] = field(default_factory=list)
    diffs_por_livro: list[DiffLivro] = field(default_factory=list)
    mapa: list[Mapeamento] = field(default_factory=list)
    cobertura: dict[str, float] = field(default_factory=dict)
    sem_correspondente_bl: list[str] = field(default_factory=list)
    xrefs: int = 0


# --------------------------------------------------------------------------- utilidades


def _contar(versos: list[VersoBruto] | list[Verso]) -> tuple[int, int, int]:
    livros = {v.livro for v in versos}
    caps = {(v.livro, v.capitulo) for v in versos}
    return len(livros), len(caps), len(versos)


def _limpar(brutos: list[VersoBruto], limpador: Limpador) -> tuple[list[Verso], dict[Ref, Ref]]:
    versos: list[Verso] = []
    marcadores: dict[Ref, Ref] = {}
    for b in brutos:
        salmo = b.livro == "PSA"
        r = limpador.limpar(b.texto_bruto, salmo=salmo)
        v = Verso(b.traducao, b.livro, b.capitulo, b.versiculo, r.texto, b.texto_bruto)
        if r.marcador_hebraico:
            marcadores[v.chave] = ("PSA", *r.marcador_hebraico)
        versos.append(v)
    return versos, marcadores


def _separar_titulos(versos: list[Verso], contador: Counter[str]) -> None:
    """Títulos de salmo da MS (v. 1 e, se o v. 1 for só título, v. 2)."""
    por_salmo: dict[int, list[Verso]] = defaultdict(list)
    for v in versos:
        if v.livro == "PSA":
            por_salmo[v.capitulo].append(v)
    for lista in por_salmo.values():
        lista.sort(key=lambda x: x.versiculo)
        anterior_titulo = False
        for v in lista[:2]:
            if v is lista[1] and not anterior_titulo:
                break
            titulo, corpo = separar_titulo_salmo(v.texto, anterior_e_titulo=anterior_titulo)
            if titulo is None:
                break
            v.titulo = titulo.rstrip(" ,;:")
            if corpo:
                v.texto = corpo
                v.marcar(F_TITULO_SEPARADO)
                contador["fundido_separado"] += 1
                break
            v.marcar(F_TITULO_SALMO)
            contador["versiculo_so_titulo"] += 1
            anterior_titulo = True


# Na Vulgata a numeração destes salmos continua a do anterior (Sl 115 = 10–19; Sl 147 = 12–20).
NUMERACAO_CONTINUA = frozenset({("PSA", 115), ("PSA", 147)})


def _lacunas_brutas(versos: list[Verso]) -> dict[tuple[str, int], list[int]]:
    por_cap: dict[tuple[str, int], set[int]] = defaultdict(set)
    for v in versos:
        por_cap[(v.livro, v.capitulo)].add(v.versiculo)
    faltas: dict[tuple[str, int], list[int]] = {}
    for k, nums in por_cap.items():
        inicio = min(nums) if k in NUMERACAO_CONTINUA else 1
        miss = [i for i in range(inicio, max(nums) + 1) if i not in nums]
        if miss:
            faltas[k] = miss
    return faltas


# --------------------------------------------------------------------------- alinhamento


@dataclass(slots=True)
class _EstadoLivro:
    mapa: list[Mapeamento]
    fundidos: dict[Ref, int]  # MS ref → nº de versículos BLIVRE contidos (2 ou 3)
    bl_sem_par: list[Ref]
    divisoes: list[DivisaoAuto]


def _alinhar_livro(
    livro: str,
    ms: list[Verso],
    bl: list[Verso],
    vrs: Versificacao,
    marcadores: dict[Ref, Ref],
    variantes: dict[str, str],
    lacunas: set[Ref],
) -> _EstadoLivro:
    estado = _EstadoLivro([], {}, [], [])
    bl_idx = {v.chave: i for i, v in enumerate(bl)}
    entrada: list[Verso] = []
    previsao: list[Ref | None] = []
    for v in ms:
        if v.e_titulo:
            continue
        p = vrs.ms_para_eng(v.chave)
        if p is None:
            v.marcar(F_DEUTERO_TRECHO)
            pseudo = "DAG" if livro == "DAN" else ("ESG" if livro == "EST" else livro)
            v.ref_canonica = f"{pseudo}.{v.capitulo}.{v.versiculo}"
            continue
        entrada.append(v)
        previsao.append(p)
    # guia: índice BLIVRE previsto pela tabela (interpolado onde faltar)
    guia_bruto: list[float | None] = []
    for p in previsao:
        if p is None:
            guia_bruto.append(None)
            continue
        alvo = (p[0], p[1], max(p[2], 1))
        guia_bruto.append(float(bl_idx[alvo]) if alvo in bl_idx else None)
    guia = _interpolar(guia_bruto, len(bl))
    preferidos = [
        int(g) if g is not None and p is not None and p[2] >= 1 else None
        for g, p in zip(guia_bruto, previsao, strict=True)
    ]
    textos_ms = [
        _texto_alinhamento(v.texto, livro, inicio=True, variantes=variantes) for v in entrada
    ]
    textos_bl = [_texto_alinhamento(v.texto, livro, inicio=False, variantes=variantes) for v in bl]
    salmos = livro == "PSA"
    passos = alinhar(
        textos_ms,
        textos_bl,
        guia,
        ParametrosAlinhamento(),
        preferidos=preferidos,
        capitulos_a=[v.capitulo for v in entrada] if salmos else None,
        capitulos_b=[v.capitulo for v in bl] if salmos else None,
        fusao_provavel=[(v.livro, v.capitulo, v.versiculo + 1) in lacunas for v in entrada],
    )
    usados_bl: set[int] = set()
    inicio_salmo = True
    capitulo_atual = None
    for passo in passos:
        if passo.ni == 0:
            estado.bl_sem_par.extend(bl[j].chave for j in range(passo.j, passo.j + passo.nj))
            continue
        for d in range(passo.ni):
            k = passo.i + d
            v = entrada[k]
            if v.capitulo != capitulo_atual:
                capitulo_atual, inicio_salmo = v.capitulo, True
            p = previsao[k]
            if passo.nj == 0:
                if livro == "PSA" and inicio_salmo and p is not None and p[2] == 0:
                    v.marcar(F_TITULO_SALMO)
                    if not v.titulo:
                        v.titulo = v.texto
                    estado.mapa.append(
                        Mapeamento(
                            "ms-vulg",
                            ref_str(v.chave),
                            "eng",
                            f"PSA.{p[1]}.0",
                            None,
                            "alinhamento",
                            0.9,
                        )
                    )
                    continue
                inicio_salmo = False
                if p is not None and p[2] >= 1 and p in bl_idx:
                    _registrar(estado, v, p, None, "tabela", 0.7)
                else:
                    v.marcar(F_SEM_CORRESPONDENTE)
                continue
            inicio_salmo = False
            alvo_ini = bl[passo.j].chave
            alvo_fim = bl[passo.j + passo.nj - 1].chave if passo.nj > 1 else None
            usados_bl.update(range(passo.j, passo.j + passo.nj))
            concorda = p is not None and (
                p == alvo_ini
                or (
                    alvo_fim is not None
                    and p[1] == alvo_ini[1]
                    and alvo_ini[2] <= p[2] <= alvo_fim[2]
                )
            )
            if v.chave in marcadores:
                _registrar(estado, v, marcadores[v.chave], None, "marcador", 0.99)
                continue
            if passo.ni == 1 and passo.nj == 1:
                if concorda:
                    _registrar(estado, v, alvo_ini, None, "tabela", 0.98)
                else:
                    conf = 0.9 if passo.sim >= 0.3 else (0.85 if passo.sim >= 0.18 else 0.6)
                    _registrar(estado, v, alvo_ini, None, "alinhamento", conf)
            elif passo.nj > 1:  # um versículo da MS contém 2–3 da BLIVRE
                estado.fundidos[v.chave] = passo.nj
                conf = 0.92 if concorda else (0.85 if passo.sim >= 0.25 else 0.65)
                _registrar(estado, v, alvo_ini, alvo_fim, "alinhamento", conf)
            else:  # dois versículos da MS ↔ um da BLIVRE
                conf = 0.92 if concorda else (0.85 if passo.sim >= 0.25 else 0.65)
                _registrar(estado, v, alvo_ini, None, "alinhamento", conf)
    # divisão automática de versículos fundidos ao lado de lacuna
    novos: list[Verso] = []
    for v in entrada:
        nj = estado.fundidos.get(v.chave)
        seguinte = (v.livro, v.capitulo, v.versiculo + 1)
        if nj != 2 or seguinte not in lacunas:
            continue
        m = next((x for x in estado.mapa if x.ref_origem == ref_str(v.chave)), None)
        if m is None or m.ref_destino_fim is None:
            continue
        b1, b2 = bl[bl_idx[_ref(m.ref_destino)]], bl[bl_idx[_ref(m.ref_destino_fim)]]
        div = melhor_divisao(v.texto, b1.texto, b2.texto)
        if div is None:
            continue
        pos, s1, s2 = div
        aplicar = s1 >= 0.12 and s2 >= 0.12
        estado.divisoes.append(
            DivisaoAuto(
                v.livro, v.capitulo, v.versiculo, s1, s2, aplicar, v.texto[pos:].strip()[:80]
            )
        )
        if not aplicar:
            continue
        parte2 = v.texto[pos:].strip()
        v.texto = v.texto[:pos].strip()
        v.marcar(F_CORRIGIDO_AUTO)
        nv = Verso(
            v.traducao,
            v.livro,
            v.capitulo,
            v.versiculo + 1,
            parte2,
            "",
            ref_canonica=ref_str(b2.chave),
        )
        nv.marcar(F_CORRIGIDO_AUTO)
        novos.append(nv)
        estado.fundidos.pop(v.chave, None)
        estado.mapa = [x for x in estado.mapa if x.ref_origem != ref_str(v.chave)]
        _registrar(estado, v, b1.chave, None, "alinhamento", max(m.confianca, 0.85))
        _registrar(estado, nv, b2.chave, None, "alinhamento", max(m.confianca, 0.85))
    ms.extend(novos)
    return estado


_ALELUIA_INICIO = re.compile(r"^\s*aleluia[.!]?\s*", re.IGNORECASE)
_ALELUIA_FIM = re.compile(r"\s*aleluia[.!]?\s*$", re.IGNORECASE)


def _texto_alinhamento(texto: str, livro: str, *, inicio: bool, variantes: dict[str, str]) -> str:
    """Nos salmos, a Vulgata põe no início do salmo o "Aleluia" que o hebraico tem no fim do
    anterior; removê-lo evita que o alinhamento case versículos de salmos vizinhos."""
    if livro == "PSA":
        texto = (_ALELUIA_INICIO if inicio else _ALELUIA_FIM).sub(" ", texto)
    return normalizar_para_busca(texto, variantes)


def _ref(s: str) -> Ref:
    a, b, c = s.split(".")
    return (a, int(b), int(c))


def _registrar(
    estado: _EstadoLivro, v: Verso, alvo: Ref, fim: Ref | None, metodo: str, conf: float
) -> None:
    v.ref_canonica = ref_str(alvo)
    estado.mapa.append(
        Mapeamento(
            "ms-vulg",
            ref_str(v.chave),
            "eng",
            ref_str(alvo),
            ref_str(fim) if fim else None,
            metodo,  # type: ignore[arg-type]
            conf,
        )
    )


def _interpolar(valores: list[float | None], m: int) -> list[float]:
    """Guia para a banda do alinhamento: linha i = nº de versículos BLIVRE antes do i-ésimo da MS."""
    n = len(valores)
    saida: list[float] = [0.0] * (n + 1)
    conhecidos = [(i, v) for i, v in enumerate(valores) if v is not None]
    pontos = [(0, 0.0), *conhecidos, (n, float(m))]
    for (i0, v0), (i1, v1) in itertools.pairwise(pontos):
        for i in range(i0, i1 + 1):
            t = 0.0 if i1 == i0 else (i - i0) / (i1 - i0)
            saida[min(i, n)] = v0 + t * (v1 - v0)
    for i in range(1, n + 1):  # monotônico
        saida[i] = max(saida[i], saida[i - 1])
    return saida


# --------------------------------------------------------------------------- referências cruzadas


def _ler_xrefs(caminho: Path) -> list[tuple[str, str, str | None, int]]:
    linhas: list[tuple[str, str, str | None, int]] = []

    def conv(osis: str) -> str | None:
        partes = osis.split(".")
        if len(partes) != 3:
            return None
        lv = por_osis(partes[0])
        return f"{lv.codigo}.{int(partes[1])}.{int(partes[2])}" if lv else None

    for linha in caminho.read_text(encoding="utf-8").splitlines()[1:]:
        cols = linha.split("\t")
        if len(cols) < 3:
            continue
        de = conv(cols[0])
        alvo = cols[1].split("-")
        ini = conv(alvo[0])
        fim = conv(alvo[1]) if len(alvo) > 1 else None
        if de and ini:
            linhas.append((de, ini, fim, int(cols[2])))
    return linhas


# --------------------------------------------------------------------------- principal


def construir_corpus(raw: Path, dir_config: Path, destino: Path) -> ResultadoConstrucao:
    res = ResultadoConstrucao()
    variantes = variantes_ortograficas(dir_config / "variantes_ortograficas.tsv")
    ms_b = ler_biblia_json(raw / "ms" / "biblia.json")
    bl_b = ler_blivre(raw / "blivre" / "versoes" / "blivre" / "json")
    res.contagens_brutas = {"ms": _contar(ms_b), "blivre": _contar(bl_b)}
    res.diffs_por_livro = comparar_arquivos_por_livro(raw / "ms", ms_b)

    correcoes = carregar_correcoes(dir_config / "correcoes_ms.tsv", "ms")
    ms_b, res.decisoes_duplicados = resolver_duplicados(ms_b, correcoes)
    ms_b, res.log_edicoes = aplicar_edicoes(ms_b, correcoes)
    bl_b, dec_bl = resolver_duplicados(bl_b, [])
    res.decisoes_duplicados += dec_bl
    duplicados = {(d.livro, d.capitulo, d.versiculo) for d in res.decisoes_duplicados}
    editados: set[Ref] = set()
    for c in correcoes:
        if c.acao in {"substituir", "texto", "dividir"}:
            editados.add((c.livro, c.capitulo, c.versiculo))
        if c.acao == "dividir":
            editados.add((c.livro, c.capitulo, c.versiculo + 1))
        if c.acao == "mover":
            cap, vers = (int(x) for x in c.valor.split(","))
            editados.add((c.livro, cap, vers))

    lim_ms, lim_bl = Limpador(), Limpador()
    ms, marcadores = _limpar(ms_b, lim_ms)
    bl, _ = _limpar(bl_b, lim_bl)
    res.limpeza = {"ms": lim_ms.contadores, "blivre": lim_bl.contadores}
    for v in ms:
        if v.chave in duplicados:
            v.marcar(F_DUPLICADO_RESOLVIDO)
        if v.chave in editados:
            v.marcar(F_CORRIGIDO_MANUAL)
    _separar_titulos(ms, res.titulos)

    faltas = _lacunas_brutas(ms)
    lacunas_ms: set[Ref] = {(lv, c, n) for (lv, c), ns in faltas.items() for n in ns}
    aceitas_manual = {
        (c.livro, c.capitulo, c.versiculo) for c in correcoes if c.acao == "aceitar_lacuna"
    }
    lacunas_auto = lacunas_ms - aceitas_manual  # candidatas a divisão automática

    vrs = Versificacao.carregar(raw / "vrs" / "examples")
    por_livro_ms: dict[str, list[Verso]] = defaultdict(list)
    por_livro_bl: dict[str, list[Verso]] = defaultdict(list)
    for v in ms:
        por_livro_ms[v.livro].append(v)
    for v in bl:
        por_livro_bl[v.livro].append(v)
        v.ref_canonica = ref_str(v.chave)
    fundidos: dict[Ref, int] = {}
    for lv in LIVROS:
        lista_ms = sorted(por_livro_ms[lv.codigo], key=lambda x: (x.capitulo, x.versiculo))
        if lv.deuterocanonico:
            for v in lista_ms:
                p = vrs.ms_para_eng(v.chave)
                alvo = p if p is not None else v.chave
                v.ref_canonica = ref_str(alvo)
                res.mapa.append(
                    Mapeamento(
                        "ms-vulg", ref_str(v.chave), "eng", ref_str(alvo), None, "tabela", 0.8
                    )
                )
            continue
        lista_bl = sorted(por_livro_bl[lv.codigo], key=lambda x: (x.capitulo, x.versiculo))
        est = _alinhar_livro(
            lv.codigo, lista_ms, lista_bl, vrs, marcadores, variantes, lacunas_auto
        )
        por_livro_ms[lv.codigo] = lista_ms
        res.mapa.extend(est.mapa)
        res.divisoes.extend(est.divisoes)
        res.sem_correspondente_bl.extend(ref_str(r) for r in est.bl_sem_par)
        fundidos.update(est.fundidos)
    ms = [
        v
        for lv in LIVROS
        for v in sorted(por_livro_ms[lv.codigo], key=lambda x: (x.capitulo, x.versiculo))
    ]

    # classificação das lacunas
    manuais = {
        (c.livro, c.capitulo, c.versiculo): c for c in correcoes if c.acao == "aceitar_lacuna"
    }
    presentes = {v.chave for v in ms}
    medianas: dict[tuple[str, int], float] = {}
    por_cap: dict[tuple[str, int], list[int]] = defaultdict(list)
    for v in ms:
        por_cap[(v.livro, v.capitulo)].append(len(v.texto))
    for k, comps in por_cap.items():
        medianas[k] = statistics.median(comps)
    textos = {v.chave: v for v in ms}
    for ref in sorted(lacunas_ms, key=lambda r: (por_codigo(r[0]).ordem_catolica, r[1], r[2])):
        livro, cap, n = ref
        if ref in presentes:
            res.lacunas.append(
                Lacuna("ms", livro, cap, n, "corrigida", "fundido", "dividido automaticamente")
            )
            continue
        if ref in manuais:
            c = manuais[ref]
            tipo = "fundido" if c.valor == "fundido" else "ausente"
            res.lacunas.append(Lacuna("ms", livro, cap, n, "aceita", tipo, c.nota))  # type: ignore[arg-type]
            continue
        anterior = textos.get((livro, cap, n - 1))
        anterior2 = textos.get((livro, cap, n - 2))
        if anterior and fundidos.get(anterior.chave):
            _marcar_fundido(anterior, n)
            res.lacunas.append(
                Lacuna(
                    "ms", livro, cap, n, "aceita", "fundido", "texto contido no versículo anterior"
                )
            )
        elif anterior2 and fundidos.get(anterior2.chave, 0) >= 3:
            _marcar_fundido(anterior2, n)
            res.lacunas.append(
                Lacuna("ms", livro, cap, n, "aceita", "fundido", "texto contido em v-2")
            )
        elif (
            por_codigo(livro).deuterocanonico
            and anterior
            and len(anterior.texto) > 1.6 * medianas[(livro, cap)]
        ):
            _marcar_fundido(anterior, n)
            res.lacunas.append(
                Lacuna(
                    "ms",
                    livro,
                    cap,
                    n,
                    "aceita",
                    "fundido",
                    "heurística de comprimento (sem par protestante)",
                )
            )
        else:
            tipo = "desconhecido" if por_codigo(livro).deuterocanonico else "ausente"
            res.lacunas.append(Lacuna("ms", livro, cap, n, "aberta", tipo, ""))  # type: ignore[arg-type]

    res.contagens_finais = {"ms": _contar(ms), "blivre": _contar(bl)}
    res.cobertura = _cobertura(ms, res.mapa)

    # gravação
    if destino.exists():
        destino.unlink()
    con = banco.conectar(destino)
    try:
        banco.criar_esquema(con)
        banco.gravar_traducoes(con, TRADUCOES.values())
        banco.gravar_livros(con)
        busca = {
            (v.traducao, v.livro, v.capitulo, v.versiculo): normalizar_para_busca(
                v.texto, variantes
            )
            for v in [*ms, *bl]
        }
        banco.gravar_versiculos(con, [*ms, *bl], busca)
        banco.gravar_lacunas(con, res.lacunas)
        banco.gravar_mapa(con, res.mapa)
        res.xrefs = banco.gravar_xrefs(
            con, _ler_xrefs(raw / "xref" / "sources" / "extras" / "cross_references.txt")
        )
        banco.reconstruir_fts(con)
        banco.gravar_metadados(
            con,
            {
                "versao_corpus": "1",
                "construido_em": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "versiculos_ms": str(len(ms)),
                "versiculos_blivre": str(len(bl)),
                "cobertura_protocanonica_conf08": f"{res.cobertura.get('protocanonicos_conf08', 0):.4f}",
            },
        )
        con.commit()
    finally:
        con.close()
    return res


def _marcar_fundido(v: Verso, ate: int) -> None:
    v.marcar(F_FUNDIDO)
    v.fim_fundido = max(v.fim_fundido or 0, ate)


def _cobertura(ms: list[Verso], mapa: list[Mapeamento]) -> dict[str, float]:
    conf = {m.ref_origem: m.confianca for m in mapa if not m.ref_destino.endswith(".0")}
    alvo = [
        v
        for v in ms
        if not por_codigo(v.livro).deuterocanonico
        and not v.e_titulo
        and F_DEUTERO_TRECHO not in v.flags
    ]
    total = len(alvo)
    mapeados = sum(1 for v in alvo if ref_str(v.chave) in conf)
    alta = sum(1 for v in alvo if conf.get(ref_str(v.chave), 0) >= CONF_MINIMA_ACEITE)
    return {
        "protocanonicos": float(total),
        "mapeados": float(mapeados),
        "conf08": float(alta),
        "protocanonicos_mapeados": mapeados / total if total else 0.0,
        "protocanonicos_conf08": alta / total if total else 0.0,
    }
