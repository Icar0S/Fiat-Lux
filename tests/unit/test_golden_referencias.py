"""Regressão do parser sobre o corpus real da API (eval/golden/referencias.yaml)."""

from pathlib import Path

import pytest
import yaml

from fiat_lux.biblia.referencias import formatar, parse

GOLDEN = Path(__file__).resolve().parents[2] / "eval" / "golden" / "referencias.yaml"
CASOS = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["referencias"]


def test_corpus_tem_mais_de_mil_referencias():
    assert len(CASOS) >= 1000


def test_todas_as_referencias_reais_sao_reconhecidas():
    falhas = []
    for caso in CASOS:
        try:
            r = parse(caso["ref"], livro_padrao=caso.get("livro_padrao"))
            if r.livro != caso["livro"] or formatar(r) != caso["normalizada"]:
                falhas.append((caso["ref"], formatar(r), caso["normalizada"]))
        except Exception as e:
            falhas.append((caso["ref"], repr(e), caso["normalizada"]))
    assert not falhas, falhas[:10]


def test_forma_breve_sem_livro_herda_o_livro_certo():
    caso = next(c for c in CASOS if c["ref"] == "mais breve 10,17-27")
    assert caso["livro"] == "MRK"


@pytest.mark.parametrize(
    "caso", [c for c in CASOS if c.get("cantico")][:20], ids=lambda c: c["ref"]
)
def test_canticos(caso):
    assert parse(caso["ref"]).cantico
