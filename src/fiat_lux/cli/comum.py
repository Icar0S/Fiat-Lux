"""Utilidades compartilhadas pelos comandos."""

from __future__ import annotations

import contextlib
import sys
from typing import NoReturn

from rich.console import Console

# Consoles do Windows (cp1252) não codificam "≥", "→", "✅"…: força UTF-8.
for _fluxo in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

# safe_box=False: bordas arredondadas também no console antigo do Windows e com a saída
# redirecionada, iguais às que os scripts de configuração desenham
console = Console(stderr=False, highlight=False, safe_box=False)
erro = Console(stderr=True, highlight=False, safe_box=False)


def falhar(msg: str, codigo: int = 1) -> NoReturn:
    erro.print(f"[bold red]erro:[/] {msg}")
    sys.exit(codigo)
