"""Redação com placeholders (plano §8.5.4; prompt P4) e juiz de neutralidade (P5).

O modelo escreve SEM transcrever Escritura: usa {{P1}}, {{C1}}, {{C2}}. Só pode citar
referências do conjunto permitido (leituras do dia + principal + complementares).
"""

from __future__ import annotations

from fiat_lux.agente.contexto import ContextoDoDia
from fiat_lux.agente.selecao import Escolha
from fiat_lux.agente.verificacao import RefPermitida
from fiat_lux.biblia.referencias import Referencia, parse_com_contexto
from fiat_lux.llm.cliente import Contabilidade, LLMClient, Pedido, chamar
from fiat_lux.llm.esquemas import Julgamento, Redacao
from fiat_lux.llm.offline import embutir
from fiat_lux.llm.prompts import carregar
from fiat_lux.noticias.classificacao import sanear
from fiat_lux.rag.busca import Candidato


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
