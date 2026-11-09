import pytest

from fiat_lux.biblia import catalogo
from fiat_lux.biblia.catalogo import LIVROS, por_codigo, resolver, resolver_nome_ms

SIGLAS_CNBB = [
    "Gn",
    "Ex",
    "Lv",
    "Nm",
    "Dt",
    "Js",
    "Jz",
    "Rt",
    "1Sm",
    "2Sm",
    "1Rs",
    "2Rs",
    "1Cr",
    "2Cr",
    "Esd",
    "Ne",
    "Tb",
    "Jt",
    "Est",
    "1Mc",
    "2Mc",
    "Jó",
    "Sl",
    "Pr",
    "Ecl",
    "Ct",
    "Sb",
    "Eclo",
    "Is",
    "Jr",
    "Lm",
    "Br",
    "Ez",
    "Dn",
    "Os",
    "Jl",
    "Am",
    "Ab",
    "Jn",
    "Mq",
    "Na",
    "Hab",
    "Sf",
    "Ag",
    "Zc",
    "Ml",
    "Mt",
    "Mc",
    "Lc",
    "Jo",
    "At",
    "Rm",
    "1Cor",
    "2Cor",
    "Gl",
    "Ef",
    "Fl",
    "Cl",
    "1Ts",
    "2Ts",
    "1Tm",
    "2Tm",
    "Tt",
    "Fm",
    "Hb",
    "Tg",
    "1Pd",
    "2Pd",
    "1Jo",
    "2Jo",
    "3Jo",
    "Jd",
    "Ap",
]


def test_73_livros_na_ordem_catolica():
    assert len(LIVROS) == 73
    assert [lv.ordem_catolica for lv in LIVROS] == list(range(1, 74))
    assert sum(lv.testamento == "AT" for lv in LIVROS) == 46
    assert sum(lv.testamento == "NT" for lv in LIVROS) == 27
    assert {lv.codigo for lv in LIVROS if lv.deuterocanonico} == {
        "TOB",
        "JDT",
        "1MA",
        "2MA",
        "WIS",
        "SIR",
        "BAR",
    }


def test_ordem_protestante_tem_66_livros():
    ordens = [lv.ordem_protestante for lv in LIVROS if lv.ordem_protestante]
    assert ordens == list(range(1, 67))
    assert por_codigo("EST").ordem_protestante == 17
    assert por_codigo("REV").ordem_protestante == 66


def test_siglas_cnbb_resolvem_na_ordem():
    assert [resolver(s).codigo for s in SIGLAS_CNBB] == [lv.codigo for lv in LIVROS]


@pytest.mark.parametrize(
    ("sigla", "codigo"),
    [
        ("Ees", "ECC"),
        ("Eus", "SIR"),
        ("Sa", "WIS"),
        ("Cc", "SNG"),
        ("Ps", "PSA"),
        ("Pv", "PRO"),
        ("Ju", "JDG"),
        ("Jdi", "JDT"),
        ("Jda", "JUD"),
        ("Jn", "JON"),
        ("Je", "JER"),
        ("Js", "JOS"),
        ("Job", "JOB"),
        ("1Pa", "1CH"),
        ("2Pa", "2CH"),
        ("Act", "ACT"),
        ("Tob", "TOB"),
        ("Ba", "BAR"),
        ("Mic", "MIC"),
        ("Hc", "HAB"),
        ("So", "ZEP"),
        ("1Ma", "1MA"),
        ("Fp", "PHP"),
    ],
)
def test_siglas_da_matos_soares(sigla, codigo):
    assert resolver(sigla).codigo == codigo


def test_jo_e_jo_acentuado_nao_colidem():
    assert resolver("Jo").codigo == "JHN"
    assert resolver("Jó").codigo == "JOB"
    assert resolver("jó").codigo == "JOB"
    assert resolver("JOÃO").codigo == "JHN"


@pytest.mark.parametrize(
    ("texto", "codigo"),
    [
        ("Primeira Epístola de S. João", "1JN"),
        ("Livro Segundo de Samuel", "2SA"),
        ("Evangelho segundo S. Mateus", "MAT"),
        ("I Coríntios", "1CO"),
        ("2 Co", "2CO"),
        ("2Samuel", "2SA"),
        ("Cântico dos Cânticos", "SNG"),
        ("eclesiastico", "SIR"),
        ("Eclesiastes", "ECC"),
        ("Atos dos Apóstolos", "ACT"),
        ("apocalipse", "REV"),
    ],
)
def test_nomes_por_extenso(texto, codigo):
    assert resolver(texto).codigo == codigo


def test_nomes_da_ms_mapeiam_por_nome():
    for lv in LIVROS:
        assert resolver_nome_ms(lv.nome_ms).codigo == lv.codigo
    assert resolver_nome_ms("Actos dos Apóstolos").codigo == "ACT"


def test_osis_e_blivre():
    assert catalogo.por_osis("Ps").codigo == "PSA"
    assert catalogo.por_osis("1John").codigo == "1JN"
    assert catalogo.por_sigla_blivre("hc").codigo == "HAB"
    assert sum(1 for lv in LIVROS if lv.sigla_blivre) == 66


def test_desconhecido_devolve_none():
    assert resolver("Xyz") is None
    assert resolver("") is None
    with pytest.raises(KeyError):
        catalogo.resolver_obrigatorio("Xyz")


def test_tipos_de_pericope_e_prioritarios():
    assert por_codigo("PSA").tipo_pericope == "salmos"
    assert por_codigo("SIR").tipo_pericope == "proverbial"
    assert por_codigo("MAT").tipo_pericope == "narrativo"
    assert por_codigo("ROM").tipo_pericope == "padrao"
    assert por_codigo("ISA").prioritario and por_codigo("LUK").prioritario
    assert not por_codigo("GEN").prioritario
