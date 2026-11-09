"""Modelos de dados do corpus bíblico."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Esquema = Literal["ms-vulg", "eng", "cnbb-lit"]

# Flags de versículo (coluna `versiculos.flags`)
F_TITULO_SALMO = "titulo_salmo"  # versículo é só o título do salmo
F_TITULO_SEPARADO = "titulo_separado"  # título fundido ao corpo foi separado em `titulo`
F_CORRIGIDO_MANUAL = "corrigido_manual"
F_CORRIGIDO_AUTO = "corrigido_auto"
F_DUPLICADO_RESOLVIDO = "duplicado_resolvido"
F_FUNDIDO = "fundido_com_seguinte"  # contém também o texto do(s) versículo(s) seguinte(s)
F_DEUTERO_TRECHO = "deutero_trecho"  # acréscimo grego em livro protocanônico (Dn, Est)
F_SEM_CORRESPONDENTE = "sem_correspondente"  # não alinhado ao esquema `eng`


@dataclass(slots=True)
class VersoBruto:
    """Versículo como veio da fonte, antes de qualquer limpeza."""

    traducao: str
    livro: str  # código USFM
    capitulo: int
    versiculo: int
    texto_bruto: str
    ocorrencia: int = 1  # ordem entre números repetidos no mesmo capítulo


@dataclass(slots=True)
class Verso:
    traducao: str
    livro: str
    capitulo: int
    versiculo: int
    texto: str
    texto_bruto: str
    titulo: str | None = None
    ref_canonica: str | None = None
    flags: list[str] = field(default_factory=list)
    fim_fundido: int | None = None  # último versículo contido, quando fundido

    @property
    def ref(self) -> str:
        return f"{self.livro}.{self.capitulo}.{self.versiculo}"

    @property
    def chave(self) -> tuple[str, int, int]:
        return (self.livro, self.capitulo, self.versiculo)

    def marcar(self, flag: str) -> None:
        if flag not in self.flags:
            self.flags.append(flag)

    @property
    def e_titulo(self) -> bool:
        return F_TITULO_SALMO in self.flags


@dataclass(frozen=True, slots=True)
class Traducao:
    id: str
    nome: str
    sigla: str
    tradicao: Literal["catolica", "protestante"]
    idioma: str
    versificacao: Esquema
    licenca: str
    atribuicao: str | None
    fonte_repo: str
    fonte_commit: str


TRADUCOES: dict[str, Traducao] = {
    "ms": Traducao(
        id="ms",
        nome="Matos Soares (1956)",
        sigla="MS",
        tradicao="catolica",
        idioma="pt-PT",
        versificacao="ms-vulg",
        licenca="não declarada (domínio público a confirmar, plano §13.3)",
        atribuicao="Bíblia Sagrada, trad. Pe. Manuel de Matos Soares (1956)",
        fonte_repo="Dancrf/biblia-db",
        fonte_commit="c5feefffc2d940efa7b11c49445c52ea1426d6a4",
    ),
    "blivre": Traducao(
        id="blivre",
        nome="Bíblia Livre (BLIVRE)",
        sigla="BLIVRE",
        tradicao="protestante",
        idioma="pt-BR",
        versificacao="eng",
        licenca="CC BY",
        atribuicao=(
            "Bíblia Livre (BLIVRE), © Diego Santos, Mario Sérgio e Marco Teles, "
            "Creative Commons Atribuição"
        ),
        fonte_repo="Projeto-Euaggelion/biblia.publica",
        fonte_commit="723197403aa40be0bd82e0b5997ca6aa2832850f",
    ),
}


@dataclass(frozen=True, slots=True)
class Lacuna:
    traducao: str
    livro: str
    capitulo: int
    versiculo: int
    status: Literal["aberta", "corrigida", "aceita"] = "aberta"
    tipo: Literal["ausente", "fundido", "desconhecido"] = "desconhecido"
    nota: str = ""


@dataclass(frozen=True, slots=True)
class Mapeamento:
    esquema_origem: str
    ref_origem: str
    esquema_destino: str
    ref_destino: str
    ref_destino_fim: str | None
    metodo: Literal["tabela", "alinhamento", "manual", "identidade", "marcador"]
    confianca: float
