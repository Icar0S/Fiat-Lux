"""Rerank (plano §8.4.3): cross-encoder `BAAI/bge-reranker-v2-m3` quando disponível
(extra `[ml]`); senão, cosseno TF-IDF consulta × texto. Escores em [0, 1]."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

from fiat_lux.rag.embeddings import modelo_st, vetores_textos_curtos


class Reranker(Protocol):
    nome: str

    def pontuar(self, consulta: str, textos: Sequence[str]) -> list[float]: ...


class RerankerNeural:
    def __init__(self, modelo: str = "BAAI/bge-reranker-v2-m3", max_length: int = 512) -> None:
        self.nome = f"neural:{modelo}"
        self._m = modelo_st("cross", modelo, max_length=max_length)

    def pontuar(self, consulta: str, textos: Sequence[str]) -> list[float]:
        if not textos:
            return []
        logits = self._m.predict(
            [(consulta, t) for t in textos], batch_size=16, show_progress_bar=False
        )
        return [1 / (1 + math.exp(-float(x))) for x in logits]


class RerankerLexical:
    nome = "lexical:tfidf"

    def pontuar(self, consulta: str, textos: Sequence[str]) -> list[float]:
        if not textos:
            return []
        m = vetores_textos_curtos([consulta, *textos])
        return [max(0.0, float(m[0] @ m[i + 1])) for i in range(len(textos))]


def criar_reranker(usar: bool, modelo: str) -> Reranker:
    if usar:
        try:
            return RerankerNeural(modelo)
        except ImportError:
            pass
    return RerankerLexical()
