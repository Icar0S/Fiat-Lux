"""Peças da Palavra da Semana (plano §8.6): temas recorrentes, gráfico e plano de leitura."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from fiat_lux.agente.verificacao import mencoes_politicas
from fiat_lux.estado import Estado
from fiat_lux.llm.esquemas import NAO_TEMATICAS
from fiat_lux.noticias.modelos import TemaDoDia
from fiat_lux.pastoral import Neutralidade, taxonomia
from fiat_lux.rag.embeddings import vetores_textos_curtos

CORES = {"mundial": "#3b6ea8", "nacional": "#2e8b57", "regional": "#c77d1a", "composto": "#222222"}
FAIXAS_FUNDO = [(0, 29, "#e8f4ea"), (29, 54, "#fdf6e3"), (54, 74, "#fbe9d7"), (74, 100, "#f7d9d9")]


@dataclass(slots=True)
class TemaRecorrente:
    tema: TemaDoDia
    dias: int
    peso: float
    por_llm: bool = False  # rótulo neutro escrito pelo P1 (senão é a manchete, na reserva)


def rotulo_publico(tr: TemaRecorrente, neu: Neutralidade | None) -> str:
    """Rótulo que pode ir para a mensagem sem passar pelo juiz: o resumo neutro do P1, desde
    que não cite partidos, nomes vigiados ou termos partidários; senão, a descrição da
    categoria pastoral (nunca a manchete crua, que pode trazer nomes de vítimas)."""
    rotulo = tr.tema.rotulo.strip().rstrip(".")
    if tr.por_llm and rotulo and not (neu and mencoes_politicas(rotulo, neu)):
        return rotulo
    cat = taxonomia().get(tr.tema.categoria)
    return cat.nome if cat else "Outros acontecimentos"


def temas_recorrentes(
    estado: Estado, fim: dt.date, dias: int = 7, n: int = 3, limiar: float = 0.80
) -> list[TemaRecorrente]:
    """Funde clusters de dias diferentes por similaridade de rótulo (≥ limiar) e ordena por
    nº de dias × relevância acumulada."""
    ini = fim - dt.timedelta(days=dias - 1)
    rows = estado.con.execute(
        "SELECT data, escopo, rotulo, categoria, gravidade, relevancia, sensivel, links_json,"
        " classificado_por FROM clusters"
        " WHERE data BETWEEN ? AND ? AND categoria IS NOT NULL",
        (ini.isoformat(), fim.isoformat()),
    ).fetchall()
    rows = [r for r in rows if r["categoria"] not in NAO_TEMATICAS and r["rotulo"]]
    if not rows:
        return []
    vet = vetores_textos_curtos([r["rotulo"] for r in rows])
    grupos: list[list[int]] = []
    for i in range(len(rows)):
        for g in grupos:
            if float(vet[i] @ vet[g[0]]) >= limiar or (
                rows[i]["categoria"] == rows[g[0]]["categoria"]
                and float(vet[i] @ vet[g[0]]) >= limiar * 0.6
            ):
                g.append(i)
                break
        else:
            grupos.append([i])
    saida: list[TemaRecorrente] = []
    for g in grupos:
        ref = max(g, key=lambda k: rows[k]["relevancia"] or 0)
        r = rows[ref]
        dias_distintos = len({rows[k]["data"] for k in g})
        peso = dias_distintos * sum(rows[k]["relevancia"] or 0 for k in g)
        saida.append(
            TemaRecorrente(
                TemaDoDia(
                    categoria=r["categoria"],
                    rotulo=r["rotulo"],
                    escopo=r["escopo"],
                    gravidade=r["gravidade"] or 0,
                    relevancia=float(r["relevancia"] or 0),
                    sensivel=r["sensivel"],
                    links=[tuple(x) for x in json.loads(r["links_json"] or "[]")][:3],
                ),
                dias_distintos,
                peso,
                r["classificado_por"] == "llm",
            )
        )
    saida.sort(key=lambda t: -t.peso)
    vistos, unicos = set(), []
    for t in saida:
        if t.tema.categoria in vistos:
            continue
        vistos.add(t.tema.categoria)
        unicos.append(t)
    return unicos[:n]


def medicoes_semana(
    estado: Estado, fim: dt.date, dias: int = 7
) -> dict[str, list[tuple[dt.date, float]]]:
    ini = fim - dt.timedelta(days=dias - 1)
    series: dict[str, list[tuple[dt.date, float]]] = {}
    for r in estado.con.execute(
        "SELECT data, escopo, indice FROM medicoes WHERE data BETWEEN ? AND ? ORDER BY data",
        (ini.isoformat(), fim.isoformat()),
    ):
        series.setdefault(r["escopo"], []).append(
            (dt.date.fromisoformat(r["data"]), float(r["indice"]))
        )
    return series


def grafico(
    series: dict[str, list[tuple[dt.date, float]]], destino: Path, titulo: str
) -> Path | None:
    """PNG com as linhas mundial, nacional, regional e composto sobre as faixas do índice."""
    if not series:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4), dpi=120)
    for lo, hi, cor in FAIXAS_FUNDO:
        ax.axhspan(lo, hi, color=cor, zorder=0)
    rotulos = {
        "mundial": "Mundo",
        "nacional": "Brasil",
        "regional": "Região",
        "composto": "Composto",
    }
    for escopo in ("mundial", "nacional", "regional", "composto"):
        pontos = series.get(escopo)
        if not pontos:
            continue
        xs: list[Any] = [p[0] for p in pontos]
        ys = [p[1] for p in pontos]
        ax.plot(
            xs,
            ys,
            marker="o",
            lw=2.4 if escopo == "composto" else 1.6,
            color=CORES[escopo],
            label=rotulos[escopo],
            zorder=3,
        )
    ax.set_ylim(0, 100)
    ax.set_ylabel("Índice de Tensão")
    ax.set_title(titulo)
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.autofmt_xdate()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(destino)
    plt.close(fig)
    return destino


def tendencia(series: dict[str, list[tuple[dt.date, float]]]) -> str | None:
    pontos = series.get("composto") or []
    if len(pontos) < 2:
        return None
    ys = np.array([p[1] for p in pontos])
    inclinacao = float(np.polyfit(np.arange(len(ys)), ys, 1)[0])
    if inclinacao > 1.5:
        return "em alta"
    if inclinacao < -1.5:
        return "em queda"
    return "estável"
