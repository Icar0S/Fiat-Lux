"""Integração: corpus construído (marcador `corpus`, pulado se biblia.sqlite não existir)."""

from __future__ import annotations

import pytest

from fiat_lux.biblia.referencias import parse
from fiat_lux.biblia.validacao import checar_banco

pytestmark = pytest.mark.corpus


def test_todas_as_checagens_do_banco_passam(repo):
    falhas = [c for c in checar_banco(repo.con) if not c.ok]
    assert not falhas, falhas


def test_contagens_finais(repo):
    n = dict(
        repo.con.execute(
            "SELECT traducao_id, COUNT(*) FROM versiculos GROUP BY traducao_id"
        ).fetchall()
    )
    assert n["blivre"] == 31101
    assert 35600 < n["ms"] < 35800  # 35.624 brutos − duplicados + divisões de versículos fundidos
    livros = dict(
        repo.con.execute(
            "SELECT traducao_id, COUNT(DISTINCT livro) FROM versiculos GROUP BY traducao_id"
        )
    )
    assert livros == {"ms": 73, "blivre": 66}


def test_nenhuma_lacuna_aberta(repo):
    abertas = repo.con.execute("SELECT COUNT(*) FROM lacunas WHERE status='aberta'").fetchone()[0]
    assert abertas == 0


def test_cobertura_da_versificacao(repo):
    from fiat_lux.biblia.banco import metadado

    assert float(metadado(repo.con, "cobertura_protocanonica_conf08")) >= 0.99


def test_passagem_nativa_e_conversao_eng(repo):
    p = repo.get_passagem("Sl 22,1-4", "ms")
    assert "apascenta" in p.texto
    assert p.ref_formatada == "Sl 22,1-4"
    # Sl 23 (eng) → Sl 22 da MS, sem o título
    p = repo.get_passagem("Sl 23,1-2", "ms", esquema="eng")
    assert p.versiculos[0][:2] == (22, 1)
    assert p.refs_canonicas[0] == "PSA.23.1"
    p = repo.get_passagem("Jo 3,16", "blivre")
    assert "amou" in p.texto


def test_passagem_com_lacuna_e_fundido(repo):
    p = repo.get_passagem("Jó 3,22-25", "ms")
    assert p.tem_lacuna
    assert any("lacuna" in a for a in p.avisos)


def test_busca_bm25_com_variantes(repo):
    # "Egito" (PT-BR) encontra "Egipto" (PT-PT) na MS
    achados = repo.buscar_texto("saiu do Egito", "ms", limite=10)
    assert achados
    assert any("Egipto" in v.texto for v, _ in achados)


def test_referencias_cruzadas(repo):
    xs = repo.refs_cruzadas("JHN.3.16", min_votos=5)
    assert xs and all(v >= 5 for *_, v in xs)


def test_parse_e_busca_de_leitura_real(repo):
    ref = parse("Mt 25,1-13")
    p = repo.get_passagem(ref, "ms")
    assert len(p.versiculos) == 13
