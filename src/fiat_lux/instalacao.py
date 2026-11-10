"""Configuração inicial idempotente: o núcleo de `fiatlux configurar`.

Os scripts `configurar.ps1` (Windows) e `configurar.sh` (Linux/macOS) acham ou instalam o uv,
instalam as dependências e chamam `fiatlux configurar`, que usa estas funções. Cada etapa
confere o que já existe e só faz o que falta:

- a base bíblica só é remontada se a validação falhar (a ingestão recria o `biblia.sqlite` e,
  com ele, apaga o índice);
- o índice só é reconstruído se faltar, estiver incompleto ou não combinar com o ambiente:
  neural quando o extra `[ml]` está instalado, lexical quando não está. A consulta usa o
  embedder gravado no índice, então os dois precisam combinar;
- o `.env` nasce do `.env.example` e só recebe o que o usuário digitar. Chaves nunca são
  impressas;
- o servidor de LLM é testado sem inferência (`GET /v1/models`): URL errada, chave recusada ou
  modelo inexistente aparecem aqui, e não como uma Palavra do Dia de contingência.
"""

from __future__ import annotations

import importlib.util
import os
import pickle
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fiat_lux.biblia import banco
from fiat_lux.config import Settings

if TYPE_CHECKING:
    from fiat_lux.llm.servidor import ClienteServidor

# O que pode ir para o .env sem aspas: URLs, chaves de API, tokens e listas de chat_id.
_VALOR_SEGURO = re.compile(r"[A-Za-z0-9_:.,/@~+\-]*")
_NOME_VARIAVEL = re.compile(r"[A-Z][A-Z0-9_]*")


def ml_instalado() -> bool:
    """O extra `[ml]` (sentence-transformers) está instalado? Não importa o torch, que é lento."""
    return importlib.util.find_spec("sentence_transformers") is not None


def embedder_esperado(modelo: str, ml: bool) -> str:
    """Embedder que o índice deve ter neste ambiente: `neural:<modelo>` com o extra `[ml]`."""
    return f"neural:{modelo}" if ml else "lexical"


@dataclass(frozen=True, slots=True)
class SituacaoIndice:
    """O que o `biblia.sqlite` registra sobre o índice de busca."""

    embedder: str = ""  # vazio: índice nunca construído
    pericopes: int = 0  # linhas em `pericopes`
    vetores: int = 0  # linhas em `pericopes_emb`
    declarado: int = 0  # `indice_pericopes` nos metadados
    construido_em: str = ""
    lexical: Path | None = None  # arquivo do embedder lexical, quando é o caso


def _contar(con: sqlite3.Connection, tabela: str) -> int:
    try:
        return int(con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0])
    except sqlite3.OperationalError:  # tabela ausente
        return 0


def ler_situacao_indice(db: Path) -> SituacaoIndice:
    """Lê os metadados do índice; banco ausente ou ilegível conta como índice inexistente."""
    if not db.is_file():
        return SituacaoIndice()
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            meta = {str(k): str(v) for k, v in con.execute("SELECT chave, valor FROM metadados")}
            pericopes, vetores = _contar(con, "pericopes"), _contar(con, "pericopes_emb")
        finally:
            con.close()
    except sqlite3.DatabaseError:
        return SituacaoIndice()
    embedder = meta.get("indice_embedder", "")
    lexical: Path | None = None
    if embedder.startswith("lexical"):
        # mesma regra de `rag.indice.carregar_embedder`: o caminho gravado ou o vizinho do banco
        gravado = meta.get("indice_lexical", "")
        lexical = (
            Path(gravado) if gravado and Path(gravado).is_file() else db.with_name("lexical.pkl")
        )
    declarado = meta.get("indice_pericopes", "")
    return SituacaoIndice(
        embedder=embedder,
        pericopes=pericopes,
        vetores=vetores,
        declarado=int(declarado) if declarado.isdigit() else 0,
        construido_em=meta.get("indice_construido_em", ""),
        lexical=lexical,
    )


