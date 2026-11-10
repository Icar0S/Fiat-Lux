"""Entrega pelo Telegram (plano §8.7).

Bot API `sendMessage` com `parse_mode=HTML` (escapando `<`, `>` e `&`) e
`disable_web_page_preview`; mensagens divididas em até 4.096 caracteres respeitando as seções;
`sendPhoto` para o gráfico semanal; allowlist de `chat_id`; 400 ⇒ reenvio sem formatação.
Feedback sem servidor: `getUpdates` a partir do último `update_id` salvo.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

API = "https://api.telegram.org/bot{token}/{metodo}"


class ErroTelegram(RuntimeError):
    pass


def _inline(texto: str) -> str:
    t = html.escape(texto, quote=False)
    t = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>',
        t,
    )
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<i>\1</i>", t)
    t = re.sub(r"&lt;sub&gt;(.*?)&lt;/sub&gt;", r"<i>\1</i>", t)
    return t


def markdown_para_html(md: str) -> str:
    """Conversão do subconjunto de Markdown usado nos templates para o HTML do Telegram."""
    saida: list[str] = []
    for linha in md.splitlines():
        s = linha.rstrip()
        if s.startswith("# "):
            saida.append(f"<b>{_inline(s[2:])}</b>")
        elif s.startswith("## "):
            saida.append(f"\n<b>{_inline(s[3:])}</b>")
        elif s.startswith("> "):
            saida.append(f"<blockquote>{_inline(s[2:])}</blockquote>")
        elif s.startswith("- "):
            saida.append(f"• {_inline(s[2:])}")
        elif s.strip() == "---":
            saida.append("—")
        else:
            saida.append(_inline(s))
    texto = "\n".join(saida)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def dividir(texto_html: str, limite: int = 4096) -> list[str]:
    """Divide por seções (linhas em negrito) e, se preciso, por parágrafos/linhas."""
    blocos = re.split(r"\n(?=\n<b>)", texto_html)
    partes: list[str] = []
    atual = ""
    for b in blocos:
        if len(b) > limite:
            for par in b.split("\n"):
                while len(par) > limite:
                    partes.append(par[:limite])
                    par = par[limite:]
                if len(atual) + len(par) + 1 > limite:
                    partes.append(atual.strip())
                    atual = ""
                atual += par + "\n"
            continue
        if len(atual) + len(b) + 1 > limite:
            partes.append(atual.strip())
            atual = ""
        atual += b + "\n"
    if atual.strip():
        partes.append(atual.strip())
    return [p for p in partes if p]


@dataclass(slots=True)
class ClienteTelegram:
    token: str
    permitidos: tuple[str, ...]
    http: httpx.Client | None = None

    def _cli(self) -> httpx.Client:
        if self.http is None:
            self.http = httpx.Client(timeout=30)
        return self.http

    def _chamar(
        self, metodo: str, dados: dict[str, Any], arquivos: dict[str, Any] | None = None
    ) -> Any:
        resp = self._cli().post(
            API.format(token=self.token, metodo=metodo), data=dados, files=arquivos
        )
        corpo = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        if resp.status_code >= 400 or not corpo.get("ok", False):
            raise ErroTelegram(
                f"{metodo}: HTTP {resp.status_code} — {corpo.get('description', '')}"
            )
        return corpo["result"]

    def _checar(self, chat_id: str) -> None:
        if chat_id not in self.permitidos:
            raise ErroTelegram("chat_id fora da allowlist")

    def enviar_markdown(self, chat_id: str, markdown: str, limite: int = 4096) -> list[int]:
        self._checar(chat_id)
        ids: list[int] = []
        for parte in dividir(markdown_para_html(markdown), limite):
            try:
                r = self._chamar(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": parte,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": "true",
                    },
                )
            except ErroTelegram as e:
                if "HTTP 400" not in str(e):
                    raise
                texto_puro = re.sub(r"<[^>]+>", "", parte)
                r = self._chamar(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": html.unescape(texto_puro),
                        "disable_web_page_preview": "true",
                    },
                )
            ids.append(int(r["message_id"]))
        return ids

    def enviar_texto(self, chat_id: str, texto: str) -> int:
        r = self._chamar(
            "sendMessage",
            {"chat_id": chat_id, "text": texto[:4000], "disable_web_page_preview": "true"},
        )
        return int(r["message_id"])

    def enviar_foto(self, chat_id: str, caminho: Path, legenda: str = "") -> int:
        self._checar(chat_id)
        with caminho.open("rb") as fh:
            r = self._chamar(
                "sendPhoto", {"chat_id": chat_id, "caption": legenda[:1000]}, {"photo": fh}
            )
        return int(r["message_id"])

    def atualizacoes(self, offset: int | None = None) -> list[dict[str, Any]]:
        dados: dict[str, Any] = {"timeout": 0, "allowed_updates": '["message"]'}
        if offset is not None:
            dados["offset"] = offset
        resultado: list[dict[str, Any]] = self._chamar("getUpdates", dados)
        return resultado

    def identidade(self) -> dict[str, Any]:
        """`getMe`: confere o token e devolve os dados do bot (id, username…)."""
        resultado: dict[str, Any] = self._chamar("getMe", {})
        return resultado


def chats_recentes(updates: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(chat_id, nome) de quem escreveu ao bot, sem repetir, na ordem das mensagens."""
    chats: dict[str, str] = {}
    for u in updates:
        mensagem = u.get("message") or u.get("edited_message") or {}
        chat = mensagem.get("chat") or {}
        if "id" not in chat:
            continue
        nome = (
            chat.get("title")
            or " ".join(p for p in (chat.get("first_name"), chat.get("last_name")) if p)
            or chat.get("username")
            or str(chat["id"])
        )
        chats.setdefault(str(chat["id"]), str(nome))
    return list(chats.items())


def interpretar_feedback(
    updates: list[dict[str, Any]], ids_por_mensagem: dict[int, int]
) -> tuple[list[tuple[int, int, str]], int | None]:
    """Respostas 👍/👎 (ou comentários) às mensagens do bot → (mensagem_id, nota, comentário)."""
    saida: list[tuple[int, int, str]] = []
    ultimo: int | None = None
    for u in updates:
        ultimo = max(ultimo or 0, int(u.get("update_id", 0)))
        msg = u.get("message") or {}
        resp = (msg.get("reply_to_message") or {}).get("message_id")
        if resp is None or int(resp) not in ids_por_mensagem:
            continue
        texto = (msg.get("text") or "").strip()
        nota = (
            1 if texto.startswith(("👍", "+1")) else (-1 if texto.startswith(("👎", "-1")) else 0)
        )
        saida.append((ids_por_mensagem[int(resp)], nota, texto[:500]))
    return saida, ultimo
