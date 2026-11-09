"""Contrato da API de liturgia v2 (fixtures gravadas + cliente com HTTP simulado)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest
import respx

from fiat_lux.estado import Estado
from fiat_lux.liturgia.cliente_api import ClienteLiturgia, ErroApiLiturgia
from fiat_lux.liturgia.modelos import RespostaV2
from fiat_lux.liturgia.servico import (
    ServicoLiturgia,
    canario,
    de_resposta,
    escolher,
    grau_do_nome,
    local,
)

URL = "https://liturgia.up.railway.app/v2/"


def carregar(fixtures: Path, dia: str) -> dict:
    return json.loads((fixtures / "liturgia" / f"{dia}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("dia", ["2026-11-08", "2026-04-04", "2026-03-29", "2026-01-13"])
def test_fixtures_respeitam_o_contrato(fixtures, dia):
    bruto = carregar(fixtures, dia)
    assert canario(bruto) == []
    r = RespostaV2.model_validate(bruto)
    assert r.data_iso == dt.date.fromisoformat(dia)


def test_canario_detecta_mudanca_de_esquema():
    assert canario({"data": "01/01/2026"})
    assert any(
        "evangelho" in p
        for p in canario({"data": "x", "liturgia": "y", "cor": "Verde", "leituras": {}})
    )


def test_conversao_para_dominio(fixtures):
    dia = de_resposta(RespostaV2.model_validate(carregar(fixtures, "2026-11-08")))
    assert dia.celebracao == "32º Domingo do Tempo Comum"
    assert (dia.grau, dia.cor, dia.tempo, dia.semana) == ("domingo", "Verde", "comum", 32)
    assert (dia.ciclo_dominical, dia.ciclo_ferial) == ("A", "II")
    assert dia.evangelho is not None and dia.evangelho.referencia == "Mt 25,1-13"
    segundas = dia.leituras_do_tipo("segunda")
    assert [x.nota for x in segundas] == ["Forma longa", "Forma breve"]
    assert not dia.avisos


def test_vigilia_pascal_e_ramos(fixtures):
    vig = de_resposta(RespostaV2.model_validate(carregar(fixtures, "2026-04-04")))
    assert vig.grau == "solenidade"
    assert len(vig.leituras) > 8
    ramos = de_resposta(RespostaV2.model_validate(carregar(fixtures, "2026-03-29")))
    evs = ramos.leituras_do_tipo("evangelho")
    assert len(evs) == 3
    assert ramos.evangelho is not None and ramos.evangelho.nota != "mais breve"


def test_cantico_no_lugar_do_salmo(fixtures):
    dia = de_resposta(RespostaV2.model_validate(carregar(fixtures, "2026-01-13")))
    assert dia.leituras_do_tipo("salmo")[0].referencia == "Sl 1Sm 2"
    assert not dia.avisos


@pytest.mark.parametrize(
    ("nome", "data", "grau"),
    [
        (
            "Dedicação da Basílica do Latrão (Catedral de Roma), Festa",
            dt.date(2026, 11, 9),
            "festa",
        ),
        ("São Leão Magno, papa e doutor da Igreja, Memória", dt.date(2026, 11, 10), "memoria"),
        ("Epifania do Senhor, Solenidade", dt.date(2026, 1, 4), "solenidade"),
        ("6ª feira da 32ª Semana do Tempo Comum", dt.date(2026, 11, 13), "feria"),
        ("32º Domingo do Tempo Comum", dt.date(2026, 11, 8), "domingo"),
        ("Santos Cirilo, monge, e Metódio, bispo", dt.date(2026, 2, 14), "memoria_facultativa"),
    ],
)
def test_grau_do_nome(nome, data, grau):
    assert grau_do_nome(nome, data) == grau


def test_escolha_por_precedencia():
    d = dt.date(2026, 11, 10)
    feria = local(d).model_copy(update={"grau": "feria", "celebracao": "3ª feira"})
    mem_fac = feria.model_copy(update={"grau": "memoria_facultativa", "celebracao": "Santo X"})
    sol = feria.model_copy(update={"grau": "solenidade", "celebracao": "Solenidade Y"})
    assert escolher([feria, sol, mem_fac]).celebracao == "Solenidade Y"
    escolhido = escolher([mem_fac, feria])
    assert escolhido.celebracao == "3ª feira" and "Santo X" in escolhido.avisos[-1]
    assert escolher([mem_fac, feria], memoria_facultativa_usa_feria=False).celebracao == "Santo X"


@respx.mock
def test_cliente_404_retry_e_sucesso(fixtures):
    bruto = carregar(fixtures, "2026-11-08")
    rota = respx.get(URL).mock(side_effect=[httpx.Response(500), httpx.Response(200, json=bruto)])
    cli = ClienteLiturgia(URL, tentativas=3)
    r = cli.dia(dt.date(2026, 11, 8))
    assert r is not None and r.liturgia.startswith("32º")
    assert rota.call_count == 2
    assert rota.calls.last.request.url.params["dia"] == "8"
    respx.get(URL).mock(return_value=httpx.Response(404))
    assert cli.dia(dt.date(2030, 1, 1)) is None


@respx.mock
def test_cliente_falha_definitiva():
    respx.get(URL).mock(side_effect=httpx.ConnectError("sem rede"))
    with pytest.raises(ErroApiLiturgia):
        ClienteLiturgia(URL, tentativas=2).dia(dt.date(2026, 1, 1))


@respx.mock
def test_servico_cache_api_e_fallback(fixtures):
    bruto = carregar(fixtures, "2026-11-08")
    estado = Estado(":memory:")
    rota = respx.get(URL).mock(return_value=httpx.Response(200, json=bruto))
    svc = ServicoLiturgia(estado, ClienteLiturgia(URL, tentativas=1))
    d = dt.date(2026, 11, 8)
    assert svc.obter(d).fonte == "api_v2"
    assert svc.obter(d).fonte == "cache"  # segunda chamada não vai à rede
    assert rota.call_count == 1
    respx.get(URL).mock(side_effect=httpx.ConnectError("fora do ar"))
    fb = svc.obter(dt.date(2026, 11, 9))
    assert fb.fonte == "calendario_local" and fb.avisos and fb.tempo == "comum"


@respx.mock
def test_prefetch_periodo(fixtures):
    bruto = carregar(fixtures, "2026-11-08")
    respx.get(URL, params={"periodo": "7"}).mock(return_value=httpx.Response(200, json=[bruto]))
    estado = Estado(":memory:")
    svc = ServicoLiturgia(estado, ClienteLiturgia(URL, tentativas=1))
    assert svc.prefetch(7) == 1
    assert estado.dia_liturgico(dt.date(2026, 11, 8)) is not None
