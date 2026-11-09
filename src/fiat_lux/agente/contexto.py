"""Contexto do dia (plano §8.5.1)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from fiat_lux.liturgia.modelos import DiaLiturgico
from fiat_lux.llm.cliente import Contabilidade, ErroLLM, LLMClient, Pedido, chamar
from fiat_lux.llm.esquemas import ResumoEvangelho
from fiat_lux.llm.offline import embutir
from fiat_lux.llm.prompts import carregar
from fiat_lux.noticias.modelos import Medicao, ResultadoNoticias, TemaDoDia
from fiat_lux.pastoral import Perfil


@dataclass(slots=True)
class ContextoDoDia:
    data: dt.date
    liturgia: DiaLiturgico | None
    perfil: Perfil
    evangelho_ref: str | None = None
    evangelho_texto: str | None = None
    evangelho_resumo: str | None = None
    medicoes: dict[str, Medicao] = field(default_factory=dict)
    temas: list[TemaDoDia] = field(default_factory=list)
    evento_dominante: TemaDoDia | None = None
    sensibilidades: set[str] = field(default_factory=set)
    noticias_disponiveis: bool = False
    links: list[tuple[str, str]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def tempo(self) -> str:
        return self.liturgia.tempo if self.liturgia else "comum"

    @property
    def categorias(self) -> list[str]:
        return [t.categoria for t in self.temas]

    @property
    def calibrando(self) -> bool:
        return any(m.calibrando for m in self.medicoes.values())

    def urls_permitidas(self) -> set[str]:
        return {u for _, u in self.links}


def resumir_evangelho(
    texto: str | None,
    llm: LLMClient | None,
    modelo: str,
    contabilidade: Contabilidade | None = None,
) -> str | None:
    if not texto:
        return None
    if llm is None:
        return None
    try:
        r = chamar(
            llm,
            Pedido(
                "resumo_evangelho",
                modelo,
                carregar("resumo_evangelho").texto,
                embutir(texto[:6000], "evangelho"),
                "low",
                2000,
            ),
            ResumoEvangelho,
            contabilidade,
        )
        return r.resumo.strip() or None
    except ErroLLM:
        return None


def montar(
    data: dt.date,
    perfil: Perfil,
    liturgia: DiaLiturgico | None,
    noticias: ResultadoNoticias | None,
    llm: LLMClient | None,
    modelo_resumo: str,
    contabilidade: Contabilidade | None = None,
) -> ContextoDoDia:
    ctx = ContextoDoDia(data=data, liturgia=liturgia, perfil=perfil)
    if liturgia is not None:
        ctx.avisos += liturgia.avisos
        ev = liturgia.evangelho
        if ev is not None:
            ctx.evangelho_ref, ctx.evangelho_texto = ev.referencia, ev.texto
    if noticias is not None and noticias.disponivel:
        ctx.noticias_disponiveis = True
        ctx.medicoes = dict(noticias.medicoes)
        ctx.temas = list(noticias.temas)
        ctx.evento_dominante = noticias.evento_dominante
        ctx.sensibilidades = set(noticias.sensibilidades) | {
            t.sensivel for t in noticias.temas if t.sensivel
        }
        for t in ctx.temas:
            ctx.links += [link for link in t.links if link not in ctx.links]
        ctx.avisos += noticias.avisos
    ctx.evangelho_resumo = resumir_evangelho(ctx.evangelho_texto, llm, modelo_resumo, contabilidade)
    return ctx
