from pathlib import Path

import pytest

from fiat_lux.biblia.correcoes import (
    Correcao,
    aplicar_edicoes,
    carregar_correcoes,
    resolver_duplicados,
)
from fiat_lux.biblia.modelos import VersoBruto


def vb(livro, cap, vers, texto, oc=1):
    return VersoBruto("ms", livro, cap, vers, texto, oc)


def test_identicos_mantem_o_primeiro():
    saida, dec = resolver_duplicados(
        [vb("ROM", 8, 26, "O Espírito ajuda"), vb("ROM", 8, 26, "O Espírito ajuda", 2)], []
    )
    assert len(saida) == 1 and dec[0].metodo == "identico"


def test_copia_espuria_de_outro_capitulo_e_descartada():
    brutos = [
        vb("EZR", 4, 14, "Nós, lembrando-nos do sal do palácio"),
        vb("EZR", 6, 14, "Nós, lembrando-nos do sal do palácio"),
        vb("EZR", 6, 14, "Os anciãos dos Judeus edificavam", 2),
    ]
    saida, dec = resolver_duplicados(brutos, [])
    textos = [v.texto_bruto for v in saida if v.capitulo == 6]
    assert textos == ["Os anciãos dos Judeus edificavam"]
    assert dec[0].metodo == "copia_espuria"


def test_manual_unir_e_manter():
    brutos = [vb("DAN", 2, 28, "O teu sonho..."), vb("DAN", 2, 28, "Mas no céu há um Deus", 2)]
    c = [Correcao("ms", "DAN", 2, 28, "unir_ocorrencias", "2,1", "")]
    saida, _ = resolver_duplicados(brutos, c)
    assert saida[0].texto_bruto == "Mas no céu há um Deus O teu sonho..."
    c2 = [Correcao("ms", "DAN", 2, 28, "manter_ocorrencia", "2", "")]
    assert resolver_duplicados(brutos, c2)[0][0].texto_bruto == "Mas no céu há um Deus"


def test_quase_identico_e_pendente():
    _, dec = resolver_duplicados(
        [vb("JOS", 8, 9, "entro Betel e Hai"), vb("JOS", 8, 9, "entre Betel e Hai", 2)], []
    )
    assert dec[0].metodo == "quase_identico"
    _, dec = resolver_duplicados(
        [vb("JOB", 1, 1, "aaaa bbbb"), vb("JOB", 1, 1, "zzzz yyyy xxxx", 2)], []
    )
    assert dec[0].metodo == "pendente"


def test_edicoes_dividir_encadeado_mover_e_substituir():
    brutos = [
        vb("SIR", 30, 21, "Primeiro. Não abandones a tua alma. O júbilo do coração é vida."),
        vb("1CH", 10, 26, "Os mais valentes"),
        vb("JER", 31, 24, "os lavrador® e"),
    ]
    c = [
        Correcao("ms", "SIR", 30, 21, "dividir", "Não abandones", ""),
        Correcao("ms", "SIR", 30, 22, "dividir", "O júbilo", ""),
        Correcao("ms", "1CH", 10, 26, "mover", "11,26", ""),
        Correcao("ms", "JER", 31, 24, "substituir", "lavrador®|lavradores", ""),
    ]
    saida, log = aplicar_edicoes(brutos, c)
    chaves = {(v.livro, v.capitulo, v.versiculo): v.texto_bruto for v in saida}
    assert chaves[("SIR", 30, 21)] == "Primeiro."
    assert chaves[("SIR", 30, 22)] == "Não abandones a tua alma."
    assert chaves[("SIR", 30, 23)] == "O júbilo do coração é vida."
    assert ("1CH", 11, 26) in chaves and ("1CH", 10, 26) not in chaves
    assert chaves[("JER", 31, 24)] == "os lavradores e"
    assert len(log) == 4


def test_marcador_inexistente_falha():
    with pytest.raises(ValueError):
        aplicar_edicoes(
            [vb("GEN", 1, 1, "No princípio")], [Correcao("ms", "GEN", 1, 1, "dividir", "XYZ", "")]
        )


def test_carregar_tsv_do_projeto(raiz: Path):
    c = carregar_correcoes(raiz / "config" / "correcoes_ms.tsv", "ms")
    assert c and all(x.traducao == "ms" for x in c)
    assert any(x.acao == "mover" for x in c)


def test_tsv_invalido(tmp_path: Path):
    p = tmp_path / "c.tsv"
    p.write_text("ms\tGEN\t1\t1\tinventada\tx\n", encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_correcoes(p)
