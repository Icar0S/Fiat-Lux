"""Fase 5: verificação V1–V8, seleção em conjunto fechado, montagem e LLM (sem rede)."""

from __future__ import annotations

import datetime as dt

import pytest

from fiat_lux.agente.contexto import ContextoDoDia
from fiat_lux.agente.montagem import citacao_inline, data_extenso, substituir
from fiat_lux.agente.selecao import Escolha, deterministica, selecionar, validar
from fiat_lux.agente.verificacao import (
    EntradaVerificacao,
    RefPermitida,
    aprovado,
    extrair_referencias,
    verificar,
)
from fiat_lux.avaliacao import avaliar_adversarial
from fiat_lux.llm.cache import CacheLLM
from fiat_lux.llm.cliente import (
    ClienteComCache,
    ClienteOffline,
    Contabilidade,
    ErroLLM,
    ErroOrcamento,
    Pedido,
    RespostaLLM,
    TabelaPrecos,
    Uso,
)
from fiat_lux.llm.esquemas import Julgamento, Redacao, Selecao
from fiat_lux.llm.prompts import carregar, hash_conjunto
from fiat_lux.pastoral import neutralidade, perfil
from fiat_lux.rag.busca import Candidato


def cand(i: int, livro: str = "MAT", escore: float = 0.5, cap: int = 5, vers: int = 4) -> Candidato:
    return Candidato(
        id=f"p:{i}",
        traducao="ms",
        livro=livro,
        versiculo_ids=[i],
        refs_canonicas=[f"{livro}.{cap}.{vers}"],
        texto=f"Texto {i} da Escritura, longo o bastante para uma citação.",
        textos=[f"Texto {i}"],
        caps_vers=[(cap, vers)],
        escores={"S": escore},
    )


def redacao_valida(**mudancas: str) -> Redacao:
    base = {
        "olhar_sobre_o_dia": " ".join(["palavra"] * 60),
        "reflexao": "A Palavra diz: {{P1}} " + " ".join(["reflexão"] * 220),
        "ensinamento": "Deus está perto de quem sofre.",
        "gesto": "Reze hoje por uma pessoa que sofre.",
        "oracao": " ".join(["Senhor"] * 50),
    }
    base.update(mudancas)
    return Redacao(**base)


def entrada(r: Redacao, **kw) -> EntradaVerificacao:
    padrao = {
        "permitidas": [RefPermitida("MAT", 5, 1, 12), RefPermitida("JHN", 3, 16, 17)],
        "textos_permitidos": ["Bem-aventurados os que choram, porque serão consolados."],
        "urls_permitidas": {"https://g1.com/x"},
        "sensibilidades": set(),
        "perfil": "catolico",
        "livros_passagens": [("MAT", False)],
        "neutralidade": neutralidade(),
    }
    padrao.update(kw)
    return EntradaVerificacao(redacao=r, **padrao)


# ------------------------------------------------------------------ verificação


def test_rascunho_valido_passa_em_todos_os_portoes():
    checks = verificar(entrada(redacao_valida()))
    assert aprovado(checks), [c for c in checks if not c.ok]


def test_citacao_fiel_aprovada_e_inventada_reprovada():
    ok = redacao_valida(
        reflexao="Jesus disse: “Bem-aventurados os que choram, porque serão consolados” {{P1}} "
        + "x " * 200
    )
    assert aprovado(verificar(entrada(ok)))
    ruim = redacao_valida(
        reflexao="Está escrito: “quem doar o dízimo nesta semana ficará rico para sempre” {{P1}} "
        + "x " * 200
    )
    assert any(c.id == "V3" and not c.ok for c in verificar(entrada(ruim)))


def test_referencias_permitidas_e_fora_do_conjunto():
    assert extrair_referencias("Como em Mt 5,4 e em Jo 3,16-17.")[0][:3] == ("MAT", 5, 4)
    assert (
        extrair_referencias("os 3 filhos")[:1] == []
    )  # "Os" (Oseias) sem vírgula não é referência
    fora = redacao_valida(reflexao="{{P1}} Leia Ap 13,16. " + "x " * 200)
    assert any(c.id == "V2" and not c.ok for c in verificar(entrada(fora)))


