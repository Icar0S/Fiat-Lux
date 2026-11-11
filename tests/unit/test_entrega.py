"""Fase 6: Telegram (HTML, divisão, allowlist, reenvio sem formatação), arquivo e feedback."""

from __future__ import annotations

import datetime as dt
from typing import ClassVar

import httpx
import pytest
import respx

from fiat_lux.entrega.markdown import arquivar, caminho
from fiat_lux.entrega.telegram import (
    ClienteTelegram,
    ErroTelegram,
    dividir,
    interpretar_feedback,
    markdown_para_html,
)

MD = """# Palavra do Dia — domingo, 8 de novembro de 2026

**32º Domingo do Tempo Comum** · Tempo Comum · cor verde

## A Palavra para hoje — Mt 25,13 (MS)

> Vigiai, pois, porque não sabeis o dia nem a hora.

Texto com <tag> & [g1](https://g1.globo.com/x) e *itálico*.

---
<sub>Fiat Lux v0.1.0</sub>
"""


def test_markdown_para_html_escapa_e_converte():
    h = markdown_para_html(MD)
    assert "<b>Palavra do Dia" in h and "<blockquote>Vigiai" in h
    assert "&lt;tag&gt; &amp;" in h and '<a href="https://g1.globo.com/x">g1</a>' in h
    assert "<i>itálico</i>" in h and "<i>Fiat Lux v0.1.0</i>" in h


def test_dividir_respeita_limite_e_secoes():
    texto = "\n\n".join(f"<b>Seção {i}</b>\n" + ("linha de texto " * 40) for i in range(20))
    partes = dividir(texto, 1000)
    assert all(len(p) <= 1000 for p in partes) and len(partes) > 5
    assert "".join(partes).count("<b>Seção") == 20


def test_arquivo_em_saidas(tmp_path):
    p = arquivar(tmp_path, dt.date(2026, 11, 8), "conteúdo")
    assert (
        p == tmp_path / "2026" / "11" / "2026-11-08.md"
        and p.read_text(encoding="utf-8") == "conteúdo"
    )
    assert caminho(tmp_path, dt.date(2026, 11, 14), "semanal").name == "2026-W46.md"
    assert (
        caminho(tmp_path, dt.date(2026, 11, 8), perfil="evangelico").name
        == "2026-11-08-evangelico.md"
    )


@respx.mock
def test_envio_allowlist_e_reenvio_sem_formatacao():
    url = "https://api.telegram.org/botTOKEN/sendMessage"
    rota = respx.post(url).mock(
        side_effect=[
            httpx.Response(
                400, json={"ok": False, "description": "Bad Request: can't parse entities"}
            ),
            httpx.Response(200, json={"ok": True, "result": {"message_id": 7}}),
        ]
    )
    tg = ClienteTelegram("TOKEN", ("123",))
    assert tg.enviar_markdown("123", "# Título\n\nTexto") == [7]
    assert rota.call_count == 2
    assert "parse_mode" not in rota.calls.last.request.content.decode()
    with pytest.raises(ErroTelegram):
        tg.enviar_markdown("999", "x")


def test_feedback_por_resposta():
    updates = [
        {"update_id": 10, "message": {"text": "👍 gostei", "reply_to_message": {"message_id": 7}}},
        {"update_id": 11, "message": {"text": "👎", "reply_to_message": {"message_id": 8}}},
        {"update_id": 12, "message": {"text": "oi"}},
    ]
    itens, ultimo = interpretar_feedback(updates, {7: 1, 8: 2})
    assert itens == [(1, 1, "👍 gostei"), (2, -1, "👎")] and ultimo == 12


# ------------------------------------------------------------------ e-mail (canal provisório)


