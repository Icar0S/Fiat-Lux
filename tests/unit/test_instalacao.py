"""`fiatlux configurar`: o que já existe é reaproveitado, o .env é editado sem estragar nada."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from fiat_lux import instalacao as inst
from fiat_lux.entrega.telegram import chats_recentes

MODELO = "intfloat/multilingual-e5-base"
EXEMPLO = (
    "# Copie para .env e preencha.\r\n"
    "FIATLUX_LLM_URL=\r\n"
    "TELEGRAM_CHAT_IDS=            # separados por vírgula\r\n"
    "FIATLUX_PERFIL=catolico       # catolico | evangelico | ecumenico\r\n"
)


def _banco(
    pasta: Path,
    embedder: str = "",
    pericopes: int = 3,
    vetores: int | None = None,
    declarado: int | None = None,
) -> Path:
    db = pasta / "biblia.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT);"
        "CREATE TABLE pericopes (id INTEGER PRIMARY KEY);"
        "CREATE TABLE pericopes_emb (pericope_id INTEGER PRIMARY KEY, embedding BLOB);"
    )
    con.executemany("INSERT INTO pericopes VALUES (?)", [(i,) for i in range(pericopes)])
    n_vetores = pericopes if vetores is None else vetores
    con.executemany("INSERT INTO pericopes_emb VALUES (?, x'00')", [(i,) for i in range(n_vetores)])
    if embedder:
        con.executemany(
            "INSERT INTO metadados VALUES (?, ?)",
            [
                ("indice_embedder", embedder),
                ("indice_pericopes", str(pericopes if declarado is None else declarado)),
                ("indice_construido_em", "2026-11-09T12:00:00+00:00"),
                ("indice_lexical", "/home/runner/work/lexical.pkl"),  # caminho gravado no CI
            ],
        )
    con.commit()
    con.close()
    return db


def test_sem_banco_o_indice_precisa_ser_construido(tmp_path: Path) -> None:
    sit = inst.ler_situacao_indice(tmp_path / "nao-existe.sqlite")
    assert sit == inst.SituacaoIndice()
    assert inst.motivo_reconstruir_indice(sit, "lexical") == "índice ainda não construído"


def test_banco_ilegivel_conta_como_sem_indice(tmp_path: Path) -> None:
    db = tmp_path / "biblia.sqlite"
    db.write_bytes(b"isto nao e um banco sqlite " * 200)
    assert inst.ler_situacao_indice(db) == inst.SituacaoIndice()


def test_banco_recem_ingerido_ainda_sem_indice(tmp_path: Path) -> None:
    sit = inst.ler_situacao_indice(_banco(tmp_path, pericopes=0))
    assert inst.motivo_reconstruir_indice(sit, "lexical") == "índice ainda não construído"


def test_indice_neural_pronto_nao_e_refeito(tmp_path: Path) -> None:
    sit = inst.ler_situacao_indice(_banco(tmp_path, f"neural:{MODELO}"))
    assert (sit.pericopes, sit.vetores, sit.declarado) == (3, 3, 3)
    assert sit.construido_em.startswith("2026-11-09")
    assert inst.motivo_reconstruir_indice(sit, inst.embedder_esperado(MODELO, ml=True)) is None


def test_indice_lexical_e_refeito_quando_os_modelos_neurais_chegam(tmp_path: Path) -> None:
    (tmp_path / "lexical.pkl").write_bytes(b"x")
    sit = inst.ler_situacao_indice(_banco(tmp_path, "lexical:lsa256"))
    assert inst.motivo_reconstruir_indice(sit, inst.embedder_esperado(MODELO, ml=False)) is None
    motivo = inst.motivo_reconstruir_indice(sit, inst.embedder_esperado(MODELO, ml=True))
    assert motivo is not None
    assert "modo completo" in motivo


def test_indice_neural_e_refeito_sem_os_modelos_instalados(tmp_path: Path) -> None:
    sit = inst.ler_situacao_indice(_banco(tmp_path, f"neural:{MODELO}"))
    motivo = inst.motivo_reconstruir_indice(sit, inst.embedder_esperado(MODELO, ml=False))
    assert motivo is not None
    assert "não estão instalados" in motivo


def test_outro_modelo_neural_e_refeito(tmp_path: Path) -> None:
    sit = inst.ler_situacao_indice(_banco(tmp_path, "neural:outro/modelo"))
    assert inst.motivo_reconstruir_indice(sit, f"neural:{MODELO}") is not None


def test_indice_lexical_usa_o_pkl_ao_lado_do_banco(tmp_path: Path) -> None:
    db = _banco(tmp_path, "lexical:lsa256")
    motivo = inst.motivo_reconstruir_indice(inst.ler_situacao_indice(db), "lexical")
    assert motivo is not None
    assert "lexical.pkl" in motivo
    (tmp_path / "lexical.pkl").write_bytes(b"x")
    sit = inst.ler_situacao_indice(db)
    assert sit.lexical == tmp_path / "lexical.pkl"
    assert inst.motivo_reconstruir_indice(sit, "lexical") is None


@pytest.mark.parametrize(("vetores", "declarado"), [(2, None), (3, 5)])
def test_indice_incompleto_e_refeito(tmp_path: Path, vetores: int, declarado: int | None) -> None:
    db = _banco(tmp_path, f"neural:{MODELO}", pericopes=3, vetores=vetores, declarado=declarado)
    motivo = inst.motivo_reconstruir_indice(inst.ler_situacao_indice(db), f"neural:{MODELO}")
    assert motivo is not None
    assert "incompleto" in motivo


def test_checar_corpus_sem_banco(tmp_path: Path) -> None:
    from fiat_lux.config import Caminhos, Settings

    s = Settings.model_construct(caminhos=Caminhos().resolvidos(tmp_path))
    assert inst.checar_corpus(s) == (False, "a base bíblica ainda não existe")


def test_garantir_env_copia_o_exemplo_uma_vez(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_bytes(EXEMPLO.encode())
    assert inst.garantir_env(tmp_path) is True
    assert (tmp_path / ".env").read_bytes() == EXEMPLO.encode()
    (tmp_path / ".env").write_bytes(b"FIATLUX_LLM_CHAVE=minha\n")
    assert inst.garantir_env(tmp_path) is False
    assert (tmp_path / ".env").read_bytes() == b"FIATLUX_LLM_CHAVE=minha\n"


def test_gravar_variavel_preserva_comentarios_e_quebras_de_linha(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_bytes(EXEMPLO.encode())
    inst.gravar_variavel_env(env, "FIATLUX_LLM_URL", "https://llm.exemplo.com:8443/raiz")
    inst.gravar_variavel_env(env, "TELEGRAM_CHAT_IDS", "123,-100456")
    texto = env.read_bytes().decode("utf-8")
    assert "\r\nFIATLUX_LLM_URL=https://llm.exemplo.com:8443/raiz\r\n" in texto
    assert "\r\nTELEGRAM_CHAT_IDS=123,-100456            # separados por vírgula\r\n" in texto
    assert texto.count("\n") == texto.count("\r\n") == 4
    assert not texto.startswith("﻿")
    valores = inst.ler_env(env)
    assert valores["FIATLUX_LLM_URL"] == "https://llm.exemplo.com:8443/raiz"
    assert valores["TELEGRAM_CHAT_IDS"] == "123,-100456"
    assert valores["FIATLUX_PERFIL"] == "catolico"


def test_gravar_variavel_acrescenta_a_que_falta(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_bytes(b"FIATLUX_PERFIL=catolico")  # sem quebra de linha no fim
    inst.gravar_variavel_env(env, "TELEGRAM_BOT_TOKEN", "123:abc")
    assert env.read_bytes() == b"FIATLUX_PERFIL=catolico\nTELEGRAM_BOT_TOKEN=123:abc\n"


@pytest.mark.parametrize("valor", ["com espaço", 'aspas"', "a#b", "duas\nlinhas"])
def test_gravar_variavel_recusa_valor_que_precisaria_de_aspas(tmp_path: Path, valor: str) -> None:
    with pytest.raises(ValueError, match="FIATLUX_LLM_CHAVE"):
        inst.gravar_variavel_env(tmp_path / ".env", "FIATLUX_LLM_CHAVE", valor)
    assert not (tmp_path / ".env").exists()


def test_chats_recentes_sem_repetir_e_com_nome() -> None:
    updates = [
        {"update_id": 1, "message": {"chat": {"id": 42, "first_name": "Maria", "last_name": "S."}}},
        {"update_id": 2, "message": {"chat": {"id": 42, "first_name": "Maria"}}},
        {"update_id": 3, "message": {"chat": {"id": -1001, "title": "Família"}}},
        {"update_id": 4, "edited_message": {"chat": {"id": 7, "username": "joao"}}},
        {"update_id": 5, "my_chat_member": {}},
    ]
    assert chats_recentes(updates) == [("42", "Maria S."), ("-1001", "Família"), ("7", "joao")]


def test_entrada_nula_nao_conta_como_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    # No Windows, o NUL responde isatty() == True; sem esta checagem, o configurar ficava
    # esperando uma chave que ninguém ia digitar (execução agendada, CI, agente).
    import os
    import sys

    from fiat_lux.cli.cmd_configurar import _terminal_interativo

    with open(os.devnull) as nulo:
        monkeypatch.setattr(sys, "stdin", nulo)
        assert _terminal_interativo() is False


def _respostas(monkeypatch: pytest.MonkeyPatch, *respostas: str) -> None:
    from fiat_lux.cli import cmd_configurar

    fila = iter(respostas)
    monkeypatch.setattr(cmd_configurar, "_perguntar", lambda texto, secreto=False: next(fila))


def test_escolher_chats(monkeypatch: pytest.MonkeyPatch) -> None:
    from fiat_lux.cli.cmd_configurar import _escolher_chats

    tres = [("1", "A"), ("2", "B"), ("3", "C")]
    _respostas(monkeypatch, "1, 3", "", "", "n", "")
    assert _escolher_chats(tres) == ["1", "3"]
    assert _escolher_chats(tres) == ["1", "2", "3"]  # Enter = todos
    assert _escolher_chats([("9", "Z")]) == ["9"]  # Enter = sim
    assert _escolher_chats([("9", "Z")]) == []
    assert _escolher_chats([]) == []  # Enter = pular


def test_perguntar_llm_grava_url_e_chave_validas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fiat_lux.cli.cmd_configurar import _perguntar_llm

    monkeypatch.delenv("FIATLUX_LLM_URL", raising=False)
    env = tmp_path / ".env"
    env.write_bytes(EXEMPLO.encode())
    # 1ª vez: algo que não é URL (nada gravado, e a chave nem é pedida).
    # 2ª vez: URL com /v1 no fim (gravada sem ele) e chave colada com o prefixo Bearer.
    _respostas(monkeypatch, "meu servidor", "https://llm.exemplo.com/v1/", "Bearer sk-abc_DEF-123")
    _perguntar_llm(env)
    assert inst.ler_env(env)["FIATLUX_LLM_URL"] == ""
    _perguntar_llm(env)
    valores = inst.ler_env(env)
    assert valores["FIATLUX_LLM_URL"] == "https://llm.exemplo.com"
    assert valores["FIATLUX_LLM_CHAVE"] == "sk-abc_DEF-123"
    _perguntar_llm(env)  # já configurado: não pergunta mais nada (a fila de respostas acabou)


def test_perguntar_telegram_acha_o_chat_e_manda_mensagem_de_teste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fiat_lux.cli.cmd_configurar import _perguntar_telegram
    from fiat_lux.entrega import telegram

    enviados: list[str] = []

    class TelegramFalso:
        def __init__(self, token: str, permitidos: tuple[str, ...]) -> None:
            self.http = None

        def identidade(self) -> dict[str, str]:
            return {"username": "fiat_lux_bot"}

        def atualizacoes(self) -> list[dict[str, object]]:
            return [{"message": {"chat": {"id": 42, "first_name": "Maria"}}}]

        def enviar_texto(self, chat_id: str, texto: str) -> int:
            enviados.append(chat_id)
            return 1

    monkeypatch.setattr(telegram, "ClienteTelegram", TelegramFalso)
    env = tmp_path / ".env"
    env.write_bytes(EXEMPLO.encode())
    token = "123456789:" + "A" * 35
    # configurar agora? · token · Enter depois de escrever ao bot · confirmar a conversa
    _respostas(monkeypatch, "s", token, "", "")
    _perguntar_telegram(env)
    valores = inst.ler_env(env)
    assert valores["TELEGRAM_BOT_TOKEN"] == token
    assert valores["TELEGRAM_CHAT_IDS"] == "42"
    assert valores["TELEGRAM_ADMIN_CHAT_ID"] == "42"
    assert enviados == ["42"]


def test_gravar_senha_entre_aspas_e_ler_igual(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_bytes(b"SMTP_SENHA=\n")
    senha = "a#b c!$x"
    inst.gravar_variavel_env(env, "SMTP_SENHA", senha, aspas=True)
    assert env.read_bytes() == b"SMTP_SENHA='a#b c!$x'\n"
    assert inst.ler_env(env)["SMTP_SENHA"] == senha
    for impossivel in ("com'aspa", "barra\\", "${HOME}"):
        with pytest.raises(ValueError, match="SMTP_SENHA"):
            inst.gravar_variavel_env(env, "SMTP_SENHA", impossivel, aspas=True)


class EmailFalso:
    enviados: ClassVar[list[tuple[str, str, str]]] = []
    erro: str | None = None

    def __init__(self, host: str, porta: int, usuario: str, senha: str, remetente: str) -> None:
        self.dados = (host, porta, usuario, senha, remetente)

    def enviar(self, para: str, assunto: str, markdown: str, anexos: object = ()) -> None:
        from fiat_lux.entrega.email import ErroEmail

        if EmailFalso.erro:
            raise ErroEmail(EmailFalso.erro, "senha")
        EmailFalso.enviados.append((para, self.dados[0], self.dados[3]))


def test_perguntar_email_testa_a_conta_antes_de_gravar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fiat_lux.cli.cmd_configurar import _perguntar_email
    from fiat_lux.entrega import email

    monkeypatch.setattr(email, "ClienteEmail", EmailFalso)
    EmailFalso.enviados, EmailFalso.erro = [], None
    env = tmp_path / ".env"
    env.write_bytes(EXEMPLO.encode())
    # configurar agora? · quem envia · senha de app (com os espaços do Google) · quem recebe
    _respostas(monkeypatch, "s", "voce@gmail.com", "abcd efgh ijkl mnop", "")
    _perguntar_email(env)
    assert EmailFalso.enviados == [("voce@gmail.com", "smtp.gmail.com", "abcdefghijklmnop")]
    valores = inst.ler_env(env)
    assert valores["SMTP_HOST"] == "smtp.gmail.com" and valores["SMTP_PORT"] == "587"
    assert valores["SMTP_USUARIO"] == valores["EMAIL_REMETENTE"] == "voce@gmail.com"
    assert valores["SMTP_SENHA"] == "abcdefghijklmnop"
    assert valores["EMAIL_DESTINATARIOS"] == "voce@gmail.com"
    _perguntar_email(env)  # já configurado: não pergunta mais nada (a fila de respostas acabou)


def test_perguntar_email_com_senha_recusada_nao_grava_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fiat_lux.cli.cmd_configurar import _perguntar_email
    from fiat_lux.entrega import email

    monkeypatch.setattr(email, "ClienteEmail", EmailFalso)
    EmailFalso.enviados, EmailFalso.erro = [], "o servidor de e-mail recusou o usuário ou a senha"
    env = tmp_path / ".env"
    env.write_bytes(EXEMPLO.encode())
    # outro provedor: servidor e porta perguntados; dois destinatários
    _respostas(
        monkeypatch,
        "s",
        "eu@provedor.com.br",
        "smtp.provedor.com.br",
        "465",
        "x",
        "a@b.com, c@d.org",
    )
    _perguntar_email(env)
    assert env.read_bytes() == EXEMPLO.encode()


@pytest.fixture
def app_configurar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Só o comando, sem o callback da CLI: ele reconfiguraria os logs para o stream
    temporário do CliRunner, que fecha no fim e quebraria os testes seguintes. Base bíblica e
    índice prontos; o índice não pode ser refeito."""
    import typer

    from fiat_lux.cli.cmd_configurar import configurar
    from fiat_lux.cli.comum import console
    from fiat_lux.config import obter_settings
    from fiat_lux.rag import indice

    app = typer.Typer()
    app.command()(configurar)
    largura = console._width  # sem terminal, o Rich usaria a do console de quem roda os testes
    console.width = 120
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.toml").write_text("", encoding="utf-8")
    (tmp_path / ".env.example").write_bytes(EXEMPLO.encode())
    (tmp_path / "lexical.pkl").write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FIATLUX_RAIZ", str(tmp_path))
    for variavel in (
        "FIATLUX_LLM_URL",
        "FIATLUX_LLM_CHAVE",
        "FIATLUX_LLM_MODELO",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_IDS",
        "SMTP_HOST",
        "SMTP_USUARIO",
        "SMTP_SENHA",
        "EMAIL_REMETENTE",
        "EMAIL_DESTINATARIOS",
    ):
        monkeypatch.delenv(variavel, raising=False)
    monkeypatch.setattr(inst, "ml_instalado", lambda: False)
    monkeypatch.setattr(inst, "checar_corpus", lambda s: (True, "28 checagens ok"))
    monkeypatch.setattr(
        inst,
        "ler_situacao_indice",
        lambda db: inst.SituacaoIndice(
            "lexical:lsa256", 5, 5, 5, "ontem", tmp_path / "lexical.pkl"
        ),
    )

    def nao_reconstruir(*args: object, **kwargs: object) -> None:
        raise AssertionError("o índice já servia")

    monkeypatch.setattr(indice, "construir", nao_reconstruir)
    yield app
    obter_settings.cache_clear()
    console._width = largura


