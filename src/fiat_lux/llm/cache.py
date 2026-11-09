"""Cache de respostas do LLM em SQLite, por hash da entrada (plano §9)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any


class CacheLLM:
    def __init__(self, caminho: Path | str) -> None:
        if str(caminho) != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(caminho))
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS respostas (chave TEXT PRIMARY KEY, tarefa TEXT, modelo TEXT,"
            " dados TEXT NOT NULL, criado_em TEXT NOT NULL)"
        )

    def obter(self, chave: str) -> dict[str, Any] | None:
        r = self.con.execute(
            "SELECT modelo, dados FROM respostas WHERE chave=?", (chave,)
        ).fetchone()
        if r is None:
            return None
        return {"modelo": r[0], "dados": json.loads(r[1])}

    def gravar(self, chave: str, tarefa: str, modelo: str, dados: dict[str, Any]) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO respostas VALUES (?,?,?,?,?)",
            (
                chave,
                tarefa,
                modelo,
                json.dumps(dados, ensure_ascii=False),
                dt.datetime.now(dt.UTC).isoformat(),
            ),
        )
        self.con.commit()

    def limpar(self, tarefa: str | None = None) -> int:
        if tarefa:
            n = self.con.execute("DELETE FROM respostas WHERE tarefa=?", (tarefa,)).rowcount
        else:
            n = self.con.execute("DELETE FROM respostas").rowcount
        self.con.commit()
        return int(n)
