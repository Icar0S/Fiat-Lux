"""Calendário litúrgico local (plano §8.2.2): fallback e enriquecimento, sem rede.

Regras do Brasil (Diretório da Liturgia da CNBB): Epifania no domingo entre 2 e 8/1;
Ascensão no 7º domingo da Páscoa; São Pedro e São Paulo, Assunção e Todos os Santos
transferidos para o domingo; Nossa Senhora Aparecida em 12/10; Corpus Christi na quinta.
"""

from __future__ import annotations

import datetime as dt
from functools import cache

from dateutil.easter import easter

from fiat_lux.liturgia.modelos import DiaLiturgicoBase, Grau, Tempo

D = dt.timedelta
DIAS = ("2ª feira", "3ª feira", "4ª feira", "5ª feira", "6ª feira", "Sábado", "Domingo")


def _domingo_ate(d: dt.date) -> dt.date:
    """Domingo da semana litúrgica de `d` (o próprio, se for domingo)."""
    return d - D(days=(d.weekday() + 1) % 7)


def _domingo_entre(ano: int, mes: int, dia_ini: int) -> dt.date:
    d = dt.date(ano, mes, dia_ini)
    return d + D(days=(6 - d.weekday()) % 7)


@cache
def pascoa(ano: int) -> dt.date:
    return easter(ano)


@cache
def advento1(ano: int) -> dt.date:
    natal = dt.date(ano, 12, 25)
    recuo = (natal.weekday() + 1) % 7 or 7
    return natal - D(days=recuo) - D(weeks=3)


@cache
def epifania(ano: int) -> dt.date:
    """Domingo entre 2 e 8 de janeiro (Brasil)."""
    return _domingo_entre(ano, 1, 2)


@cache
def batismo(ano: int) -> dt.date:
    ep = epifania(ano)
    return ep + D(days=1) if ep.day >= 7 else ep + D(days=7)


def ano_liturgico(d: dt.date) -> int:
    """Ano litúrgico que termina no ano civil Y (começa no 1º Domingo do Advento de Y-1)."""
    return d.year + 1 if d >= advento1(d.year) else d.year


def ciclos(d: dt.date) -> tuple[str, str]:
    y = ano_liturgico(d)
    dominical = {1: "A", 2: "B", 0: "C"}[y % 3]
    ferial = "I" if y % 2 == 1 else "II"
    return dominical, ferial


def _celebracoes_fixas(ano: int) -> dict[dt.date, tuple[str, Grau]]:
    p = pascoa(ano)
    a1 = advento1(ano)
    natal = dt.date(ano, 12, 25)
    sagrada_familia = natal + D(days=(6 - natal.weekday()) % 7 or 7)
    if natal.weekday() == 6:
        sagrada_familia = dt.date(ano, 12, 30)
    imaculada = dt.date(ano, 12, 8)
    if imaculada.weekday() == 6:
        imaculada += D(days=1)
    fixas: dict[dt.date, tuple[str, Grau]] = {
        dt.date(ano, 1, 1): ("Santa Maria, Mãe de Deus", "solenidade"),
        epifania(ano): ("Epifania do Senhor", "solenidade"),
        batismo(ano): ("Batismo do Senhor", "festa"),
        dt.date(ano, 2, 2): ("Apresentação do Senhor", "festa"),
        p - D(days=46): ("Quarta-feira de Cinzas", "feria"),
        p - D(days=7): ("Domingo de Ramos da Paixão do Senhor", "domingo"),
        p - D(days=3): (
            "5ª feira da Semana Santa - Missa Vespertina da Ceia do Senhor",
            "solenidade",
        ),
        p - D(days=2): ("6ª feira da Paixão do Senhor", "solenidade"),
        p - D(days=1): ("Sábado Santo - Vigília Pascal", "solenidade"),
        p: ("Domingo da Páscoa na Ressurreição do Senhor", "solenidade"),
        p + D(days=7): ("2º Domingo da Páscoa ou Domingo da Divina Misericórdia", "domingo"),
        p + D(days=42): ("Ascensão do Senhor", "solenidade"),
        p + D(days=49): ("Domingo de Pentecostes", "solenidade"),
        p + D(days=56): ("Santíssima Trindade", "solenidade"),
        p + D(days=60): ("Santíssimo Corpo e Sangue de Cristo", "solenidade"),
        p + D(days=68): ("Sagrado Coração de Jesus", "solenidade"),
        dt.date(ano, 6, 24): ("Natividade de São João Batista", "solenidade"),
        _domingo_entre(ano, 6, 28): ("Santos Pedro e Paulo Apóstolos", "solenidade"),
        dt.date(ano, 8, 6): ("Transfiguração do Senhor", "festa"),
        _domingo_entre(ano, 8, 15): ("Assunção de Nossa Senhora", "solenidade"),
        dt.date(ano, 9, 14): ("Exaltação da Santa Cruz", "festa"),
        dt.date(ano, 10, 12): (
            "Nossa Senhora da Conceição Aparecida, Padroeira do Brasil",
            "solenidade",
        ),
        _domingo_entre(ano, 11, 1): ("Todos os Santos", "solenidade"),
        dt.date(ano, 11, 2): ("Comemoração de Todos os Fiéis Defuntos", "solenidade"),
        a1 - D(days=7): ("Nosso Senhor Jesus Cristo, Rei do Universo", "solenidade"),
        imaculada: ("Imaculada Conceição de Nossa Senhora", "solenidade"),
        natal: ("Natal do Senhor", "solenidade"),
        sagrada_familia: ("Sagrada Família de Jesus, Maria e José", "festa"),
    }
    sao_jose = dt.date(ano, 3, 19)
    anunciacao = dt.date(ano, 3, 25)
    semana_santa = {p - D(days=k) for k in range(0, 8)} | {p + D(days=k) for k in range(0, 8)}
    if sao_jose.weekday() == 6 and p - D(days=46) < sao_jose:
        sao_jose += D(days=1)
    if sao_jose not in semana_santa:
        fixas[sao_jose] = ("São José, esposo da Bem-Aventurada Virgem Maria", "solenidade")
    if anunciacao.weekday() == 6:
        anunciacao += D(days=1)
    if anunciacao in semana_santa:
        anunciacao = p + D(days=8)
    fixas[anunciacao] = ("Anunciação do Senhor", "solenidade")
    return fixas


