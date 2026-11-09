"""Montagem final (plano §8.7 e Apêndice A): placeholders → texto da base, template Jinja."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from fiat_lux.agente.contexto import ContextoDoDia
from fiat_lux.agente.selecao import Escolha
from fiat_lux.biblia.modelos import TRADUCOES
from fiat_lux.llm.esquemas import Redacao
from fiat_lux.rag.busca import Candidato

DIR_TEMPLATES = Path(__file__).resolve().parents[1] / "entrega" / "templates"
_ENV = Environment(
    loader=FileSystemLoader(str(DIR_TEMPLATES)),
    undefined=StrictUndefined,
    trim_blocks=False,
    lstrip_blocks=False,
    keep_trailing_newline=True,
    autoescape=False,
)
MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)
DIAS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)
TEMPOS = {
    "advento": "Advento",
    "natal": "Tempo do Natal",
    "comum": "Tempo Comum",
    "quaresma": "Quaresma",
    "triduo": "Tríduo Pascal",
    "pascoa": "Tempo Pascal",
}
FAIXAS = {"calmo": "calmo", "atencao": "atenção", "tensao": "tensão", "crise": "crise"}


def _compactar(md: str) -> str:
    """No máximo uma linha em branco seguida; termina com uma quebra de linha."""
    return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"


_SOBRESCRITO = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_NUM_VERSICULO = re.compile(r"(?<![\w\d])(\d{1,3})(?=[A-Za-zÀ-ÿ“\"‘'(])")


def formatar_leitura(texto: str | None) -> str | None:
    """Números de versículo colados ao texto da API ("13Estava") viram sobrescritos (¹³Estava)."""
    if not texto:
        return texto
    return _NUM_VERSICULO.sub(lambda m: m.group(1).translate(_SOBRESCRITO), texto)


def data_extenso(d: dt.date) -> str:
    return f"{DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def citacao_inline(c: Candidato, max_palavras: int = 22) -> str:
    """Citação curta dentro da reflexão (o texto completo já aparece em destaque)."""
    texto = c.texto.strip()
    palavras = texto.split()
    if len(palavras) > max_palavras:
        corte = " ".join(palavras[:max_palavras])
        fim_frase = max(corte.rfind(p) for p in (".", ";", ":", "!", "?"))
        corte = corte[: fim_frase + 1] if fim_frase > len(corte) // 2 else corte.rstrip(",;:") + "…"
        texto = corte
    return f"“{texto}” ({c.rotulo()})"


def substituir(texto: str, escolha: Escolha) -> str:
    mapa = {"P1": escolha.principal}
    for i, c in enumerate(escolha.complementares[:2], 1):
        mapa[f"C{i}"] = c
    return re.sub(
        r"\{\{\s*(P1|C1|C2)\s*\}\}",
        lambda m: citacao_inline(mapa[m.group(1)]) if m.group(1) in mapa else "",
        texto,
    )


def _passagem(c: Candidato, rotulo_deutero: str | None) -> dict[str, Any]:
    return {
        "ref": c.rotulo(),
        "traducao": TRADUCOES[c.traducao].sigla,
        "texto": c.texto,
        "rotulo_deutero": rotulo_deutero if (c.deutero and rotulo_deutero) else None,
    }


def atribuicao(traducoes: set[str]) -> str:
    return " · ".join(str(TRADUCOES[t].atribuicao or TRADUCOES[t].nome) for t in sorted(traducoes))


def renderizar_diaria(
    ctx: ContextoDoDia, escolha: Escolha, redacao: Redacao, versao: str, regiao: str = "Ceará"
) -> str:
    lit = ctx.liturgia
    m = ctx.medicoes
    passagens = [escolha.principal, *escolha.complementares]
    noticias_gdelt = False
    return _compactar(
        _ENV.get_template("diaria.md.j2").render(
            data_extenso=data_extenso(ctx.data),
            celebracao=lit.celebracao if lit else "",
            tempo=TEMPOS.get(ctx.tempo, ctx.tempo),
            semana=lit.semana
            if lit and lit.tempo in {"comum", "advento", "quaresma", "pascoa"}
            else None,
            cor=(lit.cor.lower() if lit else ""),
            ciclo_dominical=lit.ciclo_dominical if lit else "",
            ciclo_ferial=lit.ciclo_ferial if lit else "",
            medidor={
                k: {"indice": f"{v.indice:.0f}", "faixa": FAIXAS[v.faixa]} for k, v in m.items()
            }
            if m
            else None,
            calibrando=ctx.calibrando,
            regiao=regiao,
            olhar_sobre_o_dia=substituir(redacao.olhar_sobre_o_dia, escolha),
            links=[{"dominio": d, "url": u} for d, u in ctx.links[:3]],
            evangelho={
                "referencia": ctx.evangelho_ref,
                "texto": formatar_leitura(ctx.evangelho_texto),
            }
            if ctx.evangelho_ref
            else None,
            rotulo_evangelho=ctx.perfil.rotulo_evangelho,
            p1=_passagem(escolha.principal, ctx.perfil.rotulo_deutero),
            reflexao=substituir(redacao.reflexao, escolha),
            ensinamento=substituir(redacao.ensinamento, escolha),
            gesto=substituir(redacao.gesto, escolha),
            oracao=substituir(redacao.oracao, escolha),
            complementares=[
                _passagem(c, ctx.perfil.rotulo_deutero) for c in escolha.complementares[:2]
            ],
            atribuicao=atribuicao({c.traducao for c in passagens}),
            creditos_noticias=(
                "The GDELT Project e fontes indicadas"
                if noticias_gdelt
                else "fontes indicadas (RSS)"
            )
            if ctx.noticias_disponiveis
            else None,
            versao=versao,
        )
    )


def renderizar_fallback(
    ctx: ContextoDoDia, passagem: Candidato | None, motivo: str, oracao: str, versao: str
) -> str:
    lit = ctx.liturgia
    return _compactar(
        _ENV.get_template("fallback.md.j2").render(
            data_extenso=data_extenso(ctx.data),
            celebracao=lit.celebracao if lit else "",
            tempo=TEMPOS.get(ctx.tempo, ctx.tempo),
            cor=(lit.cor.lower() if lit else ""),
            evangelho={
                "referencia": ctx.evangelho_ref,
                "texto": formatar_leitura(ctx.evangelho_texto),
            }
            if ctx.evangelho_ref and ctx.evangelho_texto
            else None,
            rotulo_evangelho=ctx.perfil.rotulo_evangelho,
            passagem=_passagem(passagem, ctx.perfil.rotulo_deutero) if passagem else None,
            atribuicao=atribuicao({passagem.traducao}) if passagem else None,
            oracao=oracao,
            motivo=motivo,
            versao=versao,
        )
    )


def renderizar(template: str, **ctx: Any) -> str:
    """Renderiza um template de `entrega/templates` com o mesmo ambiente da mensagem diária."""
    return _compactar(_ENV.get_template(template).render(**ctx))
