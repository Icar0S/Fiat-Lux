# Runbook de operação (plano §12)

Diagnóstico rápido: `fiatlux estado execucoes --ultimos 10` mostra status, etapa da falha,
duração e custo de cada execução. Toda falha ou fallback também gera uma mensagem ao
`TELEGRAM_ADMIN_CHAT_ID`.

| Sintoma | O que o sistema já fez | O que fazer |
|---|---|---|
| API de liturgia fora do ar | Usou o cache (prefetch de 7 dias) e, sem cache, o calendário local; mensagem marcada como `fallback` se faltar o Evangelho | Verificar o status da API; `fiatlux liturgia canario`; abrir issue no projeto da API |
| Esquema da API de liturgia mudou | O canário de contrato falha; o pipeline segue com o que conseguir validar | Atualizar `liturgia/modelos.py`, as fixtures e os testes de contrato |
| Referência litúrgica não reconhecida | Aviso no log; a leitura aparece com a referência da API | Acrescentar o caso a `eval/golden/referencias.yaml` (`scripts/gerar_golden_referencias.py`) e ajustar `biblia/referencias.py` |
| GDELT 429/5xx | Não insiste nos demais escopos; usa RSS; o medidor perde o tom | Normal em IPs compartilhados; ajustar `intervalo_s` e consultas em `config/fontes_noticias.yaml` |
| RSS de um veículo falhou | Os demais feeds seguem; aviso no log | Validar a URL; trocar o feed na configuração |
| Telegram 400 | Reenviou a parte sem formatação | Revisar o escape HTML em `entrega/telegram.py` |
| Telegram 401/403 | Mensagem arquivada, não enviada; status `falhou` | Conferir `TELEGRAM_BOT_TOKEN` e se o bot foi iniciado no chat |
| Índice bíblico ausente no CI | `fiatlux indice baixar-release` | Rodar o workflow `construir-indice.yml` |
| Custo acima do teto mensal | Só fallback (Evangelho + oração) e aviso | Revisar o tamanho dos prompts, o lote de clusters e `custo_max_mensal_usd` |
| Verificação reprovou após 2 revisões | Fallback e aviso com as violações | Ver `mensagens.verificacao_json`; ajustar o prompt P4 ou a regra |
| Sem `ANTHROPIC_API_KEY` | Classificação por palavras-chave, consultas determinísticas, seleção pelo escore; sem redação, sai o fallback | Definir a chave no `.env` (local) ou nos *secrets* (CI) |
| Recusa do modelo (`refusal`) | Sonnet: fallback server-side; Haiku: classificador por palavras-chave | Ver a categoria no log; reformular o prompt se for falso positivo |
| Pipeline lento, perto do `timeout-minutes` | Nada | Ver `evento=rerank` no log (pares e segundos); usar `--sem-rerank` ou `usar_rerank = false` em `config/settings.toml` (ADR-010) |
| Execução duplicada | Idempotência por (data, tipo, perfil, destinatário) | Nada; para reenviar, apague a linha em `mensagens` |

## Reprocessar um dia

```bash
uv run fiatlux palavra diaria --data 2026-11-08 --dry-run      # não envia
uv run fiatlux palavra diaria --data 2026-11-08 --sem-envio    # arquiva sem enviar
```

## Calibração do medidor

Registre a percepção diária ("o dia foi pesado?", 0–100) por 30 dias:
`uv run fiatlux estado percepcao 2026-11-09 60`. A Fase 7 compara essa série com o índice
composto (Spearman ρ ≥ 0,5).

## LGPD

`uv run fiatlux estado apagar-destinatario <chat_id> --sim` remove mensagens e feedback.
