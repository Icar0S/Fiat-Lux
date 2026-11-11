"""`fiatlux biblia ...` — Fase 1 (corpus)."""

from __future__ import annotations

import pickle
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from fiat_lux.cli.comum import console, falhar

app = typer.Typer(no_args_is_help=True)


def _caminho_resultado() -> Path:
    from fiat_lux.config import obter_settings

    return obter_settings().caminhos.interim / "construcao.pkl"


def baixar_todas(progresso: Callable[[str], None] | None = None) -> dict[str, int]:
    """O núcleo de `baixar` (todas as fontes, sem aceitar hash novo) sem saída própria: o
    `configurar` mostra o andamento do seu jeito. `FonteAlterada` sobe para quem chamou."""
    from fiat_lux.biblia.fontes import baixar_fontes
    from fiat_lux.config import obter_settings, raiz_projeto

    s = obter_settings()
    return baixar_fontes(
        s.caminhos.raw, raiz_projeto() / "fontes.lock.json", None, False, progresso=progresso
    )


@app.command()
def baixar(
    fonte: list[str] = typer.Option(
        None, "--fonte", "-f", help="ms, blivre, xref, vrs (padrão: todas)"
    ),
    atualizar_lock: bool = typer.Option(
        False, "--atualizar-lock", help="Aceita novos hashes (consciente)."
    ),
) -> None:
    """Baixa as fontes fixadas por commit e confere o SHA-256 (fontes.lock.json)."""
    from fiat_lux.biblia.fontes import FonteAlterada, baixar_fontes
    from fiat_lux.config import obter_settings, raiz_projeto

    s = obter_settings()
    try:
        r = baixar_fontes(
            s.caminhos.raw,
            raiz_projeto() / "fontes.lock.json",
            fonte or None,
            atualizar_lock,
            progresso=lambda p: console.print(f"  ↓ {p}"),
        )
    except FonteAlterada as e:
        falhar(str(e))
        return
    console.print(f"[green]ok[/]: {r['baixados']} baixados, {r['conferidos']} conferidos")


def ingerir_corpus() -> tuple[Any, list[Any]]:
    """O núcleo de `ingerir` sem saída própria: monta o `biblia.sqlite`, grava o resultado e o
    relatório e devolve (resultado, checagens). Fonte ausente ou alterada: `RuntimeError`."""
    from fiat_lux.biblia import banco
    from fiat_lux.biblia.construcao import construir_corpus
    from fiat_lux.biblia.fontes import verificar_fontes
    from fiat_lux.biblia.validacao import checar_banco, checar_contagens, gerar_relatorio
    from fiat_lux.config import dir_config, obter_settings, raiz_projeto

    s = obter_settings()
    problemas = verificar_fontes(s.caminhos.raw, raiz_projeto() / "fontes.lock.json")
    if problemas:
        raise RuntimeError(
            "fontes ausentes ou alteradas — rode `fiatlux biblia baixar`:\n  "
            + "\n  ".join(problemas[:10])
        )
    res = construir_corpus(s.caminhos.raw, dir_config(), s.caminhos.biblia_db)
    s.caminhos.interim.mkdir(parents=True, exist_ok=True)
    _caminho_resultado().write_bytes(pickle.dumps(res))
    con = banco.conectar(s.caminhos.biblia_db, somente_leitura=True)
    checagens = checar_contagens(res) + checar_banco(con)
    con.close()
    gerar_relatorio(res, checagens, s.caminhos.relatorio_corpus)
    return res, checagens


@app.command()
def ingerir() -> None:
    """Normaliza, limpa, alinha a versificação e grava data/processed/biblia.sqlite."""
    from fiat_lux.config import obter_settings

    s = obter_settings()
    try:
        with console.status("construindo o corpus…"):
            res, checagens = ingerir_corpus()
    except RuntimeError as e:
        falhar(str(e))
        return
    cob = res.cobertura
    console.print(
        f"[green]ok[/]: MS {res.contagens_finais['ms'][2]} versículos, BLIVRE {res.contagens_finais['blivre'][2]}; "
        f"versificação ≥0,8: {cob.get('protocanonicos_conf08', 0):.2%}; "
        f"lacunas {len(res.lacunas)} ({sum(x.status == 'aberta' for x in res.lacunas)} abertas); "
        f"checagens {sum(c.ok for c in checagens)}/{len(checagens)}"
    )
    console.print(f"relatório: {s.caminhos.relatorio_corpus}")


@app.command()
def validar() -> None:
    """Confere contagens, âncoras de texto e de versificação (falha com código 1)."""
    from fiat_lux.biblia import banco
    from fiat_lux.biblia.validacao import checar_banco, checar_contagens
    from fiat_lux.config import obter_settings

    s = obter_settings()
    con = banco.conectar(s.caminhos.biblia_db, somente_leitura=True)
    checagens = checar_banco(con)
    con.close()
    if _caminho_resultado().is_file():
        res = pickle.loads(_caminho_resultado().read_bytes())
        checagens = checar_contagens(res) + checagens
    falhas = [c for c in checagens if not c.ok]
    for c in checagens:
        console.print(f"{'✅' if c.ok else '❌'} {c.nome}: {c.detalhe}")
    if falhas:
        falhar(f"{len(falhas)} checagem(ns) falharam")
    console.print(f"[green]ok[/]: {len(checagens)} checagens")


@app.command()
def relatorio() -> None:
    """Regera docs/qualidade-corpus.md a partir da última ingestão."""
    from fiat_lux.biblia import banco
    from fiat_lux.biblia.validacao import checar_banco, checar_contagens, gerar_relatorio
    from fiat_lux.config import obter_settings

    s = obter_settings()
    if not _caminho_resultado().is_file():
        falhar("rode `fiatlux biblia ingerir` antes")
    res = pickle.loads(_caminho_resultado().read_bytes())
    con = banco.conectar(s.caminhos.biblia_db, somente_leitura=True)
    checagens = checar_contagens(res) + checar_banco(con)
    con.close()
    gerar_relatorio(res, checagens, s.caminhos.relatorio_corpus)
    console.print(f"[green]ok[/]: {s.caminhos.relatorio_corpus}")


@app.command("exportar-md")
def exportar_md(
    traducao: list[str] = typer.Option(None, "--traducao", "-t", help="ms, blivre (padrão: ambas)"),
) -> None:
    """Exporta um Markdown por capítulo (frontmatter YAML + âncoras ^vN, compatível com Obsidian)."""
    from fiat_lux.biblia.exportar_md import exportar
    from fiat_lux.config import obter_settings

    s = obter_settings()
    r = exportar(s.caminhos.biblia_db, s.caminhos.markdown, traducao or ["ms", "blivre"])
    console.print(
        f"[green]ok[/]: {r['arquivos']} arquivos em {s.caminhos.markdown} ({r['links_quebrados']} links quebrados)"
    )


@app.command()
def passagem(ref: str, traducao: str = typer.Option("ms", "--traducao", "-t")) -> None:
    """Mostra uma passagem: `fiatlux biblia passagem "Jo 3,16-17"`."""
    from fiat_lux.biblia.repositorio import Repositorio

    repo = Repositorio.abrir()
    p = repo.get_passagem(ref, traducao)
    console.print(f"[bold]{p.ref_formatada}[/] ({p.traducao})")
    for cap, vers, texto in p.versiculos:
        console.print(f"[dim]{cap},{vers}[/] {texto}")
    for aviso in p.avisos:
        console.print(f"[yellow]aviso:[/] {aviso}")
