"""Embeddings (plano §8.4.2; ADR-010).

- `EmbedderNeural`: sentence-transformers (padrão do plano: `intfloat/multilingual-e5-base`,
  com prefixos `query:`/`passage:`). Requer o extra `[ml]`.
- `EmbedderLexical`: TF-IDF de n-gramas de caracteres + LSA (TruncatedSVD), ajustado no
  corpus e persistido junto do índice. Sem dependências pesadas: serve ao CI e como reserva.

O índice grava qual embedder o construiu; a consulta usa sempre o mesmo.
"""

from __future__ import annotations

import pickle
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
from numpy.typing import NDArray

from fiat_lux.textos import normalizar_para_busca

Tipo = Literal["query", "passage"]


def _normalizar_linhas(m: NDArray[np.float32]) -> NDArray[np.float32]:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (m / n).astype(np.float32)


class Embedder(Protocol):
    nome: str
    dim: int

    def encode(self, textos: Sequence[str], tipo: Tipo = "passage") -> NDArray[np.float32]: ...


_MODELOS: dict[tuple[Any, ...], Any] = {}


def modelo_st(
    tipo: Literal["bi", "cross"], modelo: str, dispositivo: str | None = None, **kw: Any
) -> Any:
    """Carrega cada modelo sentence-transformers uma única vez por processo (a avaliação E2E
    e o modo semanal abrem o buscador várias vezes)."""
    chave = (tipo, modelo, dispositivo, *sorted(kw.items()))
    if chave not in _MODELOS:
        if tipo == "bi":
            from sentence_transformers import SentenceTransformer

            _MODELOS[chave] = SentenceTransformer(modelo, device=dispositivo, **kw)
        else:
            from sentence_transformers import CrossEncoder

            _MODELOS[chave] = CrossEncoder(modelo, device=dispositivo, **kw)
    return _MODELOS[chave]


class EmbedderNeural:
    def __init__(
        self,
        modelo: str = "intfloat/multilingual-e5-base",
        lote: int = 32,
        dispositivo: str | None = None,
    ) -> None:
        self.modelo_nome = modelo
        self.nome = f"neural:{modelo}"
        self._m = modelo_st("bi", modelo, dispositivo)
        obter_dim = (
            getattr(self._m, "get_embedding_dimension", None)
            or self._m.get_sentence_embedding_dimension
        )
        self.dim = int(obter_dim() or 768)
        self.lote = lote
        self.e5 = "e5" in modelo.lower()

    def encode(self, textos: Sequence[str], tipo: Tipo = "passage") -> NDArray[np.float32]:
        if not textos:
            return np.zeros((0, self.dim), dtype=np.float32)
        entrada = [f"{tipo}: {t}" for t in textos] if self.e5 else list(textos)
        vet = self._m.encode(
            entrada, batch_size=self.lote, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vet, dtype=np.float32)


class EmbedderLexical:
    """TF-IDF (char_wb 3–5 + palavras 1–2) → LSA. Determinístico (random_state fixo)."""

    def __init__(self, dim: int = 256) -> None:
        self.nome = f"lexical:lsa{dim}"
        self.dim = dim
        self._vec_c: Any = None
        self._vec_p: Any = None
        self._svd: Any = None

    def ajustar(self, textos: Sequence[str]) -> EmbedderLexical:
        from scipy.sparse import hstack
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        norm = [normalizar_para_busca(t) for t in textos]
        self._vec_c = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=2,
            max_features=200_000,
            sublinear_tf=True,
        )
        self._vec_p = TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), min_df=2, max_features=100_000, sublinear_tf=True
        )
        m = hstack([self._vec_c.fit_transform(norm), self._vec_p.fit_transform(norm)]).tocsr()
        dim = min(self.dim, m.shape[1] - 1, m.shape[0] - 1)
        self._svd = TruncatedSVD(n_components=max(2, dim), random_state=42)
        self._svd.fit(m)
        self.dim = int(self._svd.n_components)
        self.nome = f"lexical:lsa{self.dim}"
        return self

    def encode(self, textos: Sequence[str], tipo: Tipo = "passage") -> NDArray[np.float32]:
        if self._svd is None or self._vec_c is None or self._vec_p is None:
            raise RuntimeError("EmbedderLexical não ajustado (rode `fiatlux indice construir`)")
        from scipy.sparse import hstack

        if not textos:
            return np.zeros((0, self.dim), dtype=np.float32)
        norm = [normalizar_para_busca(t) for t in textos]
        m = hstack([self._vec_c.transform(norm), self._vec_p.transform(norm)]).tocsr()
        return _normalizar_linhas(np.asarray(self._svd.transform(m), dtype=np.float32))

    def salvar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(
            pickle.dumps({"vc": self._vec_c, "vp": self._vec_p, "svd": self._svd, "dim": self.dim})
        )

    @classmethod
    def carregar(cls, caminho: Path) -> EmbedderLexical:
        dados = pickle.loads(caminho.read_bytes())  # arquivo gerado localmente pelo próprio índice
        e = cls(int(dados["dim"]))
        e._vec_c, e._vec_p, e._svd = dados["vc"], dados["vp"], dados["svd"]
        e.nome = f"lexical:lsa{e.dim}"
        return e


def neural_disponivel() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def vetores_textos_curtos(textos: Sequence[str]) -> NDArray[np.float32]:
    """Vetores para agrupar manchetes sem modelo neural: TF-IDF ajustado no próprio lote."""
    from scipy.sparse import hstack
    from sklearn.feature_extraction.text import TfidfVectorizer

    if not textos:
        return np.zeros((0, 1), dtype=np.float32)
    norm = [normalizar_para_busca(t) for t in textos]
    partes = []
    for analisador, faixa in (("word", (1, 2)), ("char_wb", (3, 5))):
        try:
            partes.append(
                TfidfVectorizer(
                    analyzer=analisador, ngram_range=faixa, sublinear_tf=True
                ).fit_transform(norm)
            )
        except ValueError:  # vocabulário vazio
            continue
    if not partes:
        return np.zeros((len(textos), 1), dtype=np.float32)
    m = hstack(partes).toarray().astype(np.float32)
    return _normalizar_linhas(m)
