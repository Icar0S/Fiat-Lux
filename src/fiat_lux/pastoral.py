"""Conhecimento pastoral configurável: taxonomia, tempos litúrgicos, perfis e neutralidade."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from fiat_lux.config import dir_config
from fiat_lux.textos import chave


@dataclass(frozen=True, slots=True)
class CategoriaPastoral:
    codigo: str
    descricao: str  # para o classificador (pode trazer notas internas)
    temas: tuple[str, ...]
    sementes: tuple[str, ...]
    sementes_deutero: tuple[str, ...]
    palavras_chave: tuple[str, ...]
    gravidade_base: int
    nome: str = ""  # exibido ao leitor (ex.: temas da Palavra da Semana)


@dataclass(frozen=True, slots=True)
class Perfil:
    nome: str
    traducao: str
    traducao_deutero: str | None
    canon: int
    deuterocanonicos: str  # normais | excluidos | rotulados
    rotulo_deutero: str | None
    rotulo_evangelho: str

    @property
    def inclui_deutero(self) -> bool:
        return self.deuterocanonicos != "excluidos"


@dataclass(frozen=True, slots=True)
class Neutralidade:
    partidos: tuple[str, ...]
    termos_partidarios: tuple[str, ...]
    nomes_vigiados: tuple[str, ...]
    proibidas: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _yaml(nome: str, base: Path | None = None) -> Any:
    return yaml.safe_load(((base or dir_config()) / nome).read_text(encoding="utf-8"))


@cache
def taxonomia(base: Path | None = None) -> dict[str, CategoriaPastoral]:
    dados = _yaml("taxonomia_pastoral.yaml", base)
    saida: dict[str, CategoriaPastoral] = {}
    for codigo, c in dados["categorias"].items():
        saida[codigo] = CategoriaPastoral(
            codigo=codigo,
            descricao=str(c.get("descricao", "")),
            temas=tuple(c.get("temas", []) or []),
            sementes=tuple(c.get("sementes", []) or []),
            sementes_deutero=tuple(c.get("sementes_deutero", []) or []),
            palavras_chave=tuple(chave(p) for p in (c.get("palavras_chave", []) or [])),
            gravidade_base=int(c.get("gravidade_base", 0)),
            nome=str(c.get("nome") or c.get("descricao", "")),
        )
    return saida


@cache
def sensibilidades(base: Path | None = None) -> dict[str, tuple[str, ...]]:
    dados = _yaml("taxonomia_pastoral.yaml", base)
    return {k: tuple(chave(x) for x in v) for k, v in (dados.get("sensibilidades") or {}).items()}


@cache
def tempos_liturgicos(base: Path | None = None) -> dict[str, tuple[str, ...]]:
    return {k: tuple(v) for k, v in _yaml("tempos_liturgicos.yaml", base).items()}


@cache
def perfis(base: Path | None = None) -> dict[str, Perfil]:
    return {
        nome: Perfil(
            nome=nome,
            traducao=str(p["traducao"]),
            traducao_deutero=p.get("traducao_deutero"),
            canon=int(p["canon"]),
            deuterocanonicos=str(p["deuterocanonicos"]),
            rotulo_deutero=p.get("rotulo_deutero"),
            rotulo_evangelho=str(p.get("rotulo_evangelho", "Evangelho do dia")),
        )
        for nome, p in _yaml("perfis.yaml", base).items()
    }


def perfil(nome: str) -> Perfil:
    try:
        return perfis()[nome]
    except KeyError as e:
        raise KeyError(f"perfil desconhecido: {nome!r} (use {', '.join(perfis())})") from e


@cache
def neutralidade(base: Path | None = None) -> Neutralidade:
    d = _yaml("neutralidade.yaml", base)
    return Neutralidade(
        partidos=tuple(d.get("partidos", [])),
        termos_partidarios=tuple(chave(x) for x in d.get("termos_partidarios", [])),
        nomes_vigiados=tuple(d.get("nomes_vigiados", [])),
        proibidas={
            k: tuple(chave(x) for x in v) for k, v in (d.get("expressoes_proibidas") or {}).items()
        },
    )


# Perda de vidas prevalece pastoralmente (uma enchente com mortos é, antes de tudo, luto).
PESOS_CATEGORIA = {"luto_tragedia": 2.0, "guerra_conflito": 1.5, "esporte_entretenimento": 0.8}


def classificar_por_palavras(titulos: list[str]) -> tuple[str, float, int]:
    """Classificador de reserva (sem LLM): categoria, confiança e gravidade por palavras-chave."""
    texto = " " + chave(" ".join(titulos)) + " "
    melhor, pontos = "outro", 0.0
    for codigo, cat in taxonomia().items():
        n = sum(texto.count(" " + p) for p in cat.palavras_chave if p) * PESOS_CATEGORIA.get(
            codigo, 1.0
        )
        if n > pontos:
            melhor, pontos = codigo, n
    if pontos == 0:
        return "outro", 0.2, 0
    conf = min(0.9, 0.45 + 0.1 * pontos)
    grav = taxonomia()[melhor].gravidade_base
    if melhor in {"luto_tragedia", "guerra_conflito"} and any(
        t in texto for t in (" dezenas de mortos", " centenas de mortos", " mortos ", " massacre")
    ):
        grav = min(3, grav + 1)
    return melhor, conf, grav


def detectar_sensibilidade(texto: str) -> str | None:
    t = " " + chave(texto) + " "
    for tipo, termos in sensibilidades().items():
        if any((" " + x) in t for x in termos):
            return tipo
    return None
