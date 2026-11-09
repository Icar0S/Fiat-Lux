"""Consultas ao `biblia.sqlite` (plano §8.1.6)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from fiat_lux.biblia import banco
from fiat_lux.biblia.catalogo import por_codigo
from fiat_lux.biblia.modelos import F_TITULO_SALMO
from fiat_lux.biblia.referencias import Intervalo, Referencia, formatar_intervalos, parse
from fiat_lux.textos import normalizar_para_busca


@dataclass(frozen=True, slots=True)
class Versiculo:
    id: int
    traducao: str
    livro: str
    capitulo: int
    versiculo: int
    texto: str
    titulo: str | None
    ref_canonica: str | None
    flags: tuple[str, ...]
    fim_fundido: int | None

    @property
    def ref(self) -> str:
        return f"{self.livro}.{self.capitulo}.{self.versiculo}"


@dataclass(frozen=True, slots=True)
class Passagem:
    traducao: str
    livro: str
    ref_formatada: str
    versiculos: tuple[tuple[int, int, str], ...]
    tem_lacuna: bool = False
    avisos: tuple[str, ...] = field(default_factory=tuple)
    refs_canonicas: tuple[str, ...] = field(default_factory=tuple)

    @property
    def texto(self) -> str:
        return " ".join(t for _, _, t in self.versiculos)

    def texto_numerado(self) -> str:
        return " ".join(f"{v} {t}" for _, v, t in self.versiculos)


def _linha(r: sqlite3.Row) -> Versiculo:
    return Versiculo(
        r["id"],
        r["traducao_id"],
        r["livro"],
        r["capitulo"],
        r["versiculo"],
        r["texto"],
        r["titulo"],
        r["ref_canonica"],
        tuple(json.loads(r["flags"])),
        r["fim_fundido"],
    )


def _chave_ref(ref: str) -> tuple[str, int, int]:
    livro, cap, vers = ref.split(".")
    return livro, int(cap), int(vers)


class Repositorio:
    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    @classmethod
    def abrir(cls, caminho: Path | None = None) -> Repositorio:
        if caminho is None:
            from fiat_lux.config import obter_settings

            caminho = obter_settings().caminhos.biblia_db
        return cls(banco.conectar(caminho, somente_leitura=True))

    def fechar(self) -> None:
        self.con.close()

    # ------------------------------------------------------------------ básicos

    def versiculo(self, traducao: str, livro: str, cap: int, vers: int) -> Versiculo | None:
        r = self.con.execute(
            "SELECT * FROM versiculos WHERE traducao_id=? AND livro=? AND capitulo=? AND versiculo=?",
            (traducao, livro, cap, vers),
        ).fetchone()
        return _linha(r) if r else None

    def por_id(self, vid: int) -> Versiculo | None:
        r = self.con.execute("SELECT * FROM versiculos WHERE id=?", (vid,)).fetchone()
        return _linha(r) if r else None

    def capitulo(self, traducao: str, livro: str, cap: int) -> list[Versiculo]:
        rows = self.con.execute(
            "SELECT * FROM versiculos WHERE traducao_id=? AND livro=? AND capitulo=? ORDER BY versiculo",
            (traducao, livro, cap),
        ).fetchall()
        return [_linha(r) for r in rows]

    def livro(self, traducao: str, livro: str) -> list[Versiculo]:
        rows = self.con.execute(
            "SELECT * FROM versiculos WHERE traducao_id=? AND livro=? ORDER BY capitulo, versiculo",
            (traducao, livro),
        ).fetchall()
        return [_linha(r) for r in rows]

    @cached_property
    def _lacunas(self) -> dict[tuple[str, str, int, int], str]:
        rows = self.con.execute(
            "SELECT traducao_id, livro, capitulo, versiculo, status, tipo FROM lacunas"
        )
        return {
            (r[0], r[1], r[2], r[3]): f"{r[4]}:{r[5]}"
            for r in rows
            if r[4] == "aberta" or r[5] == "ausente"
        }

    def lacuna(self, traducao: str, livro: str, cap: int, vers: int) -> bool:
        return (traducao, livro, cap, vers) in self._lacunas

    # ------------------------------------------------------------------ intervalos nativos

    def versiculos_intervalo(
        self, traducao: str, iv: Intervalo, incluir_titulos: bool = False
    ) -> list[Versiculo]:
        cap_fim = iv.cap_fim or iv.cap_ini
        if iv.capitulo_inteiro:
            rows = self.con.execute(
                "SELECT * FROM versiculos WHERE traducao_id=? AND livro=? AND capitulo BETWEEN ? AND ?"
                " ORDER BY capitulo, versiculo",
                (traducao, iv.livro, iv.cap_ini, cap_fim),
            ).fetchall()
        else:
            v_fim = iv.vers_fim if iv.vers_fim is not None else iv.vers_ini
            rows = self.con.execute(
                "SELECT * FROM versiculos WHERE traducao_id=? AND livro=?"
                " AND (capitulo * 1000 + versiculo) BETWEEN ? AND ? ORDER BY capitulo, versiculo",
                (
                    traducao,
                    iv.livro,
                    iv.cap_ini * 1000 + (iv.vers_ini or 0),
                    cap_fim * 1000 + (v_fim or 999),
                ),
            ).fetchall()
        versos = [_linha(r) for r in rows]
        if not incluir_titulos:
            versos = [v for v in versos if F_TITULO_SALMO not in v.flags]
        return versos

    def get_passagem(
        self, ref: str | Intervalo | Referencia, traducao: str = "ms", esquema: str | None = None
    ) -> Passagem:
        """Texto de uma referência.

        `esquema=None`: numeração nativa da tradução. `esquema="eng"`: a referência está no
        esquema canônico e é convertida (ex.: eng Sl 23 → MS Sl 22).
        """
        if isinstance(ref, str):
            intervalos = list(parse(ref, esquema or "nativo").intervalos)
        elif isinstance(ref, Referencia):
            intervalos = list(ref.intervalos)
        else:
            intervalos = [ref]
        avisos: list[str] = []
        versos: list[Versiculo] = []
        for iv in intervalos:
            if esquema == "eng" and traducao != "blivre":
                achados = self.eng_para_nativo(traducao, iv)
            else:
                achados = self.versiculos_intervalo(traducao, iv)
            if iv.parte_ini or iv.parte_fim:
                avisos.append("partes de versículo (a/b) exibidas por inteiro")
            versos.extend(achados)
        vistos: set[int] = set()
        unicos = [v for v in versos if not (v.id in vistos or vistos.add(v.id))]  # type: ignore[func-returns-value]
        tem_lacuna = False
        if unicos:
            livro = unicos[0].livro
            caps = {v.capitulo for v in unicos}
            for cap in caps:
                nums = sorted(v.versiculo for v in unicos if v.capitulo == cap)
                for n in range(nums[0], nums[-1] + 1):
                    if self.lacuna(traducao, livro, cap, n):
                        tem_lacuna = True
                        avisos.append(f"lacuna na fonte: {por_codigo(livro).sigla_pt} {cap},{n}")
            for v in unicos:
                if v.fim_fundido:
                    avisos.append(
                        f"{v.capitulo},{v.versiculo} contém também até o v. {v.fim_fundido}"
                    )
        if not unicos:
            avisos.append("nenhum versículo encontrado")
        livro_ref = intervalos[0].livro if intervalos else ""
        return Passagem(
            traducao=traducao,
            livro=livro_ref,
            ref_formatada=self.formatar_nativo(unicos)
            if unicos
            else formatar_intervalos(livro_ref, intervalos),
            versiculos=tuple((v.capitulo, v.versiculo, v.texto) for v in unicos),
            tem_lacuna=tem_lacuna,
            avisos=tuple(dict.fromkeys(avisos)),
            refs_canonicas=tuple(v.ref_canonica for v in unicos if v.ref_canonica),
        )

    def passagem_ids(self, ids: list[int]) -> Passagem:
        versos = [v for v in (self.por_id(i) for i in ids) if v is not None]
        if not versos:
            raise KeyError("ids vazios")
        return Passagem(
            traducao=versos[0].traducao,
            livro=versos[0].livro,
            ref_formatada=self.formatar_nativo(versos),
            versiculos=tuple((v.capitulo, v.versiculo, v.texto) for v in versos),
            refs_canonicas=tuple(v.ref_canonica for v in versos if v.ref_canonica),
        )

    @staticmethod
    def formatar_nativo(versos: list[Versiculo]) -> str:
        """Forma compacta "Jo 3,16-17" (ou "Sl 22,1-6") para versículos contíguos/ordenados."""
        if not versos:
            return ""
        ivs: list[Intervalo] = []
        ini = ant = versos[0]
        fim_ant = ant.fim_fundido or ant.versiculo

        def fechar(a: Versiculo, b: Versiculo, fim_b: int) -> Intervalo:
            if a.capitulo == b.capitulo and a.versiculo == fim_b:
                return Intervalo(a.livro, a.capitulo, a.versiculo, esquema="nativo")
            return Intervalo(
                a.livro,
                a.capitulo,
                a.versiculo,
                None,
                b.capitulo if b.capitulo != a.capitulo else None,
                fim_b,
                None,
                "nativo",
            )

        for v in versos[1:]:
            contiguo = (v.capitulo == ant.capitulo and v.versiculo == fim_ant + 1) or (
                v.capitulo == ant.capitulo + 1 and v.versiculo == 1
            )
            if not contiguo:
                ivs.append(fechar(ini, ant, fim_ant))
                ini = v
            ant = v
            fim_ant = v.fim_fundido or v.versiculo
        ivs.append(fechar(ini, ant, fim_ant))
        return formatar_intervalos(versos[0].livro, ivs)

    # ------------------------------------------------------------------ conversão eng ↔ nativo

    @cached_property
    def _mapa_eng(self) -> dict[str, list[tuple[str, str | None, str]]]:
        """eng → [(ref_destino, ref_destino_fim, ref_origem_ms)] por livro (cache)."""
        por_livro: dict[str, list[tuple[str, str | None, str]]] = {}
        rows = self.con.execute(
            "SELECT ref_origem, ref_destino, ref_destino_fim FROM mapa_versificacao WHERE esquema_origem='ms-vulg'"
        )
        for origem, dest, dest_fim in rows:
            por_livro.setdefault(dest.split(".")[0], []).append((dest, dest_fim, origem))
        return por_livro

    def eng_para_nativo(self, traducao: str, iv: Intervalo) -> list[Versiculo]:
        """Versículos da tradução (MS) cujo mapeamento cai no intervalo eng."""
        if traducao == "blivre":
            return self.versiculos_intervalo(traducao, iv)
        cap_fim = iv.cap_fim or iv.cap_ini
        lo = (iv.cap_ini, iv.vers_ini or 0)
        hi = (
            cap_fim,
            iv.vers_fim
            if iv.vers_fim is not None
            else (iv.vers_ini if iv.vers_ini is not None else 999),
        )
        if iv.capitulo_inteiro:
            hi = (cap_fim, 999)
        origens: list[str] = []
        for dest, dest_fim, origem in self._mapa_eng.get(iv.livro, []):
            _, c, v = _chave_ref(dest)
            if v == 0:
                continue
            c2, v2 = (c, v) if not dest_fim else _chave_ref(dest_fim)[1:]
            if (c2, v2) >= lo and (c, v) <= hi:
                origens.append(origem)
        versos = []
        for o in origens:
            livro, cap, vers = _chave_ref(o)
            achado = self.versiculo(traducao, livro, cap, vers)
            if achado and F_TITULO_SALMO not in achado.flags:
                versos.append(achado)
        versos.sort(key=lambda x: (x.capitulo, x.versiculo))
        return versos

    def nativo_para_eng(self, traducao: str, livro: str, cap: int, vers: int) -> str | None:
        v = self.versiculo(traducao, livro, cap, vers)
        return v.ref_canonica if v else None

    # ------------------------------------------------------------------ busca e grafo

    def buscar_texto(
        self, consulta: str, traducao: str, limite: int = 50
    ) -> list[tuple[Versiculo, float]]:
        """BM25 (FTS5) sobre o texto normalizado; devolve (versículo, escore ≥ 0)."""
        termos = [t for t in normalizar_para_busca(consulta).split() if len(t) > 2]
        if not termos:
            return []
        expr = " OR ".join(f'"{t}"' for t in termos)
        rows = self.con.execute(
            "SELECT v.*, bm25(versiculos_fts) AS escore FROM versiculos_fts"
            " JOIN versiculos v ON v.id = versiculos_fts.rowid"
            " WHERE versiculos_fts MATCH ? AND v.traducao_id = ? ORDER BY escore LIMIT ?",
            (expr, traducao, limite),
        ).fetchall()
        return [(_linha(r), -float(r["escore"])) for r in rows]

    def refs_cruzadas(
        self, ref_canonica: str, min_votos: int = 5
    ) -> list[tuple[str, str | None, int]]:
        rows = self.con.execute(
            "SELECT para_ini, para_fim, votos FROM referencias_cruzadas WHERE de_ref = ? AND votos >= ?"
            " ORDER BY votos DESC",
            (ref_canonica, min_votos),
        ).fetchall()
        return [(r[0], r[1], int(r[2])) for r in rows]
