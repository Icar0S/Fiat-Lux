"""Serviço de liturgia (plano §8.2.3): cache → API → calendário local, sempre enriquecido."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from fiat_lux.biblia.referencias import (
    Referencia,
    ReferenciaInvalida,
    parse_com_contexto,
    tentar_parse,
)
from fiat_lux.estado import Estado
from fiat_lux.liturgia import calendario_local
from fiat_lux.liturgia.cliente_api import ClienteLiturgia, ErroApiLiturgia
from fiat_lux.liturgia.modelos import (
    PRECEDENCIA,
    DiaLiturgico,
    Grau,
    Leitura,
    LeituraApi,
    RespostaV2,
    TipoLeitura,
)
from fiat_lux.logs import log

_NOTA = re.compile(r"\(([^()]*[A-Za-zÀ-ÿ]{3,}[^()]*)\)\s*$")
_TIPOS: tuple[tuple[str, TipoLeitura], ...] = (
    ("primeiraLeitura", "primeira"),
    ("salmo", "salmo"),
    ("segundaLeitura", "segunda"),
    ("evangelho", "evangelho"),
    ("extras", "extra"),
)


def grau_do_nome(nome: str, data: dt.date) -> Grau:
    n = nome.casefold()
    if n.endswith("solenidade") or "páscoa na ressurreição" in n or "vigília pascal" in n:
        return "solenidade"
    if n.endswith("festa"):
        return "festa"
    if n.endswith("memória facultativa"):
        return "memoria_facultativa"
    if n.endswith("memória"):
        return "memoria"
    if data.weekday() == 6 or "domingo" in n:
        return "domingo"
    if re.search(r"\b(feira|sábado|semana|cinzas|oitava|tempo do natal)\b", n):
        return "feria"
    return "memoria_facultativa"  # santo sem grau explícito


def _leituras(resp: RespostaV2) -> list[Leitura]:
    """Converte as leituras; a forma breve sem livro ("mais breve 10,17-27") herda o livro."""
    saida: list[Leitura] = []
    for campo, tipo in _TIPOS:
        lista: list[LeituraApi] = getattr(resp.leituras, campo)
        anteriores: list[Referencia] = []
        for x in lista:
            if not x.referencia and not x.texto:
                continue
            ref = x.referencia.strip()
            try:
                r = parse_com_contexto(ref, anteriores)
            except (ReferenciaInvalida, ValueError, KeyError):
                r = None
            if r is not None:
                if anteriores and tentar_parse(ref) is None:  # sem livro: reescreve com a sigla
                    sem_prefixo = re.sub(r"^\s*(?:ou\s+)?(?:mais|forma)\s+\w+\s*:?\s*", "", ref)
                    ref = f"{r.livro_obj.sigla_pt} {sem_prefixo} (mais breve)"
                anteriores.append(r)
            m = _NOTA.search(ref)
            saida.append(
                Leitura(
                    tipo=tipo,
                    referencia=ref,
                    titulo=x.titulo,
                    texto=(x.texto or "").strip(),
                    refrao=x.refrao,
                    nota=m.group(1).strip() if m else None,
                )
            )
    return saida


def de_resposta(resp: RespostaV2, fonte: str = "api_v2") -> DiaLiturgico:
    data = resp.data_iso
    base = calendario_local.calcular(data)
    avisos: list[str] = []
    cor = resp.cor.strip().capitalize() or base.cor_padrao
    if cor not in {"Verde", "Vermelho", "Roxo", "Rosa", "Branco", "Preto", "Azul"}:
        avisos.append(f"cor inesperada da API: {resp.cor!r}")
    leituras = _leituras(resp)
    for lt in leituras:
        if lt.referencia and tentar_parse(lt.referencia) is None:
            avisos.append(f"referência não reconhecida: {lt.referencia!r}")
    primeiras = [x for x in leituras if x.tipo == "primeira" and not x.nota]
    if len(primeiras) > 1:
        avisos.append(
            f"a API listou {len(primeiras)} conjuntos de leituras; usado o primeiro "
            f"(ciclo {base.ciclo_dominical}/{base.ciclo_ferial})"
        )
    oracoes = {k: v for k, v in resp.oracoes.model_dump().items() if isinstance(v, str) and v}
    return DiaLiturgico(
        data=data,
        celebracao=resp.liturgia.strip(),
        grau=grau_do_nome(resp.liturgia, data),
        cor=cor,
        tempo=base.tempo,
        semana=base.semana,
        ciclo_dominical=base.ciclo_dominical,
        ciclo_ferial=base.ciclo_ferial,
        leituras=leituras,
        oracoes=oracoes,
        antifonas=dict(resp.antifonas),
        fonte=fonte,  # type: ignore[arg-type]
        avisos=avisos,
    )


def local(data: dt.date, leituras: list[Leitura] | None = None) -> DiaLiturgico:
    base = calendario_local.calcular(data)
    return DiaLiturgico(
        data=data,
        celebracao=base.nome_estimado,
        grau=base.grau_estimado,
        cor=base.cor_padrao,
        tempo=base.tempo,
        semana=base.semana,
        ciclo_dominical=base.ciclo_dominical,
        ciclo_ferial=base.ciclo_ferial,
        leituras=leituras or [],
        fonte="calendario_local",
        avisos=["liturgia calculada localmente (API indisponível); leituras podem estar ausentes"],
    )


def escolher(
    celebracoes: list[DiaLiturgico], memoria_facultativa_usa_feria: bool = True
) -> DiaLiturgico:
    """Várias celebrações no dia (API v3): solenidade > domingo > festa > memória > féria."""
    if len(celebracoes) == 1:
        return celebracoes[0]
    ordenadas = sorted(celebracoes, key=lambda c: PRECEDENCIA[c.grau])
    topo = ordenadas[0]
    if topo.grau == "memoria_facultativa" and memoria_facultativa_usa_feria:
        ferias = [c for c in celebracoes if c.grau == "feria"]
        if ferias:
            return ferias[0].model_copy(
                update={"avisos": [*ferias[0].avisos, f"memória facultativa: {topo.celebracao}"]}
            )
    return topo


class ServicoLiturgia:
    def __init__(self, estado: Estado, cliente: ClienteLiturgia | None = None) -> None:
        self.estado = estado
        self.cliente = cliente

    def _do_cache(self, data: dt.date) -> DiaLiturgico | None:
        row = self.estado.dia_liturgico(data)
        if row is None or not row["bruto_json"]:
            return None
        try:
            return de_resposta(
                RespostaV2.model_validate(json.loads(row["bruto_json"])), fonte="cache"
            )
        except ValueError:
            return None

    def _gravar(self, resp: RespostaV2, dia: DiaLiturgico) -> None:
        self.estado.gravar_dia_liturgico(
            dia.data,
            {
                "celebracao": dia.celebracao,
                "cor": dia.cor,
                "tempo": dia.tempo,
                "semana": dia.semana,
                "ciclo_dominical": dia.ciclo_dominical,
                "ciclo_ferial": dia.ciclo_ferial,
                "leituras": [x.model_dump() for x in dia.leituras],
                "fonte": "api_v2",
                "bruto": resp.model_dump(),
            },
        )

    def obter(self, data: dt.date, usar_rede: bool = True) -> DiaLiturgico:
        cache = self._do_cache(data)
        if cache is not None:
            return cache
        if usar_rede and self.cliente is not None:
            try:
                resp = self.cliente.dia(data)
                if resp is not None:
                    dia = de_resposta(resp)
                    self._gravar(resp, dia)
                    return dia
                log().warning("liturgia_404", data=data.isoformat())
            except ErroApiLiturgia as e:
                log().warning("liturgia_api_falhou", data=data.isoformat(), erro=str(e))
        return local(data)

    def prefetch(self, dias: int = 7) -> int:
        if self.cliente is None:
            return 0
        n = 0
        for resp in self.cliente.periodo(dias):
            dia = de_resposta(resp)
            self._gravar(resp, dia)
            n += 1
        return n


def canario(resp: dict[str, Any]) -> list[str]:
    """Teste de contrato diário: lista problemas no esquema da resposta (vazio = ok)."""
    problemas: list[str] = []
    for chave in ("data", "liturgia", "cor", "leituras"):
        if chave not in resp:
            problemas.append(f"campo ausente: {chave}")
    leituras = resp.get("leituras", {})
    if isinstance(leituras, dict):
        for chave in ("primeiraLeitura", "salmo", "evangelho"):
            if chave not in leituras:
                problemas.append(f"leituras.{chave} ausente")
        for item in leituras.get("evangelho", []) or []:
            if "referencia" not in item or "texto" not in item:
                problemas.append("evangelho sem referencia/texto")
    else:
        problemas.append("leituras não é objeto")
    try:
        RespostaV2.model_validate(resp)
    except ValueError as e:
        problemas.append(f"validação: {e}")
    return problemas
