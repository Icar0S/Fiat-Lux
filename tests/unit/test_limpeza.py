import pytest

from fiat_lux.biblia.limpeza import Limpador, separar_titulo_salmo


@pytest.mark.parametrize(
    ("bruto", "limpo"),
    [
        ("vos tirarei de lá em paz. (ver nota)", "vos tirarei de lá em paz."),
        ("filho (ver nota), e", "filho, e"),
        ("hí\u00adfen", "hífen"),
        (
            "os anjos (ou {1:embaixadores) da paz chorarão} amargamente.",
            "os anjos (ou embaixadores) da paz chorarão amargamente.",
        ),
        ("Vós_(que)_sois justos", "Vós (que) sois justos"),
        ("em seu alcance*", "em seu alcance"),
        ("como está escrito ([Gn. 12,1]).", "como está escrito (Gn. 12,1)."),
        ("“Tu és” ‘meu’", "\"Tu és\" 'meu'"),
        ("palavra ,  dita", "palavra, dita"),
        ("De Davide.1", "De Davide."),
    ],
)
def test_regras(bruto, limpo):
    assert Limpador().limpar(bruto).texto == limpo


def test_contadores_e_marcador_hebraico():
    lim = Limpador()
    r = lim.limpar("Por que te conservas afastado ó Senhor (ver nota) (10,1)", salmo=True)
    assert r.marcador_hebraico == (10, 1)
    assert r.texto == "Por que te conservas afastado ó Senhor"
    assert lim.contadores["ver_nota"] == 1
    assert lim.contadores["marcador_hebraico"] == 1
    # fora dos salmos o marcador não é interpretado
    assert Limpador().limpar("texto (10,1)").marcador_hebraico is None


@pytest.mark.parametrize(
    ("texto", "titulo", "corpo"),
    [
        (
            "Salmo. De Davide. O Senhor me apascenta: nada me falta;",
            "Salmo. De Davide.",
            "O Senhor me apascenta: nada me falta;",
        ),
        (
            "Salmo, De Davide, quando foge de Absalão, seu filho.",
            "Salmo, De Davide, quando foge de Absalão, seu filho.",
            "",
        ),
        ("Ao mestre do coro. Salmo. De Davide.", "Ao mestre do coro. Salmo. De Davide.", ""),
        (
            'Ao mestre do coro. Segundo a melodia do cântico "Os Lagares" ... Salmo. De Davide.',
            None,
            "",
        ),
        (
            "Ao mestre do coro. De Davide. o insensato diz no seu coração",
            "Ao mestre do coro. De Davide.",
            "o insensato diz no seu coração",
        ),
        ("Maskil. De Davide, quando estava na caverna. Súplica.", None, ""),
        (
            "Cântico das subidas. Quando o Senhor fez voltar os cativos de Sião",
            "Cântico das subidas.",
            "Quando o Senhor fez voltar os cativos de Sião",
        ),
        (
            "Súplicas dum aflito que, desalentado, derrama a sua angústia diante do Senhor.",
            None,
            "",
        ),
        (
            "Oração. De Moisés, homem de Deus. Senhor, tu tens sido o nosso refúgio",
            "Oração. De Moisés, homem de Deus.",
            "Senhor, tu tens sido o nosso refúgio",
        ),
        ("Aleluia. Louvai o Senhor", None, "Aleluia. Louvai o Senhor"),
        (
            "Bem-aventurado o homem que não segue o conselho dos ímpios",
            None,
            "Bem-aventurado o homem que não segue o conselho dos ímpios",
        ),
        ("Cantai ao Senhor um cântico novo", None, "Cantai ao Senhor um cântico novo"),
    ],
)
def test_titulos_de_salmos(texto, titulo, corpo):
    t, c = separar_titulo_salmo(texto)
    assert c == corpo
    if titulo is not None:
        assert t == titulo
    if not corpo:
        assert t  # versículo só de título


def test_continuacao_de_titulo_no_v2():
    _t, c = separar_titulo_salmo(
        "Quando o profeta Natan foi ter com ele, depois de haver pecado com Betsabé.",
        anterior_e_titulo=True,
    )
    assert c == ""
