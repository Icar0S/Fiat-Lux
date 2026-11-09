"""Coleta por RSS/Atom (plano §8.3.1): regional e fallback dos demais escopos.

Guarda só título, link, data e domínio — nada de corpo de artigo (§13.5). No Google News,
o veículo vem em `<source>`.
"""

from __future__ import annotations

import calendar
import datetime as dt
from typing import Any

import feedparser
import httpx

from fiat_lux.noticias.modelos import Artigo, Escopo
from fiat_lux.noticias.normalizacao import dominio

USER_AGENT = "Mozilla/5.0 (compatible; fiat-lux/0.1; +https://github.com/Icar0S/Fiat-Lux)"


class ErroRss(RuntimeError):
    pass


def _data(entrada: Any) -> dt.datetime | None:
    for campo in ("published_parsed", "updated_parsed"):
        t = entrada.get(campo)
        if t:
            return dt.datetime.fromtimestamp(calendar.timegm(t), tz=dt.UTC)
    return None


def interpretar(
    conteudo: bytes, nome: str, escopo: Escopo, max_itens: int | None = None
) -> list[Artigo]:
    feed = feedparser.parse(conteudo)
    saida: list[Artigo] = []
    for e in feed.entries[: max_itens or None]:
        titulo = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        if not titulo or not link:
            continue
        fonte = e.get("source") or {}
        fonte_nome = fonte.get("title") if isinstance(fonte, dict) else None
        fonte_url = fonte.get("href") if isinstance(fonte, dict) else None
        saida.append(
            Artigo(
                url=link,
                titulo=titulo,
                dominio=dominio(fonte_url) if fonte_url else dominio(link),
                fonte_nome=fonte_nome,
                escopo=escopo,
                publicado_em=_data(e),
                fonte_coleta=f"rss:{nome}",
            )
        )
    return saida


class ClienteRss:
    def __init__(self, timeout_s: float = 25, cliente: httpx.Client | None = None) -> None:
        self._http = cliente or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=timeout_s, follow_redirects=True
        )

    def fechar(self) -> None:
        self._http.close()

    def coletar(
        self, url: str, nome: str, escopo: Escopo, max_itens: int | None = None
    ) -> list[Artigo]:
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ErroRss(f"{nome}: {e}") from e
        return interpretar(resp.content, nome, escopo, max_itens)
