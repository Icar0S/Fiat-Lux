"""Servidor de LLM pela API HTTP (ADR-012): contrato, formato JSON, fila e falhas definitivas.

Nada vai à rede: o `httpx.MockTransport` faz o papel do servidor.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
import types
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import structlog

from fiat_lux import instalacao as inst
from fiat_lux.agente import consultas
from fiat_lux.agente.contexto import ContextoDoDia
from fiat_lux.agente.selecao import selecionar
from fiat_lux.config import Settings
from fiat_lux.llm.cache import CacheLLM
from fiat_lux.llm.cliente import (
    ClienteComCache,
    ClienteNaoConfigurado,
    ErroLLM,
    ErroPermanente,
    Pedido,
    RespostaLLM,
    motivo_curto,
    provedor_bloqueado,
)
from fiat_lux.llm.esquemas import ClassificacaoLote, Julgamento, Selecao
from fiat_lux.llm.servidor import (
    ClienteServidor,
    esquema_compacto,
    extrair_json,
    instrucao_formato,
    molde,
)
from fiat_lux.noticias.classificacao import classificar
from fiat_lux.noticias.modelos import Artigo, Cluster
from fiat_lux.orquestracao.diaria import (
    ResultadoDiaria,
    aviso_de_falha,
    registrar_bloqueio,
    resumo_da_falha,
)
from fiat_lux.orquestracao.nucleo import Rastreio, Recursos, gerar_palavra
from fiat_lux.pastoral import perfil
from fiat_lux.rag.busca import Candidato

URL = "http://llm.teste"
JULGAMENTO_OK = {
    "partidario": False,
    "castigo_ou_profecia": False,
    "exposicao_vitimas": False,
    "tom_condenatorio": False,
    "motivos": [],
}


def resposta_chat(conteudo: str, modelo: str = "qwen3:4b", **extra: Any) -> dict[str, Any]:
    return {
        "content": conteudo,
        "model": modelo,
        "requested_model": modelo,
        "fallback_applied": False,
        "tokens_in": 120,
        "tokens_out": 30,
        "duration_s": 1.5,
        "queue_wait_s": 0.0,
        **extra,
    }


class Servidor:
    """Servidor falso: responde da fila `respostas` (status, corpo, cabeçalhos) e guarda os
    pedidos recebidos. Uma exceção na fila é levantada no lugar da resposta. Não tem
    `GET /v1/status` (404), como qualquer servidor que não informa a fila."""

    def __init__(self, *respostas: Any) -> None:
        self.respostas = list(respostas)
        self.pedidos: list[httpx.Request] = []
        self.esperas: list[float] = []
        self.status = 0  # consultas a /v1/status

    def fila(self) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not Found"})

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path == "/v1/status":
            self.status += 1
            return self.fila()
        self.pedidos.append(pedido)
        item = self.respostas.pop(0) if self.respostas else (200, resposta_chat("{}"), {})
        if isinstance(item, Exception):
            raise item
        status, corpo, cabecalhos = item
        return httpx.Response(status, json=corpo, headers=cabecalhos)

    def corpo(self, i: int) -> dict[str, Any]:
        dados: dict[str, Any] = json.loads(self.pedidos[i].content)
        return dados

    def cliente(self, chave: str | None = "sk-teste", **kw: Any) -> ClienteServidor:
        return ClienteServidor(
            URL, chave, transporte=httpx.MockTransport(self), dormir=self.esperas.append, **kw
        )


def pedido(modelo: str = "qwen3:8b", tarefa: str = "juiz", max_tokens: int = 4000) -> Pedido:
    return Pedido(tarefa, modelo, "Avalie.", "<mensagem>texto</mensagem>", 0.0, max_tokens)


# ------------------------------------------------------------------ contrato e formato


def test_chat_pede_json_no_prompt_e_valida_a_resposta() -> None:
    texto = "Claro! Segue:\n```json\n" + json.dumps(JULGAMENTO_OK) + "\n```\nQualquer coisa."
    srv = Servidor((200, resposta_chat(texto, "qwen3:4b", fallback_applied=True), {}))
    r = srv.cliente().gerar(pedido(max_tokens=16000), Julgamento)
    assert r.dados.aprovado and r.modelo == "qwen3:4b"  # o modelo que de fato respondeu
    assert (r.uso.tokens_entrada, r.uso.tokens_saida, r.uso.custo_usd) == (120, 30, 0.0)
    enviado = srv.pedidos[0]
    assert enviado.url.path == "/v1/chat" and enviado.headers["Authorization"] == "Bearer sk-teste"
    corpo = srv.corpo(0)
    assert corpo["model"] == "qwen3:8b" and corpo["temperature"] == 0.0
    assert corpo["max_tokens"] == 8192  # teto da API
    assert corpo["allow_fallback"] is True
    sistema, usuario = corpo["messages"]
    assert sistema["role"] == "system" and "## Formato da resposta" in sistema["content"]
    assert '"partidario"' in sistema["content"] and usuario["role"] == "user"


def test_sem_modelo_nem_chave_usa_o_padrao_do_servidor() -> None:
    srv = Servidor((200, resposta_chat(json.dumps(JULGAMENTO_OK)), {}))
    srv.cliente(chave=None).gerar(pedido(modelo=""), Julgamento)
    assert "model" not in srv.corpo(0) and "Authorization" not in srv.pedidos[0].headers


def test_resposta_fora_do_formato_e_pedida_de_novo_com_o_erro() -> None:
    srv = Servidor(
        (200, resposta_chat("Não sei responder em JSON."), {}),
        (200, resposta_chat(json.dumps(JULGAMENTO_OK)), {}),
    )
    r = srv.cliente().gerar(pedido(), Julgamento)
    assert r.dados.aprovado and len(srv.pedidos) == 2
    mensagens = srv.corpo(1)["messages"]
    assert [m["role"] for m in mensagens] == ["system", "user", "assistant", "user"]
    assert "não seguiu o formato" in mensagens[-1]["content"]
    assert r.uso.tokens_entrada == 240  # as duas tentativas contam


def test_campo_faltando_tambem_volta_ao_modelo_e_depois_desiste() -> None:
    incompleto = json.dumps({"partidario": False})
    srv = Servidor((200, resposta_chat(incompleto), {}), (200, resposta_chat(incompleto), {}))
    cli = srv.cliente()
    with pytest.raises(ErroLLM, match="fora do formato") as e:
        cli.gerar(pedido(), Julgamento)
    assert not isinstance(e.value, ErroPermanente) and "castigo_ou_profecia" in str(e.value)
    assert provedor_bloqueado(cli) is None


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ('<think>pensando {"x": 1}</think>{"ok": true}', {"ok": True}),
        ('Resposta: {"ok": true} e mais texto {"outro": 1}', {"ok": True}),
        ('```\n{"ok": true}\n```', {"ok": True}),
    ],
)
def test_extrair_json_tolera_raciocinio_cercas_e_texto(texto: str, esperado: Any) -> None:
    assert extrair_json(texto) == esperado


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("", "vazia"),
        ("só texto", "não traz um objeto JSON"),
        ("<think>pensando sem fim", "meio do raciocínio"),
        ('{"ok": tru', "JSON inválido"),
    ],
)
def test_extrair_json_explica_o_que_faltou(texto: str, motivo: str) -> None:
    with pytest.raises(ValueError, match=motivo):
        extrair_json(texto)


def test_esquema_compacto_sem_referencias_nem_titulos() -> None:
    esquema = esquema_compacto(ClassificacaoLote)
    texto = json.dumps(esquema)
    assert "$ref" not in texto and "$defs" not in texto and '"title"' not in texto
    grupo = esquema["properties"]["grupos"]["items"]
    assert "luto_tragedia" in grupo["properties"]["categoria"]["enum"]
    assert set(grupo["required"]) >= {"id", "categoria", "gravidade", "rotulo", "confianca"}


def test_prompt_traz_um_molde_e_nao_o_json_schema() -> None:
    """Com o JSON Schema cru, o qwen3:8b devolvia `{"properties": {…}}` (visto em 10/11/2026)."""
    instrucao = instrucao_formato(ClassificacaoLote)
    assert '"properties"' not in instrucao and '"required"' not in instrucao
    assert '{"grupos": [{"id": "<texto>", "categoria": "<um destes: luto_tragedia | ' in instrucao
    assert '"sensivel": "<um destes: suicidio | ' in instrucao and "ou null (opcional)" in instrucao
    assert instrucao.rstrip().endswith("}, …]}")
    assert molde(esquema_compacto(Julgamento)).startswith('{"partidario": <true ou false>')


def test_molde_da_redacao_pede_a_reflexao_em_4_paragrafos_e_junta_num_texto() -> None:
    """Pedida como um texto de 180 a 380 palavras, o qwen2.5-coder:7b escrevia ~90 a 120 (em
    11/11/2026); a estrutura de 4 parágrafos, cada um com o seu papel, é o que ele segue."""
    from fiat_lux.llm.esquemas import Redacao

    m = molde(esquema_compacto(Redacao))
    assert '"olhar_sobre_o_dia": "<um parágrafo de 3 a 4 frases sobre o momento>"' in m
    assert '"reflexao": ["<1º parágrafo, 4 a 5 frases: o que diz a passagem principal, com o ' in m
    assert m.count("º parágrafo") == 4 and ", …" not in m
    r = Redacao.model_validate(
        {
            "olhar_sobre_o_dia": "o",
            "reflexao": ["Um {{P1}}.", " Dois. ", "", "Três."],
            "ensinamento": "e",
            "gesto": "g",
            "oracao": "o",
        }
    )
    assert r.reflexao == "Um {{P1}}.\n\nDois.\n\nTrês."
    assert Redacao(**r.model_dump()).reflexao == r.reflexao  # o cache guarda o texto já junto


def test_resposta_embrulhada_num_campo_e_aceita_sem_nova_tentativa() -> None:
    srv = Servidor((200, resposta_chat(json.dumps({"properties": JULGAMENTO_OK})), {}))
    assert srv.cliente().gerar(pedido(), Julgamento).dados.aprovado
    assert len(srv.pedidos) == 1


# ------------------------------------------------------------------ fila e falhas


def test_fila_cheia_espera_o_que_o_servidor_pede() -> None:
    srv = Servidor(
        (429, {"detail": "fila cheia"}, {"Retry-After": "7", "X-Queue-Position": "3"}),
        (503, {"detail": "sob pressão"}, {}),
        (200, resposta_chat(json.dumps(JULGAMENTO_OK)), {}),
    )
    cli = srv.cliente(espera_fila_max_s=100)
    assert cli.gerar(pedido(), Julgamento).dados.aprovado
    assert srv.esperas == [7.0, 30.0] and cli.espera_restante_s == 63.0


def test_ocupado_por_tempo_demais_desiste_ate_o_fim_da_execucao() -> None:
    srv = Servidor((503, {"detail": "sob pressão"}, {"Retry-After": "60"}))
    cli = srv.cliente(espera_fila_max_s=30)
    with pytest.raises(ErroPermanente) as e:
        cli.gerar(pedido(), Julgamento)
    assert e.value.causa == "ocupado" and srv.esperas == []
    with pytest.raises(ErroPermanente):
        cli.gerar(pedido(), Julgamento)
    assert len(srv.pedidos) == 1


def test_chave_recusada_fecha_o_cliente_depois_da_primeira_chamada() -> None:
    srv = Servidor((401, {"detail": "informe a chave no header: Authorization: Bearer sk-..."}, {}))
    cli = srv.cliente()
    with pytest.raises(ErroPermanente) as primeiro:
        cli.gerar(pedido(), Julgamento)
    assert primeiro.value.causa == "chave" and primeiro.value.modelo is None
    assert str(primeiro.value).startswith("LLM indisponível: o servidor de LLM recusou a chave")
    with pytest.raises(ErroPermanente):  # a segunda nem vai à rede
        cli.gerar(pedido("qwen3:4b", "classificacao"), Julgamento)
    assert len(srv.pedidos) == 1 and provedor_bloqueado(cli) is not None
    assert motivo_curto(primeiro.value) == "sem o LLM"


def test_sem_chave_o_401_diz_que_a_chave_falta() -> None:
    srv = Servidor((401, {"detail": "informe a chave"}, {}))
    with pytest.raises(ErroPermanente, match="FIATLUX_LLM_CHAVE está vazia"):
        srv.cliente(chave=None).gerar(pedido(), Julgamento)


def test_modelo_desconhecido_fecha_so_aquele_modelo() -> None:
    srv = Servidor(
        (404, {"detail": "modelo desconhecido: qwen9:99b"}, {}),
        (200, resposta_chat(json.dumps(JULGAMENTO_OK)), {}),
    )
    cli = srv.cliente()
    with pytest.raises(ErroPermanente) as e:
        cli.gerar(pedido("qwen9:99b"), Julgamento)
    assert e.value.causa == "modelo" and e.value.modelo == "qwen9:99b"
    assert "qwen9:99b" in motivo_curto(e.value)  # o aviso da etapa diz qual modelo
    assert cli.gerar(pedido("qwen3:4b"), Julgamento).dados.aprovado
    assert provedor_bloqueado(cli) is None and provedor_bloqueado(cli, "qwen9:99b") is not None


def test_rota_inexistente_e_url_errada() -> None:
    srv = Servidor((404, {"detail": "Not Found"}, {}))
    with pytest.raises(ErroPermanente) as e:
        srv.cliente().gerar(pedido(), Julgamento)
    assert e.value.causa == "url" and "sem /v1" in e.value.motivo


def test_servidor_fora_do_ar_desiste_depois_de_tres_tentativas() -> None:
    falha = httpx.ConnectError("conexão recusada")
    srv = Servidor(falha, falha, falha)
    cli = srv.cliente()
    with pytest.raises(ErroPermanente) as e:
        cli.gerar(pedido(), Julgamento)
    assert e.value.causa == "conexao" and len(srv.pedidos) == 3 and srv.esperas == [2.0, 4.0]


def test_demora_na_resposta_nao_fecha_o_cliente() -> None:
    srv = Servidor(httpx.ReadTimeout("lento"), (200, resposta_chat(json.dumps(JULGAMENTO_OK)), {}))
    cli = srv.cliente(timeout_s=5)
    with pytest.raises(ErroLLM, match="não respondeu em 5 s") as e:
        cli.gerar(pedido(), Julgamento)
    assert not isinstance(e.value, ErroPermanente)
    assert cli.gerar(pedido(), Julgamento).dados.aprovado


def test_pedido_recusado_422_diz_o_campo() -> None:
    erro = {"detail": [{"loc": ["body", "max_tokens"], "msg": "deve ser <= 8192"}]}
    srv = Servidor((422, erro, {}))
    with pytest.raises(ErroLLM, match=r"body\.max_tokens: deve ser <= 8192"):
        srv.cliente().gerar(pedido(), Julgamento)


def test_cache_responde_mesmo_com_o_servidor_fechado(tmp_path) -> None:
    srv = Servidor((200, resposta_chat(json.dumps(JULGAMENTO_OK)), {}), (401, {"detail": "x"}, {}))
    cli = ClienteComCache(srv.cliente(), CacheLLM(tmp_path / "llm.sqlite"))
    cli.gerar(pedido(), Julgamento)  # vai para o cache
    with pytest.raises(ErroPermanente):
        cli.gerar(pedido(tarefa="outra"), Julgamento)
    assert provedor_bloqueado(cli) is not None
    assert cli.gerar(pedido(), Julgamento).do_cache


def test_sem_servidor_configurado_e_permanente() -> None:
    cli = ClienteNaoConfigurado()
    bloqueio = provedor_bloqueado(cli)
    assert bloqueio is not None and bloqueio.causa == "sem_servidor"
    with pytest.raises(ErroPermanente, match="FIATLUX_LLM_URL"):
        cli.gerar(pedido(), Julgamento)


# ------------------------------------------------------------------ configuração


def test_url_chave_e_modelos_vem_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIATLUX_LLM_URL", " http://llm.teste ")
    monkeypatch.setenv("FIATLUX_LLM_MODELO", "qwen3:4b")
    monkeypatch.setenv("FIATLUX_LLM_MODELO_GERACAO", "qwen3:8b")
    monkeypatch.setenv("FIATLUX_LLM_CHAVE", "")
    s = Settings(_env_file=None)
    assert s.llm.url == "http://llm.teste" and s.llm_chave is None
    assert (s.llm.modelo_classificacao, s.llm.modelo_geracao, s.llm.modelo_juiz) == (
        "qwen3:4b",
        "qwen3:8b",
        "qwen3:4b",
    )


def test_sem_url_o_padrao_e_nao_configurado(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("FIATLUX_LLM_URL", "FIATLUX_LLM_MODELO", "FIATLUX_LLM_MODELO_GERACAO"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.llm.provedor == "local" and s.llm.url == "" and s.llm.modelo_geracao == ""
    assert s.custos.precos == {}  # servidor local: custo zero


# ------------------------------------------------------------------ teste do configurar


MODELOS = {
    "default": "qwen3:4b",
    "default_vision": "moondream",
    "models": [
        {"name": "qwen3:4b", "tier": "light", "context": 32768, "installed": True,
         "available": True, "loaded": True, "resident_mb": 3000, "description": "padrão"},
        {"name": "qwen3:8b", "tier": "standard", "context": 32768, "installed": True,
         "available": False, "loaded": False, "resident_mb": 6000, "description": "",
         "unavailable_reason": "memória"},
        {"name": "pequeno:1b", "tier": "light", "context": 2048, "installed": True,
         "available": True, "loaded": False, "resident_mb": 900, "description": ""},
        {"name": "qwen2.5-coder:7b", "tier": "standard", "context": 32768, "installed": False,
         "available": False, "loaded": False, "resident_mb": 5000, "description": ""},
    ],
}  # fmt: skip


def _settings(monkeypatch: pytest.MonkeyPatch, **modelos: str) -> Settings:
    for var in ("FIATLUX_LLM_MODELO", "FIATLUX_LLM_MODELO_GERACAO", "FIATLUX_LLM_MODELO_JUIZ",
                "FIATLUX_LLM_MODELO_CLASSIFICACAO"):  # fmt: skip
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("FIATLUX_LLM_URL", URL)
    for tarefa, nome in modelos.items():
        monkeypatch.setenv(f"FIATLUX_LLM_MODELO_{tarefa.upper()}", nome)
    return Settings(_env_file=None)


def test_testar_llm_confere_os_modelos_sem_inferencia(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, geracao="qwen3:8b")
    srv = Servidor((200, MODELOS, {}))
    sit = inst.testar_llm(s, srv.cliente())
    assert sit.estado == "ok" and srv.pedidos[0].url.path == "/v1/models"
    assert dict(sit.modelos) == {
        "classificação": "qwen3:4b",
        "seleção e redação": "qwen3:8b",
        "juiz": "qwen3:4b",
    }
    assert any("qwen3:8b não está disponível agora (memória)" in a for a in sit.avisos)


@pytest.mark.parametrize(
    ("modelo", "trecho"),
    [("qwen9:99b", "não tem o modelo qwen9:99b"), ("qwen2.5-coder:7b", "ainda não foi baixado")],
)
def test_testar_llm_modelo_que_falta(
    monkeypatch: pytest.MonkeyPatch, modelo: str, trecho: str
) -> None:
    sit = inst.testar_llm(
        _settings(monkeypatch, juiz=modelo), Servidor((200, MODELOS, {})).cliente()
    )
    assert (sit.estado, sit.causa) == ("indisponivel", "modelo") and trecho in sit.detalhe


def test_testar_llm_janela_curta_vira_aviso(monkeypatch: pytest.MonkeyPatch) -> None:
    sit = inst.testar_llm(
        _settings(monkeypatch, classificacao="pequeno:1b"), Servidor((200, MODELOS, {})).cliente()
    )
    assert sit.estado == "ok" and any("janela de 2048 tokens" in a for a in sit.avisos)


def test_testar_llm_chave_recusada_e_servidor_fora(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    sit = inst.testar_llm(s, Servidor((401, {"detail": "chave"}, {})).cliente())
    assert (sit.estado, sit.causa) == ("indisponivel", "chave")
    falha = httpx.ConnectError("recusada")
    sit = inst.testar_llm(s, Servidor(falha, falha, falha).cliente())
    assert (sit.estado, sit.causa) == ("indisponivel", "conexao")


def test_testar_llm_sem_servidor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIATLUX_LLM_URL", raising=False)
    assert inst.testar_llm(Settings(_env_file=None)).estado == "sem_servidor"


# ------------------------------------------------------------------ etapas sem o LLM


class Bloqueado:
    """Cliente que já sabe que o servidor está fora (como o ClienteServidor depois do 1º erro)."""

    nome = "bloqueado"

    def __init__(self, causa: str = "conexao", modelo: str | None = None) -> None:
        self.erro = ErroPermanente(
            causa, "servidor de LLM inalcançável em http://llm.teste", modelo
        )
        self.chamadas = 0

    def bloqueio(self, modelo: str | None = None) -> ErroPermanente | None:
        if self.erro.modelo is None or self.erro.modelo == modelo:
            return self.erro
        return None

    def gerar(self, pedido: Pedido, esquema: Any) -> Any:
        self.chamadas += 1
        raise self.erro.copia()


def _cluster(escopo: str, titulo: str) -> Cluster:
    agora = dt.datetime(2026, 11, 10, 12, tzinfo=dt.UTC)
    artigos = [
        Artigo(
            url=f"https://x.com/{escopo}/{i}",
            titulo=titulo,
            fonte_nome=f"F{i}",
            publicado_em=agora,
            escopo=escopo,  # type: ignore[arg-type]
            fonte_coleta="rss:teste",
        )
        for i in range(2)
    ]
    return Cluster(escopo=escopo, artigos=artigos, relevancia=5)  # type: ignore[arg-type]


def test_classificacao_tenta_uma_vez_e_avisa_uma_vez() -> None:
    llm = Bloqueado()
    clusters = [
        _cluster(e, "Enchente deixa desabrigados") for e in ("mundial", "nacional", "regional")
    ]
    avisos = classificar(clusters, llm, "qwen3:4b")
    assert llm.chamadas == 1
    assert avisos == ["classificação das notícias por palavras-chave (sem o LLM)"]
    assert all(c.classificado_por == "palavras" for c in clusters)


def test_consultas_sem_o_llm() -> None:
    ctx = ContextoDoDia(data=dt.date(2026, 11, 10), liturgia=None, perfil=perfil("catolico"))
    ctx.evangelho_resumo = "Somos servos inúteis"
    textos, _, avisos = consultas.gerar(ctx, Bloqueado(), "qwen3:4b")
    assert textos and avisos == ["consultas só determinísticas (sem o LLM)"]


def _cand(i: int, livro: str, escore: float) -> Candidato:
    return Candidato(
        id=f"p:{i}",
        traducao="ms",
        livro=livro,
        versiculo_ids=[i],
        refs_canonicas=[f"{livro}.1.{i}"],
        texto=f"Texto {i}",
        textos=[f"Texto {i}"],
        caps_vers=[(1, i)],
        escores={"S": escore},
    )


CANDS = [_cand(1, "MAT", 0.9), _cand(2, "JHN", 0.8), _cand(3, "PSA", 0.7)]
CTX = ContextoDoDia(data=dt.date(2026, 11, 10), liturgia=None, perfil=perfil("catolico"))


def test_selecao_sem_o_llm_nao_tenta_de_novo() -> None:
    llm = Bloqueado()
    e = selecionar(CTX, CANDS, llm, "qwen3:8b")
    assert llm.chamadas == 1 and e.metodo == "deterministico"
    assert e.alertas == ["seleção pelo escore (sem o LLM)"]


def test_selecao_com_falha_passageira_repete_sem_dizer_que_a_resposta_foi_invalida() -> None:
    usuarios: list[str] = []

    class Instavel:
        nome = "instavel"

        def gerar(self, pedido: Pedido, esquema: Any) -> RespostaLLM[Selecao]:
            usuarios.append(pedido.usuario)
            raise ErroLLM("o servidor de LLM não respondeu em 600 s")

    e = selecionar(CTX, CANDS, Instavel(), "qwen3:8b")
    assert len(usuarios) == 2 and usuarios[0] == usuarios[1]  # nada de "resposta inválida"
    assert e.alertas == [
        "seleção do LLM falhou duas vezes: o servidor de LLM não respondeu em 600 s"
    ]


def test_sem_o_modelo_de_geracao_nem_busca_passagens() -> None:
    """O fallback sairia de qualquer jeito; o rerank neural (≈ 1 min em CPU) é pulado."""
    s = Settings(_env_file=None)
    r = Recursos(s, None, Bloqueado(), None, None, None)  # type: ignore[arg-type]
    rast = Rastreio()
    with pytest.raises(ErroPermanente):
        gerar_palavra(CTX, None, r, rast)
    assert rast.etapa == "redacao" and r._rec is None


def test_so_o_modelo_de_classificacao_fora_nao_impede_a_redacao() -> None:
    s = Settings(_env_file=None)
    s.llm.modelo_classificacao, s.llm.modelo_geracao = "qwen3:4b", "qwen3:8b"

    class Recuperou(Exception):
        pass

    class Rec:
        def recuperar(self, entrada: object) -> list[Candidato]:
            raise Recuperou

    estado = SimpleNamespace(passagens_recentes=lambda *a: [])
    llm = Bloqueado(causa="modelo", modelo="qwen3:4b")
    r = Recursos(s, estado, llm, None, None, None)  # type: ignore[arg-type]
    r._rec = Rec()  # type: ignore[assignment]
    with pytest.raises(Recuperou):  # passou pelas consultas e chegou à busca
        gerar_palavra(CTX, None, r, Rastreio())
    assert llm.chamadas == 1  # a das consultas, que usam o modelo de classificação


def test_avisos_dizem_o_motivo_uma_vez_e_o_alerta_usa_o_motivo() -> None:
    res = ResultadoDiaria(avisos=["consultas só determinísticas (sem o LLM)"])
    aviso_de_falha(res, "redacao", Bloqueado().erro.copia(), "diaria_falhou")
    registrar_bloqueio(res, Bloqueado())
    assert res.avisos[0] == (
        "LLM indisponível nesta execução: servidor de LLM inalcançável em http://llm.teste"
    )
    assert res.avisos[-1].startswith("sem a redação (sem o LLM): saiu a mensagem de contingência")
    assert res.llm_causa == "conexao"
    assert (
        resumo_da_falha(res, 2)
        == "LLM indisponível: servidor de LLM inalcançável em http://llm.teste"
    )


def test_falta_de_servidor_ja_avisada_no_inicio_nao_se_repete() -> None:
    res = ResultadoDiaria(avisos=["sem FIATLUX_LLM_URL: …"])
    registrar_bloqueio(res, ClienteNaoConfigurado())
    assert res.avisos == ["sem FIATLUX_LLM_URL: …"] and res.llm_causa == "sem_servidor"


def test_falha_inesperada_continua_com_traceback_no_log() -> None:
    res = ResultadoDiaria()
    with structlog.testing.capture_logs() as eventos:
        try:
            raise ValueError("bug")
        except ValueError as e:
            aviso_de_falha(res, "rag", e, "diaria_falhou")
    assert res.avisos == ["falha em rag: bug"]
    assert eventos[0]["log_level"] == "error" and "ValueError" in eventos[0]["trace"]


# ------------------------------------------------------------------ saída


def test_logs_mascaram_a_chave_do_servidor() -> None:
    from fiat_lux import logs

    evento = logs._mascarar(
        None, "info", {"event": "x", "erro": "chave sk-abc123def456ghi e Bearer tok.en_123456"}
    )
    assert "sk-abc" not in evento["erro"] and "tok.en" not in evento["erro"]


def test_console_esconde_o_traceback_e_o_configurar_restaura_os_logs() -> None:
    from fiat_lux import logs

    evento = logs._sem_trace(None, "error", {"event": "x", "trace": "Traceback…"})
    assert "trace" not in evento and evento["traceback"].startswith("fiatlux --verboso")
    antes = structlog.get_config()["wrapper_class"]
    nivel = logging.getLogger().level
    with logs.so_erros_no_console():
        assert structlog.get_config()["wrapper_class"] is not antes
        assert logging.getLogger().level == logging.ERROR
    assert structlog.get_config()["wrapper_class"] is antes
    assert logging.getLogger().level == nivel


def test_barras_do_transformers_desligadas_sem_mexer_nas_do_hub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fiat_lux.rag import embeddings

    ganchos: list[Any] = []
    falso = types.ModuleType("transformers.utils.logging")
    falso.set_tqdm_hook = ganchos.append  # type: ignore[attr-defined]
    utils = types.ModuleType("transformers.utils")
    utils.logging = falso  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", types.ModuleType("transformers"))
    monkeypatch.setitem(sys.modules, "transformers.utils", utils)
    monkeypatch.setitem(sys.modules, "transformers.utils.logging", falso)
    embeddings._sem_barras_do_transformers()
    assert len(ganchos) == 1
    recebido: dict[str, Any] = {}
    ganchos[0](lambda *a, **kw: recebido.update(kw), (), {"desc": "Loading weights"})
    assert recebido == {"desc": "Loading weights", "disable": True}


# ------------------------------------------------------------------ LLM local mais leve


LIVRE = (0, 0, 0.0)  # (aguardando, rodando, espera estimada)
OCUPADO = (0, 1, 0.0)  # um pedido rodando; o servidor não conta o que já roda na estimativa


class ServidorComStatus(Servidor):
    """Como o Servidor, com `GET /v1/status`: cada consulta tira um estado de `filas` (o último
    se repete). Com `filas` vazio, 404."""

    def __init__(self, filas: list[tuple[int, int, float]], *respostas: Any) -> None:
        super().__init__(*respostas)
        self.filas = list(filas)

    def fila(self) -> httpx.Response:
        if not self.filas:
            return super().fila()
        aguardando, rodando, espera = self.filas.pop(0) if len(self.filas) > 1 else self.filas[0]
        return httpx.Response(
            200,
            json={
                "state": "green",
                "queue": {
                    "depth": aguardando,
                    "running": rodando,
                    "max_depth": 16,
                    "max_concurrent": 1,
                    "avg_duration_s": 160.0,
                    "estimated_wait_s": espera,
                    "completed": 7,
                    "rejected": 0,
                },
            },
        )


def test_marca_sem_raciocinio_so_nas_tarefas_simples() -> None:
    srv = Servidor(
        (200, resposta_chat(json.dumps(JULGAMENTO_OK)), {}),
        (200, resposta_chat(json.dumps(JULGAMENTO_OK)), {}),
    )
    cli = srv.cliente(marcador_sem_raciocinio="/no_think", tarefas_sem_raciocinio=("consultas",))
    cli.gerar(pedido(tarefa="consultas"), Julgamento)
    cli.gerar(pedido(tarefa="redacao"), Julgamento)
    assert srv.corpo(0)["messages"][1]["content"].endswith("\n\n/no_think")
    assert "/no_think" not in srv.corpo(1)["messages"][1]["content"]


def test_tarefa_opcional_nao_espera_fila_longa() -> None:
    srv = ServidorComStatus([(3, 1, 600.0)])  # ~10 min de fila
    cli = srv.cliente(tarefas_opcionais=("classificacao",), espera_max_opcional_s=120)
    with pytest.raises(ErroLLM, match="fila do servidor de LLM longa") as e:
        cli.gerar(pedido(tarefa="classificacao"), Julgamento)
    assert not isinstance(e.value, ErroPermanente)  # a redação, depois, ainda pode usar o LLM
    assert srv.pedidos == [] and srv.esperas == []  # nada foi para /v1/chat, nem esperou


def test_espera_a_vez_com_o_servidor_ocupado_em_vez_de_entrar_na_fila() -> None:
    from fiat_lux.llm.servidor import OBSERVADOR

    eventos: list[tuple[str, str]] = []
    srv = ServidorComStatus(
        [OCUPADO, OCUPADO, LIVRE], (200, resposta_chat(json.dumps(JULGAMENTO_OK)), {})
    )
    cli = srv.cliente(espera_fila_max_s=100)
    marca = OBSERVADOR.set(lambda evento, tarefa: eventos.append((evento, tarefa)))
    try:
        assert cli.gerar(pedido(tarefa="juiz"), Julgamento).dados.aprovado
    finally:
        OBSERVADOR.reset(marca)
    assert srv.esperas == [5.0, 5.0] and cli.espera_restante_s == 90.0
    assert srv.status == 3 and len(srv.pedidos) == 1
    assert eventos == [("fila", "juiz"), ("pedido", "juiz"), ("fim", "juiz")]


def test_opcional_com_o_servidor_sempre_ocupado_segue_pela_reserva() -> None:
    srv = ServidorComStatus([OCUPADO])
    cli = srv.cliente(tarefas_opcionais=("consultas",), espera_max_opcional_s=12)
    with pytest.raises(ErroLLM, match=r"ocupado \(10 s esperando a vez\)") as e:
        cli.gerar(pedido(tarefa="consultas"), Julgamento)
    assert not isinstance(e.value, ErroPermanente)
    assert srv.esperas == [5.0, 5.0] and srv.pedidos == []
    assert cli.tempo_opcionais_s >= 10.0  # a espera conta no orçamento das opcionais


def test_essencial_com_o_servidor_ocupado_por_tempo_demais_desiste_da_execucao() -> None:
    srv = ServidorComStatus([OCUPADO])
    cli = srv.cliente(espera_fila_max_s=10)
    with pytest.raises(ErroPermanente) as e:
        cli.gerar(pedido(tarefa="redacao"), Julgamento)
    assert e.value.causa == "ocupado" and srv.esperas == [5.0, 5.0] and srv.pedidos == []
    assert provedor_bloqueado(cli) is not None


def test_orcamento_das_opcionais_esgotado_vai_direto_a_reserva() -> None:
    ok = (200, resposta_chat(json.dumps(JULGAMENTO_OK)), {})
    srv = Servidor(ok, ok)
    cli = srv.cliente(tarefas_opcionais=("consultas",), tempo_max_opcionais_s=100)
    cli.gerar(pedido(tarefa="consultas"), Julgamento)  # sem /v1/status: segue normalmente
    assert srv.status == 1 and cli.tempo_opcionais_s > 0
    cli.tempo_opcionais_s = 100.0
    with pytest.raises(ErroLLM, match="tempo das etapas opcionais do LLM esgotado"):
        cli.gerar(pedido(tarefa="consultas"), Julgamento)
    assert cli.gerar(pedido(tarefa="redacao"), Julgamento).dados.aprovado  # não opcional
    assert srv.status == 1  # o servidor sem /v1/status não é consultado de novo


CORTE = (524, {"detail": "A timeout occurred"}, {})  # Cloudflare: o servidor demorou demais


def test_corte_do_proxy_nao_repete_e_o_segundo_fecha_o_modelo() -> None:
    srv = Servidor(CORTE, CORTE, (200, resposta_chat(json.dumps(JULGAMENTO_OK)), {}))
    cli = srv.cliente()
    with pytest.raises(ErroLLM, match="cortou a resposta") as primeiro:
        cli.gerar(pedido("qwen3:8b"), Julgamento)
    assert not isinstance(primeiro.value, ErroPermanente)
    assert len(srv.pedidos) == 1 and srv.esperas == []  # repetir dobraria o trabalho lá
    with pytest.raises(ErroPermanente) as segundo:
        cli.gerar(pedido("qwen3:8b"), Julgamento)
    assert segundo.value.causa == "lento" and segundo.value.modelo == "qwen3:8b"
    assert "passam do tempo que o proxy" in segundo.value.motivo
    assert motivo_curto(segundo.value) == "sem o LLM"  # o motivo vai uma vez, no topo
    with pytest.raises(ErroPermanente):  # nem vai à rede
        cli.gerar(pedido("qwen3:8b"), Julgamento)
    assert len(srv.pedidos) == 2
    assert cli.gerar(pedido("qwen2.5-coder:7b"), Julgamento).dados.aprovado  # outro modelo, sim
    assert provedor_bloqueado(cli) is None and provedor_bloqueado(cli, "qwen3:8b") is not None


def test_modelo_padrao_lento_aparece_uma_vez_no_topo_dos_avisos() -> None:
    srv = Servidor(CORTE, CORTE)
    cli = srv.cliente()
    for _ in range(2):
        with pytest.raises(ErroLLM):
            cli.gerar(pedido(""), Julgamento)
    assert provedor_bloqueado(cli) is None and provedor_bloqueado(cli, "") is not None
    res = ResultadoDiaria(avisos=["seleção pelo escore (sem o LLM)"])
    registrar_bloqueio(res, cli, ("", "", ""))
    assert res.llm_causa == "lento"
    assert res.avisos[0].startswith(
        "LLM indisponível nesta execução: as respostas do modelo padrão passam do tempo"
    )
    assert len(res.avisos) == 2


def test_erro_passageiro_do_servidor_e_repetido() -> None:
    srv = Servidor(
        (500, {"detail": "erro interno"}, {}), (200, resposta_chat(json.dumps(JULGAMENTO_OK)), {})
    )
    assert srv.cliente().gerar(pedido(), Julgamento).dados.aprovado
    assert srv.esperas == [5.0] and len(srv.pedidos) == 2


def test_andamento_recebe_os_eventos_dos_pedidos() -> None:
    from fiat_lux.llm.servidor import OBSERVADOR

    eventos: list[tuple[str, str]] = []
    srv = Servidor(
        (429, {"detail": "fila cheia"}, {"Retry-After": "1"}),
        (200, resposta_chat("sem JSON"), {}),
        (200, resposta_chat(json.dumps(JULGAMENTO_OK)), {}),
    )
    marca = OBSERVADOR.set(lambda evento, tarefa: eventos.append((evento, tarefa)))
    try:
        srv.cliente().gerar(pedido(tarefa="juiz"), Julgamento)
    finally:
        OBSERVADOR.reset(marca)
    assert eventos == [("pedido", "juiz"), ("fila", ""), ("formato", "juiz"), ("fim", "juiz")]


def test_configuracao_da_marca_e_dos_lotes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIATLUX_LLM_SEM_RACIOCINIO", " /no_think ")
    s = Settings(_env_file=None)
    assert s.llm.marcador_sem_raciocinio == "/no_think"
    # atrás de um proxy que corta em ~2 min, nenhuma tarefa pode raciocinar: a marca vale em todas
    assert set(s.llm.tarefas_sem_raciocinio) == {
        "classificacao",
        "consultas",
        "resumo_evangelho",
        "selecao",
        "redacao",
        "juiz",
        "semanal",
    }
    assert set(s.llm.tarefas_opcionais) == {"classificacao", "consultas", "resumo_evangelho"}
    assert s.noticias.top_clusters_classificar == 8 and s.noticias.titulos_por_cluster == 3
