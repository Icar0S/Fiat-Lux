"""Classificação pastoral dos clusters (plano §8.3.4; prompt P1).

Lote dos top-N clusters por escopo, com até 5 manchetes cada, delimitadas como dados não
confiáveis e saneadas (§10.9). Confiança < 0,5 ⇒ "outro". Se o LLM falhar ou recusar, o
lote cai no classificador por palavras-chave da taxonomia.
"""

from __future__ import annotations

import re

from fiat_lux.llm.cliente import (
    Contabilidade,
    ErroLLM,
    ErroPermanente,
    LLMClient,
    Pedido,
    chamar,
    motivo_curto,
)
from fiat_lux.llm.esquemas import ClassificacaoLote
from fiat_lux.llm.offline import embutir
from fiat_lux.llm.prompts import carregar
from fiat_lux.logs import log
from fiat_lux.noticias.modelos import Cluster
from fiat_lux.pastoral import classificar_por_palavras, detectar_sensibilidade, taxonomia

_INJECAO = re.compile(
    r"(ignor\w*\s+(as|todas|all|the|previous|anteriores)\b.{0,40}(instru|ordens|prompt|rules)"
    r"|system\s*prompt|you are now|voc[eê] agora [eé]|aja como|act as|<\s*/?\s*(system|instru|dados|grupos)[^>]*>)",
    re.IGNORECASE,
)


def sanear(titulo: str, limite: int = 220) -> str:
    """Remove marcações e trechos com cara de comando (notícia é dado, não instrução)."""
    t = re.sub(r"<[^>]{0,200}>", " ", titulo)
    t = _INJECAO.sub("[trecho removido]", t)
    t = re.sub(r"[\x00-\x1f\x7f`{}]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limite]


def _por_palavras(c: Cluster) -> None:
    cat, conf, grav = classificar_por_palavras(c.titulos)
    c.categoria, c.confianca, c.gravidade = cat, conf, grav
    c.sensivel = detectar_sensibilidade(" ".join(c.titulos))
    c.rotulo = c.rotulo or sanear(c.titulos[0])[:140]
    c.classificado_por = "palavras"


def classificar(
    clusters: list[Cluster],
    llm: LLMClient | None,
    modelo: str,
    temperatura: float = 0.1,
    top: int = 15,
    titulos_por_cluster: int = 5,
    confianca_minima: float = 0.5,
    contabilidade: Contabilidade | None = None,
) -> list[str]:
    """Classifica (in place) os `top` clusters mais relevantes de cada escopo. Devolve avisos."""
    avisos: list[str] = []
    por_escopo: dict[str, list[Cluster]] = {}
    for c in clusters:
        por_escopo.setdefault(c.escopo, []).append(c)
    sistema = carregar("classificacao", categorias=taxonomia()).texto
    for escopo, lista in por_escopo.items():
        lote = sorted(lista, key=lambda c: -c.relevancia)[:top]
        if not lote:
            continue
        if llm is None:
            for c in lote:
                _por_palavras(c)
            continue
        grupos = [
            {
                "id": f"{escopo}-{i}",
                "manchetes": [sanear(t) for t in c.titulos[:titulos_por_cluster]],
            }
            for i, c in enumerate(lote)
        ]
        pedido = Pedido(
            tarefa="classificacao",
            modelo=modelo,
            sistema=sistema,
            usuario=f"Escopo: {escopo}.\n{embutir({'grupos': grupos})}",
            temperatura=temperatura,
            max_tokens=8000,
        )
        try:
            resp = chamar(llm, pedido, ClassificacaoLote, contabilidade)
        except ErroPermanente as e:
            # o provedor não volta nesta execução: os demais escopos vão direto às palavras-chave
            avisos.append(f"classificação das notícias por palavras-chave ({motivo_curto(e)})")
            llm = None
            for c in lote:
                _por_palavras(c)
            continue
        except ErroLLM as e:
            log().warning("classificacao_reserva", escopo=escopo, erro=str(e))
            avisos.append(f"classificação por palavras-chave no escopo {escopo} ({e})")
            for c in lote:
                _por_palavras(c)
            continue
        _aplicar(lote, resp, escopo, confianca_minima)
    return avisos


def _aplicar(
    lote: list[Cluster], resp: ClassificacaoLote, escopo: str, confianca_minima: float
) -> None:
    por_id = {g.id: g for g in resp.grupos}
    for i, c in enumerate(lote):
        g = por_id.get(f"{escopo}-{i}")
        if g is None:
            _por_palavras(c)
            continue
        c.categoria = g.categoria if g.confianca >= confianca_minima else "outro"
        c.gravidade, c.confianca, c.sensivel = g.gravidade, g.confianca, g.sensivel
        c.rotulo = g.rotulo
        c.classificado_por = "llm"
        # reforço determinístico de sensibilidade (não depende só do LLM)
        c.sensivel = c.sensivel or detectar_sensibilidade(" ".join(c.titulos))
