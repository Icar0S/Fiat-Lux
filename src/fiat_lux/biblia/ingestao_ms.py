"""Ingestão da Matos Soares (`Dancrf/biblia-db`), plano §3.2 e §8.1.2.

Fonte canônica: `biblia.json`. Os arquivos por livro só entram na comparação cruzada
(relatório), porque divergem em 66 livros e usam nomes inconsistentes.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from fiat_lux.biblia.catalogo import LIVROS, resolver_nome_ms
from fiat_lux.biblia.modelos import VersoBruto
from fiat_lux.textos import chave

_PREFIXO = re.compile(r"^\s*\[\d+\]\s*")


def ler_biblia_json(caminho: Path) -> list[VersoBruto]:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    saida: list[VersoBruto] = []
    for livro in dados:
        cod = resolver_nome_ms(livro["livro"]).codigo
        for cap in livro["capitulos"]:
            vistos: Counter[int] = Counter()
            for v in cap["versiculos"]:
                n = int(v["numero"])
                vistos[n] += 1
                saida.append(
                    VersoBruto("ms", cod, int(cap["capitulo"]), n, str(v["texto"]), vistos[n])
                )
    return saida


@dataclass(frozen=True, slots=True)
class DiffLivro:
    codigo: str
    nome_arquivo: str
    nome_biblia_json: str
    versiculos_arquivo: int
    versiculos_biblia: int
    divergentes: int
    so_no_arquivo: int
    so_na_biblia: int


def comparar_arquivos_por_livro(dir_ms: Path, brutos: list[VersoBruto]) -> list[DiffLivro]:
    """Compara `biblia.json` com `antigotestamento/` e `novotestamento/` (após tirar `[n] `)."""
    base: dict[tuple[str, int, int], str] = {}
    for v in brutos:
        base.setdefault((v.livro, v.capitulo, v.versiculo), v.texto_bruto)
    diffs: list[DiffLivro] = []
    for lv in LIVROS:
        pasta = "antigotestamento" if lv.testamento == "AT" else "novotestamento"
        arq = dir_ms / pasta / f"{lv.sigla_ms.lower()}.json"
        if not arq.is_file():
            continue
        dados = json.loads(arq.read_text(encoding="utf-8"))
        textos: dict[tuple[int, int], str] = {}
        for cap in dados.get("capitulos", []):
            for v in cap.get("versiculos", []):
                textos.setdefault(
                    (int(cap["capitulo"]), int(v["numero"])), _PREFIXO.sub("", str(v["texto"]))
                )
        do_livro = {(c, n): t for (cod, c, n), t in base.items() if cod == lv.codigo}
        comuns = do_livro.keys() & textos.keys()
        divergentes = sum(1 for k in comuns if chave(do_livro[k]) != chave(textos[k]))
        diffs.append(
            DiffLivro(
                codigo=lv.codigo,
                nome_arquivo=str(dados.get("livro", "")),
                nome_biblia_json=lv.nome_ms,
                versiculos_arquivo=len(textos),
                versiculos_biblia=len(do_livro),
                divergentes=divergentes,
                so_no_arquivo=len(textos.keys() - do_livro.keys()),
                so_na_biblia=len(do_livro.keys() - textos.keys()),
            )
        )
    return diffs
