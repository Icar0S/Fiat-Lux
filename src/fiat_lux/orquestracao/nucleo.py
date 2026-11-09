"""Núcleo compartilhado pela Palavra do Dia e da Semana: consultas → RAG → seleção → redação
com verificação V1–V8 e até `max_tentativas_redacao` revisões."""

from __future__ import annotations

from dataclasses import dataclass, field

from fiat_lux.agente import consultas as mod_consultas
from fiat_lux.agente.contexto import ContextoDoDia
from fiat_lux.agente.montagem import substituir
from fiat_lux.agente.redacao import julgar, permitidas, redigir
from fiat_lux.agente.selecao import Escolha, selecionar
from fiat_lux.agente.verificacao import Checagem, EntradaVerificacao, aprovado, verificar, violacoes
from fiat_lux.biblia.repositorio import Repositorio
from fiat_lux.biblia.versificacao import Versificacao
from fiat_lux.config import Settings
from fiat_lux.estado import Estado
from fiat_lux.liturgia.modelos import DiaLiturgico
from fiat_lux.llm.cliente import Contabilidade, ErroLLM, LLMClient
from fiat_lux.llm.esquemas import Julgamento, Redacao
from fiat_lux.logs import log
from fiat_lux.pastoral import neutralidade
from fiat_lux.rag.busca import Buscador, Candidato
from fiat_lux.rag.embeddings import neural_disponivel
from fiat_lux.rag.recuperacao import EntradaRecuperacao, Recuperador, ancora_do_dia
from fiat_lux.rag.rerank import criar_reranker


class VerificacaoReprovada(RuntimeError):
    def __init__(self, checagens: list[Checagem]) -> None:
        super().__init__(
            "verificação reprovou após as revisões: " + "; ".join(violacoes(checagens))
        )
        self.checagens = checagens


@dataclass(slots=True)
class Rastreio:
    etapa: str = "inicio"
    avisos: list[str] = field(default_factory=list)
    tentativas_redacao: int = 0


@dataclass(slots=True)
class Recursos:
    s: Settings
    estado: Estado
    llm: LLMClient
    contab: Contabilidade
    repo: Repositorio
    buscador: Buscador
    usar_rerank: bool | None = None
    _rec: Recuperador | None = None
    _vrs: Versificacao | None = None

    @property
    def recuperador(self) -> Recuperador:
        if self._rec is None:
            usar = self.s.rag.usar_rerank if self.usar_rerank is None else self.usar_rerank
            self._rec = Recuperador(
                self.buscador,
                criar_reranker(usar and neural_disponivel(), self.s.rag.modelo_rerank),
                self.repo,
                self.s.rag,
            )
        return self._rec

    @property
    def vrs(self) -> Versificacao:
        if self._vrs is None:
            self._vrs = Versificacao.carregar()
        return self._vrs


@dataclass(slots=True)
class Palavra:
    escolha: Escolha
    redacao: Redacao
    checagens: list[Checagem]
    candidatos: list[Candidato]


def recuperar(
    ctx: ContextoDoDia, dia: DiaLiturgico | None, r: Recursos, rast: Rastreio
) -> list[Candidato]:
    rast.etapa = "consultas"
    qs, origens, av = mod_consultas.gerar(
        ctx, r.llm, r.s.llm.modelo_classificacao, r.s.llm.esforco_consultas, r.contab
    )
    rast.avisos += av
    rast.etapa = "rag"
    rep = r.s.rag.repeticao
    entrada = EntradaRecuperacao(
        consultas=qs,
        origens=origens,
        perfil=ctx.perfil,
        tempo=ctx.tempo,
        categorias=ctx.categorias,
        ancora=ancora_do_dia(dia, r.vrs, r.repo),
        recentes_principais=r.estado.passagens_recentes(
            ctx.perfil.nome, ctx.data, rep.principal_dias, "principal"
        ),
        recentes_complementares=r.estado.passagens_recentes(
            ctx.perfil.nome, ctx.data, rep.complementar_dias, "complementar"
        ),
    )
    return r.recuperador.recuperar(entrada)


def gerar_palavra(
    ctx: ContextoDoDia, dia: DiaLiturgico | None, r: Recursos, rast: Rastreio
) -> Palavra:
    cands = recuperar(ctx, dia, r, rast)
    rast.etapa = "selecao"
    escolha = selecionar(
        ctx, cands, r.llm, r.s.llm.modelo_geracao, r.s.llm.esforco_selecao, r.contab
    )
    rast.avisos += escolha.alertas
    rast.etapa = "redacao"
    refs, textos = permitidas(ctx, escolha)
    revisao: list[str] | None = None
    checagens: list[Checagem] = []
    redacao: Redacao | None = None
    for tentativa in range(r.s.llm.max_tentativas_redacao + 1):
        rast.tentativas_redacao = tentativa + 1
        redacao = redigir(
            ctx, escolha, r.llm, r.s.llm.modelo_geracao, r.s.llm.esforco_redacao, revisao, r.contab
        )
        julg: Julgamento | None = None
        try:
            texto = "\n\n".join(
                substituir(getattr(redacao, c), escolha)
                for c in ("olhar_sobre_o_dia", "reflexao", "ensinamento", "gesto", "oracao")
            )
            julg = julgar(texto, r.llm, r.s.llm.modelo_juiz, r.s.llm.esforco_juiz, r.contab)
        except ErroLLM as e:
            rast.avisos.append(f"juiz indisponível: {e}")
        perfil = ctx.perfil
        checagens = verificar(
            EntradaVerificacao(
                redacao=redacao,
                permitidas=refs,
                textos_permitidos=textos,
                urls_permitidas=ctx.urls_permitidas(),
                sensibilidades=ctx.sensibilidades,
                perfil=perfil.nome,
                livros_passagens=[
                    (c.livro, c.deutero) for c in [escolha.principal, *escolha.complementares]
                ],
                rotulos_deutero_presentes=perfil.deuterocanonicos != "rotulados"
                or bool(perfil.rotulo_deutero),
                neutralidade=neutralidade(),
                julgamento=julg,
            )
        )
        if aprovado(checagens):
            break
        revisao = violacoes(checagens)
        log().warning("verificacao_reprovou", tentativa=tentativa, violacoes=revisao)
    if redacao is None or not aprovado(checagens):
        raise VerificacaoReprovada(checagens)
    return Palavra(escolha, redacao, checagens, cands)
