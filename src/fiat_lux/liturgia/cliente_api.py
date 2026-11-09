"""Cliente da API de liturgia v2 (plano §8.2.1).

    GET /v2/                         → dia corrente
    GET /v2/?dia=DD&mes=MM&ano=AAAA  → dia específico
    GET /v2/?periodo=7               → próximos 7 dias (ignora dia/mes/ano)

404 ⇒ não há liturgia para a data (aciona o fallback). Timeout de 10 s e 3 tentativas
com backoff exponencial. User-Agent genérico, sem dados pessoais.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from fiat_lux.liturgia.modelos import RespostaV2

USER_AGENT = "fiat-lux/0.1 (+https://github.com/Icar0S/Fiat-Lux)"


class ErroApiLiturgia(RuntimeError):
    pass


def _transitorio(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


class ClienteLiturgia:
    def __init__(
        self,
        url_base: str = "https://liturgia.up.railway.app/v2/",
        timeout_s: float = 10,
        tentativas: int = 3,
        cliente: httpx.Client | None = None,
    ) -> None:
        self.url_base = url_base
        self.tentativas = tentativas
        self._http = cliente or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=timeout_s, follow_redirects=True
        )

    def fechar(self) -> None:
        self._http.close()

    def _get(self, params: dict[str, Any]) -> Any:
        @retry(
            retry=retry_if_exception(_transitorio),
            stop=stop_after_attempt(self.tentativas),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        )
        def chamar() -> Any:
            resp = self._http.get(self.url_base, params=params)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

        try:
            return chamar()
        except (httpx.HTTPError, ValueError) as e:
            raise ErroApiLiturgia(f"falha na API de liturgia: {e}") from e

    def dia(self, data: dt.date) -> RespostaV2 | None:
        dados = self._get({"dia": data.day, "mes": data.month, "ano": data.year})
        if dados is None:
            return None
        return RespostaV2.model_validate(dados)

    def hoje(self) -> RespostaV2 | None:
        dados = self._get({})
        return None if dados is None else RespostaV2.model_validate(dados)

    def periodo(self, dias: int = 7) -> list[RespostaV2]:
        dados = self._get({"periodo": min(max(dias, 1), 7)})
        if not dados:
            return []
        if isinstance(dados, dict):
            dados = [dados]
        return [RespostaV2.model_validate(x) for x in dados]
