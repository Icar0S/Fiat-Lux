"""Acesso ao `estado.sqlite` (plano §7.2): cresce a cada dia e persiste entre execuções."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ESQUEMA = """
CREATE TABLE IF NOT EXISTS dias_liturgicos (
  data TEXT PRIMARY KEY,
  celebracao TEXT, cor TEXT, tempo TEXT,
  semana INTEGER, ciclo_dominical TEXT, ciclo_ferial TEXT,
  leituras_json TEXT,
  fonte TEXT NOT NULL,
  coletado_em TEXT NOT NULL,
  bruto_json TEXT
);

CREATE TABLE IF NOT EXISTS noticias (
  id INTEGER PRIMARY KEY,
  url_hash TEXT UNIQUE NOT NULL,
  url TEXT NOT NULL, titulo TEXT NOT NULL, dominio TEXT,
  idioma TEXT, pais_fonte TEXT,
  escopo TEXT NOT NULL CHECK (escopo IN ('mundial','nacional','regional')),
  publicado_em TEXT, coletado_em TEXT NOT NULL,
  fonte_coleta TEXT NOT NULL,
  cluster_id INTEGER,
  data_ref TEXT
);
CREATE INDEX IF NOT EXISTS ix_noticias_data ON noticias(data_ref, escopo);

CREATE TABLE IF NOT EXISTS clusters (
  id INTEGER PRIMARY KEY,
  data TEXT NOT NULL, escopo TEXT NOT NULL,
  rotulo TEXT,
  categoria TEXT,
  gravidade INTEGER CHECK (gravidade BETWEEN 0 AND 3),
  confianca REAL,
  n_artigos INTEGER, n_fontes INTEGER,
  relevancia REAL,
  sensivel TEXT,
  titulos_json TEXT,
  links_json TEXT,
  classificado_por TEXT                   -- 'llm' | 'palavras' (reserva: rótulo = manchete)
);
CREATE INDEX IF NOT EXISTS ix_clusters_data ON clusters(data, escopo);

CREATE TABLE IF NOT EXISTS medicoes (
  data TEXT, escopo TEXT,
  volume INTEGER, volume_z REAL,
  tom_medio REAL, tom_z REAL,
  gravidade_media REAL,
  indice REAL, faixa TEXT,
  calibrando INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (data, escopo)
);

CREATE TABLE IF NOT EXISTS series_gdelt (
  escopo TEXT, data TEXT, metrica TEXT, valor REAL,
  PRIMARY KEY (escopo, data, metrica)
);

CREATE TABLE IF NOT EXISTS mensagens (
  id INTEGER PRIMARY KEY,
  data TEXT, tipo TEXT CHECK (tipo IN ('diaria','semanal')),
  perfil TEXT, destinatario TEXT,
  conteudo_md TEXT NOT NULL,
  passagens_json TEXT NOT NULL,
  verificacao_json TEXT NOT NULL,
  modelo_llm TEXT, hash_prompts TEXT, versao_pipeline TEXT,
  tokens_entrada INTEGER, tokens_saida INTEGER, custo_estimado REAL,
  status TEXT CHECK (status IN ('rascunho','enviada','fallback','falhou')),
  enviada_em TEXT,
  telegram_message_ids TEXT,
  UNIQUE (data, tipo, perfil, destinatario)
);

CREATE TABLE IF NOT EXISTS passagens_usadas (
  data TEXT, perfil TEXT, ref_canonica TEXT, papel TEXT
);
CREATE INDEX IF NOT EXISTS ix_pu ON passagens_usadas(perfil, data);

CREATE TABLE IF NOT EXISTS execucoes (
  id INTEGER PRIMARY KEY, iniciada_em TEXT, terminada_em TEXT,
  tipo TEXT, status TEXT, etapa_falha TEXT, erro TEXT, duracao_s REAL,
  data_ref TEXT, custo REAL
);

CREATE TABLE IF NOT EXISTS feedback (
  mensagem_id INTEGER REFERENCES mensagens(id),
  nota INTEGER CHECK (nota IN (-1, 1)), comentario TEXT, criado_em TEXT
);

