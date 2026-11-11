"""Identidade visual do terminal: `fiatlux configurar` e a Palavra do Dia.

*Fiat lux*, "faça-se a luz": o logo vai do claro ao âmbar, como luz que desce, e o dourado
marca as etapas. Fora de um terminal (saída redirecionada para arquivo, CI), o Rich tira cores e
animações sozinho, e as animações viram linhas simples; com `NO_COLOR`, ficam só as formas.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from typing import Protocol

from rich import box
from rich.console import Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from fiat_lux.cli.comum import console

OURO = "#F5A623"
OK = "#6CC570"
AVISO = "#E8C468"
ERRO = "#E5534B"
APAGADO = "grey58"

LOGO = (
    "███████╗██╗ █████╗ ████████╗    ██╗     ██╗   ██╗██╗  ██╗",
    "██╔════╝██║██╔══██╗╚══██╔══╝    ██║     ██║   ██║╚██╗██╔╝",
    "█████╗  ██║███████║   ██║       ██║     ██║   ██║ ╚███╔╝ ",
    "██╔══╝  ██║██╔══██║   ██║       ██║     ██║   ██║ ██╔██╗ ",
    "██║     ██║██║  ██║   ██║       ███████╗╚██████╔╝██╔╝ ██╗",
    "╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝       ╚══════╝ ╚═════╝ ╚═╝  ╚═╝",
)
# do claro ao âmbar, linha a linha (claro o bastante para brilhar num fundo escuro, sem sumir num
# claro); a última, só de sombra, mais escura
GRADIENTE = ("#FFE08A", "#FFCF5C", "#F5B53A", "#F5A623", "#E3851B", "#9C5B1F")
LEMA = "assistente diário e semanal da Palavra de Deus"

# etapa do pipeline (Rastreio.etapa) → o que o andamento mostra
ETAPAS = {
    "liturgia": "lendo a liturgia do dia",
    "indice": "abrindo a base bíblica",
    "noticias": "coletando e classificando as notícias",
    "contexto": "resumindo o Evangelho do dia",
    "consultas": "preparando a busca",
    "rag": "buscando passagens na Bíblia",
    "selecao": "escolhendo as passagens",
    "redacao": "escrevendo e verificando a reflexão",
    "montagem": "montando a mensagem",
    "semana": "reunindo os temas e o medidor da semana",
    "extras": "escrevendo a frase e as perguntas da semana",
    "plano_de_leitura": "montando o plano de leitura",
}

# nível → (ícone, cor) nas linhas de etapa e no resumo
NIVEIS = {
    "ok": ("✓", OK),
    "aviso": ("!", AVISO),
    "erro": ("✗", ERRO),
    "neutro": ("·", APAGADO),
}


# --------------------------------------------------------------------------- cabeçalho


def cabecalho(subtitulo: str, detalhes: Iterable[tuple[str, str]] = ()) -> None:
    """O logo, o lema e um quadro com o essencial (pasta, versão). Num terminal estreito, o logo
    grande vira uma linha."""
    console.print()
    if console.width >= len(LOGO[0]) + 4:
        for linha, cor in zip(LOGO, GRADIENTE, strict=True):
            console.print(Text("  " + linha, style=f"bold {cor}"), no_wrap=True, overflow="crop")
    else:
        console.print(Text("  ✦ FIAT LUX", style=f"bold {OURO}"))
    grade = Table.grid(padding=(0, 2))
    grade.add_column(style=APAGADO, no_wrap=True)
    grade.add_column(overflow="fold")
    for rotulo, valor in detalhes:
        grade.add_row(rotulo, valor)
    titulo = Text.assemble(("✦ ", f"bold {OURO}"), (subtitulo, "bold"), ("  ·  " + LEMA, APAGADO))
    corpo: list[RenderableType] = [titulo]
    if grade.row_count:
        corpo += [Text(), grade]
    painel = Panel(Group(*corpo), box=box.ROUNDED, border_style=OURO, padding=(0, 2), expand=False)
    console.print(Padding(painel, (1, 0, 0, 2)))


# --------------------------------------------------------------------------- etapas


def etapa(titulo: str, detalhe: str = "") -> None:
    """Início de uma etapa: `● Título  detalhe`."""
    console.print()
    console.print(
        Text.assemble(
            (" ● ", f"bold {OURO}"), (titulo, "bold"), (f"  {detalhe}" if detalhe else "", APAGADO)
        )
    )


def linha(nivel: str, texto: str | Text, recuo: int = 3) -> None:
    """Uma linha dentro da etapa, com o ícone do nível. Texto longo quebra alinhado ao texto, não
    à margem."""
    icone, cor = NIVEIS.get(nivel, ("·", APAGADO))
    estilo = {"ok": "", "neutro": APAGADO}.get(nivel, cor)
    grade = Table.grid(padding=(0, 1))
    grade.add_column(no_wrap=True)
    grade.add_column(overflow="fold")
    corpo = texto if isinstance(texto, Text) else Text(texto, style=estilo)
    grade.add_row(Text(" " * recuo + icone, style=f"bold {cor}"), corpo)
    console.print(grade)


def ok(texto: str | Text) -> None:
    linha("ok", texto)


def info(texto: str | Text) -> None:
    linha("neutro", texto)


def aviso(texto: str | Text) -> None:
    linha("aviso", texto)


def erro(texto: str | Text) -> None:
    linha("erro", texto)


def dica(texto: str) -> None:
    """O que fazer, logo abaixo de um aviso."""
    grade = Table.grid(padding=(0, 1))
    grade.add_column(no_wrap=True)
    grade.add_column(overflow="fold")
    grade.add_row(Text("     →", style=f"bold {OURO}"), Text(texto))
    console.print(grade)


def prompt(texto: str) -> str:
    """Texto de pergunta no mesmo alinhamento das linhas (`   ? pergunta`)."""
    return f"   ? {texto}"


# --------------------------------------------------------------------------- andamento


class Andamento:
    """Indicador de que algo está rodando: animado num terminal; fora dele, uma linha por texto."""

    def __init__(self, texto: str, animado: bool) -> None:
        self.texto = texto
        self.animado = animado
        self.inicio = time.monotonic()
        self._spinner = Spinner("dots", style=f"bold {OURO}")

    @property
    def decorrido(self) -> str:
        s = int(time.monotonic() - self.inicio)
        return f"{s // 60}:{s % 60:02d}"

    def atualizar(self, texto: str) -> None:
        if texto == self.texto:
            return
        self.texto = texto
        if not self.animado:
            info(texto)

    def __rich__(self) -> RenderableType:
        self._spinner.update(
            text=Text.assemble((self.texto, "bold"), (f"  {self.decorrido}", APAGADO))
        )
        return Padding(self._spinner, (0, 0, 0, 3))


@contextmanager
def andamento(texto: str, animar: bool = True) -> Iterator[Andamento]:
    """Enquanto o bloco roda, mostra `⠹ texto  0:42`; `atualizar(...)` troca o texto. A animação
    some ao terminar (quem chamou diz o resultado). Não captura stdout nem stderr: barras de
    download que aparecerem continuam visíveis. Sem terminal (ou com `animar=False`), cada
    texto vira uma linha."""
    estado = Andamento(texto, animado=animar and console.is_terminal)
    if not estado.animado:
        info(texto)
        yield estado
        return
    with Live(
        estado,
        console=console,
        transient=True,
        refresh_per_second=10,
        redirect_stdout=False,
        redirect_stderr=False,
    ):
        yield estado


class _Barra(Protocol):
    def __call__(self, feito: int, total: int) -> None: ...


@contextmanager
def barra(texto: str) -> Iterator[_Barra]:
    """Barra de progresso (`feito`, `total`); fora de um terminal, não desenha nada."""
    if not console.is_terminal:
        yield lambda feito, total: None
        return
    progresso = Progress(
        TextColumn("   "),
        TextColumn(f"[bold]{texto}[/]"),
        BarColumn(bar_width=32, style=APAGADO, complete_style=OURO, finished_style=OK),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )
    with progresso:
        tarefa = progresso.add_task(texto, total=None)
        yield lambda feito, total: progresso.update(tarefa, completed=feito, total=total)


_FRACAO = re.compile(r"(\d+)/(\d+)")


def progresso_em_texto(avancar: _Barra, mostrar: Callable[[str], None]) -> Callable[[str], None]:
    """Adapta um callback de texto ("256/16703") para a barra; o resto do texto vai a `mostrar`."""

    def receber(mensagem: str) -> None:
        m = _FRACAO.search(mensagem)
        if m:
            avancar(int(m[1]), int(m[2]))
        elif mensagem.strip():
            mostrar(mensagem.strip())

    return receber


# --------------------------------------------------------------------------- resumo e painéis


def resumo(linhas: Iterable[tuple[str, str, str, str]]) -> None:
    """Tabela (item, situação, detalhe, nível), com o ícone do nível na primeira coluna."""
    tabela = Table(
        box=box.ROUNDED,
        border_style=APAGADO,
        header_style=f"bold {OURO}",
        pad_edge=True,
        expand=False,
    )
    tabela.add_column("", no_wrap=True)
    tabela.add_column("Item", style="bold", no_wrap=True)
    tabela.add_column("Situação", no_wrap=True)
    tabela.add_column("Detalhe", style=APAGADO, overflow="fold")
    for item, situacao, detalhe, nivel in linhas:
        icone, cor = NIVEIS.get(nivel, ("·", APAGADO))
        tabela.add_row(
            Text(icone, style=f"bold {cor}"), item, Text(situacao, style=cor), Text(detalhe)
        )
    console.print(Padding(tabela, (0, 0, 0, 3)))


def marcadores(itens: Iterable[str], cor: str = AVISO) -> Table:
    """Lista com `•`; o texto longo quebra alinhado ao texto, não ao marcador."""
    grade = Table.grid(padding=(0, 1))
    grade.add_column(no_wrap=True)
    grade.add_column(overflow="fold")
    for item in itens:
        grade.add_row(Text("  •", style=f"bold {cor}"), Text(item))
    return grade


def comandos(pares: Iterable[tuple[str, str]]) -> Table:
    """Grade "comando · o que faz", com o comando em dourado."""
    grade = Table.grid(padding=(0, 3))
    grade.add_column(style=OURO, no_wrap=True)
    grade.add_column(style=APAGADO, overflow="fold")
    for comando, descricao in pares:
        grade.add_row(comando, descricao)
    return grade


def painel(titulo: str, nivel: str, corpo: Iterable[RenderableType]) -> None:
    """Painel final com o veredito no título, na cor do nível (`ok` ganha o ✦ da marca)."""
    icone, cor = NIVEIS.get(nivel, ("·", APAGADO))
    if nivel == "ok":
        icone = "✦"
    console.print()
    console.print(
        Padding(
            Panel(
                Group(*corpo),
                title=Text(f"{icone} {titulo}", style=f"bold {cor}"),
                title_align="left",
                border_style=cor,
                box=box.ROUNDED,
                padding=(1, 2),
            ),
            (0, 1),
        )
    )


# --------------------------------------------------------------------------- Palavra do Dia


def separar_titulo(markdown: str) -> tuple[str, str]:
    """(título do `# …` inicial, resto). Sem título, ("", markdown)."""
    primeira, _, resto = markdown.lstrip().partition("\n")
    if primeira.startswith("# "):
        return primeira[2:].strip(), resto.lstrip("\n")
    return "", markdown


def mensagem(markdown: str, rodape: str = "") -> None:
    """A mensagem formatada num painel: títulos, ênfases, citações e listas do Markdown; links
    viram o nome da fonte (clicável onde o terminal permitir), sem a URL inteira na tela."""
    titulo, corpo = separar_titulo(markdown)
    console.print(
        Padding(
            Panel(
                Markdown(corpo, hyperlinks=True),
                title=Text(f"✦ {titulo}", style=f"bold {OURO}") if titulo else None,
                title_align="left",
                subtitle=Text(rodape, style=APAGADO) if rodape else None,
                subtitle_align="right",
                border_style=OURO,
                box=box.ROUNDED,
                padding=(1, 2),
                width=min(console.width - 2, 104),
            ),
            (1, 0, 0, 1),
        )
    )


class _Checagem(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def ok(self) -> bool: ...

    @property
    def motivo(self) -> str: ...


def verificacao(checagens: Iterable[_Checagem]) -> None:
    """`✓ verificação 8/8   V1 ✓  V2 ✓ …`; as reprovadas, com o motivo, logo abaixo."""
    lista = list(checagens)
    if not lista:
        return
    aprovadas = sum(c.ok for c in lista)
    marcas = Text("  ").join(
        Text.assemble(
            (c.id, "bold" if c.ok else f"bold {ERRO}"),
            (" ✓" if c.ok else " ✗", OK if c.ok else ERRO),
        )
        for c in lista
    )
    texto = Text.assemble((f"verificação {aprovadas}/{len(lista)}   ", "bold"), marcas)
    linha("ok" if aprovadas == len(lista) else "erro", texto)
    for c in lista:
        if not c.ok and c.motivo:
            linha("erro", f"{c.id}: {c.motivo}", recuo=5)
