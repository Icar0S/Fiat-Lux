"""Perícopes por janelas deslizantes dentro do capítulo (plano §8.4.1).

| Família        | Janela / passo                                   |
|----------------|--------------------------------------------------|
| Salmos         | salmo inteiro se ≤ 12 vv. (sem título); senão 6/4 |
| Pv, Eclo, Ecl  | 3 / 2                                            |
| Narrativos     | 8 / 5 (Gn–Mc, Evangelhos, Atos)                  |
| Demais         | 5 / 3                                            |

`tem_lacuna = 1` quando a janela atravessa uma lacuna com texto ausente na fonte.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from fiat_lux.biblia.catalogo import por_codigo
from fiat_lux.biblia.modelos import F_TITULO_SALMO

JANELAS: dict[str, tuple[int, int]] = {
    "salmos": (6, 4),
    "proverbial": (3, 2),
    "narrativo": (8, 5),
    "padrao": (5, 3),
}
SALMO_INTEIRO_ATE = 12


@dataclass(slots=True)
class Pericope:
    traducao: str
    livro: str
    cap_ini: int
    vers_ini: int
    cap_fim: int
    vers_fim: int
    texto: str
    versiculo_ids: list[int]
    refs_canonicas: list[str]
    tem_lacuna: bool = False
    id: int | None = None
    textos: list[str] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return len(self.texto.split())

    def rotulo(self) -> str:
        lv = por_codigo(self.livro)
        if self.cap_ini == self.cap_fim:
            faixa = (
                f"{self.vers_ini}"
                if self.vers_ini == self.vers_fim
                else f"{self.vers_ini}-{self.vers_fim}"
            )
            return f"{lv.nome_pt} {self.cap_ini},{faixa}"
        return f"{lv.nome_pt} {self.cap_ini},{self.vers_ini}-{self.cap_fim},{self.vers_fim}"


def _janelas(n: int, tamanho: int, passo: int) -> list[tuple[int, int]]:
    if n <= tamanho:
        return [(0, n)]
    saida = [(i, i + tamanho) for i in range(0, n - tamanho + 1, passo)]
    if saida[-1][1] < n:
        saida.append((n - tamanho, n))
    return saida


def gerar(con: sqlite3.Connection, traducao: str) -> list[Pericope]:
    lacunas: dict[tuple[str, int], set[int]] = defaultdict(set)
    for r in con.execute(
        "SELECT livro, capitulo, versiculo FROM lacunas WHERE traducao_id=? AND (status='aberta' OR tipo='ausente')",
        (traducao,),
    ):
        lacunas[(r[0], r[1])].add(int(r[2]))
    rows = con.execute(
        "SELECT id, livro, capitulo, versiculo, texto, ref_canonica, flags, fim_fundido FROM versiculos"
        " WHERE traducao_id=? ORDER BY livro, capitulo, versiculo",
        (traducao,),
    ).fetchall()
    por_cap: dict[tuple[str, int], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        if F_TITULO_SALMO in json.loads(r["flags"]):
            continue
        por_cap[(r["livro"], r["capitulo"])].append(r)
    saida: list[Pericope] = []
    for (livro, cap), versos in sorted(
        por_cap.items(), key=lambda kv: (por_codigo(kv[0][0]).ordem_catolica, kv[0][1])
    ):
        familia = por_codigo(livro).tipo_pericope
        tamanho, passo = JANELAS[familia]
        if familia == "salmos" and len(versos) <= SALMO_INTEIRO_ATE:
            tamanho, passo = len(versos), len(versos)
        for a, b in _janelas(len(versos), tamanho, passo):
            jan = versos[a:b]
            v_ini, v_fim = (
                int(jan[0]["versiculo"]),
                int(jan[-1]["fim_fundido"] or jan[-1]["versiculo"]),
            )
            buracos = {n for n in lacunas.get((livro, cap), set()) if v_ini <= n <= v_fim}
            saida.append(
                Pericope(
                    traducao=traducao,
                    livro=livro,
                    cap_ini=cap,
                    vers_ini=v_ini,
                    cap_fim=cap,
                    vers_fim=v_fim,
                    texto=" ".join(r["texto"] for r in jan),
                    versiculo_ids=[int(r["id"]) for r in jan],
                    refs_canonicas=[r["ref_canonica"] for r in jan if r["ref_canonica"]],
                    tem_lacuna=bool(buracos),
                    textos=[r["texto"] for r in jan],
                )
            )
    return saida