class SMTPFalso:
    """smtplib.SMTP de mentira: guarda o que cada conexão fez."""

    conexoes: ClassVar[list[SMTPFalso]] = []
    com_tls = True
    senha_certa = "certa"

    def __init__(self, host: str, porta: int, timeout: float = 30, **_: object) -> None:
        self.host, self.porta = host, porta
        self.passos: list[str] = []
        self.enviadas: list[object] = []
        SMTPFalso.conexoes.append(self)

    def ehlo(self) -> None:
        self.passos.append("ehlo")

    def has_extn(self, nome: str) -> bool:
        return nome == "starttls" and self.com_tls

    def starttls(self, context: object = None) -> None:
        self.passos.append("starttls")

    def login(self, usuario: str, senha: str) -> None:
        import smtplib

        if senha != self.senha_certa:
            raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
        self.passos.append(f"login {usuario}")

    def noop(self) -> None:
        self.passos.append("noop")

    def send_message(self, msg: object) -> None:
        self.enviadas.append(msg)

    def quit(self) -> None:
        self.passos.append("quit")

    def close(self) -> None:
        self.passos.append("close")


@pytest.fixture
def smtp_falso(monkeypatch: pytest.MonkeyPatch) -> type[SMTPFalso]:
    import smtplib

    SMTPFalso.conexoes = []
    SMTPFalso.com_tls = True
    monkeypatch.setattr(smtplib, "SMTP", SMTPFalso)
    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTPFalso)
    return SMTPFalso


def test_email_html_assunto_e_endereco_mascarado():
    from fiat_lux.entrega.email import assunto_de, markdown_para_html, mascarar

    html = markdown_para_html(MD)
    assert "<h1" in html and "Palavra do Dia — domingo, 8 de novembro de 2026</h1>" in html
    assert "<blockquote" in html and "Vigiai, pois" in html
    assert "&lt;tag&gt; &amp;" in html and '<a href="https://g1.globo.com/x">g1</a>' in html
    assert "<i>itálico</i>" in html and "<sub>" not in html and "Fiat Lux v0.1.0</p>" in html
    assert markdown_para_html("- um\n- dois\n\nfim").count("<li>") == 2
    assert assunto_de(MD) == "Palavra do Dia — domingo, 8 de novembro de 2026"
    assert assunto_de("sem título") == "Fiat Lux"
    assert mascarar("maria.silva@exemplo.com") == "ma…@exemplo.com"


def test_email_entra_com_starttls_e_envia_a_cada_destinatario(smtp_falso, tmp_path):
    from fiat_lux.entrega.email import ClienteEmail

    grafico = tmp_path / "tendencia.png"
    grafico.write_bytes(b"\x89PNG")
    cli = ClienteEmail("smtp.exemplo.com", 587, "eu@exemplo.com", "certa", "eu@exemplo.com")
    cli.enviar("voce@exemplo.com", "Assunto", MD, [grafico])
    c = smtp_falso.conexoes[-1]
    assert c.passos[:4] == ["ehlo", "starttls", "ehlo", "login eu@exemplo.com"]
    msg = c.enviadas[0]
    assert msg["To"] == "voce@exemplo.com" and msg["From"] == "eu@exemplo.com"
    assert msg["Subject"] == "Assunto" and msg["Message-ID"].endswith("@exemplo.com>")
    tipos = [p.get_content_type() for p in msg.walk()]
    assert {"text/plain", "text/html", "image/png"} <= set(tipos)
    cli.testar()
    assert smtp_falso.conexoes[-1].passos[-2:] == ["noop", "quit"]


def test_email_sem_tls_nao_manda_a_senha_e_senha_recusada_diz_a_causa(smtp_falso):
    from fiat_lux.entrega.email import ClienteEmail, ErroEmail

    smtp_falso.com_tls = False
    with pytest.raises(ErroEmail) as e:
        ClienteEmail("smtp.exemplo.com", 25, "eu@exemplo.com", "certa", "eu@exemplo.com").testar()
    assert e.value.causa == "tls" and not any("login" in p for p in smtp_falso.conexoes[-1].passos)
    smtp_falso.com_tls = True
    with pytest.raises(ErroEmail) as e:
        ClienteEmail("smtp.gmail.com", 587, "eu@gmail.com", "errada", "eu@gmail.com").testar()
    assert e.value.causa == "senha" and "senha de app" in e.value.motivo


