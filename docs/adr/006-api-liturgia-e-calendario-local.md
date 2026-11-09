# ADR-006: API de liturgia + calendário local

- **Status:** aceito (2026-11-09)

## Contexto

A API (`liturgia.up.railway.app/v2`) é não oficial e não informa tempo, semana nem ciclos.

## Decisão

Cache → API → calendário local, sempre enriquecido pelo cálculo local (Páscoa, Advento, ciclos A/B/C e I/II, regras do Brasil). `?periodo=7` pré-carrega o cache (ignora dia/mes/ano). Canário de contrato diário.

## Consequências

O calendário local acertou tempo e semana em 100% dos dias de 2026 e 2027 comparáveis com a API, e a cor em 502/503. Achados: referências reais com formatos não documentados (refrão '(R. …)', 'Sl 1Sm 2', 'ou mais breve', erros de digitação); para 2027 a API lista conjuntos de leituras de vários ciclos no mesmo domingo (usamos o primeiro e registramos aviso). Alternativas: só calendário local; romcal via Node.
