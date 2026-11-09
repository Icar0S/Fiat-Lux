"""Palavra da Semana: rótulos públicos neutros, migração do estado e template (plano §8.6, §10)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3

from fiat_lux.agente.montagem import renderizar
from fiat_lux.agente.semanal import TemaRecorrente, rotulo_publico, temas_recorrentes
from fiat_lux.agente.verificacao import mencoes_politicas
from fiat_lux.estado import Estado
from fiat_lux.llm.cliente import Pedido
from fiat_lux.llm.offline import embutir, semanal
from fiat_lux.noticias.modelos import TemaDoDia
from fiat_lux.pastoral import neutralidade


def _tema(rotulo: str, categoria: str = "igreja_fe") -> TemaDoDia:
    return TemaDoDia(
        categoria=categoria, rotulo=rotulo, escopo="mundial", gravidade=1, relevancia=3.0
    )


def test_mencoes_politicas_detecta_nomes_partidos_e_termos():
    neu = neutralidade()
    assert mencoes_politicas("Papa pede a Milei que preserve a democracia", neu) == ["Milei"]
    assert "PT" in mencoes_politicas("Deputados do PT e do PL votam projeto", neu)
    assert mencoes_politicas("a oposição golpista reagiu", neu)  # termos comparados sem acento
    assert mencoes_politicas("Papa visita a Argentina e fala de paz", neu) == []
    # sigla dentro de palavra não conta
    assert mencoes_politicas("O PTolomeu e o PLanalto", neu) == []


def test_rotulo_publico_usa_resumo_neutro_do_llm():
    neu = neutralidade()
    tr = TemaRecorrente(_tema("Papa visita a Argentina e fala de paz."), 2, 6.0, por_llm=True)
    assert rotulo_publico(tr, neu) == "Papa visita a Argentina e fala de paz"


def test_rotulo_publico_cai_na_categoria_com_politica_ou_manchete_crua():
    neu = neutralidade()
    com_nome = TemaRecorrente(_tema("Papa pede a Milei que preserve a democracia"), 1, 3.0, True)
    assert rotulo_publico(com_nome, neu) == "Vida da Igreja"
    manchete = TemaRecorrente(_tema("Fulano de Tal morre em acidente", "luto_tragedia"), 1, 3.0)
    assert rotulo_publico(manchete, neu) == "Luto e tragédias"  # reserva por palavras-chave


def test_estado_migra_coluna_classificado_por(tmp_path):
    db = tmp_path / "antigo.sqlite"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE clusters (id INTEGER PRIMARY KEY, data TEXT NOT NULL, escopo TEXT NOT NULL,"
        " rotulo TEXT, categoria TEXT, gravidade INTEGER, confianca REAL, n_artigos INTEGER,"
        " n_fontes INTEGER, relevancia REAL, sensivel TEXT, titulos_json TEXT, links_json TEXT)"
    )
    con.commit()
    con.close()
    estado = Estado(db)
    try:
        cols = {r["name"] for r in estado.con.execute("PRAGMA table_info(clusters)")}
        assert "classificado_por" in cols
    finally:
        estado.fechar()


def test_temas_recorrentes_marca_origem_do_rotulo(tmp_path):
    estado = Estado(tmp_path / "e.sqlite")
    try:
        for i, (rot, por) in enumerate(
            [
                ("Papa fala de paz na Argentina", "llm"),
                ("Papa Leão fala de paz na Argentina", "palavras"),
            ]
        ):
            estado.con.execute(
                "INSERT INTO clusters (data, escopo, rotulo, categoria, gravidade, relevancia,"
                " links_json, classificado_por) VALUES (?,?,?,?,?,?,?,?)",
                (f"2026-11-1{i}", "mundial", rot, "igreja_fe", 1, 5.0 - i, json.dumps([]), por),
            )
        estado.con.commit()
        temas = temas_recorrentes(estado, dt.date(2026, 11, 14))
        assert len(temas) == 1 and temas[0].dias == 2
        assert temas[0].por_llm  # o representante (maior relevância) veio do P1
    finally:
        estado.fechar()


def test_frase_offline_usa_categorias_e_nunca_manchetes():
    pedido = Pedido(
        "semanal",
        "offline",
        "",
        embutir(
            {
                "temas": [
                    {"categoria": "violencia", "rotulo": "PMCE prende dois suspeitos em Juazeiro"},
                    {"categoria": "igreja_fe", "rotulo": "Papa pede a Milei que preserve"},
                ],
                "evangelho_ref": "Mt 25,14-30",
            }
        ),
    )
    out = semanal(pedido)
    assert out["frase"].startswith("Uma semana marcada por notícias sobre violência e a vida")
    assert "Milei" not in out["frase"] and "PMCE" not in out["frase"]
    assert "Mt 25,14-30" in out["perguntas"][0]


def test_template_semanal_listas_em_linhas_proprias():
    md = renderizar(
        "semanal.md.j2",
        semana="46/2026",
        data_extenso="domingo, 15 de novembro de 2026",
        celebracao="33º Domingo do Tempo Comum",
        tempo="Tempo Comum",
        ciclo="A",
        frase="Uma semana de esperança.",
        tendencia=None,
        medidor={"composto": {"indice": "38", "faixa": "atenção"}},
        grafico=None,
        temas=[{"rotulo": "Vida da Igreja", "dias": 2}, {"rotulo": "Saúde e doença", "dias": 1}],
        evangelho={"referencia": "Mt 25,14-30", "resumo": "Parábola dos talentos."},
        p1={"ref": "Mt 25,21", "traducao": "MS", "texto": "Muito bem, servo bom e fiel."},
        reflexao="Reflexão.",
        ensinamento="Ensinamento.",
        gesto="Gesto.",
        oracao="Oração.",
        plano=[
            {
                "dia": "Seg 16/11",
                "ref": "Sl 90,1-6",
                "traducao": "MS",
                "evangelho": "Lc 18,35-43",
                "tema": "Vida da Igreja",
            },
            {
                "dia": "Ter 17/11",
                "ref": "Ef 4,13-17",
                "traducao": "MS",
                "evangelho": None,
                "tema": None,
            },
        ],
        perguntas=["Primeira?", "Segunda?"],
        atribuicao="Matos Soares",
        versao="0.1.0",
    )
    linhas = md.splitlines()
    assert "- Vida da Igreja (2 dias)" in linhas and "- Saúde e doença (1 dia)" in linhas
    assert (
        "- **Seg 16/11** — Sl 90,1-6 (MS) · Evangelho do dia: Lc 18,35-43 · *Vida da Igreja*"
        in linhas
    )
    assert "- **Ter 17/11** — Ef 4,13-17 (MS)" in linhas
    assert "1. Primeira?" in linhas and "2. Segunda?" in linhas
    assert "\n\n\n" not in md
    # todo título de seção começa depois de uma linha em branco
    for i, ln in enumerate(linhas):
        if ln.startswith("## "):
            assert linhas[i - 1] == "", ln
