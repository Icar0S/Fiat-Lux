# ADR-001: Python 3.12 + uv

- **Status:** aceito (2026-11-09)

## Contexto

O projeto é um pipeline de dados + NLP + LLM, executado num cron e localmente no Windows do autor.

## Decisão

Python 3.12 gerenciado pelo uv (lockfile `uv.lock`, `uv sync --frozen` no CI). CLI em Typer + Rich.

## Consequências

Ecossistema de NLP (scikit-learn, sentence-transformers), SDK oficial `anthropic`. O Python 3.12 é instalado pelo próprio uv (a máquina tinha 3.11). Alternativas: Node/TypeScript (romcal nativo), Poetry.
