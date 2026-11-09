"""Deduplicação (plano §8.3.2): URL exata e títulos quase iguais no mesmo escopo e dia.

Duplicata aproximada: `token_set_ratio ≥ 90` ou cosseno ≥ 0,92 entre vetores de títulos.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from numpy.typing import NDArray
from rapidfuzz import fuzz

from fiat_lux.noticias.modelos import Artigo
from fiat_lux.textos import chave

Vetorizador = Callable[[Sequence[str]], NDArray[np.float32]]


def deduplicar(
    artigos: list[Artigo],
    limiar_titulo: int = 90,
    limiar_cosseno: float = 0.92,
    vetorizar: Vetorizador | None = None,
) -> list[Artigo]:
    vistos: set[str] = set()
    unicos: list[Artigo] = []
    for a in artigos:
        if a.url_hash and a.url_hash in vistos:
            continue
        vistos.add(a.url_hash)
        unicos.append(a)
    if len(unicos) < 2:
        return unicos
    chaves = [chave(a.titulo) for a in unicos]
    vet = vetorizar([a.titulo for a in unicos]) if vetorizar else None
    manter: list[int] = []
    for i, k in enumerate(chaves):
        dup = False
        for j in manter:
            if unicos[i].escopo != unicos[j].escopo:
                continue
            if fuzz.token_set_ratio(k, chaves[j]) >= limiar_titulo:
                dup = True
                break
            if vet is not None and float(vet[i] @ vet[j]) >= limiar_cosseno:
                dup = True
                break
        if not dup:
            manter.append(i)
    return [unicos[i] for i in manter]


def precisao_dedup(pares: list[tuple[str, str, bool]], limiar_titulo: int = 90) -> float:
    """Precisão em pares anotados (título_a, título_b, é_duplicata) — meta ≥ 95% (Fase 3)."""
    if not pares:
        return 1.0
    acertos = sum(
        (fuzz.token_set_ratio(chave(a), chave(b)) >= limiar_titulo) == dup for a, b, dup in pares
    )
    return acertos / len(pares)
