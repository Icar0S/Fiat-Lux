# ADR-010: `multilingual-e5-base` (provisório) e embedder lexical de reserva

- **Status:** aceito (2026-11-09)

## Contexto

Modelos neurais pesam (torch + 1,1 GB do e5 + 2,3 GB do reranker) e deixam o CI lento.

## Decisão

Padrão de produção: `intfloat/multilingual-e5-base` (extra `[ml]`) e rerank `BAAI/bge-reranker-v2-m3`. Reserva: TF-IDF de n-gramas + LSA (256 dimensões), persistido junto do índice; o índice grava qual embedder o construiu.

## Consequências

Comparação lexical × neural registrada na avaliação (Fase 7); a comparação com `bge-m3` fica no backlog. O limiar de clusterização depende do embedder.

## Medições (09/11/2026, golden de recuperação v0, 40 casos, sem sementes)

| Perfil | Rerank | acerto@10 | recall@10 | nDCG@10 | MRR | Tempo (CPU local) |
|---|---|---|---|---|---|---|
| católico | lexical (denso + TF-IDF) | 0,85 | 0,29 | 0,35 | 0,68 | 17 s |
| católico | `bge-reranker-v2-m3` | 0,90 | 0,33 | 0,42 | 0,81 | 724 s |
| evangélico | lexical (denso + TF-IDF) | 0,975 | 0,34 | 0,42 | 0,80 | 7 s |
| evangélico | `bge-reranker-v2-m3` | 0,975 | 0,36 | 0,46 | 0,85 | 760 s |

O cross-encoder melhora a ordem (MRR +0,13 no católico), mas custa cerca de 0,45 s por par
consulta × perícope em CPU. Por isso a Palavra do Dia e a Palavra da Semana usam o rerank
neural, e o plano de leitura semanal (7 buscas a mais) usa o lexical. O tempo de cada rerank
aparece no log (`evento=rerank`). Nenhuma das configurações atinge ainda as metas do plano
(recall@10 ≥ 0,80; nDCG@10 ≥ 0,60): o MMR espalha o top-10 por livros diferentes, o que limita o
recall estrito, e o golden v0 ainda precisa de um segundo leitor.
