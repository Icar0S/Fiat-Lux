"""`fiatlux palavra diaria|semanal` — Fases 5, 6 e 8."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from fiat_lux.cli import visual as v
from fiat_lux.cli.comum import falhar

if TYPE_CHECKING:
    from fiat_lux.orquestracao.diaria import ResultadoDiaria

app = typer.Typer(no_args_is_help=True)

# status da execução → como aparece no rodapé do painel
_STATUS = {
    "rascunho": "rascunho · nada foi enviado",
    "enviada": "enviada",
    "fallback": "contingência · Evangelho do dia + oração",
    "falhou": "falhou",
}


def _relativo(caminho: Path | None) -> str:
    from fiat_lux.config import raiz_projeto

    if caminho is None:
        return "—"
    raiz = raiz_projeto()
    return str(caminho.relative_to(raiz) if caminho.is_relative_to(raiz) else caminho)


def anunciar(status: str, tempo: str, o_que: str = "Palavra do Dia") -> None:
    """A linha que fecha o andamento: pronta, contingência ou falha, com o tempo."""
    if status in {"rascunho", "enviada"}:
        v.ok(f"{o_que} pronta em {tempo}")
    elif status == "fallback":
        v.aviso(f"saiu a mensagem de contingência, em {tempo}")
    else:
        v.erro(f"{o_que}: falhou, em {tempo}")


def imprimir_resultado_diaria(r: ResultadoDiaria, mostrar: bool = True) -> None:
    """A mensagem formatada (opcional), a verificação V1–V8 numa linha, o status e os avisos."""
    if mostrar and r.markdown:
        v.mensagem(r.markdown, rodape=_STATUS.get(r.status, r.status))
    v.verificacao(r.verificacao)
    partes = [f"status {r.status}", f"LLM {r.llm}"]
    if r.custo:
        partes.append(f"custo US$ {r.custo:.4f}")
    partes.append(f"arquivo {_relativo(r.caminho)}")
    v.info(" · ".join(partes))
    for a in r.avisos:
        v.aviso(a)


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
        False, "--sem-envio", help="Arquiva em saidas/, mas não envia (e-mail)."
    ),
    llm: str = typer.Option(None, "--llm", help="local (servidor de LLM) | offline"),
    sem_noticias: bool = typer.Option(
        False, "--sem-noticias", help="Não coleta (usa as já coletadas)."
    ),
    sem_gdelt: bool = typer.Option(False, "--sem-gdelt"),
    rerank: bool = typer.Option(None, "--rerank/--sem-rerank"),
    mostrar: bool = typer.Option(True, "--mostrar/--quieto"),
) -> None:
    """Gera (e entrega) a Palavra do Dia."""
    from fiat_lux.config import obter_settings
    from fiat_lux.logs import logs_detalhados, so_erros_no_console
    from fiat_lux.orquestracao.diaria import OpcoesDiaria, executar

    s = obter_settings()
    # o andamento e o resultado dizem o que importa; com --verboso ou --json-logs, valem os logs
    with (
        so_erros_no_console(),
        v.andamento("começando", animar=not logs_detalhados()) as andamento,
        v.acompanhar_llm(andamento),
    ):
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
                ao_mudar_etapa=lambda e: andamento.atualizar(v.ETAPAS.get(e, e)),
            ),
            s,
        )
    anunciar(r.status, andamento.decorrido)
    imprimir_resultado_diaria(r, mostrar)
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
    from fiat_lux.logs import logs_detalhados, so_erros_no_console
    from fiat_lux.orquestracao.semanal import OpcoesSemanal, executar, sabado_da_semana

    s = obter_settings()
    ref = sabado_da_semana(semana) if semana else _data(None)
    with (
        so_erros_no_console(),
        v.andamento("começando", animar=not logs_detalhados()) as andamento,
        v.acompanhar_llm(andamento),
    ):
        r = executar(
            OpcoesSemanal(
                data=ref,
                perfil=perfil or s.geral.perfil_padrao,
                dry_run=dry_run,
                sem_envio=sem_envio,
                provedor_llm=llm,
                usar_rerank=rerank,
                ao_mudar_etapa=lambda e: andamento.atualizar(v.ETAPAS.get(e, e)),
            ),
            s,
        )
    anunciar(r.status, andamento.decorrido, "Palavra da Semana")
    imprimir_resultado_diaria(r)  # a semanal tem o mesmo formato de resultado
    if r.status == "falhou":
        raise typer.Exit(1)
