"""Fallback seguro (plano §4.3, princípio 4; §8.5.5): nunca se entrega conteúdo não verificado.

Conteúdo: Evangelho do dia (referência + texto da API) ou, sem liturgia, uma passagem fixa
do tempo litúrgico tirada da base; oração fixa; aviso do que não pôde ser concluído.
A oração fixa abaixo deve ser revisada por um sacerdote ou agente de pastoral (D10).
"""

from __future__ import annotations

from fiat_lux.agente.contexto import ContextoDoDia
from fiat_lux.agente.montagem import renderizar_fallback
from fiat_lux.biblia.referencias import Intervalo
from fiat_lux.biblia.repositorio import Repositorio
from fiat_lux.rag.busca import Buscador, Candidato

ORACAO_FIXA = (
    "Senhor, nosso Deus, tu conheces as alegrias e as dores deste dia. Acolhe as pessoas que sofrem, "
    "fortalece os que trabalham pelo bem e ensina-nos a viver com fé, esperança e caridade. Que a tua "
    "Palavra ilumine os nossos passos e nos faça instrumentos da tua paz. Por Cristo, nosso Senhor. Amém."
)

# Passagem fixa por tempo litúrgico (esquema eng), quando nem o Evangelho do dia está disponível.
PASSAGEM_POR_TEMPO = {
    "advento": ("ISA", 40, 1, 5),
    "natal": ("JHN", 1, 14, 14),
    "comum": ("MAT", 11, 28, 30),
    "quaresma": ("JOL", 2, 12, 13),
    "triduo": ("JHN", 3, 16, 17),
    "pascoa": ("JHN", 20, 19, 21),
}


def passagem_fixa(
    ctx: ContextoDoDia, repo: Repositorio, buscador: Buscador | None
) -> Candidato | None:
    livro, cap, v1, v2 = PASSAGEM_POR_TEMPO.get(ctx.tempo, PASSAGEM_POR_TEMPO["comum"])
    iv = Intervalo(livro, cap, v1, None, None, v2, None, "eng")
    trad = ctx.perfil.traducao
    versos = (
        repo.versiculos_intervalo(trad, iv) if trad == "blivre" else repo.eng_para_nativo(trad, iv)
    )
    if not versos:
        return None
    if buscador is not None:
        return buscador.candidato_de_versiculos(
            [v.id for v in versos], "fallback", f"f:{livro}.{cap}.{v1}"
        )
    return Candidato(
        id=f"f:{livro}.{cap}.{v1}",
        traducao=trad,
        livro=versos[0].livro,
        versiculo_ids=[v.id for v in versos],
        refs_canonicas=[v.ref_canonica for v in versos if v.ref_canonica],
        texto=" ".join(v.texto for v in versos),
        textos=[v.texto for v in versos],
        caps_vers=[(v.capitulo, v.versiculo) for v in versos],
        origem="fallback",
    )


def gerar(
    ctx: ContextoDoDia,
    motivo: str,
    repo: Repositorio | None,
    buscador: Buscador | None,
    versao: str,
) -> str:
    passagem = None
    if not (ctx.evangelho_ref and ctx.evangelho_texto) and repo is not None:
        passagem = passagem_fixa(ctx, repo, buscador)
    return renderizar_fallback(ctx, passagem, motivo, ORACAO_FIXA, versao)
