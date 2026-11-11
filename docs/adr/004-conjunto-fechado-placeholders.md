# ADR-004: Seleção em conjunto fechado + placeholders

- **Status:** aceito (2026-11-09)

## Contexto

Alucinação de citação é o risco crítico (R7).

## Decisão

O LLM escolhe entre 12 candidatos identificados por id; escreve com {{P1}}/{{C1}}/{{C2}} e o texto é inserido a partir da base. O recorte (1–5 versículos) é feito ANTES da seleção, para que o modelo veja exatamente o trecho que será citado. V2/V3 bloqueiam qualquer referência ou citação fora do conjunto. Na montagem, {{P1}} vira uma citação curta inline (o texto completo já aparece em destaque), evitando duplicar o versículo.

## Consequências

Citação inválida = 0 por construção (verificado na avaliação E2E). Alternativa descartada: geração livre com verificação posterior.

## Adendo (2026-11-11): modelos pequenos

Com o LLM local (ADR-012), o `qwen2.5-coder:7b` e o `qwen3:8b` escolhiam passagens da lista, mas
respondiam com a referência ("Lc 17,16") ou com o texto do candidato no lugar do id, e nunca
escreviam o `{{P1}}`: toda execução terminava no fallback. Duas regras, sem abrir o conjunto:

- **Ids pela referência ou pelo texto:** a resposta da seleção que indica um único candidato da
  lista (pelo id em outra grafia, pela referência ou por um trecho de 6 palavras ou mais do
  texto) vale como o id dele. O que não indica nenhum candidato, ou indica mais de um, continua
  inválido.
- **Marcadores ajustados antes da verificação:** sem o `{{P1}}`, o Fiat Lux põe `Diz a
  Escritura: {{P1}}.` depois da frase da reflexão que cita a passagem principal (ou fala do
  livro dela; sem nenhuma, depois da primeira frase). Repetições viram a referência da passagem,
  e marcadores desconhecidos saem. O texto bíblico continua vindo só da base, e V2/V3 continuam
  bloqueando referências e citações fora do conjunto.
