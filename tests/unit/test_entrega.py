"""Fase 6: Telegram (HTML, divisão, allowlist, reenvio sem formatação), arquivo e feedback."""

from __future__ import annotations

import datetime as dt

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
