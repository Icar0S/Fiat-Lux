"""Cliente do GDELT DOC 2.0 (plano §8.3.1).

Modos: `ArtList` (artigos), `TimelineTone` e `TimelineVol` (linha de base de 30 dias, que
resolve o arranque a frio). A API pede no máximo uma requisição a cada 5 s; quando excede,
responde 429 com um texto ("Please limit requests…") em vez de JSON — tratado como
`ErroLimiteGdelt`, sem tempestade de tentativas (o chamador cai para o RSS).
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

import httpx

from fiat_lux.noticias.modelos import Artigo, Escopo

URL = "https://api.gdeltproject.org/api/v2/doc/doc"
USER_AGENT = "fiat-lux/0.1 (+https://github.com/Icar0S/Fiat-Lux)"


class ErroGdelt(RuntimeError):
    pass


class ErroLimiteGdelt(ErroGdelt):
    pass


def _data_gdelt(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=dt.UTC)
        except ValueError:
            continue
    return None


class ClienteGdelt:
    def __init__(
        self,
        url: str = URL,
        intervalo_s: float = 5.5,
        timeout_s: float = 40,
        cliente: httpx.Client | None = None,
        dormir: Any = time.sleep,
    ) -> None:
        self.url = url
        self.intervalo_s = intervalo_s
        self._http = cliente or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout_s)
        self._ultima = 0.0
        self._dormir = dormir

    def fechar(self) -> None:
        self._http.close()

    def _get(self, params: dict[str, Any]) -> Any:
        espera = self.intervalo_s - (time.monotonic() - self._ultima)
        if espera > 0 and self._ultima:
            self._dormir(espera)
        for tentativa in range(2):
            self._ultima = time.monotonic()
            try:
                resp = self._http.get(self.url, params={**params, "format": "json"})
            except httpx.HTTPError as e:
                raise ErroGdelt(f"falha de rede no GDELT: {e}") from e
            corpo = resp.text.strip()
            if resp.status_code == 429 or corpo.startswith("Please limit requests"):
                if tentativa == 0:
                    self._dormir(max(10.0, self.intervalo_s * 2))
                    continue
                raise ErroLimiteGdelt("GDELT recusou por limite de taxa (429)")
            if resp.status_code >= 400:
                raise ErroGdelt(f"GDELT respondeu {resp.status_code}")
            if not corpo:
                return {}
            try:
                return resp.json()
            except ValueError as e:
                raise ErroGdelt(f"resposta não-JSON do GDELT: {corpo[:120]!r}") from e
        raise ErroLimiteGdelt("GDELT recusou por limite de taxa (429)")

    def artigos(
        self,
        consulta: str,
        escopo: Escopo,
        timespan: str = "24h",
        maxrecords: int = 250,
        sort: str = "HybridRel",
    ) -> list[Artigo]:
        dados = self._get(
            {
                "query": consulta,
                "mode": "ArtList",
                "maxrecords": maxrecords,
                "timespan": timespan,
                "sort": sort,
            }
        )
        saida: list[Artigo] = []
        for a in dados.get("articles", []) or []:
            url = a.get("url")
            titulo = a.get("title")
            if not url or not titulo:
                continue
            idioma = (a.get("language") or "").lower()
            saida.append(
                Artigo(
                    url=url,
                    titulo=titulo,
                    dominio=a.get("domain"),
                    idioma={"portuguese": "pt", "english": "en", "spanish": "es"}.get(
                        idioma, idioma or None
                    ),
                    pais_fonte=a.get("sourcecountry"),
                    escopo=escopo,
                    publicado_em=_data_gdelt(a.get("seendate")),
                    fonte_coleta="gdelt",
                )
            )
        return saida

    def serie(
        self, consulta: str, modo: str = "TimelineTone", timespan: str = "30d"
    ) -> list[tuple[dt.date, float]]:
        """Série diária (média por dia) de `TimelineTone` ou `TimelineVol`."""
        dados = self._get({"query": consulta, "mode": modo, "timespan": timespan})
        por_dia: dict[dt.date, list[float]] = {}
        for serie in dados.get("timeline", []) or []:
            for ponto in serie.get("data", []) or []:
                d = _data_gdelt(ponto.get("date"))
                if d is None or ponto.get("value") is None:
                    continue
                por_dia.setdefault(d.date(), []).append(float(ponto["value"]))
        return sorted((d, sum(v) / len(v)) for d, v in por_dia.items())
