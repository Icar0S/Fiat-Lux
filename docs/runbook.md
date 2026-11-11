# Runbook de operação (plano §12)

Diagnóstico rápido: `fiatlux estado execucoes --ultimos 10` mostra status, etapa da falha,
duração e custo de cada execução. Toda falha ou fallback também gera um e-mail `Fiat Lux: alerta`
para o `EMAIL_ADMIN` (sem ele, para quem envia); com o Telegram ligado e sem e-mail, uma mensagem
ao `TELEGRAM_ADMIN_CHAT_ID`.

| Sintoma | O que o sistema já fez | O que fazer |
|---|---|---|
| API de liturgia fora do ar | Usou o cache (prefetch de 7 dias) e, sem cache, o calendário local; mensagem marcada como `fallback` se faltar o Evangelho | Verificar o status da API; `fiatlux liturgia canario`; abrir issue no projeto da API |
| Esquema da API de liturgia mudou | O canário de contrato falha; o pipeline segue com o que conseguir validar | Atualizar `liturgia/modelos.py`, as fixtures e os testes de contrato |
| Referência litúrgica não reconhecida | Aviso no log; a leitura aparece com a referência da API | Acrescentar o caso a `eval/golden/referencias.yaml` (`scripts/gerar_golden_referencias.py`) e ajustar `biblia/referencias.py` |
| GDELT 429/5xx | Não insiste nos demais escopos; usa RSS; o medidor perde o tom | Normal em IPs compartilhados; ajustar `intervalo_s` e consultas em `config/fontes_noticias.yaml` |
| RSS de um veículo falhou | Os demais feeds seguem; aviso no log | Validar a URL; trocar o feed na configuração |
| E-mail: senha recusada (535), servidor inalcançável ou sem TLS | Mensagem arquivada, não enviada; status `falhou`; aviso com o destinatário mascarado (`ma…@exemplo.com`) | Conferir `SMTP_HOST`, `SMTP_PORT` e `SMTP_SENHA` (no Gmail, senha de app); `fiatlux configurar` entra na conta sem enviar nada |
| Seleção do LLM com a referência no lugar do id | Aceitou a referência (ou o texto) do candidato como o id dele; o log tem `selecao_ids_pela_referencia` | Nada; se o modelo insistir em passagens fora da lista, cai na seleção pelo escore |
| Redação sem o `{{P1}}` ou com marcador repetido | Pôs o `{{P1}}` depois da frase que cita a passagem principal (ou da primeira frase) e tirou as repetições; log `redacao_marcadores_ajustados` | Nada; o texto bíblico continua vindo da base |
| Telegram 400 | Reenviou a parte sem formatação | Revisar o escape HTML em `entrega/telegram.py` |
| Telegram 401/403 | Mensagem arquivada, não enviada; status `falhou` | Conferir `TELEGRAM_BOT_TOKEN` e se o bot foi iniciado no chat |
| Índice bíblico ausente no CI | `fiatlux indice baixar-release` | Rodar o workflow `construir-indice.yml` |
| Custo acima do teto mensal | Só fallback (Evangelho + oração) e aviso | Revisar o tamanho dos prompts, o lote de clusters e `custo_max_mensal_usd` |
| Verificação reprovou após 2 revisões | Fallback e aviso com as violações | Ver `mensagens.verificacao_json`; ajustar o prompt P4 ou a regra |
| Sem `FIATLUX_LLM_URL` | Classificação por palavras-chave, consultas determinísticas, seleção pelo escore; sem redação, sai o fallback | Definir `FIATLUX_LLM_URL` e `FIATLUX_LLM_CHAVE` no `.env` (local) ou nos *secrets* (CI) |
| Servidor de LLM recusou a chave, URL errada ou servidor inalcançável | Na primeira falha, parou de chamar o servidor até o fim da execução (`evento=llm_indisponivel`); reservas e fallback, com o motivo no 1º aviso e no alerta | Conferir `<URL>/v1/ready`, a chave e a URL; `fiatlux configurar` confere sem gerar texto |
| Servidor de LLM ocupado (429/503) | Esperou o `Retry-After` (`evento=llm_espera`), até `espera_fila_max_s` somado na execução; depois, como acima | Ver a fila em `/v1/status`; aumentar `espera_fila_max_s` ou mudar o horário do agendamento |
| Resposta fora do formato JSON | Pediu de novo com o erro (`evento=llm_formato`); na 2ª falha, a etapa usa a reserva | Se for frequente, usar um modelo maior (`FIATLUX_LLM_MODELO_GERACAO`) ou aumentar `tentativas_formato` |
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
