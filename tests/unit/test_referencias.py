import contextlib

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fiat_lux.biblia.referencias import (
    Intervalo,
    ReferenciaInvalida,
    formatar,
    formatar_intervalos,
    normalizar,
    parse,
    parse_intervalos,
    tentar_parse,
)


def iv(livro, c1, v1=None, p1=None, c2=None, v2=None, p2=None):
    return Intervalo(livro, c1, v1, p1, c2, v2, p2, "cnbb-lit")


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Gn 1, 1-2, 2", [iv("GEN", 1, 1, None, 2, 2)]),
        ("Gn 1, 1. 26-31a", [iv("GEN", 1, 1), iv("GEN", 1, 26, None, None, 31, "a")]),
        (
            "Gn 22, 1-2. 9a. 10-13. 15-18",
            [
                iv("GEN", 22, 1, None, None, 2),
                iv("GEN", 22, 9, "a"),
                iv("GEN", 22, 10, None, None, 13),
                iv("GEN", 22, 15, None, None, 18),
            ],
        ),
        ("Ex 14, 15–15, 1", [iv("EXO", 14, 15, None, 15, 1)]),
        ("Br 3, 9-15. 32–4, 4", [iv("BAR", 3, 9, None, None, 15), iv("BAR", 3, 32, None, 4, 4)]),
        (
            "Ez 36, 16-17a. 18-28",
            [iv("EZK", 36, 16, None, None, 17, "a"), iv("EZK", 36, 18, None, None, 28)],
        ),
        ("Sl 103", [iv("PSA", 103)]),
        ("Sl 18B", [iv("PSA", 18, 8, None, None, 15)]),
        ("Rm 6, 3-11", [iv("ROM", 6, 3, None, None, 11)]),
        ("Is 7, 10-14; 8, 10c", [iv("ISA", 7, 10, None, None, 14), iv("ISA", 8, 10, "c")]),
        ("Dn 3, 52. 53. 54. 55. 56", [iv("DAN", 3, n) for n in range(52, 57)]),
        (
            "1Cor 12, 3b-7. 12-13",
            [iv("1CO", 12, 3, "b", None, 7), iv("1CO", 12, 12, None, None, 13)],
        ),
        ("Mt 5, 1-12a", [iv("MAT", 5, 1, None, None, 12, "a")]),
        ("2Mc 7, 1. 20-31", [iv("2MA", 7, 1), iv("2MA", 7, 20, None, None, 31)]),
        ("Est 4, 17n. p-r", [iv("EST", 4, 17, "n"), iv("EST", 4, 17, "p", None, 17, "r")]),
        ("Lc 1, 26-38", [iv("LUK", 1, 26, None, None, 38)]),
        ("Jd 17.20-25", [iv("JUD", 1, 17), iv("JUD", 1, 20, None, None, 25)]),
        ("2Jo 4-9", [iv("2JN", 1, 4, None, None, 9)]),
        ("2Sm 18,9-10.30-19,3", [iv("2SA", 18, 9, None, None, 10), iv("2SA", 18, 30, None, 19, 3)]),
        ("Mt 9, 35–10, 1. 6-8", [iv("MAT", 9, 35, None, 10, 1), iv("MAT", 10, 6, None, None, 8)]),
        ("Dn 3", [iv("DAN", 3)]),
    ],
)
def test_casos_do_plano_e_reais(texto, esperado):
    assert parse_intervalos(texto) == esperado


def test_salmos_com_numeracao_dupla_partes_e_canticos():
    r = parse("Sl 62(63)")
    assert r.intervalos == (iv("PSA", 62),)
    assert r.salmo_hebraico == "63"
    assert parse("Sl 9A(9)").intervalos == (iv("PSA", 9, 1, None, None, 21),)
    assert parse("Sl 9B").intervalos == (iv("PSA", 9, 22, None, None, 39),)
    assert parse("Sl 113b").intervalos == (iv("PSA", 113, 9, None, None, 26),)
    assert parse("Sl 18(19A)").intervalos == (iv("PSA", 18, 1, None, None, 7),)
    assert parse("Sl 147(147B)").salmo_hebraico == "147B"
    assert parse("Sl 70(71); 12(13)").intervalos == (iv("PSA", 70), iv("PSA", 12))
    assert parse("Sl 50(51), 3-4. 5-6a").intervalos[0] == iv("PSA", 50, 3, None, None, 4)
    c = parse("Sl 1Sm 2")
    assert c.cantico
    assert c.livro == "1SA"
    assert c.intervalos == (iv("1SA", 2),)
    assert parse("Sl Lc 1").livro == "LUK"


