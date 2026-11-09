"""Esquema e escrita do `biblia.sqlite` (plano §7.1).

Ajustes em relação ao plano, documentados no ADR-002: `versiculos.titulo` (título de salmo
separado), `versiculos.fim_fundido` (versículo que contém o seguinte), `versiculos.texto_busca`
(forma normalizada indexada pelo FTS5) e `mapa_versificacao.ref_destino_fim` (intervalos 1→2).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from fiat_lux.biblia.catalogo import LIVROS
from fiat_lux.biblia.modelos import Lacuna, Mapeamento, Traducao, Verso

ESQUEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS traducoes (
  id            TEXT PRIMARY KEY,
  nome          TEXT NOT NULL,
  sigla         TEXT NOT NULL,
  tradicao      TEXT NOT NULL CHECK (tradicao IN ('catolica','protestante')),
  idioma        TEXT NOT NULL,
  versificacao  TEXT NOT NULL,
  licenca       TEXT NOT NULL,
  atribuicao    TEXT,
  fonte_repo    TEXT NOT NULL,
  fonte_commit  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS livros (
  codigo            TEXT PRIMARY KEY,
  nome_pt           TEXT NOT NULL,
  sigla_pt          TEXT NOT NULL,
  aliases           TEXT NOT NULL,
  testamento        TEXT NOT NULL CHECK (testamento IN ('AT','NT')),
  deuterocanonico   INTEGER NOT NULL DEFAULT 0,
  ordem_catolica    INTEGER NOT NULL,
  ordem_protestante INTEGER,
  grupo             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS versiculos (
  id           INTEGER PRIMARY KEY,
  traducao_id  TEXT NOT NULL REFERENCES traducoes(id),
  livro        TEXT NOT NULL REFERENCES livros(codigo),
  capitulo     INTEGER NOT NULL,
  versiculo    INTEGER NOT NULL,
  texto        TEXT NOT NULL,
  texto_bruto  TEXT NOT NULL,
  texto_busca  TEXT NOT NULL,
  titulo       TEXT,
  ref_canonica TEXT,
  fim_fundido  INTEGER,
  flags        TEXT NOT NULL DEFAULT '[]',
  UNIQUE (traducao_id, livro, capitulo, versiculo)
);
CREATE INDEX IF NOT EXISTS ix_vers_canon ON versiculos(ref_canonica);
CREATE INDEX IF NOT EXISTS ix_vers_livro ON versiculos(traducao_id, livro, capitulo, versiculo);

CREATE TABLE IF NOT EXISTS lacunas (
  traducao_id TEXT, livro TEXT, capitulo INTEGER, versiculo INTEGER,
  status TEXT NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta','corrigida','aceita')),
  tipo   TEXT NOT NULL DEFAULT 'desconhecido',
  nota   TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (traducao_id, livro, capitulo, versiculo)
);

CREATE VIRTUAL TABLE IF NOT EXISTS versiculos_fts USING fts5(
  texto_busca, content='versiculos', content_rowid='id',
  tokenize = "unicode61 remove_diacritics 2"
);

CREATE TABLE IF NOT EXISTS pericopes (
  id          INTEGER PRIMARY KEY,
  traducao_id TEXT NOT NULL,
  livro       TEXT NOT NULL,
  cap_ini INTEGER, vers_ini INTEGER, cap_fim INTEGER, vers_fim INTEGER,
  texto       TEXT NOT NULL,
  tem_lacuna  INTEGER NOT NULL DEFAULT 0,
  tokens      INTEGER,
  refs_canonicas TEXT NOT NULL DEFAULT '[]',
  versiculo_ids  TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS ix_peric_livro ON pericopes(traducao_id, livro, cap_ini);

CREATE TABLE IF NOT EXISTS pericopes_emb (
  pericope_id INTEGER PRIMARY KEY REFERENCES pericopes(id),
  embedding   BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS referencias_cruzadas (
  de_ref   TEXT NOT NULL,
  para_ini TEXT NOT NULL,
  para_fim TEXT,
  votos    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_xref_de ON referencias_cruzadas(de_ref);

CREATE TABLE IF NOT EXISTS mapa_versificacao (
  esquema_origem  TEXT NOT NULL,
  ref_origem      TEXT NOT NULL,
  esquema_destino TEXT NOT NULL,
  ref_destino     TEXT NOT NULL,
  ref_destino_fim TEXT,
  metodo          TEXT NOT NULL,
  confianca       REAL NOT NULL,
  PRIMARY KEY (esquema_origem, ref_origem, esquema_destino)
);
CREATE INDEX IF NOT EXISTS ix_mapa_dest ON mapa_versificacao(esquema_destino, ref_destino);

CREATE TABLE IF NOT EXISTS metadados (chave TEXT PRIMARY KEY, valor TEXT);
"""


