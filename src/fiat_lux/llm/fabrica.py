"""Monta o cliente de LLM a partir da configuração."""

from __future__ import annotations

import os

from fiat_lux.config import Settings
from fiat_lux.llm.cache import CacheLLM
from fiat_lux.llm.cliente import (
    ClienteClaude,
    ClienteComCache,
    ClienteOffline,
    ClienteSemCredencial,
    LLMClient,
    TabelaPrecos,
)
from fiat_lux.logs import log


def tabela_precos(s: Settings) -> TabelaPrecos:
    return TabelaPrecos({m: (p.entrada, p.saida) for m, p in s.custos.precos.items()})


def tem_credencial(s: Settings) -> bool:
    """ANTHROPIC_API_KEY/AUTH_TOKEN no ambiente (um perfil `ant auth login` também serve ao SDK)."""
    return bool(
        s.anthropic_api_key
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_PROFILE")
    )


def criar_cliente(
    s: Settings, provedor: str | None = None, usar_cache: bool | None = None
) -> LLMClient:
    escolha = provedor or s.llm.provedor
    cliente: LLMClient
    if escolha == "offline":
        cliente = ClienteOffline()
    elif escolha == "anthropic" and not tem_credencial(s):
        return ClienteSemCredencial()
    elif escolha == "anthropic":
        chave = s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else None
        cliente = ClienteClaude(api_key=chave, timeout_s=s.llm.timeout_s, precos=tabela_precos(s))
    else:
        raise ValueError(f"provedor de LLM desconhecido: {escolha!r}")
    # o cliente offline é determinístico: cache só esconderia mudanças nos manipuladores
    cachear = (usar_cache if usar_cache is not None else s.llm.cache) and escolha != "offline"
    if cachear:
        cliente = ClienteComCache(cliente, CacheLLM(s.caminhos.cache / "llm.sqlite"))
    log().debug("llm_cliente", provedor=cliente.nome)
    return cliente
