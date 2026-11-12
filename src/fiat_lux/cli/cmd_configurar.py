"""`fiatlux configurar`: prepara o que falta e mostra o Fiat Lux funcionando.

Os scripts `configurar.ps1` (Windows) e `configurar.sh` (Linux/macOS) chamam este comando
depois de instalar as dependências, mas ele também roda sozinho. Pode ser repetido: cada etapa
usa o que já existe e só faz o que falta (as regras estão em `fiat_lux.instalacao`). O visual
(logo, etapas, andamento, resumo) vem de `fiat_lux.cli.visual`.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import RenderableType
from rich.text import Text

from fiat_lux.cli import visual as v
from fiat_lux.cli.comum import falhar

if TYPE_CHECKING:
    from fiat_lux.config import Settings
    from fiat_lux.instalacao import SituacaoLLM
    from fiat_lux.orquestracao.diaria import ResultadoDiaria

_SIM = {"s", "sim", "y", "yes"}
_FORMATO_URL = re.compile(r"https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[A-Za-z0-9._~\-/]*)?")
_FORMATO_CHAVE = re.compile(r"[A-Za-z0-9_.:\-]{8,}")
_FORMATO_EMAIL = re.compile(r"[^@\s,;]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_FORMATO_HOST = re.compile(r"[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+")
# servidor de envio (SMTP) dos provedores mais comuns, pelo domínio do e-mail
_SMTP_CONHECIDOS = {
    "gmail.com": ("smtp.gmail.com", 587),
    "googlemail.com": ("smtp.gmail.com", 587),
}
_SEM_LLM = "a Palavra do Dia de verdade sai só com o Evangelho do dia e uma oração fixa"
_DEMONSTRACAO = "Demonstração"

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
    "lento": (
        "lento demais para o proxy",
        "usar um modelo que responda mais rápido, sem raciocinar antes (FIATLUX_LLM_MODELO no "
        ".env), ou desligar o raciocínio (FIATLUX_LLM_SEM_RACIOCINIO; no qwen3, /no_think); se "
        "o servidor está na mesma rede, apontar a FIATLUX_LLM_URL para ele direto, sem o proxy "
        "(guia, seção 8)",
    ),
    "ocupado": (
        "ocupado",
        "rodar de novo com o servidor mais livre (GET /v1/status mostra a fila) e conferir se "
        "outra execução do Fiat Lux não está rodando ao mesmo tempo",
    ),
}

_PROXIMOS_PASSOS = (
    ("uv run fiatlux palavra diaria --dry-run", "gera de novo, sem enviar nada"),
    ("uv run fiatlux palavra diaria", "arquiva em saidas/ e envia por e-mail"),
    ("uv run fiatlux palavra semanal --dry-run", "Palavra da Semana, com gráfico"),
    ("uv run fiatlux configurar --email", "configura ou troca o e-mail"),
    ("uv run fiatlux --help", "todos os comandos"),
)


@dataclass(frozen=True, slots=True)
class Linha:
    """Uma linha do resumo. `nivel`: ok, aviso, erro ou neutro (dá o ícone e a cor)."""

    item: str
    situacao: str
    detalhe: str
    nivel: str = "ok"

    def tupla(self) -> tuple[str, str, str, str]:
        return (self.item, self.situacao, self.detalhe, self.nivel)


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
    resposta: str = typer.prompt(
        v.prompt(texto), default="", show_default=False, hide_input=secreto
    )
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
        v.aviso("isso não parece uma URL (ex.: https://llm.exemplo.com); não gravei")
        return False
    gravar_variavel_env(env, "FIATLUX_LLM_URL", url)
    v.ok("URL gravada no .env")
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
        v.aviso("isso não parece uma chave (sem espaços, 8 caracteres ou mais); não gravei")
        return False
    gravar_variavel_env(env, "FIATLUX_LLM_CHAVE", chave)
    v.ok("chave gravada no .env")
    return True


def _perguntar_llm(env: Path) -> None:
    """Sem servidor, oferece configurar um. Com servidor, não pergunta: o teste logo depois diz se
    ele responde."""
    from fiat_lux.instalacao import ler_env

    if ler_env(env).get("FIATLUX_LLM_URL") or os.environ.get("FIATLUX_LLM_URL"):
        return
    v.info(
        "Servidor de LLM (opcional): a reflexão, o ensinamento e a oração são escritos por um "
        "modelo de linguagem num servidor com a API HTTP descrita no guia (seção 8). Sem ele, "
        f"{_SEM_LLM}."
    )
    if _colar_url(env, "URL do servidor (ex.: https://llm.exemplo.com; Enter para pular)"):
        _colar_chave(env, "Chave da API (não aparece na tela; Enter se o servidor não pede chave)")


def _testar_servidor(s: Settings) -> SituacaoLLM:
    from fiat_lux.instalacao import testar_llm
    from fiat_lux.llm.fabrica import llm_configurado

    if not llm_configurado(s):
        return testar_llm(s)
    with v.andamento(f"consultando {s.llm.url}/v1/models (sem gerar texto)"):
        return testar_llm(s)


def _modelos_legiveis(sit: SituacaoLLM) -> str:
    return " · ".join(f"{tarefa}: {modelo}" for tarefa, modelo in sit.modelos)


def _explicar_llm(sit: SituacaoLLM) -> None:
    if sit.estado == "ok":
        v.ok(
            Text.assemble(
                ("LLM: o servidor respondeu ", "bold"), (f"({_modelos_legiveis(sit)})", v.APAGADO)
            )
        )
    elif sit.estado == "sem_servidor":
        v.aviso(f"LLM: sem servidor configurado por enquanto; sem ele, {_SEM_LLM}.")
    elif sit.estado == "incerto":
        v.aviso(
            f"LLM: não consegui confirmar o servidor agora ({sit.detalhe}); a demonstração "
            "tenta mesmo assim."
        )
    else:
        _, fazer = _CAUSAS.get(sit.causa, ("", ""))
        v.erro(f"LLM: {sit.detalhe}.")
        if fazer:
            v.dica(f"O que fazer: {fazer}.")
        for var in ("FIATLUX_LLM_URL", "FIATLUX_LLM_CHAVE"):
            if os.environ.get(var):
                v.dica(
                    f"Atenção: {var} também está nas variáveis de ambiente do sistema, que "
                    "valem mais que o .env."
                )
    for aviso in sit.avisos:
        v.aviso(aviso)


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
        v.info(f"{i}. {nome} (chat_id {cid})")
    if len(chats) == 1:
        resposta = _perguntar("Enviar a Palavra do Dia para esta conversa? [S/n]").lower()
        return [chats[0][0]] if resposta in _SIM | {""} else []
    resposta = _perguntar("Números de quem recebe, separados por vírgula (Enter = todos)")
    if not resposta:
        return [cid for cid, _ in chats]
    numeros = {int(n) for n in re.findall(r"\d+", resposta)}
    return [cid for i, (cid, _) in enumerate(chats, 1) if i in numeros]


def _com_atual(pedido: str, atual: str) -> str:
    """O pedido com o valor atual entre parênteses: Enter o mantém."""
    return f"{pedido} (Enter = {atual})" if atual else pedido


def _dados_smtp(remetente: str, atual: dict[str, str]) -> tuple[str, int] | None:
    """Servidor e porta de envio: os do provedor, se conhecido; senão, perguntados (Enter
    mantém os atuais)."""
    dominio = remetente.rsplit("@", 1)[1].lower()
    if dominio in _SMTP_CONHECIDOS:
        host, porta = _SMTP_CONHECIDOS[dominio]
        v.info(f"servidor de envio: {host}, porta {porta}")
        if host == "smtp.gmail.com":
            v.dica(
                "No Gmail, a senha é uma senha de app, não a da conta: ligue a verificação em "
                "duas etapas e crie a senha em myaccount.google.com/apppasswords (16 letras)."
            )
        return host, porta
    host_atual = atual.get("SMTP_HOST", "")
    host = (
        _perguntar(
            _com_atual(
                "Servidor de envio (SMTP) do seu provedor, ex.: smtp.provedor.com.br", host_atual
            )
        )
        or host_atual
    )
    if not _FORMATO_HOST.fullmatch(host):
        v.aviso("isso não parece um servidor (ex.: smtp.provedor.com.br); não gravei")
        return None
    porta_atual = atual.get("SMTP_PORT") or "587"
    resposta = (
        _perguntar(f"Porta (Enter = {porta_atual}; 465 se o provedor pede SSL)") or porta_atual
    )
    if not resposta.isdigit() or not 0 < int(resposta) < 65536:
        v.aviso("porta inválida; não gravei")
        return None
    return host, int(resposta)


def _quer_configurar_email(valores: dict[str, str], direto: bool) -> bool:
    """Sempre pergunta: sem e-mail, se configura agora (Enter = sim); com e-mail, se troca.
    `direto` (configurar --email) vai às perguntas sem confirmar."""
    remetente = valores.get("EMAIL_REMETENTE") or valores.get("SMTP_USUARIO") or ""
    para = [x for x in valores.get("EMAIL_DESTINATARIOS", "").split(",") if x.strip()]
    if valores.get("SMTP_HOST") and para:
        v.ok(f"E-mail: configurado, enviando de {remetente} para {len(para)} destinatário(s).")
        if direto:
            v.info("Enter mantém o que está entre parênteses.")
            return True
        return _perguntar("Trocar a configuração do e-mail? [s/N]").lower() in _SIM
    if direto:
        return True
    v.info(
        "E-mail: é por ele que a Palavra do Dia chega, todo dia. O envio sai da sua conta de "
        "e-mail (SMTP); no Gmail, com uma senha de app."
    )
    if _perguntar("Configurar o e-mail agora? [S/n]").lower() in _SIM | {""}:
        return True
    v.dica("Quando quiser: uv run fiatlux configurar --email")
    return False


def _perguntar_email(env: Path, direto: bool = False) -> None:
    """E-mail de quem envia, servidor, senha e quem recebe; grava no .env só depois de entrar na
    conta e mandar um e-mail de teste. Enter mantém o valor atual."""
    from fiat_lux.entrega.email import ClienteEmail, ErroEmail, mascarar
    from fiat_lux.instalacao import gravar_variavel_env, ler_env

    valores = ler_env(env)
    if not _quer_configurar_email(valores, direto):
        return
    remetente_atual = valores.get("EMAIL_REMETENTE") or valores.get("SMTP_USUARIO") or ""
    remetente = (
        _perguntar(_com_atual("Seu e-mail, que vai enviar (ex.: voce@gmail.com)", remetente_atual))
        or remetente_atual
    )
    if not _FORMATO_EMAIL.fullmatch(remetente):
        v.aviso("isso não parece um e-mail; não gravei")
        return
    smtp = _dados_smtp(remetente, valores)
    if smtp is None:
        return
    host, porta = smtp
    senha_atual = valores.get("SMTP_SENHA", "") if remetente == remetente_atual else ""
    pedido = "Senha (não aparece na tela" + ("; Enter = a atual)" if senha_atual else ")")
    senha = _perguntar(pedido, secreto=True) or senha_atual
    if host == "smtp.gmail.com":
        senha = senha.replace(" ", "")  # a senha de app aparece em 4 grupos de 4 letras
    if not senha:
        v.aviso("sem senha; não gravei")
        return
    para_atual = valores.get("EMAIL_DESTINATARIOS", "")
    resposta = _perguntar(
        "Quem recebe (e-mails separados por vírgula; Enter = " + (para_atual or "o seu") + ")"
    )
    lista = (resposta or para_atual or remetente).replace(";", ",").split(",")
    para = [x.strip() for x in lista if x.strip()]
    if not para or not all(_FORMATO_EMAIL.fullmatch(x) for x in para):
        v.aviso("algum destinatário não parece um e-mail; não gravei")
        return
    cliente = ClienteEmail(host, porta, remetente, senha, remetente)
    try:
        with v.andamento(f"entrando na conta em {host} e mandando um e-mail de teste"):
            cliente.enviar(
                para[0],
                "Fiat Lux configurado",
                "✅ Fiat Lux configurado: a Palavra do Dia vai chegar por aqui, todo dia.",
            )
    except ErroEmail as e:
        v.aviso(f"e-mail: {e.motivo}. Não gravei nada; rode o configurar de novo para tentar.")
        return
    try:  # a senha primeiro: se ela não cabe no .env, nada fica pela metade
        gravar_variavel_env(env, "SMTP_SENHA", senha, aspas=True)
    except ValueError:
        v.aviso(
            "a senha tem aspas simples, barra invertida ou ${, que o .env não guarda como estão; "
            "não gravei nada (troque a senha, ou preencha SMTP_* à mão no .env)"
        )
        return
    for chave, valor in (
        ("SMTP_HOST", host),
        ("SMTP_PORT", str(porta)),
        ("SMTP_USUARIO", remetente),
        ("EMAIL_REMETENTE", remetente),
        ("EMAIL_DESTINATARIOS", ",".join(para)),
    ):
        gravar_variavel_env(env, chave, valor)
    v.ok(
        f"e-mail configurado ({len(para)} destinatário(s)); mandei um e-mail de teste para "
        f"{mascarar(para[0])}: confira a caixa de entrada (e o spam)."
    )


def _perguntar_telegram(env: Path) -> None:
    import httpx

    from fiat_lux.entrega.telegram import ClienteTelegram, ErroTelegram, chats_recentes
    from fiat_lux.instalacao import gravar_variavel_env, ler_env

    valores = ler_env(env)
    if valores.get("TELEGRAM_BOT_TOKEN") and valores.get("TELEGRAM_CHAT_IDS"):
        v.ok("Telegram: já configurado.")
        return
    v.info(
        "Telegram (opcional): para receber a Palavra do Dia no celular. Antes, crie um bot: no "
        "Telegram, fale com o @BotFather, envie /newbot e copie o token que ele devolve."
    )
    if _perguntar("Configurar o Telegram agora? [s/N]").lower() not in _SIM:
        return
    token = valores.get("TELEGRAM_BOT_TOKEN") or _perguntar(
        "Cole o token do bot (não aparece na tela)", secreto=True
    )
    if not re.fullmatch(r"\d+:[A-Za-z0-9_\-]{30,}", token):
        v.aviso("isso não parece um token do BotFather (números:letras); não gravei")
        return
    cliente = ClienteTelegram(token, ())
    try:
        nome_bot = f"@{cliente.identidade().get('username', 'seu_bot')}"
        gravar_variavel_env(env, "TELEGRAM_BOT_TOKEN", token)
        v.ok(f"bot {nome_bot} encontrado; token gravado no .env")
        _perguntar(
            f"Agora, no Telegram, envie qualquer mensagem para {nome_bot} e tecle Enter aqui"
        )
        ids = _escolher_chats(chats_recentes(cliente.atualizacoes()))
        if not ids or not all(re.fullmatch(r"-?\d+", c) for c in ids):
            v.aviso(
                "sem destinatário por enquanto; preencha TELEGRAM_CHAT_IDS no .env quando quiser"
            )
            return
        cliente.enviar_texto(
            ids[0], "✅ Fiat Lux configurado: a Palavra do Dia vai chegar por aqui."
        )
        gravar_variavel_env(env, "TELEGRAM_CHAT_IDS", ",".join(ids))
        if not valores.get("TELEGRAM_ADMIN_CHAT_ID"):
            gravar_variavel_env(env, "TELEGRAM_ADMIN_CHAT_ID", ids[0])
        v.ok(f"Telegram configurado ({len(ids)} destinatário(s)); mandei uma mensagem de teste.")
    except (ErroTelegram, httpx.HTTPError) as e:
        v.aviso(f"o Telegram respondeu com erro: {str(e).replace(token, '<token>')}")
    finally:
        if cliente.http is not None:
            cliente.http.close()


def _linha_llm(sit: SituacaoLLM) -> Linha:
    if sit.estado == "ok":
        return Linha("LLM", "ok", _modelos_legiveis(sit))
    if sit.estado == "sem_servidor":
        return Linha("LLM", "sem servidor", f"sem ele, {_SEM_LLM}", "aviso")
    if sit.estado == "incerto":
        return Linha("LLM", "não confirmado", sit.detalhe, "aviso")
    situacao, _ = _CAUSAS.get(sit.causa, ("indisponível", ""))
    return Linha("LLM", situacao, sit.detalhe, "aviso")


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


def _linha_demonstracao(res: ResultadoDiaria, raiz: Path, offline: bool) -> Linha:
    arquivo = "—"
    if res.caminho is not None:
        arquivo = str(
            res.caminho.relative_to(raiz) if res.caminho.is_relative_to(raiz) else res.caminho
        )
    if res.status == "rascunho":
        aprovadas = sum(c.ok for c in res.verificacao)
        origem = "textos de exemplo (offline)" if offline else "textos do LLM"
        return Linha(
            _DEMONSTRACAO,
            "ok",
            f"verificação {aprovadas}/{len(res.verificacao)} · {origem} · {arquivo}",
        )
    if res.status == "fallback":
        motivo = (
            f"LLM indisponível: {res.llm_indisponivel}"
            if res.llm_indisponivel
            else f"falha em {res.etapa_falha}"
        )
        return Linha(_DEMONSTRACAO, "contingência", f"{motivo} · {arquivo}", "aviso")
    return Linha(_DEMONSTRACAO, res.status, "veja os avisos acima", "erro")


def _demonstrar(s: Settings, ml: bool, usar_llm: bool) -> ResultadoDiaria:
    from zoneinfo import ZoneInfo

    from fiat_lux.cli.cmd_palavra import anunciar, imprimir_resultado_diaria
    from fiat_lux.orquestracao.diaria import OpcoesDiaria, executar

    v.etapa("Demonstração", "a Palavra do Dia de hoje, sem enviar nada (--dry-run)")
    if usar_llm:
        v.info(
            "com o servidor de LLM: alguns minutos (ele atende um pedido por vez, e a Palavra do "
            "Dia faz de 6 a 10)"
        )
    else:
        v.info(
            "sem o LLM por enquanto: a demonstração usa o cliente offline, com textos de "
            "exemplo (o resto do caminho é o de verdade)"
        )
    v.info("rerank neural em CPU: 1 a 2 min" if ml else "busca lexical: cerca de 1 min")
    hoje = dt.datetime.now(ZoneInfo(s.geral.fuso)).date()
    with v.andamento("começando") as andamento, v.acompanhar_llm(andamento):
        res = executar(
            OpcoesDiaria(
                data=hoje,
                perfil=s.geral.perfil_padrao,
                dry_run=True,
                provedor_llm=None if usar_llm else "offline",
                ao_mudar_etapa=lambda e: andamento.atualizar(v.ETAPAS.get(e, e)),
            ),
            s,
        )
    anunciar(res.status, andamento.decorrido)
    imprimir_resultado_diaria(res)
    return res


def configurar(
    sem_demonstracao: bool = typer.Option(
        False, "--sem-demonstracao", help="Não gera a Palavra do Dia de teste no fim."
    ),
    sem_perguntas: bool = typer.Option(
        False, "--sem-perguntas", help="Não pergunta o servidor de LLM nem o e-mail."
    ),
    reconstruir_indice: bool = typer.Option(
        False, "--reconstruir-indice", help="Reconstrói o índice mesmo que o atual sirva."
    ),
    sem_cabecalho: bool = typer.Option(
        False, "--sem-cabecalho", hidden=True, help="O script de configuração já mostrou o logo."
    ),
    so_email: bool = typer.Option(
        False, "--email", help="Só configura (ou troca) o e-mail e manda um e-mail de teste."
    ),
) -> None:
    """Prepara o que falta (.env, LLM, base bíblica, índice) e gera uma Palavra do Dia de teste.

    Pode ser repetido: cada etapa usa o que já existe e só faz o que falta.
    """
    from fiat_lux.logs import so_erros_no_console

    # as etapas e o resumo dizem o que importa; avisos de log só repetiriam os mesmos fatos
    with so_erros_no_console():
        if so_email:
            _configurar_email(sem_cabecalho)
        else:
            _configurar(sem_demonstracao, sem_perguntas, reconstruir_indice, sem_cabecalho)


def _configurar_email(sem_cabecalho: bool) -> None:
    """`configurar --email`: só as perguntas do e-mail, o teste e a conferência da conta."""
    from fiat_lux.config import raiz_projeto, recarregar_settings
    from fiat_lux.instalacao import garantir_env

    raiz = raiz_projeto()
    os.chdir(raiz)  # o .env é lido da pasta atual
    if not sem_cabecalho:
        v.cabecalho("e-mail", [("pasta", str(raiz))])
    if not _terminal_interativo():
        falhar(
            "o e-mail é configurado por perguntas: rode este comando num terminal (PowerShell, "
            "Prompt de Comando ou bash), ou preencha SMTP_* e EMAIL_DESTINATARIOS no .env "
            "(guia, seção 9)"
        )
    garantir_env(raiz)
    v.etapa("E-mail")
    _perguntar_email(raiz / ".env", direto=True)
    linha, pendencia = _linha_email(recarregar_settings())
    if pendencia:
        v.aviso(pendencia)
        raise typer.Exit(1)
    v.ok(f"E-mail {linha.situacao}: {linha.detalhe}.")
    v.dica("Para mandar a Palavra do Dia de hoje agora: uv run fiatlux palavra diaria")


def _configurar(
    sem_demonstracao: bool, sem_perguntas: bool, reconstruir_indice: bool, sem_cabecalho: bool
) -> None:
    from fiat_lux import instalacao as inst
    from fiat_lux.config import raiz_projeto, recarregar_settings

    raiz = raiz_projeto()
    os.chdir(raiz)  # o .env é lido da pasta atual
    if not sem_cabecalho:
        s0 = recarregar_settings()
        v.cabecalho("configuração", [("pasta", str(raiz)), ("versão", s0.geral.versao_pipeline)])
    ml = inst.ml_instalado()
    env = raiz / ".env"
    resumo: list[Linha] = [_linha_modo(ml), _etapa_env(raiz)]
    llm = _etapa_chaves(env, sem_perguntas)
    s = recarregar_settings()
    pendencias: list[str] = []
    linha_email, pendencia_email = _linha_email(s)
    resumo.append(linha_email)
    if pendencia_email:
        pendencias.append(pendencia_email)
    if s.entrega.telegram:  # provisoriamente desligado: a entrega é por e-mail
        resumo.append(_linha_telegram(s))
    resumo.append(_etapa_corpus(s))
    resumo.append(_etapa_indice(s, ml, reconstruir_indice))
    falhou = False
    if sem_demonstracao:
        resumo.append(Linha(_DEMONSTRACAO, "pulada", "--sem-demonstracao", "neutro"))
    else:
        usar_llm = llm.estado in {"ok", "incerto"}
        res = _demonstrar(s, ml, usar_llm)
        # o teste (sem inferência) não concluiu, ou passou e a geração esbarrou em algo que só
        # aparece gerando (servidor lento demais para o proxy, ocupado): vale o da demonstração
        if res.llm_causa and llm.estado in {"incerto", "ok"}:
            llm = inst.SituacaoLLM("indisponivel", res.llm_causa, res.llm_indisponivel, llm.modelos)
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
        return Linha("Modo", "completo", "modelos neurais (sentence-transformers)")
    return Linha(
        "Modo",
        "leve",
        "busca lexical; para o completo, rode o script com -Modo completo (--completo)",
        "neutro",
    )


def _etapa_env(raiz: Path) -> Linha:
    from fiat_lux.instalacao import garantir_env

    v.etapa("Arquivo .env")
    if garantir_env(raiz):
        v.ok("criado a partir do .env.example (o .env fica fora do git)")
        return Linha(".env", "criado", "a partir do .env.example")
    v.ok("já existe; mantido como está")
    return Linha(".env", "ok", "já existia")


def _etapa_chaves(env: Path, sem_perguntas: bool) -> SituacaoLLM:
    from fiat_lux.config import recarregar_settings

    s = recarregar_settings()
    titulo = (
        "Servidor de LLM, e-mail e Telegram" if s.entrega.telegram else "Servidor de LLM e e-mail"
    )
    v.etapa(titulo, "opcional")
    interativo = not sem_perguntas and _terminal_interativo()
    if interativo:
        _perguntar_llm(env)
    else:
        v.info(
            "sem perguntas agora (--sem-perguntas ou terminal não interativo); "
            "preencha o .env quando quiser"
        )
    llm = _cuidar_do_llm(recarregar_settings(), env, interativo)
    if interativo and s.entrega.email:
        _perguntar_email(env)
    if interativo and s.entrega.telegram:
        _perguntar_telegram(env)
    return llm


def _linha_email(s: Settings) -> tuple[Linha, str | None]:
    """A linha do e-mail no resumo e, se a conta não foi aceita, a pendência. Confere servidor e
    senha entrando na conta, sem enviar nada."""
    from fiat_lux.entrega.email import ErroEmail
    from fiat_lux.orquestracao.diaria import cliente_email

    if not s.entrega.email:
        return Linha("E-mail", "desligado", "[entrega] email = false", "neutro"), None
    if not (s.email_configurado and s.email_destinatarios):
        return Linha("E-mail", "não configurado", "a mensagem fica só em saidas/", "aviso"), (
            "E-mail: é por ele que a Palavra do Dia chega. Rode uv run fiatlux configurar --email "
            "(no Gmail, com uma senha de app; guia, seção 9)."
        )
    try:
        with v.andamento(f"conferindo a conta de e-mail em {s.smtp_host} (sem enviar nada)"):
            cliente_email(s).testar()
    except ErroEmail as e:
        return Linha("E-mail", "não conferido", e.motivo, "aviso"), (
            f"E-mail ({e.motivo}): rode o configurar de novo, ou corrija SMTP_HOST, SMTP_PORT, "
            "SMTP_USUARIO e SMTP_SENHA no .env (guia, seção 9)."
        )
    n = len(s.email_destinatarios)
    return Linha("E-mail", "configurado", f"{n} destinatário(s) · conta conferida"), None


def _linha_telegram(s: Settings) -> Linha:
    if s.telegram_bot_token and s.telegram_chat_ids:
        return Linha("Telegram", "configurado", f"{len(s.telegram_chat_ids)} destinatário(s)")
    return Linha(
        "Telegram", "não configurado", "a mensagem fica em saidas/ (guia, seção 9)", "neutro"
    )


def _etapa_corpus(s: Settings) -> Linha:
    from fiat_lux.instalacao import checar_corpus

    item = "Base bíblica"
    v.etapa(item)
    ok, detalhe = checar_corpus(s)
    if ok:
        v.ok(f"pronta: {detalhe}")
        return Linha(item, "ok", f"{detalhe} (já existia)")
    v.info(f"{detalhe}: montando agora (cerca de 2 min na primeira vez)")
    from fiat_lux.biblia.fontes import FonteAlterada
    from fiat_lux.cli import cmd_biblia

    try:
        with v.andamento("baixando as fontes (o SHA-256 de cada uma é conferido)") as andamento:
            contagem = {"n": 0}

            def baixado(arquivo: str) -> None:
                contagem["n"] += 1
                andamento.atualizar(f"baixando as fontes · {contagem['n']} arquivos · {arquivo}")

            r = cmd_biblia.baixar_todas(progresso=baixado)
        v.ok(f"fontes: {r['baixados']} baixadas, {r['conferidos']} já conferidas")
        with v.andamento("montando o corpus (limpeza, versificação, validação)"):
            cmd_biblia.ingerir_corpus()
    except (FonteAlterada, RuntimeError) as e:
        falhar(str(e))
    ok, detalhe = checar_corpus(s)
    if not ok:
        falhar(
            f"a base bíblica não passou na validação: {detalhe}. "
            "Detalhes: uv run fiatlux biblia validar"
        )
    v.ok(f"pronta: {detalhe}")
    return Linha(item, "montada", detalhe)


def _etapa_indice(s: Settings, ml: bool, reconstruir: bool) -> Linha:
    from fiat_lux import instalacao as inst

    item = "Índice de busca"
    v.etapa(item)
    sit = inst.ler_situacao_indice(s.caminhos.biblia_db)
    motivo = (
        "reconstrução pedida (--reconstruir-indice)"
        if reconstruir
        else inst.motivo_reconstruir_indice(
            sit, inst.embedder_esperado(s.rag.modelo_embeddings, ml)
        )
    )
    if motivo is None:
        v.ok(
            f"pronto: {sit.embedder}, {sit.pericopes} perícopes (construído em {sit.construido_em})"
        )
        return Linha(item, "ok", f"{sit.embedder}, {sit.pericopes} perícopes (já existia)")
    tempo = (
        "cerca de 40 min em CPU, uma vez só; o modelo (~1,1 GB) é baixado se faltar"
        if ml
        else "1 a 2 min"
    )
    v.info(f"{motivo}: construindo agora ({tempo})")
    from fiat_lux.rag.indice import construir

    with v.barra("calculando os vetores") as avancar:
        r = construir(
            s.caminhos.biblia_db,
            "neural" if ml else "lexical",
            s.rag.modelo_embeddings,
            progresso=v.progresso_em_texto(avancar, v.info),
        )
    v.ok(f"pronto: {r['embedder']}, {r['pericopes']} perícopes em {r['segundos']} s")
    return Linha(item, "construído", f"{r['embedder']}, {r['pericopes']} perícopes")


def _fechar(resumo: list[Linha], pendencias: list[str], falhou: bool) -> None:
    """Tabela do resumo e o painel final: o veredito no título, o que falta e os próximos passos."""
    v.etapa("Resumo")
    v.resumo(linha.tupla() for linha in resumo)
    corpo: list[RenderableType] = []
    if falhou:
        titulo, nivel = "A demonstração falhou", "erro"
        corpo.append(Text("Veja os avisos acima, corrija e rode o configurar de novo.", "bold"))
    elif pendencias:
        falta = "falta 1 item" if len(pendencias) == 1 else f"faltam {len(pendencias)} itens"
        titulo, nivel = f"Quase pronto: {falta}", "aviso"
        corpo.append(Text("A instalação está pronta. Para a Palavra do Dia sair completa:", "bold"))
        corpo.append(v.marcadores(pendencias))
    else:
        titulo, nivel = "Tudo pronto", "ok"
        corpo.append(Text("O Fiat Lux está configurado nesta máquina.", "bold"))
    corpo += [
        Text(),
        Text("Próximos passos (na pasta do projeto)", f"bold {v.OURO}"),
        v.comandos(_PROXIMOS_PASSOS),
        Text(),
        Text(
            "Servidor de LLM e e-mail: rode de novo o configurar ou edite o .env (guia, seções 8 "
            "e 9). Agendar todo dia (o e-mail chega por volta das 7h): docs/guia-do-usuario.md, seção 10.",
            v.APAGADO,
        ),
    ]
    v.painel(titulo, nivel, corpo)
    if falhou:
        raise typer.Exit(1)
