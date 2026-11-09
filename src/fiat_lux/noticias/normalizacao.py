"""Normalização de artigos (plano §8.3.2): URL canônica, título limpo, idioma."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fiat_lux.noticias.modelos import Artigo
from fiat_lux.textos import palavras

_PARAMS_RASTREIO = re.compile(
    r"^(utm_.*|fbclid|gclid|mc_cid|mc_eid|igshid|ref|ref_src|amp|outputType|cmpid)$", re.IGNORECASE
)
_SUFIXO = re.compile(r"\s+[-–|]\s+[^-–|]{2,40}$")

_STOP_PT = frozenset(
    [
        "de",
        "da",
        "do",
        "das",
        "dos",
        "que",
        "em",
        "para",
        "com",
        "não",
        "uma",
        "por",
        "mais",
        "como",
        "mas",
        "foi",
        "ao",
        "ele",
        "das",
        "tem",
        "são",
        "seu",
        "sua",
        "ou",
        "ser",
        "quando",
        "muito",
        "nos",
        "já",
        "está",
        "também",
        "só",
        "pelo",
        "pela",
        "até",
        "isso",
        "ela",
        "entre",
        "era",
        "depois",
        "sem",
        "mesmo",
        "aos",
        "ter",
        "seus",
        "quem",
        "nas",
        "me",
        "esse",
        "eles",
        "estão",
        "você",
        "tinha",
        "foram",
        "essa",
        "num",
        "nem",
        "suas",
        "meu",
        "às",
        "minha",
        "têm",
        "numa",
        "pelos",
        "elas",
        "havia",
        "seja",
        "qual",
        "será",
        "nós",
        "tenho",
        "lhe",
        "deles",
        "essas",
        "esses",
        "pelas",
        "este",
        "fosse",
        "dele",
        "após",
        "diz",
        "sobre",
    ]
)
_STOP_EN = frozenset(
    [
        "the",
        "of",
        "and",
        "to",
        "in",
        "is",
        "for",
        "on",
        "that",
        "with",
        "as",
        "by",
        "at",
        "from",
        "it",
        "be",
        "are",
        "was",
        "this",
        "an",
        "has",
        "have",
        "after",
        "over",
        "says",
        "said",
        "new",
        "will",
        "its",
        "who",
    ]
)
_STOP_ES = frozenset(
    [
        "el",
        "los",
        "las",
        "del",
        "por",
        "para",
        "con",
        "una",
        "según",
        "tras",
        "sobre",
        "desde",
        "pero",
        "también",
        "como",
        "más",
    ]
)


def url_canonica(url: str) -> str:
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if not _PARAMS_RASTREIO.match(k)
        ]
    )
    caminho = re.sub(r"/amp/?$", "/", p.path)
    caminho = caminho.rstrip("/") or "/"
    return urlunsplit(
        (p.scheme.lower() or "https", p.netloc.lower().removeprefix("www."), caminho, query, "")
    )


def hash_url(url: str) -> str:
    return hashlib.sha256(url_canonica(url).encode("utf-8")).hexdigest()


def dominio(url: str) -> str | None:
    try:
        host = urlsplit(url).netloc.lower()
    except ValueError:
        return None
    return host.removeprefix("www.") or None


def limpar_titulo(titulo: str, sufixos: tuple[str, ...] = ()) -> str:
    t = re.sub(r"\s+", " ", titulo or "").strip()
    for s in sufixos:
        if t.endswith(s):
            t = t[: -len(s)].strip()
    t = _SUFIXO.sub("", t).strip()
    return t


def detectar_idioma(texto: str) -> str | None:
    """Heurística por palavras funcionais (pt/en/es). `None` se inconclusivo."""
    ps = palavras(texto)
    if not ps:
        return None
    contagem = {
        "pt": sum(p in _STOP_PT for p in ps)
        + sum(1 for p in ps if p.endswith(("ção", "ções", "ão"))),
        "en": sum(p in _STOP_EN for p in ps),
        "es": sum(p in _STOP_ES for p in ps),
    }
    idioma, n = max(contagem.items(), key=lambda kv: kv[1])
    return idioma if n > 0 else None


def normalizar(artigo: Artigo, sufixos: tuple[str, ...] = ()) -> Artigo:
    titulo = limpar_titulo(artigo.titulo, sufixos)
    return artigo.model_copy(
        update={
            "titulo": titulo,
            "dominio": artigo.dominio or dominio(artigo.url),
            "idioma": artigo.idioma or detectar_idioma(titulo),
            "url_hash": hash_url(artigo.url),
        }
    )