def motivo_reconstruir_indice(sit: SituacaoIndice, esperado: str) -> str | None:
    """Por que o índice precisa ser (re)construído; `None` quando o atual já serve."""
    if not sit.embedder or sit.pericopes == 0:
        return "índice ainda não construído"
    if sit.vetores != sit.pericopes or (sit.declarado and sit.declarado != sit.pericopes):
        return f"índice incompleto ({sit.vetores} vetores para {sit.pericopes} perícopes)"
    if esperado.startswith("neural:") and sit.embedder != esperado:
        return f"o índice atual é {sit.embedder}, e o modo completo usa {esperado}"
    if esperado == "lexical" and not sit.embedder.startswith("lexical"):
        return f"o índice é {sit.embedder}, mas os modelos neurais não estão instalados"
    if sit.embedder.startswith("lexical") and (sit.lexical is None or not sit.lexical.is_file()):
        return "falta o arquivo do embedder lexical (lexical.pkl)"
    return None


def checar_corpus(s: Settings) -> tuple[bool, str]:
    """(válida?, detalhe) da base bíblica, com as mesmas checagens do `fiatlux biblia validar`."""
    from fiat_lux.biblia.validacao import checar_banco, checar_contagens

    db = s.caminhos.biblia_db
    if not db.is_file():
        return False, "a base bíblica ainda não existe"
    try:
        con = banco.conectar(db, somente_leitura=True)
        try:
            checagens = checar_banco(con)
        finally:
            con.close()
    except Exception as e:  # banco parcial ou corrompido: remontar resolve
        return False, f"biblia.sqlite ilegível ({type(e).__name__}: {e})"
    resultado = s.caminhos.interim / "construcao.pkl"
    if resultado.is_file():
        try:
            checagens = checar_contagens(pickle.loads(resultado.read_bytes())) + checagens
        except Exception as e:  # resultado gravado por outra versão do código
            return False, f"resultado da última ingestão ilegível ({type(e).__name__})"
    falhas = [c.nome for c in checagens if not c.ok]
    if falhas:
        return False, f"{len(falhas)} checagem(ns) falharam ({', '.join(falhas[:3])})"
    return True, f"{len(checagens)} checagens ok"


def _restringir(caminho: Path) -> None:
    """No Linux/macOS, só o dono lê o `.env`; no Windows, a pasta do usuário já é privada."""
    if os.name == "posix":
        caminho.chmod(0o600)


def garantir_env(raiz: Path) -> bool:
    """Cria o `.env` a partir do `.env.example`, se ainda não existir. Devolve True se criou."""
    env = raiz / ".env"
    if env.exists():
        return False
    exemplo = raiz / ".env.example"
    if exemplo.is_file():
        shutil.copyfile(exemplo, env)
    else:
        env.write_bytes(b"")
    _restringir(env)
    return True


def ler_env(caminho: Path) -> dict[str, str]:
    """Variáveis do `.env`, vazias incluídas, lidas como o pydantic-settings as lê."""
    if not caminho.is_file():
        return {}
    from dotenv import dotenv_values

    return {k: v or "" for k, v in dotenv_values(caminho, encoding="utf-8").items()}


def gravar_variavel_env(caminho: Path, chave: str, valor: str) -> None:
    """Grava `CHAVE=valor` no `.env`, preservando as outras linhas, o comentário da linha e o
    tipo de quebra de linha. Só aceita valores que não precisam de aspas."""
    if not _NOME_VARIAVEL.fullmatch(chave) or not _VALOR_SEGURO.fullmatch(valor):
        raise ValueError(f"valor inesperado para {chave}")
    texto = caminho.read_bytes().decode("utf-8") if caminho.is_file() else ""
    linha = re.compile(
        rf"^{chave}[ \t]*=[^\r\n]*?(?P<comentario>[ \t]+#[^\r\n]*)?(?P<cr>\r?)$", re.MULTILINE
    )
    if linha.search(texto):
        texto = linha.sub(
            lambda m: f"{chave}={valor}{m['comentario'] or ''}{m['cr']}", texto, count=1
        )
    else:
        quebra = "\r\n" if "\r\n" in texto else "\n"
        if texto and not texto.endswith("\n"):
            texto += quebra
        texto += f"{chave}={valor}{quebra}"
    caminho.write_bytes(texto.encode("utf-8"))
    _restringir(caminho)


