"""Palavra da Semana (plano §8.6): roda no sábado à tarde, preparando o domingo."""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Any

from fiat_lux.agente import contexto as mod_contexto
from fiat_lux.agente import fallback as mod_fallback
from fiat_lux.agente import semanal as pecas
from fiat_lux.agente.montagem import (
    FAIXAS,
    TEMPOS,
    atribuicao,
    data_extenso,
    renderizar,
    substituir,
)
from fiat_lux.agente.verificacao import mencoes_politicas
from fiat_lux.biblia.modelos import TRADUCOES
from fiat_lux.biblia.repositorio import Repositorio
from fiat_lux.config import Settings, obter_settings
from fiat_lux.estado import Estado
from fiat_lux.liturgia.cliente_api import ClienteLiturgia
from fiat_lux.liturgia.modelos import DiaLiturgico
from fiat_lux.liturgia.servico import ServicoLiturgia
from fiat_lux.llm.cliente import Contabilidade, ErroLLM, Pedido, chamar, motivo_curto
from fiat_lux.llm.esquemas import ExtrasSemana
from fiat_lux.llm.offline import embutir
from fiat_lux.llm.prompts import carregar
from fiat_lux.noticias.classificacao import sanear
from fiat_lux.orquestracao.diaria import (
    ResultadoDiaria,
    aviso_de_falha,
    cliente_llm,
    entregar,
    fechar_recursos,
    registrar_bloqueio,
)
from fiat_lux.orquestracao.nucleo import Rastreio, Recursos, VerificacaoReprovada, gerar_palavra
from fiat_lux.pastoral import Neutralidade, Perfil, neutralidade, taxonomia, tempos_liturgicos
from fiat_lux.pastoral import perfil as obter_perfil
from fiat_lux.rag.busca import Buscador
from fiat_lux.rag.recuperacao import EntradaRecuperacao, Recuperador, ancora_do_dia
from fiat_lux.rag.rerank import criar_reranker

DIAS_CURTOS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
FRASE_PADRAO = "Uma semana de trabalho e de esperança, que entregamos nas mãos de Deus."


def escolher_leitura(
    dia: DiaLiturgico,
    rt: pecas.TemaRecorrente | None,
    perfil: Perfil,
    recursos: Recursos,
    recuperador: Recuperador,
    usados: set[int],
    neu: Neutralidade,
) -> dict[str, Any] | None:
    """Uma passagem para o dia, ligada ao Evangelho daquele dia e a um tema da semana (plano
    §8.6, item 5): a perícope inteira, fora do próprio Evangelho e sem repetir versículos."""
    anc = ancora_do_dia(dia, recursos.vrs, recursos.repo)
    rotulo = pecas.rotulo_publico(rt, neu) if rt else None
    if rt is not None:
        cat = taxonomia().get(rt.tema.categoria)
        consultas = [rotulo or "", *(cat.temas[:2] if cat else ())]
        categorias = [rt.tema.categoria]
    else:
        consultas = list(tempos_liturgicos().get(dia.tempo, ("Palavra de Deus para o dia",))[:3])
        categorias = []
    consultas = [c for c in consultas if c]
    entrada = EntradaRecuperacao(
        consultas,
        categorias[:1] * len(consultas) or ["tempo"] * len(consultas),
        perfil,
        dia.tempo,
        categorias,
        anc,
    )
    evangelho = set(anc.refs_evangelho)
    cands = [
        c
        for c in recuperador.recuperar(entrada)
        if not set(c.versiculo_ids) & usados and not set(c.refs_canonicas) & evangelho
    ]
    if not cands:
        return None
    # As outras leituras do dia (A = 1) já conversam com o Evangelho pelo lecionário.
    melhor = max(cands, key=lambda c: c.escores.get("S", 0) + 0.5 * c.escores.get("A", 0))
    if melhor.id.startswith("p:"):
        completo = recuperador.buscador.candidato(int(melhor.id[2:]))
        if not set(completo.refs_canonicas) & evangelho:
            melhor = completo
    usados |= set(melhor.versiculo_ids)
    ev = dia.evangelho
    return {
        "ref": melhor.rotulo(),
        "traducao": TRADUCOES[melhor.traducao].sigla,
        "evangelho": ev.referencia if ev else None,
        "tema": rotulo,
    }


@dataclass(slots=True)
class OpcoesSemanal:
    data: dt.date
    perfil: str = "catolico"
    dry_run: bool = False
    sem_envio: bool = False
    provedor_llm: str | None = None
    usar_rerank: bool | None = None


