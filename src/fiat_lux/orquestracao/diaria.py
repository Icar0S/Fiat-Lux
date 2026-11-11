"""Pipeline diário (plano §4.2): liturgia → notícias → contexto → consultas → RAG → seleção →
redação → verificação → montagem → entrega → registro.

Falha segura (§4.3): qualquer erro numa etapa leva ao fallback (Evangelho do dia + oração
fixa + aviso), nunca a conteúdo não verificado. `--dry-run` não envia nem marca como enviada.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from fiat_lux.agente import contexto as mod_contexto
from fiat_lux.agente import fallback as mod_fallback
from fiat_lux.agente.montagem import renderizar_diaria
from fiat_lux.agente.selecao import Escolha
from fiat_lux.agente.verificacao import Checagem
from fiat_lux.biblia.repositorio import Repositorio
from fiat_lux.config import Settings, obter_settings
from fiat_lux.entrega import markdown as arquivo
from fiat_lux.entrega.email import ClienteEmail, ErroEmail, assunto_de, mascarar
from fiat_lux.estado import Estado
from fiat_lux.liturgia.cliente_api import ClienteLiturgia
from fiat_lux.liturgia.servico import ServicoLiturgia
from fiat_lux.llm.cliente import (
    Contabilidade,
    ErroOrcamento,
    ErroPermanente,
    LLMClient,
    motivo_curto,
    provedor_bloqueado,
)
from fiat_lux.llm.fabrica import criar_cliente, llm_configurado
from fiat_lux.llm.prompts import hash_conjunto
from fiat_lux.logs import log
from fiat_lux.noticias.coleta import coletor_padrao, processar_dia
from fiat_lux.orquestracao.nucleo import Rastreio, Recursos, VerificacaoReprovada, gerar_palavra
from fiat_lux.pastoral import perfil as obter_perfil
from fiat_lux.rag.busca import Buscador


@dataclass(slots=True)
class OpcoesDiaria:
    data: dt.date
    perfil: str = "catolico"
    dry_run: bool = False
    sem_envio: bool = False
    provedor_llm: str | None = None
    coletar_noticias: bool = True
    usar_gdelt: bool = True
    usar_rerank: bool | None = None
    destinatarios: list[str] | None = None
    ao_mudar_etapa: Callable[[str], None] | None = None  # andamento (ex.: o do configurar)


@dataclass(slots=True)
class ResultadoDiaria:
    status: str = "falhou"
    markdown: str = ""
    caminho: Path | None = None
    verificacao: list[Checagem] = field(default_factory=list)
    escolha: Escolha | None = None
    custo: float = 0.0
    avisos: list[str] = field(default_factory=list)
    etapa_falha: str | None = None
    tentativas_redacao: int = 0
    llm: str = ""
    # o LLM ficou fora nesta execução (ErroPermanente): causa ("chave", "conexao"…) e motivo
    llm_causa: str = ""
    llm_indisponivel: str = ""


def registrar_bloqueio(res: ResultadoDiaria, llm: LLMClient, modelos: Iterable[str] = ()) -> None:
    """Diz uma vez só, no topo dos avisos, por que o LLM ficou fora nesta execução (as etapas
    dizem apenas "sem o LLM"): o servidor todo, ou um dos `modelos` da execução, lento demais
    para o proxy na frente do servidor."""
    b = provedor_bloqueado(llm) or next(
        (
            x
            for m in dict.fromkeys(modelos)
            if (x := provedor_bloqueado(llm, m)) is not None and x.causa == "lento"
        ),
        None,
    )
    if b is None:
        return
    res.llm_causa, res.llm_indisponivel = b.causa, b.motivo
    if b.causa != "sem_servidor":  # a falta de servidor já foi avisada no início (cliente_llm)
        res.avisos.insert(0, f"LLM indisponível nesta execução: {b.motivo}")


def aviso_de_falha(res: ResultadoDiaria, etapa: str, e: Exception, evento: str) -> None:
    """Registra a falha que levou ao fallback. Sem o LLM (`ErroPermanente`), é uma situação
    prevista, não um defeito: sem traceback e com um aviso que diz o que saiu no lugar."""
    if isinstance(e, ErroPermanente):
        log().warning(evento, etapa=etapa, motivo=e.motivo)
        res.avisos.append(
            f"sem a redação ({motivo_curto(e)}): saiu a mensagem de contingência "
            "(Evangelho do dia + oração)"
        )
        return
    log().error(evento, etapa=etapa, erro=str(e), trace=traceback.format_exc(limit=3))
    res.avisos.append(f"falha em {etapa}: {e}")


def resumo_da_falha(res: ResultadoDiaria, ultimos: int) -> str:
    if res.llm_indisponivel:
        return f"LLM indisponível: {res.llm_indisponivel}"
    return "; ".join(res.avisos[-ultimos:])


def passagens_json(escolha: Escolha | None) -> str:
    if escolha is None:
        return "{}"
    itens = [
        {
            "papel": papel,
            "id": c.id,
            "ref": c.rotulo(),
            "traducao": c.traducao,
            "refs_canonicas": c.refs_canonicas,
            "escores": {k: round(v, 4) for k, v in c.escores.items()},
        }
        for papel, c in [("principal", escolha.principal)]
        + [("complementar", x) for x in escolha.complementares]
    ]
    return json.dumps(
        {"passagens": itens, "metodo": escolha.metodo, "justificativa": escolha.justificativa},
        ensure_ascii=False,
    )


def cliente_llm(s: Settings, provedor: str | None, dry_run: bool, avisos: list[str]) -> LLMClient:
    escolha = provedor or s.llm.provedor
    if escolha == "local" and not llm_configurado(s):
        if dry_run:
            avisos.append("sem FIATLUX_LLM_URL: dry-run com o cliente offline (determinístico)")
            escolha = "offline"
        else:
            avisos.append(
                "sem FIATLUX_LLM_URL: as etapas de LLM usam as reservas e a mensagem sai como "
                "fallback (Evangelho + oração); aponte para o servidor de LLM no .env"
            )
    return criar_cliente(s, escolha)


def executar(
    op: OpcoesDiaria, s: Settings | None = None, estado: Estado | None = None
) -> ResultadoDiaria:
    s = s or obter_settings()
    res = ResultadoDiaria()
    estado = estado or Estado.abrir()
    eid = estado.iniciar_execucao("diaria", op.data)
    inicio = time.perf_counter()
    contab = Contabilidade(
        estado.custo_mes(op.data.year, op.data.month), s.custos.custo_max_mensal_usd
    )
    perfil = obter_perfil(op.perfil)
    llm = cliente_llm(s, op.provedor_llm, op.dry_run, res.avisos)
    res.llm = llm.nome
    rast = Rastreio(ouvinte=op.ao_mudar_etapa)
    repo: Repositorio | None = None
    buscador: Buscador | None = None
    ctx: mod_contexto.ContextoDoDia | None = None
    try:
        rast.etapa = "liturgia"
        svc = ServicoLiturgia(
            estado,
            ClienteLiturgia(s.liturgia.url_base, s.liturgia.timeout_s, s.liturgia.tentativas),
        )
        if abs((op.data - dt.date.today()).days) <= 1:
            try:
                svc.prefetch(s.liturgia.dias_prefetch)
            except Exception as e:
                res.avisos.append(f"prefetch da liturgia falhou: {e}")
        dia = svc.obter(op.data)

        rast.etapa = "indice"
        repo = Repositorio.abrir(s.caminhos.biblia_db)
        buscador = Buscador.abrir(s.caminhos.biblia_db)

        rast.etapa = "noticias"
        noticias = None
        try:
            coletor = coletor_padrao(s, op.usar_gdelt) if op.coletar_noticias else None
            ref_hora = dt.datetime.now(dt.UTC) if op.data == dt.date.today() else None
            noticias = processar_dia(
                op.data, s, estado, llm, coletor, contabilidade=contab, referencia=ref_hora
            )
        except ErroOrcamento:
            raise
        except Exception as e:
            log().warning("noticias_falharam", erro=str(e))
            res.avisos.append(f"medidor indisponível: {e}")

        rast.etapa = "contexto"
        ctx = mod_contexto.montar(
            op.data, perfil, dia, noticias, llm, s.llm.modelo_classificacao, contab
        )
        res.avisos += ctx.avisos

        palavra = gerar_palavra(
            ctx, dia, Recursos(s, estado, llm, contab, repo, buscador, op.usar_rerank), rast
        )
        res.escolha, res.verificacao = palavra.escolha, palavra.checagens

        rast.etapa = "montagem"
        res.markdown = renderizar_diaria(
            ctx, palavra.escolha, palavra.redacao, s.geral.versao_pipeline, s.geral.regiao
        )
        res.status = "rascunho"
    except Exception as e:
        res.etapa_falha = rast.etapa
        if isinstance(e, VerificacaoReprovada):
            res.verificacao = e.checagens
        motivo = (
            "O teto de custo mensal foi atingido; segue o Evangelho do dia."
            if isinstance(e, ErroOrcamento)
            else "Hoje não foi possível preparar a reflexão completa; segue o Evangelho do dia."
        )
        aviso_de_falha(res, rast.etapa, e, "diaria_falhou")
        ctx = ctx or _contexto_minimo(op.data, perfil, estado)
        try:
            res.markdown = mod_fallback.gerar(ctx, motivo, repo, buscador, s.geral.versao_pipeline)
            res.status = "fallback"
        except Exception as e2:
            res.avisos.append(f"fallback falhou: {e2}")
            res.status = "falhou"
    res.avisos += rast.avisos
    registrar_bloqueio(
        res, llm, (s.llm.modelo_classificacao, s.llm.modelo_geracao, s.llm.modelo_juiz)
    )
    res.tentativas_redacao = rast.tentativas_redacao
    res.custo = round(contab.uso.custo_usd, 5)
    entregar(
        op.data,
        "diaria",
        perfil.nome,
        res,
        contab,
        s,
        estado,
        op.dry_run,
        op.sem_envio,
        op.destinatarios,
    )
    estado.terminar_execucao(
        eid,
        res.status,
        time.perf_counter() - inicio,
        res.etapa_falha,
        resumo_da_falha(res, 3) if res.etapa_falha else None,
        res.custo,
    )
    fechar_recursos(repo, buscador)
    return res


def fechar_recursos(*recursos: Repositorio | Buscador | None) -> None:
    for r in recursos:
        if r is not None:
            r.fechar()


def _contexto_minimo(data: dt.date, perfil, estado: Estado) -> mod_contexto.ContextoDoDia:
    ctx = mod_contexto.ContextoDoDia(data=data, liturgia=None, perfil=perfil)
    try:
        ctx.liturgia = ServicoLiturgia(estado, None).obter(data, usar_rede=False)
        ev = ctx.liturgia.evangelho
        if ev is not None:
            ctx.evangelho_ref, ctx.evangelho_texto = ev.referencia, ev.texto
    except Exception:
        pass
    return ctx


def destinos(s: Settings, avisos: list[str] | None = None) -> list[str]:
    """Para onde vai a mensagem: os e-mails de EMAIL_DESTINATARIOS e, com o Telegram ligado
    (`[entrega] telegram`), as conversas de TELEGRAM_CHAT_IDS; sem nenhum, só o arquivo."""
    alvos: list[str] = []
    if s.entrega.email and s.email_destinatarios:
        if s.email_configurado:
            alvos += s.email_destinatarios
        elif avisos is not None:
            avisos.append(
                "e-mail sem SMTP_HOST ou remetente no .env: a mensagem ficou só em saidas/"
            )
    if s.entrega.telegram and s.telegram_bot_token:
        alvos += s.telegram_chat_ids
    return alvos or ["arquivo"]


def rotulo_destino(dest: str) -> str:
    """Como o destinatário fica no estado (que vai para o git): o e-mail, só por um código
    derivado do endereço, que basta para não enviar duas vezes."""
    if "@" not in dest:
        return dest
    return "email:" + hashlib.sha256(dest.strip().lower().encode()).hexdigest()[:12]


def cliente_email(s: Settings) -> ClienteEmail:
    return ClienteEmail(
        (s.smtp_host or "").strip(),
        s.smtp_port,
        s.smtp_usuario,
        s.smtp_senha.get_secret_value() if s.smtp_senha else None,
        s.email_remetente,
    )


def _enviar(
    dest: str, res: ResultadoDiaria, s: Settings, foto: Path | None, email: ClienteEmail | None
) -> list[int] | None:
    """Envia para um destinatário. Devolve os ids das mensagens do Telegram ([] no e-mail), ou
    None se não havia como enviar (e-mail sem SMTP, Telegram sem token)."""
    anexos = [foto] if foto is not None and foto.is_file() else []
    if "@" in dest:
        if email is None:
            return None
        email.enviar(dest, assunto_de(res.markdown), res.markdown, anexos)
        return []
    if not s.telegram_bot_token:
        return None
    from fiat_lux.entrega.telegram import ClienteTelegram

    tg = ClienteTelegram(s.telegram_bot_token.get_secret_value(), tuple(s.telegram_chat_ids))
    ids = [tg.enviar_foto(dest, f, "Tendência do medidor na semana") for f in anexos]
    return ids + tg.enviar_markdown(dest, res.markdown, s.entrega.limite_telegram)


def entregar(
    data: dt.date,
    tipo: str,
    perfil: str,
    res: ResultadoDiaria,
    contab: Contabilidade,
    s: Settings,
    estado: Estado,
    dry_run: bool,
    sem_envio: bool,
    destinatarios: list[str] | None,
    foto: Path | None = None,
) -> None:
    if not res.markdown:
        return
    if dry_run:
        destino = s.caminhos.cache / "dry-run" / f"{data.isoformat()}-{tipo}-{perfil}.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(res.markdown, encoding="utf-8")
        res.caminho = destino
        return
    res.caminho = arquivo.arquivar(s.caminhos.saidas, data, res.markdown, tipo, perfil)
    alvos = destinatarios if destinatarios is not None else destinos(s, res.avisos)
    email = cliente_email(s) if s.email_configurado else None
    for dest in alvos:
        rotulo = rotulo_destino(dest)
        if estado.ja_enviada(data, tipo, perfil, rotulo):
            res.avisos.append("já enviada para este destinatário; nada a fazer (idempotência)")
            continue
        mid = estado.gravar_mensagem(_registro(data, tipo, perfil, rotulo, res, contab, s))
        ids: list[int] | None = [] if dest == "arquivo" else None
        if dest != "arquivo" and not sem_envio:  # --sem-envio não marca como enviada
            from fiat_lux.entrega.telegram import ErroTelegram

            try:
                ids = _enviar(dest, res, s, foto, email)
            except (ErroEmail, ErroTelegram) as e:
                canal = f"e-mail para {mascarar(dest)}" if "@" in dest else "Telegram"
                res.avisos.append(f"{canal} falhou: {e}")
                if res.status == "rascunho":
                    res.status = "falhou"
                continue
        if ids is not None:
            estado.marcar_enviada(mid, ids)
            if res.status == "rascunho":
                res.status = "enviada"
            with estado.transacao() as c:
                c.execute("UPDATE mensagens SET status=? WHERE id=?", (res.status, mid))
    if res.escolha is not None and res.status in {"enviada", "rascunho"} and tipo == "diaria":
        estado.registrar_passagens(
            data,
            perfil,
            [(r, "principal") for r in res.escolha.principal.refs_canonicas]
            + [(r, "complementar") for c in res.escolha.complementares for r in c.refs_canonicas],
        )
    if res.status in {"fallback", "falhou"}:
        alertar_admin(
            s,
            f"Fiat Lux {data} ({tipo}): {res.status} em {res.etapa_falha} — {resumo_da_falha(res, 2)}",
        )


def _registro(
    data: dt.date,
    tipo: str,
    perfil: str,
    rotulo: str,
    res: ResultadoDiaria,
    contab: Contabilidade,
    s: Settings,
) -> dict[str, object]:
    return {
        "data": data.isoformat(),
        "tipo": tipo,
        "perfil": perfil,
        "destinatario": rotulo,
        "conteudo_md": res.markdown,
        "passagens_json": passagens_json(res.escolha),
        "verificacao_json": json.dumps(
            [{"id": c.id, "ok": c.ok, "motivo": c.motivo} for c in res.verificacao],
            ensure_ascii=False,
        ),
        "modelo_llm": ",".join(sorted(contab.modelos)) or res.llm,
        "hash_prompts": hash_conjunto(),
        "versao_pipeline": s.geral.versao_pipeline,
        "tokens_entrada": contab.uso.tokens_entrada,
        "tokens_saida": contab.uso.tokens_saida,
        "custo_estimado": res.custo,
        "status": res.status,
    }


def alertar_admin(s: Settings, texto: str) -> None:
    """Avisa quem cuida do Fiat Lux que a mensagem saiu em contingência ou falhou: por e-mail
    (EMAIL_ADMIN ou, sem ele, quem envia) ou, com o Telegram ligado, por ele; sem canal, no log."""
    if s.entrega.email and s.email_configurado and s.email_admin:
        try:
            cliente_email(s).enviar(s.email_admin, "Fiat Lux: alerta", texto)
        except ErroEmail as e:
            log().error("alerta_admin_falhou", canal="email", erro=str(e))
        return
    if s.entrega.telegram and s.telegram_bot_token and s.telegram_admin_chat_id:
        from fiat_lux.entrega.telegram import ClienteTelegram, ErroTelegram

        try:
            ClienteTelegram(
                s.telegram_bot_token.get_secret_value(), (s.telegram_admin_chat_id,)
            ).enviar_texto(s.telegram_admin_chat_id, texto)
        except ErroTelegram as e:
            log().error("alerta_admin_falhou", canal="telegram", erro=str(e))
        return
    log().warning("alerta_admin_sem_canal", texto=texto[:200])
