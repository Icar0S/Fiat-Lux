"""Ingestão da Bíblia Livre (BLIVRE), plano §3.3.

Cada arquivo `blivre-{abbrev}.json` é um livro `{name, abbrev, chapters:[{number, verses:[...]}]}`,
em texto puro, com versificação `eng` (títulos dos salmos sem número próprio).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from fiat_lux.biblia.catalogo import LIVROS, por_sigla_blivre
from fiat_lux.biblia.modelos import VersoBruto


def ler_blivre(dir_json: Path) -> list[VersoBruto]:
    saida: list[VersoBruto] = []
    for lv in LIVROS:
        if not lv.sigla_blivre:
            continue
        arq = dir_json / f"blivre-{lv.sigla_blivre}.json"
        dados = json.loads(arq.read_text(encoding="utf-8-sig"))
        cod = por_sigla_blivre(str(dados.get("abbrev", lv.sigla_blivre))).codigo
        if cod != lv.codigo:
            raise ValueError(f"{arq.name}: abbrev {dados.get('abbrev')!r} ≠ {lv.codigo}")
        for cap in dados["chapters"]:
            vistos: Counter[int] = Counter()
            for v in cap["verses"]:
                n = int(v["number"])
                vistos[n] += 1
                saida.append(
                    VersoBruto("blivre", cod, int(cap["number"]), n, str(v["text"]), vistos[n])
                )
    return saida
