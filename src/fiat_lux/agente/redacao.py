"""Redação com placeholders (plano §8.5.4; prompt P4) e juiz de neutralidade (P5).

O modelo escreve SEM transcrever Escritura: usa {{P1}}, {{C1}}, {{C2}}. Só pode citar
referências do conjunto permitido (leituras do dia + principal + complementares).

Modelos pequenos esquecem o {{P1}} ou o repetem: `ajustar_marcadores` põe o marcador depois
da frase que fala da passagem principal (o texto que entra ali vem da base conferida, nunca do
modelo) e tira repetições e marcadores desconhecidos. Revisões pedem o que falta em termos que
um modelo pequeno segue (`revisao_para`: parágrafos e frases, não só contagem de palavras).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from fiat_lux.agente.contexto import ContextoDoDia
from fiat_lux.agente.selecao import Escolha
from fiat_lux.agente.verificacao import (
    LIMITES,
    MARCADORES_VALIDOS,
    TOLERANCIA,
    Checagem,
    RefPermitida,
    extrair_referencias,
)
from fiat_lux.biblia.catalogo import por_codigo
from fiat_lux.biblia.referencias import Referencia, parse_com_contexto
from fiat_lux.llm.cliente import Contabilidade, LLMClient, Pedido, chamar
from fiat_lux.llm.esquemas import Julgamento, Redacao
from fiat_lux.llm.offline import embutir
from fiat_lux.llm.prompts import carregar
from fiat_lux.noticias.classificacao import sanear
from fiat_lux.rag.busca import Candidato
from fiat_lux.textos import chave, contar_palavras

CAMPOS = ("olhar_sobre_o_dia", "reflexao", "ensinamento", "gesto", "oracao")
INTRODUCAO_P1 = "Diz a Escritura: {{P1}}."
_MARCADOR = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
_FIM_DE_FRASE = re.compile(r"(?:(?<=[.!?…])|(?<=[.!?…][\"”’)]))\s+")
# como pedir cada campo numa revisão: frases e parágrafos, que um modelo pequeno segue melhor
# que uma contagem de palavras
_FORMA = {
    "olhar_sobre_o_dia": "um parágrafo de 3 a 4 frases",
    "reflexao": "a lista dos 4 parágrafos, cada um com 4 a 5 frases",
    "oracao": "3 a 5 frases",
}
# o que acrescentar a um texto curto: pedir para "ampliar" fazia o modelo devolver o mesmo texto
_AMPLIAR = {
    "olhar_sobre_o_dia": "acrescente 1 ou 2 frases sobre o que as pessoas vivem hoje",
    "reflexao": "mantenha os parágrafos e acrescente 2 ou 3 frases novas a CADA um (uma "
    "explicação, um exemplo da vida, uma aplicação para hoje)",
    "oracao": "acrescente 1 ou 2 frases de pedido ou de louvor",
}


def _refs_candidato(c: Candidato) -> list[RefPermitida]:
    saida: list[RefPermitida] = []
    if c.caps_vers:
        (c1, v1), (c2, v2) = c.caps_vers[0], c.caps_vers[-1]
        saida.append(RefPermitida(c.livro, c1, v1, v2, c2 if c2 != c1 else None))
    for r in c.refs_canonicas:  # também no esquema eng (ex.: "Sl 23" para MS Sl 22)
        livro, cap, vers = r.split(".")
        saida.append(RefPermitida(livro, int(cap), int(vers), int(vers)))
    return saida


def permitidas(ctx: ContextoDoDia, escolha: Escolha) -> tuple[list[RefPermitida], list[str]]:
    refs: list[RefPermitida] = []
    textos: list[str] = []
    for c in [escolha.principal, *escolha.complementares]:
        refs += _refs_candidato(c)
        textos += c.textos
    if ctx.liturgia is not None:
        anteriores: dict[str, list[Referencia]] = {}
        for lt in ctx.liturgia.leituras:
            lista = anteriores.setdefault(lt.tipo, [])
            try:
                r = parse_com_contexto(lt.referencia, lista)
            except (ValueError, KeyError):
                continue
            lista.append(r)
            for iv in r.intervalos:
                refs.append(
                    RefPermitida(iv.livro, iv.cap_ini, iv.vers_ini, iv.vers_fim, iv.cap_fim)
                )
            if lt.texto:
                textos.append(lt.texto)
    return refs, textos


def rotulo_refs(refs: list[RefPermitida]) -> list[str]:
    from fiat_lux.biblia.catalogo import por_codigo

    vistos, saida = set(), []
    for r in refs:
        s = (
            f"{por_codigo(r.livro).sigla_pt} {r.capitulo}"
            + (f",{r.vers_ini}" if r.vers_ini else "")
            + (f"-{r.vers_fim}" if r.vers_fim and r.vers_fim != r.vers_ini else "")
        )
        if s not in vistos:
            vistos.add(s)
            saida.append(s)
    return saida


def _fala_da_passagem(frase: str, c: Candidato) -> int:
    """2 se a frase cita a referência do candidato, 1 se fala do livro dele pelo nome, 0 se não."""
    refs = _refs_candidato(c)
    for livro, cap, v1, v2, _ in extrair_referencias(frase):
        if any(r.cobre(livro, cap, v1, v2) for r in refs):
            return 2
    lv = por_codigo(c.livro)
    nomes = {re.sub(r"^\d\s*", "", chave(n)) for n in (lv.nome_pt, *lv.aliases)}
    texto = f" {chave(frase)} "
    return int(any(len(n) >= 4 and f" {n} " in texto for n in nomes))


def _inserir_p1(reflexao: str, principal: Candidato) -> tuple[str, str]:
    """A reflexão com o {{P1}} depois da frase que cita a passagem principal (ou fala do livro
    dela); sem nenhuma, depois da primeira frase. Devolve também a frase escolhida."""
    texto = reflexao.strip()
    if not texto:
        return INTRODUCAO_P1, ""
    trechos = _FIM_DE_FRASE.split(texto)
    separadores = _FIM_DE_FRASE.findall(texto)
    notas = [_fala_da_passagem(t, principal) for t in trechos]
    melhor = max(notas)
    i = notas.index(melhor) if melhor else 0
    escolhida = trechos[i]
    final = "" if re.search(r"[.!?…][\"”’)]?$", escolhida) else "."
    trechos[i] = f"{escolhida}{final} {INTRODUCAO_P1}"
    partes = [trechos[0]]
    for sep, trecho in zip(separadores, trechos[1:], strict=True):
        partes += [sep, trecho]
    return "".join(partes), escolhida


def ajustar_marcadores(r: Redacao, escolha: Escolha) -> tuple[Redacao, list[str]]:
    """Garante o {{P1}} exatamente uma vez e no máximo um {{C1}} e um {{C2}} (as repetições viram
    a referência da passagem); tira marcadores que não existem. Devolve o que foi mudado."""
    ajustes: list[str] = []
    rotulos = {"P1": escolha.principal.rotulo()}
    for i, c in enumerate(escolha.complementares[:2], 1):
        rotulos[f"C{i}"] = c.rotulo()
    vistos: set[str] = set()

    def trocar(m: re.Match[str]) -> str:
        nome = m.group(1)
        if nome not in MARCADORES_VALIDOS or nome not in rotulos:
            ajustes.append(f"marcador desconhecido retirado: {m.group(0)}")
            return ""
        if nome in vistos:
            ajustes.append(f"{{{{{nome}}}}} repetido virou a referência")
            return rotulos[nome]
        vistos.add(nome)
        return m.group(0)

    campos = {c: re.sub(r"[ \t]{2,}", " ", _MARCADOR.sub(trocar, getattr(r, c))) for c in CAMPOS}
    if "P1" not in vistos:
        campos["reflexao"], frase = _inserir_p1(campos["reflexao"], escolha.principal)
        ajustes.append(f"{{{{P1}}}} inserido depois de: {frase[:80]!r}")
    if not ajustes:
        return r, []
    return r.model_copy(update=campos), ajustes


def revisao_para(checagens: Sequence[Checagem], r: Redacao) -> list[str]:
    """O que pedir na revisão: cada portão reprovado e, para os comprimentos, quanto falta (ou
    sobra), em frases e parágrafos, com o texto anterior para o modelo ampliar em vez de
    recomeçar."""
    pedidos = [f"{c.id}: {c.motivo}" for c in checagens if not c.ok and c.id != "V4"]
    so_comprimento = not pedidos
    if any(c.id == "V4" and not c.ok for c in checagens):
        for campo, (lo, hi) in LIMITES.items():
            texto = getattr(r, campo)
            n = contar_palavras(_MARCADOR.sub(" ", texto))
            if so_comprimento and lo * (1 - TOLERANCIA) <= n <= hi * (1 + TOLERANCIA):
                # o que estava certo volta igual: reescrito do zero, encolhe ou cresce demais
                pedidos.append(f"{campo}: está certo; repita-o exatamente assim: «{texto.strip()}»")
            elif n < lo * (1 - TOLERANCIA):
                pedidos.append(
                    f"{campo}: ficou com {n} palavras e precisa de {lo} a {hi} "
                    f"({_FORMA[campo]}): {_AMPLIAR[campo]}. Texto anterior, para AMPLIAR (não "
                    f"encurte nem repita igual): «{texto.strip()}»"
                )
            elif n > hi * (1 + TOLERANCIA):
                pedidos.append(
                    f"{campo}: ficou com {n} palavras e pode ter no máximo {hi}; escreva "
                    f"{_FORMA[campo]}, mais enxuto."
                )
        pedidos += [
            f"V4: {p}"
            for p in next(c.motivo for c in checagens if c.id == "V4").split("; ")
            if not p.startswith(tuple(LIMITES))
        ]
    return pedidos


def _passagem(c: Candidato, rotulo_deutero: str | None) -> dict[str, object]:
    return {
        "ref": c.rotulo(),
        "texto": c.texto,
        **({"aviso": rotulo_deutero} if c.deutero and rotulo_deutero else {}),
    }


def redigir(
    ctx: ContextoDoDia,
    escolha: Escolha,
    llm: LLMClient,
    modelo: str,
    temperatura: float = 0.7,
    revisao: list[str] | None = None,
    contabilidade: Contabilidade | None = None,
) -> Redacao:
    refs, _ = permitidas(ctx, escolha)
    m = ctx.medicoes.get("composto")
    dados = {
        "data": ctx.data.isoformat(),
        "celebracao": ctx.liturgia.celebracao if ctx.liturgia else None,
        "tempo": ctx.tempo,
        "semana": ctx.liturgia.semana if ctx.liturgia else None,
        "evangelho_ref": ctx.evangelho_ref,
        "evangelho_resumo": ctx.evangelho_resumo,
        "temas": [
            {
                "categoria": t.categoria,
                "rotulo": sanear(t.rotulo),
                "escopo": t.escopo,
                "gravidade": t.gravidade,
            }
            for t in ctx.temas
        ],
        "evento_dominante": sanear(ctx.evento_dominante.rotulo) if ctx.evento_dominante else None,
        "medidor": {"indice": m.indice, "faixa": m.faixa} if m else None,
        "sensibilidades": sorted(ctx.sensibilidades),
        "passagens": {
            "P1": _passagem(escolha.principal, ctx.perfil.rotulo_deutero),
            "C1": _passagem(escolha.complementares[0], ctx.perfil.rotulo_deutero),
            "C2": _passagem(escolha.complementares[1], ctx.perfil.rotulo_deutero)
            if len(escolha.complementares) > 1
            else None,
        },
        "ligacao_liturgica": escolha.ligacao_liturgica,
        "PERMITIDAS": rotulo_refs(refs),
    }
    usuario = embutir(dados)
    if revisao:
        usuario += (
            "\n<revisao>\nO rascunho anterior foi reprovado. Corrija:\n- "
            + "\n- ".join(revisao)
            + "\n</revisao>"
        )
    return chamar(
        llm,
        Pedido("redacao", modelo, carregar("redacao").texto, usuario, temperatura, 8192),
        Redacao,
        contabilidade,
    )


def julgar(
    texto_final: str,
    llm: LLMClient,
    modelo: str,
    temperatura: float = 0.0,
    contabilidade: Contabilidade | None = None,
) -> Julgamento:
    return chamar(
        llm,
        Pedido(
            "juiz",
            modelo,
            carregar("juiz").texto,
            embutir(texto_final, "mensagem"),
            temperatura,
            4000,
        ),
        Julgamento,
        contabilidade,
    )
