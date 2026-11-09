# ADR-002: SQLite + FTS5 + sqlite-vec

- **Status:** aceito (2026-11-09)

## Contexto

Precisamos de BM25, vetores e metadados num único artefato que rode no CI sem servidor.

## Decisão

Dois bancos SQLite: `biblia.sqlite` (imutável, publicado como Release) e `estado.sqlite` (cresce a cada dia, persistido na branch `estado`). BM25 via FTS5 sobre `versiculos.texto_busca` (forma normalizada sem acentos e com variantes PT-PT→PT-BR, o que equivale à expansão bidirecional de §8.4.2). Vetores em `pericopes_emb` (BLOB float32, sempre) e em `pericopes_vec` (vec0) quando a extensão carrega.

## Consequências

Ajustes ao esquema do plano: `versiculos.titulo`, `versiculos.fim_fundido`, `versiculos.texto_busca`, `mapa_versificacao.ref_destino_fim`, `pericopes.versiculo_ids`, `lacunas.tipo/nota`. A busca densa usa numpy sobre a matriz (16,7 mil × 768 é trivial); a tabela vec0 fica disponível para consultas KNN. Para apagar a vec0 a extensão precisa estar carregada. Alternativas: Postgres + pgvector, Qdrant, LanceDB.
