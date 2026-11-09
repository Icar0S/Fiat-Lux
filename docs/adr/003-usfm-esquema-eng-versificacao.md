# ADR-003: Códigos USFM, esquema canônico `eng` e versificação em três camadas

- **Status:** aceito (2026-11-09)

## Contexto

A MS segue a Vulgata (títulos de salmo contados ou fundidos, Sl 9 = 9+10, Dn 14 caps., Est 16 caps.); a BLIVRE segue a numeração inglesa (KJV, 31.101 versículos: junta 3Jo 1,15 e Ap 12,18); a liturgia usa a Nova Vulgata (AT em numeração HEBRAICA, salmos com capítulos da LXX).

## Decisão

USFM para os livros; `eng` (= BLIVRE) como esquema canônico interno. Camada 1: tabelas `vul.json`/`eng.json` da `ubsicap/versification_json` (MIT, embutidas no pacote), compostas em vul→org→eng (inclui `cnbb-lit`→eng). Camada 2: alinhamento MS↔BLIVRE por programação dinâmica em banda (TF-IDF de n-gramas de caracteres), com prior da tabela, bônus de fusão quando há lacuna logo depois e fusões proibidas entre salmos; o 'Aleluia' que a Vulgata move para o início do salmo é neutralizado. Camada 3: `config/versificacao_overrides.tsv` e `config/correcoes_ms.tsv` (manual, versionado).

## Consequências

Cobertura obtida: 99,94% dos versículos protocanônicos com confiança ≥ 0,8 (meta 99%), 28/28 checagens. O alinhamento também revelou e corrigiu versículos fundidos (100 divisões automáticas + 24 manuais) e um versículo no capítulo errado (1Cr 10,26 → 11,26). Alternativas: OSIS; Vulgata como canônica; TVTMS (STEPBible), formato mais complexo.
