"""Contratos de saída do LLM (validados por Pydantic; plano §9)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

Categoria = Literal[
    "luto_tragedia",
    "violencia",
    "guerra_conflito",
    "injustica_pobreza",
    "poder_bem_comum",
    "saude_doenca",
    "criacao_clima",
    "migracao_refugio",
    "familia_juventude",
    "medo_incerteza",
    "verdade_desinformacao",
    "perseguicao_religiosa",
    "esperanca_reconstrucao",
    "alegria_conquista",
    "igreja_fe",
    "esporte_entretenimento",
    "outro",
]
NAO_TEMATICAS = frozenset({"outro", "esporte_entretenimento"})
Sensivel = Literal["suicidio", "violencia_sexual", "violencia_infantil", "terrorismo", "outro"]


def _palavras(texto: str, limite: int) -> str:
    p = texto.split()
    return " ".join(p[:limite]) if len(p) > limite else texto.strip()


class ClassificacaoGrupo(BaseModel):
    id: str
    categoria: Categoria
    gravidade: int
    sensivel: Sensivel | None = None
    rotulo: str
    confianca: float

    @field_validator("gravidade")
    @classmethod
    def _gravidade(cls, v: int) -> int:
        return max(0, min(3, int(v)))

    @field_validator("confianca")
    @classmethod
    def _confianca(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    @field_validator("rotulo")
    @classmethod
    def _rotulo(cls, v: str) -> str:
        return _palavras(v, 20)


class ClassificacaoLote(BaseModel):
    grupos: list[ClassificacaoGrupo]


class ConsultaPastoral(BaseModel):
    texto: str
    origem: str  # código de categoria, "tempo" ou "evangelho"

    @field_validator("texto")
    @classmethod
    def _texto(cls, v: str) -> str:
        return _palavras(v, 15)


class Consultas(BaseModel):
    consultas: list[ConsultaPastoral]


class Selecao(BaseModel):
    principal: str
    complementares: list[str]
    temas_atendidos: list[str]
    ligacao_liturgica: str
    justificativa: str
    alertas: list[str]


class Redacao(BaseModel):
    olhar_sobre_o_dia: str
    reflexao: str
    ensinamento: str
    gesto: str
    oracao: str


class Julgamento(BaseModel):
    partidario: bool
    castigo_ou_profecia: bool
    exposicao_vitimas: bool
    tom_condenatorio: bool
    motivos: list[str]

    @property
    def aprovado(self) -> bool:
        return not (
            self.partidario
            or self.castigo_ou_profecia
            or self.exposicao_vitimas
            or self.tom_condenatorio
        )


class ResumoEvangelho(BaseModel):
    resumo: str


Criterio = Literal[
    "fidelidade_exegetica",
    "ligacao_liturgica",
    "pertinencia",
    "sobriedade",
    "neutralidade",
    "esperanca",
    "clareza",
    "gesto",
]


class NotaCriterio(BaseModel):
    criterio: Criterio
    nota: int
    justificativa: str

    @field_validator("nota")
    @classmethod
    def _nota(cls, v: int) -> int:
        return max(1, min(5, int(v)))


class Avaliacao(BaseModel):
    notas: list[NotaCriterio]
    veredito: Literal["aprova", "reprova"]


class ExtrasSemana(BaseModel):
    frase: str
    perguntas: list[str]

    @field_validator("frase")
    @classmethod
    def _frase(cls, v: str) -> str:
        return _palavras(v, 30)
