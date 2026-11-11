"""Contratos de saída do LLM (validados por Pydantic; plano §9)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

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


_PARAGRAFOS_REFLEXAO = (
    "1º parágrafo, 4 a 5 frases: o que diz a passagem principal, com o {{P1}}",
    "2º parágrafo, 4 a 5 frases: a ligação com o Evangelho do dia",
    "3º parágrafo, 4 a 5 frases: o que essa Palavra diz ao momento e aos temas do dia",
    "4º parágrafo, 4 a 5 frases: um convite esperançoso para viver isso hoje",
)


class Redacao(BaseModel):
    """O texto da Palavra do Dia. O modelo recebe a reflexão como uma lista de 4 parágrafos, cada
    um com o seu papel: modelos pequenos seguem uma estrutura melhor que um número de palavras, e
    escrevem bem mais assim. Aqui ela vira um texto só, com os parágrafos separados por linha em
    branco."""

    olhar_sobre_o_dia: str = Field(description="um parágrafo de 3 a 4 frases sobre o momento")
    reflexao: str = Field(
        json_schema_extra={
            "type": "array",
            "prefixItems": [{"type": "string", "description": d} for d in _PARAGRAFOS_REFLEXAO],
        }
    )
    ensinamento: str = Field(description="1 ou 2 frases")
    gesto: str = Field(description="uma única ação concreta, viável hoje")
    oracao: str = Field(description="3 a 5 frases, dirigidas a Deus")

    @field_validator("reflexao", mode="before")
    @classmethod
    def _paragrafos(cls, v: Any) -> Any:
        if isinstance(v, list):
            return "\n\n".join(str(p).strip() for p in v if str(p).strip())
        return v


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
