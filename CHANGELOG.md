# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões em SemVer.

## [Não lançado]

### Mudado

- **LLM local, sem APIs de terceiros ([ADR-012](docs/adr/012-llm-local-por-api-http.md)):** o
  Fiat Lux fala com um servidor de LLM pela API HTTP (`POST /v1/chat`, `GET /v1/models`,
  `Authorization: Bearer`). URL, chave e modelos ficam só no `.env` (`FIATLUX_LLM_URL`,
  `FIATLUX_LLM_CHAVE`, `FIATLUX_LLM_MODELO` e os específicos por tarefa) e, no CI, em secrets e
  variables. Quem clonar aponta para o servidor que quiser. Sem modelo configurado, vale o padrão
  do servidor; sem URL, o `--dry-run` usa o cliente offline.
- **Saída estruturada pelo prompt:** a API não tem modo JSON. Um molde da resposta, gerado do
  esquema Pydantic, vai no prompt de sistema (com o JSON Schema cru, o `qwen3:8b` devolvia
  `{"properties": {…}}`). A resposta é extraída (tolera `<think>`, cercas de código, texto em
  volta e um único campo embrulhando tudo) e validada. Fora do formato, o pedido é refeito com
  o erro explicado.
- **Temperatura por tarefa** no lugar do esforço (classificação 0,1 · consultas 0,3 · seleção
  0,2 · redação 0,7 · juiz 0) e `max_tokens` até 8192, o teto da API.
- **Fila do servidor:** 429 e 503 esperam o `Retry-After`, até 15 min somados por execução. Os
  workflows diário e semanal passaram a 45 e 60 min, porque o servidor atende um pedido por vez.

### Adicionado

- **Configuração em um comando:** `configurar.ps1` (Windows PowerShell 5.1+) e `configurar.sh`
  (Linux/macOS, bash 3.2+). Acham o `uv` (PATH, instalador oficial, winget, scoop, chocolatey,
  `pip`/`pipx` de qualquer Python, conda) ou instalam o oficial. No Windows, põem a pasta dele
  no PATH do usuário (registro, sem duplicar, preservando `REG_EXPAND_SZ`). Escolhem o modo
  (completo se os modelos neurais já estiverem instalados ou baixados), rodam `uv sync` e
  chamam `fiatlux configurar`. Avisam sobre caminhos longos demais no Windows.
- **`fiatlux configurar`:** cria o `.env`, pergunta (opcionalmente) a URL e a chave do servidor
  de LLM e configura o Telegram (confere o token com `getMe`, acha os `chat_id` com `getUpdates`
  e manda uma mensagem de teste). Confere o servidor sem gerar texto (`GET /v1/models`): chave,
  URL, se os modelos de cada tarefa existem e estão baixados, e a janela de contexto. Uma chave
  recusada ou uma URL errada podem ser corrigidas na hora. Monta a base bíblica só se a validação
  falhar e reconstrói o índice só se ele faltar, estiver incompleto ou não combinar com o modo.
  Termina com uma Palavra do Dia de teste (`--dry-run`; com o cliente offline enquanto o LLM não
  responde), um resumo, o que falta para a mensagem sair completa e o veredito na última linha
  ("Tudo pronto." só quando é verdade). Pode ser repetido; não pergunta nada sem um console de
  verdade (no Windows, `isatty()` também é verdadeiro para o `NUL`).
- **`ErroPermanente` e disjuntor no cliente de LLM:** chave recusada, URL errada, servidor
  inalcançável depois de três tentativas e fila esgotada não passam tentando de novo. Na primeira
  falha, o cliente para de chamar o servidor até o fim da execução (um modelo inexistente fecha
  só aquele modelo), e as etapas vão direto às reservas. Sem o modelo de geração, a busca e o
  rerank (≈ 1 min em CPU) são pulados, porque o fallback sairia de qualquer jeito. Os avisos dizem
  o motivo uma vez, no topo ("LLM indisponível nesta execução: …"), e o alerta ao administrador
  traz o mesmo motivo.
- Guia e README: configuração automática como caminho recomendado, o contrato da API do LLM
  (guia, seção 8) e problemas novos na tabela (uv fora do PATH, política de execução, PATH no VS
  Code, `.venv` em uso, chave recusada, URL errada, servidor inalcançável, modelo que falta,
  resposta fora do formato).

### Removido

- Claude e o SDK `anthropic`: `ClienteClaude`, `ANTHROPIC_API_KEY`, o esforço por tarefa
  (`output_config.effort`), o fallback server-side, o tratamento de recusas (`refusal`) e os
  preços dos modelos Claude (a tabela de preços fica vazia: custo zero num servidor local). Sem o
  SDK, o caminho mais longo da `.venv` no modo leve caiu de ~165 para 117 caracteres.

### Corrigido

- Ruído do Hugging Face na saída: as linhas `HTTP Request: … 404` vinham do logger `httpx2`
  (o cliente HTTP do `huggingface_hub` 2.x), e o aviso de "unauthenticated requests" é um
  cabeçalho do servidor. Agora `httpx2` fica em WARNING e `HF_HUB_VERBOSITY` é `error` por
  padrão; erros continuam aparecendo.
- O traceback de uma falha ia para o console junto com a mensagem de contingência; agora fica no
  log JSON e, no console, só com `--verboso`.
- A seleção de passagens, depois de uma falha da API, repetia o pedido dizendo ao modelo que
  "a resposta anterior foi inválida", e o aviso dizia "inválida" quando a causa era a rede.
- Barras "Loading weights" do transformers 5 a cada modelo carregado; as barras de download do
  `huggingface_hub` continuam.
- No `configurar`, os avisos de log repetiam o que o resumo já diz: durante o comando, o console
  só mostra erros (com `--verboso` ou `--json-logs`, nada muda).
- Aviso do GDELT sem repetição: `GDELT recusou por limite de taxa (429); notícias só do RSS`.

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
