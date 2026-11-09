"""Fixtures compartilhadas."""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = RAIZ / "tests" / "fixtures"
BIBLIA_DB = RAIZ / "data" / "processed" / "biblia.sqlite"


@pytest.fixture(scope="session")
def raiz() -> Path:
    return RAIZ


@pytest.fixture(scope="session")
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def versificacao():
    from fiat_lux.biblia.versificacao import Versificacao

    return Versificacao.carregar(FIXTURES / "vrs")


@pytest.fixture(scope="session")
def repo():
    if not BIBLIA_DB.is_file():
        pytest.skip("biblia.sqlite ausente (rode `fiatlux biblia ingerir`)")
    from fiat_lux.biblia.repositorio import Repositorio

    r = Repositorio.abrir(BIBLIA_DB)
    yield r
    r.fechar()
