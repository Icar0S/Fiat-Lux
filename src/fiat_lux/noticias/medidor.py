"""Índice de Tensão (plano §8.3.5).

    z_T = (μ_T,30d − T) / σ_T,30d        (tom mais negativo que o normal → positivo)
    z_V = (V − μ_V,30d) / σ_V,30d
    G   = gravidade média ponderada pela relevância dos top-5 clusters (0–3)
    Índice = clip(50 + 10·z_T + 5·z_V + 10·(G − 1,5), 0, 100)

Faixas: 0–29 calmo · 30–54 atenção · 55–74 tensão · 75–100 crise. Sem tom confiável (RSS),
o termo de tom sai da conta. Composto = média ponderada dos escopos disponíveis (pesos
renormalizados). `calibrando` enquanto houver menos de 30 dias de linha de base.
O tom do GDELT é uma medida automática: o índice é um SINAL, não uma verdade.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from fiat_lux.noticias.modelos import Cluster, Faixa, Medicao

Z_MAX = 3.0


@dataclass(frozen=True, slots=True)
class Formula:
    base: float = 50.0
    k_tom: float = 10.0
    k_volume: float = 5.0
    k_gravidade: float = 10.0


@dataclass(frozen=True, slots=True)
class Faixas:
    calmo: float = 29.0
    atencao: float = 54.0
    tensao: float = 74.0


def faixa(indice: float, faixas: Faixas | None = None) -> Faixa:
    faixas = faixas or FAIXAS_PADRAO
    if indice <= faixas.calmo:
        return "calmo"
    if indice <= faixas.atencao:
        return "atencao"
    if indice <= faixas.tensao:
        return "tensao"
    return "crise"


FORMULA_PADRAO = Formula()
FAIXAS_PADRAO = Faixas()


def zscore(valor: float, historico: Sequence[float], inverter: bool = False) -> float | None:
    """z limitado a ±3; `None` com menos de 3 pontos; 0 se o desvio for nulo."""
    if len(historico) < 3:
        return None
    mu = statistics.fmean(historico)
    sigma = statistics.pstdev(historico)
    if sigma == 0:
        return 0.0
    z = (mu - valor) / sigma if inverter else (valor - mu) / sigma
    return max(-Z_MAX, min(Z_MAX, z))


def gravidade_ponderada(clusters: Sequence[Cluster], top: int = 5) -> float | None:
    escolhidos = [
        c for c in sorted(clusters, key=lambda c: -c.relevancia) if c.gravidade is not None
    ][:top]
    peso = sum(c.relevancia for c in escolhidos)
    if not escolhidos or peso <= 0:
        return None
    return sum((c.gravidade or 0) * c.relevancia for c in escolhidos) / peso


def calcular(
    data: dt.date,
    escopo: str,
    volume: int,
    clusters: Sequence[Cluster],
    historico_volume: Sequence[float],
    tom: float | None = None,
    historico_tom: Sequence[float] = (),
    formula: Formula | None = None,
    faixas: Faixas | None = None,
    dias_baseline: int = 30,
    top: int = 5,
) -> Medicao:
    formula = formula or FORMULA_PADRAO
    faixas = faixas or FAIXAS_PADRAO
    z_t = zscore(tom, historico_tom, inverter=True) if tom is not None else None
    z_v = zscore(float(volume), historico_volume)
    g = gravidade_ponderada(clusters, top)
    indice = formula.base
    if z_t is not None:
        indice += formula.k_tom * z_t
    if z_v is not None:
        indice += formula.k_volume * z_v
    if g is not None:
        indice += formula.k_gravidade * (g - 1.5)
    indice = max(0.0, min(100.0, indice))
    baseline = max(len(historico_volume), len(historico_tom))
    return Medicao(
        data=data,
        escopo=escopo,
        volume=volume,
        volume_z=_r(z_v),
        tom_medio=_r(tom),
        tom_z=_r(z_t),
        gravidade_media=_r(g),
        indice=round(indice, 1),
        faixa=faixa(indice, faixas),
        calibrando=baseline < dias_baseline,
    )


def composto(
    medicoes: dict[str, Medicao], pesos: dict[str, float], faixas: Faixas | None = None
) -> Medicao | None:
    """Média ponderada dos escopos presentes; pesos renormalizados (MR4)."""
    presentes = {e: m for e, m in medicoes.items() if e in pesos and e != "composto"}
    if not presentes:
        return None
    total = sum(pesos[e] for e in presentes)
    indice = sum(m.indice * pesos[e] for e, m in presentes.items()) / total
    data = next(iter(presentes.values())).data
    return Medicao(
        data=data,
        escopo="composto",
        volume=sum(m.volume for m in presentes.values()),
        indice=round(indice, 1),
        faixa=faixa(indice, faixas),
        calibrando=any(m.calibrando for m in presentes.values()),
    )


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 3)