CREATE TABLE IF NOT EXISTS percepcao (          -- "o dia foi pesado?" (calibração do medidor)
  data TEXT PRIMARY KEY, nota INTEGER CHECK (nota BETWEEN 0 AND 100), comentario TEXT
);

CREATE TABLE IF NOT EXISTS kv (chave TEXT PRIMARY KEY, valor TEXT);
"""


def agora_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class Estado:
    def __init__(self, caminho: Path | str) -> None:
        self.caminho = Path(caminho) if str(caminho) != ":memory:" else caminho
        if isinstance(self.caminho, Path):
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(caminho))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)
        self._migrar()

    def _migrar(self) -> None:
        """Colunas acrescentadas depois da v0.1.0 (o estado persiste entre versões)."""
        cols = {r["name"] for r in self.con.execute("PRAGMA table_info(clusters)")}
        if "classificado_por" not in cols:
            self.con.execute("ALTER TABLE clusters ADD COLUMN classificado_por TEXT")
            self.con.commit()

    @classmethod
    def abrir(cls, caminho: Path | None = None) -> Estado:
        if caminho is None:
            from fiat_lux.config import obter_settings

            caminho = obter_settings().caminhos.estado_db
        return cls(caminho)

    def fechar(self) -> None:
        self.con.close()

    @contextmanager
    def transacao(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.con
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise

    # ------------------------------------------------------------------ kv

    def ler_kv(self, chave: str, padrao: str | None = None) -> str | None:
        r = self.con.execute("SELECT valor FROM kv WHERE chave=?", (chave,)).fetchone()
        return padrao if r is None else str(r[0])

    def gravar_kv(self, chave: str, valor: str) -> None:
        with self.transacao() as c:
            c.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (chave, valor))

    # ------------------------------------------------------------------ liturgia

    def dia_liturgico(self, data: dt.date) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self.con.execute(
            "SELECT * FROM dias_liturgicos WHERE data=?", (data.isoformat(),)
        ).fetchone()
        return row

    def gravar_dia_liturgico(self, data: dt.date, campos: dict[str, Any]) -> None:
        with self.transacao() as c:
            c.execute(
                "INSERT OR REPLACE INTO dias_liturgicos (data, celebracao, cor, tempo, semana,"
                " ciclo_dominical, ciclo_ferial, leituras_json, fonte, coletado_em, bruto_json)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    data.isoformat(),
                    campos.get("celebracao"),
                    campos.get("cor"),
                    campos.get("tempo"),
                    campos.get("semana"),
                    campos.get("ciclo_dominical"),
                    campos.get("ciclo_ferial"),
                    json.dumps(campos.get("leituras", []), ensure_ascii=False),
                    campos["fonte"],
                    agora_iso(),
                    json.dumps(campos.get("bruto"), ensure_ascii=False)
                    if campos.get("bruto")
                    else None,
                ),
            )

    # ------------------------------------------------------------------ execuções

    def iniciar_execucao(self, tipo: str, data_ref: dt.date) -> int:
        with self.transacao() as c:
            cur = c.execute(
                "INSERT INTO execucoes (iniciada_em, tipo, status, data_ref) VALUES (?,?,?,?)",
                (agora_iso(), tipo, "rodando", data_ref.isoformat()),
            )
            return int(cur.lastrowid or 0)

    def terminar_execucao(
        self,
        eid: int,
        status: str,
        duracao_s: float,
        etapa_falha: str | None = None,
        erro: str | None = None,
        custo: float | None = None,
    ) -> None:
        with self.transacao() as c:
            c.execute(
                "UPDATE execucoes SET terminada_em=?, status=?, duracao_s=?, etapa_falha=?, erro=?, custo=?"
                " WHERE id=?",
                (
                    agora_iso(),
                    status,
                    round(duracao_s, 2),
                    etapa_falha,
                    (erro or "")[:500] or None,
                    custo,
                    eid,
                ),
            )

    def execucoes(self, ultimos: int = 10) -> list[sqlite3.Row]:
        return self.con.execute(
            "SELECT * FROM execucoes ORDER BY id DESC LIMIT ?", (ultimos,)
        ).fetchall()

    # ------------------------------------------------------------------ mensagens

    def mensagem(
        self, data: dt.date, tipo: str, perfil: str, destinatario: str
    ) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self.con.execute(
            "SELECT * FROM mensagens WHERE data=? AND tipo=? AND perfil=? AND destinatario=?",
            (data.isoformat(), tipo, perfil, destinatario),
        ).fetchone()
        return row

    def ja_enviada(self, data: dt.date, tipo: str, perfil: str, destinatario: str) -> bool:
        m = self.mensagem(data, tipo, perfil, destinatario)
        return (
            m is not None and m["status"] in {"enviada", "fallback"} and m["enviada_em"] is not None
        )

    def gravar_mensagem(self, dados: dict[str, Any]) -> int:
        colunas = [
            "data",
            "tipo",
            "perfil",
            "destinatario",
            "conteudo_md",
            "passagens_json",
            "verificacao_json",
            "modelo_llm",
            "hash_prompts",
            "versao_pipeline",
            "tokens_entrada",
            "tokens_saida",
            "custo_estimado",
            "status",
            "enviada_em",
            "telegram_message_ids",
        ]
        valores = [dados.get(c) for c in colunas]
        with self.transacao() as c:
            c.execute(
                f"INSERT INTO mensagens ({', '.join(colunas)}) VALUES ({', '.join('?' for _ in colunas)})"
                " ON CONFLICT(data, tipo, perfil, destinatario) DO UPDATE SET "
                + ", ".join(f"{col}=excluded.{col}" for col in colunas[4:]),
                valores,
            )
            row = c.execute(
                "SELECT id FROM mensagens WHERE data=? AND tipo=? AND perfil=? AND destinatario=?",
                (dados["data"], dados["tipo"], dados["perfil"], dados["destinatario"]),
            ).fetchone()
            return int(row[0])

    def marcar_enviada(self, mid: int, ids_telegram: list[int] | None = None) -> None:
        with self.transacao() as c:
            c.execute(
                "UPDATE mensagens SET enviada_em=?, telegram_message_ids=? WHERE id=?",
                (agora_iso(), json.dumps(ids_telegram or []), mid),
            )

    def mensagens(self, ultimos: int = 7) -> list[sqlite3.Row]:
        return self.con.execute(
            "SELECT * FROM mensagens ORDER BY id DESC LIMIT ?", (ultimos,)
        ).fetchall()

    # ------------------------------------------------------------------ antirrepetição

    def registrar_passagens(self, data: dt.date, perfil: str, refs: list[tuple[str, str]]) -> None:
        with self.transacao() as c:
            c.execute(
                "DELETE FROM passagens_usadas WHERE data=? AND perfil=?", (data.isoformat(), perfil)
            )
            c.executemany(
                "INSERT INTO passagens_usadas VALUES (?,?,?,?)",
                [(data.isoformat(), perfil, ref, papel) for ref, papel in refs],
            )

    def passagens_recentes(self, perfil: str, antes_de: dt.date, dias: int, papel: str) -> set[str]:
        ini = (antes_de - dt.timedelta(days=dias)).isoformat()
        rows = self.con.execute(
            "SELECT ref_canonica FROM passagens_usadas WHERE perfil=? AND papel=? AND data>=? AND data<?",
            (perfil, papel, ini, antes_de.isoformat()),
        ).fetchall()
        return {r[0] for r in rows}

    # ------------------------------------------------------------------ custos e LGPD

    def custo_mes(self, ano: int, mes: int) -> float:
        prefixo = f"{ano:04d}-{mes:02d}"
        r = self.con.execute(
            "SELECT COALESCE(SUM(custo), 0) FROM execucoes WHERE data_ref LIKE ?", (prefixo + "%",)
        ).fetchone()
        return float(r[0] or 0)

    def apagar_destinatario(self, destinatario: str) -> int:
        with self.transacao() as c:
            ids = [
                r[0]
                for r in c.execute("SELECT id FROM mensagens WHERE destinatario=?", (destinatario,))
            ]
            c.executemany("DELETE FROM feedback WHERE mensagem_id=?", [(i,) for i in ids])
            n = c.execute("DELETE FROM mensagens WHERE destinatario=?", (destinatario,)).rowcount
            return int(n)
