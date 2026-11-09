"""CLI do Fiat Lux (plano §8.9). Uso: `fiatlux --help`."""

from __future__ import annotations

import typer

from fiat_lux.cli import (
    cmd_biblia,
    cmd_estado,
    cmd_eval,
    cmd_indice,
    cmd_liturgia,
    cmd_noticias,
    cmd_palavra,
)

app = typer.Typer(
    name="fiatlux",
    help="Fiat Lux: assistente diário e semanal da Palavra de Deus.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
app.add_typer(
    cmd_biblia.app, name="biblia", help="Corpus bíblico: baixar, ingerir, validar, exportar."
)
app.add_typer(cmd_indice.app, name="indice", help="Índice de busca (perícopes, FTS5, vetores).")
app.add_typer(cmd_liturgia.app, name="liturgia", help="Liturgia diária (API + calendário local).")
app.add_typer(cmd_noticias.app, name="noticias", help="Coleta de notícias e medidor.")
app.add_typer(cmd_palavra.app, name="palavra", help="Gera a Palavra do Dia / da Semana.")
app.add_typer(cmd_eval.app, name="eval", help="Suítes de avaliação.")
app.add_typer(cmd_estado.app, name="estado", help="Estado: execuções, mensagens, LGPD.")
app.command("buscar", help="Depura o RAG: busca passagens para uma consulta.")(cmd_indice.buscar)


@app.callback()
def _principal(
    json_logs: bool = typer.Option(False, "--json-logs", help="Logs estruturados em JSON."),
    verboso: bool = typer.Option(False, "--verboso", "-v"),
) -> None:
    import os

    from fiat_lux.config import raiz_projeto
    from fiat_lux.logs import configurar_logs

    # modelos do Hugging Face no cache do projeto (plano: HF_HOME=.cache/huggingface)
    os.environ.setdefault("HF_HOME", str(raiz_projeto() / ".cache" / "huggingface"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    configurar_logs(json=json_logs, nivel="DEBUG" if verboso else "INFO")


if __name__ == "__main__":
    app()
