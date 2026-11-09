"""Parser e formatador de referências bíblicas no formato litúrgico brasileiro (plano §8.1.5).

Cobre o que aparece de fato na API de liturgia (corpus de 365 dias em `eval/golden`):

    Gn 1, 1-2, 2            Gn 22, 1-2. 9a. 10-13. 15-18     Br 3, 9-15. 32–4, 4
    Is 7, 10-14; 8, 10c     Mt 4,12-23 ou 12-17              1Ts 4,13-18 (Forma longa)
    Sl 62(63)  Sl 18B  Sl 9A(9)  Sl 147(147B)  Sl 70(71); 12(13)  Sl 1Sm 2 (cântico)
    Jd 17.20-25 (livro de um capítulo)   Est 4, 17n. p-r. aa-bb   2Samuel 12,1-7

Gramática (EBNF simplificada):

    referencia := livro trechos ("ou" trechos)? nota?
    trechos    := trecho ( ("." | ";") trecho )*
    trecho     := cap "," faixa | faixa | cap SUFIXO_SALMO? ("(" cap_heb SUFIXO? ")")?
    faixa      := ponto ( "-" ( ponto | cap "," ponto ) )?
    ponto      := NUM PARTE? | PARTE          ; PARTE := [a-z]{1,2}
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from fiat_lux.biblia.catalogo import Livro, por_codigo, resolver
from fiat_lux.biblia.versificacao import PARTES_SALMO_VULG

LIVROS_UM_CAPITULO = frozenset({"OBA", "PHM", "2JN", "3JN", "JUD"})


class ReferenciaInvalida(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Intervalo:
    livro: str
    cap_ini: int
    vers_ini: int | None = None  # None = capítulo inteiro
    parte_ini: str | None = None
    cap_fim: int | None = None
    vers_fim: int | None = None
    parte_fim: str | None = None
    esquema: str = "cnbb-lit"

    @property
    def capitulo_inteiro(self) -> bool:
        return self.vers_ini is None

    @property
    def fim(self) -> tuple[int, int | None]:
        return (
            self.cap_fim or self.cap_ini,
            self.vers_fim if self.vers_fim is not None else self.vers_ini,
        )


@dataclass(frozen=True, slots=True)
class Referencia:
    texto_original: str
    livro: str
    intervalos: tuple[Intervalo, ...]
    nota: str | None = None
    alternativa: Referencia | None = None
    salmo_hebraico: str | None = None  # ex.: "63", "147B"
    cantico: bool = False  # salmo responsorial tirado de outro livro ("Sl 1Sm 2")
    refrao: str | None = None  # referência do refrão: "(R. cf. 7c)" → "cf. 7c"
    avisos: tuple[str, ...] = field(default_factory=tuple)

    @property
    def livro_obj(self) -> Livro:
        return por_codigo(self.livro)


# --------------------------------------------------------------------------- pré-processamento

_TRACOS = re.compile(r"[‐‑‒–—―−]")
_LIXO = re.compile(r"[¬¨•·*†‡§¶]+")
_NOTA = re.compile(r"\s*\(([^()]*[A-Za-zÀ-ÿ]{3,}[^()]*)\)\s*$")
_RE_LIVRO = re.compile(r"^\s*((?:[1-3]\s?)?[A-Za-zÀ-ÖØ-öø-ÿ]+)\.?\s*,?\s*")
_RE_SALMO = re.compile(
    r"^(?P<cap>\d{1,3})(?P<parte>[AaBb])?\s*(?:\(\s*(?P<heb>\d{1,3})(?P<hparte>[AaBb])?\s*\)?)?\s*(?P<resto>.*)$"
)
_RE_SALMO_BARRA = re.compile(r"^\(\s*(\d{1,3})\s*/\s*(\d{1,3})\s*\)\s*$")
_RE_TYPO_PAREN = re.compile(r"\((\d{1,2})\)(\d)\b")
_RE_PONTO = re.compile(r"^\s*(\d{1,3})?\s*([a-z]{1,4})?\s*$")


_RE_REFRAO = re.compile(r"\(\s*R\b\.?")
_RE_FORMA = re.compile(
    r"^\s*(?:ou\s+)?((?:forma|mais)\s+(?:breve|longa|longo))\s*:?\s*", re.IGNORECASE
)
_RE_CANTICO = re.compile(r"^\s*C[aâ]nt(?:ico)?\.?\s*:\s*", re.IGNORECASE)


def _cortar_refrao(t: str) -> tuple[str, str | None]:
    """Remove a referência do refrão do salmo, que vem no fim: "(R. cf. Sl 68(69),33)"."""
    achados = list(_RE_REFRAO.finditer(t))
    if not achados:
        return t, None
    i = achados[0].start()
    interno = t[i + 1 :].strip()
    if interno.endswith(")"):
        interno = interno[:-1]
    interno = re.sub(r"^R\b\.?\s*", "", interno).strip()
    return t[:i].strip(), interno or None


def _normalizar_corpo(corpo: str) -> str:
    """Corrige separadores e erros recorrentes da fonte antes da análise dos trechos."""
    c = re.sub(r"(?<=\d)O", "0", corpo)  # "1O" → "10"
    c = re.sub(r"\s*\+\s*", ".", c)  # "1 + 5"
    c = re.sub(r"(?<=[\da-z])\s+e\s+(?=\d)", ".", c)  # "3 e 4bc"
    c = re.sub(r"(?<=\d)e(?=\d)", ".", c)  # "3e10ac"
    c = re.sub(r"\s*([,.;\-])\s*", r"\1", c)
    c = re.sub(r"(?<=[\da-z])\s+(?=\d)", ".", c)  # "6-7 8abcd"
    c = re.sub(r"-\.", ".", c)  # "2-.3a"
    c = re.sub(r"\.{2,}", ".", c)
    return c.strip(" .")


def _limpar(texto: str) -> tuple[str, list[str]]:
    avisos: list[str] = []
    t = _TRACOS.sub("-", texto)
    if _LIXO.search(t):
        avisos.append("caracteres espúrios removidos")
        t = _LIXO.sub("", t)
    t = re.sub(r"\s+", " ", t).strip().rstrip(".;,")
    return t, avisos


def _ponto(token: str) -> tuple[int | None, str | None]:
    m = _RE_PONTO.match(token)
    if not m or (m.group(1) is None and m.group(2) is None):
        raise ReferenciaInvalida(f"ponto inválido: {token!r}")
    return (int(m.group(1)) if m.group(1) else None), m.group(2)


# --------------------------------------------------------------------------- núcleo


def _parse_trechos(
    livro: str, corpo: str, esquema: str, cap_atual: int | None = None
) -> tuple[list[Intervalo], int | None]:
    """Analisa o corpo após o livro. Devolve intervalos e o último capítulo corrente."""
    intervalos: list[Intervalo] = []
    corpo = _normalizar_corpo(corpo)
    um_capitulo = livro in LIVROS_UM_CAPITULO
    if um_capitulo and "," not in corpo:
        cap_atual = 1
    vers_atual: int | None = None
    # separadores: ";" sempre inicia trecho; "." também, exceto dentro de números
    blocos = [b.strip() for b in re.split(r";", corpo) if b.strip()]
    for bloco in blocos:
        segmentos = [s.strip() for s in bloco.split(".") if s.strip()]
        for seg in segmentos:
            if "," in seg and not re.match(r"^\s*\d+[a-z]{0,4}\s*-\s*\d+\s*,", seg):
                cap_txt, resto = seg.split(",", 1)
                cap_txt = cap_txt.strip()
                if not cap_txt.isdigit():
                    raise ReferenciaInvalida(f"capítulo inválido: {cap_txt!r}")
                cap_atual = int(cap_txt)
                seg = resto.strip()
                if not seg:
                    intervalos.append(Intervalo(livro, cap_atual, esquema=esquema))
                    continue
            elif cap_atual is None:
                # sem vírgula: capítulo inteiro ou faixa de capítulos ("Dn 3", "Gn 1-2")
                m = re.fullmatch(r"(\d{1,3})(?:\s*-\s*(\d{1,3}))?", seg)
                if not m:
                    raise ReferenciaInvalida(f"trecho sem capítulo: {seg!r}")
                c1 = int(m.group(1))
                c2 = int(m.group(2)) if m.group(2) else None
                intervalos.append(Intervalo(livro, c1, cap_fim=c2, esquema=esquema))
                cap_atual = c2 or c1
                continue
            # faixa dentro do capítulo corrente (fim pode trocar de capítulo: "30-19,3")
            if "-" in seg:
                ini_txt, fim_txt = (x.strip() for x in seg.split("-", 1))
                if "-" in fim_txt and "," not in fim_txt:  # "1a-2-3ab" → "1a-3ab"
                    fim_txt = fim_txt.split("-")[-1].strip()
                if not fim_txt:
                    fim_txt = None
            else:
                ini_txt, fim_txt = seg, None
            v1, p1 = _ponto(ini_txt)
            if v1 is None:
                v1 = vers_atual
                if v1 is None:
                    raise ReferenciaInvalida(f"parte sem versículo: {seg!r}")
            cap_fim = None
            v2: int | None = None
            p2: str | None = None
            if fim_txt is not None:
                if "," in fim_txt:
                    c2_txt, v2_txt = (x.strip() for x in fim_txt.split(",", 1))
                    cap_fim = int(c2_txt)
                    v2, p2 = _ponto(v2_txt)
                else:
                    v2, p2 = _ponto(fim_txt)
                    if v2 is None:
                        v2 = v1
            assert cap_atual is not None
            intervalos.append(
                Intervalo(
                    livro,
                    cap_atual,
                    v1,
                    p1,
                    cap_fim if cap_fim and cap_fim != cap_atual else None,
                    v2 if fim_txt is not None else None,
                    p2 if fim_txt is not None else None,
                    esquema,
                )
            )
            if cap_fim:
                cap_atual = cap_fim
            vers_atual = v2 if v2 is not None else v1
    return intervalos, cap_atual


def _parse_salmos(corpo: str, esquema: str) -> tuple[list[Intervalo], str | None, list[str]]:
    avisos: list[str] = []
    corpo = corpo.strip()
    mb = _RE_SALMO_BARRA.match(corpo)
    if mb:
        a, b = int(mb.group(1)), int(mb.group(2))
        lit, heb_num = (min(a, b), max(a, b)) if abs(a - b) <= 1 else (b, a)
        avisos.append("formato (a/b) interpretado como hebraico/litúrgico")
        return [Intervalo("PSA", lit, esquema=esquema)], str(heb_num), avisos
    corrigido = _RE_TYPO_PAREN.sub(r"(\1\2)", corpo)
    if corrigido != corpo:
        avisos.append(f"numeração corrigida: {corpo!r} → {corrigido!r}")
        corpo = corrigido
    intervalos: list[Intervalo] = []
    heb_primeiro: str | None = None
    for pedaco in [p.strip() for p in corpo.split(";") if p.strip()]:
        m = _RE_SALMO.match(pedaco)
        if not m:
            raise ReferenciaInvalida(f"salmo inválido: {pedaco!r}")
        cap = int(m.group("cap"))
        parte = (m.group("parte") or "").upper() or None
        heb = m.group("heb")
        if heb and heb_primeiro is None:
            heb_primeiro = heb + (m.group("hparte") or "").upper()
        if "(" in pedaco and ")" not in pedaco:
            avisos.append("parêntese não fechado")
        resto = m.group("resto").strip().lstrip(",").strip()
        if "," in resto:  # "89,90.91" → vírgula espúria entre versículos do mesmo salmo
            resto = resto.replace(",", ".")
            avisos.append("vírgula entre versículos tratada como ponto")
        if resto:
            sub, _ = _parse_trechos("PSA", f"{cap},{resto}", esquema)
            intervalos.extend(sub)
            continue
        chave_parte = f"{cap}{parte}" if parte else None
        hparte = (m.group("hparte") or "").upper()
        if chave_parte is None and heb and hparte:
            # "Sl 18(19A)": parte indicada no número hebraico
            mapa_heb = {("19", "A"): "18A", ("19", "B"): "18B"}
            chave_parte = mapa_heb.get((heb, hparte))
        if chave_parte and chave_parte in PARTES_SALMO_VULG:
            c, v1, v2 = PARTES_SALMO_VULG[chave_parte]
            intervalos.append(Intervalo("PSA", c, v1, None, None, v2, None, esquema))
        else:
            intervalos.append(Intervalo("PSA", cap, esquema=esquema))
    return intervalos, heb_primeiro, avisos


def _separar_livro(texto: str) -> tuple[Livro, str]:
    m = _RE_LIVRO.match(texto)
    if not m:
        raise ReferenciaInvalida(f"livro não encontrado em {texto!r}")
    candidato = m.group(1)
    lv = resolver(candidato)
    resto = texto[m.end() :]
    if lv is None:
        # nomes compostos ("Cântico dos Cânticos 2,8", "Atos dos Apóstolos 2,1")
        palavras = texto.split()
        for n in range(len(palavras), 1, -1):
            nome = " ".join(palavras[:n])
            if re.search(r"\d", nome.split(" ", 1)[-1] if " " in nome else ""):
                continue
            lv = resolver(nome)
            if lv:
                resto = texto[len(nome) :].lstrip(" ,.")
                break
    if lv is None:
        raise ReferenciaInvalida(f"livro não reconhecido: {candidato!r}")
    return lv, resto


def parse(texto: str, esquema: str = "cnbb-lit", livro_padrao: str | None = None) -> Referencia:
    """Analisa uma referência. Levanta `ReferenciaInvalida` se não for reconhecida.

    `livro_padrao`: livro assumido quando a referência não traz livro (ex.: a forma breve
    "mais breve 10,17-27" listada logo após "Mc 10,17-30").
    """
    if not texto or not texto.strip():
        raise ReferenciaInvalida("referência vazia")
    t, avisos = _limpar(texto)
    t, refrao = _cortar_refrao(t)
    cantico = False
    if _RE_CANTICO.match(t):
        t = _RE_CANTICO.sub("", t)
        cantico = True
    nota = None
    mn = _NOTA.search(t)
    if mn:
        nota = mn.group(1).strip()
        t = t[: mn.start()].strip()
    mf = _RE_FORMA.match(t)
    if mf:
        nota = nota or mf.group(1).strip()
        t = t[mf.end() :].strip()
    partes_ou = re.split(r"\s+ou\s+", t, maxsplit=1)
    principal = partes_ou[0].strip()
    alternativa_txt = partes_ou[1].strip() if len(partes_ou) > 1 else ""
    if re.match(r"^\d", principal) and not re.match(r"^[1-3]\s?[A-Za-zÀ-ÿ]", principal):
        if not livro_padrao:
            raise ReferenciaInvalida(f"referência sem livro: {texto!r}")
        principal = f"{por_codigo(livro_padrao).sigla_pt} {principal}"
    lv, corpo = _separar_livro(principal)
    heb: str | None = None
    if lv.codigo == "PSA" and re.match(r"^(?:[1-3]\s?)?[A-Za-zÀ-ÿ]{2,}", corpo.strip()):
        interna = parse(corpo, esquema)
        return replace(
            interna, texto_original=texto, cantico=True, nota=nota or interna.nota, refrao=refrao
        )
    if lv.codigo == "PSA":
        intervalos, heb, av = _parse_salmos(corpo, esquema)
        avisos += av
    else:
        if not corpo.strip():
            raise ReferenciaInvalida(f"sem capítulo/versículo: {texto!r}")
        intervalos, _ = _parse_trechos(lv.codigo, corpo, esquema)
    alternativa = None
    nota_alt = None
    mfa = _RE_FORMA.match(alternativa_txt) if alternativa_txt else None
    if mfa:
        nota_alt = mfa.group(1).strip()
        alternativa_txt = alternativa_txt[mfa.end() :].strip()
    if alternativa_txt:
        cap_ctx = intervalos[0].cap_ini if intervalos else None
        if re.match(r"^(?:[1-3]\s?)?[A-Za-zÀ-ÿ]{2,}", alternativa_txt):
            alternativa = parse(alternativa_txt, esquema)
            if nota_alt and not alternativa.nota:
                alternativa = replace(alternativa, nota=nota_alt)
        else:
            alt_iv, _ = _parse_trechos(lv.codigo, alternativa_txt, esquema, cap_atual=cap_ctx)
            alternativa = Referencia(alternativa_txt, lv.codigo, tuple(alt_iv), nota=nota_alt)
    if not intervalos:
        raise ReferenciaInvalida(f"nenhum trecho em {texto!r}")
    return Referencia(
        texto_original=texto,
        livro=lv.codigo,
        intervalos=tuple(intervalos),
        nota=nota,
        alternativa=alternativa,
        salmo_hebraico=heb,
        cantico=cantico,
        refrao=refrao,
        avisos=tuple(avisos),
    )


def parse_com_contexto(
    texto: str, anteriores: list[Referencia], esquema: str = "cnbb-lit"
) -> Referencia:
    """Analisa uma referência que pode vir sem livro ("mais breve 10,17-27").

    O livro é o da leitura anterior (mesmo tipo) cujo capítulo coincide; na falta, o da
    primeira leitura da lista. A API às vezes lista conjuntos de ciclos diferentes no mesmo dia.
    """
    try:
        return parse(texto, esquema)
    except ReferenciaInvalida as e:
        if "sem livro" not in str(e) or not anteriores:
            raise
    for ant in anteriores:
        r = tentar_parse(texto, esquema, livro_padrao=ant.livro)
        if r is None:
            continue
        caps_ant = {iv.cap_ini for iv in ant.intervalos}
        if ant.alternativa is not None:
            caps_ant |= {iv.cap_ini for iv in ant.alternativa.intervalos}
        if caps_ant & {iv.cap_ini for iv in r.intervalos}:
            return r
    return parse(texto, esquema, livro_padrao=anteriores[0].livro)


def parse_intervalos(texto: str, esquema: str = "cnbb-lit") -> list[Intervalo]:
    """Interface do plano: `list[Intervalo]` da forma principal."""
    return list(parse(texto, esquema).intervalos)


def tentar_parse(
    texto: str, esquema: str = "cnbb-lit", livro_padrao: str | None = None
) -> Referencia | None:
    try:
        return parse(texto, esquema, livro_padrao)
    except (ReferenciaInvalida, ValueError, KeyError):
        return None


# --------------------------------------------------------------------------- formatação


def _fmt_ponto(v: int | None, p: str | None) -> str:
    return f"{'' if v is None else v}{p or ''}"


def formatar_intervalos(livro: str, intervalos: tuple[Intervalo, ...] | list[Intervalo]) -> str:
    """Forma canônica CNBB compacta: `Gn 22,1-2.9a.10-13; 23,1`."""
    sigla = por_codigo(livro).sigla_pt
    partes: list[str] = []
    cap_corrente: int | None = None
    for iv in intervalos:
        if iv.capitulo_inteiro:
            txt = f"{iv.cap_ini}" + (f"-{iv.cap_fim}" if iv.cap_fim else "")
            partes.append(("; " if partes else "") + txt)
            cap_corrente = None
            continue
        ini = _fmt_ponto(iv.vers_ini, iv.parte_ini)
        if iv.vers_fim is not None or iv.parte_fim:
            if iv.cap_fim and iv.cap_fim != iv.cap_ini:
                fim = f"{iv.cap_fim},{_fmt_ponto(iv.vers_fim, iv.parte_fim)}"
            else:
                fim = _fmt_ponto(iv.vers_fim, iv.parte_fim)
            corpo = f"{ini}-{fim}"
        else:
            corpo = ini
        if cap_corrente == iv.cap_ini:
            partes.append(f".{corpo}")
        else:
            prefixo = "; " if partes else ""
            if livro in LIVROS_UM_CAPITULO and iv.cap_ini == 1 and not partes:
                partes.append(corpo)
            else:
                partes.append(f"{prefixo}{iv.cap_ini},{corpo}")
        cap_corrente = iv.cap_fim if iv.cap_fim else iv.cap_ini
    return f"{sigla} {''.join(partes)}"


def formatar(ref: Referencia | Intervalo | list[Intervalo]) -> str:
    if isinstance(ref, Intervalo):
        return formatar_intervalos(ref.livro, [ref])
    if isinstance(ref, list):
        return formatar_intervalos(ref[0].livro, ref) if ref else ""
    txt = formatar_intervalos(ref.livro, ref.intervalos)
    if ref.alternativa is not None:
        alt = formatar_intervalos(ref.alternativa.livro, ref.alternativa.intervalos)
        txt += f" ou {alt.split(' ', 1)[1] if ref.alternativa.livro == ref.livro else alt}"
    return txt


def normalizar(texto: str) -> str:
    """Reescreve uma referência na forma canônica (idempotente)."""
    return formatar(parse(texto))
