"""Configuração do Fiat Lux.

Fontes, em ordem de precedência: argumentos explícitos > variáveis de ambiente > `.env` >
`config/settings.toml`. Caminhos relativos são resolvidos a partir da raiz do projeto.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


def raiz_projeto() -> Path:
    """Raiz do projeto: `FIATLUX_RAIZ`, ou o primeiro ancestral do cwd com `config/settings.toml`."""
    env = os.environ.get("FIATLUX_RAIZ")
    if env:
        return Path(env).resolve()
    aqui = Path.cwd().resolve()
    for p in (aqui, *aqui.parents):
        if (p / "config" / "settings.toml").is_file():
            return p
    return Path(__file__).resolve().parents[2]


def dir_config() -> Path:
    return raiz_projeto() / "config"


class Geral(BaseModel):
    nome: str = "Fiat Lux"
    versao_pipeline: str = "0.1.0"
    fuso: str = "America/Fortaleza"
    perfil_padrao: str = "catolico"
    regiao: str = "Ceará"


class Caminhos(BaseModel):
    dados: Path = Path("data")
    raw: Path = Path("data/raw")
    interim: Path = Path("data/interim")
    biblia_db: Path = Path("data/processed/biblia.sqlite")
    estado_db: Path = Path("data/estado/estado.sqlite")
    markdown: Path = Path("data/markdown")
    cache: Path = Path("data/cache")
    saidas: Path = Path("saidas")
    relatorio_corpus: Path = Path("docs/qualidade-corpus.md")

    def resolvidos(self, raiz: Path) -> Caminhos:
        dados = {k: (v if v.is_absolute() else (raiz / v)) for k, v in self.model_dump().items()}
        return Caminhos(**dados)


class Liturgia(BaseModel):
    url_base: str = "https://liturgia.up.railway.app/v2/"
    timeout_s: float = 10
    tentativas: int = 3
    dias_prefetch: int = 7
    memoria_facultativa_usa_feria: bool = True


class LLM(BaseModel):
    provedor: str = "anthropic"
    modelo_classificacao: str = "claude-haiku-5-5"
    modelo_geracao: str = "claude-sonnet-5-5"
    modelo_juiz: str = "claude-sonnet-5-5"
    esforco_classificacao: str = "low"
    esforco_consultas: str = "low"
    esforco_selecao: str = "medium"
    esforco_redacao: str = "medium"
    esforco_juiz: str = "low"
    max_tentativas_redacao: int = 2
    max_tokens: int = 16000
    timeout_s: float = 120
    cache: bool = True


class PesosRag(BaseModel):
    rerank: float = 0.55
    ancora: float = 0.15
    tempo: float = 0.10
    grafo: float = 0.10
    cobertura: float = 0.10


class Repeticao(BaseModel):
    principal_dias: int = 60
    complementar_dias: int = 30


class Recorte(BaseModel):
    min_vers: int = 1
    max_vers: int = 5
    penalidade_comprimento: float = 0.08


class Rag(BaseModel):
    embedder: str = "auto"
    modelo_embeddings: str = "intfloat/multilingual-e5-base"
    modelo_rerank: str = "BAAI/bge-reranker-v2-m3"
    usar_rerank: bool = True
    top_denso: int = 50
    top_esparso: int = 50
    top_rerank: int = 40
    max_consultas_rerank: int = 4  # 0 = todas
    candidatos_llm: int = 12
    rrf_k: int = 60
    mmr_lambda: float = 0.7
    min_votos_xref: int = 5
    pesos: PesosRag = Field(default_factory=PesosRag)
    repeticao: Repeticao = Field(default_factory=Repeticao)
    recorte: Recorte = Field(default_factory=Recorte)


class Formula(BaseModel):
    base: float = 50
    k_tom: float = 10
    k_volume: float = 5
    k_gravidade: float = 10


class Faixas(BaseModel):
    calmo: float = 29
    atencao: float = 54
    tensao: float = 74


class Medidor(BaseModel):
    pesos_escopo: dict[str, float] = Field(
        default_factory=lambda: {"mundial": 0.35, "nacional": 0.30, "regional": 0.35}
    )
    formula: Formula = Field(default_factory=Formula)
    faixas: Faixas = Field(default_factory=Faixas)
    janela_baseline_dias: int = 30
    clusters_top: int = 5
    evento_dominante_razao: float = 3.0


class Noticias(BaseModel):
    intervalo_gdelt_s: float = 5.5
    max_registros: int = 250
    timespan: str = "24h"
    limiar_cluster: float = 0.80  # distância de cosseno, TF-IDF das manchetes (ADR-011)
    limiar_dedup_titulo: int = 90
    limiar_dedup_cosseno: float = 0.92
    top_clusters_classificar: int = 15
    titulos_por_cluster: int = 5
    confianca_minima: float = 0.5


class Entrega(BaseModel):
    telegram: bool = True
    arquivo: bool = True
    email: bool = False
    horario_limite: str = "06:30"
    limite_telegram: int = 4096


class Preco(BaseModel):
    entrada: float
    saida: float


class Custos(BaseModel):
    custo_max_mensal_usd: float = 10.0
    precos: dict[str, Preco] = Field(default_factory=dict)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FIATLUX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    geral: Geral = Field(default_factory=Geral)
    caminhos: Caminhos = Field(default_factory=Caminhos)
    liturgia: Liturgia = Field(default_factory=Liturgia)
    llm: LLM = Field(default_factory=LLM)
    rag: Rag = Field(default_factory=Rag)
    medidor: Medidor = Field(default_factory=Medidor)
    noticias: Noticias = Field(default_factory=Noticias)
    entrega: Entrega = Field(default_factory=Entrega)
    custos: Custos = Field(default_factory=Custos)

    # Atalhos planos vindos do ambiente (plano Apêndice D).
    perfil: str | None = None
    tz: str | None = None
    estado: Path | None = None
    custo_max_mensal_usd: float | None = None

    # Segredos (sem prefixo).
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY")
    )
    telegram_bot_token: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN")
    )
    telegram_chat_ids_raw: str = Field(
        default="", validation_alias=AliasChoices("TELEGRAM_CHAT_IDS")
    )
    telegram_admin_chat_id: str | None = Field(
        default=None, validation_alias=AliasChoices("TELEGRAM_ADMIN_CHAT_ID")
    )
    smtp_host: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_HOST"))
    smtp_port: int = Field(default=587, validation_alias=AliasChoices("SMTP_PORT"))
    smtp_usuario: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_USUARIO"))
    smtp_senha: SecretStr | None = Field(default=None, validation_alias=AliasChoices("SMTP_SENHA"))
    email_destinatarios_raw: str = Field(
        default="", validation_alias=AliasChoices("EMAIL_DESTINATARIOS")
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        toml = TomlConfigSettingsSource(settings_cls, toml_file=dir_config() / "settings.toml")
        return (init_settings, env_settings, dotenv_settings, toml, file_secret_settings)

    @model_validator(mode="after")
    def _aplicar_atalhos(self) -> Settings:
        if self.perfil:
            self.geral.perfil_padrao = self.perfil
        if self.tz:
            self.geral.fuso = self.tz
        if self.estado:
            self.caminhos.estado_db = self.estado
        if self.custo_max_mensal_usd is not None:
            self.custos.custo_max_mensal_usd = self.custo_max_mensal_usd
        self.caminhos = self.caminhos.resolvidos(raiz_projeto())
        return self

    @property
    def telegram_chat_ids(self) -> list[str]:
        return [c.strip() for c in self.telegram_chat_ids_raw.split(",") if c.strip()]

    @property
    def email_destinatarios(self) -> list[str]:
        return [c.strip() for c in self.email_destinatarios_raw.split(",") if c.strip()]


@lru_cache(maxsize=1)
def obter_settings() -> Settings:
    return Settings()


def recarregar_settings(**overrides: Any) -> Settings:
    """Limpa o cache e devolve uma instância nova (útil em testes)."""
    obter_settings.cache_clear()
    if overrides:
        return Settings(**overrides)
    return obter_settings()
