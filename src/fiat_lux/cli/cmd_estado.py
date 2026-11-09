"""`fiatlux estado ...` — execuções, mensagens, feedback, LGPD e persistência no CI."""

from __future__ import annotations

import typer

from fiat_lux.cli.comum import console, falhar

app = typer.Typer(no_args_is_help=True)


@app.command()
def execucoes(ultimos: int = typer.Option(10, "--ultimos")) -> None:
    """Últimas execuções (status, etapa da falha, duração, custo)."""
    from fiat_lux.estado import Estado

    for r in Estado.abrir().execucoes(ultimos):
        console.print(
            f"{r['id']:4d} {r['iniciada_em']} {r['tipo']:<8} {r['status']:<9} {r['data_ref']} "
            f"{(r['duracao_s'] or 0):6.1f}s US$ {(r['custo'] or 0):.4f} {r['etapa_falha'] or ''}",
            markup=False,
        )


@app.command()
def mensagens(ultimos: int = typer.Option(7, "--ultimos")) -> None:
    """Últimas mensagens geradas."""
    import json

    from fiat_lux.estado import Estado

    for r in Estado.abrir().mensagens(ultimos):
        passagens = json.loads(r["passagens_json"] or "{}").get("passagens", [])
        refs = ", ".join(p["ref"] for p in passagens)
        console.print(
            f"{r['data']} {r['tipo']:<8} {r['perfil']:<10} {r['status']:<9} {refs}", markup=False
        )


@app.command()
def feedback() -> None:
    """Lê respostas 👍/👎 às mensagens do bot (getUpdates) e grava em `feedback`."""
    import json

    from fiat_lux.config import obter_settings
    from fiat_lux.entrega.telegram import ClienteTelegram, interpretar_feedback
    from fiat_lux.estado import Estado, agora_iso

    s = obter_settings()
    if not s.telegram_bot_token:
        falhar("TELEGRAM_BOT_TOKEN ausente")
    estado = Estado.abrir()
    offset = estado.ler_kv("telegram_update_id")
    tg = ClienteTelegram(s.telegram_bot_token.get_secret_value(), tuple(s.telegram_chat_ids))
    updates = tg.atualizacoes(int(offset) + 1 if offset else None)
    ids: dict[int, int] = {}
    for r in estado.con.execute(
        "SELECT id, telegram_message_ids FROM mensagens WHERE telegram_message_ids IS NOT NULL"
    ):
        for t in json.loads(r[1] or "[]"):
            ids[int(t)] = int(r[0])
    itens, ultimo = interpretar_feedback(updates, ids)
    with estado.transacao() as c:
        for mid, nota, comentario in itens:
            c.execute(
                "INSERT INTO feedback VALUES (?,?,?,?)",
                (mid, nota if nota else None, comentario, agora_iso()),
            )
    if ultimo is not None:
        estado.gravar_kv("telegram_update_id", str(ultimo))
    console.print(f"[green]ok[/]: {len(itens)} feedbacks")


@app.command("apagar-destinatario")
def apagar_destinatario(
    destinatario: str = typer.Argument(...), sim: bool = typer.Option(False, "--sim")
) -> None:
    """Remove mensagens e feedback de um destinatário (LGPD, plano §13.6)."""
    from fiat_lux.estado import Estado

    if not sim:
        falhar("confirme com --sim (a remoção é definitiva)")
    n = Estado.abrir().apagar_destinatario(destinatario)
    console.print(f"[green]ok[/]: {n} mensagens removidas")


@app.command()
def percepcao(
    data: str = typer.Argument(...),
    nota: int = typer.Argument(..., min=0, max=100),
    comentario: str = typer.Option("", "--comentario"),
) -> None:
    """Registra a percepção humana do dia (0 = leve, 100 = pesadíssimo) para calibrar o medidor."""
    from fiat_lux.estado import Estado

    estado = Estado.abrir()
    with estado.transacao() as c:
        c.execute("INSERT OR REPLACE INTO percepcao VALUES (?,?,?)", (data, nota, comentario))
    console.print("[green]ok[/]")


@app.command()
def commitar(mensagem: str = typer.Option("estado: execução automática", "--mensagem")) -> None:
    """No CI: commita estado.sqlite (branch `estado`) e saidas/ (branch principal)."""
    import subprocess
    from pathlib import Path

    from fiat_lux.config import obter_settings

    s = obter_settings()
    alvo = s.caminhos.estado_db
    repo_estado = next((p for p in [alvo.parent, *alvo.parents] if (p / ".git").exists()), None)
    for raiz, caminhos in ((repo_estado, [alvo.name]), (Path.cwd(), ["saidas"])):
        if raiz is None:
            continue
        subprocess.run(["git", "-C", str(raiz), "add", *caminhos], check=False)
        diff = subprocess.run(["git", "-C", str(raiz), "diff", "--cached", "--quiet"], check=False)
        if diff.returncode == 0:
            continue
        subprocess.run(
            [
                "git",
                "-C",
                str(raiz),
                "-c",
                "user.name=fiat-lux-bot",
                "-c",
                "user.email=fiat-lux-bot@users.noreply.github.com",
                "commit",
                "-m",
                mensagem,
            ],
            check=True,
        )
        subprocess.run(["git", "-C", str(raiz), "push"], check=True)
    console.print("[green]ok[/]")
