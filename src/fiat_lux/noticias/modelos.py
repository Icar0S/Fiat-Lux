"""Modelos de notícias, clusters e medições (plano §7.2, §8.3)."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Escopo = Literal["mundial", "nacional", "regional"]
ESCOPOS: tuple[Escopo, ...] = ("mundial", "nacional", "regional")
Faixa = Literal["calmo", "atencao", "tensao", "crise"]


class Artigo(BaseModel):
    url: str
    titulo: str
    dominio: str | None = None
    fonte_nome: str | None = None
    idioma: str | None = None
    pais_fonte: str | None = None
    escopo: Escopo
    publicado_em: dt.datetime | None = None
    fonte_coleta: str  # "gdelt" | "rss:<nome>"
    url_hash: str = ""


class Cluster(BaseModel):
    escopo: Escopo
    artigos: list[Artigo]
    relevancia: float = 0.0
    n_fontes: int = 0
    rotulo: str | None = None
    categoria: str | None = None
    gravidade: int | None = None
    confianca: float | None = None
    sensivel: str | None = None
    classificado_por: str | None = None  # "llm" | "palavras"

    @property
    def titulos(self) -> list[str]:
        return [a.titulo for a in self.artigos]

    def links(self, n: int = 3) -> list[tuple[str, str]]:
        vistos: set[str] = set()
        saida: list[tuple[str, str]] = []
        for a in self.artigos:
            dom = a.fonte_nome or a.dominio or "fonte"
            if dom in vistos:
                continue
            vistos.add(dom)
            saida.append((dom, a.url))
            if len(saida) == n:
                break
        return saida


class Medicao(BaseModel):
    data: dt.date
    escopo: str  # inclui "composto"
    volume: int = 0
    volume_z: float | None = None
    tom_medio: float | None = None
    tom_z: float | None = None
    gravidade_media: float | None = None
    indice: float
    faixa: Faixa
    calibrando: bool = True


class TemaDoDia(BaseModel):
    categoria: str
    rotulo: str
    escopo: Escopo
    gravidade: int
    relevancia: float
    sensivel: str | None = None
    links: list[tuple[str, str]] = Field(default_factory=list)


class ResultadoNoticias(BaseModel):
    data: dt.date
    artigos: dict[str, int] = Field(default_factory=dict)
    clusters: list[Cluster] = Field(default_factory=list)
    medicoes: dict[str, Medicao] = Field(default_factory=dict)
    temas: list[TemaDoDia] = Field(default_factory=list)
    evento_dominante: TemaDoDia | None = None
    sensibilidades: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    disponivel: bool = True