def _settings_email(tmp_path, **extra: str):
    from fiat_lux.config import Settings

    valores = {
        "SMTP_HOST": "smtp.exemplo.com",
        "SMTP_USUARIO": "eu@exemplo.com",
        "SMTP_SENHA": "certa",
        "EMAIL_DESTINATARIOS": "maria@exemplo.com, joao@exemplo.com",
    }
    s = Settings(_env_file=None, **(valores | extra))
    s.caminhos.saidas = tmp_path / "saidas"
    return s


def test_entrega_padrao_e_por_email_e_o_endereco_nao_vai_para_o_estado(smtp_falso, tmp_path):
    from fiat_lux.estado import Estado
    from fiat_lux.llm.cliente import Contabilidade
    from fiat_lux.orquestracao.diaria import ResultadoDiaria, destinos, entregar

    s = _settings_email(tmp_path, TELEGRAM_BOT_TOKEN="1:x", TELEGRAM_CHAT_IDS="42")
    assert s.entrega.email and not s.entrega.telegram  # Telegram provisoriamente desligado
    assert destinos(s) == ["maria@exemplo.com", "joao@exemplo.com"]
    estado = Estado(tmp_path / "e.sqlite")
    dia = dt.date(2026, 11, 11)

    def entregar_uma_vez() -> ResultadoDiaria:
        res = ResultadoDiaria(status="rascunho", markdown=MD)
        entregar(dia, "diaria", "catolico", res, Contabilidade(), s, estado, False, False, None)
        return res

    res = entregar_uma_vez()
    assert res.status == "enviada" and res.caminho is not None and res.caminho.is_file()
    enviadas = [m for c in smtp_falso.conexoes for m in c.enviadas]
    assert [m["To"] for m in enviadas] == ["maria@exemplo.com", "joao@exemplo.com"]
    with estado.transacao() as c:
        gravados = [r[0] for r in c.execute("SELECT destinatario FROM mensagens")]
    assert len(gravados) == 2 and all(g.startswith("email:") for g in gravados)
    assert not any("@" in g for g in gravados)
    # de novo no mesmo dia: não reenvia (idempotência)
    n = len(smtp_falso.conexoes)
    segunda = entregar_uma_vez()
    assert len(smtp_falso.conexoes) == n and any("idempotência" in a for a in segunda.avisos)


def test_falha_no_email_vira_aviso_e_contingencia_alerta_quem_envia(smtp_falso, tmp_path):
    from fiat_lux.estado import Estado
    from fiat_lux.llm.cliente import Contabilidade
    from fiat_lux.orquestracao.diaria import ResultadoDiaria, entregar

    s = _settings_email(tmp_path, SMTP_SENHA="errada")
    res = ResultadoDiaria(status="rascunho", markdown=MD)
    estado = Estado(tmp_path / "e.sqlite")
    entregar(
        dt.date(2026, 11, 11),
        "diaria",
        "catolico",
        res,
        Contabilidade(),
        s,
        estado,
        False,
        False,
        None,
    )
    assert res.status == "falhou"
    assert any(a.startswith("e-mail para ma…@exemplo.com falhou: o servidor") for a in res.avisos)
    # a contingência avisa o admin (sem EMAIL_ADMIN, quem envia)
    s = _settings_email(tmp_path)
    fb = ResultadoDiaria(status="fallback", markdown=MD, etapa_falha="redacao")
    entregar(
        dt.date(2026, 11, 12),
        "diaria",
        "catolico",
        fb,
        Contabilidade(),
        s,
        estado,
        False,
        False,
        None,
    )
    alerta = [m for c in smtp_falso.conexoes for m in c.enviadas][-1]
    assert alerta["To"] == "eu@exemplo.com" and alerta["Subject"] == "Fiat Lux: alerta"