def _demonstracao_falsa(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: str) -> list[bool]:
    """Troca a Palavra do Dia de teste por um resultado pronto; devolve com que LLM foi pedida."""
    from fiat_lux.agente.verificacao import Checagem
    from fiat_lux.cli import cmd_configurar
    from fiat_lux.orquestracao.diaria import ResultadoDiaria

    pedidos: list[bool] = []

    def demonstrar(s: object, ml: bool, usar_llm: bool) -> ResultadoDiaria:
        pedidos.append(usar_llm)
        return ResultadoDiaria(
            status=status,
            caminho=tmp_path / "data" / "cache" / "dry-run" / "hoje.md",
            verificacao=[Checagem(f"V{i}", True) for i in range(1, 9)],
        )

    monkeypatch.setattr(cmd_configurar, "_demonstrar", demonstrar)
    return pedidos


def test_configurar_reaproveita_o_que_ja_existe(app_configurar, tmp_path: Path) -> None:
    r = CliRunner().invoke(app_configurar, ["--sem-demonstracao"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".env").read_bytes() == EXEMPLO.encode()
    # linhas das etapas (a tabela do resumo quebra o texto conforme a largura do terminal)
    assert "criado a partir do .env.example" in r.output
    assert "sem perguntas agora" in r.output
    assert "LLM: sem servidor configurado por enquanto" in r.output
    assert "pronta: 28 checagens ok" in r.output
    assert "pronto: lexical:lsa256, 5 perícopes (construído em ontem)" in r.output
    assert "Demonstração" not in r.output.split("● Resumo")[0]
    # sem servidor, a Palavra do Dia real sai incompleta: isso é dito, e o veredito (no título
    # do painel final) não é "Tudo pronto"
    final = r.output.split("● Resumo")[1]
    assert "! Quase pronto: falta 1 item" in final and "Tudo pronto" not in final
    assert "Para a Palavra do Dia sair completa" in final
    assert "Servidor de LLM: rode o configurar de novo" in final


def test_configurar_com_chave_recusada_explica_e_demonstra_offline(
    app_configurar, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        inst,
        "testar_llm",
        lambda s: inst.SituacaoLLM(
            "indisponivel", "chave", "o servidor de LLM recusou a chave (401: informe a chave)"
        ),
    )
    pedidos = _demonstracao_falsa(monkeypatch, tmp_path, "rascunho")
    r = CliRunner().invoke(app_configurar, [])
    assert r.exit_code == 0, r.output
    assert pedidos == [False]  # demonstração sem o LLM: não adianta chamar com a chave recusada
    texto = " ".join(r.output.split())  # o Rich quebra linhas longas conforme a largura
    assert "LLM: o servidor de LLM recusou a chave" in texto
    assert "pô-la na FIATLUX_LLM_CHAVE" in texto
    assert "sem chave válida" in r.output.split("● Resumo")[1]
    assert "Tudo pronto" not in r.output


def test_configurar_com_llm_ok_termina_com_tudo_pronto(
    app_configurar, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        inst,
        "testar_llm",
        lambda s: inst.SituacaoLLM(
            "ok", modelos=(("classificação", "qwen3:4b"), ("seleção e redação", "qwen3:8b"))
        ),
    )
    pedidos = _demonstracao_falsa(monkeypatch, tmp_path, "rascunho")
    r = CliRunner().invoke(app_configurar, [])
    assert r.exit_code == 0, r.output
    assert pedidos == [True]
    texto = " ".join(r.output.split())
    assert (
        "LLM: o servidor respondeu (classificação: qwen3:4b · seleção e redação: qwen3:8b)" in texto
    )
    assert "verificação 8/8" in r.output and "textos do LLM" in r.output
    final = r.output.split("● Resumo")[1]
    assert "✦ Tudo pronto" in final and "Quase pronto" not in final
    assert "E-mail" in final and "não configurado" in final and "Telegram" not in final
    assert "uv run fiatlux palavra diaria --dry-run" in final  # próximos passos no painel


def test_configurar_falha_quando_a_demonstracao_falha(
    app_configurar, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(inst, "testar_llm", lambda s: inst.SituacaoLLM("ok"))
    _demonstracao_falsa(monkeypatch, tmp_path, "falhou")
    r = CliRunner().invoke(app_configurar, [])
    assert r.exit_code == 1
    assert "✗ A demonstração falhou" in r.output.split("● Resumo")[1]


def test_configurar_mostra_o_logo_e_o_script_pode_esconder(app_configurar) -> None:
    com = CliRunner().invoke(app_configurar, ["--sem-demonstracao"])
    sem = CliRunner().invoke(app_configurar, ["--sem-demonstracao", "--sem-cabecalho"])
    assert com.exit_code == sem.exit_code == 0
    assert "███████╗██╗ █████╗" in com.output and "✦ configuração" in com.output
    assert "███████╗" not in sem.output and "● Arquivo .env" in sem.output
