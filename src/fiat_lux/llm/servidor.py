"""Cliente do servidor de LLM pela API HTTP (ADR-012).

O contrato é pequeno, e qualquer servidor que o siga serve (detalhes no guia, seção 8):

- `POST /v1/chat` recebe `messages` (`role` system/user/assistant e `content`), `model`
  (opcional: sem ele, o padrão do servidor), `temperature`, `max_tokens` e `allow_fallback`, e
  devolve `content`, `model` (o que de fato respondeu), `fallback_applied`, `tokens_in`,
  `tokens_out`, `duration_s` e `queue_wait_s`;
- `GET /v1/models` lista os modelos (`name`, `installed`, `available`, `context`) e o `default`;
- autenticação por `Authorization: Bearer <chave>`, quando o servidor exige;
- fila cheia responde 429 com `Retry-After`; servidor sob pressão, 503; modelo desconhecido, 404;
- opcional: `GET /v1/status` com a fila (`queue.depth`, `running`, `max_concurrent`,
  `estimated_wait_s`), para o cliente esperar a vez em vez de entrar numa fila longa.

A API não tem saída estruturada: um molde da resposta, gerado do esquema Pydantic, vai no prompt
de sistema, e a resposta é extraída e validada aqui. Fora do formato, o pedido é refeito com o
erro explicado (o modelo vê a própria resposta e a correção pedida).

Servidor atrás de um proxy (ex.: Cloudflare, que desiste em 100–120 s): a resposta que demora
mais vira 524 (ou 504), mas o pedido continua rodando no servidor. Repetir na hora só dobraria o
trabalho na fila; por isso o corte não é repetido, o pedido seguinte espera o servidor ficar livre
(`GET /v1/status`), e um modelo cortado duas vezes fica fora até o fim da execução.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from fiat_lux.llm.cliente import ErroLLM, ErroPermanente, Pedido, RespostaLLM, TabelaPrecos, Uso
from fiat_lux.logs import log

T = TypeVar("T", bound=BaseModel)

_PENSAMENTO = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_ESPERA_PADRAO = {429: 10.0, 503: 30.0}  # sem `Retry-After`
_ESPERA_MAXIMA = 120.0  # por vez; o total da execução é `espera_fila_max_s`
_TENTATIVAS_REDE = 3
_CORTE_PROXY = frozenset({504, 524})  # o proxy desistiu de esperar; o pedido segue no servidor
_CORTES_POR_MODELO = 2  # cortes até o modelo ficar fora da execução
_INTERVALO_STATUS = 5.0  # entre consultas a /v1/status, esperando a vez


# Quem acompanha os pedidos (o andamento da CLI): recebe (evento, tarefa), com evento
# "pedido" (enviado, esperando a resposta), "fila" (429/503, esperando), "formato" (pedindo de
# novo) ou "fim". Uma ContextVar: a CLI liga durante a execução, sem passar nada pelo pipeline.
OBSERVADOR: ContextVar[Callable[[str, str], None] | None] = ContextVar(
    "fiatlux_observador_llm", default=None
)


def _avisar(evento: str, tarefa: str) -> None:
    observador = OBSERVADOR.get()
    if observador is not None:
        observador(evento, tarefa)


# --------------------------------------------------------------------------- formato


def esquema_compacto(esquema: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema do Pydantic sem `$defs`/`$ref` nem títulos: mais fácil para modelos pequenos
    seguirem do que o esquema cheio de referências."""
    bruto = esquema.model_json_schema()
    definicoes: dict[str, Any] = bruto.pop("$defs", {})

    def resolver(no: Any) -> Any:
        if isinstance(no, dict):
            if "$ref" in no:
                return resolver(definicoes[str(no["$ref"]).rsplit("/", 1)[-1]])
            return {
                k: resolver(v)
                for k, v in no.items()
                if not (k == "title" and isinstance(v, str))  # título do esquema, não um campo
            }
        if isinstance(no, list):
            return [resolver(v) for v in no]
        return no

    resolvido: dict[str, Any] = resolver(bruto)
    return resolvido


