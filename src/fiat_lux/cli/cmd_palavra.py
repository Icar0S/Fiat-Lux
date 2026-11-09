"""`fiatlux palavra diaria|semanal` — Fases 5, 6 e 8."""

from __future__ import annotations

import datetime as dt

import typer

from fiat_lux.cli.comum import console, falhar

app = typer.Typer(no_args_is_help=True)


def _data(valor: str | None) -> dt.date:
    from zoneinfo import ZoneInfo

    from fiat_lux.config import obter_settings

    if valor:
        try:
            return dt.date.fromisoformat(valor)
        except ValueError:
            falhar("data inválida (use AAAA-MM-DD)")
    return dt.datetime.now(ZoneInfo(obter_settings().geral.fuso)).date()


@app.command()
def diaria(
    data: str = typer.Option(None, "--data", help="AAAA-MM-DD (padrão: hoje)."),
    perfil: str = typer.Option(None, "--perfil", help="catolico | evangelico | ecumenico"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Não envia nem arquiva em saidas/."),
    sem_envio: bool = typer.Option(
        False, "--sem-envio", help="Arquiva, mas não envia pelo Telegram."
    ),
    llm: str = typer.Option(None, "--llm", help="anthropic | offline"),
    sem_noticias: bool = typer.Option(
        False, "--sem-noticias", help="Não coleta (usa as já coletadas)."
    ),
    sem_gdelt: bool = typer.Option(False, "--sem-gdelt"),
    rerank: bool = typer.Option(None, "--rerank/--sem-rerank"),
    mostrar: bool = typer.Option(True, "--mostrar/--quieto"),
) -> None:
    """Gera (e entrega) a Palavra do Dia."""
    from fiat_lux.config import obter_settings
    from fiat_lux.orquestracao.diaria import OpcoesDiaria, executar

    s = obter_settings()
    r = executar(
        OpcoesDiaria(
            data=_data(data),
            perfil=perfil or s.geral.perfil_padrao,
            dry_run=dry_run,
            sem_envio=sem_envio,
            provedor_llm=llm,
            coletar_noticias=not sem_noticias,
            usar_gdelt=not sem_gdelt,
            usar_rerank=rerank,
        ),
        s,
    )
    if mostrar and r.markdown:
        console.print(r.markdown, markup=False, highlight=False)
    console.print(
        f"\n[bold]status:[/] {r.status} · llm: {r.llm} · custo: US$ {r.custo:.4f} · arquivo: {r.caminho}"
    )
    for c in r.verificacao:
        console.print(f"  {'✅' if c.ok else '❌'} {c.id} {c.motivo}", markup=False)
    for a in r.avisos:
        console.print(f"  aviso: {a}", markup=False)
    if r.status == "falhou":
        raise typer.Exit(1)


@app.command()
def semanal(
    semana: str = typer.Option(
        None, "--semana", help="AAAA-Wnn (padrão: a que termina no próximo domingo)."
    ),
    perfil: str = typer.Option(None, "--perfil"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    sem_envio: bool = typer.Option(False, "--sem-envio"),
    llm: str = typer.Option(None, "--llm"),
    rerank: bool = typer.Option(None, "--rerank/--sem-rerank"),
) -> None:
    """Gera (e entrega) a Palavra da Semana (sábado à tarde, preparando o domingo)."""
    from fiat_lux.config import obter_settings
    from fiat_lux.orquestracao.semanal import OpcoesSemanal, executar, sabado_da_semana

    s = obter_settings()
    ref = sabado_da_semana(semana) if semana else _data(None)
    r = executar(
        OpcoesSemanal(
            data=ref,
            perfil=perfil or s.geral.perfil_padrao,
            dry_run=dry_run,
            sem_envio=sem_envio,
            provedor_llm=llm,
            usar_rerank=rerank,
        ),
        s,
    )
    if r.markdown:
        console.print(r.markdown, markup=False, highlight=False)
    console.print(
        f"\n[bold]status:[/] {r.status} · custo: US$ {r.custo:.4f} · arquivo: {r.caminho}"
    )
    for a in r.avisos:
        console.print(f"  aviso: {a}", markup=False)
    if r.status == "falhou":
        raise typer.Exit(1)
