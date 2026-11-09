"""Arquivo das mensagens em `saidas/` (plano §8.7)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path


def caminho(raiz: Path, data: dt.date, tipo: str = "diaria", perfil: str = "catolico") -> Path:
    sufixo = "" if perfil == "catolico" else f"-{perfil}"
    if tipo == "semanal":
        ano, semana, _ = data.isocalendar()
        return raiz / f"{ano:04d}" / "semanas" / f"{ano:04d}-W{semana:02d}{sufixo}.md"
    return raiz / f"{data:%Y}" / f"{data:%m}" / f"{data.isoformat()}{sufixo}.md"


def arquivar(
    raiz: Path, data: dt.date, conteudo: str, tipo: str = "diaria", perfil: str = "catolico"
) -> Path:
    destino = caminho(raiz, data, tipo, perfil)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8")
    return destino
