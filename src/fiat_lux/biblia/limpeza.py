"""Limpeza determinística do texto bíblico (plano §8.1.2, passo 3).

Cada regra tem nome e contador; o texto bruto é sempre preservado à parte. Também separa os
títulos dos salmos da Matos Soares, que seguem a Vulgata: às vezes são um versículo inteiro
(Sl 3,1), às vezes vêm fundidos ao corpo (Sl 22,1 "Salmo. De Davide. O Senhor me apascenta").
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# (nome, padrão, substituição) — aplicadas em ordem.
_REGRAS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("ver_nota", re.compile(r"\s*\(\s*ver\s+nota\s*\)?", re.IGNORECASE), ""),
    ("hifen_invisivel", re.compile("­"), ""),
    ("marcador_nota_chave", re.compile(r"\{\d+:"), ""),
    ("colchetes_chaves", re.compile(r"[\[\]{}]"), ""),
    ("sublinhado", re.compile(r"_"), " "),
    ("asterisco", re.compile(r"\*"), ""),
    ("registrado", re.compile("®"), ""),
    ("nota_numerica_final", re.compile(r"(?<=[.;:!?])\d{1,2}\s*$"), ""),
    ("aspas_simples_tipograficas", re.compile("[‘’‚‛´`]"), "'"),
    ("aspas_duplas_tipograficas", re.compile("[“”„‟]"), '"'),
    ("parenteses_duplicados", re.compile(r"\(\s*\("), "("),
    ("parenteses_duplicados_fim", re.compile(r"\)\s*\)"), ")"),
    ("espaco_apos_abre", re.compile(r"\(\s+"), "("),
    ("espaco_antes_fecha", re.compile(r"\s+\)"), ")"),
    ("parenteses_vazios", re.compile(r"\(\s*\)"), ""),
    ("espaco_antes_pontuacao", re.compile(r"\s+([,.;:!?])"), r"\1"),
    ("espacos", re.compile(r"\s{2,}"), " "),
)

# Marcador da numeração hebraica no fim de versículos dos salmos fundidos (Sl 9 e 113 da MS).
_MARCADOR_HEBRAICO = re.compile(r"\s*\((\d{1,3})\s*,\s*(\d{1,3})\)\s*$")


@dataclass(slots=True)
class Limpo:
    texto: str
    regras: list[str]
    marcador_hebraico: tuple[int, int] | None = None


class Limpador:
    """Aplica as regras e acumula contadores (para o relatório de qualidade)."""

    def __init__(self) -> None:
        self.contadores: Counter[str] = Counter()

    def limpar(self, texto: str, *, salmo: bool = False) -> Limpo:
        aplicadas: list[str] = []
        marcador: tuple[int, int] | None = None
        t = texto
        if salmo:
            m = _MARCADOR_HEBRAICO.search(t)
            if m:
                marcador = (int(m.group(1)), int(m.group(2)))
                t = t[: m.start()]
                aplicadas.append("marcador_hebraico")
                self.contadores["marcador_hebraico"] += 1
        for nome, padrao, subst in _REGRAS:
            novo, n = padrao.subn(subst, t)
            if n and novo != t:
                aplicadas.append(nome)
                self.contadores[nome] += n
            t = novo
        t = t.strip()
        return Limpo(texto=t, regras=aplicadas, marcador_hebraico=marcador)


# --------------------------------------------------------------------------- títulos de salmos

_TOKENS_TITULO = [
    r"ao mestre do coro(?:\s*,\s*id[iu]th?u[nm])?",
    r"segundo id[iu]th?u[nm]",
    r"segundo a melodia\b[^.\"«]*(?:[\"«][^\"»]*[\"»])?(?:\s*\.\.\.)?",
    r"para (?:instrumentos de corda|flautas|mem[oó]ria|o dia de s[aá]bado|ac?ç[aã]o de gra[cç]as|ensinar)",
    r"sobre a oitava",
    r"c[aâ]ntico das subidas",
    r"c[aâ]ntico (?:para|de|do|da)\b[^.]*",
    r"s[uú]plicas? dum aflito[^.]*",
    r"lamenta[cç][aã]o de davide[^.]*",
    r"de mois[eé]s(?:\s*,\s*homem de deus)?",
    r"de (?:etan|heman) ezrahita",
    r"dos filhos d[eo] cor[eé]",
    r"d[eo] asaf",
    r"de salom[aã]o",
    r"de davide(?:\s*,\s*servo do senhor)?",
    r"mi?c?kt[aã]m?\w*",
    r"mas[kq]u?[iît][lL]?\w*",
    r"salmo",
    r"c[aâ]ntico",
    r"hino",
    r"s[uú]plicas?",
    r"ora[cç][aã]o",
    r"louvores?",
]
_RE_TOKEN = re.compile(
    r"^\s*(?:" + "|".join(_TOKENS_TITULO) + r")(?![\w])\s*(?:\.\.\.|[.,;:])?\s*",
    re.IGNORECASE,
)
# Circunstância do título ("quando foge de Absalão", "depois que Doeg..."), só após "De Davide".
_RE_OCASIAO = re.compile(
    r"^\s*(?:quando|depois|a prop[oó]sito|o qual|no dia|para ensinar)\b[^.]*(?:\.\s*|$)",
    re.IGNORECASE,
)


def separar_titulo_salmo(texto: str, anterior_e_titulo: bool = False) -> tuple[str | None, str]:
    """Separa o título do corpo. Devolve (titulo, corpo); corpo vazio ⇒ versículo só de título.

    `anterior_e_titulo`: o versículo anterior era só título (ex.: Sl 50,2 "Quando o profeta
    Natan foi ter com ele..." continua o título de Sl 50,1).
    """
    resto = texto
    partes: list[str] = []
    viu_davide = False
    if anterior_e_titulo and _RE_OCASIAO.match(resto):
        return texto.strip(), ""
    while True:
        m = _RE_TOKEN.match(resto)
        if m and m.end() > 0:
            trecho = m.group(0)
            partes.append(trecho)
            viu_davide = viu_davide or "davide" in trecho.casefold()
            resto = resto[m.end() :]
            continue
        if viu_davide:
            m2 = _RE_OCASIAO.match(resto)
            if m2 and m2.end() > 0:
                partes.append(m2.group(0))
                resto = resto[m2.end() :]
                continue
        break
    if not partes:
        return None, texto
    titulo = "".join(partes).strip()
    corpo = resto.strip()
    if re.fullmatch(r"[\d\s.,;:]*", corpo):
        corpo = ""
    return titulo, corpo