@dataclass(frozen=True, slots=True)
class SituacaoLLM:
    """Resultado de `testar_llm`.

    `estado`: "ok"; "sem_servidor"; "indisponivel" (não passa tentando de novo: `causa` vem do
    `ErroPermanente`, como "chave", "modelo", "url" ou "conexao"); ou "incerto" (erro passageiro:
    a demonstração tenta mesmo assim). `modelos`: (tarefa, modelo) que cada etapa vai usar.
    `avisos`: o que vale saber, como modelo fora do ar agora ou janela de contexto curta.
    """

    estado: str
    causa: str = ""
    detalhe: str = ""
    modelos: tuple[tuple[str, str], ...] = ()
    avisos: tuple[str, ...] = ()


# A seleção manda 12 passagens com contexto (≈ 5 mil tokens com o prompt e o esquema).
CONTEXTO_MINIMO = 8192
_TAREFAS = (
    ("classificacao", "classificação"),
    ("geracao", "seleção e redação"),
    ("juiz", "juiz"),
)


def testar_llm(s: Settings, cliente: ClienteServidor | None = None) -> SituacaoLLM:
    """Pergunta ao servidor quais modelos ele tem (`GET /v1/models`), sem inferência: confere a
    URL, a chave e se os modelos de cada tarefa existem e estão baixados."""
    from fiat_lux.llm.cliente import ErroLLM, ErroPermanente
    from fiat_lux.llm.fabrica import cliente_servidor, llm_configurado

    if cliente is None:
        if not llm_configurado(s):
            return SituacaoLLM("sem_servidor")
        cliente = cliente_servidor(s, timeout_s=30, espera_fila_max_s=60)
    try:
        info = cliente.modelos()
    except ErroPermanente as e:
        if e.causa == "ocupado":
            return SituacaoLLM("incerto", detalhe=e.motivo)
        return SituacaoLLM("indisponivel", e.causa, e.motivo)
    except ErroLLM as e:
        return SituacaoLLM("incerto", detalhe=str(e))
    finally:
        cliente.fechar()
    return avaliar_modelos(s, info)


def avaliar_modelos(s: Settings, info: dict[str, Any]) -> SituacaoLLM:
    """Confronta a resposta de `GET /v1/models` com os modelos configurados para cada tarefa."""
    lista = info.get("models")
    if not isinstance(lista, list):
        return SituacaoLLM(
            "incerto", detalhe="a resposta de /v1/models não traz a lista de modelos"
        )
    por_nome = {str(m["name"]): m for m in lista if isinstance(m, dict) and m.get("name")}
    padrao = str(info.get("default") or "")
    usados = tuple(
        (rotulo, getattr(s.llm, f"modelo_{campo}") or padrao or "padrão do servidor")
        for campo, rotulo in _TAREFAS
    )
    avisos: list[str] = []
    for nome in dict.fromkeys(m for _, m in usados):
        m = por_nome.get(nome)
        if m is None:
            if nome == "padrão do servidor":
                continue
            tem = ", ".join(sorted(por_nome)) or "nenhum"
            return SituacaoLLM(
                "indisponivel", "modelo", f"o servidor não tem o modelo {nome} (tem: {tem})", usados
            )
        if m.get("installed") is False:
            return SituacaoLLM(
                "indisponivel",
                "modelo",
                f"o modelo {nome} ainda não foi baixado no servidor",
                usados,
            )
        if m.get("available") is False:
            motivo = m.get("unavailable_reason") or "servidor ocupado"
            avisos.append(
                f"{nome} não está disponível agora ({motivo}); enquanto isso, o servidor usa um "
                "modelo mais leve"
            )
        contexto = int(m.get("context") or 0)
        if 0 < contexto < CONTEXTO_MINIMO:
            avisos.append(f"{nome} tem janela de {contexto} tokens; pedidos maiores serão cortados")
    return SituacaoLLM(
        "ok",
        detalhe=f"padrão do servidor: {padrao}" if padrao else "",
        modelos=usados,
        avisos=tuple(avisos),
    )
