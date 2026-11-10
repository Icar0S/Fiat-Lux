"""Logs estruturados (structlog) em JSON ou console, sem segredos (plano §12)."""

from __future__ import annotations

import contextlib
import logging
import re
import sys
from collections.abc import Iterator
from typing import Any

import structlog

# token do bot do Telegram, chaves no formato sk-… (a do servidor de LLM) e cabeçalhos Bearer
_SEGREDOS = re.compile(
    r"(bot\d+:[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9._~+/=-]{8,})"
)


def _mascarar(_: Any, __: str, evento: dict[str, Any]) -> dict[str, Any]:
    for k, v in list(evento.items()):
        if isinstance(v, str):
            evento[k] = _SEGREDOS.sub("***", v)
        if k in {"chat_id", "destinatario"} and isinstance(v, str | int):
            s = str(v)
            evento[k] = (s[:2] + "…" + s[-2:]) if len(s) > 4 else "…"
    return evento


def _sem_trace(_: Any, __: str, evento: dict[str, Any]) -> dict[str, Any]:
    """No console, o traceback só aparece com --verboso (o JSON dos logs guarda sempre)."""
    if evento.pop("trace", None) is not None:
        evento["traceback"] = "fiatlux --verboso …"
    return evento


_atual: dict[str, Any] = {"json": False, "nivel": "INFO"}


def configurar_logs(json: bool = False, nivel: str = "INFO") -> None:
    _atual.update(json=json, nivel=nivel)
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=nivel)
    logging.getLogger().setLevel(nivel)
    # httpx2: cliente HTTP do huggingface_hub 2.x ("HTTP Request: HEAD … 404" a cada arquivo)
    for ruidoso in ("httpx", "httpx2", "httpcore", "urllib3", "sentence_transformers", "filelock"):
        logging.getLogger(ruidoso).setLevel(max(logging.WARNING, logging.getLevelName(nivel)))
    processadores: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _mascarar,
    ]
    if json:
        processadores.append(structlog.processors.JSONRenderer(ensure_ascii=False))
    else:
        if nivel != "DEBUG":
            processadores.append(_sem_trace)
        processadores.append(structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()))
    structlog.configure(
        processors=processadores,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(nivel)),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


@contextlib.contextmanager
def so_erros_no_console() -> Iterator[None]:
    """Para comandos que resumem os avisos no fim (`fiatlux configurar`): no console, só erros,
    até o fim do bloco. Com --verboso ou --json-logs, nada muda. Só o filtro de nível é trocado
    (e depois restaurado): o destino dos logs fica onde estava."""
    if _atual["json"] or _atual["nivel"] in {"DEBUG", "ERROR", "CRITICAL"}:
        yield
        return
    filtro = structlog.get_config()["wrapper_class"]
    raiz = logging.getLogger()
    nivel_raiz = raiz.level
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))
    raiz.setLevel(logging.ERROR)
    try:
        yield
    finally:
        structlog.configure(wrapper_class=filtro)
        raiz.setLevel(nivel_raiz)


def log(nome: str = "fiat_lux") -> Any:
    return structlog.get_logger(nome)
