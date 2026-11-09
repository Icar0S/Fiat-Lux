"""Gera eval/golden/referencias.yaml a partir das liturgias baixadas (data/raw/liturgia).

Cada referência real vira um caso de regressão do parser: a forma normalizada e o livro
ficam gravados; mudanças de comportamento aparecem como diff no YAML.

    uv run python scripts/gerar_golden_referencias.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from fiat_lux.biblia.referencias import (
    Referencia,
    formatar,
    parse_com_contexto,
    tentar_parse,
)

RAIZ = Path(__file__).resolve().parents[1]


def main() -> int:
    origem = RAIZ / "data" / "raw" / "liturgia"
    casos: dict[str, dict[str, object]] = {}
    for arq in sorted(origem.glob("*.json")):
        dados = json.loads(arq.read_text(encoding="utf-8"))
        for campo, lista in dados.get("leituras", {}).items():
            anteriores: list[Referencia] = []
            for item in lista:
                ref = (item.get("referencia") or "").strip()
                if not ref:
                    continue
                r = parse_com_contexto(ref, anteriores)
                contexto = r.livro if tentar_parse(ref) is None else None
                anteriores.append(r)
                if ref in casos:
                    continue
                casos[ref] = {
                    "ref": ref,
                    "tipo": campo,
                    "primeira_data": arq.stem,
                    "livro": r.livro,
                    "normalizada": formatar(r),
                    **({"cantico": True} if r.cantico else {}),
                    **({"salmo_hebraico": r.salmo_hebraico} if r.salmo_hebraico else {}),
                    **({"nota": r.nota} if r.nota else {}),
                    **({"livro_padrao": contexto} if contexto else {}),
                }
    destino = RAIZ / "eval" / "golden" / "referencias.yaml"
    destino.parent.mkdir(parents=True, exist_ok=True)
    cabecalho = (
        "# Corpus real de referências da API de liturgia (gerado; não edite à mão).\n"
        "# scripts/gerar_golden_referencias.py — plano §11.2 (meta ≥ 1.000 referências).\n"
    )
    corpo = yaml.safe_dump(
        {"versao": 1, "total": len(casos), "referencias": list(casos.values())},
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )
    destino.write_text(cabecalho + corpo, encoding="utf-8")
    print(f"{len(casos)} referências → {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