def molde(no: dict[str, Any]) -> str:
    """Molde legível da resposta, como `{"campo": <true ou false>, "lista": [<texto>, …]}`.

    Modelos pequenos seguem um molde melhor que um JSON Schema: com o esquema cru no prompt, o
    `qwen3:8b` copiava a estrutura e devolvia `{"properties": {…}}`."""
    if "anyOf" in no:
        opcoes = [o for o in no["anyOf"] if o.get("type") != "null"]
        base = molde(opcoes[0]) if opcoes else "null"
        return base if len(opcoes) == len(no["anyOf"]) else f"{base} ou null"
    if "enum" in no:
        return '"<um destes: ' + " | ".join(str(v) for v in no["enum"]) + '>"'
    tipo = no.get("type")
    if tipo == "object":
        obrigatorios = set(no.get("required", ()))
        campos = [
            f'"{nome}": {molde(sub)}' + ("" if nome in obrigatorios else " (opcional)")
            for nome, sub in no.get("properties", {}).items()
        ]
        return "{" + ", ".join(campos) + "}"
    if tipo == "array":
        return f"[{molde(no.get('items', {}))}, …]"
    return {
        "string": '"<texto>"',
        "boolean": "<true ou false>",
        "integer": "<inteiro>",
        "number": "<número>",
    }.get(str(tipo), "<valor>")


def instrucao_formato(esquema: type[BaseModel]) -> str:
    return (
        "\n\n## Formato da resposta\n"
        "Responda SOMENTE com um objeto JSON válido, sem texto antes ou depois e sem blocos de "
        "código, neste formato (troque cada <…> pelo valor; inclua todos os campos, salvo os "
        "marcados como opcionais):\n" + molde(esquema_compacto(esquema))
    )


def _validar[M: BaseModel](esquema: type[M], obj: Any) -> M:
    """Valida a resposta. Se o modelo a embrulhou num único campo (`{"properties": {…}}`,
    `{"resposta": {…}}`), tenta o conteúdo antes de desistir."""
    try:
        return esquema.model_validate(obj)
    except ValidationError:
        if isinstance(obj, dict) and len(obj) == 1:
            interno = next(iter(obj.values()))
            if isinstance(interno, dict):
                try:
                    return esquema.model_validate(interno)
                except ValidationError:
                    pass
        raise


def extrair_json(texto: str) -> Any:
    """O primeiro objeto JSON da resposta. Tolera raciocínio entre `<think>`, cercas de código e
    texto em volta; `ValueError` (com o motivo) se não houver objeto legível."""
    t = _PENSAMENTO.sub("", texto)
    if "<think>" in t.lower():
        raise ValueError("a resposta parou no meio do raciocínio (max_tokens curto demais?)")
    t = _dentro_da_cerca(t)
    inicio = t.find("{")
    if inicio < 0:
        raise ValueError(
            "a resposta não traz um objeto JSON" if t.strip() else "a resposta veio vazia"
        )
    try:
        obj, _ = json.JSONDecoder().raw_decode(t[inicio:])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido: {e.msg} (posição {e.pos})") from e
    return obj


def _dentro_da_cerca(t: str) -> str:
    """O conteúdo do primeiro bloco de código (```json … ```), se houver; senão, o texto todo."""
    ini = t.find("```")
    fim = t.find("```", ini + 3) if ini >= 0 else -1
    if fim < 0:
        return t
    bloco = t[ini + 3 : fim]
    return bloco[4:] if bloco[:4].lower() == "json" else bloco


def _resumir(e: Exception) -> str:
    if isinstance(e, ValidationError):
        partes = []
        for erro in e.errors()[:6]:
            local = ".".join(str(x) for x in erro.get("loc", ())) or "(raiz)"
            partes.append(f"{local}: {erro.get('msg', '')}")
        return "; ".join(partes)
    return str(e)


# --------------------------------------------------------------------------- HTTP


def _detalhe(r: httpx.Response) -> str:
    """O `detail` do corpo de erro, legível e curto."""
    try:
        corpo = r.json()
    except ValueError:
        return r.text[:200].strip()
    detalhe = corpo.get("detail", corpo) if isinstance(corpo, dict) else corpo
    if isinstance(detalhe, list):  # 422: [{"loc": [...], "msg": "..."}]
        return "; ".join(
            f"{'.'.join(str(x) for x in d.get('loc', ()))}: {d.get('msg', '')}"
            if isinstance(d, dict)
            else str(d)
            for d in detalhe[:5]
        )
    return str(detalhe)[:300]


