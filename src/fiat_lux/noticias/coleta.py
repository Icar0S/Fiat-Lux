"""Coleta e processamento do dia: artigos → clusters → classificação → medições → temas."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fiat_lux.config import Settings, dir_config
from fiat_lux.estado import Estado, agora_iso
from fiat_lux.llm.cliente import Contabilidade, LLMClient
from fiat_lux.llm.esquemas import NAO_TEMATICAS
from fiat_lux.logs import log
from fiat_lux.noticias import clusterizacao, medidor
from fiat_lux.noticias.classificacao import classificar
from fiat_lux.noticias.dedup import deduplicar
from fiat_lux.noticias.gdelt import ClienteGdelt, ErroGdelt
from fiat_lux.noticias.modelos import ESCOPOS, Artigo, Cluster, Escopo, ResultadoNoticias, TemaDoDia
from fiat_lux.noticias.normalizacao import normalizar
from fiat_lux.noticias.rss import ClienteRss, ErroRss
from fiat_lux.rag.embeddings import vetores_textos_curtos

IDIOMAS_ACEITOS = {"pt", "en", None}
JANELA_HORAS = 36


def carregar_fontes(caminho: Path | None = None) -> dict[str, Any]:
    dados: dict[str, Any] = yaml.safe_load(
        (caminho or dir_config() / "fontes_noticias.yaml").read_text(encoding="utf-8")
    )
    return dados


@dataclass(slots=True)
class Coletor:
    fontes: dict[str, Any]
    gdelt: ClienteGdelt | None = None
    rss: ClienteRss | None = None
    max_registros: int = 250
    timespan: str = "24h"

    def coletar(
        self, referencia: dt.datetime
    ) -> tuple[dict[str, list[Artigo]], list[str], dict[str, float | None]]:
        """Devolve (artigos por escopo, avisos, tom do dia por escopo quando o GDELT responde)."""
        avisos: list[str] = []
        tons: dict[str, float | None] = {}
        sufixos = tuple(self.fontes.get("sufixos_titulo", []))
        saida: dict[str, list[Artigo]] = {}
        gdelt_ok = self.gdelt is not None
        for escopo in ESCOPOS:
            cfg = self.fontes["escopos"].get(escopo, {})
            artigos: list[Artigo] = []
            if gdelt_ok and self.gdelt is not None:
                try:
                    for consulta in cfg.get("gdelt", {}).get("consultas", []):
                        artigos += self.gdelt.artigos(
                            consulta, escopo, self.timespan, self.max_registros
                        )
                    tom_q = cfg.get("gdelt", {}).get("tom")
                    if tom_q:
                        serie = self.gdelt.serie(tom_q, "TimelineTone", "1d")
                        tons[escopo] = serie[-1][1] if serie else None
                except ErroGdelt as e:  # as mensagens do ErroGdelt já citam o GDELT
                    avisos.append(f"{e}; notícias só do RSS")
                    gdelt_ok = False  # não insiste nos demais escopos
            if self.rss is not None and (escopo == "regional" or len(artigos) < 30):
                for feed in cfg.get("rss", []):
                    try:
                        artigos += self.rss.coletar(feed["url"], feed["nome"], escopo)
                    except ErroRss as e:
                        avisos.append(f"RSS {feed['nome']} falhou: {e}")
            saida[escopo] = artigos
        if self.rss is not None:
            for comp in self.fontes.get("complementares", []):
                try:
                    saida[comp["escopo"]] += self.rss.coletar(
                        comp["url"], comp["nome"], comp["escopo"], comp.get("max_itens")
                    )
                except ErroRss as e:
                    avisos.append(f"RSS {comp['nome']} falhou: {e}")
        limite = referencia - dt.timedelta(hours=JANELA_HORAS)
        for nome_escopo, lista in saida.items():
            normalizados = [normalizar(a, sufixos) for a in lista]
            filtrados = [
                a
                for a in normalizados
                if a.idioma in IDIOMAS_ACEITOS
                and (
                    a.publicado_em is None
                    or limite <= a.publicado_em <= referencia + dt.timedelta(hours=2)
                )
            ]
            saida[nome_escopo] = filtrados
        return saida, avisos, tons


def gravar_artigos(estado: Estado, data: dt.date, artigos: dict[str, list[Artigo]]) -> int:
    n = 0
    with estado.transacao() as c:
        for lista in artigos.values():
            for a in lista:
                cur = c.execute(
                    "INSERT OR IGNORE INTO noticias (url_hash, url, titulo, dominio, idioma, pais_fonte, escopo,"
                    " publicado_em, coletado_em, fonte_coleta, data_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        a.url_hash,
                        a.url,
                        a.titulo,
                        a.fonte_nome or a.dominio,
                        a.idioma,
                        a.pais_fonte,
                        a.escopo,
                        a.publicado_em.isoformat() if a.publicado_em else None,
                        agora_iso(),
                        a.fonte_coleta,
                        data.isoformat(),
                    ),
                )
                n += cur.rowcount
    return n


def artigos_do_dia(estado: Estado, data: dt.date) -> dict[str, list[Artigo]]:
    rows = estado.con.execute(
        "SELECT * FROM noticias WHERE data_ref=? ORDER BY id", (data.isoformat(),)
    ).fetchall()
    saida: dict[str, list[Artigo]] = {e: [] for e in ESCOPOS}
    for r in rows:
        saida[r["escopo"]].append(
            Artigo(
                url=r["url"],
                titulo=r["titulo"],
                dominio=r["dominio"],
                fonte_nome=r["dominio"],
                idioma=r["idioma"],
                pais_fonte=r["pais_fonte"],
                escopo=r["escopo"],
                publicado_em=dt.datetime.fromisoformat(r["publicado_em"])
                if r["publicado_em"]
                else None,
                fonte_coleta=r["fonte_coleta"],
                url_hash=r["url_hash"],
            )
        )
    return saida


def _historico(
    estado: Estado, escopo: str, data: dt.date, dias: int
) -> tuple[list[float], list[float]]:
    ini = (data - dt.timedelta(days=dias)).isoformat()
    vol = [
        float(r[0])
        for r in estado.con.execute(
            "SELECT volume FROM medicoes WHERE escopo=? AND data>=? AND data<? ORDER BY data",
            (escopo, ini, data.isoformat()),
        )
    ]
    tom = [
        float(r[0])
        for r in estado.con.execute(
            "SELECT valor FROM series_gdelt WHERE escopo=? AND metrica='tom' AND data>=? AND data<? ORDER BY data",
            (escopo, ini, data.isoformat()),
        )
    ]
    return vol, tom


def _gravar_resultado(estado: Estado, res: ResultadoNoticias) -> None:
    d = res.data.isoformat()
    with estado.transacao() as c:
        c.execute("DELETE FROM clusters WHERE data=?", (d,))
        for cl in res.clusters:
            c.execute(
                "INSERT INTO clusters (data, escopo, rotulo, categoria, gravidade, confianca, n_artigos, n_fontes,"
                " relevancia, sensivel, titulos_json, links_json, classificado_por)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    d,
                    cl.escopo,
                    cl.rotulo,
                    cl.categoria,
                    cl.gravidade,
                    cl.confianca,
                    len(cl.artigos),
                    cl.n_fontes,
                    cl.relevancia,
                    cl.sensivel,
                    json.dumps(cl.titulos[:10], ensure_ascii=False),
                    json.dumps(cl.links(), ensure_ascii=False),
                    cl.classificado_por,
                ),
            )
        for m in res.medicoes.values():
            c.execute(
                "INSERT OR REPLACE INTO medicoes VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    d,
                    m.escopo,
                    m.volume,
                    m.volume_z,
                    m.tom_medio,
                    m.tom_z,
                    m.gravidade_media,
                    m.indice,
                    m.faixa,
                    int(m.calibrando),
                ),
            )


def temas_do_dia(clusters: list[Cluster], n: int = 3) -> list[TemaDoDia]:
    """Top-n temas: categorias diferentes, ignorando "outro" e clusters não classificados."""
    candidatos = [c for c in clusters if c.categoria and c.categoria not in NAO_TEMATICAS]
    candidatos.sort(key=lambda c: -(c.relevancia * (1 + 0.25 * (c.gravidade or 0))))
    vistos: set[str] = set()
    temas: list[TemaDoDia] = []
    for c in candidatos:
        if c.categoria in vistos:
            continue
        vistos.add(c.categoria or "")
        temas.append(
            TemaDoDia(
                categoria=c.categoria or "outro",
                rotulo=c.rotulo or c.titulos[0],
                escopo=c.escopo,
                gravidade=c.gravidade or 0,
                relevancia=c.relevancia,
                sensivel=c.sensivel,
                links=c.links(3),
            )
        )
        if len(temas) == n:
            break
    return temas


def processar_dia(
    data: dt.date,
    s: Settings,
    estado: Estado,
    llm: LLMClient | None,
    coletor: Coletor | None,
    contabilidade: Contabilidade | None = None,
    referencia: dt.datetime | None = None,
) -> ResultadoNoticias:
    ref = referencia or dt.datetime.combine(data, dt.time(8, 0), tzinfo=dt.UTC)
    res = ResultadoNoticias(data=data)
    tons: dict[str, float | None] = {}
    if coletor is not None:
        artigos, avisos, tons = coletor.coletar(ref)
        res.avisos += avisos
        gravar_artigos(estado, data, artigos)
    artigos = artigos_do_dia(estado, data)
    if not any(artigos.values()):
        res.disponivel = False
        res.avisos.append("nenhuma notícia disponível para a data")
        return res

    # TF-IDF de n-gramas ajustado nas manchetes do dia, em qualquer modo (ADR-011): o e5
    # comprime o cosseno (mediana 0,77–0,84 entre manchetes sem relação) e agrupa por assunto,
    # não por história; o LSA lexical foi ajustado na Bíblia e zera vocabulário moderno.
    limiar = s.noticias.limiar_cluster
    for escopo in ESCOPOS:
        lista = deduplicar(
            artigos[escopo], s.noticias.limiar_dedup_titulo, s.noticias.limiar_dedup_cosseno
        )
        res.artigos[escopo] = len(lista)
        if not lista:
            continue
        vet = vetores_textos_curtos([a.titulo for a in lista])
        res.clusters += clusterizacao.agrupar(lista, vet, escopo, limiar, ref)
    res.avisos += classificar(
        res.clusters,
        llm,
        s.llm.modelo_classificacao,
        s.llm.temperatura_classificacao,
        s.noticias.top_clusters_classificar,
        s.noticias.titulos_por_cluster,
        s.noticias.confianca_minima,
        contabilidade,
    )
    formula = medidor.Formula(**s.medidor.formula.model_dump())
    faixas = medidor.Faixas(**s.medidor.faixas.model_dump())
    for escopo in ESCOPOS:
        cl = [c for c in res.clusters if c.escopo == escopo]
        if not res.artigos.get(escopo):
            continue
        hist_v, hist_t = _historico(estado, escopo, data, s.medidor.janela_baseline_dias)
        tom = tons.get(escopo)
        if tom is not None:
            with estado.transacao() as c:
                c.execute(
                    "INSERT OR REPLACE INTO series_gdelt VALUES (?,?,?,?)",
                    (escopo, data.isoformat(), "tom", tom),
                )
        res.medicoes[escopo] = medidor.calcular(
            data,
            escopo,
            res.artigos[escopo],
            cl,
            hist_v,
            tom,
            hist_t,
            formula,
            faixas,
            s.medidor.janela_baseline_dias,
            s.medidor.clusters_top,
        )
    comp = medidor.composto(res.medicoes, s.medidor.pesos_escopo, faixas)
    if comp is not None:
        res.medicoes["composto"] = comp
    res.temas = temas_do_dia(res.clusters)
    dom = clusterizacao.evento_dominante(
        sorted(
            [c for c in res.clusters if c.categoria and c.categoria not in NAO_TEMATICAS],
            key=lambda c: -c.relevancia,
        ),
        s.medidor.evento_dominante_razao,
    )
    if dom is not None:
        res.evento_dominante = next((t for t in res.temas if t.rotulo == dom.rotulo), None)
    res.sensibilidades = sorted({c.sensivel for c in res.clusters[:30] if c.sensivel})
    _gravar_resultado(estado, res)
    log().info(
        "noticias",
        data=data.isoformat(),
        artigos=res.artigos,
        clusters=len(res.clusters),
        composto=res.medicoes.get("composto").indice if res.medicoes.get("composto") else None,  # type: ignore[union-attr]
    )
    return res


def bootstrap_baseline_gdelt(estado: Estado, gdelt: ClienteGdelt, fontes: dict[str, Any]) -> int:
    """Arranque a frio: grava 30 dias de tom (TimelineTone) por escopo."""
    n = 0
    for escopo in ESCOPOS:
        consulta = fontes["escopos"].get(escopo, {}).get("gdelt", {}).get("tom")
        if not consulta:
            continue
        serie = gdelt.serie(consulta, "TimelineTone", "30d")
        with estado.transacao() as c:
            for d, v in serie:
                c.execute(
                    "INSERT OR REPLACE INTO series_gdelt VALUES (?,?,?,?)",
                    (escopo, d.isoformat(), "tom", v),
                )
                n += 1
    return n


def coletor_padrao(s: Settings, usar_gdelt: bool = True) -> Coletor:
    fontes = carregar_fontes()
    g = fontes.get("gdelt", {})
    return Coletor(
        fontes=fontes,
        gdelt=ClienteGdelt(
            g.get("url", "https://api.gdeltproject.org/api/v2/doc/doc"),
            float(g.get("intervalo_s", 5.5)),
            float(g.get("timeout_s", 40)),
        )
        if usar_gdelt
        else None,
        rss=ClienteRss(),
        max_registros=s.noticias.max_registros,
        timespan=s.noticias.timespan,
    )


def escopo_valido(e: str) -> Escopo:
    if e not in ESCOPOS:
        raise ValueError(f"escopo inválido: {e}")
    return e
