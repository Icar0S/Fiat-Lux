"""Cliente de LLM (plano §5, §9; ADR-008, ADR-012).

`LLMClient` é um Protocol: o pipeline não conhece o provedor. Implementações:

- `ClienteServidor` (`fiat_lux.llm.servidor`): o servidor de LLM da instalação, pela API HTTP
  (`POST /v1/chat`). URL, chave e modelos vêm do `.env`. A saída estruturada é pedida no prompt
  e validada por Pydantic. Falhas que não passam tentando de novo (chave recusada, modelo
  inexistente, servidor inalcançável) viram `ErroPermanente` e fecham o cliente pelo resto da
  execução: as chamadas seguintes falham na hora, sem rede.
- `ClienteOffline`: determinístico e sem rede, delega a "manipuladores" por tarefa
  (`fiat_lux.llm.offline`). Usado em testes, `--dry-run` sem servidor e como reserva.
- `ClienteComCache`: embrulha qualquer cliente com cache por hash da entrada (§9).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ErroLLM(RuntimeError):
    """Falha ao obter resposta válida do LLM."""


class ErroPermanente(ErroLLM):
    """O servidor de LLM não vai responder nesta execução, por mais que se tente.

    `causa`: "chave", "conexao", "url", "ocupado", "sem_servidor" (o servidor todo fica fora) ou
    "modelo" (só `modelo` fica fora). `motivo` é a explicação curta, para pessoas.
    """

    def __init__(self, causa: str, motivo: str, modelo: str | None = None) -> None:
        super().__init__(f"LLM indisponível: {motivo}")
        self.causa = causa
        self.motivo = motivo
        self.modelo = modelo

    def copia(self) -> ErroPermanente:
        return ErroPermanente(self.causa, self.motivo, self.modelo)


def motivo_curto(e: ErroLLM) -> str:
    """Motivo para o aviso de uma etapa. Quando o servidor todo está fora, o motivo aparece uma
    vez só, no topo dos avisos (`provedor_bloqueado`), e as etapas dizem apenas "sem o LLM"."""
    if isinstance(e, ErroPermanente) and e.modelo is None:
        return "sem o LLM"
    return str(e)


class ErroOrcamento(ErroLLM):
    """O teto de custo mensal foi atingido (plano §12)."""


@dataclass(slots=True)
class Uso:
    tokens_entrada: int = 0
    tokens_saida: int = 0
    tokens_cache_leitura: int = 0
    tokens_cache_escrita: int = 0
    custo_usd: float = 0.0

    def somar(self, outro: Uso) -> None:
        self.tokens_entrada += outro.tokens_entrada
        self.tokens_saida += outro.tokens_saida
        self.tokens_cache_leitura += outro.tokens_cache_leitura
        self.tokens_cache_escrita += outro.tokens_cache_escrita
        self.custo_usd += outro.custo_usd


@dataclass(slots=True)
class RespostaLLM[T]:
    dados: T
    modelo: str
    uso: Uso = field(default_factory=Uso)
    do_cache: bool = False
    duracao_s: float = 0.0


@dataclass(frozen=True, slots=True)
class Pedido:
    tarefa: str  # "classificacao", "consultas", "selecao", "redacao", "juiz", "avaliacao"…
    modelo: str  # vazio: o modelo padrão do servidor
    sistema: str
    usuario: str
    temperatura: float = 0.3
    max_tokens: int = 8192

    def chave(self, esquema: type[BaseModel]) -> str:
        conteudo = json.dumps(
            {
                "tarefa": self.tarefa,
                "modelo": self.modelo,
                "sistema": self.sistema,
                "usuario": self.usuario,
                "temperatura": self.temperatura,
                "esquema": esquema.__name__,
                "schema": esquema.model_json_schema(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


class LLMClient(Protocol):
    nome: str

    def gerar(self, pedido: Pedido, esquema: type[T]) -> RespostaLLM[T]: ...


def provedor_bloqueado(
    cliente: LLMClient | None, modelo: str | None = None
) -> ErroPermanente | None:
    """O `ErroPermanente` que já fechou o servidor nesta execução (todo ele ou só `modelo`), se
    houver. Clientes sem esse controle (offline, falsos de teste) nunca estão bloqueados."""
    bloqueio = getattr(cliente, "bloqueio", None)
    return bloqueio(modelo) if callable(bloqueio) else None


# --------------------------------------------------------------------------- custos


@dataclass(frozen=True, slots=True)
class TabelaPrecos:
    """US$ por milhão de tokens (entrada, saída), por modelo. Vazia num servidor local: custo
    zero. Cache: leitura 0,1×, escrita 1,25× da entrada."""

    precos: dict[str, tuple[float, float]] = field(default_factory=dict)

    def custo(self, modelo: str, uso: Uso) -> float:
        entrada, saida = self.precos.get(modelo, (0.0, 0.0))
        return (
            uso.tokens_entrada * entrada
            + uso.tokens_cache_leitura * entrada * 0.1
            + uso.tokens_cache_escrita * entrada * 1.25
            + uso.tokens_saida * saida
        ) / 1_000_000


# --------------------------------------------------------------------------- offline


Manipulador = Callable[[Pedido], dict[str, Any]]


def _manipuladores_padrao() -> dict[str, Manipulador]:
    from fiat_lux.llm.offline import MANIPULADORES

    return dict(MANIPULADORES)


class ClienteNaoConfigurado:
    """Provedor `local` sem `FIATLUX_LLM_URL`: cada chamada falha com um ErroPermanente claro, e
    cada etapa cai na sua reserva (classificação por palavras-chave, consultas determinísticas,
    seleção pelo escore); sem redação, sai o fallback seguro. Nada vai para a rede."""

    nome = "local:sem-servidor"

    def bloqueio(self, modelo: str | None = None) -> ErroPermanente:
        return ErroPermanente(
            "sem_servidor",
            "sem FIATLUX_LLM_URL (aponte para o servidor de LLM no .env, ou use --dry-run para "
            "o cliente offline)",
        )

    def gerar(self, pedido: Pedido, esquema: type[T]) -> RespostaLLM[T]:
        raise self.bloqueio()


class ClienteOffline:
    """Determinístico e sem rede. Cada tarefa tem um manipulador que devolve o JSON da resposta."""

    nome = "offline"

    def __init__(self, manipuladores: dict[str, Manipulador] | None = None) -> None:
        self.manipuladores: dict[str, Manipulador] = (
            manipuladores if manipuladores is not None else _manipuladores_padrao()
        )
        self.chamadas: list[Pedido] = []

    def gerar(self, pedido: Pedido, esquema: type[T]) -> RespostaLLM[T]:
        self.chamadas.append(pedido)
        if pedido.tarefa not in self.manipuladores:
            raise ErroLLM(f"cliente offline sem manipulador para {pedido.tarefa!r}")
        bruto = self.manipuladores[pedido.tarefa](pedido)
        return RespostaLLM(dados=esquema.model_validate(bruto), modelo=f"offline:{pedido.tarefa}")


# --------------------------------------------------------------------------- cache


class ClienteComCache:
    """Cache por hash da entrada (modelo + prompts + esquema): reexecuções não custam nada."""

    def __init__(self, interno: LLMClient, cache: Any) -> None:
        self.interno = interno
        self.cache = cache
        self.nome = f"{interno.nome}+cache"

    def bloqueio(self, modelo: str | None = None) -> ErroPermanente | None:
        return provedor_bloqueado(self.interno, modelo)

    def gerar(self, pedido: Pedido, esquema: type[T]) -> RespostaLLM[T]:
        chave = pedido.chave(esquema)
        achado = self.cache.obter(chave)
        if achado is not None:
            return RespostaLLM(
                dados=esquema.model_validate(achado["dados"]),
                modelo=achado["modelo"],
                uso=Uso(),
                do_cache=True,
            )
        resp = self.interno.gerar(pedido, esquema)
        self.cache.gravar(chave, pedido.tarefa, resp.modelo, resp.dados.model_dump(mode="json"))
        return resp


class Contabilidade:
    """Acumula uso/custo de uma execução e aplica o teto mensal (§12)."""

    def __init__(self, gasto_mes_usd: float = 0.0, teto_mes_usd: float | None = None) -> None:
        self.uso = Uso()
        self.gasto_mes_usd = gasto_mes_usd
        self.teto = teto_mes_usd
        self.modelos: set[str] = set()

    def checar(self) -> None:
        if self.teto is not None and self.gasto_mes_usd + self.uso.custo_usd >= self.teto:
            raise ErroOrcamento(
                f"teto mensal de US$ {self.teto:.2f} atingido (gasto: US$ {self.gasto_mes_usd + self.uso.custo_usd:.2f})"
            )

    def registrar(self, resp: RespostaLLM[Any]) -> None:
        self.uso.somar(resp.uso)
        self.modelos.add(resp.modelo)


def chamar[M: BaseModel](
    cliente: LLMClient, pedido: Pedido, esquema: type[M], contabilidade: Contabilidade | None = None
) -> M:
    """Atalho: checa o orçamento, chama, registra o uso e devolve os dados validados."""
    if contabilidade is not None:
        contabilidade.checar()
    resp = cliente.gerar(pedido, esquema)
    if contabilidade is not None:
        contabilidade.registrar(resp)
    return resp.dados
