"""Portões de qualidade V1–V8 (plano §8.5.5 e §10). Nada é entregue sem passar por aqui.

| #  | Checagem                | Falha quando                                                        |
|----|-------------------------|---------------------------------------------------------------------|
| V1 | Placeholders            | {{P1}} ausente/duplicado; {{C1}}/{{C2}} duplicados; marcador desconhecido |
| V2 | Referências citadas     | referência no texto fora do conjunto permitido                      |
| V3 | Fidelidade de citações  | trecho entre aspas com ≥ 6 palavras sem par (partial_ratio ≥ 95)    |
| V4 | Comprimentos            | fora dos limites (tolerância de 15%)                                |
| V5 | Neutralidade política   | termo partidário, ou juiz aponta posição partidária                 |
| V6 | Sensibilidade           | CVV ausente com tema suicídio; castigo/profecia; vítimas; condenação |
| V7 | Perfil                  | deuterocanônico no evangélico; sem rótulo no ecumênico              |
| V8 | Injeção e saída         | URL fora das notícias; instruções ecoadas; HTML/Markdown malformado |
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from fiat_lux.biblia.catalogo import resolver
from fiat_lux.llm.esquemas import Julgamento, Redacao
from fiat_lux.pastoral import Neutralidade
from fiat_lux.textos import chave, contar_palavras

LINHA_CVV = "Se você está sofrendo, fale com o CVV: 188 (ligação gratuita) ou cvv.org.br"
MARCADORES_VALIDOS = ("P1", "C1", "C2")
_MARCADOR = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
_ASPAS = re.compile(r"[“\"«]([^”\"»]{12,600})[”\"»]")
_URL = re.compile(r"https?://[^\s)>\]]+")
_REF = re.compile(
    r"(?<![\w])((?:[1-3]\s?)?[A-ZÀ-Ú][a-zà-úç]{1,14}\.?)\s+(\d{1,3})(?:\s*[,:]\s*(\d{1,3})[a-z]?(?:\s*[-–]\s*(\d{1,3})[a-z]?)?)?"
)
_ECO = re.compile(
    r"(ignore\s+(as|todas|all|previous)|system\s*prompt|<\s*/?\s*(dados|mensagem|revisao|evangelho)\b|instru[cç][oõ]es (do|de) sistema|PERMITIDAS)",
    re.IGNORECASE,
)
_HTML = re.compile(r"<\s*/?\s*(script|iframe|style|img|a|div|span|b|i|u|p|br)\b", re.IGNORECASE)

# Limites (palavras), plano §8.5.4
LIMITES: dict[str, tuple[int, int]] = {
    "olhar_sobre_o_dia": (40, 90),
    "reflexao": (180, 380),
    "oracao": (30, 90),
}
TOLERANCIA = 0.15


@dataclass(frozen=True, slots=True)
class Checagem:
    id: str
    ok: bool
    motivo: str = ""


@dataclass(slots=True)
class RefPermitida:
    livro: str
    capitulo: int
    vers_ini: int | None = None
    vers_fim: int | None = None
    cap_fim: int | None = None

    def cobre(self, livro: str, cap: int, v1: int | None, v2: int | None) -> bool:
        if livro != self.livro:
            return False
        c_fim = self.cap_fim or self.capitulo
        if not (self.capitulo <= cap <= c_fim):
            return False
        if v1 is None or self.vers_ini is None:
            return True
        lo = self.vers_ini if cap == self.capitulo else 1
        hi = (
            (self.vers_fim if self.vers_fim is not None else self.vers_ini) if cap == c_fim else 999
        )
        fim = v2 if v2 is not None else v1
        return not (fim < lo - 1 or v1 > hi + 1)


@dataclass(slots=True)
class EntradaVerificacao:
    redacao: Redacao
    permitidas: list[RefPermitida]
    textos_permitidos: list[str]  # versículos das passagens e textos das leituras do dia
    urls_permitidas: set[str]
    sensibilidades: set[str]
    perfil: str
    livros_passagens: list[tuple[str, bool]]  # (livro, deuterocanônico)
    rotulos_deutero_presentes: bool = True
    neutralidade: Neutralidade | None = None
    julgamento: Julgamento | None = None
    extras: dict[str, str] = field(default_factory=dict)


def texto_completo(r: Redacao) -> str:
    return "\n".join([r.olhar_sobre_o_dia, r.reflexao, r.ensinamento, r.gesto, r.oracao])


def v1_placeholders(r: Redacao) -> Checagem:
    achados = _MARCADOR.findall(texto_completo(r))
    desconhecidos = sorted({m for m in achados if m not in MARCADORES_VALIDOS})
    if desconhecidos:
        return Checagem("V1", False, f"marcadores desconhecidos: {', '.join(desconhecidos)}")
    n_p1 = achados.count("P1")
    if n_p1 != 1:
        return Checagem(
            "V1", False, f"{{{{P1}}}} deve aparecer exatamente uma vez (apareceu {n_p1})"
        )
    for m in ("C1", "C2"):
        if achados.count(m) > 1:
            return Checagem("V1", False, f"{{{{{m}}}}} duplicado")
    return Checagem("V1", True)


def extrair_referencias(texto: str) -> list[tuple[str, int, int | None, int | None, str]]:
    """(livro USFM, cap, v1, v2, trecho) para cada referência bíblica reconhecível no texto."""
    saida = []
    for m in _REF.finditer(_MARCADOR.sub(" ", texto)):
        lv = resolver(m.group(1).rstrip("."))
        if lv is None:
            continue
        nome = m.group(1).rstrip(".")
        # palavras comuns que coincidem com siglas ("Os 3 filhos", "Am 2" é raro) exigem vírgula
        if (
            nome.lower() in {"os", "am", "is", "at", "ex", "ab", "ag", "na", "ne", "jo", "sl"}
            and m.group(3) is None
        ):
            continue
        saida.append(
            (
                lv.codigo,
                int(m.group(2)),
                int(m.group(3)) if m.group(3) else None,
                int(m.group(4)) if m.group(4) else None,
                m.group(0),
            )
        )
    return saida


def v2_referencias(r: Redacao, permitidas: Sequence[RefPermitida]) -> Checagem:
    fora = [
        trecho
        for livro, cap, v1, v2, trecho in extrair_referencias(texto_completo(r))
        if not any(p.cobre(livro, cap, v1, v2) for p in permitidas)
    ]
    if fora:
        return Checagem(
            "V2", False, f"referências fora do conjunto permitido: {'; '.join(fora[:5])}"
        )
    return Checagem("V2", True)


def v3_fidelidade(r: Redacao, textos_permitidos: Sequence[str]) -> Checagem:
    base = [chave(t) for t in textos_permitidos if t]
    for m in _ASPAS.finditer(texto_completo(r)):
        citado = m.group(1)
        if contar_palavras(citado) < 6:
            continue
        k = chave(citado)
        if not any(fuzz.partial_ratio(k, t) >= 95 for t in base):
            return Checagem("V3", False, f"citação sem correspondência na base: “{citado[:80]}”")
    return Checagem("V3", True)


def _dentro(n: int, lo: int, hi: int) -> bool:
    return lo * (1 - TOLERANCIA) <= n <= hi * (1 + TOLERANCIA)


def v4_comprimentos(r: Redacao) -> Checagem:
    problemas = []
    for campo, (lo, hi) in LIMITES.items():
        n = contar_palavras(_MARCADOR.sub(" ", getattr(r, campo)))
        if not _dentro(n, lo, hi):
            problemas.append(f"{campo}: {n} palavras (esperado {lo}–{hi})")
    frases = [f for f in re.split(r"(?<=[.!?])\s+", r.ensinamento.strip()) if f]
    if not 1 <= len(frases) <= 2:
        problemas.append(f"ensinamento: {len(frases)} frases (esperado 1–2)")
    if not r.gesto.strip() or contar_palavras(r.gesto) > 45:
        problemas.append("gesto: deve ser uma única ação concreta e curta")
    if problemas:
        return Checagem("V4", False, "; ".join(problemas))
    return Checagem("V4", True)


def _contem(texto_chave: str, termos: Iterable[str]) -> list[str]:
    t = f" {texto_chave} "
    return [x for x in termos if x and f" {x} " in t]


def mencoes_politicas(texto: str, neu: Neutralidade) -> list[str]:
    """Termos partidários, partidos e nomes vigiados presentes no texto. Usado onde não há
    juiz (ex.: rótulos de temas exibidos na Palavra da Semana)."""
    achados = _contem(chave(texto), neu.termos_partidarios)
    achados += [
        x
        for x in (*neu.partidos, *neu.nomes_vigiados)
        if re.search(rf"(?<![\w]){re.escape(x)}(?![\w])", texto)
    ]
    return achados


def v5_neutralidade(r: Redacao, neu: Neutralidade | None, julg: Julgamento | None) -> Checagem:
    t = chave(texto_completo(r))
    if neu is not None:
        termos = _contem(t, neu.termos_partidarios)
        if termos:
            return Checagem("V5", False, f"termos partidários: {', '.join(termos)}")
        partidos = [
            p
            for p in neu.partidos
            if re.search(rf"(?<![\w]){re.escape(p)}(?![\w])", texto_completo(r))
        ]
        nomes = [
            n
            for n in neu.nomes_vigiados
            if re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", texto_completo(r))
        ]
        if (partidos or nomes) and julg is None:
            return Checagem(
                "V5", False, f"menção política sem revisão do juiz: {', '.join(partidos + nomes)}"
            )
    if julg is not None and julg.partidario:
        return Checagem(
            "V5", False, "juiz: tomada de posição partidária — " + "; ".join(julg.motivos[:2])
        )
    return Checagem("V5", True)


def v6_sensibilidade(
    r: Redacao, sensibilidades: set[str], neu: Neutralidade | None, julg: Julgamento | None
) -> Checagem:
    texto = texto_completo(r)
    if "suicidio" in sensibilidades and chave(LINHA_CVV) not in chave(texto):
        return Checagem("V6", False, "tema suicídio sem a linha do CVV (188, cvv.org.br)")
    if neu is not None:
        t = chave(texto)
        for grupo in ("castigo_divino", "profecia", "promessa_indevida"):
            achados = _contem(t, neu.proibidas.get(grupo, ()))
            if achados:
                return Checagem("V6", False, f"expressão proibida ({grupo}): {', '.join(achados)}")
    if julg is not None:
        if julg.castigo_ou_profecia:
            return Checagem("V6", False, "juiz: castigo divino ou leitura profética")
        if julg.exposicao_vitimas:
            return Checagem("V6", False, "juiz: exposição de vítimas ou detalhes gráficos")
        if julg.tom_condenatorio:
            return Checagem("V6", False, "juiz: tom condenatório")
    return Checagem("V6", True)


def v7_perfil(perfil: str, livros: Sequence[tuple[str, bool]], rotulos_presentes: bool) -> Checagem:
    if perfil == "evangelico" and any(deut for _, deut in livros):
        return Checagem("V7", False, "deuterocanônico no perfil evangélico")
    if perfil == "ecumenico" and any(deut for _, deut in livros) and not rotulos_presentes:
        return Checagem("V7", False, "deuterocanônico sem rótulo no perfil ecumênico")
    return Checagem("V7", True)


def v8_saida(r: Redacao, urls_permitidas: set[str]) -> Checagem:
    texto = texto_completo(r)
    urls = [u.rstrip(".,;") for u in _URL.findall(texto)]
    estranhas = [
        u for u in urls if u not in urls_permitidas and not u.startswith("https://cvv.org.br")
    ]
    if estranhas:
        return Checagem("V8", False, f"URL fora das notícias coletadas: {estranhas[0][:80]}")
    if _ECO.search(texto):
        return Checagem("V8", False, "instruções ou delimitadores ecoados no texto")
    if _HTML.search(texto):
        return Checagem("V8", False, "HTML no texto")
    if texto.count("**") % 2 or texto.count("`") % 2:
        return Checagem("V8", False, "Markdown malformado")
    return Checagem("V8", True)


def verificar(e: EntradaVerificacao) -> list[Checagem]:
    r = e.redacao
    return [
        v1_placeholders(r),
        v2_referencias(r, e.permitidas),
        v3_fidelidade(r, e.textos_permitidos),
        v4_comprimentos(r),
        v5_neutralidade(r, e.neutralidade, e.julgamento),
        v6_sensibilidade(r, e.sensibilidades, e.neutralidade, e.julgamento),
        v7_perfil(e.perfil, e.livros_passagens, e.rotulos_deutero_presentes),
        v8_saida(r, e.urls_permitidas),
    ]


def aprovado(checagens: Sequence[Checagem]) -> bool:
    return all(c.ok for c in checagens)


def violacoes(checagens: Sequence[Checagem]) -> list[str]:
    return [f"{c.id}: {c.motivo}" for c in checagens if not c.ok]
