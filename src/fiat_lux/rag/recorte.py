"""Recorte (plano §8.4.4): o trecho contíguo de 1 a 5 versículos que maximiza a soma dos
escores por versículo, com penalidade de comprimento. A citação fica enxuta e íntegra."""

from __future__ import annotations

from collections.abc import Sequence

from fiat_lux.rag.embeddings import vetores_textos_curtos


def escores_por_versiculo(textos: Sequence[str], consultas: Sequence[str]) -> list[float]:
    """Similaridade lexical de cada versículo com a melhor consulta (TF-IDF no lote)."""
    if not textos:
        return []
    if not consultas:
        return [1.0] * len(textos)
    m = vetores_textos_curtos([*consultas, *textos])
    q, v = m[: len(consultas)], m[len(consultas) :]
    sims = v @ q.T
    return [float(x) for x in sims.max(axis=1)]


def melhor_trecho(
    escores: Sequence[float], min_vers: int = 1, max_vers: int = 5, penalidade: float = 0.08
) -> tuple[int, int]:
    """Índices [ini, fim) do melhor trecho. Escores normalizados pelo máximo."""
    n = len(escores)
    if n == 0:
        return (0, 0)
    topo = max(escores) or 1.0
    s = [x / topo for x in escores]
    melhor, melhor_valor = (0, min(n, max_vers)), -1e9
    for i in range(n):
        acumulado = 0.0
        for j in range(i, min(n, i + max_vers)):
            acumulado += s[j]
            tamanho = j - i + 1
            if tamanho < min_vers:
                continue
            # média com bônus suave por contexto, menos penalidade por comprimento
            valor = acumulado / tamanho + 0.15 * min(tamanho, 3) / 3 - penalidade * (tamanho - 1)
            if valor > melhor_valor:
                melhor, melhor_valor = (i, j + 1), valor
    return melhor
