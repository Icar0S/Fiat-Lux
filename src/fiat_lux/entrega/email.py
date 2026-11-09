"""Entrega por e-mail (plano §8.7, Could): SMTP com o HTML do mesmo template."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from fiat_lux.entrega.telegram import markdown_para_html


def enviar(
    host: str,
    porta: int,
    usuario: str | None,
    senha: str | None,
    remetente: str,
    destinatarios: list[str],
    assunto: str,
    markdown: str,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = remetente
    msg["To"] = ", ".join(destinatarios)
    msg.set_content(markdown)
    corpo = markdown_para_html(markdown).replace("\n", "<br>\n")
    msg.add_alternative(
        f"<html><body style='font-family:Georgia,serif;max-width:640px'>{corpo}</body></html>",
        subtype="html",
    )
    with smtplib.SMTP(host, porta, timeout=30) as smtp:
        smtp.starttls()
        if usuario and senha:
            smtp.login(usuario, senha)
        smtp.send_message(msg)
