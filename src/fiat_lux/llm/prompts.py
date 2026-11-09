"""Prompts versionados em `llm/prompts/*.md` (templates Jinja). O SHA-256 de cada um fica
registrado na mensagem gerada (plano §9)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined

DIR = Path(__file__).resolve().parent / "prompts"
_ENV = Environment(autoescape=False, undefined=StrictUndefined, keep_trailing_newline=False)

NOMES = (
    "classificacao",
    "consultas",
    "selecao",
    "redacao",
    "juiz",
    "avaliacao",
    "resumo_evangelho",
    "semanal",
)


@dataclass(frozen=True, slots=True)
class Prompt:
    nome: str
    texto: str
    sha256: str


@cache
def _bruto(nome: str) -> str:
    return (DIR / f"{nome}.md").read_text(encoding="utf-8")


def carregar(nome: str, **contexto: Any) -> Prompt:
    """Renderiza o prompt. O hash é do template (versão), não do texto renderizado."""
    bruto = _bruto(nome)
    texto = _ENV.from_string(bruto).render(**contexto).strip()
    return Prompt(nome, texto, hashlib.sha256(bruto.encode("utf-8")).hexdigest())


def hash_conjunto(nomes: tuple[str, ...] = NOMES) -> str:
    """Hash combinado dos templates (curto), gravado em `mensagens.hash_prompts`."""
    h = hashlib.sha256()
    for n in nomes:
        h.update(n.encode())
        h.update(_bruto(n).encode("utf-8"))
    return h.hexdigest()[:16]
