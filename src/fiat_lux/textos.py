"""Utilitários de texto: acentos, chaves de comparação, tokens e variantes PT-PT → PT-BR."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

_ESPACOS = re.compile(r"\s+")
_NAO_ALFANUM = re.compile(r"[^0-9a-z]+")
_PALAVRA = re.compile(r"[0-9a-záàâãäéèêëíìîïóòôõöúùûüçñ]+", re.IGNORECASE)


def sem_acentos(texto: str) -> str:
    """Remove diacríticos preservando as letras-base ("Gênesis" → "Genesis")."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_espacos(texto: str) -> str:
    return _ESPACOS.sub(" ", texto).strip()


def chave(texto: str) -> str:
    """Chave de comparação: minúsculas, sem acentos, só [0-9a-z] separados por espaço."""
    t = sem_acentos(texto).casefold()
    return normalizar_espacos(_NAO_ALFANUM.sub(" ", t))


def chave_compacta(texto: str) -> str:
    """Como `chave`, mas sem espaços ("1 Cor" → "1cor")."""
    return chave(texto).replace(" ", "")


def slug_ascii(texto: str) -> str:
    """Nome de arquivo ASCII: "1 Coríntios" → "1-Corintios"."""
    t = sem_acentos(texto)
    t = re.sub(r"[^0-9A-Za-z]+", "-", t).strip("-")
    return t


def palavras(texto: str) -> list[str]:
    """Palavras em minúsculas, sem acentos."""
    return [sem_acentos(p).casefold() for p in _PALAVRA.findall(texto)]


def contar_palavras(texto: str) -> int:
    return len(_PALAVRA.findall(texto))


@lru_cache(maxsize=4)
def _carregar_variantes(caminho: str) -> dict[str, str]:
    mapa: dict[str, str] = {}
    p = Path(caminho)
    if not p.is_file():
        return mapa
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = linha.split("\t")
        if len(partes) < 2:
            continue
        origem, destino = chave(partes[0]), chave(partes[1])
        if origem and destino and origem != destino:
            mapa[origem] = destino
    return mapa


def variantes_ortograficas(caminho: Path | None = None) -> dict[str, str]:
    """Mapa PT-PT → PT-BR (formas já normalizadas por `chave`)."""
    if caminho is None:
        from fiat_lux.config import dir_config

        caminho = dir_config() / "variantes_ortograficas.tsv"
    return _carregar_variantes(str(caminho))


def normalizar_para_busca(texto: str, variantes: dict[str, str] | None = None) -> str:
    """Forma canônica para indexação e consulta: sem acentos, minúsculas e PT-BR.

    Aplicada igualmente ao texto indexado e às consultas, equivale à expansão bidirecional
    de variantes do plano (§8.4.2).
    """
    if variantes is None:
        variantes = variantes_ortograficas()
    return " ".join(variantes.get(p, p) for p in palavras(texto))


def truncar(texto: str, limite: int, reticencias: str = "…") -> str:
    if len(texto) <= limite:
        return texto
    corte = texto[: limite - len(reticencias)].rsplit(" ", 1)[0]
    return corte + reticencias
