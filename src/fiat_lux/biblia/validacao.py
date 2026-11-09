"""Validação do corpus e relatório de qualidade (plano §8.1.3 e §8.1.4)."""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from fiat_lux.biblia.catalogo import por_codigo
from fiat_lux.biblia.construcao import ResultadoConstrucao
from fiat_lux.textos import chave

CONTAGENS_BRUTAS_ESPERADAS = {
    "ms": (73, 1334, 35624),
    "blivre": (66, 1189, 31101),
}  # BLIVRE junta 3Jo 1,15 e Ap 12,18

# (tradução, livro, cap, vers, trecho esperado) — comparação sem acentos/maiúsculas
ANCORAS_TEXTO: tuple[tuple[str, str, int, int, str], ...] = (
    ("ms", "GEN", 1, 1, "No princípio criou Deus"),
    ("ms", "GEN", 1, 3, "Exista a luz"),
    ("ms", "PSA", 22, 1, "apascenta"),
    ("ms", "PSA", 136, 1, "rios de Babilônia"),
    ("ms", "JHN", 3, 16, "Deus amou"),
    ("blivre", "JHN", 3, 16, "Deus amou"),
    ("ms", "BAR", 6, 1, "cativos a Babil"),
    ("blivre", "PSA", 23, 1, "SENHOR é meu pastor"),
)

# (ref MS, ref eng esperada, fenômeno) — afirmadas pelo mapa (alinhamento por texto)
ANCORAS_VERSIFICACAO: tuple[tuple[str, str, str], ...] = (
    ("PSA.22.1", "PSA.23.1", "deslocamento de capítulo (título fundido)"),
    ("PSA.9.2", "PSA.9.1", "título contado como versículo"),
    ("PSA.9.22", "PSA.10.1", "fusão Sl 9+10 na Vulgata"),
    ("PSA.50.3", "PSA.51.1", "título em dois versículos"),
    ("PSA.113.9", "PSA.115.1", "fusão Sl 114+115"),
    ("PSA.114.1", "PSA.116.1", "divisão do Sl 116"),
    ("PSA.115.10", "PSA.116.10", "divisão do Sl 116 (numeração continua do Sl 114)"),
    ("PSA.136.1", "PSA.137.1", "deslocamento"),
    ("PSA.138.1", "PSA.139.1", "título fundido"),
    ("PSA.146.1", "PSA.147.1", "divisão do Sl 147"),
    ("PSA.147.12", "PSA.147.12", "divisão do Sl 147 (numeração continua do Sl 146)"),
    ("DAN.3.91", "DAN.3.24", "acréscimo grego antes (Dn 3,24-90)"),
    ("DAN.3.98", "DAN.4.1", "Dn 3,98-100 = eng 4,1-3"),
    ("MAL.4.1", "MAL.4.1", "Malaquias com 4 capítulos"),
    ("JHN.3.16", "JHN.3.16", "identidade"),
)


@dataclass(frozen=True, slots=True)
class Checagem:
    nome: str
    ok: bool
    detalhe: str


def checar_banco(con: sqlite3.Connection) -> list[Checagem]:
    saida: list[Checagem] = []
    for trad, livro, cap, vers, trecho in ANCORAS_TEXTO:
        row = con.execute(
            "SELECT texto FROM versiculos WHERE traducao_id=? AND livro=? AND capitulo=? AND versiculo=?",
            (trad, livro, cap, vers),
        ).fetchone()
        ok = row is not None and chave(trecho) in chave(row["texto"])
        saida.append(
            Checagem(
                f"âncora {trad} {livro} {cap},{vers}", ok, row["texto"][:70] if row else "ausente"
            )
        )
    for ref_ms, esperado, fenomeno in ANCORAS_VERSIFICACAO:
        row = con.execute(
            "SELECT ref_destino, ref_destino_fim, metodo, confianca FROM mapa_versificacao"
            " WHERE esquema_origem='ms-vulg' AND ref_origem=?",
            (ref_ms,),
        ).fetchone()
        ok = row is not None and row["ref_destino"] == esperado
        det = (
            f"→ {row['ref_destino']}{'–' + row['ref_destino_fim'] if row['ref_destino_fim'] else ''}"
            f" ({row['metodo']}, {row['confianca']:.2f}) — {fenomeno}"
            if row
            else f"sem mapeamento — {fenomeno}"
        )
        saida.append(Checagem(f"versificação {ref_ms}→{esperado}", ok, det))
    for ref in ("DAN.3.24", "DAN.13.1", "EST.11.2"):
        livro, cap_txt, vers_txt = ref.split(".")
        row = con.execute(
            "SELECT flags FROM versiculos WHERE traducao_id='ms' AND livro=? AND capitulo=? AND versiculo=?",
            (livro, int(cap_txt), int(vers_txt)),
        ).fetchone()
        ok = row is not None and "deutero_trecho" in row["flags"]
        saida.append(
            Checagem(f"acréscimo grego {ref} marcado", ok, row["flags"] if row else "ausente")
        )
    return saida