def _ordinal(n: int, feminino: bool = False) -> str:
    return f"{n}{'ª' if feminino else 'º'}"


def calcular(d: dt.date) -> DiaLiturgicoBase:
    """Tempo, semana, ciclos, cor padrão e nome estimado para a data."""
    y = d.year
    p = pascoa(y)
    cinzas = p - D(days=46)
    pentecostes = p + D(days=49)
    a1_ano = advento1(y)
    bat = batismo(y)
    dia_semana = d.weekday()
    domingo = dia_semana == 6
    dom = _domingo_ate(d)
    semana: int | None = None
    tempo: Tempo
    if d >= a1_ano and d < dt.date(y, 12, 25):
        tempo, semana = "advento", 1 + (dom - a1_ano).days // 7
    elif d >= dt.date(y, 12, 25) or d <= bat:
        tempo = "natal"
    elif d < cinzas:
        tempo = "comum"
        dom_bat = _domingo_ate(bat)
        semana = 1 if dom <= dom_bat else 1 + (dom - dom_bat).days // 7
    elif d < p - D(days=3):
        tempo = "quaresma"
        q1 = cinzas + D(days=4)
        semana = 0 if d < q1 else 1 + (dom - q1).days // 7
    elif d < p:
        tempo = "triduo"
    elif d <= pentecostes:
        tempo, semana = "pascoa", 1 + (dom - p).days // 7
    else:
        tempo = "comum"
        cristo_rei = a1_ano - D(days=7)
        semana = 34 - (cristo_rei - dom).days // 7
    cor = {
        "advento": "Roxo",
        "natal": "Branco",
        "comum": "Verde",
        "quaresma": "Roxo",
        "triduo": "Vermelho",
        "pascoa": "Branco",
    }[tempo]
    if (tempo == "advento" and domingo and semana == 3) or (
        tempo == "quaresma" and domingo and semana == 4
    ):
        cor = "Rosa"
    if d == pentecostes or d == p - D(days=7) or d == p - D(days=2):
        cor = "Vermelho"
    if d in (p - D(days=3), p - D(days=1)):
        cor = "Branco"
    fixas = _celebracoes_fixas(y)
    if d in fixas:
        nome, grau = fixas[d]
    else:
        grau = "domingo" if domingo else "feria"
        nome = _nome_ferial(d, tempo, semana, domingo)
    dominical, ferial = ciclos(d)
    return DiaLiturgicoBase(
        data=d,
        tempo=tempo,
        semana=semana,
        dia_semana=dia_semana,
        ciclo_dominical=dominical,  # type: ignore[arg-type]
        ciclo_ferial=ferial,  # type: ignore[arg-type]
        cor_padrao=cor,
        nome_estimado=nome,
        grau_estimado=grau,
        ano_liturgico=ano_liturgico(d),
    )


def _nome_ferial(d: dt.date, tempo: Tempo, semana: int | None, domingo: bool) -> str:
    dia = DIAS[d.weekday()]
    titulo = {
        "advento": "do Advento",
        "comum": "do Tempo Comum",
        "quaresma": "da Quaresma",
        "pascoa": "da Páscoa",
        "natal": "do Tempo do Natal",
        "triduo": "da Semana Santa",
    }[tempo]
    if tempo == "natal":
        return f"{dia} do Tempo do Natal"
    if tempo == "quaresma" and semana == 0:
        return f"{dia} depois das Cinzas"
    if tempo == "pascoa" and semana == 1:
        return f"{dia} na Oitava da Páscoa"
    if tempo == "quaresma" and semana == 6:
        return f"{dia} da Semana Santa"
    if domingo and semana:
        return f"{_ordinal(semana)} Domingo {titulo}"
    if semana:
        return f"{dia} da {_ordinal(semana, True)} Semana {titulo}"
    return f"{dia} {titulo}"
