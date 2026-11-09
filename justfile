# Atalhos do Fiat Lux. Uso: uv run just <receita>
set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]
set dotenv-load := true

default:
    @just --list

# Instala dependências (base + dev) e os hooks do pre-commit
setup:
    uv sync
    uv run pre-commit install

# Instala também os modelos neurais (sentence-transformers)
setup-ml:
    uv sync --extra ml

lint:
    uv run ruff check src tests eval scripts
    uv run ruff format --check src tests eval scripts
    uv run mypy

fmt:
    uv run ruff format src tests eval scripts
    uv run ruff check --fix src tests eval scripts

test *ARGS:
    uv run pytest {{ARGS}}

cov:
    uv run pytest --cov=fiat_lux --cov-report=term

# Pipeline do corpus (Fase 1)
corpus:
    uv run fiatlux biblia baixar
    uv run fiatlux biblia ingerir
    uv run fiatlux biblia validar
    uv run fiatlux biblia exportar-md
    uv run fiatlux biblia relatorio

indice:
    uv run fiatlux indice construir

eval suite="rapida":
    uv run fiatlux eval rodar --suite {{suite}}

diaria *ARGS:
    uv run fiatlux palavra diaria {{ARGS}}

semanal *ARGS:
    uv run fiatlux palavra semanal {{ARGS}}
