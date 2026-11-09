import datetime as dt

import pytest

from fiat_lux.liturgia.calendario_local import advento1, batismo, calcular, ciclos, epifania, pascoa

d = dt.date


@pytest.mark.parametrize(
    ("ano", "esperado"),
    [
        (2025, d(2025, 4, 20)),
        (2026, d(2026, 4, 5)),
        (2027, d(2027, 3, 28)),
        (2028, d(2028, 4, 16)),
        (2029, d(2029, 4, 1)),
        (2030, d(2030, 4, 21)),
    ],
)
def test_pascoa(ano, esperado):
    assert pascoa(ano) == esperado


@pytest.mark.parametrize(
    ("ano", "esperado"),
    [
        (2022, d(2022, 11, 27)),
        (2025, d(2025, 11, 30)),
        (2026, d(2026, 11, 29)),
        (2027, d(2027, 11, 28)),
        (2028, d(2028, 12, 3)),
        (2030, d(2030, 12, 1)),
    ],
)
def test_primeiro_domingo_do_advento(ano, esperado):
    assert advento1(ano) == esperado
    assert esperado.weekday() == 6


@pytest.mark.parametrize(
    ("data", "ciclo"),
    [
        (d(2026, 6, 1), ("A", "II")),
        (d(2025, 11, 30), ("A", "II")),
        (d(2026, 11, 28), ("A", "II")),
        (d(2026, 11, 29), ("B", "I")),
        (d(2027, 6, 1), ("B", "I")),
        (d(2028, 6, 1), ("C", "II")),
    ],
)
def test_ciclos(data, ciclo):
    assert ciclos(data) == ciclo


def test_epifania_e_batismo_no_brasil():
    assert epifania(2026) == d(2026, 1, 4)
    assert batismo(2026) == d(2026, 1, 11)
    # Epifania em 7/1 ⇒ Batismo na segunda-feira seguinte
    assert epifania(2029) == d(2029, 1, 7)
    assert batismo(2029) == d(2029, 1, 8)


@pytest.mark.parametrize(
    ("data", "tempo", "semana", "nome"),
    [
        (d(2026, 11, 8), "comum", 32, "32º Domingo do Tempo Comum"),
        (d(2026, 11, 13), "comum", 32, "6ª feira da 32ª Semana do Tempo Comum"),
        (d(2026, 1, 12), "comum", 1, "2ª feira da 1ª Semana do Tempo Comum"),
        (d(2026, 1, 18), "comum", 2, "2º Domingo do Tempo Comum"),
        (d(2026, 2, 18), "quaresma", 0, "Quarta-feira de Cinzas"),
        (d(2026, 2, 19), "quaresma", 0, "5ª feira depois das Cinzas"),
        (d(2026, 2, 22), "quaresma", 1, "1º Domingo da Quaresma"),
        (d(2026, 3, 29), "quaresma", 6, "Domingo de Ramos da Paixão do Senhor"),
        (
            d(2026, 4, 2),
            "triduo",
            None,
            "5ª feira da Semana Santa - Missa Vespertina da Ceia do Senhor",
        ),
        (d(2026, 4, 5), "pascoa", 1, "Domingo da Páscoa na Ressurreição do Senhor"),
        (d(2026, 4, 6), "pascoa", 1, "2ª feira na Oitava da Páscoa"),
        (d(2026, 5, 17), "pascoa", 7, "Ascensão do Senhor"),
        (d(2026, 5, 24), "pascoa", 8, "Domingo de Pentecostes"),
        (d(2026, 5, 25), "comum", 8, "2ª feira da 8ª Semana do Tempo Comum"),
        (d(2026, 6, 4), "comum", 9, "Santíssimo Corpo e Sangue de Cristo"),
        (d(2026, 6, 28), "comum", 13, "Santos Pedro e Paulo Apóstolos"),
        (d(2026, 11, 22), "comum", 34, "Nosso Senhor Jesus Cristo, Rei do Universo"),
        (d(2026, 11, 29), "advento", 1, "1º Domingo do Advento"),
        (d(2026, 12, 25), "natal", None, "Natal do Senhor"),
        (d(2027, 1, 1), "natal", None, "Santa Maria, Mãe de Deus"),
    ],
)
def test_dias_de_referencia(data, tempo, semana, nome):
    b = calcular(data)
    assert (b.tempo, b.semana, b.nome_estimado) == (tempo, semana, nome)


@pytest.mark.parametrize(
    ("data", "cor"),
    [
        (d(2026, 3, 15), "Rosa"),
        (d(2026, 12, 13), "Rosa"),
        (d(2026, 3, 29), "Vermelho"),
        (d(2026, 4, 3), "Vermelho"),
        (d(2026, 5, 24), "Vermelho"),
        (d(2026, 4, 2), "Branco"),
        (d(2026, 7, 7), "Verde"),
        (d(2026, 12, 1), "Roxo"),
    ],
)
def test_cores(data, cor):
    assert calcular(data).cor_padrao == cor
