"""Busca híbrida (plano §8.4.2): BM25 (FTS5, versículo → perícope pelo máximo) + vetorial
(cosseno) fundidos por Reciprocal Rank Fusion (k = 60), com filtros de tradução, cânon do
perfil e lacunas.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from fiat_lux.biblia import banco
from fiat_lux.biblia.catalogo import por_codigo
from fiat_lux.pastoral import Perfil
from fiat_lux.rag.embeddings import Embedder
from fiat_lux.rag.indice import carregar_embedder
from fiat_lux.textos import normalizar_para_busca


@dataclass(slots=True)
class Candidato:
    id: str  # "p:<id da perícope>" ou "s:<semente>"
    traducao: str
    livro: str
    versiculo_ids: list[int]
    refs_canonicas: list[str]
    texto: str
    textos: list[str] = field(default_factory=list)
    caps_vers: list[tuple[int, int]] = field(default_factory=list)
    origem: str = "busca"  # busca | semente
    consultas: set[int] = field(default_factory=set)
    escores: dict[str, float] = field(default_factory=dict)
    vetor: NDArray[np.float32] | None = None
    contexto: str = ""  # perícope inteira (o LLM julga o sentido no contexto)

    @property
    def deutero(self) -> bool:
        return por_codigo(self.livro).deuterocanonico

    @property
    def testamento(self) -> str:
        return por_codigo(self.livro).testamento

    def rotulo(self) -> str:
        from fiat_lux.biblia.referencias import Intervalo, formatar_intervalos

        if not self.caps_vers:
            return por_codigo(self.livro).sigla_pt
        (c1, v1), (c2, v2) = self.caps_vers[0], self.caps_vers[-1]
        iv = Intervalo(
            self.livro,
            c1,
            v1,
            None,
            c2 if c2 != c1 else None,
            v2 if (c2, v2) != (c1, v1) else None,
            None,
            "nativo",
        )
        return formatar_intervalos(self.livro, [iv])


def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    escores: dict[int, float] = defaultdict(float)
    for lista in rankings:
        for pos, pid in enumerate(lista):
            escores[pid] += 1.0 / (k + pos + 1)
    return dict(escores)


def traducoes_do_perfil(perfil: Perfil) -> dict[str, bool]:
    """{tradução: inclui deuterocanônicos?} conforme o perfil (§8.5.6)."""
    if perfil.deuterocanonicos == "excluidos":
        return {perfil.traducao: False}
    if perfil.traducao_deutero and perfil.traducao_deutero != perfil.traducao:
        return {perfil.traducao: False, perfil.traducao_deutero: True}
    return {perfil.traducao: True}


class Buscador:
    def __init__(self, con: sqlite3.Connection, embedder: Embedder) -> None:
        self.con = con
        self.embedder = embedder

    @classmethod
    def abrir(cls, caminho_db: Path | None = None, embedder: Embedder | None = None) -> Buscador:
        if caminho_db is None:
            from fiat_lux.config import obter_settings

            caminho_db = obter_settings().caminhos.biblia_db
        con = banco.conectar(caminho_db, somente_leitura=True)
        meta = {r[0]: r[1] for r in con.execute("SELECT chave, valor FROM metadados")}
        if "indice_embedder" not in meta:
            raise RuntimeError("índice não construído: rode `fiatlux indice construir`")
        return cls(con, embedder or carregar_embedder(meta, caminho_db))

    def fechar(self) -> None:
        self.con.close()

    @cached_property
    def _pericopes(self) -> dict[int, sqlite3.Row]:
        return {int(r["id"]): r for r in self.con.execute("SELECT * FROM pericopes")}

    @cached_property
    def _verso_para_pericopes(self) -> dict[int, list[int]]:
        mapa: dict[int, list[int]] = defaultdict(list)
        for pid, r in self._pericopes.items():
            for vid in json.loads(r["versiculo_ids"]):
                mapa[int(vid)].append(pid)
        return mapa

    @cached_property
    def _matrizes(self) -> dict[str, tuple[NDArray[np.int64], NDArray[np.float32]]]:
        por_trad: dict[str, tuple[list[int], list[NDArray[np.float32]]]] = {}
        for r in self.con.execute(
            "SELECT e.pericope_id, e.embedding, p.traducao_id FROM pericopes_emb e JOIN pericopes p ON p.id = e.pericope_id"
        ):
            ids, vets = por_trad.setdefault(r[2], ([], []))
            ids.append(int(r[0]))
            vets.append(np.frombuffer(r[1], dtype=np.float32))
        saida: dict[str, tuple[NDArray[np.int64], NDArray[np.float32]]] = {}
        for t, (ids, vets) in por_trad.items():
            arr = np.asarray(ids)
            ordem = np.argsort(arr)  # searchsorted em vetor_pericope exige ids ordenados
            saida[t] = (arr[ordem], np.vstack(vets)[ordem])
        return saida

    def vetor_pericope(self, pid: int) -> NDArray[np.float32] | None:
        trad = self._pericopes[pid]["traducao_id"]
        ids, mat = self._matrizes[trad]
        pos = np.searchsorted(ids, pid)
        if pos < len(ids) and ids[pos] == pid:
            return mat[pos]
        return None

    def _permitida(self, pid: int, traducoes: dict[str, bool]) -> bool:
        r = self._pericopes[pid]
        trad = r["traducao_id"]
        if trad not in traducoes or r["tem_lacuna"]:
            return False
        deutero = por_codigo(r["livro"]).deuterocanonico
        incluir_deutero = traducoes[trad]
        if deutero:
            return incluir_deutero
        # tradução só de deuterocanônicos (perfil ecumênico) não traz protocanônicos
        return not (incluir_deutero and len(traducoes) > 1)

    def bm25(self, consulta: str, traducoes: dict[str, bool], limite: int = 50) -> list[int]:
        termos = [t for t in normalizar_para_busca(consulta).split() if len(t) > 2]
        if not termos:
            return []
        expr = " OR ".join(f'"{t}"' for t in termos)
        melhores: dict[int, float] = {}
        for trad in traducoes:
            rows = self.con.execute(
                "SELECT v.id, bm25(versiculos_fts) AS s FROM versiculos_fts JOIN versiculos v ON v.id = versiculos_fts.rowid"
                " WHERE versiculos_fts MATCH ? AND v.traducao_id = ? ORDER BY s LIMIT ?",
                (expr, trad, limite * 4),
            ).fetchall()
            for vid, s in rows:
                for pid in self._verso_para_pericopes.get(int(vid), []):
                    if self._permitida(pid, traducoes):
                        melhores[pid] = max(melhores.get(pid, 0.0), -float(s))
        return [pid for pid, _ in sorted(melhores.items(), key=lambda kv: -kv[1])[:limite]]

    def denso(
        self, vetor: NDArray[np.float32], traducoes: dict[str, bool], limite: int = 50
    ) -> list[tuple[int, float]]:
        saida: list[tuple[int, float]] = []
        for trad in traducoes:
            if trad not in self._matrizes:
                continue
            ids, mat = self._matrizes[trad]
            sims = mat @ vetor
            ordem = np.argsort(-sims)
            n = 0
            for i in ordem:
                pid = int(ids[i])
                if not self._permitida(pid, traducoes):
                    continue
                saida.append((pid, float(sims[i])))
                n += 1
                if n >= limite:
                    break
        saida.sort(key=lambda t: -t[1])
        return saida[:limite]

    def candidato(self, pid: int) -> Candidato:
        r = self._pericopes[pid]
        vids = [int(x) for x in json.loads(r["versiculo_ids"])]
        linhas = {
            int(x["id"]): x
            for x in self.con.execute(
                f"SELECT id, capitulo, versiculo, texto FROM versiculos WHERE id IN ({','.join('?' * len(vids))})",
                vids,
            )
        }
        return Candidato(
            id=f"p:{pid}",
            traducao=r["traducao_id"],
            livro=r["livro"],
            versiculo_ids=vids,
            refs_canonicas=json.loads(r["refs_canonicas"]),
            texto=r["texto"],
            textos=[linhas[v]["texto"] for v in vids],
            caps_vers=[(linhas[v]["capitulo"], linhas[v]["versiculo"]) for v in vids],
            vetor=self.vetor_pericope(pid),
        )

    def buscar(
        self,
        consultas: list[str],
        perfil: Perfil,
        top_denso: int = 50,
        top_esparso: int = 50,
        k: int = 60,
        limite: int = 40,
    ) -> list[Candidato]:
        traducoes = traducoes_do_perfil(perfil)
        vetores = (
            self.embedder.encode(consultas, "query")
            if consultas
            else np.zeros((0, 1), dtype=np.float32)
        )
        rankings: list[list[int]] = []
        por_consulta: dict[int, set[int]] = defaultdict(set)
        denso_max: dict[int, float] = {}
        for i, q in enumerate(consultas):
            esparso = self.bm25(q, traducoes, top_esparso)
            denso = self.denso(vetores[i], traducoes, top_denso)
            rankings += [esparso, [pid for pid, _ in denso]]
            for pid in esparso:
                por_consulta[pid].add(i)
            for pid, s in denso:
                por_consulta[pid].add(i)
                denso_max[pid] = max(denso_max.get(pid, -1.0), s)
        fundido = rrf(rankings, k)
        melhores = sorted(fundido.items(), key=lambda kv: -kv[1])[:limite]
        saida = []
        for pid, s in melhores:
            c = self.candidato(pid)
            c.consultas = por_consulta[pid]
            c.escores["rrf"] = s
            c.escores["denso"] = denso_max.get(pid, 0.0)
            saida.append(c)
        return saida

    def candidato_de_versiculos(
        self, ids: list[int], origem: str, rotulo_id: str
    ) -> Candidato | None:
        if not ids:
            return None
        linhas = self.con.execute(
            f"SELECT id, livro, traducao_id, capitulo, versiculo, texto, ref_canonica FROM versiculos WHERE id IN ({','.join('?' * len(ids))})"
            " ORDER BY capitulo, versiculo",
            ids,
        ).fetchall()
        if not linhas:
            return None
        textos = [x["texto"] for x in linhas]
        vet = self.embedder.encode([" ".join(textos)], "passage")[0]
        return Candidato(
            id=rotulo_id,
            traducao=linhas[0]["traducao_id"],
            livro=linhas[0]["livro"],
            versiculo_ids=[int(x["id"]) for x in linhas],
            refs_canonicas=[x["ref_canonica"] for x in linhas if x["ref_canonica"]],
            texto=" ".join(textos),
            textos=textos,
            caps_vers=[(x["capitulo"], x["versiculo"]) for x in linhas],
            origem=origem,
            vetor=vet,
        )
