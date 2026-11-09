"""Boosts e diversidade (plano §8.4.3).

    S = 0,55·R + 0,15·A + 0,10·T + 0,10·X + 0,10·Q − P

R rerank (melhor consulta) · A âncora litúrgica (1,0 nas leituras do dia; 0,6 no capítulo do
Evangelho) · T afinidade com o tempo litúrgico · X proximidade no grafo de referências
cruzadas a partir do Evangelho (até 2 saltos) · Q cobertura dos temas · P repetição (1,0 se foi
principal nos últimos 60 dias; 0,5 se complementar nos últimos 30). Depois, MMR (λ = 0,7).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from fiat_lux.rag.busca import Candidato


@dataclass(frozen=True, slots=True)
class Pesos:
    rerank: float = 0.55
    ancora: float = 0.15
    tempo: float = 0.10
    grafo: float = 0.10
    cobertura: float = 0.10


def _norm(valores: list[float]) -> list[float]:
    if not valores:
        return []
    lo, hi = min(valores), max(valores)
    if hi - lo < 1e-9:
        return [0.5 if hi > 0 else 0.0 for _ in valores]
    return [(v - lo) / (hi - lo) for v in valores]


def ancora(
    c: Candidato, refs_leituras: set[str], capitulo_evangelho: tuple[str, int] | None
) -> float:
    if refs_leituras and any(r in refs_leituras for r in c.refs_canonicas):
        return 1.0
    if capitulo_evangelho is not None:
        livro, cap = capitulo_evangelho
        if any(r.split(".")[0] == livro and int(r.split(".")[1]) == cap for r in c.refs_canonicas):
            return 0.6
    return 0.0


def grafo(c: Candidato, proximidade: dict[str, float]) -> float:
    return max((proximidade.get(r, 0.0) for r in c.refs_canonicas), default=0.0)


def cobertura(c: Candidato, consultas_por_tema: dict[str, set[int]]) -> float:
    if not consultas_por_tema:
        return 0.0
    atendidos = sum(1 for qs in consultas_por_tema.values() if qs & c.consultas)
    return atendidos / len(consultas_por_tema)


def repeticao(c: Candidato, principais: set[str], complementares: set[str]) -> float:
    refs = set(c.refs_canonicas)
    if refs & principais:
        return 1.0
    if refs & complementares:
        return 0.5
    return 0.0


def aplicar(
    candidatos: list[Candidato],
    rerank_por_cand: list[float],
    afinidade_tempo: list[float],
    refs_leituras: set[str],
    capitulo_evangelho: tuple[str, int] | None,
    proximidade_grafo: dict[str, float],
    consultas_por_tema: dict[str, set[int]],
    recentes_principais: set[str],
    recentes_complementares: set[str],
    pesos: Pesos | None = None,
) -> None:
    """Preenche `c.escores` (R, A, T, X, Q, P, S) de cada candidato."""
    pesos = pesos or Pesos()
    r_norm = _norm(rerank_por_cand)
    t_norm = _norm(afinidade_tempo)
    for i, c in enumerate(candidatos):
        a = ancora(c, refs_leituras, capitulo_evangelho)
        x = grafo(c, proximidade_grafo)
        q = cobertura(c, consultas_por_tema)
        p = repeticao(c, recentes_principais, recentes_complementares)
        s = (
            pesos.rerank * r_norm[i]
            + pesos.ancora * a
            + pesos.tempo * t_norm[i]
            + pesos.grafo * x
            + pesos.cobertura * q
            - p
        )
        if c.origem == "semente":
            s += 0.02  # desempate a favor das passagens-semente curadas
        c.escores.update(
            {"R": r_norm[i], "A": a, "T": t_norm[i], "X": x, "Q": q, "P": p, "S": round(s, 4)}
        )


def mmr(candidatos: list[Candidato], k: int = 12, lam: float = 0.7) -> list[Candidato]:
    """Maximal Marginal Relevance sobre S, com similaridade de vetores (+0,2 se mesmo livro)."""
    restantes = sorted(candidatos, key=lambda c: -c.escores.get("S", 0.0))
    escolhidos: list[Candidato] = []
    while restantes and len(escolhidos) < k:
        melhor, melhor_valor = None, -1e9
        for c in restantes:
            sim = 0.0
            for e in escolhidos:
                s = 0.0
                if c.vetor is not None and e.vetor is not None:
                    s = float(np.dot(c.vetor, e.vetor))
                if c.livro == e.livro:
                    s += 0.2
                if set(c.versiculo_ids) & set(e.versiculo_ids):
                    s += 1.0  # sobreposição de versículos: quase duplicata
                sim = max(sim, s)
            valor = lam * c.escores.get("S", 0.0) - (1 - lam) * sim
            if valor > melhor_valor:
                melhor, melhor_valor = c, valor
        assert melhor is not None
        escolhidos.append(melhor)
        restantes.remove(melhor)
    return escolhidos


def proximidade_xref(
    vizinhos: Iterable[tuple[str, str | None, int]],
    segundo_salto: dict[str, list[tuple[str, str | None, int]]],
) -> dict[str, float]:
    """Mapa ref → proximidade [0,1] a partir das refs cruzadas do Evangelho (1 salto = votos
    normalizados; 2 saltos = metade)."""
    prox: dict[str, float] = {}
    lista = list(vizinhos)
    maximo = max((v for *_, v in lista), default=0)
    if maximo <= 0:
        return prox

    def expandir(ini: str, fim: str | None) -> list[str]:
        if not fim:
            return [ini]
        livro, c1, v1 = ini.split(".")
        l2, c2, v2 = fim.split(".")
        if livro != l2 or c1 != c2:
            return [ini, fim]
        return [f"{livro}.{c1}.{v}" for v in range(int(v1), int(v2) + 1)]

    for ini, fim, votos in lista:
        for r in expandir(ini, fim):
            prox[r] = max(prox.get(r, 0.0), votos / maximo)
    for origem, segundos in segundo_salto.items():
        base = prox.get(origem, 0.0)
        m2 = max((v for *_, v in segundos), default=0)
        for ini, fim, votos in segundos:
            for r in expandir(ini, fim):
                valor = 0.5 * base * (votos / m2 if m2 else 0)
                prox[r] = max(prox.get(r, 0.0), valor)
    return prox
