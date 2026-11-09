"""Recuperação ponta a ponta (plano §4.2, passo 7): ≤ 40 candidatos → 12 após rerank e boosts.

O recorte (1–5 versículos) acontece ANTES da seleção pelo LLM: o modelo vê exatamente o
trecho que será citado, e a citação final é inserida a partir da base (§4.3, princípio 1).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from fiat_lux.biblia.referencias import Referencia, parse_com_contexto
from fiat_lux.biblia.repositorio import Repositorio
from fiat_lux.biblia.versificacao import Versificacao, ref_str
from fiat_lux.config import Rag
from fiat_lux.liturgia.modelos import DiaLiturgico
from fiat_lux.logs import log
from fiat_lux.pastoral import Perfil, taxonomia, tempos_liturgicos
from fiat_lux.rag import boosts
from fiat_lux.rag.busca import Buscador, Candidato
from fiat_lux.rag.recorte import escores_por_versiculo, melhor_trecho
from fiat_lux.rag.rerank import Reranker


def _minmax(v: np.ndarray) -> np.ndarray:
    lo, hi = float(np.min(v)), float(np.max(v))
    return (v - lo) / (hi - lo) if hi - lo > 1e-9 else np.zeros_like(v)


@dataclass(slots=True)
class AncoraLiturgica:
    refs_leituras: set[str] = field(default_factory=set)
    refs_evangelho: list[str] = field(default_factory=list)
    capitulo_evangelho: tuple[str, int] | None = None


def _expandir_eng(ref: Referencia, vrs: Versificacao, repo: Repositorio) -> list[str]:
    saida: list[str] = []
    for iv in ref.intervalos:
        livro = iv.livro
        hebraico = livro != "PSA"
        if iv.capitulo_inteiro:
            caps = range(iv.cap_ini, (iv.cap_fim or iv.cap_ini) + 1)
            pontos = [(c, v) for c in caps for v in range(1, 177)]
        elif iv.cap_fim and iv.cap_fim != iv.cap_ini:
            pontos = [(iv.cap_ini, v) for v in range(iv.vers_ini or 1, 177)] + [
                (iv.cap_fim, v) for v in range(1, (iv.vers_fim or 1) + 1)
            ]
        else:
            fim = iv.vers_fim if iv.vers_fim is not None else iv.vers_ini or 1
            pontos = [(iv.cap_ini, v) for v in range(iv.vers_ini or 1, fim + 1)]
        for c, v in pontos:
            eng = vrs.cnbb_para_eng(livro, c, v, hebraico=hebraico)
            if eng is not None and eng[2] > 0:
                saida.append(ref_str(eng))
    # remove refs que não existem (capítulo inteiro / fim de capítulo estimado)
    existentes = set()
    livros = {r.split(".")[0] for r in saida}
    for lv in livros:
        existentes |= {f"{lv}.{c}.{v}" for (c, v) in _versos_eng(repo, lv)}
    return [r for r in dict.fromkeys(saida) if r in existentes or r.split(".")[0] not in livros]


_CACHE_VERSOS: dict[str, set[tuple[int, int]]] = {}


def _versos_eng(repo: Repositorio, livro: str) -> set[tuple[int, int]]:
    if livro not in _CACHE_VERSOS:
        rows = repo.con.execute(
            "SELECT ref_canonica FROM versiculos WHERE livro=? AND ref_canonica IS NOT NULL",
            (livro,),
        )
        conj: set[tuple[int, int]] = set()
        for (r,) in rows:
            partes = r.split(".")
            if len(partes) == 3 and partes[0] == livro:
                conj.add((int(partes[1]), int(partes[2])))
        _CACHE_VERSOS[livro] = conj
    return _CACHE_VERSOS[livro]


def ancora_do_dia(
    dia: DiaLiturgico | None, vrs: Versificacao, repo: Repositorio
) -> AncoraLiturgica:
    anc = AncoraLiturgica()
    if dia is None:
        return anc
    anteriores: dict[str, list[Referencia]] = {}
    for lt in dia.leituras:
        lista = anteriores.setdefault(lt.tipo, [])
        try:
            r = parse_com_contexto(lt.referencia, lista)
        except (ValueError, KeyError):
            continue
        lista.append(r)
        refs = _expandir_eng(r, vrs, repo)
        anc.refs_leituras |= set(refs)
        if lt.tipo == "evangelho" and not anc.refs_evangelho:
            anc.refs_evangelho = refs
            if refs:
                livro, cap, _ = refs[0].split(".")
                anc.capitulo_evangelho = (livro, int(cap))
    return anc


@dataclass(slots=True)
class EntradaRecuperacao:
    consultas: list[str]
    origens: list[str]
    perfil: Perfil
    tempo: str
    categorias: list[str]
    ancora: AncoraLiturgica = field(default_factory=AncoraLiturgica)
    recentes_principais: set[str] = field(default_factory=set)
    recentes_complementares: set[str] = field(default_factory=set)


class Recuperador:
    def __init__(self, buscador: Buscador, reranker: Reranker, repo: Repositorio, cfg: Rag) -> None:
        self.buscador = buscador
        self.reranker = reranker
        self.repo = repo
        self.cfg = cfg

    def sementes(self, categorias: list[str], perfil: Perfil) -> list[Candidato]:
        from fiat_lux.biblia.referencias import Intervalo

        tax = taxonomia()
        saida: list[Candidato] = []
        for cat in categorias:
            c = tax.get(cat)
            if c is None:
                continue
            refs = list(c.sementes) + (list(c.sementes_deutero) if perfil.inclui_deutero else [])
            for semente in refs:
                livro, cap, vers = semente.split(".")
                v1, _, v2 = vers.partition("-")
                iv = Intervalo(
                    livro, int(cap), int(v1), None, None, int(v2) if v2 else None, None, "eng"
                )
                from fiat_lux.biblia.catalogo import por_codigo

                deutero = por_codigo(livro).deuterocanonico
                if deutero and not perfil.inclui_deutero:
                    continue
                trad = (perfil.traducao_deutero or perfil.traducao) if deutero else perfil.traducao
                if trad == "blivre":
                    versos = self.repo.versiculos_intervalo("blivre", iv)
                else:
                    versos = self.repo.eng_para_nativo(trad, iv)
                cand = self.buscador.candidato_de_versiculos(
                    [v.id for v in versos], "semente", f"s:{semente}"
                )
                if cand is not None:
                    saida.append(cand)
        return saida

    def recuperar(self, e: EntradaRecuperacao) -> list[Candidato]:
        cfg = self.cfg
        cands = self.buscador.buscar(
            e.consultas, e.perfil, cfg.top_denso, cfg.top_esparso, cfg.rrf_k, cfg.top_rerank
        )
        vistos = {v for c in cands for v in c.versiculo_ids}
        for s in self.sementes(e.categorias, e.perfil):
            if not set(s.versiculo_ids) & vistos:
                cands.append(s)
                vistos |= set(s.versiculo_ids)
        if not cands:
            return []
        # R: melhor consulta no rerank
        textos = [c.texto for c in cands]
        r_por = np.zeros(len(cands))
        t0 = time.perf_counter()
        para_rerank = e.consultas
        if self.reranker.nome.startswith("neural") and cfg.max_consultas_rerank > 0:
            # o cross-encoder domina o tempo do pipeline em CPU (RNF-06): só as primeiras
            # consultas (as mais informativas; ver agente/consultas.py) passam por ele
            para_rerank = e.consultas[: cfg.max_consultas_rerank]
        for q in para_rerank:
            r_por = np.maximum(r_por, np.asarray(self.reranker.pontuar(q, textos)))
        log().info(
            "rerank",
            reranker=self.reranker.nome,
            pares=len(textos) * len(para_rerank),
            segundos=round(time.perf_counter() - t0, 2),
        )
        if not self.reranker.nome.startswith("neural"):
            # sem cross-encoder: o rerank lexical privilegia coincidência literal; combina com
            # a similaridade densa (melhor consulta) para não premiar versículos fora de contexto
            qv = self.buscador.embedder.encode(e.consultas, "query")
            denso = np.array(
                [float(np.max(qv @ c.vetor)) if c.vetor is not None else 0.0 for c in cands]
            )
            r_por = 0.6 * _minmax(denso) + 0.4 * _minmax(r_por)
        # T: afinidade com o tempo litúrgico
        descr = " ; ".join(tempos_liturgicos().get(e.tempo, ()))
        if descr:
            vt = self.buscador.embedder.encode([descr], "query")[0]
            afinidade = [float(np.dot(c.vetor, vt)) if c.vetor is not None else 0.0 for c in cands]
        else:
            afinidade = [0.0] * len(cands)
        # X: grafo de referências cruzadas a partir do Evangelho
        vizinhos: list[tuple[str, str | None, int]] = []
        for ref in e.ancora.refs_evangelho[:40]:
            vizinhos += self.repo.refs_cruzadas(ref, cfg.min_votos_xref)
        vizinhos.sort(key=lambda t: -t[2])
        segundo = {
            ini: self.repo.refs_cruzadas(ini, cfg.min_votos_xref)[:15]
            for ini, _, _ in vizinhos[:10]
        }
        prox = boosts.proximidade_xref(vizinhos, segundo)
        # Q: consultas por tema
        por_tema: dict[str, set[int]] = {}
        for i, origem in enumerate(e.origens):
            if origem in e.categorias:
                por_tema.setdefault(origem, set()).add(i)
        p = cfg.pesos
        boosts.aplicar(
            cands,
            [float(x) for x in r_por],
            afinidade,
            e.ancora.refs_leituras,
            e.ancora.capitulo_evangelho,
            prox,
            por_tema,
            e.recentes_principais,
            e.recentes_complementares,
            boosts.Pesos(p.rerank, p.ancora, p.tempo, p.grafo, p.cobertura),
        )
        escolhidos = boosts.mmr(cands, cfg.candidatos_llm, cfg.mmr_lambda)
        return [self.recortar(c, e.consultas) for c in escolhidos]

    def recortar(self, c: Candidato, consultas: list[str]) -> Candidato:
        rc = self.cfg.recorte
        if len(c.textos) <= rc.max_vers and c.origem == "semente":
            return c
        esc = escores_por_versiculo(c.textos, consultas)
        a, b = melhor_trecho(esc, rc.min_vers, rc.max_vers, rc.penalidade_comprimento)
        if (a, b) == (0, len(c.textos)):
            return c
        refs_trecho = []
        for vid in c.versiculo_ids[a:b]:
            v = self.repo.por_id(vid)
            if v is not None and v.ref_canonica:
                refs_trecho.append(v.ref_canonica)
        return Candidato(
            id=c.id,
            traducao=c.traducao,
            livro=c.livro,
            versiculo_ids=c.versiculo_ids[a:b],
            refs_canonicas=refs_trecho,
            texto=" ".join(c.textos[a:b]),
            textos=c.textos[a:b],
            caps_vers=c.caps_vers[a:b],
            origem=c.origem,
            consultas=c.consultas,
            escores=c.escores,
            vetor=c.vetor,
            contexto=c.texto,
        )
