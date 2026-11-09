# ADR-005: GDELT + RSS

- **Status:** aceito (2026-11-09)

## Contexto

Precisamos de volume e tom por escopo, sem custo.

## Decisão

GDELT DOC 2.0 (ArtList, TimelineTone, TimelineVol) para mundial e nacional; RSS (Google News por seção e busca, BBC Brasil, g1, Agência Brasil, Vatican News) como fallback e fonte do regional. Só metadados (§13.5).

## Consequências

Na validação da Fase 3, o GDELT respondeu 429 ('Please limit requests…') a toda requisição deste IP, mesmo com pausas longas: o cliente trata o 429 em texto e cai para o RSS sem insistir. No GitHub Actions (outro IP) o GDELT pode funcionar; sem ele, o índice do medidor usa volume e gravidade (sem tom). A busca regional exclui futebol ('Ceará' e 'Fortaleza' são também clubes) e há a categoria não temática `esporte_entretenimento`. Alternativas: NewsAPI (pago), scraping.
