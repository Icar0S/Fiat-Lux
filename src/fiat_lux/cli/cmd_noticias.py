"""`fiatlux noticias ...` — Fase 3."""

from __future__ import annotations

import datetime as dt

import typer

from fiat_lux.cli.comum import console

app = typer.Typer(no_args_is_help=True)


def _hoje() -> dt.date:
    from zoneinfo import ZoneInfo

    from fiat_lux.config import obter_settings

    return dt.datetime.now(ZoneInfo(obter_settings().geral.fuso)).date()


@app.command()
def coletar(
    data: str = typer.Option(None, "--data", help="AAAA-MM-DD (padrão: hoje)"),
    sem_gdelt: bool = typer.Option(False, "--sem-gdelt", help="Só RSS."),
    llm: str = typer.Option(None, "--llm", help="anthropic | offline"),
    sem_llm: bool = typer.Option(False, "--sem-llm", help="Classifica por palavras-chave."),
) -> None:
    """Coleta, agrupa, classifica e mede as notícias do dia."""
    from fiat_lux.config import obter_settings
    from fiat_lux.estado import Estado
    from fiat_lux.llm.fabrica import criar_cliente
    from fiat_lux.noticias.coleta import coletor_padrao, processar_dia

    s = obter_settings()
    d = dt.date.fromisoformat(data) if data else _hoje()
    cliente = None if sem_llm else criar_cliente(s, llm)
    ref = dt.datetime.now(dt.UTC) if d == _hoje() else None
    res = processar_dia(
        d, s, Estado.abrir(), cliente, coletor_padrao(s, not sem_gdelt), referencia=ref
    )
    _mostrar(res)


@app.command()
def medir(
    data: str = typer.Option(None, "--data"),
    sem_llm: bool = typer.Option(True, "--sem-llm/--com-llm"),
) -> None:
    """Recalcula clusters e medições com as notícias já coletadas (sem rede)."""
    from fiat_lux.config import obter_settings
    from fiat_lux.estado import Estado
    from fiat_lux.llm.fabrica import criar_cliente
    from fiat_lux.noticias.coleta import processar_dia

    s = obter_settings()
    d = dt.date.fromisoformat(data) if data else _hoje()
    res = processar_dia(d, s, Estado.abrir(), None if sem_llm else criar_cliente(s), None)
    _mostrar(res)


def _mostrar(res) -> None:
    from rich.markup import escape

    console.print(f"[bold]{res.data}[/] — artigos únicos: {res.artigos}")
    for e, m in res.medicoes.items():
        cal = " (calibrando)" if m.calibrando else ""
        console.print(
            f"  {e:<9} índice {m.indice:5.1f} · {m.faixa}{cal} · G={m.gravidade_media} zV={m.volume_z}"
        )
    for t in res.temas:
        console.print(escape(f"  tema: [{t.categoria}] {t.rotulo} ({t.escopo}, g{t.gravidade})"))
    if res.evento_dominante:
        console.print(f"  [bold]dia marcado por:[/] {escape(res.evento_dominante.rotulo)}")
    for c in res.clusters[:8]:
        console.print(
            escape(
                f"  · {c.escopo[:3]} r={c.relevancia:5.1f} n={len(c.artigos)} [{c.categoria}/{c.classificado_por}] {c.titulos[0][:90]}"
            )
        )
    for a in res.avisos:
        console.print(f"  [yellow]aviso:[/] {escape(a)}")
