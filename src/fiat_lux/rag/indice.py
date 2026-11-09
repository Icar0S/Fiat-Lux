"""Construção do índice de busca (plano §8.4.2): perícopes + vetores no `biblia.sqlite`.

O BM25 usa a tabela FTS5 já criada na ingestão (nível de versículo). Os vetores ficam em
`pericopes_emb` (BLOB float32, sempre) e, quando a extensão carrega, também em
`pericopes_vec` (sqlite-vec). O embedder usado fica em `metadados` para a consulta usar o mesmo.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from fiat_lux.biblia import banco
from fiat_lux.rag.embeddings import Embedder, EmbedderLexical, EmbedderNeural, neural_disponivel
from fiat_lux.rag.pericopes import Pericope, gerar

TRADUCOES = ("ms", "blivre")


def texto_indexado(p: Pericope) -> str:
    return f"{p.rotulo()} — {p.texto}"


def escolher_embedder(modo: str, modelo: str, textos: list[str], caminho_lexical: Path) -> Embedder:
    if modo == "neural" or (modo == "auto" and neural_disponivel()):
        return EmbedderNeural(modelo)
    lex = EmbedderLexical().ajustar(textos)
    lex.salvar(caminho_lexical)
    return lex


def construir(
    caminho_db: Path,
    modo: str = "auto",
    modelo: str = "intfloat/multilingual-e5-base",
    caminho_lexical: Path | None = None,
    progresso: Callable[[str], None] | None = None,
    lote: int = 256,
) -> dict[str, object]:
    inicio = time.perf_counter()
    lexical_path = caminho_lexical or caminho_db.with_name("lexical.pkl")
    con = banco.conectar(caminho_db)
    try:
        banco.carregar_sqlite_vec(con)  # necessário para apagar a tabela virtual vec0 anterior
        con.execute("DROP TABLE IF EXISTS pericopes_vec")
        con.execute("DROP TABLE IF EXISTS pericopes_emb")
        con.execute("DROP TABLE IF EXISTS pericopes")
        banco.criar_esquema(con)  # recria com o esquema atual
        todas: list[Pericope] = []
        for trad in TRADUCOES:
            todas += gerar(con, trad)
        for p in todas:
            cur = con.execute(
                "INSERT INTO pericopes (traducao_id, livro, cap_ini, vers_ini, cap_fim, vers_fim, texto, tem_lacuna,"
                " tokens, refs_canonicas, versiculo_ids) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    p.traducao,
                    p.livro,
                    p.cap_ini,
                    p.vers_ini,
                    p.cap_fim,
                    p.vers_fim,
                    p.texto,
                    int(p.tem_lacuna),
                    p.tokens,
                    json.dumps(p.refs_canonicas),
                    json.dumps(p.versiculo_ids),
                ),
            )
            p.id = int(cur.lastrowid or 0)
        con.commit()
        textos = [texto_indexado(p) for p in todas]
        if progresso:
            progresso(f"{len(todas)} perícopes; calculando vetores…")
        emb = escolher_embedder(modo, modelo, textos, lexical_path)
        vetores = np.zeros((len(textos), emb.dim), dtype=np.float32)
        for i in range(0, len(textos), lote):
            vetores[i : i + lote] = emb.encode(textos[i : i + lote], "passage")
            if progresso and (i // lote) % 10 == 0:
                progresso(f"  {min(i + lote, len(textos))}/{len(textos)}")
        con.executemany(
            "INSERT INTO pericopes_emb VALUES (?, ?)",
            [(p.id, vetores[k].tobytes()) for k, p in enumerate(todas)],
        )
        vec_ok = banco.carregar_sqlite_vec(con)
        if vec_ok:
            con.execute(
                f"CREATE VIRTUAL TABLE pericopes_vec USING vec0(embedding float[{emb.dim}])"
            )
            con.executemany(
                "INSERT INTO pericopes_vec(rowid, embedding) VALUES (?, ?)",
                [(p.id, vetores[k].tobytes()) for k, p in enumerate(todas)],
            )
        meta = {
            "indice_embedder": emb.nome,
            "indice_dim": str(emb.dim),
            "indice_pericopes": str(len(todas)),
            "indice_sqlite_vec": "1" if vec_ok else "0",
            "indice_construido_em": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "indice_lexical": str(lexical_path) if emb.nome.startswith("lexical") else "",
        }
        banco.gravar_metadados(con, meta)
        con.commit()
    finally:
        con.close()
    return {
        "pericopes": len(todas),
        "por_traducao": {t: sum(1 for p in todas if p.traducao == t) for t in TRADUCOES},
        "com_lacuna": sum(p.tem_lacuna for p in todas),
        "embedder": emb.nome,
        "dim": emb.dim,
        "sqlite_vec": vec_ok,
        "segundos": round(time.perf_counter() - inicio, 1),
    }


def carregar_embedder(con_meta: dict[str, str], caminho_db: Path) -> Embedder:
    nome = con_meta.get("indice_embedder", "")
    if nome.startswith("neural:"):
        return EmbedderNeural(nome.split(":", 1)[1])
    caminho = Path(con_meta.get("indice_lexical") or caminho_db.with_name("lexical.pkl"))
    if not caminho.is_file():
        caminho = caminho_db.with_name("lexical.pkl")
    return EmbedderLexical.carregar(caminho)
