"""Seleção em conjunto fechado (plano §8.5.3; prompt P3).

O LLM recebe 12 candidatos com id, referência e texto, e devolve ids. Modelos pequenos às vezes
devolvem a referência ("Lc 17,16") ou o texto do candidato no lugar do id: isso vale como o
candidato correspondente (`resolver_id`), e só candidato da lista vale. Validação: ids do
conjunto, principal ≠ complementares, regra de perfil e, de preferência, uma complementar de
outro testamento. Resposta inválida ⇒ nova tentativa com o erro explicado; segunda falha ⇒
seleção determinística pelo escore S (direto, se o provedor estiver fora: `ErroPermanente`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from fiat_lux.agente.contexto import ContextoDoDia
from fiat_lux.biblia.referencias import tentar_parse
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
from fiat_lux.textos import chave

_ID = re.compile(r"\s*(?:cand(?:idato)?[\s_\-]*)?0*(\d{1,2})\s*", re.IGNORECASE)
_REF_NO_INICIO = re.compile(
    r"\s*\(?\s*((?:[1-3]\s?)?[A-Za-zÀ-ÿ]+\.?\s*\d{1,3}"
    r"(?:\s*[,:]\s*\d{1,3}[a-z]?(?:\s*[-–]\s*\d{1,3}[a-z]?)?)?)"
)
_MIN_PALAVRAS_TEXTO = 6  # trecho mais curto que isso não identifica um candidato pelo texto


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


def _mesma_ref(valor: str, c: Candidato) -> bool:
    """`valor` começa pela referência do candidato ("Lc 17,16", "Lucas 17:16", "(Lc 17,16) E…")."""
    m = _REF_NO_INICIO.match(valor)
    if m is None or not c.caps_vers:
        return False
    ref = tentar_parse(m.group(1).replace(":", ","), "nativo")
    if ref is None or ref.livro != c.livro or len(ref.intervalos) != 1:
        return False
    iv = ref.intervalos[0]
    (c1, v1), (c2, v2) = c.caps_vers[0], c.caps_vers[-1]
    return (iv.cap_ini, iv.vers_ini) == (c1, v1) and iv.fim == (c2, v2)


def _pelo_texto(valor: str, mapa: dict[str, Candidato]) -> str | None:
    """O candidato cujo texto o modelo copiou (inteiro ou um trecho), se só um combina."""
    k = chave(valor)
    if len(k.split()) < _MIN_PALAVRAS_TEXTO:
        return None
    achados = [cid for cid, c in mapa.items() if fuzz.partial_ratio(k, chave(c.texto)) >= 95]
    return achados[0] if len(achados) == 1 else None


def resolver_id(valor: str, mapa: dict[str, Candidato]) -> str | None:
    """O id do candidato que `valor` indica: o próprio id ("cand_01", "cand 1", "1"), a referência
    ou o texto do candidato. None se não indica nenhum, ou mais de um."""
    if valor in mapa:
        return valor
    m = _ID.fullmatch(valor)
    if m is not None:
        cid = f"cand_{int(m.group(1)):02d}"
        return cid if cid in mapa else None
    pela_ref = [cid for cid, c in mapa.items() if _mesma_ref(valor, c)]
    if len(pela_ref) == 1:
        return pela_ref[0]
    return _pelo_texto(valor, mapa) if not pela_ref else None


def normalizar(s: Selecao, mapa: dict[str, Candidato]) -> tuple[Selecao, list[str]]:
    """A seleção com ids no lugar de referências e textos, e o que foi trocado (para o log). O
    que não indica nenhum candidato fica como veio: a validação o recusa."""
    trocas: list[str] = []

    def troca(valor: str) -> str:
        cid = resolver_id(valor, mapa)
        if cid is None or cid == valor:
            return valor
        trocas.append(f"{valor[:40]!r} → {cid}")
        return cid

    principal = troca(s.principal)
    complementares = [troca(c) for c in s.complementares if c]
    return s.model_copy(update={"principal": principal, "complementares": complementares}), trocas


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
        s, trocas = normalizar(s, mapa)
        if trocas:
            log().info("selecao_ids_pela_referencia", trocas=trocas)
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
