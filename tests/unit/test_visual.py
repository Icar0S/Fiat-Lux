"""Visual do terminal (`cli/visual.py`). Sem terminal (CI, saída num arquivo), tudo vira texto
simples e legível: sem animação, sem cores, com os mesmos ícones."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rich.text import Text

from fiat_lux.cli import visual as v
from fiat_lux.cli.comum import console
from fiat_lux.orquestracao.nucleo import Rastreio


def capturar(funcao: Callable[[], object], largura: int = 100) -> str:
    """Saída do console do Fiat Lux, com largura fixa e como se não houvesse terminal."""
    largura_antes, terminal_antes = console._width, console._force_terminal
    console.width, console._force_terminal = largura, False
    try:
        with console.capture() as cap:
            funcao()
        return cap.get()
    finally:
        console._width, console._force_terminal = largura_antes, terminal_antes


def test_logo_tem_linhas_iguais_e_uma_cor_por_linha() -> None:
    assert len({len(linha) for linha in v.LOGO}) == 1
    assert len(v.GRADIENTE) == len(v.LOGO)


def test_cabecalho_largo_mostra_o_logo_e_estreito_so_o_nome() -> None:
    largo = capturar(lambda: v.cabecalho("configuração", [("pasta", r"C:\projetos\Fiat-Lux")]))
    assert v.LOGO[0] in largo and "✦ configuração" in largo
    assert r"C:\projetos\Fiat-Lux" in largo and v.LEMA in largo
    estreito = capturar(lambda: v.cabecalho("configuração"), largura=40)
    assert "✦ FIAT LUX" in estreito and "███" not in estreito


def test_etapa_e_linhas_com_icone_por_nivel() -> None:
    def desenhar() -> None:
        v.etapa("Base bíblica", "opcional")
        v.ok("pronta: 28 checagens ok")
        v.info("detalhe")
        v.aviso("cuidado")
        v.erro("falhou")
        v.dica("O que fazer: algo.")

    texto = capturar(desenhar)
    for trecho in (
        " ● Base bíblica  opcional",
        "✓ pronta: 28 checagens ok",
        "· detalhe",
        "! cuidado",
        "✗ falhou",
        "→ O que fazer: algo.",
    ):
        assert trecho in texto
    assert v.prompt("Configurar agora?") == "   ? Configurar agora?"


def test_linha_longa_quebra_alinhada_ao_texto() -> None:
    texto = capturar(lambda: v.aviso("palavra " * 30), largura=60)
    continuacao = texto.splitlines()[1]
    assert continuacao.startswith("     ") and not continuacao.strip().startswith("!")


def test_andamento_sem_terminal_vira_uma_linha_por_texto() -> None:
    def rodar() -> None:
        with v.andamento("lendo a liturgia do dia") as andamento:
            andamento.atualizar("buscando passagens")
            andamento.atualizar("buscando passagens")  # repetido: não imprime de novo
            assert andamento.decorrido.startswith("0:0")

    texto = capturar(rodar)
    assert texto.count("· lendo a liturgia do dia") == 1
    assert texto.count("· buscando passagens") == 1


def test_progresso_em_texto_separa_a_fracao_do_resto() -> None:
    feitos: list[tuple[int, int]] = []
    mensagens: list[str] = []
    receber = v.progresso_em_texto(lambda f, t: feitos.append((f, t)), mensagens.append)
    receber("16703 perícopes; calculando vetores…")
    receber("  256/16703")
    assert feitos == [(256, 16703)] and mensagens == ["16703 perícopes; calculando vetores…"]
    with v.barra("calculando") as avancar:  # sem terminal: não desenha nada
        avancar(1, 2)


def test_resumo_e_painel_final() -> None:
    def desenhar() -> None:
        v.resumo([("Modo", "completo", "neural", "ok"), ("LLM", "sem servidor", "x", "aviso")])
        v.painel("Tudo pronto", "ok", [Text("corpo do painel"), v.comandos([("cmd", "faz")])])

    texto = capturar(desenhar)
    assert "✓" in texto and "Modo" in texto and "! " in texto.split("LLM")[0][-6:]
    assert "✦ Tudo pronto" in texto and "corpo do painel" in texto and "cmd" in texto


def test_mensagem_usa_o_titulo_e_nao_mostra_as_urls() -> None:
    md = (
        "# Palavra do Dia — terça-feira, 10 de novembro de 2026\n\n"
        "**São Leão Magno** · Tempo Comum\n\n"
        "Fontes: [G1](https://news.google.com/rss/articles/CBMi9gFBVV95cUxN)\n\n"
        "<sub>Texto bíblico: Matos Soares</sub>\n"
    )
    texto = capturar(lambda: v.mensagem(md, rodape="rascunho · nada foi enviado"))
    assert "✦ Palavra do Dia — terça-feira, 10 de novembro de 2026" in texto
    assert "Fontes: G1" in texto and "news.google.com" not in texto
    assert "Texto bíblico: Matos Soares" in texto and "<sub>" not in texto
    assert "rascunho · nada foi enviado" in texto
    assert v.separar_titulo("sem título") == ("", "sem título")


@dataclass(frozen=True)
class Checagem:
    id: str
    ok: bool
    motivo: str = ""


def test_verificacao_numa_linha_e_reprovadas_com_motivo() -> None:
    texto = capturar(
        lambda: v.verificacao([Checagem("V1", True), Checagem("V2", False, "citação inventada")])
    )
    assert "✗ verificação 1/2" in texto and "V1 ✓" in texto and "V2 ✗" in texto
    assert "V2: citação inventada" in texto
    assert capturar(lambda: v.verificacao([])) == ""


def test_rastreio_avisa_o_ouvinte_a_cada_etapa() -> None:
    etapas: list[str] = []
    r = Rastreio(ouvinte=etapas.append)
    assert r.etapa == "inicio"
    r.etapa = "noticias"
    r.etapa = "redacao"
    assert etapas == ["noticias", "redacao"] and r.etapa == "redacao"
    sem_ouvinte = Rastreio()
    sem_ouvinte.etapa = "rag"
    assert sem_ouvinte.etapa == "rag"


def test_resultado_da_palavra_do_dia() -> None:
    from fiat_lux.cli.cmd_palavra import imprimir_resultado_diaria
    from fiat_lux.orquestracao.diaria import ResultadoDiaria

    res = ResultadoDiaria(
        status="rascunho",
        markdown="# Palavra do Dia — teste\n\nUma reflexão.",
        verificacao=[Checagem("V1", True)],  # type: ignore[list-item]
        avisos=["GDELT recusou por limite de taxa (429); notícias só do RSS"],
        llm="local+cache",
    )
    texto = capturar(lambda: imprimir_resultado_diaria(res))
    assert "✦ Palavra do Dia — teste" in texto and "Uma reflexão." in texto
    assert "rascunho · nada foi enviado" in texto and "✓ verificação 1/1" in texto
    assert "· status rascunho · LLM local+cache · arquivo —" in texto
    assert "! GDELT recusou por limite de taxa" in texto and "custo" not in texto
    quieto = capturar(lambda: imprimir_resultado_diaria(res, mostrar=False))
    assert "Uma reflexão." not in quieto and "verificação 1/1" in quieto


def test_anunciar_fecha_o_andamento_com_o_resultado() -> None:
    from fiat_lux.cli.cmd_palavra import anunciar

    texto = capturar(
        lambda: (
            anunciar("rascunho", "3:12"),
            anunciar("fallback", "0:41"),
            anunciar("falhou", "0:05", "Palavra da Semana"),
        )
    )
    assert "✓ Palavra do Dia pronta em 3:12" in texto
    assert "! saiu a mensagem de contingência, em 0:41" in texto
    assert "✗ Palavra da Semana: falhou, em 0:05" in texto
    assert set(v.ETAPAS) >= {"liturgia", "noticias", "rag", "redacao", "semana", "plano_de_leitura"}


def test_andamento_mostra_o_pedido_ao_llm_em_curso() -> None:
    from fiat_lux.llm.servidor import OBSERVADOR

    def rodar() -> None:
        with v.andamento("coletando e classificando as notícias") as a, v.acompanhar_llm(a):
            observador = OBSERVADOR.get()
            assert observador is not None
            observador("pedido", "classificacao")
            assert a.detalhe == "LLM: classificando as notícias"
            observador("fim", "classificacao")
            assert a.detalhe == ""
        assert OBSERVADOR.get() is None  # desligado ao sair

    texto = capturar(rodar)
    assert "· LLM: classificando as notícias" in texto  # sem terminal, vira linha
    animado = v.Andamento("buscando", animado=True)
    animado.detalhar("LLM: escrevendo a reflexão")
    renderizado = capturar(lambda: console.print(animado))
    assert "buscando  ·  LLM: escrevendo a reflexão 0:00" in renderizado
