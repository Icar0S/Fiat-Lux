"""`fiatlux configurar`: prepara o que falta e mostra o Fiat Lux funcionando.

Os scripts `configurar.ps1` (Windows) e `configurar.sh` (Linux/macOS) chamam este comando
depois de instalar as dependências, mas ele também roda sozinho. Pode ser repetido: cada etapa
usa o que já existe e só faz o que falta (as regras estão em `fiat_lux.instalacao`).
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.markup import escape
from rich.table import Table

from fiat_lux.cli.comum import console, falhar

if TYPE_CHECKING:
    from fiat_lux.config import Settings
    from fiat_lux.instalacao import SituacaoLLM
    from fiat_lux.orquestracao.diaria import ResultadoDiaria

_SIM = {"s", "sim", "y", "yes"}
_FORMATO_URL = re.compile(r"https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[A-Za-z0-9._~\-/]*)?")
_FORMATO_CHAVE = re.compile(r"[A-Za-z0-9_.:\-]{8,}")
_SEM_LLM = "a Palavra do Dia de verdade sai só com o Evangelho do dia e uma oração fixa"

# causa do ErroPermanente → (situação no resumo, o que fazer)
_CAUSAS: dict[str, tuple[str, str]] = {
    "chave": (
        "sem chave válida",
        "emitir uma chave no servidor (se ainda não tem) e pô-la na FIATLUX_LLM_CHAVE: rode o "
        "configurar de novo e cole a chave, ou edite o .env",
    ),
    "url": (
        "URL errada",
        "conferir a FIATLUX_LLM_URL: é a raiz do servidor, sem /v1 no fim",
    ),
    "conexao": (
        "inalcançável",
        "conferir a FIATLUX_LLM_URL e se o servidor está no ar (GET /v1/ready)",
    ),
    "modelo": (
        "modelo indisponível",
        "trocar o modelo no .env (FIATLUX_LLM_MODELO, ou FIATLUX_LLM_MODELO_GERACAO e os "
        "outros por tarefa) ou baixar o modelo no servidor",
    ),
}


def _etapa(titulo: str) -> None:
    console.print(f"\n[bold cyan]==> {titulo}[/]")


def _terminal_interativo() -> bool:
    """Há alguém no teclado? No Windows, `isatty()` também é verdadeiro para o `NUL` (a entrada de
    processos sem ninguém olhando), e o getpass leria direto do console, esperando para sempre:
    lá só vale um console de verdade, em que o GetConsoleMode funciona."""
    if sys.stdin is None or not sys.stdin.isatty():
        return False
    if sys.platform != "win32":
        return True
    import ctypes
    import msvcrt
    from ctypes import wintypes

    try:
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
    except (OSError, ValueError):
        return False
    modo = wintypes.DWORD()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    return bool(kernel32.GetConsoleMode(wintypes.HANDLE(handle), ctypes.byref(modo)))


def _perguntar(texto: str, secreto: bool = False) -> str:
    resposta: str = typer.prompt(texto, default="", show_default=False, hide_input=secreto)
    return resposta.strip()


def _colar_url(env: Path, pedido: str) -> bool:
    """Pede a URL do servidor de LLM e grava no .env. Devolve True se gravou."""
    from fiat_lux.instalacao import gravar_variavel_env

    url = _perguntar(pedido).rstrip("/")
    if not url:
        return False
    if url.endswith("/v1"):
        url = url[: -len("/v1")]
    if not _FORMATO_URL.fullmatch(url):
        console.print(
            "[yellow]isso não parece uma URL (ex.: https://llm.exemplo.com); não gravei.[/]"
        )
        return False
    gravar_variavel_env(env, "FIATLUX_LLM_URL", url)
    console.print("[green]URL gravada no .env[/]")
    return True


def _colar_chave(env: Path, pedido: str) -> bool:
    """Pede a chave do servidor (sem eco na tela) e grava no .env. Devolve True se gravou."""
    from fiat_lux.instalacao import gravar_variavel_env

    chave = _perguntar(pedido, secreto=True)
    if chave.lower().startswith("bearer "):
        chave = chave[len("bearer ") :].strip()
    if not chave:
        return False
    if not _FORMATO_CHAVE.fullmatch(chave):
        console.print(
            "[yellow]isso não parece uma chave (sem espaços, 8 caracteres ou mais); não gravei.[/]"
        )
        return False
    gravar_variavel_env(env, "FIATLUX_LLM_CHAVE", chave)
    console.print("[green]chave gravada no .env[/]")
    return True


def _perguntar_llm(env: Path) -> None:
    """Sem servidor, oferece configurar um. Com servidor, não pergunta: o teste logo depois diz se
    ele responde."""
    from fiat_lux.instalacao import ler_env

    if ler_env(env).get("FIATLUX_LLM_URL") or os.environ.get("FIATLUX_LLM_URL"):
        return
    console.print(
        "Servidor de LLM (opcional): a reflexão, o ensinamento e a oração são escritos por um "
        "modelo de linguagem num servidor com a API HTTP descrita no guia (seção 8). Sem ele, "
        f"{_SEM_LLM}."
    )
    if _colar_url(env, "URL do servidor (ex.: https://llm.exemplo.com; Enter para pular)"):
        _colar_chave(env, "Chave da API (não aparece na tela; Enter se o servidor não pede chave)")


def _testar_servidor(s: Settings) -> SituacaoLLM:
    from fiat_lux.instalacao import testar_llm
    from fiat_lux.llm.fabrica import llm_configurado

    if llm_configurado(s):
        console.print(f"LLM: consultando {escape(s.llm.url)}/v1/models (sem gerar texto)…")
    return testar_llm(s)


def _modelos_legiveis(sit: SituacaoLLM) -> str:
    return " · ".join(f"{tarefa}: {modelo}" for tarefa, modelo in sit.modelos)


def _explicar_llm(sit: SituacaoLLM) -> None:
    if sit.estado == "ok":
        console.print(f"[green]LLM: o servidor respondeu[/] ({escape(_modelos_legiveis(sit))})")
    elif sit.estado == "sem_servidor":
        console.print(f"LLM: sem servidor configurado por enquanto; sem ele, {_SEM_LLM}.")
    elif sit.estado == "incerto":
        console.print(
            f"[yellow]LLM: não consegui confirmar o servidor agora[/] ({escape(sit.detalhe)}); "
            "a demonstração tenta mesmo assim."
        )
    else:
        _, fazer = _CAUSAS.get(sit.causa, ("", ""))
        console.print(f"[yellow]LLM: {escape(sit.detalhe)}.[/]")
        if fazer:
            console.print(f"  O que fazer: {escape(fazer)}.")
        for var in ("FIATLUX_LLM_URL", "FIATLUX_LLM_CHAVE"):
            if os.environ.get(var):
                console.print(
                    f"  Atenção: {var} também está nas variáveis de ambiente do sistema, que "
                    "valem mais que o .env."
                )
    for aviso in sit.avisos:
        console.print(f"  aviso: {escape(aviso)}")


def _cuidar_do_llm(s: Settings, env: Path, interativo: bool) -> SituacaoLLM:
    """Testa o servidor e explica o resultado; num terminal, uma chave recusada ou uma URL errada
    podem ser trocadas na hora (salvo quando vêm de variáveis de ambiente, que o .env não
    sobrepõe)."""
    from fiat_lux.config import recarregar_settings

    sit = _testar_servidor(s)
    _explicar_llm(sit)
    if not interativo or sit.estado != "indisponivel":
        return sit
    trocou = False
    if sit.causa == "chave" and not os.environ.get("FIATLUX_LLM_CHAVE"):
        trocou = _colar_chave(
            env, "Cole a chave do servidor (não aparece na tela; Enter para pular)"
        )
    elif sit.causa in {"url", "conexao"} and not os.environ.get("FIATLUX_LLM_URL"):
        trocou = _colar_url(env, "URL certa do servidor (Enter mantém a atual)")
    if trocou:
        sit = _testar_servidor(recarregar_settings())
        _explicar_llm(sit)
    return sit


def _escolher_chats(chats: list[tuple[str, str]]) -> list[str]:
    """Quem recebe, entre as conversas que escreveram ao bot (ou digitado à mão)."""
    if not chats:
        cid = _perguntar(
            "Não achei mensagens para o bot. Digite o chat_id de quem recebe (Enter para pular)"
        )
        return [cid] if cid else []
    for i, (cid, nome) in enumerate(chats, 1):
        console.print(f"  {i}. {escape(nome)} (chat_id {cid})")
    if len(chats) == 1:
        resposta = _perguntar("Enviar a Palavra do Dia para esta conversa? [S/n]").lower()
        return [chats[0][0]] if resposta in _SIM | {""} else []
    resposta = _perguntar("Números de quem recebe, separados por vírgula (Enter = todos)")
    if not resposta:
        return [cid for cid, _ in chats]
    numeros = {int(n) for n in re.findall(r"\d+", resposta)}
    return [cid for i, (cid, _) in enumerate(chats, 1) if i in numeros]


def _perguntar_telegram(env: Path) -> None:
    import httpx

    from fiat_lux.entrega.telegram import ClienteTelegram, ErroTelegram, chats_recentes
    from fiat_lux.instalacao import gravar_variavel_env, ler_env

    valores = ler_env(env)
    if valores.get("TELEGRAM_BOT_TOKEN") and valores.get("TELEGRAM_CHAT_IDS"):
        console.print("Telegram: já configurado.")
        return
    console.print(
        "Telegram (opcional): para receber a Palavra do Dia no celular. Antes, crie um bot: no "
        "Telegram, fale com o @BotFather, envie /newbot e copie o token que ele devolve."
    )
    if _perguntar("Configurar o Telegram agora? [s/N]").lower() not in _SIM:
        return
    token = valores.get("TELEGRAM_BOT_TOKEN") or _perguntar(
        "Cole o token do bot (não aparece na tela)", secreto=True
    )
    if not re.fullmatch(r"\d+:[A-Za-z0-9_\-]{30,}", token):
        console.print(
            "[yellow]isso não parece um token do BotFather (números:letras); não gravei.[/]"
        )
        return
    cliente = ClienteTelegram(token, ())
    try:
        nome_bot = f"@{cliente.identidade().get('username', 'seu_bot')}"
        gravar_variavel_env(env, "TELEGRAM_BOT_TOKEN", token)
        console.print(f"bot {nome_bot} encontrado; token gravado no .env")
        _perguntar(
            f"Agora, no Telegram, envie qualquer mensagem para {nome_bot} e tecle Enter aqui"
        )
        ids = _escolher_chats(chats_recentes(cliente.atualizacoes()))
        if not ids or not all(re.fullmatch(r"-?\d+", c) for c in ids):
            console.print(
                "[yellow]sem destinatário por enquanto; preencha TELEGRAM_CHAT_IDS no .env "
                "quando quiser.[/]"
            )
            return
        cliente.enviar_texto(
            ids[0], "✅ Fiat Lux configurado: a Palavra do Dia vai chegar por aqui."
        )
        gravar_variavel_env(env, "TELEGRAM_CHAT_IDS", ",".join(ids))
        if not valores.get("TELEGRAM_ADMIN_CHAT_ID"):
            gravar_variavel_env(env, "TELEGRAM_ADMIN_CHAT_ID", ids[0])
        console.print(
            f"[green]Telegram configurado[/] ({len(ids)} destinatário(s)); mandei uma "
            "mensagem de teste."
        )
    except (ErroTelegram, httpx.HTTPError) as e:
        motivo = escape(str(e).replace(token, "<token>"))
        console.print(f"[yellow]o Telegram respondeu com erro: {motivo}[/]")
    finally:
        if cliente.http is not None:
            cliente.http.close()


def _linha_llm(sit: SituacaoLLM) -> tuple[str, str, str]:
    if sit.estado == "ok":
        return ("LLM", "ok", _modelos_legiveis(sit))
    if sit.estado == "sem_servidor":
        return ("LLM", "sem servidor", f"sem ele, {_SEM_LLM}")
    if sit.estado == "incerto":
        return ("LLM", "não confirmado", sit.detalhe)
    situacao, _ = _CAUSAS.get(sit.causa, ("indisponível", ""))
    return ("LLM", situacao, sit.detalhe)


def _pendencia_llm(sit: SituacaoLLM) -> str | None:
    if sit.estado == "sem_servidor":
        return (
            "Servidor de LLM: rode o configurar de novo e informe a URL e a chave quando ele "
            "perguntar (ou preencha FIATLUX_LLM_URL e FIATLUX_LLM_CHAVE no .env). Sem ele, "
            f"{_SEM_LLM}."
        )
    if sit.estado != "indisponivel":
        return None
    _, fazer = _CAUSAS.get(sit.causa, ("", "ver a mensagem acima"))
    return (
        f"LLM ({sit.detalhe}): {fazer}. Depois, rode o configurar de novo para testar. Até lá, "
        f"{_SEM_LLM}."
    )


def _linha_demonstracao(res: ResultadoDiaria, raiz: Path, offline: bool) -> tuple[str, str, str]:
    arquivo = "—"
    if res.caminho is not None:
        arquivo = str(
            res.caminho.relative_to(raiz) if res.caminho.is_relative_to(raiz) else res.caminho
        )
    if res.status == "rascunho":
        aprovadas = sum(c.ok for c in res.verificacao)
        origem = "textos de exemplo (offline)" if offline else "textos do LLM"
        return (
            "Demonstração",
            "ok",
            f"verificação {aprovadas}/{len(res.verificacao)} · {origem} · {arquivo}",
        )
    if res.status == "fallback":
        motivo = (
            f"LLM indisponível: {res.llm_indisponivel}"
            if res.llm_indisponivel
            else f"falha em {res.etapa_falha}"
        )
        return ("Demonstração", "contingência", f"{motivo} · {arquivo}")
    return ("Demonstração", res.status, "veja os avisos acima")


def _demonstrar(s: Settings, ml: bool, usar_llm: bool) -> ResultadoDiaria:
    from zoneinfo import ZoneInfo

    from fiat_lux.cli.cmd_palavra import imprimir_resultado_diaria
    from fiat_lux.orquestracao.diaria import OpcoesDiaria, executar

    _etapa("Demonstração: a Palavra do Dia de hoje, sem enviar nada (--dry-run)")
    if usar_llm:
        console.print(
            "com o servidor de LLM: alguns minutos (ele atende um pedido por vez, e a Palavra do "
            "Dia faz de 6 a 10)"
        )
    else:
        console.print(
            "sem o LLM por enquanto: a demonstração usa o cliente offline, com textos de "
            "exemplo (o resto do caminho é o de verdade)"
        )
    console.print("≈ 1 a 2 min de rerank neural em CPU" if ml else "busca lexical: ≈ 1 min")
    hoje = dt.datetime.now(ZoneInfo(s.geral.fuso)).date()
    res = executar(
        OpcoesDiaria(
            data=hoje,
            perfil=s.geral.perfil_padrao,
            dry_run=True,
            provedor_llm=None if usar_llm else "offline",
        ),
        s,
    )
    imprimir_resultado_diaria(res)
    return res


def configurar(
    sem_demonstracao: bool = typer.Option(
        False, "--sem-demonstracao", help="Não gera a Palavra do Dia de teste no fim."
    ),
    sem_perguntas: bool = typer.Option(
        False, "--sem-perguntas", help="Não pergunta o servidor de LLM nem o Telegram."
    ),
    reconstruir_indice: bool = typer.Option(
        False, "--reconstruir-indice", help="Reconstrói o índice mesmo que o atual sirva."
    ),
) -> None:
    """Prepara o que falta (.env, LLM, base bíblica, índice) e gera uma Palavra do Dia de teste.

    Pode ser repetido: cada etapa usa o que já existe e só faz o que falta.
    """
    from fiat_lux.logs import so_erros_no_console

    # as etapas e o resumo dizem o que importa; avisos de log só repetiriam os mesmos fatos
    with so_erros_no_console():
        _configurar(sem_demonstracao, sem_perguntas, reconstruir_indice)


Linha = tuple[str, str, str]  # (item, situação, detalhe) do resumo


def _configurar(sem_demonstracao: bool, sem_perguntas: bool, reconstruir_indice: bool) -> None:
    from fiat_lux import instalacao as inst
    from fiat_lux.config import raiz_projeto, recarregar_settings

    raiz = raiz_projeto()
    os.chdir(raiz)  # o .env é lido da pasta atual
    ml = inst.ml_instalado()
    env = raiz / ".env"
    resumo: list[Linha] = [_linha_modo(ml), _etapa_env(raiz)]
    llm = _etapa_chaves(env, sem_perguntas)
    s = recarregar_settings()
    resumo.append(_linha_telegram(s))
    resumo.append(_etapa_corpus(s))
    resumo.append(_etapa_indice(s, ml, reconstruir_indice))
    pendencias: list[str] = []
    falhou = False
    if sem_demonstracao:
        resumo.append(("Demonstração", "pulada", "--sem-demonstracao"))
    else:
        usar_llm = llm.estado in {"ok", "incerto"}
        res = _demonstrar(s, ml, usar_llm)
        if llm.estado == "incerto" and res.llm_causa:  # o teste não concluiu; a demonstração sim
            llm = inst.SituacaoLLM("indisponivel", res.llm_causa, res.llm_indisponivel)
        resumo.append(_linha_demonstracao(res, raiz, offline=not usar_llm))
        falhou = res.status == "falhou"
        if res.status == "fallback" and llm.estado != "indisponivel":
            pendencias.append("A demonstração saiu como contingência: veja os avisos acima dela.")
    resumo.insert(2, _linha_llm(llm))
    pendencia = _pendencia_llm(llm)
    if pendencia:
        pendencias.insert(0, pendencia)
    _fechar(resumo, pendencias, falhou)


def _linha_modo(ml: bool) -> Linha:
    if ml:
        return ("Modo", "completo", "modelos neurais (sentence-transformers)")
    return (
        "Modo",
        "leve",
        "busca lexical; para o completo, rode o script com -Modo completo (--completo)",
    )


def _etapa_env(raiz: Path) -> Linha:
    from fiat_lux.instalacao import garantir_env

    _etapa("Arquivo .env")
    if garantir_env(raiz):
        console.print("criado a partir do .env.example (o .env fica fora do git)")
        return (".env", "criado", "a partir do .env.example")
    console.print("já existe; mantido como está")
    return (".env", "ok", "já existia")


def _etapa_chaves(env: Path, sem_perguntas: bool) -> SituacaoLLM:
    from fiat_lux.config import recarregar_settings

    _etapa("Servidor de LLM e Telegram (opcional)")
    interativo = not sem_perguntas and _terminal_interativo()
    if interativo:
        _perguntar_llm(env)
    else:
        console.print(
            "sem perguntas agora (--sem-perguntas ou terminal não interativo); "
            "preencha o .env quando quiser"
        )
    llm = _cuidar_do_llm(recarregar_settings(), env, interativo)
    if interativo:
        _perguntar_telegram(env)
    return llm


def _linha_telegram(s: Settings) -> Linha:
    if s.telegram_bot_token and s.telegram_chat_ids:
        return ("Telegram", "configurado", f"{len(s.telegram_chat_ids)} destinatário(s)")
    return ("Telegram", "não configurado", "a mensagem fica em saidas/ (guia, seção 9)")


def _etapa_corpus(s: Settings) -> Linha:
    from fiat_lux.instalacao import checar_corpus

    item = "Base bíblica"
    _etapa(item)
    ok, detalhe = checar_corpus(s)
    if ok:
        console.print(f"[green]pronta[/]: {detalhe}")
        return (item, "ok", f"{detalhe} (já existia)")
    console.print(f"{detalhe}: montando agora (≈ 2 min na primeira vez)")
    from fiat_lux.cli import cmd_biblia

    cmd_biblia.baixar(fonte=[], atualizar_lock=False)
    cmd_biblia.ingerir()
    ok, detalhe = checar_corpus(s)
    if not ok:
        falhar(
            f"a base bíblica não passou na validação: {detalhe}. "
            "Detalhes: uv run fiatlux biblia validar"
        )
    console.print(f"[green]pronta[/]: {detalhe}")
    return (item, "montada", detalhe)


def _etapa_indice(s: Settings, ml: bool, reconstruir: bool) -> Linha:
    from fiat_lux import instalacao as inst

    item = "Índice de busca"
    _etapa(item)
    sit = inst.ler_situacao_indice(s.caminhos.biblia_db)
    motivo = (
        "reconstrução pedida (--reconstruir-indice)"
        if reconstruir
        else inst.motivo_reconstruir_indice(
            sit, inst.embedder_esperado(s.rag.modelo_embeddings, ml)
        )
    )
    if motivo is None:
        console.print(
            f"[green]pronto[/]: {sit.embedder}, {sit.pericopes} perícopes "
            f"(construído em {sit.construido_em})"
        )
        return (item, "ok", f"{sit.embedder}, {sit.pericopes} perícopes (já existia)")
    tempo = (
        "≈ 40 min em CPU, uma vez só; o modelo (~1,1 GB) é baixado se faltar"
        if ml
        else "≈ 1 a 2 min"
    )
    console.print(f"{motivo}: construindo agora ({tempo})")
    from fiat_lux.rag.indice import construir

    r = construir(
        s.caminhos.biblia_db,
        "neural" if ml else "lexical",
        s.rag.modelo_embeddings,
        progresso=lambda m: console.print(m),
    )
    console.print(
        f"[green]pronto[/]: {r['embedder']}, {r['pericopes']} perícopes em {r['segundos']} s"
    )
    return (item, "construído", f"{r['embedder']}, {r['pericopes']} perícopes")


def _fechar(resumo: list[Linha], pendencias: list[str], falhou: bool) -> None:
    """Tabela do resumo, o que falta fazer, como usar e o veredito (última linha)."""
    _etapa("Resumo")
    tabela = Table(header_style="bold")
    for coluna in ("Item", "Situação", "Detalhe"):
        tabela.add_column(coluna)
    for item, situacao, det in resumo:
        tabela.add_row(item, situacao, escape(det))
    console.print(tabela)
    if pendencias:
        console.print("\n[bold yellow]Falta para a Palavra do Dia sair completa:[/]")
        for p in pendencias:
            console.print(f"  • {escape(p)}")
    console.print(
        "\n[bold]Para usar[/] (na pasta do projeto):\n"
        "  uv run fiatlux palavra diaria --dry-run    gera de novo, sem enviar nada\n"
        "  uv run fiatlux palavra diaria              arquiva em saidas/ e envia pelo Telegram\n"
        "  uv run fiatlux palavra semanal --dry-run   Palavra da Semana, com gráfico\n"
        "  uv run fiatlux --help                      todos os comandos\n"
        "Servidor de LLM e Telegram: rode de novo o configurar ou edite o .env (guia, seções 8 e 9).\n"
        "Agendar todo dia às 05:00: docs/guia-do-usuario.md, seção 10."
    )
    if falhou:
        console.print("\n[bold red]A demonstração falhou[/]: veja os avisos acima.")
        raise typer.Exit(1)
    if not pendencias:
        console.print("\n[bold green]Tudo pronto.[/]")
        return
    falta = "falta 1 item" if len(pendencias) == 1 else f"faltam {len(pendencias)} itens"
    console.print(
        f"\n[bold yellow]Instalação pronta, mas {falta} (acima) para a Palavra do Dia "
        "sair completa.[/]"
    )
