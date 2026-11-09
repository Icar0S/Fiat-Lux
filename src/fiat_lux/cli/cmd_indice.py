"""`fiatlux indice ...` e `fiatlux buscar` — Fase 4."""

from __future__ import annotations

import typer

from fiat_lux.cli.comum import console, falhar

app = typer.Typer(no_args_is_help=True)


@app.command()
def construir(
    modelo: str = typer.Option(None, "--modelo", help="Modelo de embeddings (padrão: settings)."),
    embedder: str = typer.Option(None, "--embedder", help="auto | neural | lexical"),
) -> None:
    """Gera as perícopes e os vetores no biblia.sqlite."""
    from fiat_lux.config import obter_settings
    from fiat_lux.rag.indice import construir as _construir

    s = obter_settings()
    if not s.caminhos.biblia_db.is_file():
        falhar("biblia.sqlite ausente: rode `fiatlux biblia ingerir`")
    r = _construir(
        s.caminhos.biblia_db,
        embedder or s.rag.embedder,
        modelo or s.rag.modelo_embeddings,
        progresso=lambda m: console.print(m),
    )
    console.print(f"[green]ok[/]: {r}")


@app.command("baixar-release")
def baixar_release(
    repo: str = typer.Option("Icar0S/Fiat-Lux", "--repo"),
    tag: str = typer.Option("indice-latest", "--tag"),
) -> None:
    """Baixa o biblia.sqlite publicado como asset de Release (CI; usa `gh`)."""
    import shutil
    import subprocess

    from fiat_lux.config import obter_settings

    s = obter_settings()
    if s.caminhos.biblia_db.is_file():
        console.print("biblia.sqlite já presente")
        return
    if shutil.which("gh") is None:
        falhar("GitHub CLI (gh) não encontrado")
    s.caminhos.biblia_db.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "gh",
            "release",
            "download",
            tag,
            "--repo",
            repo,
            "--pattern",
            "*.sqlite",
            "--pattern",
            "*.pkl",
            "--dir",
            str(s.caminhos.biblia_db.parent),
            "--clobber",
        ],
        check=True,
    )
    console.print(f"[green]ok[/]: {s.caminhos.biblia_db}")


def buscar(
    consulta: str = typer.Argument(..., help="Consulta em linguagem natural."),
    perfil: str = typer.Option("catolico", "--perfil"),
    k: int = typer.Option(10, "--k"),
    tempo: str = typer.Option("comum", "--tempo"),
    rerank: bool = typer.Option(
        False, "--rerank/--sem-rerank", help="Rerank neural (lento em CPU)."
    ),
) -> None:
    """Depura o RAG: busca híbrida + boosts para uma consulta."""
    from rich.markup import escape

    from fiat_lux.biblia.repositorio import Repositorio
    from fiat_lux.config import obter_settings
    from fiat_lux.pastoral import perfil as obter_perfil
    from fiat_lux.rag.busca import Buscador
    from fiat_lux.rag.recuperacao import EntradaRecuperacao, Recuperador
    from fiat_lux.rag.rerank import criar_reranker

    s = obter_settings()
    rec = Recuperador(
        Buscador.abrir(),
        criar_reranker(rerank, s.rag.modelo_rerank),
        Repositorio.abrir(),
        s.rag.model_copy(update={"candidatos_llm": k}),
    )
    cands = rec.recuperar(
        EntradaRecuperacao([consulta], ["consulta"], obter_perfil(perfil), tempo, [])
    )
    for i, c in enumerate(cands, 1):
        e = c.escores
        console.print(
            f"[bold]{i:2d}. {escape(c.rotulo())}[/] ({c.traducao}, {c.origem}) S={e.get('S', 0):.3f} "
            f"R={e.get('R', 0):.2f} T={e.get('T', 0):.2f} rrf={e.get('rrf', 0):.4f}"
        )
        console.print(f"    {escape(c.texto[:220])}")
