# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões em SemVer.

## [0.1.0] — 2026-11-09

Primeira implementação do [plano](plano.md), fases F0–F8 (nome definitivo: **Fiat Lux**; o
plano usava "Lâmpada" como nome provisório).

### Adicionado

- **F0 Fundação:** projeto Python 3.12 + uv, CLI `fiatlux` (Typer), configuração com
  pydantic-settings + `config/settings.toml`, logs estruturados (structlog), ruff, mypy (estrito
  no núcleo), pre-commit, justfile, workflows do GitHub Actions, ADRs 001–010.
- **F1 Corpus:** catálogo de 73 livros (USFM, siglas CNBB/MS/BLIVRE, OSIS); download fixado por
  commit + SHA-256; ingestão MS e BLIVRE; limpeza determinística com contadores; títulos de
  salmos separados; duplicados resolvidos (automático + manual); versificação em três camadas
  (tabelas ubsicap + alinhamento MS↔BLIVRE + correções manuais) com 99,94% dos versículos
  protocanônicos com confiança ≥ 0,8; 165 lacunas classificadas (0 abertas); referências
  cruzadas (344 mil); parser de referências litúrgicas validado em 1.560 referências reais;
  repositório de consultas; exportação de 2.523 capítulos em Markdown (Obsidian); relatório
  `docs/qualidade-corpus.md`.
- **F2 Liturgia:** cliente da API v2 com retry, calendário litúrgico local (Páscoa, Advento,
  ciclos, regras do Brasil; 100% de acerto de tempo/semana em 2026–2027), serviço com cache,
  prefetch de 7 dias, fallback local e canário de contrato.
- **F3 Notícias:** GDELT (ArtList/Timeline, tratamento do 429 em texto) e RSS por escopo,
  normalização, deduplicação, clusterização aglomerativa, classificação pastoral (P1, com
  reserva por palavras-chave e saneamento contra injeção) e Índice de Tensão com composto
  renormalizado.
- **F4 RAG:** perícopes por família de livro (16.703), índice FTS5 + vetores (sqlite-vec),
  embeddings `multilingual-e5-base` ou lexical (TF-IDF + LSA), busca híbrida com RRF, rerank
  (`bge-reranker-v2-m3` ou lexical), boosts A/T/X/Q/P, MMR e recorte de 1–5 versículos.
- **F5 Agente:** `LLMClient` (Claude com saída estruturada, esforço por tarefa, cache de prompt e
  fallback de recusa; offline determinístico; cache por hash), prompts P1–P6 versionados com
  hash, contexto do dia, consultas, seleção em conjunto fechado, redação com placeholders,
  verificação V1–V8, fallback seguro e template da mensagem diária.
- **F6 Entrega:** arquivo em `saidas/`, Telegram (HTML, divisão, allowlist, reenvio sem
  formatação, feedback por `getUpdates`), e-mail (SMTP), idempotência e alerta ao admin.
- **F7 Avaliação:** goldens de referências (1.560), recuperação (40 casos) e adversariais (15),
  testes metamórficos MR1/MR3/MR4/MR6, E2E em dias congelados e relatório HTML/JSON.
- **F8 Semanal:** temas recorrentes, gráfico de 7 dias (matplotlib), Palavra da Semana,
  plano de leitura ligado ao Evangelho de cada dia (perícope inteira, sem repetir o próprio
  Evangelho) e perguntas para partilha. Os temas só aparecem com o resumo neutro do P1 quando
  não citam política; senão, e sempre que a classificação caiu na reserva por palavras-chave,
  aparece o nome da categoria pastoral (nunca a manchete crua).

- **Documentação:** [guia do usuário](docs/guia-do-usuario.md) (instalação, primeira execução,
  comandos, Telegram, agendamento, problemas comuns), runbook e ADRs 001–011. O roteiro de
  primeira execução do README foi validado num clone limpo.
- Sem `ANTHROPIC_API_KEY` e fora do `--dry-run`, cada etapa de LLM usa a sua reserva com um aviso
  claro, e a mensagem sai como fallback (antes: erro interno do SDK).

### Medições

- Avaliação completa: parser 100% (1.560 referências), adversariais 15/15, MR1/MR3/MR4/MR6,
  E2E em 30 dias congelados com 0 citação inválida e 0% de fallback.
- Recuperação abaixo das metas do plano (recall@10 0,33/0,36 e nDCG@10 0,42/0,46 com o
  cross-encoder; acerto@10 0,90/0,975). Ablação lexical × neural no ADR-010.

### Desvios do plano (detalhes nos ADRs)

- `temperature` não é mais aceito pela API (versão 2026-10-21); as temperaturas do plano
  viraram níveis de `output_config.effort` (ADR-008).
- O GDELT recusou todas as requisições deste IP (429); o RSS cobre os três escopos (ADR-005).
- Formatos reais de referência e do calendário diferem do documentado; o parser e o serviço
  foram ampliados a partir de 730 dias reais da API (ADR-006).
- As manchetes são agrupadas por TF-IDF das manchetes do dia (limiar 0,80), não pelos
  embeddings do RAG. Com o e5 e o limiar 0,35 do plano, cada escopo virava um único grupo
  (ADR-011).
- O rerank neural usa só as 4 primeiras consultas: resumo do Evangelho e consultas do LLM
  (`rag.max_consultas_rerank`). Isso mantém a execução diária abaixo de 10 min em CPU
  (RNF-06).