def test_adversariais_do_golden():
    rel = avaliar_adversarial()
    falhas = [r for r in rel["resultados"] if not r["ok"]]
    assert not falhas, falhas


def test_juiz_reprova_partidarismo_e_castigo():
    julg = Julgamento(
        partidario=True,
        castigo_ou_profecia=False,
        exposicao_vitimas=False,
        tom_condenatorio=False,
        motivos=["elogia candidato"],
    )
    assert any(
        c.id == "V5" and not c.ok for c in verificar(entrada(redacao_valida(), julgamento=julg))
    )
    julg2 = Julgamento(
        partidario=False,
        castigo_ou_profecia=True,
        exposicao_vitimas=False,
        tom_condenatorio=False,
        motivos=["castigo"],
    )
    assert any(
        c.id == "V6" and not c.ok for c in verificar(entrada(redacao_valida(), julgamento=julg2))
    )


def test_mencao_politica_exige_juiz():
    r = redacao_valida(olhar_sobre_o_dia="Hoje Lula e o PT estiveram no noticiário. " + "x " * 50)
    assert any(c.id == "V5" and not c.ok for c in verificar(entrada(r)))
    neutro = Julgamento(
        partidario=False,
        castigo_ou_profecia=False,
        exposicao_vitimas=False,
        tom_condenatorio=False,
        motivos=[],
    )
    assert all(c.ok for c in verificar(entrada(r, julgamento=neutro)) if c.id == "V5")


# ------------------------------------------------------------------ seleção


def test_validacao_de_selecao_em_conjunto_fechado():
    mapa = {"cand_01": cand(1), "cand_02": cand(2, "JHN"), "cand_03": cand(3, "WIS")}
    mapa["cand_03"].livro = "WIS"
    s = Selecao(
        principal="cand_99",
        complementares=["cand_01", "cand_01"],
        temas_atendidos=[],
        ligacao_liturgica="",
        justificativa="",
        alertas=[],
    )
    erros = validar(s, mapa, perfil_evangelico=False)
    assert any("não está" in e for e in erros) and any("diferentes" in e for e in erros)
    s2 = Selecao(
        principal="cand_01",
        complementares=["cand_02", "cand_03"],
        temas_atendidos=[],
        ligacao_liturgica="",
        justificativa="",
        alertas=[],
    )
    assert validar(s2, mapa, perfil_evangelico=False) == []
    assert any("evangélico" in e for e in validar(s2, mapa, perfil_evangelico=True))


def test_selecao_offline_e_deterministica_com_outro_testamento():
    cands = [
        cand(1, "MAT", 0.9),
        cand(2, "MAT", 0.8),
        cand(3, "JHN", 0.7),
        cand(4, "PSA", 0.6, 23, 1),
    ]
    ctx = ContextoDoDia(data=dt.date(2026, 11, 8), liturgia=None, perfil=perfil("catolico"))
    e = selecionar(ctx, cands, ClienteOffline(), "offline")
    assert (
        e.principal.id == "p:1"
        and len(e.complementares) == 2
        and e.principal not in e.complementares
    )
    d = deterministica(cands, "teste")
    assert d.principal.id == "p:1" and any(c.testamento == "AT" for c in d.complementares)


def test_selecao_invalida_duas_vezes_cai_no_deterministico():
    class Teimoso:
        nome = "teimoso"

        def gerar(self, pedido, esquema):
            return RespostaLLM(
                dados=Selecao(
                    principal="cand_42",
                    complementares=[],
                    temas_atendidos=[],
                    ligacao_liturgica="",
                    justificativa="",
                    alertas=[],
                ),
                modelo="x",
            )

    ctx = ContextoDoDia(data=dt.date(2026, 11, 8), liturgia=None, perfil=perfil("catolico"))
    e = selecionar(ctx, [cand(1, escore=0.9), cand(2, "JHN"), cand(3, "PSA")], Teimoso(), "x")
    assert e.metodo == "deterministico" and "inválida" in e.alertas[0]


# ------------------------------------------------------------------ montagem


