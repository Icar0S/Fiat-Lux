import pytest

from fiat_lux.biblia.versificacao import (
    ParametrosAlinhamento,
    TabelaVrs,
    _expandir,
    alinhar,
    melhor_divisao,
    parse_ref_str,
    ref_str,
)


def test_expandir_intervalos():
    assert _expandir("GEN 32:1-3", "GEN 32:2-4") == [
        (("GEN", 32, 1), ("GEN", 32, 2)),
        (("GEN", 32, 2), ("GEN", 32, 3)),
        (("GEN", 32, 3), ("GEN", 32, 4)),
    ]
    assert _expandir("PSA 51:0", "PSA 51:1-2") == [(("PSA", 51, 0), ("PSA", 51, 1))]
    assert _expandir("ESG 1:1", "ESG 1:1a") == [(("ESG", 1, 1), ("ESG", 1, 1))]
    assert _expandir("DAG 3:52-23", "S3Y 1:30-31")[0][0] == ("DAG", 3, 52)  # intervalo malformado
    assert _expandir("lixo", "GEN 1:1") == []


def test_ref_str_ida_e_volta():
    assert parse_ref_str(ref_str(("PSA", 23, 1))) == ("PSA", 23, 1)


@pytest.mark.parametrize(
    ("ms", "eng"),
    [
        (("PSA", 22, 1), ("PSA", 23, 1)),
        (("PSA", 3, 1), ("PSA", 3, 0)),  # título
        (("PSA", 3, 2), ("PSA", 3, 1)),
        (("PSA", 9, 22), ("PSA", 10, 1)),
        (("PSA", 50, 3), ("PSA", 51, 1)),
        (("PSA", 113, 9), ("PSA", 115, 1)),
        (("PSA", 115, 10), ("PSA", 116, 10)),
        (("PSA", 147, 12), ("PSA", 147, 12)),
        (("DAN", 3, 91), ("DAN", 3, 24)),
        (("DAN", 3, 98), ("DAN", 4, 1)),
        (("MAL", 4, 1), ("MAL", 4, 1)),
        (("BAR", 6, 1), ("BAR", 6, 1)),
        (("JHN", 3, 16), ("JHN", 3, 16)),
    ],
)
def test_tabela_ms_para_eng(versificacao, ms, eng):
    assert versificacao.ms_para_eng(ms) == eng


@pytest.mark.parametrize(
    "ref", [("DAN", 3, 24), ("DAN", 13, 1), ("DAN", 14, 2), ("EST", 11, 2), ("EST", 10, 4)]
)
def test_acrescimos_gregos_sem_eng(versificacao, ref):
    assert versificacao.ms_para_eng(ref) is None


@pytest.mark.parametrize(
    ("lit", "eng"),
    [
        (("MAL", 3, 23), ("MAL", 4, 5)),
        (("ISA", 8, 23), ("ISA", 9, 1)),
        (("ISA", 9, 1), ("ISA", 9, 2)),
        (("NAM", 2, 1), ("NAM", 1, 15)),
        (("HOS", 2, 16), ("HOS", 2, 14)),
        (("JOL", 4, 1), ("JOL", 3, 1)),
        (("2SA", 19, 1), ("2SA", 18, 33)),
        (("MAT", 5, 3), ("MAT", 5, 3)),
    ],
)
def test_cnbb_hebraico_para_eng(versificacao, lit, eng):
    assert versificacao.cnbb_para_eng(*lit) == eng


def test_cnbb_salmo_pela_lxx(versificacao):
    assert versificacao.cnbb_para_eng("PSA", 22, 1, hebraico=False) == ("PSA", 23, 1)
    assert versificacao.cnbb_para_eng("PSA", 50, 3, hebraico=False) == ("PSA", 51, 1)


def test_tabela_carrega_com_correcao_de_entradas(fixtures):
    t = TabelaVrs.carregar(fixtures / "vrs" / "vul.json")
    assert t.para_org(("PSA", 9, 22)) == ("PSA", 10, 1)  # entrada posterior corrige a anterior
    assert t.de_org(("PSA", 116, 10)) == ("PSA", 115, 10)


def test_alinhamento_identidade():
    a = ["no principio criou deus o ceu e a terra", "a terra estava vazia", "e deus disse haja luz"]
    passos = alinhar(a, list(a))
    assert [(p.i, p.ni, p.j, p.nj) for p in passos] == [(0, 1, 0, 1), (1, 1, 1, 1), (2, 1, 2, 1)]


def test_alinhamento_detecta_versiculo_fundido():
    a = [
        "abrao disse nao me deste filhos e o senhor lhe disse este nao sera teu herdeiro",
        "olha para o ceu e conta as estrelas",
    ]
    b = [
        "abrao disse nao me deste filhos",
        "o senhor lhe disse este nao sera teu herdeiro",
        "olha para o ceu e conta as estrelas",
    ]
    passos = alinhar(a, b, fusao_provavel=[True, False])
    assert (passos[0].ni, passos[0].nj) == (1, 2)


def test_alinhamento_pula_versiculo_sem_par_com_prior_da_tabela():
    a = ["primeiro texto sobre o senhor", "terceiro texto da casa de israel"]
    b = [
        "primeiro texto sobre o senhor",
        "josue disse ao povo nao podereis servir",
        "terceiro texto da casa de israel",
    ]
    passos = alinhar(a, b, preferidos=[0, 2], params=ParametrosAlinhamento())
    pares = {(p.i, p.j) for p in passos if p.ni == 1 and p.nj == 1}
    assert pares == {(0, 0), (1, 2)}
    assert any(p.ni == 0 and p.j == 1 for p in passos)


def test_fusao_nao_atravessa_capitulos_nos_salmos():
    a = ["louvai o senhor porque e bom", "junto dos rios da babilonia nos assentamos"]
    b = [
        "dai gracas ao senhor",
        "louvai o senhor porque e bom",
        "junto aos rios da babilonia estavamos",
    ]
    passos = alinhar(a, b, capitulos_a=[136, 137], capitulos_b=[136, 136, 137])
    assert all(not (p.nj == 2 and p.j == 1) for p in passos)


def test_melhor_divisao():
    texto = (
        "Uns repartem liberalmente e ficam mais ricos. A alma beneficente será cumulada de bens."
    )
    r = melhor_divisao(
        texto, "uns repartem e ficam mais ricos", "a alma generosa sera cumulada de bens"
    )
    assert r is not None
    pos, s1, s2 = r
    assert texto[pos:].startswith("A alma beneficente")
    assert s1 > 0 and s2 > 0
    assert melhor_divisao("curto", "a", "b") is None
