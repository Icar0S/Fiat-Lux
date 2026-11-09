"""Manipuladores determinísticos do `ClienteOffline` (sem rede, sem chave de API).

Cada tarefa lê o JSON embutido em `<dados>…</dados>` (ou `<mensagem>`/`<evangelho>`) e
responde por regras: palavras-chave da taxonomia, maior escore, modelos de texto. Servem
para testes, `--dry-run` sem chave e como reserva quando o LLM falha.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fiat_lux.llm.cliente import Pedido
from fiat_lux.pastoral import (
    classificar_por_palavras,
    detectar_sensibilidade,
    neutralidade,
    taxonomia,
    tempos_liturgicos,
)
from fiat_lux.textos import chave, contar_palavras

LINHA_CVV = "Se você está sofrendo, fale com o CVV: 188 (ligação gratuita) ou cvv.org.br"


def embutir(dados: Any, marcador: str = "dados") -> str:
    return f"<{marcador}>\n{json.dumps(dados, ensure_ascii=False, indent=1)}\n</{marcador}>"


def extrair(texto: str, marcador: str = "dados") -> Any:
    m = re.search(rf"<{marcador}>\s*(.*?)\s*</{marcador}>", texto, re.DOTALL)
    if not m:
        return {}
    bruto = m.group(1)
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        return bruto


def _rotulo_neutro(titulo: str) -> str:
    t = re.sub(r"\s+[-–|]\s+[^-–|]{2,40}$", "", titulo).strip()
    return " ".join(t.split()[:20])


def classificacao(p: Pedido) -> dict[str, Any]:
    d = extrair(p.usuario)
    saida = []
    for g in d.get("grupos", []):
        titulos = [str(x) for x in g.get("manchetes", [])]
        cat, conf, grav = classificar_por_palavras(titulos)
        saida.append(
            {
                "id": str(g.get("id")),
                "categoria": cat,
                "gravidade": grav,
                "sensivel": detectar_sensibilidade(" ".join(titulos)),
                "rotulo": _rotulo_neutro(titulos[0]) if titulos else "",
                "confianca": conf,
            }
        )
    return {"grupos": saida}


def consultas(p: Pedido) -> dict[str, Any]:
    d = extrair(p.usuario)
    tax = taxonomia()
    saida: list[dict[str, str]] = []
    for tema in d.get("temas", [])[:3]:
        cat = tax.get(str(tema.get("categoria")), tax["outro"])
        for t in cat.temas[:1]:
            saida.append({"texto": f"Deus oferece {t} a quem sofre e espera", "origem": cat.codigo})
    tempo = str(d.get("tempo", "comum"))
    for desc in tempos_liturgicos().get(tempo, ())[:2]:
        saida.append({"texto": f"{desc} na vida de quem segue o Senhor", "origem": "tempo"})
    resumo = d.get("evangelho_resumo")
    if resumo:
        saida.append({"texto": " ".join(str(resumo).split()[:15]), "origem": "evangelho"})
    if len(saida) < 3:
        saida.append(
            {"texto": "a palavra de Deus que consola e orienta o seu povo", "origem": "tempo"}
        )
    return {"consultas": saida[:6]}


def selecao(p: Pedido) -> dict[str, Any]:
    d = extrair(p.usuario)
    cands = sorted(d.get("candidatos", []), key=lambda c: -float(c.get("escore", 0)))
    if not cands:
        return {
            "principal": "",
            "complementares": [],
            "temas_atendidos": [],
            "ligacao_liturgica": "",
            "justificativa": "sem candidatos",
            "alertas": ["sem candidatos"],
        }
    principal = cands[0]
    comp: list[dict[str, Any]] = []
    for c in cands[1:]:
        if len(comp) == 2:
            break
        if c.get("livro") == principal.get("livro") and len(cands) > 3:
            continue
        comp.append(c)
    if comp and all(c.get("testamento") == principal.get("testamento") for c in comp):
        outro = next(
            (
                c
                for c in cands[1:]
                if c.get("testamento") != principal.get("testamento") and c not in comp
            ),
            None,
        )
        if outro is not None:
            comp[-1] = outro
    while len(comp) < 2 and len(cands) > len(comp) + 1:
        extra = next(c for c in cands[1:] if c not in comp)
        comp.append(extra)
    temas = [str(t.get("categoria")) for t in d.get("temas", [])][:3]
    return {
        "principal": str(principal["id"]),
        "complementares": [str(c["id"]) for c in comp[:2]],
        "temas_atendidos": temas,
        "ligacao_liturgica": f"Em sintonia com o Evangelho ({d.get('evangelho_ref') or 'do dia'}).",
        "justificativa": "Maior escore combinado de pertinência, âncora litúrgica e diversidade (modo offline).",
        "alertas": [],
    }


COMPLEMENTOS = (
    "O Senhor caminha conosco, e cada gesto de bondade, por pequeno que seja, torna presente o seu Reino.",
    "Nada escapa ao olhar amoroso do Pai, que conhece cada um pelo nome e sustenta os que caem.",
    "Por isso, mesmo cansados, podemos recomeçar, confiantes de que a última palavra pertence à misericórdia.",
    "A oração não nos afasta da vida: devolve-nos a ela com mais coragem, mansidão e esperança.",
    "Quem se deixa tocar pela Palavra aprende a olhar o próximo como irmão, e não como ameaça.",
    "Assim, o dia que começa pode ser vivido com serenidade, atenção aos outros e confiança em Deus.",
)


def _completar(texto: str, minimo: int) -> str:
    i = 0
    while contar_palavras(texto) < minimo:
        texto = f"{texto} {COMPLEMENTOS[i % len(COMPLEMENTOS)]}"
        i += 1
    return texto


def redacao(p: Pedido) -> dict[str, Any]:
    d = extrair(p.usuario)
    temas = d.get("temas", [])
    tempo = str(d.get("tempo", "comum"))
    ev = d.get("evangelho_ref") or "o Evangelho do dia"
    sens = set(d.get("sensibilidades", []))
    # Só as categorias, nunca os rótulos: na reserva por palavras-chave o rótulo é a manchete
    # crua (pode trazer nomes de vítimas e de políticos; plano §10).
    assuntos = list(
        dict.fromkeys(ASSUNTOS[c] for t in temas if (c := str(t.get("categoria"))) in ASSUNTOS)
    )[:2]
    if assuntos:
        olhar = (
            f"O noticiário de hoje traz notícias sobre {' e sobre '.join(assuntos)}. Diante disso, "
            "não queremos ficar presos ao medo nem à indiferença: levamos tudo à presença de Deus, "
            "lembrando as pessoas por trás de cada fato e o bem comum que todos somos chamados a "
            "construir."
        )
    else:
        olhar = (
            "Hoje o noticiário não traz um acontecimento que se imponha sobre os demais. É ocasião para "
            "voltar o coração ao essencial e ouvir com calma o que o Senhor nos diz no Evangelho do dia, "
            "sem pressa e com gratidão."
        )
    if "suicidio" in sens:
        olhar += f" {LINHA_CVV}."
    reflexao = (
        "A Palavra que hoje nos é dada diz: {{P1}} "
        f"Ela ilumina o que vivemos neste tempo {tempo_extenso(tempo)} e conversa com {ev}. "
        "Deus não se afasta de quem sofre; ao contrário, aproxima-se, consola e chama à confiança. "
        "A fé não nos tira do mundo, mas nos devolve a ele com um olhar novo, capaz de reconhecer "
        "sinais de esperança mesmo onde tudo parece escuro. Quando acolhemos esta Palavra, aprendemos "
        "a não responder ao mal com o mal, a cuidar de quem está ferido e a rezar por todos, também "
        "por aqueles que têm responsabilidades sobre a vida comum."
    )
    reflexao = _completar(reflexao, 185)
    oracao = (
        "Senhor, Deus de misericórdia, olha para o teu povo neste dia. Consola os que choram, fortalece "
        "os que trabalham pelo bem e dá-nos um coração atento aos irmãos. Que a tua Palavra seja luz "
        "para os nossos passos. Por Cristo, nosso Senhor. Amém."
    )
    return {
        "olhar_sobre_o_dia": olhar,
        "reflexao": reflexao,
        "ensinamento": "Deus está perto de quem sofre e nos chama a ser sinal da sua bondade.",
        "gesto": "Reserve dez minutos hoje para rezar por uma pessoa que está passando por dificuldade e, se puder, envie-lhe uma mensagem de apoio.",
        "oracao": oracao,
    }


def tempo_extenso(tempo: str) -> str:
    return {
        "advento": "do Advento",
        "natal": "do Natal",
        "comum": "comum",
        "quaresma": "da Quaresma",
        "triduo": "do Tríduo Pascal",
        "pascoa": "pascal",
    }.get(tempo, "litúrgico")


def juiz(p: Pedido) -> dict[str, Any]:
    msg = extrair(p.usuario, "mensagem")
    texto = msg if isinstance(msg, str) else json.dumps(msg, ensure_ascii=False)
    t = " " + chave(texto) + " "
    neu = neutralidade()
    motivos: list[str] = []
    castigo = any(
        (" " + x) in t
        for x in neu.proibidas.get("castigo_divino", ()) + neu.proibidas.get("profecia", ())
    )
    if castigo:
        motivos.append("expressão de castigo divino ou leitura profética")
    partidario = any((" " + x + " ") in t for x in neu.termos_partidarios)
    if partidario:
        motivos.append("termo partidário")
    return {
        "partidario": partidario,
        "castigo_ou_profecia": castigo,
        "exposicao_vitimas": False,
        "tom_condenatorio": " condenacao eterna " in t or " inferno " in t,
        "motivos": motivos,
    }


def resumo_evangelho(p: Pedido) -> dict[str, Any]:
    texto = extrair(p.usuario, "evangelho")
    texto = texto if isinstance(texto, str) else ""
    texto = re.sub(r"[\d\[\]]+", "", texto)  # números de versículo e trechos facultativos
    frase = re.split(r"(?<=[.!?])\s", texto.strip(), maxsplit=1)[0] if texto.strip() else ""
    return {"resumo": " ".join(frase.split()[:25])}


def avaliacao(p: Pedido) -> dict[str, Any]:
    criterios = [
        "fidelidade_exegetica",
        "ligacao_liturgica",
        "pertinencia",
        "sobriedade",
        "neutralidade",
        "esperanca",
        "clareza",
        "gesto",
    ]
    return {
        "notas": [
            {"criterio": c, "nota": 4, "justificativa": "avaliação offline (heurística)"}
            for c in criterios
        ],
        "veredito": "aprova",
    }


ASSUNTOS = {
    "luto_tragedia": "luto e tragédias",
    "violencia": "violência",
    "guerra_conflito": "guerras e conflitos",
    "injustica_pobreza": "injustiça e pobreza",
    "poder_bem_comum": "a vida pública",
    "saude_doenca": "saúde",
    "criacao_clima": "o clima e a criação",
    "migracao_refugio": "migrantes e refugiados",
    "familia_juventude": "família e juventude",
    "medo_incerteza": "incertezas econômicas",
    "verdade_desinformacao": "verdade e desinformação",
    "perseguicao_religiosa": "perseguição religiosa",
    "esperanca_reconstrucao": "reconstrução e esperança",
    "alegria_conquista": "conquistas e alegrias",
    "igreja_fe": "a vida da Igreja",
}


def semanal(p: Pedido) -> dict[str, Any]:
    """Frase neutra a partir das categorias (nunca das manchetes) + perguntas fixas."""
    d = extrair(p.usuario)
    assuntos = list(
        dict.fromkeys(
            ASSUNTOS[c] for t in d.get("temas", []) if (c := str(t.get("categoria"))) in ASSUNTOS
        )
    )[:2]
    frase = (
        f"Uma semana marcada por notícias sobre {' e '.join(assuntos)}, que levamos à presença de Deus."
        if assuntos
        else "Uma semana de trabalho e de esperança, que entregamos nas mãos de Deus."
    )
    ev = d.get("evangelho_ref") or "o Evangelho do domingo"
    return {
        "frase": frase,
        "perguntas": [
            f"O que {ev} diz à minha vida nesta semana?",
            "Onde percebi Deus agindo nos acontecimentos destes dias?",
            "Que gesto concreto posso assumir, em família ou comunidade, na próxima semana?",
        ],
    }


MANIPULADORES = {
    "semanal": semanal,
    "classificacao": classificacao,
    "consultas": consultas,
    "selecao": selecao,
    "redacao": redacao,
    "juiz": juiz,
    "resumo_evangelho": resumo_evangelho,
    "avaliacao": avaliacao,
}