def _eh_json(r: httpx.Response) -> bool:
    return "json" in r.headers.get("content-type", "")


def _retry_after(r: httpx.Response, padrao: float) -> float:
    try:
        return max(1.0, float(r.headers.get("Retry-After", "")))
    except ValueError:
        return padrao


@dataclass(frozen=True, slots=True)
class Fila:
    """A fila do servidor, de `GET /v1/status` (`queue`)."""

    aguardando: int = 0  # `depth`
    rodando: int = 0  # `running`
    simultaneos: int = 1  # `max_concurrent`
    espera_estimada_s: float = 0.0  # `estimated_wait_s` (o servidor não conta o que já roda)

    @property
    def ocupada(self) -> bool:
        return self.aguardando > 0 or self.rodando >= self.simultaneos

    @classmethod
    def de(cls, corpo: Any) -> Fila | None:
        fila = corpo.get("queue") if isinstance(corpo, dict) else None
        if not isinstance(fila, dict) or "running" not in fila:
            return None
        return cls(
            aguardando=int(fila.get("depth") or 0),
            rodando=int(fila.get("running") or 0),
            simultaneos=max(1, int(fila.get("max_concurrent") or 1)),
            espera_estimada_s=float(fila.get("estimated_wait_s") or 0.0),
        )


class ClienteServidor:
    """Fala com o servidor de LLM da instalação. Um por execução: o disjuntor (`bloqueio`), o
    orçamento de espera na fila e o das tarefas opcionais valem até o fim dela."""

    nome = "local"

    def __init__(
        self,
        url: str,
        chave: str | None = None,
        *,
        timeout_s: float = 600,
        tentativas_formato: int = 2,
        espera_fila_max_s: float = 900,
        max_tokens: int = 8192,
        precos: TabelaPrecos | None = None,
        marcador_sem_raciocinio: str = "",
        tarefas_sem_raciocinio: Iterable[str] = (),
        tarefas_opcionais: Iterable[str] = (),
        tempo_max_opcionais_s: float = 300,
        espera_max_opcional_s: float = 120,
        transporte: httpx.BaseTransport | None = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.url = url.strip().rstrip("/")
        cabecalhos = {"User-Agent": "fiat-lux", "Accept": "application/json"}
        if chave:
            cabecalhos["Authorization"] = f"Bearer {chave}"
        self._http = httpx.Client(
            base_url=self.url,
            headers=cabecalhos,
            timeout=httpx.Timeout(timeout_s, connect=15.0),
            transport=transporte,
        )
        self.timeout_s = timeout_s
        self.tentativas_formato = max(1, tentativas_formato)
        self.espera_restante_s = espera_fila_max_s
        self.max_tokens = max_tokens
        self.precos = precos or TabelaPrecos()
        self.marcador_sem_raciocinio = marcador_sem_raciocinio.strip()
        self.tarefas_sem_raciocinio = frozenset(tarefas_sem_raciocinio)
        self.tarefas_opcionais = frozenset(tarefas_opcionais)
        self.tempo_max_opcionais_s = tempo_max_opcionais_s
        self.espera_max_opcional_s = espera_max_opcional_s
        self.tempo_opcionais_s = 0.0  # já gasto nas tarefas opcionais nesta execução
        self.cortes: dict[str, int] = {}  # respostas cortadas pelo proxy (504/524), por modelo
        self._sem_status = False  # o servidor não tem GET /v1/status: não pergunta de novo
        self._esperou_s = 0.0  # esperando a vez, no pedido em curso
        self._dormir = dormir
        self._tem_chave = bool(chave)
        # disjuntor: depois de um ErroPermanente, nada vai à rede até o fim da execução
        self._bloqueio: ErroPermanente | None = None
        self._bloqueio_modelo: dict[str, ErroPermanente] = {}  # "" = o modelo padrão

    def bloqueio(self, modelo: str | None = None) -> ErroPermanente | None:
        if self._bloqueio is not None:
            return self._bloqueio
        return self._bloqueio_modelo.get(modelo) if modelo is not None else None

    def fechar(self) -> None:
        self._http.close()

    def modelos(self) -> dict[str, Any]:
        """`GET /v1/models`: confere a URL e a chave e diz quais modelos existem, sem inferência."""
        return self._pedir("GET", "/v1/models", None, "")

    def fila(self) -> Fila | None:
        """A fila do servidor agora (`GET /v1/status`); `None` se ele não informa (rota ausente,
        erro, outro formato), e aí não pergunta de novo nesta execução."""
        if self._sem_status:
            return None
        try:
            r = self._http.get("/v1/status", timeout=10)
            fila = Fila.de(r.json()) if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError, TypeError):
            fila = None
        if fila is None:
            self._sem_status = True
        return fila

    def _aguardar_vez(self, pedido: Pedido, opcional: bool) -> None:
        """Com o servidor ocupado, espera a vez aqui, e não na fila dele: atrás de um proxy, a
        espera na fila conta para o limite da resposta, e o pedido cortado segue rodando lá,
        atrasando os seguintes. Tarefa opcional (com reserva sem o LLM) espera pouco e, com fila
        longa, nem espera: `ErroLLM` e a etapa segue pela reserva. O tempo esperado fica em
        `_esperou_s`."""
        if opcional:
            limite = min(
                self.espera_max_opcional_s, self.tempo_max_opcionais_s - self.tempo_opcionais_s
            )
        else:
            limite = self.espera_restante_s
        while (fila := self.fila()) is not None and fila.ocupada:
            longa = opcional and fila.espera_estimada_s > limite
            if longa or self._esperou_s + _INTERVALO_STATUS > limite:
                raise self._sem_vez(pedido, opcional, fila if longa else None)
            if not self._esperou_s:
                log().info(
                    "llm_aguarda_vez",
                    tarefa=pedido.tarefa,
                    aguardando=fila.aguardando,
                    rodando=fila.rodando,
                )
                _avisar("fila", pedido.tarefa)
            self._dormir(_INTERVALO_STATUS)
            self._esperou_s += _INTERVALO_STATUS
            if not opcional:
                self.espera_restante_s -= _INTERVALO_STATUS

    def _sem_vez(self, pedido: Pedido, opcional: bool, fila_longa: Fila | None) -> ErroLLM:
        """Desiste de esperar a vez: a tarefa opcional segue pela reserva; a essencial fecha o
        servidor até o fim da execução (`espera_fila_max_s` esgotado)."""
        if not opcional:
            return self._fechar(
                ErroPermanente(
                    "ocupado", "o servidor de LLM ficou ocupado por tempo demais nesta execução"
                )
            )
        if fila_longa is not None:
            return ErroLLM(
                f"fila do servidor de LLM longa (~{fila_longa.espera_estimada_s / 60:.0f} min): "
                f"{pedido.tarefa} segue sem o LLM"
            )
        return ErroLLM(
            f"servidor de LLM ocupado ({self._esperou_s:.0f} s esperando a vez): "
            f"{pedido.tarefa} segue sem o LLM"
        )

    def gerar(self, pedido: Pedido, esquema: type[T]) -> RespostaLLM[T]:
        bloqueio = self.bloqueio(pedido.modelo)
        if bloqueio is not None:
            raise bloqueio.copia()
        opcional = pedido.tarefa in self.tarefas_opcionais
        if opcional and self.tempo_opcionais_s >= self.tempo_max_opcionais_s:
            raise ErroLLM(
                f"tempo das etapas opcionais do LLM esgotado ({self.tempo_opcionais_s:.0f} s): "
                f"{pedido.tarefa} segue sem o LLM"
            )
        inicio = time.perf_counter()
        self._esperou_s = 0.0
        usuario = pedido.usuario
        if self.marcador_sem_raciocinio and pedido.tarefa in self.tarefas_sem_raciocinio:
            usuario = f"{usuario}\n\n{self.marcador_sem_raciocinio}"
        mensagens = [
            {"role": "system", "content": pedido.sistema + instrucao_formato(esquema)},
            {"role": "user", "content": usuario},
        ]
        try:
            self._aguardar_vez(pedido, opcional)
            _avisar("pedido", pedido.tarefa)
            return self._tentar(pedido, esquema, mensagens, inicio)
        finally:
            if opcional:  # a espera conta: o orçamento é do tempo das opcionais, não da inferência
                self.tempo_opcionais_s += max(time.perf_counter() - inicio, self._esperou_s)
            _avisar("fim", pedido.tarefa)

    def _tentar(
        self, pedido: Pedido, esquema: type[T], mensagens: list[dict[str, str]], inicio: float
    ) -> RespostaLLM[T]:
        uso = Uso()
        erro = ""
        for tentativa in range(self.tentativas_formato):
            if tentativa:
                _avisar("formato", pedido.tarefa)
            resp = self._pedir("POST", "/v1/chat", self._corpo(pedido, mensagens), pedido.modelo)
            uso.tokens_entrada += int(resp.get("tokens_in") or 0)
            uso.tokens_saida += int(resp.get("tokens_out") or 0)
            modelo_real = str(resp.get("model") or pedido.modelo or "padrão")
            conteudo = str(resp.get("content") or "")
            try:
                dados = _validar(esquema, extrair_json(conteudo))
            except ValueError as e:  # inclui o ValidationError do Pydantic
                erro = _resumir(e)
                log().warning(
                    "llm_formato",
                    tarefa=pedido.tarefa,
                    tentativa=tentativa,
                    modelo=modelo_real,
                    erro=erro,
                )
                mensagens = [
                    *mensagens,
                    {"role": "assistant", "content": conteudo[:6000]},
                    {
                        "role": "user",
                        "content": f"A resposta anterior não seguiu o formato pedido ({erro}). "
                        "Responda de novo SOMENTE com o objeto JSON, com todos os campos "
                        "obrigatórios.",
                    },
                ]
                continue
            uso.custo_usd = self.precos.custo(modelo_real, uso)
            log().info(
                "llm",
                tarefa=pedido.tarefa,
                modelo=modelo_real,
                fallback=bool(resp.get("fallback_applied")),
                entrada=uso.tokens_entrada,
                saida=uso.tokens_saida,
                fila_s=resp.get("queue_wait_s"),
                duracao_s=resp.get("duration_s"),
            )
            return RespostaLLM(
                dados=dados, modelo=modelo_real, uso=uso, duracao_s=time.perf_counter() - inicio
            )
        raise ErroLLM(
            f"resposta fora do formato em {pedido.tarefa} "
            f"({self.tentativas_formato} tentativa(s)): {erro}"
        )

    def _corpo(self, pedido: Pedido, mensagens: list[dict[str, str]]) -> dict[str, Any]:
        corpo: dict[str, Any] = {
            "messages": mensagens,
            "temperature": pedido.temperatura,
            "max_tokens": min(pedido.max_tokens, self.max_tokens),
            "allow_fallback": True,  # sob pressão, um modelo mais leve em vez de 503
        }
        if pedido.modelo:
            corpo["model"] = pedido.modelo
        return corpo

    def _pedir(
        self, metodo: str, rota: str, corpo: dict[str, Any] | None, modelo: str
    ) -> dict[str, Any]:
        falhas_servidor = 0
        while True:
            inicio = time.perf_counter()
            r = self._enviar(metodo, rota, corpo)
            if r.status_code == 200:
                return self._json(r, rota)
            if r.status_code in _ESPERA_PADRAO:
                self._esperar(r)
            elif r.status_code in _CORTE_PROXY:
                raise self._cortado(r, rota, modelo, time.perf_counter() - inicio)
            elif r.status_code >= 500 and falhas_servidor < 2:
                falhas_servidor += 1
                self._dormir(5.0 * falhas_servidor)
            else:
                raise self._erro_http(r, rota, modelo)

    def _enviar(self, metodo: str, rota: str, corpo: dict[str, Any] | None) -> httpx.Response:
        """Um pedido HTTP, repetido em falhas de rede (até `_TENTATIVAS_REDE` vezes). Demora na
        resposta não se repete: o servidor ainda pode estar gerando."""
        tentativa = 0
        while True:
            tentativa += 1
            try:
                return self._http.request(metodo, rota, json=corpo)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                if tentativa >= _TENTATIVAS_REDE:
                    raise self._fechar(
                        ErroPermanente(
                            "conexao",
                            f"servidor de LLM inalcançável em {self.url} ({type(e).__name__})",
                        )
                    ) from e
            except httpx.TimeoutException as e:
                raise ErroLLM(f"o servidor de LLM não respondeu em {self.timeout_s:.0f} s") from e
            except httpx.TransportError as e:
                if tentativa >= _TENTATIVAS_REDE:
                    raise ErroLLM(
                        f"falha de rede com o servidor de LLM ({type(e).__name__})"
                    ) from e
            self._dormir(2.0 * tentativa)

    def _cortado(self, r: httpx.Response, rota: str, modelo: str, segundos: float) -> ErroLLM:
        """504/524: o proxy na frente do servidor desistiu de esperar a resposta, que continua
        sendo gerada lá. Não repete na hora (dobraria o trabalho na fila; o próximo pedido espera
        a vez); no segundo corte do mesmo modelo, ele fica fora até o fim da execução: as
        respostas dele não cabem no tempo do proxy."""
        corte = f"{r.status_code} em {segundos:.0f} s"
        if rota != "/v1/chat":
            return ErroLLM(f"o proxy na frente do servidor de LLM desistiu de esperar ({corte})")
        n = self.cortes[modelo] = self.cortes.get(modelo, 0) + 1
        nome = modelo or "padrão"
        log().warning("llm_cortado", modelo=nome, status=r.status_code, segundos=round(segundos))
        if n >= _CORTES_POR_MODELO:
            return self._fechar(
                ErroPermanente(
                    "lento",
                    f"as respostas do modelo {nome} passam do tempo que o proxy na frente do "
                    f"servidor espera ({corte})",
                    modelo,
                )
            )
        return ErroLLM(
            f"o proxy na frente do servidor de LLM cortou a resposta ({corte}); o pedido segue "
            "rodando lá"
        )

    @staticmethod
    def _json(r: httpx.Response, rota: str) -> dict[str, Any]:
        try:
            dados = r.json()
        except ValueError as e:
            raise ErroLLM(f"o servidor de LLM devolveu algo que não é JSON em {rota}") from e
        if not isinstance(dados, dict):
            raise ErroLLM(f"resposta inesperada do servidor de LLM em {rota}")
        return dados

    def _esperar(self, r: httpx.Response) -> None:
        """429 (fila cheia) ou 503 (sob pressão): espera o que o servidor pede, até o limite da
        execução; passado o limite, desiste do servidor até o fim dela."""
        espera = min(_retry_after(r, _ESPERA_PADRAO[r.status_code]), _ESPERA_MAXIMA)
        if espera > self.espera_restante_s:
            raise self._fechar(
                ErroPermanente(
                    "ocupado",
                    "o servidor de LLM ficou ocupado (fila cheia ou sob pressão) por tempo "
                    "demais nesta execução",
                )
            )
        log().info(
            "llm_espera",
            status=r.status_code,
            segundos=espera,
            posicao=r.headers.get("X-Queue-Position"),
            estimativa_s=r.headers.get("X-Estimated-Wait"),
        )
        self.espera_restante_s -= espera
        _avisar("fila", "")
        self._dormir(espera)

    def _erro_http(self, r: httpx.Response, rota: str, modelo: str) -> ErroLLM:
        detalhe = _detalhe(r)
        if r.status_code in (401, 403):
            motivo = (
                f"o servidor de LLM recusou a chave ({r.status_code}: {detalhe})"
                if self._tem_chave
                else f"o servidor de LLM pede uma chave, e a FIATLUX_LLM_CHAVE está vazia ({r.status_code})"
            )
            return self._fechar(ErroPermanente("chave", motivo))
        if r.status_code == 404:
            if not _eh_json(r) or detalhe.strip().lower() == "not found":
                return self._fechar(
                    ErroPermanente(
                        "url",
                        f"{self.url}{rota} não existe (FIATLUX_LLM_URL é a raiz do servidor, "
                        "sem /v1 no fim)",
                    )
                )
            return self._fechar(
                ErroPermanente(
                    "modelo",
                    f"o servidor não tem o modelo {modelo or 'padrão'} ({detalhe})",
                    modelo or None,
                )
            )
        if r.status_code == 422:
            return ErroLLM(f"o servidor de LLM recusou o pedido (422): {detalhe}")
        return ErroLLM(f"o servidor de LLM respondeu {r.status_code} em {rota}: {detalhe}")

    def _fechar(self, erro: ErroPermanente) -> ErroPermanente:
        if erro.modelo is None:
            self._bloqueio = erro
        else:
            self._bloqueio_modelo[erro.modelo] = erro
        log().warning("llm_indisponivel", causa=erro.causa, motivo=erro.motivo)
        return erro
