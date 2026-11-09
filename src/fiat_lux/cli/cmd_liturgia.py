"""`fiatlux liturgia ...` — Fase 2."""

from __future__ import annotations

import datetime as dt

import typer

from fiat_lux.cli.comum import console, falhar

app = typer.Typer(no_args_is_help=True)


def _servico(sem_rede: bool = False):
    from fiat_lux.config import obter_settings
    from fiat_lux.estado import Estado
    from fiat_lux.liturgia.cliente_api import ClienteLiturgia
    from fiat_lux.liturgia.servico import ServicoLiturgia

    s = obter_settings()
    cliente = (
        None
        if sem_rede
        else ClienteLiturgia(s.liturgia.url_base, s.liturgia.timeout_s, s.liturgia.tentativas)
    )
    return ServicoLiturgia(Estado.abrir(), cliente)


def _mostrar(dia) -> None:
    semana = f" · {dia.semana}ª semana" if dia.semana else ""
    console.print(
        f"[bold]{dia.data:%d/%m/%Y}[/] — {dia.celebracao} ([italic]{dia.grau}[/])\n"
        f"tempo: {dia.tempo}{semana} · cor: {dia.cor} · Ano {dia.ciclo_dominical}/{dia.ciclo_ferial} · fonte: {dia.fonte}"
    )
    for lt in dia.leituras:
        console.print(f"  {lt.tipo:<9} {lt.referencia}{'  [' + lt.nota + ']' if lt.nota else ''}")
    for a in dia.avisos:
        console.print(f"  [yellow]aviso:[/] {a}")


@app.command()
def hoje(
    sem_rede: bool = typer.Option(False, "--sem-rede", help="Só cache/calendário local."),
) -> None:
    """Liturgia de hoje (fuso configurado)."""
    from zoneinfo import ZoneInfo

    from fiat_lux.config import obter_settings

    data = dt.datetime.now(ZoneInfo(obter_settings().geral.fuso)).date()
    _mostrar(_servico(sem_rede).obter(data, usar_rede=not sem_rede))


@app.command()
def dia(
    data: str = typer.Argument(..., help="AAAA-MM-DD"),
    sem_rede: bool = typer.Option(False, "--sem-rede"),
) -> None:
    """Liturgia de uma data."""
    try:
        d = dt.date.fromisoformat(data)
    except ValueError:
        falhar("data inválida (use AAAA-MM-DD)")
        return
    _mostrar(_servico(sem_rede).obter(d, usar_rede=not sem_rede))


@app.command()
def prefetch(dias: int = typer.Option(7, min=1, max=7)) -> None:
    """Pré-carrega o cache com os próximos dias (`?periodo=7`)."""
    n = _servico().prefetch(dias)
    console.print(f"[green]ok[/]: {n} dias no cache")


@app.command()
def canario() -> None:
    """Teste de contrato contra a API real (alerta se o esquema mudar)."""
    from fiat_lux.config import obter_settings
    from fiat_lux.liturgia.cliente_api import ClienteLiturgia
    from fiat_lux.liturgia.servico import canario as checar

    s = obter_settings()
    cli = ClienteLiturgia(s.liturgia.url_base, s.liturgia.timeout_s, s.liturgia.tentativas)
    bruto = cli._get({})
    problemas = checar(bruto) if isinstance(bruto, dict) else ["resposta vazia"]
    if problemas:
        falhar("contrato da API mudou: " + "; ".join(problemas))
    console.print("[green]ok[/]: contrato da API de liturgia válido")
