"""Cliente de LLM (plano §5, §9; ADR-008).

`LLMClient` é um Protocol: o pipeline não conhece o provedor. Implementações:

- `ClienteClaude`: SDK oficial `anthropic` (2.x), saída estruturada validada por Pydantic
  (`messages.parse` + `output_format`), profundidade controlada por `output_config.effort`
  (a API 2026-10-21 não aceita mais `temperature`), cache de prompt automático e
  `fallbacks: "default"` nos modelos que o suportam (Sonnet 5.5). Recusas (`stop_reason ==
  "refusal"`) viram `ErroRecusa`, tratado pelo chamador.
- `ClienteOffline`: determinístico e sem rede, delega a "manipuladores" por tarefa
  (`fiat_lux.llm.offline`). Usado em testes, `--dry-run` sem chave e como reserva.
- `ClienteComCache`: embrulha qualquer cliente com cache por hash da entrada (§9).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel

from fiat_lux.logs import log

T = TypeVar("T", bound=BaseModel)
Esforco = Literal["low", "medium", "high", "xhigh", "max"]

# Modelos com fallback server-side (beta `server-side-fallback-2026-07-01`, forma "default").
# Haiku 5.5 não tem fallback: uma recusa fica recusada.
MODELOS_COM_FALLBACK = frozenset(
    {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
)
BETA_FALLBACK = "server-side-fallback-2026-07-01"


class ErroLLM(RuntimeError):
    """Falha ao obter resposta válida do LLM."""


class ErroRecusa(ErroLLM):
    """O modelo recusou (classificador de segurança)."""

    def __init__(self, categoria: str | None, explicacao: str | None = None) -> None:
        super().__init__(f"recusa do modelo (categoria={categoria})")
        self.categoria = categoria
        self.explicacao = explicacao


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
    tarefa: str  # "classificacao", "consultas", "selecao", "redacao", "juiz", "avaliacao"
    modelo: str
    sistema: str
    usuario: str
    esforco: str = "medium"  # low | medium | high | xhigh | max
    max_tokens: int = 16000

    def chave(self, esquema: type[BaseModel]) -> str:
        conteudo = json.dumps(
            {
                "tarefa": self.tarefa,
                "modelo": self.modelo,
                "sistema": self.sistema,
                "usuario": self.usuario,
                "esforco": self.esforco,
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


# --------------------------------------------------------------------------- custos


@dataclass(frozen=True, slots=True)
class TabelaPrecos:
    """US$ por milhão de tokens (entrada, saída). Cache: leitura 0,1×, escrita 1,25× da entrada."""

    precos: dict[str, tuple[float, float]]

    def custo(self, modelo: str, uso: Uso) -> float:
        entrada, saida = self.precos.get(modelo, (0.0, 0.0))
        return (
            uso.tokens_entrada * entrada
            + uso.tokens_cache_leitura * entrada * 0.1
            + uso.tokens_cache_escrita * entrada * 1.25
            + uso.tokens_saida * saida
        ) / 1_000_000


PRECOS_PADRAO = TabelaPrecos(
    {
        "claude-haiku-5-5": (0.10, 0.50),
        "claude-sonnet-5-5": (2.00, 10.00),
        "claude-opus-5-5": (4.00, 20.00),
    }
)


# --------------------------------------------------------------------------- Claude


class ClienteClaude:
    nome = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        timeout_s: float = 120,
        max_retries: int = 3,
        precos: TabelaPrecos = PRECOS_PADRAO,
        cliente: Any | None = None,
    ) -> None:
        if cliente is None:
            import anthropic

            cliente = anthropic.Anthropic(
                api_key=api_key, timeout=timeout_s, max_retries=max_retries
            )
        self._cli = cliente
        self.precos = precos

    def gerar(self, pedido: Pedido, esquema: type[T]) -> RespostaLLM[T]:
        import anthropic

        inicio = time.perf_counter()
        extras: dict[str, Any] = {}
        if pedido.modelo in MODELOS_COM_FALLBACK:
            extras = {"betas": [BETA_FALLBACK], "fallbacks": "default"}
        try:
            resp = self._cli.beta.messages.parse(
                model=pedido.modelo,
                max_tokens=pedido.max_tokens,
                system=pedido.sistema,
                messages=[{"role": "user", "content": pedido.usuario}],
                output_format=esquema,
                output_config={"effort": pedido.esforco},  # type: ignore[arg-type]
                cache_control={"type": "ephemeral"},
                **extras,
            )
        except anthropic.BadRequestError as e:
            raise ErroLLM(f"requisição inválida ({pedido.tarefa}): {e.message}") from e
        except anthropic.AuthenticationError as e:
            raise ErroLLM("chave da API inválida ou ausente (ANTHROPIC_API_KEY)") from e
        except anthropic.PermissionDeniedError as e:
            raise ErroLLM("a chave não tem permissão para este modelo") from e
        except anthropic.NotFoundError as e:
            raise ErroLLM(f"modelo ou endpoint inexistente: {pedido.modelo}") from e
        except anthropic.RateLimitError as e:
            raise ErroLLM("limite de taxa da API (429) após as tentativas automáticas") from e
        except anthropic.APIStatusError as e:
            raise ErroLLM(f"erro da API ({e.status_code}) em {pedido.tarefa}") from e
        except anthropic.APIConnectionError as e:
            raise ErroLLM("falha de conexão com a API da Anthropic") from e
        uso = Uso(
            tokens_entrada=int(getattr(resp.usage, "input_tokens", 0) or 0),
            tokens_saida=int(getattr(resp.usage, "output_tokens", 0) or 0),
            tokens_cache_leitura=int(getattr(resp.usage, "cache_read_input_tokens", 0) or 0),
            tokens_cache_escrita=int(getattr(resp.usage, "cache_creation_input_tokens", 0) or 0),
        )
        modelo_real = str(getattr(resp, "model", pedido.modelo) or pedido.modelo)
        uso.custo_usd = self.precos.custo(modelo_real, uso)
        if resp.stop_reason == "refusal":
            det = getattr(resp, "stop_details", None)
            raise ErroRecusa(getattr(det, "category", None), getattr(det, "explanation", None))
        if resp.stop_reason == "max_tokens":
            raise ErroLLM(f"resposta truncada por max_tokens em {pedido.tarefa}")
        dados = resp.parsed_output
        if dados is None:
            raise ErroLLM(f"saída estruturada ausente em {pedido.tarefa}")
        log().info(
            "llm",
            tarefa=pedido.tarefa,
            modelo=modelo_real,
            entrada=uso.tokens_entrada,
            saida=uso.tokens_saida,
            cache_leitura=uso.tokens_cache_leitura,
            custo=round(uso.custo_usd, 5),
        )
        return RespostaLLM(
            dados=dados, modelo=modelo_real, uso=uso, duracao_s=time.perf_counter() - inicio
        )


# --------------------------------------------------------------------------- offline


Manipulador = Callable[[Pedido], dict[str, Any]]


def _manipuladores_padrao() -> dict[str, Manipulador]:
    from fiat_lux.llm.offline import MANIPULADORES

    return dict(MANIPULADORES)


class ClienteSemCredencial:
    """Provedor `anthropic` sem chave: cada chamada falha com um ErroLLM claro, e cada etapa cai
    na sua reserva (classificação por palavras-chave, consultas determinísticas, seleção pelo
    escore); sem redação, sai o fallback seguro. Nada é enviado à API."""

    nome = "anthropic:sem-credencial"

    def gerar(self, pedido: Pedido, esquema: type[T]) -> RespostaLLM[T]:
        raise ErroLLM(
            "sem ANTHROPIC_API_KEY: defina a chave no .env, ou use --dry-run (cliente offline)"
        )


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
