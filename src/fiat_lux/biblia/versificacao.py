"""Versificação: conversão entre esquemas e alinhamento MS ↔ BLIVRE (plano §8.1.4).

Esquemas:
- `eng` (canônico interno): BLIVRE, referências cruzadas, taxonomia. Títulos de salmo = v. 0.
- `ms-vulg`: Matos Soares (Vulgata/LXX; títulos às vezes contados; Dn 14 caps; Est 16 caps).
- `cnbb-lit`: referências da API de liturgia (Nova Vulgata): AT com numeração **hebraica**
  (ex.: Ml 3,23 = eng Ml 4,5) e salmos com capítulos da LXX.

Estratégia em três camadas:
1. **Tabelas** (`ubsicap/versification_json`, MIT): vul→org e eng→org, compostas em vul→eng.
2. **Alinhamento** monotônico MS↔BLIVRE por programação dinâmica em banda, guiado pela
   previsão das tabelas; similaridade TF-IDF de n-gramas de caracteres (as duas traduções em
   português servem de pedra de Roseta). Movimentos 1-1, 1-0, 0-1, 2-1, 1-2 e 1-3.
3. **Sobrescritas** manuais em `config/versificacao_overrides.tsv`.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from sklearn.feature_extraction.text import TfidfVectorizer

Ref = tuple[str, int, int]  # (livro USFM, capítulo, versículo)
DIR_DADOS = Path(__file__).resolve().parent / "dados"

LIVROS_SEM_ENG = frozenset(
    {"S3Y", "SUS", "BEL", "ESG", "DAG", "PS2", "MAN", "1ES", "2ES", "3MA", "4MA", "LAO", "6EZ"}
)
_RE_REF = re.compile(r"^([1-4A-Z][A-Z0-9]{2})\s+(\d+):(\d+)[a-z]*(?:-(\d+)[a-z]*)?$")


def ref_str(ref: Ref) -> str:
    return f"{ref[0]}.{ref[1]}.{ref[2]}"


def parse_ref_str(s: str) -> Ref:
    livro, cap, vers = s.split(".")
    return (livro, int(cap), int(vers))


# --------------------------------------------------------------------------- tabelas VRS


def _expandir(origem: str, destino: str) -> list[tuple[Ref, Ref]]:
    mo, md = _RE_REF.match(origem.strip()), _RE_REF.match(destino.strip())
    if not mo or not md:
        return []
    lo, co, vo1, vo2 = mo.group(1), int(mo.group(2)), int(mo.group(3)), mo.group(4)
    ld, cd, vd1, vd2 = md.group(1), int(md.group(2)), int(md.group(3)), md.group(4)
    so = list(range(vo1, int(vo2) + 1)) if vo2 and int(vo2) >= vo1 else [vo1]
    sd = list(range(vd1, int(vd2) + 1)) if vd2 and int(vd2) >= vd1 else [vd1]
    if len(sd) == 1:
        return [((lo, co, v), (ld, cd, sd[0])) for v in so]
    if len(so) == 1:
        return [((lo, co, so[0]), (ld, cd, sd[0]))]
    return [((lo, co, a), (ld, cd, b)) for a, b in zip(so, sd, strict=False)]


@dataclass(slots=True)
class TabelaVrs:
    """`mappedVerses` de um arquivo de versificação: ref (esquema) → ref (org)."""

    para_org_map: dict[Ref, Ref] = field(default_factory=dict)
    de_org_map: dict[Ref, Ref] = field(default_factory=dict)

    @classmethod
    def carregar(cls, caminho: Path) -> TabelaVrs:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        t = cls()
        for k, v in dados.get("mappedVerses", {}).items():
            for a, b in _expandir(k, v):
                t.para_org_map[a] = b  # entradas posteriores corrigem anteriores (ex.: PSA 9:22)
        for a, b in t.para_org_map.items():
            t.de_org_map.setdefault(b, a)
        return t

    def para_org(self, ref: Ref) -> Ref:
        return self.para_org_map.get(ref, ref)

    def de_org(self, ref: Ref) -> Ref:
        return self.de_org_map.get(ref, ref)


# Partes de salmo da liturgia, em numeração da Vulgata (LXX): (cap, vers_ini, vers_fim)
PARTES_SALMO_VULG: dict[str, tuple[int, int, int]] = {
    "9A": (9, 1, 21),
    "9B": (9, 22, 39),
    "113A": (113, 1, 8),
    "113B": (113, 9, 26),
    "18A": (18, 1, 7),
    "18B": (18, 8, 15),
}
# Partes em numeração hebraica (org): (cap, vers_ini, vers_fim)
PARTES_SALMO_ORG: dict[str, tuple[int, int, int]] = {
    "19A": (19, 1, 7),
    "19B": (19, 8, 15),
    "147A": (147, 1, 11),
    "147B": (147, 12, 20),
    "116A": (116, 1, 9),
    "116B": (116, 10, 19),
}


class Versificacao:
    """Conversões entre esquemas usando as tabelas VRS (camada 1)."""

    def __init__(self, eng: TabelaVrs, vul: TabelaVrs) -> None:
        self.eng = eng
        self.vul = vul

    @classmethod
    def carregar(cls, dir_vrs: Path | None = None) -> Versificacao:
        """Tabelas eng/vul; por padrão, as cópias embutidas no pacote (MIT, ubsicap)."""
        base = dir_vrs or DIR_DADOS
        return cls(TabelaVrs.carregar(base / "eng.json"), TabelaVrs.carregar(base / "vul.json"))

    def org_para_eng(self, ref: Ref) -> Ref | None:
        r = self.eng.de_org(ref)
        if r[0] == "LJE":  # Carta de Jeremias = Br 6 no esquema eng
            r = ("BAR", 6, r[2])
        if r[0] in LIVROS_SEM_ENG:
            return None
        return r

    def vul_para_eng(self, ref: Ref) -> Ref | None:
        livro, cap, vers = ref
        if livro == "EST":  # Vulgata: 1,1–10,3 = hebraico; 10,4–16,24 = acréscimos gregos
            return ref if (cap < 10 or (cap == 10 and vers <= 3)) else None
        if livro == "DAN":
            # vul.json tem Daniel na numeração da Vulgata (DAN) e, à parte, o grego (DAG)
            mapa = self.vul.para_org_map
            org = mapa.get(ref) or mapa.get(("DAG", cap, vers)) or ref
        else:
            org = self.vul.para_org(ref)
        if org[0] == "DAG":
            org = ("DAN", org[1], org[2])
        return self.org_para_eng(org)

    def ms_para_eng(self, ref: Ref) -> Ref | None:
        """Previsão tabelada (camada 1) para um versículo da Matos Soares."""
        return self.vul_para_eng(ref)

    def cnbb_para_eng(
        self, livro: str, cap: int, vers: int, *, hebraico: bool = True
    ) -> Ref | None:
        """Converte uma referência da liturgia (Nova Vulgata) para `eng`.

        Salmos: `hebraico=False` quando só veio o número da LXX (então segue a Vulgata).
        Daniel: segue a Vulgata (acréscimos em Dn 3,24-90; 13; 14).
        """
        if livro == "PSA" and not hebraico:
            return self.vul_para_eng((livro, cap, vers))
        if livro == "DAN":
            return self.vul_para_eng((livro, cap, vers))
        if livro == "EST":
            return (livro, cap, vers)
        return self.org_para_eng((livro, cap, vers))


# --------------------------------------------------------------------------- alinhamento


@dataclass(frozen=True, slots=True)
class Par:
    """Um passo do alinhamento: `ni` versículos da MS a partir de `i` ↔ `nj` da BLIVRE a partir de `j`."""

    i: int
    ni: int
    j: int
    nj: int
    sim: float


@dataclass(slots=True)
class ParametrosAlinhamento:
    banda: int = 40
    theta: float = 0.10  # similaridade abaixo da qual casar é pior que pular
    custo_fusao: float = 0.06
    recompensa_pulo: float = -0.01
    bonus_tabela: float = 0.25  # prior: par previsto pelas tabelas de versificação
    bonus_lacuna: float = 0.15  # prior: versículo da MS seguido de lacuna tende a estar fundido


class _Similaridades:
    """Matrizes de similaridade (cosseno TF-IDF) 1-1, 2-1, 1-2 e 1-3 entre dois livros."""

    def __init__(self, a: Sequence[str], b: Sequence[str]) -> None:
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, norm=None)
        matriz = vec.fit_transform(list(a) + list(b))
        ra, rb = matriz[: len(a)], matriz[len(a) :]
        self.c: NDArray[np.float32] = (ra @ rb.T).toarray().astype(np.float32)
        self.na = np.sqrt(np.asarray(ra.multiply(ra).sum(axis=1)).ravel()).astype(np.float32)
        self.nb = np.sqrt(np.asarray(rb.multiply(rb).sum(axis=1)).ravel()).astype(np.float32)
        self.na[self.na == 0] = 1e-6
        self.nb[self.nb == 0] = 1e-6
        ga = np.asarray(ra[:-1].multiply(ra[1:]).sum(axis=1)).ravel() if len(a) > 1 else np.zeros(0)
        gb = np.asarray(rb[:-1].multiply(rb[1:]).sum(axis=1)).ravel() if len(b) > 1 else np.zeros(0)
        gb2 = (
            np.asarray(rb[1:-1].multiply(rb[2:]).sum(axis=1)).ravel() if len(b) > 2 else np.zeros(0)
        )
        gb02 = (
            np.asarray(rb[:-2].multiply(rb[2:]).sum(axis=1)).ravel() if len(b) > 2 else np.zeros(0)
        )
        self.s11 = self.c / np.outer(self.na, self.nb)
        if len(a) > 1:
            na2 = np.sqrt(self.na[:-1] ** 2 + self.na[1:] ** 2 + 2 * ga)
            self.s21 = (self.c[:-1] + self.c[1:]) / np.outer(na2, self.nb)
        else:
            self.s21 = np.zeros((0, len(b)), dtype=np.float32)
        if len(b) > 1:
            nb2 = np.sqrt(self.nb[:-1] ** 2 + self.nb[1:] ** 2 + 2 * gb)
            self.s12 = (self.c[:, :-1] + self.c[:, 1:]) / np.outer(self.na, nb2)
        else:
            self.s12 = np.zeros((len(a), 0), dtype=np.float32)
        if len(b) > 2:
            nb3 = np.sqrt(
                self.nb[:-2] ** 2
                + self.nb[1:-1] ** 2
                + self.nb[2:] ** 2
                + 2 * (gb[:-1] + gb2 + gb02)
            )
            self.s13 = (self.c[:, :-2] + self.c[:, 1:-1] + self.c[:, 2:]) / np.outer(self.na, nb3)
        else:
            self.s13 = np.zeros((len(a), 0), dtype=np.float32)


def alinhar(
    a: Sequence[str],
    b: Sequence[str],
    guia: Sequence[float] | None = None,
    params: ParametrosAlinhamento | None = None,
    preferidos: Sequence[int | None] | None = None,
    capitulos_a: Sequence[int] | None = None,
    capitulos_b: Sequence[int] | None = None,
    fusao_provavel: Sequence[bool] | None = None,
) -> list[Par]:
    """Alinha duas sequências de versículos (mesmo livro) em ordem. Devolve os passos.

    `preferidos[i]`: índice em `b` previsto pelas tabelas para `a[i]` (recebe bônus).
    `capitulos_a/b`: se dados, fusões 2-1/1-2/1-3 não podem atravessar capítulos (salmos).
    `fusao_provavel[i]`: `a[i]` é seguido de lacuna de numeração (bônus para 1-2 e 1-3).
    """
    p = params or ParametrosAlinhamento()
    pref: list[int] = [(-9 if x is None else x) for x in (preferidos or [])] or [-9] * len(a)
    bonus = p.bonus_tabela
    ca = list(capitulos_a) if capitulos_a is not None else None
    cb = list(capitulos_b) if capitulos_b is not None else None
    fus = (
        [p.bonus_lacuna if x else 0.0 for x in fusao_provavel] if fusao_provavel else [0.0] * len(a)
    )
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return [Par(i, 1, 0, 0, 0.0) for i in range(n)] + [Par(n, 0, j, 1, 0.0) for j in range(m)]
    sims = _Similaridades(a, b)
    if guia is None:
        guia = [i * m / n for i in range(n + 1)]
    centro = [0.0] * (n + 1)
    for i in range(n + 1):
        centro[i] = min(max(guia[i] if i < len(guia) else m, 0.0), float(m))
    centro[0], centro[n] = 0.0, float(m)
    banda = p.banda
    lo = [max(0, math.floor(c) - banda) for c in centro]
    hi = [min(m, math.ceil(c) + banda) for c in centro]
    lo[0], hi[n] = 0, m
    neg = -1e18
    dp: list[list[float]] = [[neg] * (hi[i] - lo[i] + 1) for i in range(n + 1)]
    bp: list[list[int]] = [[-1] * (hi[i] - lo[i] + 1) for i in range(n + 1)]
    dp[0][0] = 0.0
    th, cf, rp = p.theta, p.custo_fusao, p.recompensa_pulo
    s11, s21, s12, s13 = sims.s11, sims.s21, sims.s12, sims.s13
    for i in range(n + 1):
        li, hi_i = lo[i], hi[i]
        row = dp[i]
        brow = bp[i]
        prev = dp[i - 1] if i >= 1 else None
        lp = lo[i - 1] if i >= 1 else 0
        hp = hi[i - 1] if i >= 1 else -1
        prev2 = dp[i - 2] if i >= 2 else None
        lp2 = lo[i - 2] if i >= 2 else 0
        hp2 = hi[i - 2] if i >= 2 else -1
        r11 = s11[i - 1].tolist() if i >= 1 else None
        r12 = s12[i - 1].tolist() if i >= 1 and m > 1 else None
        r13 = s13[i - 1].tolist() if i >= 1 and m > 2 else None
        r21 = s21[i - 2].tolist() if i >= 2 else None
        for j in range(li, hi_i + 1):
            k = j - li
            if i == 0 and j == 0:
                continue
            best, arg = neg, -1
            if prev is not None:
                pi = pref[i - 1]
                if j >= 1 and lp <= j - 1 <= hp and r11 is not None:
                    v = prev[j - 1 - lp]
                    if v > neg:
                        cand = v + 2 * (r11[j - 1] - th) + (bonus if pi == j - 1 else 0.0)
                        if cand > best:
                            best, arg = cand, 0
                if lp <= j <= hp:
                    v = prev[j - lp]
                    if v > neg and v + rp > best:
                        best, arg = v + rp, 1
                if (
                    j >= 2
                    and lp <= j - 2 <= hp
                    and r12 is not None
                    and (cb is None or cb[j - 2] == cb[j - 1])
                ):
                    v = prev[j - 2 - lp]
                    if v > neg:
                        extra = (bonus if pi in (j - 2, j - 1) else 0.0) + fus[i - 1]
                        cand = v + 2 * (r12[j - 2] - th) - cf + extra
                        if cand > best:
                            best, arg = cand, 3
                if (
                    j >= 3
                    and lp <= j - 3 <= hp
                    and r13 is not None
                    and (cb is None or cb[j - 3] == cb[j - 1])
                ):
                    v = prev[j - 3 - lp]
                    if v > neg:
                        extra = (bonus if pi in (j - 3, j - 2, j - 1) else 0.0) + fus[i - 1]
                        cand = v + 2 * (r13[j - 3] - th) - 2 * cf + extra
                        if cand > best:
                            best, arg = cand, 5
            if j >= 1 and k >= 1:
                v = row[k - 1]
                if v > neg and v + rp > best:
                    best, arg = v + rp, 2
            if (
                prev2 is not None
                and j >= 1
                and lp2 <= j - 1 <= hp2
                and r21 is not None
                and (ca is None or ca[i - 2] == ca[i - 1])
            ):
                v = prev2[j - 1 - lp2]
                if v > neg:
                    extra = bonus if j - 1 in (pref[i - 2], pref[i - 1]) else 0.0
                    cand = v + 2 * (r21[j - 1] - th) - cf + extra
                    if cand > best:
                        best, arg = cand, 4
            row[k] = best
            brow[k] = arg
    # backtracking
    passos: list[Par] = []
    i, j = n, m
    while i > 0 or j > 0:
        arg = bp[i][j - lo[i]]
        if arg == 0:
            passos.append(Par(i - 1, 1, j - 1, 1, float(s11[i - 1, j - 1])))
            i, j = i - 1, j - 1
        elif arg == 1:
            passos.append(Par(i - 1, 1, j, 0, 0.0))
            i -= 1
        elif arg == 2:
            passos.append(Par(i, 0, j - 1, 1, 0.0))
            j -= 1
        elif arg == 3:
            passos.append(Par(i - 1, 1, j - 2, 2, float(s12[i - 1, j - 2])))
            i, j = i - 1, j - 2
        elif arg == 4:
            passos.append(Par(i - 2, 2, j - 1, 1, float(s21[i - 2, j - 1])))
            i, j = i - 2, j - 1
        elif arg == 5:
            passos.append(Par(i - 1, 1, j - 3, 3, float(s13[i - 1, j - 3])))
            i, j = i - 1, j - 3
        else:  # célula inalcançável dentro da banda: recua consumindo a sequência mais longa
            if i > 0:
                passos.append(Par(i - 1, 1, j, 0, 0.0))
                i -= 1
            else:
                passos.append(Par(i, 0, j - 1, 1, 0.0))
                j -= 1
    passos.reverse()
    return passos


def similaridade_textos(a: str, b: str) -> float:
    """Cosseno TF-IDF de n-gramas de caracteres entre dois textos isolados."""
    if not a.strip() or not b.strip():
        return 0.0
    s = _Similaridades([a], [b])
    return float(s.s11[0, 0])


def melhor_divisao(texto: str, alvo1: str, alvo2: str) -> tuple[int, float, float] | None:
    """Ponto de divisão de um versículo fundido que melhor reproduz `alvo1` + `alvo2`.

    Candidatos: fronteiras após `.;:!?` (e, na falta delas, após vírgulas). Devolve
    (posição, sim1, sim2) ou None se não houver candidato.
    """
    candidatos = [m.end() for m in re.finditer(r"[.;:!?]['\"»)]*\s+", texto)]
    if not candidatos:
        candidatos = [m.end() for m in re.finditer(r",\s+", texto)]
    candidatos = [c for c in candidatos if 8 <= c <= len(texto) - 8]
    if not candidatos:
        return None
    partes_a = [texto[:c].strip() for c in candidatos]
    partes_b = [texto[c:].strip() for c in candidatos]
    sims = _Similaridades(partes_a + partes_b, [alvo1, alvo2])
    k = len(candidatos)
    melhor: tuple[int, float, float] | None = None
    melhor_total = -1.0
    total_len = len(alvo1) + len(alvo2)
    for idx, c in enumerate(candidatos):
        s1 = float(sims.s11[idx, 0])
        s2 = float(sims.s11[k + idx, 1])
        # prior de comprimento (Gale-Church simplificado)
        esperado = len(alvo1) / total_len if total_len else 0.5
        desvio = abs(c / len(texto) - esperado)
        total = s1 + s2 - 0.5 * desvio
        if total > melhor_total:
            melhor_total, melhor = total, (c, s1, s2)
    return melhor
