"""Modelos da liturgia diária (plano §8.2)."""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Tempo = Literal["advento", "natal", "comum", "quaresma", "triduo", "pascoa"]
Grau = Literal["solenidade", "festa", "memoria", "memoria_facultativa", "domingo", "feria"]
TipoLeitura = Literal["primeira", "salmo", "segunda", "evangelho", "extra"]

PRECEDENCIA: dict[str, int] = {
    "solenidade": 0,
    "domingo": 1,
    "festa": 2,
    "memoria": 3,
    "memoria_facultativa": 4,
    "feria": 5,
}


# ------------------------------------------------------------------ resposta bruta da API v2


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


class LeituraApi(_Base):
    referencia: str = ""
    titulo: str | None = None
    texto: str = ""
    refrao: str | None = None


class LeiturasApi(_Base):
    primeiraLeitura: list[LeituraApi] = Field(default_factory=list)
    salmo: list[LeituraApi] = Field(default_factory=list)
    segundaLeitura: list[LeituraApi] = Field(default_factory=list)
    evangelho: list[LeituraApi] = Field(default_factory=list)
    extras: list[LeituraApi] = Field(default_factory=list)


class OracoesApi(_Base):
    coleta: str | None = None
    oferendas: str | None = None
    comunhao: str | None = None
    extras: list[dict[str, str]] = Field(default_factory=list)


class RespostaV2(_Base):
    """Contrato da API `liturgia.up.railway.app/v2/` (validado pelo teste de contrato/canário)."""

    data: str
    liturgia: str
    cor: str
    oracoes: OracoesApi = Field(default_factory=OracoesApi)
    leituras: LeiturasApi = Field(default_factory=LeiturasApi)
    antifonas: dict[str, str] = Field(default_factory=dict)

    @property
    def data_iso(self) -> dt.date:
        d, m, a = (int(x) for x in self.data.split("/"))
        return dt.date(a, m, d)


# ------------------------------------------------------------------ domínio


class Leitura(BaseModel):
    tipo: TipoLeitura
    referencia: str
    titulo: str | None = None
    texto: str = ""
    refrao: str | None = None
    nota: str | None = None  # "Forma longa", "mais breve"...

    @property
    def forma_breve(self) -> bool:
        return bool(self.nota and re.search(r"breve", self.nota, re.IGNORECASE))


class DiaLiturgicoBase(BaseModel):
    """Calculado localmente (sem rede): tempo, semana, ciclos e cor padrão."""

    data: dt.date
    tempo: Tempo
    semana: int | None
    dia_semana: int  # 0 = segunda … 6 = domingo
    ciclo_dominical: Literal["A", "B", "C"]
    ciclo_ferial: Literal["I", "II"]
    cor_padrao: str
    nome_estimado: str
    grau_estimado: Grau
    ano_liturgico: int


class DiaLiturgico(BaseModel):
    data: dt.date
    celebracao: str
    grau: Grau
    cor: str
    tempo: Tempo
    semana: int | None
    ciclo_dominical: str
    ciclo_ferial: str
    leituras: list[Leitura] = Field(default_factory=list)
    oracoes: dict[str, str] = Field(default_factory=dict)
    antifonas: dict[str, str] = Field(default_factory=dict)
    fonte: Literal["api_v2", "cache", "calendario_local"] = "api_v2"
    avisos: list[str] = Field(default_factory=list)

    def leituras_do_tipo(self, tipo: TipoLeitura) -> list[Leitura]:
        return [x for x in self.leituras if x.tipo == tipo]

    @property
    def evangelho(self) -> Leitura | None:
        lista = [x for x in self.leituras if x.tipo == "evangelho" and not x.forma_breve]
        lista = lista or self.leituras_do_tipo("evangelho")
        return lista[0] if lista else None

    @property
    def tem_leituras(self) -> bool:
        return any(x.texto for x in self.leituras)

    @property
    def domingo(self) -> bool:
        return self.data.weekday() == 6
