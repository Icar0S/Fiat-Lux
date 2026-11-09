"""Download fixado das fontes de dados (plano §8.1.2, passo 1; §13.1).

Cada arquivo é baixado de `raw.githubusercontent.com/<repo>/<commit SHA>/<caminho>`
(equivalente reprodutível ao clone raso + checkout do SHA) para `data/raw/<fonte>/`, num
diretório isolado. O SHA-256 de cada arquivo fica em `fontes.lock.json`; se um hash divergir,
a operação falha.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from fiat_lux.biblia.catalogo import LIVROS

USER_AGENT = "fiat-lux/0.1 (+https://github.com/Icar0S/Fiat-Lux)"
URL_RAW = "https://raw.githubusercontent.com/{repo}/{commit}/{caminho}"


class FonteAlterada(RuntimeError):
    """O hash de um arquivo não confere com o registrado em `fontes.lock.json`."""


@dataclass(frozen=True, slots=True)
class Fonte:
    id: str
    repo: str
    commit: str
    arquivos: tuple[str, ...]
    licenca: str
    descricao: str


def _arquivos_ms() -> tuple[str, ...]:
    por_livro = [
        f"{'antigotestamento' if lv.testamento == 'AT' else 'novotestamento'}/{lv.sigla_ms.lower()}.json"
        for lv in LIVROS
    ]
    return ("biblia.json", "listalivros.json", "README.md", *por_livro)


def _arquivos_blivre() -> tuple[str, ...]:
    return tuple(
        f"versoes/blivre/json/blivre-{lv.sigla_blivre}.json" for lv in LIVROS if lv.sigla_blivre
    )


FONTES: tuple[Fonte, ...] = (
    Fonte(
        id="ms",
        repo="Dancrf/biblia-db",
        commit="c5feefffc2d940efa7b11c49445c52ea1426d6a4",
        arquivos=_arquivos_ms(),
        licenca="não declarada (ver plano §13.3)",
        descricao="Bíblia Sagrada, trad. Pe. Manuel de Matos Soares (1956), 73 livros",
    ),
    Fonte(
        id="blivre",
        repo="Projeto-Euaggelion/biblia.publica",
        commit="723197403aa40be0bd82e0b5997ca6aa2832850f",
        arquivos=_arquivos_blivre(),
        licenca="CC BY (BLIVRE); projeto CC BY-SA 4.0",
        descricao="Bíblia Livre (BLIVRE), 66 livros",
    ),
    Fonte(
        id="xref",
        repo="scrollmapper/bible_databases",
        commit="59b18c5af5845728c275d5b7178ad0d024172b1f",
        arquivos=("sources/extras/cross_references.txt", "LICENSE"),
        licenca="MIT (repositório); referências cruzadas: OpenBible.info, CC BY",
        descricao="Referências cruzadas do OpenBible.info (via scrollmapper/bible_databases)",
    ),
    Fonte(
        id="vrs",
        repo="ubsicap/versification_json",
        commit="0833abd5252e810fc76e80919a3109ed9c9cc3ae",
        arquivos=(
            "examples/eng.json",
            "examples/org.json",
            "examples/vul.json",
            "examples/lxx.json",
            "LICENSE",
        ),
        licenca="MIT",
        descricao="Tabelas de versificação (eng, org, vul, lxx) da United Bible Societies",
    ),
)


def fonte(id_: str) -> Fonte:
    for f in FONTES:
        if f.id == id_:
            return f
    raise KeyError(id_)


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()


def ler_lock(caminho: Path) -> dict[str, dict[str, object]]:
    if not caminho.is_file():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    fontes: dict[str, dict[str, object]] = dados.get("fontes", {})
    return fontes


def gravar_lock(caminho: Path, fontes: dict[str, dict[str, object]]) -> None:
    conteudo = {"versao": 1, "fontes": dict(sorted(fontes.items()))}
    caminho.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    reraise=True,
)
def _baixar_bytes(cliente: httpx.Client, url: str) -> bytes:
    resp = cliente.get(url)
    resp.raise_for_status()
    return resp.content


def baixar_fontes(
    destino_raw: Path,
    caminho_lock: Path,
    ids: Iterable[str] | None = None,
    atualizar_lock: bool = False,
    cliente: httpx.Client | None = None,
    progresso: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Baixa (ou confere) os arquivos das fontes. Devolve contadores por situação."""
    lock = ler_lock(caminho_lock)
    selecionadas = [f for f in FONTES if ids is None or f.id in set(ids)]
    contadores = {"baixados": 0, "conferidos": 0}
    proprio = cliente is None
    cli = cliente or httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True
    )
    try:
        for f in selecionadas:
            entrada = lock.get(f.id, {})
            if entrada.get("commit") not in (None, f.commit) and not atualizar_lock:
                raise FonteAlterada(
                    f"{f.id}: commit do lock ({entrada.get('commit')}) difere do código ({f.commit}); "
                    "use --atualizar-lock conscientemente"
                )
            hashes_lock: dict[str, str] = dict(entrada.get("arquivos", {}))  # type: ignore[call-overload]
            novos: dict[str, str] = {}
            base = destino_raw / f.id
            for rel in f.arquivos:
                alvo = base / rel
                esperado = None if atualizar_lock else hashes_lock.get(rel)
                if alvo.is_file() and esperado and sha256_arquivo(alvo) == esperado:
                    novos[rel] = esperado
                    contadores["conferidos"] += 1
                    continue
                url = URL_RAW.format(repo=f.repo, commit=f.commit, caminho=rel)
                conteudo = _baixar_bytes(cli, url)
                digest = hashlib.sha256(conteudo).hexdigest()
                if esperado and digest != esperado:
                    raise FonteAlterada(f"{f.id}/{rel}: sha256 {digest} ≠ lock {esperado}")
                alvo.parent.mkdir(parents=True, exist_ok=True)
                alvo.write_bytes(conteudo)
                novos[rel] = digest
                contadores["baixados"] += 1
                if progresso:
                    progresso(f"{f.id}/{rel}")
            lock[f.id] = {
                "repo": f.repo,
                "commit": f.commit,
                "licenca": f.licenca,
                "descricao": f.descricao,
                "arquivos": dict(sorted(novos.items())),
            }
    finally:
        if proprio:
            cli.close()
    gravar_lock(caminho_lock, lock)
    return contadores


def verificar_fontes(destino_raw: Path, caminho_lock: Path) -> list[str]:
    """Lista problemas (ausência ou hash divergente) sem baixar nada."""
    problemas: list[str] = []
    lock = ler_lock(caminho_lock)
    for f in FONTES:
        entrada = lock.get(f.id)
        if not entrada:
            problemas.append(f"{f.id}: ausente do lock")
            continue
        arquivos: dict[str, str] = dict(entrada.get("arquivos", {}))  # type: ignore[call-overload]
        for rel in f.arquivos:
            alvo = destino_raw / f.id / rel
            if not alvo.is_file():
                problemas.append(f"{f.id}/{rel}: arquivo ausente")
            elif arquivos.get(rel) != sha256_arquivo(alvo):
                problemas.append(f"{f.id}/{rel}: hash divergente")
    return problemas
