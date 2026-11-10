"""Seleção em conjunto fechado (plano §8.5.3; prompt P3).

O LLM recebe 12 candidatos com id, referência e texto, e devolve ids. Validação: ids do
conjunto, principal ≠ complementares, regra de perfil e, de preferência, uma complementar de
outro testamento. Resposta inválida ⇒ nova tentativa com o erro explicado; segunda falha ⇒
seleção determinística pelo escore S (direto, se o provedor estiver fora: `ErroPermanente`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fiat_lux.agente.contexto import ContextoDoDia
from fiat_lux.llm.cliente import (
    Contabilidade,
    ErroLLM,
    ErroPermanente,
    LLMClient,
    Pedido,
    chamar,
    motivo_curto,
)
from fiat_lux.llm.esquemas import Selecao
from fiat_lux.llm.offline import embutir
from fiat_lux.llm.prompts import carregar
from fiat_lux.logs import log
from fiat_lux.noticias.classificacao import sanear
from fiat_lux.rag.busca import Candidato


@dataclass(slots=True)
class Escolha:
    principal: Candidato
    complementares: list[Candidato]
    temas_atendidos: list[str] = field(default_factory=list)
    ligacao_liturgica: str = ""
    justificativa: str = ""
    alertas: list[str] = field(default_factory=list)
    metodo: str = "llm"  # llm | deterministico


def ids_curtos(cands: list[Candidato]) -> dict[str, Candidato]:
    return {f"cand_{i:02d}": c for i, c in enumerate(cands, 1)}


def validar(s: Selecao, mapa: dict[str, Candidato], perfil_evangelico: bool) -> list[str]:
    erros = []
    if s.principal not in mapa:
        erros.append(f"principal {s.principal!r} não está entre os candidatos")
    comp = [c for c in s.complementares if c]
    if len(comp) != 2:
        erros.append("são necessárias exatamente 2 complementares")
    for c in comp:
        if c not in mapa:
            erros.append(f"complementar {c!r} não está entre os candidatos")
    if s.principal in comp or len(set(comp)) != len(comp):
        erros.append("principal e complementares devem ser todas diferentes")
    if perfil_evangelico and any(mapa[x].deutero for x in [s.principal, *comp] if x in mapa):
        erros.append("deuterocanônico não é permitido no perfil evangélico")
    return erros


def deterministica(cands: list[Candidato], motivo: str) -> Escolha:
    ordem = sorted(cands, key=lambda c: -c.escores.get("S", 0.0))
    principal = ordem[0]
    resto = ordem[1:]
    outro_testamento = next((c for c in resto if c.testamento != principal.testamento), None)
    comp = [c for c in resto if c.livro != principal.livro][:2] or resto[:2]
    if outro_testamento is not None and outro_testamento not in comp:
        comp = [comp[0], outro_testamento] if comp else [outro_testamento]
    return Escolha(principal, comp[:2], metodo="deterministico", alertas=[motivo])


def selecionar(
    ctx: ContextoDoDia,
    cands: list[Candidato],
    llm: LLMClient | None,
    modelo: str,
    temperatura: float = 0.2,
    contabilidade: Contabilidade | None = None,
) -> Escolha:
    if len(cands) < 3:
        raise ValueError("são necessários ao menos 3 candidatos")
    mapa = ids_curtos(cands)
    if llm is None:
        return deterministica(cands, "sem LLM: seleção pelo escore")
    dados = {
        "data": ctx.data.isoformat(),
        "celebracao": ctx.liturgia.celebracao if ctx.liturgia else None,
        "tempo": ctx.tempo,
        "evangelho_ref": ctx.evangelho_ref,
        "evangelho_resumo": ctx.evangelho_resumo,
        "temas": [
            {"categoria": t.categoria, "rotulo": sanear(t.rotulo), "gravidade": t.gravidade}
            for t in ctx.temas
        ],
        "candidatos": [
            {
                "id": cid,
                "ref": c.rotulo(),
                "livro": c.livro,
                "testamento": c.testamento,
                "deuterocanonico": c.deutero,
                "texto": c.texto,
                **(
                    {"contexto": " ".join(c.contexto.split()[:150])}
                    if c.contexto and c.contexto != c.texto
                    else {}
                ),
                "escore": round(c.escores.get("S", 0.0), 4),
            }
            for cid, c in mapa.items()
        ],
    }
    sistema = carregar("selecao").texto
    usuario = embutir(dados)
    correcao: list[str] = []  # só erros de validação voltam ao modelo; falha da API não
    ultimo = ""
    for tentativa in range(2):
        u = (
            usuario
            if not correcao
            else f"{usuario}\n\nA resposta anterior foi inválida: {'; '.join(correcao)}. Corrija."
        )
        try:
            s = chamar(
                llm,
                Pedido("selecao", modelo, sistema, u, temperatura, 6000),
                Selecao,
                contabilidade,
            )
        except ErroPermanente as e:
            return deterministica(cands, f"seleção pelo escore ({motivo_curto(e)})")
        except ErroLLM as e:
            log().warning("selecao_llm_falhou", tentativa=tentativa, erro=str(e))
            ultimo = f"seleção do LLM falhou duas vezes: {e}"
            continue
        erros = validar(s, mapa, ctx.perfil.nome == "evangelico")
        if not erros:
            return Escolha(
                principal=mapa[s.principal],
                complementares=[mapa[c] for c in s.complementares],
                temas_atendidos=s.temas_atendidos,
                ligacao_liturgica=s.ligacao_liturgica,
                justificativa=s.justificativa,
                alertas=s.alertas,
                metodo="llm",
            )
        correcao = erros
        ultimo = f"seleção do LLM inválida duas vezes: {'; '.join(erros)}"
    return deterministica(cands, ultimo)
