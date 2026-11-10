"""Consultas pastorais (plano §8.5.2): determinísticas + geradas pelo LLM (prompt P2)."""

from __future__ import annotations

from fiat_lux.agente.contexto import ContextoDoDia
from fiat_lux.llm.cliente import (
    Contabilidade,
    ErroLLM,
    ErroPermanente,
    LLMClient,
    Pedido,
    chamar,
    motivo_curto,
)
from fiat_lux.llm.esquemas import Consultas
from fiat_lux.llm.offline import embutir
from fiat_lux.llm.prompts import carregar
from fiat_lux.logs import log
from fiat_lux.noticias.classificacao import sanear
from fiat_lux.pastoral import taxonomia, tempos_liturgicos


def deterministicas(ctx: ContextoDoDia) -> list[tuple[str, str]]:
    """(texto, origem): temas-chave das categorias ativas + descritores do tempo litúrgico."""
    saida: list[tuple[str, str]] = []
    tax = taxonomia()
    for t in ctx.temas:
        cat = tax.get(t.categoria)
        if cat and cat.temas:
            saida.append((" ".join(cat.temas[:2]), cat.codigo))
    descr = tempos_liturgicos().get(ctx.tempo, ())
    if descr:
        saida.append((" ".join(descr[:3]), "tempo"))
    if ctx.evangelho_resumo:
        saida.append((ctx.evangelho_resumo, "evangelho"))
    return saida


def gerar(
    ctx: ContextoDoDia,
    llm: LLMClient | None,
    modelo: str,
    temperatura: float = 0.3,
    contabilidade: Contabilidade | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Devolve (consultas, origens, avisos)."""
    avisos: list[str] = []
    det = deterministicas(ctx)
    # Ordem = prioridade no rerank neural (só as primeiras passam pelo cross-encoder): resumo do
    # Evangelho, depois as consultas em linguagem natural do LLM, por fim as palavras-chave.
    pares = [p for p in det if p[1] == "evangelho"]
    resto = [p for p in det if p[1] != "evangelho"]
    if llm is not None:
        dados = {
            "temas": [
                {"categoria": t.categoria, "rotulo": sanear(t.rotulo), "escopo": t.escopo}
                for t in ctx.temas
            ],
            "tempo": ctx.tempo,
            "descritores": list(tempos_liturgicos().get(ctx.tempo, ())),
            "evangelho_ref": ctx.evangelho_ref,
            "evangelho_resumo": ctx.evangelho_resumo,
        }
        try:
            r = chamar(
                llm,
                Pedido(
                    "consultas",
                    modelo,
                    carregar("consultas").texto,
                    embutir(dados),
                    temperatura,
                    4000,
                ),
                Consultas,
                contabilidade,
            )
            pares += [(c.texto, c.origem) for c in r.consultas[:6]]
        except ErroLLM as e:
            if not isinstance(e, ErroPermanente):  # o permanente já foi registrado pelo cliente
                log().warning("consultas_llm_falhou", erro=str(e))
            avisos.append(f"consultas só determinísticas ({motivo_curto(e)})")
    pares += resto
    vistos: set[str] = set()
    textos, origens = [], []
    for texto, origem in pares:
        k = texto.strip().casefold()
        if not k or k in vistos:
            continue
        vistos.add(k)
        textos.append(texto.strip())
        origens.append(origem)
    return textos[:9], origens[:9], avisos
