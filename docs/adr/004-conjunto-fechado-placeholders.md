# ADR-004: Seleção em conjunto fechado + placeholders

- **Status:** aceito (2026-11-09)

## Contexto

Alucinação de citação é o risco crítico (R7).

## Decisão

O LLM escolhe entre 12 candidatos identificados por id; escreve com {{P1}}/{{C1}}/{{C2}} e o texto é inserido a partir da base. O recorte (1–5 versículos) é feito ANTES da seleção, para que o modelo veja exatamente o trecho que será citado. V2/V3 bloqueiam qualquer referência ou citação fora do conjunto. Na montagem, {{P1}} vira uma citação curta inline (o texto completo já aparece em destaque), evitando duplicar o versículo.

## Consequências

Citação inválida = 0 por construção (verificado na avaliação E2E). Alternativa descartada: geração livre com verificação posterior.