def test_substituicao_de_placeholders_e_citacao_inline():
    c = cand(1)
    c.texto = "Bem-aventurados os que choram, porque serão consolados."
    e = Escolha(principal=c, complementares=[cand(2, "JHN"), cand(3, "PSA")])
    txt = substituir("A Palavra diz: {{P1}} e também {{C1}}.", e)
    assert "“Bem-aventurados os que choram, porque serão consolados.” (Mt 5,4)" in txt
    assert "{{" not in txt
    longo = cand(5)
    longo.texto = " ".join(f"palavra{i}" for i in range(60))
    assert citacao_inline(longo).count(" ") < 40 and "…" in citacao_inline(longo)


def test_data_extenso():
    assert data_extenso(dt.date(2026, 11, 8)) == "domingo, 8 de novembro de 2026"


# ------------------------------------------------------------------ LLM


def test_prompts_carregam_e_tem_hash_estavel():
    p = carregar(
        "classificacao", categorias={"luto_tragedia": type("C", (), {"descricao": "Mortes"})()}
    )
    assert "luto_tragedia" in p.texto and len(p.sha256) == 64
    assert "{{P1}}" in carregar("redacao").texto
    assert hash_conjunto() == hash_conjunto()


def test_cache_evita_segunda_chamada(tmp_path):
    offline = ClienteOffline()
    cli = ClienteComCache(offline, CacheLLM(tmp_path / "c.sqlite"))
    pedido = Pedido("juiz", "m", "s", "<mensagem>texto</mensagem>")
    r1 = cli.gerar(pedido, Julgamento)
    r2 = cli.gerar(pedido, Julgamento)
    assert not r1.do_cache and r2.do_cache and len(offline.chamadas) == 1


def test_custos_e_teto_mensal():
    t = TabelaPrecos({"modelo-pago": (2.0, 10.0)})
    assert t.custo(
        "modelo-pago", Uso(tokens_entrada=1_000_000, tokens_saida=100_000)
    ) == pytest.approx(3.0)
    c = Contabilidade(gasto_mes_usd=9.99, teto_mes_usd=10.0)
    c.uso.custo_usd = 0.02
    with pytest.raises(ErroOrcamento):
        c.checar()


def test_offline_sem_manipulador():
    with pytest.raises(ErroLLM):
        ClienteOffline({}).gerar(Pedido("inexistente", "m", "s", "u"), Julgamento)


def test_redacao_offline_nunca_copia_manchetes():
    """O cliente offline fala das categorias; manchetes cruas (com nomes) não entram no texto."""
    from fiat_lux.llm.cliente import Pedido
    from fiat_lux.llm.offline import embutir, redacao

    dados = {
        "temas": [
            {"categoria": "guerra_conflito", "rotulo": "Arab News | Trump says he is unlikely to"},
            {"categoria": "luto_tragedia", "rotulo": "Estudante de 16 anos morre durante prova"},
        ],
        "tempo": "comum",
        "evangelho_ref": "Jo 2,13-22",
    }
    out = redacao(Pedido("redacao", "offline", "", embutir(dados)))
    olhar = out["olhar_sobre_o_dia"]
    assert "Trump" not in olhar and "Estudante" not in olhar
    assert "guerras e conflitos" in olhar and "luto e tragédias" in olhar
    assert 40 <= len(olhar.split()) <= 90


def test_sem_servidor_de_llm_falha_com_erro_claro(monkeypatch):
    """Sem FIATLUX_LLM_URL (e fora do dry-run), as etapas recebem ErroLLM e usam as reservas."""
    import pytest

    from fiat_lux.config import Settings
    from fiat_lux.llm.cliente import ErroLLM, Pedido
    from fiat_lux.llm.esquemas import Consultas
    from fiat_lux.llm.fabrica import criar_cliente

    monkeypatch.delenv("FIATLUX_LLM_URL", raising=False)
    s = Settings(_env_file=None)
    cliente = criar_cliente(s, "local")
    assert cliente.nome == "local:sem-servidor"
    with pytest.raises(ErroLLM, match="FIATLUX_LLM_URL"):
        cliente.gerar(Pedido("consultas", "", "", ""), Consultas)


def test_provedor_desconhecido_diz_as_opcoes():
    import pytest

    from fiat_lux.config import Settings
    from fiat_lux.llm.fabrica import criar_cliente

    with pytest.raises(ValueError, match="use local ou offline"):
        criar_cliente(Settings(_env_file=None), "anthropic")
