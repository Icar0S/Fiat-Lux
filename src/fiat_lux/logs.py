"""Logs estruturados (structlog) em JSON ou console, sem segredos (plano §12)."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

_SEGREDOS = re.compile(r"(bot\d+:[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{10,})")


def _mascarar(_: Any, __: str, evento: dict[str, Any]) -> dict[str, Any]:
    for k, v in list(evento.items()):
        if isinstance(v, str):
            evento[k] = _SEGREDOS.sub("***", v)
        if k in {"chat_id", "destinatario"} and isinstance(v, str | int):
            s = str(v)
            evento[k] = (s[:2] + "…" + s[-2:]) if len(s) > 4 else "…"
    return evento


def configurar_logs(json: bool = False, nivel: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=nivel)
    for ruidoso in ("httpx", "httpcore", "urllib3", "sentence_transformers", "filelock"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    processadores: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _mascarar,
    ]
    processadores.append(
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if json
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )
    structlog.configure(
        processors=processadores,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(nivel)),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def log(nome: str = "fiat_lux") -> Any:
    return structlog.get_logger(nome)
