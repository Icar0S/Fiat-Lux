# ADR-008: LLMClient como Protocol, Claude como padrão; esforço no lugar de temperatura

- **Status:** aceito (2026-11-09)

## Contexto

O plano previa temperaturas por tarefa (0 / 0,2 / 0,6). A API versão 2026-10-21 (SDK `anthropic` 2.x) rejeita `temperature`, `top_p` e `top_k` em todos os modelos, e Haiku 5.5 / Sonnet 5.5 só amostram com o padrão.

## Decisão

`LLMClient` (Protocol) com `ClienteClaude` (saída estruturada via `beta.messages.parse` + Pydantic, `output_config.effort` por tarefa, cache de prompt automático, `fallbacks: "default"` no Sonnet 5.5, tratamento de `refusal`), `ClienteOffline` (determinístico, para testes e dry-run sem chave) e `ClienteComCache` (hash da entrada). Modelos do plano: `claude-haiku-5-5` (classificação, consultas, resumo) e `claude-sonnet-5-5` (seleção, redação, juiz). Esforço: classificação/consultas/juiz `low`, seleção/redação `medium`.

## Consequências

A reprodutibilidade que a temperatura 0 daria vem do cache por hash da entrada. Haiku 5.5 não tem fallback server-side: uma recusa cai no classificador por palavras-chave. Preços configurados: Haiku 5.5 US$ 0,10/0,50 e Sonnet 5.5 US$ 2/10 por milhão de tokens.
