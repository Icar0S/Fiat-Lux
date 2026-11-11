"""Entrega por e-mail (plano §8.7): SMTP, com o Markdown do template como texto e um HTML
simples ao lado (os clientes de e-mail mostram o HTML; o texto fica para quem não mostra).

Porta 465: SSL direto; as outras (587, a de costume): STARTTLS. Sem TLS, a senha não é enviada.
Um e-mail por destinatário, para ninguém ver o endereço dos outros.
"""

from __future__ import annotations

import re
import smtplib
import ssl
from collections.abc import Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from fiat_lux.entrega.telegram import markdown_inline

_ESTILO = {
    "corpo": "font-family:Georgia,'Times New Roman',serif;font-size:16px;line-height:1.55;"
    "color:#222;max-width:640px;margin:0 auto;padding:8px 16px",
    "h1": "font-size:22px;margin:16px 0 4px",
    "h2": "font-size:18px;color:#7a5a00;margin:24px 0 8px",
    "citacao": "margin:12px 0;padding:4px 0 4px 14px;border-left:3px solid #c9a227;color:#333",
    "rodape": "font-size:12px;color:#777",
}
_GMAIL = "smtp.gmail.com"


class ErroEmail(RuntimeError):
    """Falha no envio. `causa`: senha, conexao, tls, destinatario, remetente ou smtp."""

    def __init__(self, motivo: str, causa: str = "smtp") -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.causa = causa


def markdown_para_html(md: str) -> str:
    """O subconjunto de Markdown dos templates em HTML de e-mail (estilos inline, que é o que os
    clientes de e-mail respeitam)."""
    blocos: list[str] = []
    paragrafo: list[str] = []
    lista: list[str] = []

    def fechar() -> None:
        if paragrafo:
            blocos.append(f"<p>{'<br>'.join(paragrafo)}</p>")
            paragrafo.clear()
        if lista:
            blocos.append(f"<ul>{''.join(lista)}</ul>")
            lista.clear()

    for linha in md.splitlines():
        s = linha.rstrip()
        rodape = re.fullmatch(r"<sub>(.*)</sub>", s.strip())
        if s.startswith("- "):
            if paragrafo:
                fechar()
            lista.append(f"<li>{markdown_inline(s[2:])}</li>")
            continue
        fechar()
        if not s.strip():
            continue
        if s.startswith("# "):
            blocos.append(f'<h1 style="{_ESTILO["h1"]}">{markdown_inline(s[2:])}</h1>')
        elif s.startswith("## "):
            blocos.append(f'<h2 style="{_ESTILO["h2"]}">{markdown_inline(s[3:])}</h2>')
        elif s.startswith("> "):
            blocos.append(
                f'<blockquote style="{_ESTILO["citacao"]}">{markdown_inline(s[2:])}</blockquote>'
            )
        elif s.strip() == "---":
            blocos.append('<hr style="border:0;border-top:1px solid #ddd;margin:24px 0">')
        elif rodape is not None:
            blocos.append(f'<p style="{_ESTILO["rodape"]}">{markdown_inline(rodape.group(1))}</p>')
        else:
            paragrafo.append(markdown_inline(s))
    fechar()
    return f'<div style="{_ESTILO["corpo"]}">{"".join(blocos)}</div>'


def assunto_de(markdown: str, padrao: str = "Fiat Lux") -> str:
    """O título da mensagem (a primeira linha "# …") como assunto do e-mail."""
    for linha in markdown.splitlines():
        if linha.startswith("# "):
            return linha[2:].strip()
    return padrao


def mascarar(endereco: str) -> str:
    """ "maria.silva@exemplo.com" → "ma…@exemplo.com": para avisos e logs, sem expor o endereço."""
    nome, _, dominio = endereco.partition("@")
    return f"{nome[:2]}…@{dominio}" if dominio else "…"


def _causa(e: Exception, host: str) -> ErroEmail:
    if isinstance(e, smtplib.SMTPAuthenticationError):
        dica = (
            "; no Gmail, a senha é uma senha de app (myaccount.google.com/apppasswords, com a "
            "verificação em duas etapas ligada), não a senha da conta"
            if host == _GMAIL
            else ""
        )
        return ErroEmail(
            f"o servidor de e-mail recusou o usuário ou a senha ({e.smtp_code}){dica}", "senha"
        )
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return ErroEmail("o servidor de e-mail recusou o destinatário", "destinatario")
    if isinstance(e, smtplib.SMTPSenderRefused):
        return ErroEmail(f"o servidor de e-mail recusou o remetente ({e.smtp_code})", "remetente")
    # SMTPException herda de OSError: o que não é do protocolo é rede (DNS, recusa, timeout)
    if isinstance(e, smtplib.SMTPServerDisconnected | smtplib.SMTPConnectError) or not isinstance(
        e, smtplib.SMTPException
    ):
        return ErroEmail(f"não consegui falar com {host}: {e}", "conexao")
    return ErroEmail(f"o servidor de e-mail respondeu com erro: {e}", "smtp")


@dataclass(slots=True)
class ClienteEmail:
    host: str
    porta: int
    usuario: str | None
    senha: str | None
    remetente: str
    timeout: float = 30

    def _abrir(self) -> smtplib.SMTP:
        contexto = ssl.create_default_context()
        if self.porta == 465:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                self.host, self.porta, timeout=self.timeout, context=contexto
            )
        else:
            smtp = smtplib.SMTP(self.host, self.porta, timeout=self.timeout)
            smtp.ehlo()
            if smtp.has_extn("starttls"):
                smtp.starttls(context=contexto)
                smtp.ehlo()
            elif self.senha:
                smtp.close()
                raise ErroEmail(
                    f"{self.host} não oferece conexão segura (STARTTLS); a senha não vai sem "
                    "criptografia",
                    "tls",
                )
        if self.usuario and self.senha:
            smtp.login(self.usuario, self.senha)
        return smtp

    def _sessao(self) -> smtplib.SMTP:
        try:
            return self._abrir()
        except ErroEmail:
            raise
        except (smtplib.SMTPException, OSError) as e:
            raise _causa(e, self.host) from e

    def testar(self) -> None:
        """Conecta e entra na conta, sem enviar nada (confere servidor, porta e senha)."""
        smtp = self._sessao()
        try:
            smtp.noop()
        finally:
            _encerrar(smtp)

    def mensagem(
        self, para: str, assunto: str, markdown: str, anexos: Sequence[Path] = ()
    ) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = assunto
        msg["From"] = self.remetente
        msg["To"] = para
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=self.remetente.partition("@")[2] or None)
        msg.set_content(markdown)
        msg.add_alternative(
            f"<!doctype html><html><body>{markdown_para_html(markdown)}</body></html>",
            subtype="html",
        )
        for anexo in anexos:
            msg.add_attachment(
                anexo.read_bytes(), maintype="image", subtype="png", filename=anexo.name
            )
        return msg

    def enviar(self, para: str, assunto: str, markdown: str, anexos: Sequence[Path] = ()) -> None:
        msg = self.mensagem(para, assunto, markdown, anexos)
        smtp = self._sessao()
        try:
            smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as e:
            raise _causa(e, self.host) from e
        finally:
            _encerrar(smtp)


def _encerrar(smtp: smtplib.SMTP) -> None:
    try:
        smtp.quit()
    except (smtplib.SMTPException, OSError):
        smtp.close()