def sabado_da_semana(semana_iso: str) -> dt.date:
    """'2026-W46' → sábado dessa semana ISO."""
    ano, num = semana_iso.upper().split("-W")
    return dt.date.fromisocalendar(int(ano), int(num), 6)


def _sabado(d: dt.date) -> dt.date:
    return d + dt.timedelta(days=(5 - d.weekday()) % 7)


def executar(
    op: OpcoesSemanal, s: Settings | None = None, estado: Estado | None = None
) -> ResultadoDiaria:
    s = s or obter_settings()
    estado = estado or Estado.abrir()
    sabado = _sabado(op.data)
    domingo = sabado + dt.timedelta(days=1)
    res = ResultadoDiaria()
    eid = estado.iniciar_execucao("semanal", sabado)
    inicio = time.perf_counter()
    contab = Contabilidade(
        estado.custo_mes(sabado.year, sabado.month), s.custos.custo_max_mensal_usd
    )
    perfil = obter_perfil(op.perfil)
    llm = cliente_llm(s, op.provedor_llm, op.dry_run, res.avisos)
    res.llm = llm.nome
    rast = Rastreio()
    repo = buscador = None
    ctx = None
    foto = None
    try:
        rast.etapa = "liturgia"
        svc = ServicoLiturgia(
            estado,
            ClienteLiturgia(s.liturgia.url_base, s.liturgia.timeout_s, s.liturgia.tentativas),
        )
        try:
            svc.prefetch(7)
        except Exception as e:
            res.avisos.append(f"prefetch falhou: {e}")
        dia_dom = svc.obter(domingo)
        rast.etapa = "indice"
        repo = Repositorio.abrir(s.caminhos.biblia_db)
        buscador = Buscador.abrir(s.caminhos.biblia_db)

        rast.etapa = "semana"
        recorrentes = pecas.temas_recorrentes(estado, sabado)
        series = pecas.medicoes_semana(estado, sabado)
        ano, num, _ = sabado.isocalendar()
        if series:
            # dry-run não escreve em saidas/: o PNG fica ao lado do Markdown de teste
            pasta = (
                s.caminhos.cache / "dry-run"
                if op.dry_run
                else s.caminhos.saidas / f"{ano:04d}" / "semanas"
            )
            foto = pecas.grafico(
                series,
                pasta / f"{ano:04d}-W{num:02d}.png",
                f"Semana {num:02d}/{ano} — Índice de Tensão",
            )
        ctx = mod_contexto.ContextoDoDia(data=domingo, liturgia=dia_dom, perfil=perfil)
        ev = dia_dom.evangelho
        if ev is not None:
            ctx.evangelho_ref, ctx.evangelho_texto = ev.referencia, ev.texto
        ctx.temas = [t.tema for t in recorrentes]
        ctx.sensibilidades = {t.sensivel for t in ctx.temas if t.sensivel}
        ctx.links = [link for t in ctx.temas for link in t.links][:6]
        ctx.noticias_disponiveis = bool(recorrentes)
        ctx.evangelho_resumo = mod_contexto.resumir_evangelho(
            ctx.evangelho_texto, llm, s.llm.modelo_classificacao, contab
        )

        recursos = Recursos(s, estado, llm, contab, repo, buscador, op.usar_rerank)
        palavra = gerar_palavra(ctx, dia_dom, recursos, rast)
        res.escolha, res.verificacao = palavra.escolha, palavra.checagens

        rast.etapa = "extras"
        try:
            extras = chamar(
                llm,
                Pedido(
                    "semanal",
                    s.llm.modelo_geracao,
                    carregar("semanal").texto,
                    embutir(
                        {
                            "temas": [
                                {"categoria": t.categoria, "rotulo": sanear(t.rotulo)}
                                for t in ctx.temas
                            ],
                            "tendencia": pecas.tendencia(series),
                            "evangelho_ref": ctx.evangelho_ref,
                            "evangelho_resumo": ctx.evangelho_resumo,
                        }
                    ),
                    s.llm.temperatura_redacao,
                    4000,
                ),
                ExtrasSemana,
                contab,
            )
        except ErroLLM as e:
            res.avisos.append(f"extras da semana indisponíveis: {motivo_curto(e)}")
            extras = ExtrasSemana(frase=FRASE_PADRAO, perguntas=[])
        neu = neutralidade()
        if mencoes_politicas(" ".join([extras.frase, *extras.perguntas]), neu):
            res.avisos.append("frase/perguntas da semana citavam política: usado o texto padrão")
            extras = ExtrasSemana(frase=FRASE_PADRAO, perguntas=[])

        rast.etapa = "plano_de_leitura"
        # 7 buscas a mais: o rerank lexical (denso + TF-IDF) mantém o modo semanal dentro do
        # tempo do CI; o cross-encoder fica para a Palavra da Semana.
        rec_plano = Recuperador(buscador, criar_reranker(False, s.rag.modelo_rerank), repo, s.rag)
        plano = []
        usados = {
            v
            for c in [palavra.escolha.principal, *palavra.escolha.complementares]
            for v in c.versiculo_ids
        }
        for i in range(1, 8):
            d = domingo + dt.timedelta(days=i)
            try:  # cache → API (?dia&mes&ano) → calendário local
                dia = svc.obter(d)
            except Exception as e:
                res.avisos.append(f"liturgia de {d} indisponível para o plano: {e}")
                dia = svc.obter(d, usar_rede=False)
            rt = recorrentes[(i - 1) % len(recorrentes)] if recorrentes else None
            item = escolher_leitura(dia, rt, perfil, recursos, rec_plano, usados, neu)
            if item:
                plano.append(
                    {"dia": f"{DIAS_CURTOS[d.weekday()]} {d.day:02d}/{d.month:02d}", **item}
                )

        rast.etapa = "montagem"
        esc = palavra.escolha
        ultimo = {k: v[-1][1] for k, v in series.items() if v}
        res.markdown = renderizar(
            "semanal.md.j2",
            semana=f"{num:02d}/{ano}",
            data_extenso=data_extenso(domingo),
            celebracao=dia_dom.celebracao,
            tempo=TEMPOS.get(dia_dom.tempo, dia_dom.tempo),
            ciclo=dia_dom.ciclo_dominical,
            frase=extras.frase,
            tendencia=pecas.tendencia(series),
            medidor={
                k: {"indice": f"{v:.0f}", "faixa": FAIXAS[_faixa(v)]} for k, v in ultimo.items()
            },
            grafico=foto.name if foto else None,
            temas=[
                {"rotulo": pecas.rotulo_publico(rt, neu), "dias": rt.dias} for rt in recorrentes
            ],
            evangelho={"referencia": ctx.evangelho_ref, "resumo": ctx.evangelho_resumo}
            if ctx.evangelho_ref
            else None,
            p1={
                "ref": esc.principal.rotulo(),
                "traducao": TRADUCOES[esc.principal.traducao].sigla,
                "texto": esc.principal.texto,
            },
            reflexao=substituir(palavra.redacao.reflexao, esc),
            ensinamento=substituir(palavra.redacao.ensinamento, esc),
            gesto=substituir(palavra.redacao.gesto, esc),
            oracao=substituir(palavra.redacao.oracao, esc),
            plano=plano,
            perguntas=extras.perguntas[:3],
            atribuicao=atribuicao({c.traducao for c in [esc.principal, *esc.complementares]}),
            versao=s.geral.versao_pipeline,
        )
        res.status = "rascunho"
    except Exception as ex:
        res.etapa_falha = rast.etapa
        if isinstance(ex, VerificacaoReprovada):
            res.verificacao = ex.checagens
        aviso_de_falha(res, rast.etapa, ex, "semanal_falhou")
        ctx = ctx or mod_contexto.ContextoDoDia(data=domingo, liturgia=None, perfil=perfil)
        try:
            res.markdown = mod_fallback.gerar(
                ctx,
                "Não foi possível preparar a Palavra da Semana completa.",
                repo,
                buscador,
                s.geral.versao_pipeline,
            )
            res.status = "fallback"
        except Exception as e2:
            res.avisos.append(f"fallback falhou: {e2}")
    res.avisos += rast.avisos
    registrar_bloqueio(res, llm)
    res.custo = round(contab.uso.custo_usd, 5)
    entregar(
        sabado, "semanal", perfil.nome, res, contab, s, estado, op.dry_run, op.sem_envio, None, foto
    )
    estado.terminar_execucao(
        eid, res.status, time.perf_counter() - inicio, res.etapa_falha, None, res.custo
    )
    fechar_recursos(repo, buscador)
    return res


def _faixa(v: float) -> str:
    from fiat_lux.noticias.medidor import faixa

    return faixa(v)
