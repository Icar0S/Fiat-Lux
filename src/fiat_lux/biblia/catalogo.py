"""Catálogo canônico dos 73 livros (plano §8.1.1).

Cada livro tem código USFM (padrão aberto), nome e sigla CNBB, sigla e nome na fonte
Matos Soares (MS), sigla do arquivo BLIVRE, abreviação OSIS (referências cruzadas do
openbible.info), ordens católica e protestante e grupo.

Regra: os livros da MS são mapeados **por nome**, nunca por posição, porque a ordem de
`listalivros.json` (Macabeus depois de Malaquias) difere da de `biblia.json`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Literal

from fiat_lux.textos import chave, chave_compacta, sem_acentos, slug_ascii

Testamento = Literal["AT", "NT"]
Grupo = Literal[
    "pentateuco",
    "historicos",
    "sapienciais",
    "profetas",
    "evangelhos",
    "atos",
    "cartas",
    "apocalipse",
]


@dataclass(frozen=True, slots=True)
class Livro:
    codigo: str
    nome_pt: str
    sigla_pt: str
    sigla_ms: str
    nome_ms: str
    sigla_blivre: str | None
    osis: str
    grupo: Grupo
    deuterocanonico: bool
    aliases: tuple[str, ...]
    ordem_catolica: int
    ordem_protestante: int | None
    testamento: Testamento

    @property
    def nome_arquivo(self) -> str:
        return slug_ascii(self.nome_pt)

    @property
    def tipo_pericope(self) -> str:
        """Família de janela de perícope (plano §8.4.1)."""
        if self.codigo == "PSA":
            return "salmos"
        if self.codigo in {"PRO", "SIR", "ECC"}:
            return "proverbial"
        if self.grupo in {"pentateuco", "historicos", "evangelhos", "atos"}:
            return "narrativo"
        return "padrao"

    @property
    def prioritario(self) -> bool:
        """Livros que mais aparecem nas buscas (meta de correção de lacunas, plano §8.1.2)."""
        return self.grupo in {"evangelhos", "sapienciais"} or self.codigo in PROFETAS_MAIORES


PROFETAS_MAIORES = frozenset({"ISA", "JER", "LAM", "BAR", "EZK", "DAN"})

# codigo, nome_pt, sigla CNBB, sigla MS, nome MS (exato), sigla BLIVRE, OSIS, grupo, deutero, aliases
_DADOS: tuple[
    tuple[str, str, str, str, str, str | None, str, Grupo, bool, tuple[str, ...]], ...
] = (
    ("GEN", "Gênesis", "Gn", "Gn", "Gênesis", "gn", "Gen", "pentateuco", False, ("Gên", "Gen")),
    ("EXO", "Êxodo", "Ex", "Ex", "Êxodo", "ex", "Exod", "pentateuco", False, ("Êx", "Exo")),
    ("LEV", "Levítico", "Lv", "Lv", "Levítico", "lv", "Lev", "pentateuco", False, ("Lev",)),
    ("NUM", "Números", "Nm", "Nm", "Números", "nm", "Num", "pentateuco", False, ("Núm", "Num")),
    (
        "DEU",
        "Deuteronômio",
        "Dt",
        "Dt",
        "Deuteronómio",
        "dt",
        "Deut",
        "pentateuco",
        False,
        ("Deut",),
    ),
    ("JOS", "Josué", "Js", "Js", "Livro de Josué", "js", "Josh", "historicos", False, ("Jos",)),
    ("JDG", "Juízes", "Jz", "Ju", "Livro dos Juízes", "jz", "Judg", "historicos", False, ("Juí",)),
    ("RUT", "Rute", "Rt", "Rt", "Livro de Rute", "rt", "Ruth", "historicos", False, ()),
    (
        "1SA",
        "1 Samuel",
        "1Sm",
        "1Sm",
        "Livro Primeiro de Samuel",
        "1sm",
        "1Sam",
        "historicos",
        False,
        ("1Sam",),
    ),
    (
        "2SA",
        "2 Samuel",
        "2Sm",
        "2Sm",
        "Livro Segundo de Samuel",
        "2sm",
        "2Sam",
        "historicos",
        False,
        ("2Sam",),
    ),
    (
        "1KI",
        "1 Reis",
        "1Rs",
        "1Rs",
        "Livro Primeiro dos Reis",
        "1rs",
        "1Kgs",
        "historicos",
        False,
        (),
    ),
    (
        "2KI",
        "2 Reis",
        "2Rs",
        "2Rs",
        "Livro Segundo dos Reis",
        "2rs",
        "2Kgs",
        "historicos",
        False,
        (),
    ),
    (
        "1CH",
        "1 Crônicas",
        "1Cr",
        "1Pa",
        "Livro Primeiro das Crónicas",
        "1cr",
        "1Chr",
        "historicos",
        False,
        ("1Crôn", "1 Paralipômenos", "1Par"),
    ),
    (
        "2CH",
        "2 Crônicas",
        "2Cr",
        "2Pa",
        "Livro Segundo das Crónicas",
        "2cr",
        "2Chr",
        "historicos",
        False,
        ("2Crôn", "2 Paralipômenos", "2Par"),
    ),
    ("EZR", "Esdras", "Esd", "Esd", "Livro de Esdras", "ed", "Ezra", "historicos", False, ()),
    ("NEH", "Neemias", "Ne", "Ne", "Livro de Neemias", "ne", "Neh", "historicos", False, ("Nee",)),
    ("TOB", "Tobias", "Tb", "Tob", "Livro de Tobias", None, "Tob", "historicos", True, ()),
    (
        "JDT",
        "Judite",
        "Jt",
        "Jdi",
        "Livro de Judit",
        None,
        "Jdt",
        "historicos",
        True,
        ("Jdt", "Judit"),
    ),
    ("EST", "Ester", "Est", "Est", "Livro de Ester", "et", "Esth", "historicos", False, ()),
    (
        "1MA",
        "1 Macabeus",
        "1Mc",
        "1Ma",
        "Livro Primeiro dos Macabeus",
        None,
        "1Macc",
        "historicos",
        True,
        ("1Mac",),
    ),
    (
        "2MA",
        "2 Macabeus",
        "2Mc",
        "2Ma",
        "Livro Segundo dos Macabeus",
        None,
        "2Macc",
        "historicos",
        True,
        ("2Mac",),
    ),
    ("JOB", "Jó", "Jó", "Job", "Livro de Job (Jó)", "job", "Job", "sapienciais", False, ("Job",)),
    (
        "PSA",
        "Salmos",
        "Sl",
        "Ps",
        "Salmos",
        "sl",
        "Ps",
        "sapienciais",
        False,
        ("Sal", "Salmo", "Slm"),
    ),
    (
        "PRO",
        "Provérbios",
        "Pr",
        "Pv",
        "Livro dos Provérbios",
        "pv",
        "Prov",
        "sapienciais",
        False,
        ("Prov",),
    ),
    (
        "ECC",
        "Eclesiastes",
        "Ecl",
        "Ees",
        "Livro do Eclesiaste",
        "ec",
        "Eccl",
        "sapienciais",
        False,
        ("Ecle", "Coélet", "Qohelet", "Eclesiaste"),
    ),
    (
        "SNG",
        "Cântico dos Cânticos",
        "Ct",
        "Cc",
        "Cânticos dos Cânticos",
        "ct",
        "Song",
        "sapienciais",
        False,
        ("Cânt", "Cantares", "Cânticos"),
    ),
    (
        "WIS",
        "Sabedoria",
        "Sb",
        "Sa",
        "Livro da Sabedoria",
        None,
        "Wis",
        "sapienciais",
        True,
        ("Sab",),
    ),
    (
        "SIR",
        "Eclesiástico",
        "Eclo",
        "Eus",
        "Eclesiástico",
        None,
        "Sir",
        "sapienciais",
        True,
        ("Sir", "Sirácida", "Ben Sirá"),
    ),
    ("ISA", "Isaías", "Is", "Is", "Profecia de Isaías", "is", "Isa", "profetas", False, ("Isa",)),
    (
        "JER",
        "Jeremias",
        "Jr",
        "Je",
        "Profecia de Jeremias",
        "jr",
        "Jer",
        "profetas",
        False,
        ("Jer",),
    ),
    (
        "LAM",
        "Lamentações",
        "Lm",
        "Lm",
        "Trenos ou Lamentações de Jeremias",
        "lm",
        "Lam",
        "profetas",
        False,
        ("Lam", "Trenos"),
    ),
    (
        "BAR",
        "Baruc",
        "Br",
        "Ba",
        "Profecia de Baruch",
        None,
        "Bar",
        "profetas",
        True,
        ("Bar", "Baruch", "Baruque"),
    ),
    (
        "EZK",
        "Ezequiel",
        "Ez",
        "Ez",
        "Profecia de Ezequiel",
        "ez",
        "Ezek",
        "profetas",
        False,
        ("Ezeq",),
    ),
    ("DAN", "Daniel", "Dn", "Dn", "Profecia de Daniel", "dn", "Dan", "profetas", False, ("Dan",)),
    ("HOS", "Oseias", "Os", "Os", "Oseias", "os", "Hos", "profetas", False, ("Oséias",)),
    ("JOL", "Joel", "Jl", "Jl", "Profecia de Joel", "jl", "Joel", "profetas", False, ()),
    ("AMO", "Amós", "Am", "Am", "Profecia de Amós", "am", "Amos", "profetas", False, ()),
    (
        "OBA",
        "Abdias",
        "Ab",
        "Ab",
        "Profecia de Abdias",
        "ob",
        "Obad",
        "profetas",
        False,
        ("Abd", "Ob", "Obadias"),
    ),
    ("JON", "Jonas", "Jn", "Jn", "Profecia de Jonas", "jn", "Jonah", "profetas", False, ("Jon",)),
    (
        "MIC",
        "Miqueias",
        "Mq",
        "Mic",
        "Profecia de Miqueias",
        "mq",
        "Mic",
        "profetas",
        False,
        ("Miq", "Miquéias"),
    ),
    ("NAM", "Naum", "Na", "Na", "Profecia de Naum", "na", "Nah", "profetas", False, ()),
    (
        "HAB",
        "Habacuc",
        "Hab",
        "Hc",
        "Profecia de Habucuc",
        "hc",
        "Hab",
        "profetas",
        False,
        ("Habacuque", "Habucuc"),
    ),
    (
        "ZEP",
        "Sofonias",
        "Sf",
        "So",
        "Profecia de Sofonias",
        "sf",
        "Zeph",
        "profetas",
        False,
        ("Sof",),
    ),
    ("HAG", "Ageu", "Ag", "Ag", "Profecia de Ageu", "ag", "Hag", "profetas", False, ()),
    (
        "ZEC",
        "Zacarias",
        "Zc",
        "Zc",
        "Profecia de Zacarias",
        "zc",
        "Zech",
        "profetas",
        False,
        ("Zac",),
    ),
    (
        "MAL",
        "Malaquias",
        "Ml",
        "Ml",
        "Profecia de Malaquias",
        "ml",
        "Mal",
        "profetas",
        False,
        ("Mal",),
    ),
    (
        "MAT",
        "Mateus",
        "Mt",
        "Mt",
        "Evangelho segundo S. Mateus",
        "mt",
        "Matt",
        "evangelhos",
        False,
        ("Mat",),
    ),
    (
        "MRK",
        "Marcos",
        "Mc",
        "Mc",
        "Evangelho segundo S. Marcos",
        "mc",
        "Mark",
        "evangelhos",
        False,
        ("Mar",),
    ),
    (
        "LUK",
        "Lucas",
        "Lc",
        "Lc",
        "Evangelho segundo S. Lucas",
        "lc",
        "Luke",
        "evangelhos",
        False,
        ("Luc",),
    ),
    ("JHN", "João", "Jo", "Jo", "Evangelho segundo S. João", "jo", "John", "evangelhos", False, ()),
    (
        "ACT",
        "Atos dos Apóstolos",
        "At",
        "Act",
        "Atos dos Apóstolos",
        "at",
        "Acts",
        "atos",
        False,
        ("Atos", "Actos", "Actos dos Apóstolos"),
    ),
    ("ROM", "Romanos", "Rm", "Rm", "Epístola aos Romanos", "rm", "Rom", "cartas", False, ("Rom",)),
    (
        "1CO",
        "1 Coríntios",
        "1Cor",
        "1Co",
        "Primeira Epístola aos Coríntios",
        "1co",
        "1Cor",
        "cartas",
        False,
        (),
    ),
    (
        "2CO",
        "2 Coríntios",
        "2Cor",
        "2Co",
        "Segunda Epístola aos Coríntios",
        "2co",
        "2Cor",
        "cartas",
        False,
        (),
    ),
    ("GAL", "Gálatas", "Gl", "Gl", "Epístola aos Galatas", "gl", "Gal", "cartas", False, ("Gál",)),
    ("EPH", "Efésios", "Ef", "Ef", "Epístola aos Efésios", "ef", "Eph", "cartas", False, ("Efés",)),
    (
        "PHP",
        "Filipenses",
        "Fl",
        "Fp",
        "Epístola aos Filipenses",
        "fp",
        "Phil",
        "cartas",
        False,
        ("Flp", "Filip"),
    ),
    (
        "COL",
        "Colossenses",
        "Cl",
        "Cl",
        "Epístola aos Colossenses",
        "cl",
        "Col",
        "cartas",
        False,
        ("Col",),
    ),
    (
        "1TH",
        "1 Tessalonicenses",
        "1Ts",
        "1Ts",
        "Primeira Epístola aos Tessalonicenses",
        "1ts",
        "1Thess",
        "cartas",
        False,
        ("1Tes",),
    ),
    (
        "2TH",
        "2 Tessalonicenses",
        "2Ts",
        "2Ts",
        "Segunda Epístola aos Tessalonicenses",
        "2ts",
        "2Thess",
        "cartas",
        False,
        ("2Tes",),
    ),
    (
        "1TI",
        "1 Timóteo",
        "1Tm",
        "1Tm",
        "Primeira Epístola a Timóteo",
        "1tm",
        "1Tim",
        "cartas",
        False,
        ("1Tim",),
    ),
    (
        "2TI",
        "2 Timóteo",
        "2Tm",
        "2Tm",
        "Segunda Epístola a Timóteo",
        "2tm",
        "2Tim",
        "cartas",
        False,
        ("2Tim",),
    ),
    ("TIT", "Tito", "Tt", "Tt", "Epístola a Títo", "tt", "Titus", "cartas", False, ("Tit",)),
    (
        "PHM",
        "Filêmon",
        "Fm",
        "Fm",
        "Epístola a Filémon",
        "fm",
        "Phlm",
        "cartas",
        False,
        ("Filemom", "Flm"),
    ),
    ("HEB", "Hebreus", "Hb", "Hb", "Epístola aos Hebreus", "hb", "Heb", "cartas", False, ("Heb",)),
    ("JAS", "Tiago", "Tg", "Tg", "Epístola de S. Tiago", "tg", "Jas", "cartas", False, ("Tia",)),
    (
        "1PE",
        "1 Pedro",
        "1Pd",
        "1Pe",
        "Primeira Epístola de S. Pedro",
        "1pe",
        "1Pet",
        "cartas",
        False,
        ("1Ped",),
    ),
    (
        "2PE",
        "2 Pedro",
        "2Pd",
        "2Pe",
        "Segunda Epístola de S. Pedro",
        "2pe",
        "2Pet",
        "cartas",
        False,
        ("2Ped",),
    ),
    (
        "1JN",
        "1 João",
        "1Jo",
        "1Jo",
        "Primeira Epístola de S. João",
        "1jo",
        "1John",
        "cartas",
        False,
        (),
    ),
    (
        "2JN",
        "2 João",
        "2Jo",
        "2Jo",
        "Segunda Epístolas de S. João",
        "2jo",
        "2John",
        "cartas",
        False,
        (),
    ),
    (
        "3JN",
        "3 João",
        "3Jo",
        "3Jo",
        "Terceira Epístolas de S. João",
        "3jo",
        "3John",
        "cartas",
        False,
        (),
    ),
    ("JUD", "Judas", "Jd", "Jda", "Epístola de S. Judas", "jd", "Jude", "cartas", False, ()),
    (
        "REV",
        "Apocalipse",
        "Ap",
        "Ap",
        "Apocalipse de S. João",
        "ap",
        "Rev",
        "apocalipse",
        False,
        ("Apoc",),
    ),
)


def _construir() -> tuple[Livro, ...]:
    livros: list[Livro] = []
    ordem_prot = 0
    for i, (cod, nome, sigla, sms, nms, sbl, osis, grupo, deut, aliases) in enumerate(_DADOS, 1):
        if not deut:
            ordem_prot += 1
        livros.append(
            Livro(
                codigo=cod,
                nome_pt=nome,
                sigla_pt=sigla,
                sigla_ms=sms,
                nome_ms=nms,
                sigla_blivre=sbl,
                osis=osis,
                grupo=grupo,
                deuterocanonico=deut,
                aliases=aliases,
                ordem_catolica=i,
                ordem_protestante=None if deut else ordem_prot,
                testamento="AT" if i <= 46 else "NT",
            )
        )
    return tuple(livros)


LIVROS: tuple[Livro, ...] = _construir()
_POR_CODIGO = {lv.codigo: lv for lv in LIVROS}

# Palavras de enchimento em nomes por extenso ("Primeira Epístola de S. João").
_FRASES_ENCHIMENTO = (
    "evangelho segundo",
    "evangelho de",
    "trenos ou",
    "livro",
    "profecia",
    "epistolas",
    "epistola",
    "carta",
    "cartas",
)
_PALAVRAS_ENCHIMENTO = frozenset(
    {"de", "do", "da", "dos", "das", "a", "ao", "aos", "s", "sao", "santo", "sto", "apostolo", "o"}
)
_ORDINAIS = {
    "primeira": "1", "primeiro": "1", "i": "1", "1": "1", "1a": "1", "1o": "1",
    "segunda": "2", "segundo": "2", "ii": "2", "2": "2", "2a": "2", "2o": "2",
    "terceira": "3", "terceiro": "3", "iii": "3", "3": "3", "3a": "3", "3o": "3",
}  # fmt: skip


def _forma_canonica(texto: str) -> str:
    """Normaliza nomes por extenso: ordinais → dígito, sem palavras de enchimento."""
    t = chave(texto)
    # "1 Cor" e "1Cor" convergem; separa dígito colado em letra
    t = re.sub(r"^(\d)([a-z])", r"\1 \2", t)
    for frase in _FRASES_ENCHIMENTO:
        t = re.sub(rf"\b{frase}\b", " ", t)
    tokens = t.split()
    ordinal = ""
    if tokens and tokens[0] in _ORDINAIS:
        ordinal = _ORDINAIS[tokens.pop(0)]
    resto = [p for p in tokens if p not in _PALAVRAS_ENCHIMENTO]
    return ordinal + "".join(resto)


@cache
def _indices() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    exato: dict[str, str] = {}
    sem_acento: dict[str, str] = {}
    canonico: dict[str, str] = {}

    def nomes(lv: Livro) -> list[str]:
        base = [lv.codigo, lv.sigla_pt, lv.sigla_ms, lv.nome_pt, lv.nome_ms, lv.osis, *lv.aliases]
        if lv.sigla_blivre:
            base.append(lv.sigla_blivre)
        return base

    # 1º passe: formas sem acento têm prioridade ("Jo" = João; "Jó" só com acento = Jó)
    for lv in LIVROS:
        for n in nomes(lv):
            k = n.casefold().replace(" ", "").replace(".", "")
            exato.setdefault(k, lv.codigo)
            if sem_acentos(n) == n:
                sem_acento.setdefault(chave_compacta(n), lv.codigo)
    for lv in LIVROS:
        for n in nomes(lv):
            sem_acento.setdefault(chave_compacta(n), lv.codigo)
            canonico.setdefault(_forma_canonica(n), lv.codigo)
    return exato, sem_acento, canonico


def por_codigo(codigo: str) -> Livro:
    try:
        return _POR_CODIGO[codigo.upper()]
    except KeyError as e:
        raise KeyError(f"código USFM desconhecido: {codigo!r}") from e


def resolver(texto: str) -> Livro | None:
    """Resolve sigla, nome, alias ou nome por extenso para um `Livro` (ou `None`).

    Não diferencia maiúsculas, ignora acentos (exceto quando eles desambiguam: Jó × Jo)
    e aceita ordinais por extenso.
    """
    if not texto or not texto.strip():
        return None
    exato, sem_acento, canonico = _indices()
    k = texto.strip().casefold().replace(" ", "").replace(".", "")
    if k in exato:
        return _POR_CODIGO[exato[k]]
    k2 = chave_compacta(texto)
    if k2 in sem_acento:
        return _POR_CODIGO[sem_acento[k2]]
    k3 = _forma_canonica(texto)
    if k3 in canonico:
        return _POR_CODIGO[canonico[k3]]
    return None


def resolver_obrigatorio(texto: str) -> Livro:
    lv = resolver(texto)
    if lv is None:
        raise KeyError(f"livro não reconhecido: {texto!r}")
    return lv


@cache
def _por_nome_ms() -> dict[str, str]:
    return {chave(lv.nome_ms): lv.codigo for lv in LIVROS}


def resolver_nome_ms(nome: str) -> Livro:
    """Mapeia o nome do livro em `biblia.json` (MS) — sempre por nome, nunca por posição."""
    k = chave(nome)
    cod = _por_nome_ms().get(k)
    if cod is None:
        lv = resolver(nome)
        if lv is None:
            raise KeyError(f"livro MS não mapeado: {nome!r}")
        return lv
    return _POR_CODIGO[cod]


@cache
def _por_sigla_blivre() -> dict[str, str]:
    return {lv.sigla_blivre: lv.codigo for lv in LIVROS if lv.sigla_blivre}


def por_sigla_blivre(sigla: str) -> Livro:
    return _POR_CODIGO[_por_sigla_blivre()[sigla.lower()]]


@cache
def _por_osis() -> dict[str, str]:
    return {lv.osis.casefold(): lv.codigo for lv in LIVROS}


def por_osis(osis: str) -> Livro | None:
    cod = _por_osis().get(osis.casefold())
    return _POR_CODIGO[cod] if cod else None


def canone(incluir_deutero: bool) -> tuple[Livro, ...]:
    return tuple(lv for lv in LIVROS if incluir_deutero or not lv.deuterocanonico)


def ordem(codigo: str) -> int:
    return por_codigo(codigo).ordem_catolica
