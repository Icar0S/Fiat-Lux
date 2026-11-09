"""Clusterização de manchetes (plano §8.3.3).

Aglomerativa (cosseno, ligação média, limiar de distância). Relevância =
n_artigos × (1 + ln n_fontes) × fator de recência. Tamanho mínimo: 2 (mundial e nacional)
ou 1 (regional, de pouco volume).
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
from numpy.typing import NDArray
from sklearn.cluster import AgglomerativeClustering

from fiat_lux.noticias.modelos import Artigo, Cluster, Escopo

TAMANHO_MINIMO: dict[str, int] = {"mundial": 2, "nacional": 2, "regional": 1}


def _recencia(artigos: list[Artigo], referencia: dt.datetime) -> float:
    fatores = []
    for a in artigos:
        if a.publicado_em is None:
            fatores.append(0.7)
            continue
        horas = max(0.0, (referencia - a.publicado_em).total_seconds() / 3600)
        fatores.append(math.exp(-horas / 36))
    return sum(fatores) / len(fatores) if fatores else 0.5


def relevancia(artigos: list[Artigo], referencia: dt.datetime) -> float:
    fontes = {a.fonte_nome or a.dominio for a in artigos}
    return len(artigos) * (1 + math.log(max(1, len(fontes)))) * _recencia(artigos, referencia)


def _sem_vetores_nulos(v: NDArray[np.float32]) -> NDArray[np.float32]:
    """O cosseno não aceita vetor nulo (manchete sem nenhum termo conhecido): cada um ganha uma
    dimensão própria, ortogonal às demais, e fica num grupo só seu."""
    nulos = np.flatnonzero(np.linalg.norm(v, axis=1) == 0)
    if not len(nulos):
        return v
    extra = np.zeros((v.shape[0], len(nulos)), dtype=np.float32)
    extra[nulos, np.arange(len(nulos))] = 1.0
    return np.hstack([v, extra]).astype(np.float32)


def agrupar(
    artigos: list[Artigo],
    vetores: NDArray[np.float32],
    escopo: Escopo,
    limiar: float,
    referencia: dt.datetime | None = None,
    minimo: int | None = None,
) -> list[Cluster]:
    if not artigos:
        return []
    ref = referencia or dt.datetime.now(dt.UTC)
    if len(artigos) == 1:
        rotulos = np.zeros(1, dtype=int)
    else:
        modelo = AgglomerativeClustering(
            n_clusters=None, metric="cosine", linkage="average", distance_threshold=limiar
        )
        rotulos = modelo.fit_predict(_sem_vetores_nulos(np.asarray(vetores, dtype=np.float32)))
    grupos: dict[int, list[Artigo]] = {}
    for art, r in zip(artigos, rotulos, strict=True):
        grupos.setdefault(int(r), []).append(art)
    tam_min = minimo if minimo is not None else TAMANHO_MINIMO.get(escopo, 2)
    clusters = [
        Cluster(
            escopo=escopo,
            artigos=g,
            relevancia=round(relevancia(g, ref), 4),
            n_fontes=len({a.fonte_nome or a.dominio for a in g}),
        )
        for g in grupos.values()
        if len(g) >= tam_min
    ]
    clusters.sort(key=lambda c: -c.relevancia)
    return clusters


def evento_dominante(clusters: list[Cluster], razao: float = 3.0) -> Cluster | None:
    """ "Dia marcado por…": o 1º cluster tem relevância > `razao` × a do 2º."""
    if not clusters:
        return None
    if len(clusters) == 1:
        return clusters[0] if clusters[0].relevancia >= 3 else None
    a, b = clusters[0], clusters[1]
    return a if b.relevancia > 0 and a.relevancia > razao * b.relevancia else None