def conectar(caminho: Path, somente_leitura: bool = False) -> sqlite3.Connection:
    if somente_leitura:
        if not caminho.is_file():
            raise FileNotFoundError(
                f"{caminho} não existe; rode `fiatlux biblia ingerir` (ou baixe o Release do índice)"
            )
        con = sqlite3.connect(f"file:{caminho.as_posix()}?mode=ro", uri=True)
    else:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    return con


def carregar_sqlite_vec(con: sqlite3.Connection) -> bool:
    """Tenta carregar a extensão sqlite-vec; devolve False se indisponível."""
    try:
        import sqlite_vec

        con.enable_load_extension(True)
        sqlite_vec.load(con)
        con.enable_load_extension(False)
        return True
    except Exception:  # extensão é opcional (há fallback em numpy)
        return False


def criar_esquema(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA)


def gravar_traducoes(con: sqlite3.Connection, traducoes: Iterable[Traducao]) -> None:
    con.executemany(
        "INSERT OR REPLACE INTO traducoes VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                t.id,
                t.nome,
                t.sigla,
                t.tradicao,
                t.idioma,
                t.versificacao,
                t.licenca,
                t.atribuicao,
                t.fonte_repo,
                t.fonte_commit,
            )
            for t in traducoes
        ],
    )


def gravar_livros(con: sqlite3.Connection) -> None:
    con.executemany(
        "INSERT OR REPLACE INTO livros VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (
                lv.codigo,
                lv.nome_pt,
                lv.sigla_pt,
                json.dumps([lv.sigla_ms, lv.nome_ms, lv.osis, *lv.aliases], ensure_ascii=False),
                lv.testamento,
                int(lv.deuterocanonico),
                lv.ordem_catolica,
                lv.ordem_protestante,
                lv.grupo,
            )
            for lv in LIVROS
        ],
    )


def gravar_versiculos(
    con: sqlite3.Connection,
    versos: Iterable[Verso],
    texto_busca: dict[tuple[str, str, int, int], str],
) -> int:
    linhas = [
        (
            v.traducao,
            v.livro,
            v.capitulo,
            v.versiculo,
            v.texto,
            v.texto_bruto,
            texto_busca[(v.traducao, v.livro, v.capitulo, v.versiculo)],
            v.titulo,
            v.ref_canonica,
            v.fim_fundido,
            json.dumps(v.flags, ensure_ascii=False),
        )
        for v in versos
    ]
    con.executemany(
        "INSERT INTO versiculos (traducao_id, livro, capitulo, versiculo, texto, texto_bruto,"
        " texto_busca, titulo, ref_canonica, fim_fundido, flags) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        linhas,
    )
    return len(linhas)


def gravar_lacunas(con: sqlite3.Connection, lacunas: Iterable[Lacuna]) -> None:
    con.executemany(
        "INSERT OR REPLACE INTO lacunas VALUES (?,?,?,?,?,?,?)",
        [(x.traducao, x.livro, x.capitulo, x.versiculo, x.status, x.tipo, x.nota) for x in lacunas],
    )


def gravar_mapa(con: sqlite3.Connection, mapa: Iterable[Mapeamento]) -> None:
    con.executemany(
        "INSERT OR REPLACE INTO mapa_versificacao VALUES (?,?,?,?,?,?,?)",
        [
            (
                m.esquema_origem,
                m.ref_origem,
                m.esquema_destino,
                m.ref_destino,
                m.ref_destino_fim,
                m.metodo,
                round(m.confianca, 4),
            )
            for m in mapa
        ],
    )


def gravar_xrefs(
    con: sqlite3.Connection, linhas: Iterable[tuple[str, str, str | None, int]]
) -> int:
    lista = list(linhas)
    con.executemany("INSERT INTO referencias_cruzadas VALUES (?,?,?,?)", lista)
    return len(lista)


def gravar_metadados(con: sqlite3.Connection, dados: dict[str, str]) -> None:
    con.executemany("INSERT OR REPLACE INTO metadados VALUES (?,?)", list(dados.items()))


def reconstruir_fts(con: sqlite3.Connection) -> None:
    con.execute("INSERT INTO versiculos_fts(versiculos_fts) VALUES ('rebuild')")


def metadado(con: sqlite3.Connection, chave: str) -> str | None:
    row = con.execute("SELECT valor FROM metadados WHERE chave = ?", (chave,)).fetchone()
    return None if row is None else str(row[0])