def test_erros_da_fonte_sao_tolerados_com_aviso():
    r = parse("Sl 106(10)7")
    assert r.salmo_hebraico == "107"
    assert r.avisos
    assert parse("Sl 118(119").salmo_hebraico == "119"
    assert parse("Sl (71/70)").intervalos == (iv("PSA", 70),)
    assert parse("Lc 14,1.7-11¬¬").avisos
    assert parse("Ecl, 3,1-11").intervalos == (iv("ECC", 3, 1, None, None, 11),)
    assert parse("2 Co 5, 14-17").livro == "2CO"
    assert parse("2Samuel 12,1-7.10-17").livro == "2SA"


def test_notas_e_alternativas():
    assert parse("1Ts 4,13-18 (Forma longa)").nota == "Forma longa"
    r = parse("Jo 9,1-41 ou 1.6-9.13-17.34-38")
    assert r.alternativa is not None
    assert r.alternativa.intervalos[0] == iv("JHN", 9, 1)
    assert formatar(r) == "Jo 9,1-41 ou 9,1.6-9.13-17.34-38"


def test_formatacao_canonica():
    assert normalizar("Gn 22, 1-2. 9a. 10-13. 15-18") == "Gn 22,1-2.9a.10-13.15-18"
    assert normalizar("Is 7, 10-14; 8, 10c") == "Is 7,10-14; 8,10c"
    assert normalizar("Br 3, 9-15. 32–4, 4") == "Br 3,9-15.32-4,4"
    assert normalizar("Jd 17.20-25") == "Jd 17.20-25"
    assert formatar(iv("JHN", 3, 16)) == "Jo 3,16"


@pytest.mark.parametrize("texto", ["", "   ", "Xyz 1,2", "Mt", "Mt ,", "Gn a,b"])
def test_invalidas(texto):
    with pytest.raises((ReferenciaInvalida, ValueError)):
        parse(texto)
    assert tentar_parse(texto) is None


_livros = st.sampled_from(["GEN", "PSA", "ISA", "MAT", "JHN", "ROM", "REV", "SIR", "1CO"])


@st.composite
def intervalos_validos(draw):
    livro = draw(_livros)
    n = draw(st.integers(1, 4))
    cap = draw(st.integers(1, 40))
    vers = draw(st.integers(1, 20))
    saida = []
    for _ in range(n):
        if draw(st.booleans()):
            cap += draw(st.integers(1, 3))
            vers = draw(st.integers(1, 20))
        v1 = vers + draw(st.integers(1, 5))
        p1 = draw(st.sampled_from([None, None, "a", "b"]))
        if draw(st.booleans()):
            v2 = v1 + draw(st.integers(1, 8))
            p2 = draw(st.sampled_from([None, None, "a"]))
            saida.append(Intervalo(livro, cap, v1, p1, None, v2, p2, "cnbb-lit"))
            vers = v2
        else:
            saida.append(Intervalo(livro, cap, v1, p1, None, None, None, "cnbb-lit"))
            vers = v1
    return livro, saida


@given(intervalos_validos())
@settings(max_examples=300, deadline=None)
def test_propriedade_formatar_parse_ida_e_volta(dados):
    livro, ivs = dados
    texto = formatar_intervalos(livro, ivs)
    assert parse_intervalos(texto) == ivs
    assert normalizar(texto) == texto


@given(st.text(max_size=30))
@settings(max_examples=300, deadline=None)
def test_propriedade_nunca_levanta_excecao_inesperada(lixo):
    with contextlib.suppress(ReferenciaInvalida, ValueError, KeyError):
        parse(lixo)
