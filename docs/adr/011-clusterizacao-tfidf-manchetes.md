# ADR-011: Clusterização de manchetes por TF-IDF das manchetes do dia

- **Status:** aceito (2026-11-09). Substitui a escolha de vetores do plano §8.3.3.

## Contexto

O plano agrupava as manchetes com os embeddings do RAG (`multilingual-e5-base`, prefixo
`query:`), por cosseno, com ligação média e limiar de distância 0,35, a calibrar na Fase 7.
A calibração com as 753 manchetes únicas de 09/11/2026 mostrou três problemas:

- O e5 comprime o cosseno: entre manchetes **sem relação**, a mediana fica entre 0,77 e 0,84
  (p95 entre 0,85 e 0,90). Com 0,35, cada escopo virava **um único grupo**: 3 grupos para 753
  manchetes.
- Com limiares menores (0,10 a 0,21, ligação média ou completa), o e5 agrupa por assunto, não
  por história. Um acidente de trem no Egito caía junto com mísseis na Arábia Saudita, e
  notícias cearenses sem relação se juntavam por compartilharem "Ceará"/"Fortaleza".
- No modo leve, o LSA lexical foi ajustado na Bíblia e zera manchetes de vocabulário moderno.
  Isso derrubava o medidor ("cosine affinity cannot be used when X contains zero vectors").

## Decisão

Agrupar, em qualquer modo, por TF-IDF de n-gramas ajustado nas próprias manchetes do dia
(`vetores_textos_curtos`). A ligação é média e o limiar de distância é **0,80**
(similaridade ≥ 0,20; `noticias.limiar_cluster`). Um vetor nulo vira um grupo isolado, em vez de
derrubar a etapa.

## Consequências

- Os grupos ficam por história: 193 grupos para 753 manchetes. Exemplos: Trump–Irã com 7
  manchetes, Aramco com 4, gabarito do Enem, vagas de emprego, Mega-Sena.
- O medidor passa a independer do modelo neural, com o mesmo resultado no modo leve e no
  completo, e a etapa de notícias fica mais rápida.
- A mesma história em português e em inglês pode virar dois grupos no escopo mundial. Os
  temas do dia são deduplicados por categoria, o que limita o efeito.
- O limiar deve ser recalibrado com os 200 clusters rotulados da Fase 7 (anotação humana
  pendente).