def checar_contagens(res: ResultadoConstrucao) -> list[Checagem]:
    saida = []
    for trad, esperado in CONTAGENS_BRUTAS_ESPERADAS.items():
        obtido = res.contagens_brutas.get(trad)
        saida.append(
            Checagem(
                f"contagem bruta {trad}", obtido == esperado, f"{obtido} (esperado {esperado})"
            )
        )
    return saida


def _tabela(cab: list[str], linhas: list[list[str]]) -> str:
    out = ["| " + " | ".join(cab) + " |", "|" + "|".join("---" for _ in cab) + "|"]
    out += ["| " + " | ".join(lin) + " |" for lin in linhas]
    return "\n".join(out)


def gerar_relatorio(res: ResultadoConstrucao, checagens: list[Checagem], destino: Path) -> str:
    cob = res.cobertura
    lac_status = Counter((x.status, x.tipo) for x in res.lacunas)
    prioritarias = [x for x in res.lacunas if por_codigo(x.livro).prioritario]
    prior_resolvidas = sum(1 for x in prioritarias if x.status in {"corrigida", "aceita"})
    por_livro = Counter(x.livro for x in res.lacunas if x.status == "aberta")
    partes: list[str] = []
    partes.append("# Qualidade do corpus bíblico\n")
    partes.append(
        "> Relatório gerado por `fiatlux biblia relatorio` (não edite à mão). "
        "Fontes fixadas em `fontes.lock.json`.\n"
    )
    partes.append("## Contagens\n")
    linhas = []
    for trad in ("ms", "blivre"):
        b = res.contagens_brutas.get(trad, (0, 0, 0))
        f = res.contagens_finais.get(trad, (0, 0, 0))
        linhas.append([trad, str(b[0]), str(b[1]), str(b[2]), str(f[2])])
    partes.append(
        _tabela(
            ["Tradução", "Livros", "Capítulos", "Versículos (brutos)", "Versículos (finais)"],
            linhas,
        )
    )
    partes.append("\n## Checagens\n")
    ok = sum(c.ok for c in checagens)
    partes.append(f"**{ok}/{len(checagens)} aprovadas.**\n")
    partes.append(
        _tabela(
            ["Checagem", "OK", "Detalhe"],
            [[c.nome, "✅" if c.ok else "❌", c.detalhe.replace("|", "/")] for c in checagens],
        )
    )
    partes.append("\n## Versificação MS → eng\n")
    partes.append(
        f"- Versículos protocanônicos da MS (sem títulos e acréscimos gregos): **{int(cob.get('protocanonicos', 0))}**\n"
        f"- Mapeados: **{cob.get('protocanonicos_mapeados', 0):.2%}**\n"
        f"- Mapeados com confiança ≥ 0,8: **{cob.get('protocanonicos_conf08', 0):.2%}** (meta ≥ 99%)\n"
    )
    metodos = Counter(m.metodo for m in res.mapa)
    partes.append("Métodos: " + ", ".join(f"{k} {v}" for k, v in metodos.most_common()) + "\n")
    baixa = [m for m in res.mapa if m.confianca < 0.8 and not m.ref_destino.endswith(".0")]
    if baixa:
        partes.append(f"\nMapeamentos de baixa confiança ({len(baixa)}; primeiros 40):\n")
        partes.append(
            _tabela(
                ["MS", "eng", "Método", "Conf."],
                [
                    [
                        m.ref_origem,
                        m.ref_destino + (f"–{m.ref_destino_fim}" if m.ref_destino_fim else ""),
                        m.metodo,
                        f"{m.confianca:.2f}",
                    ]
                    for m in baixa[:40]
                ],
            )
        )
    if res.sem_correspondente_bl:
        partes.append(
            f"\nVersículos da BLIVRE sem par na MS: {len(res.sem_correspondente_bl)} "
            f"(ex.: {', '.join(res.sem_correspondente_bl[:15])})\n"
        )
    partes.append("\n## Títulos de salmos (MS)\n")
    partes.append(", ".join(f"{k}: {v}" for k, v in res.titulos.items()) + "\n")
    partes.append("\n## Lacunas (versículos ausentes na numeração da MS)\n")
    partes.append(
        f"Total: **{len(res.lacunas)}**. Nos livros prioritários (Evangelhos, Salmos, Sapienciais, "
        f"Profetas maiores): {len(prioritarias)}, das quais **{prior_resolvidas}** corrigidas ou aceitas "
        f"({(prior_resolvidas / len(prioritarias)) if prioritarias else 1:.0%}).\n"
    )
    partes.append(
        _tabela(
            ["Status", "Tipo", "Qtde"], [[s, t, str(n)] for (s, t), n in sorted(lac_status.items())]
        )
    )
    if por_livro:
        partes.append(
            "\nAbertas por livro: "
            + ", ".join(f"{k} {v}" for k, v in por_livro.most_common())
            + "\n"
        )
    abertas = [x for x in res.lacunas if x.status == "aberta"]
    if abertas:
        partes.append(
            "\nLacunas abertas (perícopes que as atravessam ficam fora da seleção): "
            + ", ".join(f"{x.livro} {x.capitulo},{x.versiculo}" for x in abertas[:80])
            + ("…" if len(abertas) > 80 else "")
            + "\n"
        )
    partes.append("\n## Divisões automáticas de versículos fundidos\n")
    aplicadas = [d for d in res.divisoes if d.aplicada]
    partes.append(f"{len(aplicadas)} aplicadas de {len(res.divisoes)} candidatas.\n")
    if res.divisoes:
        partes.append(
            _tabela(
                ["Ref (MS)", "sim1", "sim2", "Aplicada", "Início da 2ª parte"],
                [
                    [
                        f"{d.livro} {d.capitulo},{d.versiculo}",
                        f"{d.sim1:.2f}",
                        f"{d.sim2:.2f}",
                        "sim" if d.aplicada else "não",
                        d.trecho2.replace("|", "/"),
                    ]
                    for d in res.divisoes[:60]
                ],
            )
        )
    partes.append("\n## Duplicados resolvidos\n")
    partes.append(
        _tabela(
            ["Ref", "Ocorrências", "Método", "Detalhe"],
            [
                [f"{d.livro} {d.capitulo},{d.versiculo}", str(d.ocorrencias), d.metodo, d.detalhe]
                for d in res.decisoes_duplicados
            ],
        )
    )
    if res.log_edicoes:
        partes.append("\nEdições manuais: " + "; ".join(res.log_edicoes) + "\n")
    partes.append("\n## Limpeza (ocorrências por regra)\n")
    for trad, cont in res.limpeza.items():
        partes.append(
            f"- **{trad}**: "
            + (", ".join(f"{k} {v}" for k, v in cont.most_common()) or "nenhuma")
            + "\n"
        )
    partes.append("\n## Arquivos por livro × `biblia.json` (MS)\n")
    div = [d for d in res.diffs_por_livro if d.divergentes or d.so_no_arquivo or d.so_na_biblia]
    partes.append(
        f"{len(div)} de {len(res.diffs_por_livro)} livros com diferenças (não usados como fonte).\n"
    )
    partes.append(
        _tabela(
            ["Livro", "Nome no arquivo", "Divergentes", "Só no arquivo", "Só no biblia.json"],
            [
                [
                    d.codigo,
                    d.nome_arquivo,
                    str(d.divergentes),
                    str(d.so_no_arquivo),
                    str(d.so_na_biblia),
                ]
                for d in div
            ],
        )
    )
    partes.append(f"\n\nReferências cruzadas importadas: {res.xrefs}.\n")
    texto = "\n".join(partes)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return texto
