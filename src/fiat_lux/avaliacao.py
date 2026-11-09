"""Suítes de avaliação (plano §11): parser, recuperação, adversariais, metamórficos e E2E.

    fiatlux eval rodar --suite rapida     # determinística, sem juiz e sem rede (CI de cada PR)
    fiatlux eval rodar --suite completa   # + E2E em dias congelados e juiz (P6) quando houver chave

Relatórios: eval/relatorios/AAAA-MM-DD.json e .html.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import math
import random
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from fiat_lux.config import Settings, raiz_projeto

EVAL = raiz_projeto() / "eval"


def _golden(nome: str) -> Any:
    return yaml.safe_load((EVAL / "golden" / nome).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ parser


def avaliar_parser() -> dict[str, Any]:
    from fiat_lux.biblia.referencias import formatar, parse

    casos = _golden("referencias.yaml")["referencias"]
    erros = []
    for c in casos:
        try:
            r = parse(c["ref"], livro_padrao=c.get("livro_padrao"))
            if r.livro != c["livro"] or formatar(r) != c["normalizada"]:
                erros.append(c["ref"])
        except Exception:
            erros.append(c["ref"])
    return {
        "casos": len(casos),
        "acuracia": 1 - len(erros) / len(casos),
        "erros": erros[:20],
        "meta": 1.0,
    }


# ------------------------------------------------------------------ recuperação


def _expandir(ref: str) -> set[str]:
    livro, cap, vers = ref.split(".")
    v1, _, v2 = vers.partition("-")
    return {f"{livro}.{cap}.{v}" for v in range(int(v1), int(v2 or v1) + 1)}


def avaliar_recuperacao(
    perfil_nome: str = "catolico", k: int = 10, usar_rerank: bool = False, s: Settings | None = None
) -> dict[str, Any]:
    from fiat_lux.biblia.repositorio import Repositorio
    from fiat_lux.config import obter_settings
    from fiat_lux.pastoral import perfil
    from fiat_lux.rag.busca import Buscador
    from fiat_lux.rag.recuperacao import EntradaRecuperacao, Recuperador
    from fiat_lux.rag.rerank import criar_reranker

    s = s or obter_settings()
    casos = _golden("recuperacao.yaml")["casos"]
    buscador = Buscador.abrir(s.caminhos.biblia_db)
    rec = Recuperador(
        buscador,
        criar_reranker(usar_rerank, s.rag.modelo_rerank),
        Repositorio.abrir(s.caminhos.biblia_db),
        s.rag.model_copy(update={"candidatos_llm": k}),
    )
    p = perfil(perfil_nome)
    acertos = recall = ndcg = mrr = 0.0
    detalhes = []
    for caso in casos:
        aceit = [_expandir(a) for a in caso["aceitaveis"]]
        cands = rec.recuperar(
            EntradaRecuperacao([caso["consulta"]], [caso["categoria"]], p, "comum", [])
        )
        rel = [any(set(c.refs_canonicas) & a for a in aceit) for c in cands[:k]]
        cobertos = sum(1 for a in aceit if any(set(c.refs_canonicas) & a for c in cands[:k]))
        acertos += 1.0 if any(rel) else 0.0
        recall += cobertos / len(aceit)
        dcg = sum(1 / math.log2(i + 2) for i, r in enumerate(rel) if r)
        ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(aceit))))
        ndcg += dcg / ideal if ideal else 0
        primeira = next((i for i, r in enumerate(rel) if r), None)
        mrr += 1 / (primeira + 1) if primeira is not None else 0
        detalhes.append(
            {
                "id": caso["id"],
                "acerto": any(rel),
                "primeira": primeira,
                "top3": [c.rotulo() for c in cands[:3]],
            }
        )
    n = len(casos)
    return {
        "perfil": perfil_nome,
        "embedder": buscador.embedder.nome,
        "rerank": usar_rerank,
        "casos": n,
        f"acerto@{k}": round(acertos / n, 3),
        f"recall@{k}": round(recall / n, 3),
        f"ndcg@{k}": round(ndcg / n, 3),
        "mrr": round(mrr / n, 3),
        "metas": {"recall@10_f4": 0.70, "recall@10": 0.80, "ndcg@10": 0.60},
        "detalhes": detalhes,
    }


# ------------------------------------------------------------------ adversariais


def avaliar_adversarial() -> dict[str, Any]:
    from fiat_lux.agente.verificacao import EntradaVerificacao, RefPermitida, verificar
    from fiat_lux.llm.esquemas import Redacao
    from fiat_lux.pastoral import neutralidade

    g = _golden("adversarial.yaml")
    resultados = []
    for caso in g["casos"]:
        campos = dict(g["base"])
        if "campo" in caso:
            if "substituir" in caso:
                campos[caso["campo"]] = caso["substituir"]
            else:
                campos[caso["campo"]] = campos[caso["campo"]] + caso.get("acrescentar", "")
        checks = verificar(
            EntradaVerificacao(
                redacao=Redacao(**campos),
                permitidas=[RefPermitida("MAT", 5, 1, 12)],
                textos_permitidos=["Bem-aventurados os que choram, porque serão consolados."],
                urls_permitidas=set(),
                sensibilidades=set(caso.get("sensibilidades", [])),
                perfil=caso.get("perfil", "catolico"),
                livros_passagens=[("WIS", True)] if caso.get("livro_deutero") else [("MAT", False)],
                neutralidade=neutralidade(),
            )
        )
        falhas = [c.id for c in checks if not c.ok]
        ok = (not falhas) if caso["espera"] == "ok" else (caso["espera"] in falhas)
        resultados.append(
            {
                "id": caso["id"],
                "descricao": caso["descricao"],
                "espera": caso["espera"],
                "falhas": falhas,
                "ok": ok,
            }
        )
    return {
        "casos": len(resultados),
        "aprovados": sum(r["ok"] for r in resultados),
        "resultados": resultados,
    }


# ------------------------------------------------------------------ metamórficos


def avaliar_metamorficos() -> dict[str, Any]:
    from fiat_lux.llm.cliente import ClienteOffline
    from fiat_lux.noticias import medidor
    from fiat_lux.noticias.classificacao import classificar
    from fiat_lux.noticias.coleta import temas_do_dia
    from fiat_lux.noticias.modelos import Artigo, Cluster, Medicao

    fix = json.loads(
        (raiz_projeto() / "tests" / "fixtures" / "noticias" / "2026-11-09.json").read_text(
            encoding="utf-8"
        )
    )
    titulos = [r["titulo"] for r in fix if r["escopo"] == "nacional"][:60]

    def clusters(ts: list[str]) -> list[Cluster]:
        cl = []
        for i in range(0, len(ts) - 1, 2):
            arts = [
                Artigo(url=f"https://x/{hash(t)}", titulo=t, escopo="nacional", fonte_coleta="t")
                for t in ts[i : i + 2]
            ]
            cl.append(Cluster(escopo="nacional", artigos=arts, relevancia=float(len(ts) - i)))
        return cl

    base = clusters(titulos)
    classificar(base, ClienteOffline(), "offline", top=100)
    # MR1: permutar a ordem das manchetes dentro de cada cluster
    perm = []
    for c in base:
        novos = list(c.artigos)
        random.Random(7).shuffle(novos)
        perm.append(Cluster(escopo="nacional", artigos=novos, relevancia=c.relevancia))
    classificar(perm, ClienteOffline(), "offline", top=100)
    mr1 = [a.categoria for a in base] == [b.categoria for b in perm]
    # MR3: injetar manchetes irrelevantes de baixa relevância
    lixo = clusters(
        [
            "Receita de bolo de cenoura fácil",
            "Como limpar a geladeira",
            "Dicas de jardinagem",
            "Tutorial de crochê",
        ]
    )
    for c in lixo:
        c.relevancia = 0.1
    classificar(lixo, ClienteOffline(), "offline", top=100)
    mr3 = [t.categoria for t in temas_do_dia(base)] == [
        t.categoria for t in temas_do_dia(base + lixo)
    ]
    # MR4: remover o escopo regional muda o composto só pela renormalização
    d = dt.date(2026, 11, 9)
    meds = {
        e: Medicao(data=d, escopo=e, indice=v, faixa=medidor.faixa(v))
        for e, v in (("mundial", 62.0), ("nacional", 41.0), ("regional", 30.0))
    }
    pesos = {"mundial": 0.35, "nacional": 0.30, "regional": 0.35}
    comp = medidor.composto({k: v for k, v in meds.items() if k != "regional"}, pesos)
    mr4 = comp is not None and abs(comp.indice - (62 * 0.35 + 41 * 0.30) / 0.65) < 0.11
    return {"MR1_permutacao": mr1, "MR3_ruido": mr3, "MR4_renormalizacao": mr4}


def avaliar_mr6(s: Settings | None = None) -> dict[str, Any]:
    """MR6: trocar o perfil para evangélico ⇒ zero deuterocanônicos entre os candidatos."""
    from fiat_lux.biblia.repositorio import Repositorio
    from fiat_lux.config import obter_settings
    from fiat_lux.pastoral import perfil
    from fiat_lux.rag.busca import Buscador
    from fiat_lux.rag.recuperacao import EntradaRecuperacao, Recuperador
    from fiat_lux.rag.rerank import RerankerLexical

    s = s or obter_settings()
    rec = Recuperador(
        Buscador.abrir(s.caminhos.biblia_db),
        RerankerLexical(),
        Repositorio.abrir(s.caminhos.biblia_db),
        s.rag,
    )
    consultas = ["a sabedoria de Deus guia os justos", "consolo para quem chora"]
    cat = rec.recuperar(
        EntradaRecuperacao(
            consultas, ["outro", "luto_tragedia"], perfil("catolico"), "comum", ["luto_tragedia"]
        )
    )
    ev = rec.recuperar(
        EntradaRecuperacao(
            consultas, ["outro", "luto_tragedia"], perfil("evangelico"), "comum", ["luto_tragedia"]
        )
    )
    return {
        "MR6_deutero_catolico": sum(c.deutero for c in cat),
        "MR6_deutero_evangelico": sum(c.deutero for c in ev),
        "MR6_ok": sum(c.deutero for c in ev) == 0,
    }


# ------------------------------------------------------------------ E2E em dias congelados


def avaliar_dias(
    datas: list[dt.date], provedor: str = "offline", perfil: str = "catolico"
) -> dict[str, Any]:
    """Dry-run do pipeline diário em dias congelados (liturgia do cache; sem coleta de notícias)."""
    from fiat_lux.config import obter_settings
    from fiat_lux.estado import Estado
    from fiat_lux.orquestracao.diaria import OpcoesDiaria, executar

    s = obter_settings()
    raw = s.caminhos.raw / "liturgia"
    from fiat_lux.liturgia.modelos import RespostaV2
    from fiat_lux.liturgia.servico import ServicoLiturgia, de_resposta

    resultados: list[dict[str, Any]] = []
    # Windows não apaga um SQLite aberto: fecha o estado antes de limpar o diretório.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        estado = Estado(Path(tmp) / "estado.sqlite")
        try:
            svc = ServicoLiturgia(estado, None)
            for d in datas:  # congela a liturgia a partir dos arquivos baixados
                arq = raw / f"{d.isoformat()}.json"
                if arq.is_file():
                    resp = RespostaV2.model_validate(json.loads(arq.read_text(encoding="utf-8")))
                    svc._gravar(resp, de_resposta(resp))
            for d in datas:
                t0 = time.perf_counter()
                r = executar(
                    OpcoesDiaria(
                        data=d,
                        perfil=perfil,
                        dry_run=True,
                        provedor_llm=provedor,
                        coletar_noticias=False,
                        usar_rerank=False,
                    ),
                    s,
                    estado,
                )
                invalidas = sum(1 for c in r.verificacao if c.id in {"V2", "V3"} and not c.ok)
                resultados.append(
                    {
                        "data": d.isoformat(),
                        "status": r.status,
                        "principal": r.escolha.principal.rotulo() if r.escolha else None,
                        "citacoes_invalidas": invalidas,
                        "tentativas": r.tentativas_redacao,
                        "segundos": round(time.perf_counter() - t0, 1),
                        "etapa_falha": r.etapa_falha,
                    }
                )
        finally:
            estado.fechar()
    n = len(resultados)
    fallbacks = sum(r["status"] == "fallback" for r in resultados)
    return {
        "dias": n,
        "provedor": provedor,
        "perfil": perfil,
        "taxa_fallback": round(fallbacks / n, 3) if n else None,
        "citacoes_invalidas": sum(r["citacoes_invalidas"] for r in resultados),
        "tempo_medio_s": round(sum(r["segundos"] for r in resultados) / n, 1) if n else None,
        "resultados": resultados,
    }


# ------------------------------------------------------------------ relatório


def rodar(suite: str = "rapida", s: Settings | None = None) -> dict[str, Any]:
    rel: dict[str, Any] = {
        "suite": suite,
        "gerado_em": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }
    rel["parser"] = avaliar_parser()
    rel["adversarial"] = avaliar_adversarial()
    rel["metamorficos"] = avaliar_metamorficos()
    db = s.caminhos.biblia_db if s else None
    try:
        rel["recuperacao_catolico"] = avaliar_recuperacao("catolico", s=s)
        rel["recuperacao_evangelico"] = avaliar_recuperacao("evangelico", s=s)
        rel["metamorficos"].update(avaliar_mr6(s))
    except (FileNotFoundError, RuntimeError) as e:
        rel["recuperacao_catolico"] = {"erro": f"índice indisponível: {e}", "db": str(db)}
    if suite == "completa":
        inicio = dt.date(2026, 11, 1)
        rel["e2e"] = avaliar_dias([inicio + dt.timedelta(days=i) for i in range(30)])
    destino = EVAL / "relatorios"
    destino.mkdir(parents=True, exist_ok=True)
    hoje = dt.date.today().isoformat()
    (destino / f"{hoje}-{suite}.json").write_text(
        json.dumps(rel, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    (destino / f"{hoje}-{suite}.html").write_text(_html(rel), encoding="utf-8")
    return rel


def _html(rel: dict[str, Any]) -> str:
    linhas = [
        f"<h1>Fiat Lux — avaliação ({html.escape(rel['suite'])})</h1><p>{html.escape(rel['gerado_em'])}</p>"
    ]
    for chave, valor in rel.items():
        if not isinstance(valor, dict):
            continue
        resumo = {k: v for k, v in valor.items() if not isinstance(v, list | dict)}
        linhas.append(f"<h2>{html.escape(chave)}</h2><table>")
        linhas += [
            f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
            for k, v in resumo.items()
        ]
        linhas.append("</table>")
    estilo = "body{font-family:system-ui;max-width:900px;margin:2em auto}th{text-align:left;padding-right:1em}td,th{border-bottom:1px solid #ddd}"
    return f"<!doctype html><meta charset='utf-8'><title>Avaliação Fiat Lux</title><style>{estilo}</style>{''.join(linhas)}"
