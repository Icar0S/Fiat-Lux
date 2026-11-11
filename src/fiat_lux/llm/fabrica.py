"""Monta o cliente de LLM a partir da configuração."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fiat_lux.config import Settings
from fiat_lux.llm.cache import CacheLLM
from fiat_lux.llm.cliente import (
    ClienteComCache,
    ClienteNaoConfigurado,
    ClienteOffline,
    LLMClient,
    TabelaPrecos,
)
from fiat_lux.logs import log

if TYPE_CHECKING:
    from fiat_lux.llm.servidor import ClienteServidor

PROVEDORES = ("local", "offline")


def tabela_precos(s: Settings) -> TabelaPrecos:
    return TabelaPrecos({m: (p.entrada, p.saida) for m, p in s.custos.precos.items()})


def llm_configurado(s: Settings) -> bool:
    """Há um servidor de LLM configurado (`FIATLUX_LLM_URL` no `.env`)?"""
    return bool(s.llm.url.strip())


def cliente_servidor(s: Settings, **ajustes: Any) -> ClienteServidor:
    """O cliente HTTP do servidor configurado; `ajustes` troca parâmetros (ex.: `timeout_s`)."""
    from fiat_lux.llm.servidor import ClienteServidor

    parametros: dict[str, Any] = {
        "timeout_s": s.llm.timeout_s,
        "tentativas_formato": s.llm.tentativas_formato,
        "espera_fila_max_s": s.llm.espera_fila_max_s,
        "max_tokens": s.llm.max_tokens,
        "precos": tabela_precos(s),
        "marcador_sem_raciocinio": s.llm.marcador_sem_raciocinio,
        "tarefas_sem_raciocinio": s.llm.tarefas_sem_raciocinio,
        "tarefas_opcionais": s.llm.tarefas_opcionais,
        "tempo_max_opcionais_s": s.llm.tempo_max_opcionais_s,
        "espera_max_opcional_s": s.llm.espera_max_opcional_s,
    }
    parametros.update(ajustes)
    chave = s.llm_chave.get_secret_value() if s.llm_chave else None
    return ClienteServidor(s.llm.url, chave, **parametros)


def criar_cliente(
    s: Settings, provedor: str | None = None, usar_cache: bool | None = None
) -> LLMClient:
    escolha = provedor or s.llm.provedor
    cliente: LLMClient
    if escolha == "offline":
        cliente = ClienteOffline()
    elif escolha == "local" and not llm_configurado(s):
        return ClienteNaoConfigurado()
    elif escolha == "local":
        cliente = cliente_servidor(s)
    else:
        raise ValueError(f"provedor de LLM desconhecido: {escolha!r} (use local ou offline)")
    # o cliente offline é determinístico: cache só esconderia mudanças nos manipuladores
    cachear = (usar_cache if usar_cache is not None else s.llm.cache) and escolha != "offline"
    if cachear:
        cliente = ClienteComCache(cliente, CacheLLM(s.caminhos.cache / "llm.sqlite"))
    log().debug("llm_cliente", provedor=cliente.nome)
    return cliente
