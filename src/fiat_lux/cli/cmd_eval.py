"""`fiatlux eval rodar` — Fase 7."""

from __future__ import annotations

import json

import typer

from fiat_lux.cli.comum import console

app = typer.Typer(no_args_is_help=True)


@app.command()
def rodar(suite: str = typer.Option("rapida", "--suite", help="rapida | completa")) -> None:
    """Roda a suíte de avaliação e grava eval/relatorios/AAAA-MM-DD-<suite>.{json,html}."""
    from fiat_lux.avaliacao import rodar as _rodar

    rel = _rodar(suite)
    resumo = {
        "parser": rel["parser"]["acuracia"],
        "adversarial": f"{rel['adversarial']['aprovados']}/{rel['adversarial']['casos']}",
        "metamorficos": {k: v for k, v in rel["metamorficos"].items() if isinstance(v, bool)},
    }
    for perfil in ("catolico", "evangelico"):
        r = rel.get(f"recuperacao_{perfil}", {})
        if "acerto@10" in r:
            resumo[f"rag_{perfil}"] = {
                k: r[k] for k in ("embedder", "acerto@10", "recall@10", "ndcg@10", "mrr")
            }
    if "e2e" in rel:
        resumo["e2e"] = {
            k: rel["e2e"][k]
            for k in ("dias", "taxa_fallback", "citacoes_invalidas", "tempo_medio_s")
        }
    console.print_json(json.dumps(resumo, ensure_ascii=False))
