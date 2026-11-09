"""Exportação do corpus em Markdown, um arquivo por capítulo (plano §8.1.7).

`data/markdown/{traducao}/{NN}-{Livro}/{Livro}-{CC}.md`, com frontmatter YAML e âncoras
`^vN` (links de bloco no Obsidian: `[[Genesis-01#^v3]]`). Cada tradução forma um cofre
próprio (os nomes de arquivo se repetem entre traduções).
"""

from __future__ import annotations

import re
import shutil
from collections import defaultdict
from pathlib import Path

import yaml

from fiat_lux.biblia import banco
from fiat_lux.biblia.catalogo import LIVROS, Livro
from fiat_lux.biblia.modelos import F_TITULO_SALMO, F_TITULO_SEPARADO, TRADUCOES

_LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


def _pasta_livro(lv: Livro, ordem: int) -> str:
    return f"{ordem:02d}-{lv.nome_arquivo}"


def _arquivo_capitulo(lv: Livro, cap: int) -> str:
    return f"{lv.nome_arquivo}-{cap:02d}" if lv.codigo != "PSA" else f"{lv.nome_arquivo}-{cap:03d}"


def exportar(caminho_db: Path, destino: Path, traducoes: list[str]) -> dict[str, int]:
    con = banco.conectar(caminho_db, somente_leitura=True)
    total = 0
    try:
        for trad in traducoes:
            t = TRADUCOES[trad]
            raiz = destino / trad
            if raiz.exists():
                shutil.rmtree(raiz)
            raiz.mkdir(parents=True)
            rows = con.execute(
                "SELECT livro, capitulo, versiculo, texto, titulo, flags, fim_fundido FROM versiculos"
                " WHERE traducao_id=? ORDER BY livro, capitulo, versiculo",
                (trad,),
            ).fetchall()
            lacunas = defaultdict(list)
            for r in con.execute(
                "SELECT livro, capitulo, versiculo, status, tipo FROM lacunas WHERE traducao_id=?",
                (trad,),
            ):
                lacunas[(r[0], r[1])].append({"versiculo": r[2], "status": r[3], "tipo": r[4]})
            por_cap: dict[tuple[str, int], list[tuple[int, str, str | None, str, int | None]]] = (
                defaultdict(list)
            )
            for r in rows:
                por_cap[(r["livro"], r["capitulo"])].append(
                    (r["versiculo"], r["texto"], r["titulo"], r["flags"], r["fim_fundido"])
                )
            livros = [lv for lv in LIVROS if any(k[0] == lv.codigo for k in por_cap)]
            sequencia: list[tuple[Livro, int]] = []
            for lv in livros:
                caps = sorted(c for (cod, c) in por_cap if cod == lv.codigo)
                sequencia.extend((lv, c) for c in caps)
            readme = [
                f"# {t.nome}\n",
                f"Fonte: `{t.fonte_repo}@{t.fonte_commit[:7]}` · licença: {t.licenca}\n",
            ]
            for ordem, lv in enumerate(livros, 1):
                pasta = raiz / _pasta_livro(lv, ordem)
                pasta.mkdir()
                caps = [c for (lv2, c) in sequencia if lv2 is lv]
                indice = [
                    "---",
                    f"traducao: {t.nome}",
                    f"livro: {lv.nome_pt}",
                    f"codigo: {lv.codigo}",
                    f"capitulos: {len(caps)}",
                    "---",
                    "",
                    f"# {lv.nome_pt}",
                    "",
                ]
                indice += [f"- [[{_arquivo_capitulo(lv, c)}|{lv.nome_pt} {c}]]" for c in caps]
                (pasta / "_index.md").write_text("\n".join(indice) + "\n", encoding="utf-8")
                readme.append(
                    f"- [[{_arquivo_capitulo(lv, caps[0])}|{lv.nome_pt}]] ({len(caps)} cap.)"
                )
            for idx, (lv, cap) in enumerate(sequencia):
                ordem = livros.index(lv) + 1
                versos = por_cap[(lv.codigo, cap)]
                anterior = sequencia[idx - 1] if idx > 0 else None
                proximo = sequencia[idx + 1] if idx + 1 < len(sequencia) else None
                fm = {
                    "traducao": t.nome,
                    "sigla_traducao": t.sigla,
                    "livro": lv.nome_pt,
                    "codigo": lv.codigo,
                    "capitulo": cap,
                    "testamento": lv.testamento,
                    "deuterocanonico": lv.deuterocanonico,
                    "versificacao": t.versificacao,
                    "versiculos": len(versos),
                    "lacunas": lacunas.get((lv.codigo, cap), []),
                    "fonte": f"{t.fonte_repo}@{t.fonte_commit[:7]}",
                    "tags": [f"biblia/{trad}/{lv.codigo.lower()}"],
                }
                linhas = [
                    "---",
                    yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip(),
                    "---",
                    "",
                ]
                linhas.append(f"# {lv.nome_pt} {cap}")
                linhas.append("")
                nav = []
                if anterior:
                    nav.append(f"[[{_arquivo_capitulo(*anterior)}|← Anterior]]")
                nav.append(f"[[{_pasta_livro(lv, ordem)}/_index|{lv.nome_pt}]]")
                if proximo:
                    nav.append(f"[[{_arquivo_capitulo(*proximo)}|Próximo →]]")
                linhas.append(" · ".join(nav))
                linhas.append("")
                for num, texto, titulo, flags, fim in versos:
                    rotulo = f"{num}-{fim}" if fim else f"{num}"
                    if F_TITULO_SALMO in flags:
                        linhas.append(f"**{rotulo}** *{texto}* ^v{num}")
                    else:
                        if F_TITULO_SEPARADO in flags and titulo:
                            linhas.append(f"*{titulo}*")
                            linhas.append("")
                        linhas.append(f"**{rotulo}** {texto} ^v{num}")
                    linhas.append("")
                pasta = raiz / _pasta_livro(lv, ordem)
                (pasta / f"{_arquivo_capitulo(lv, cap)}.md").write_text(
                    "\n".join(linhas), encoding="utf-8"
                )
                total += 1
            (raiz / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    finally:
        con.close()
    return {"arquivos": total, "links_quebrados": verificar_links(destino, traducoes)}


def verificar_links(destino: Path, traducoes: list[str]) -> int:
    """Conta wikilinks que não resolvem para um arquivo do mesmo cofre (tradução)."""
    quebrados = 0
    for trad in traducoes:
        raiz = destino / trad
        nomes = {p.stem for p in raiz.rglob("*.md")}
        for arq in raiz.rglob("*.md"):
            for alvo in _LINK.findall(arq.read_text(encoding="utf-8")):
                alvo = alvo.strip()
                ok = (raiz / f"{alvo}.md").is_file() if "/" in alvo else alvo in nomes
                if not ok:
                    quebrados += 1
    return quebrados


def validar_frontmatter(arquivo: Path) -> dict[str, object]:
    texto = arquivo.read_text(encoding="utf-8")
    if not texto.startswith("---\n"):
        raise ValueError(f"{arquivo}: sem frontmatter")
    fim = texto.index("\n---", 4)
    dados = yaml.safe_load(texto[4:fim])
    if not isinstance(dados, dict):
        raise ValueError(f"{arquivo}: frontmatter inválido")
    return dados
