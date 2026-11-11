# ADR-012: LLM local por API HTTP, configurado em cada instalação

- **Status:** aceito (2026-11-10). Substitui a parte do Claude no ADR-008; o `LLMClient` como
  Protocol continua.

## Contexto

O dono do projeto decidiu usar o modelo local que já mantém, um servidor de LLM num Mac mini
com API HTTP própria (Ollama por baixo, uma inferência por vez, com fila), e não usar nenhuma
API de LLM de terceiros. Quem clonar o repositório configura o LLM que quiser: URL, chave e
modelos não podem ficar no repositório, que é público.

O servidor expõe `POST /v1/chat` (mensagens, modelo opcional, `temperature`, `max_tokens` até
8192, `allow_fallback`) e `GET /v1/models` (nome, instalado, disponível agora, janela de
contexto). Autentica por `Authorization: Bearer`, responde 429 com `Retry-After` quando a fila
está cheia, 503 quando a máquina está sob pressão e 404 para modelo desconhecido. Não há saída
estruturada nem nível de esforço. Os modelos são pequenos (`qwen3:4b`, `qwen3:8b`), e os que
raciocinam gastam cerca de 1000 tokens antes de responder.

## Decisão

- `ClienteServidor` (`fiat_lux/llm/servidor.py`) fala esse contrato com `httpx`. Sai o SDK
  `anthropic`, com o `ClienteClaude`, os preços por modelo, o fallback server-side e o
  tratamento de recusas (`refusal`).
- **Saída estruturada pelo prompt:** um molde da resposta vai no prompt de sistema, gerado do
  esquema Pydantic (`{"partidario": <true ou false>, "motivos": ["<texto>", …]}`, com os
  valores aceitos de cada enum). Com o JSON Schema cru, o `qwen3:8b` copiava a estrutura e
  devolvia `{"properties": {…}}` (testado em 10/11/2026). A resposta é extraída, tolerando
  raciocínio entre `<think>`, cercas de código e texto em volta, desembrulhada se vier dentro
  de um único campo e validada. Fora do formato, o pedido é refeito com a resposta e o erro
  (`tentativas_formato = 2`).
- **Temperatura por tarefa**, no lugar do esforço do ADR-008: classificação 0,1, consultas 0,3,
  seleção 0,2, redação 0,7, juiz 0. A reprodutibilidade continua vindo do cache por hash.
- **Configuração só no `.env`:** `FIATLUX_LLM_URL`, `FIATLUX_LLM_CHAVE`, `FIATLUX_LLM_MODELO` e
  os específicos por tarefa (`_CLASSIFICACAO`, `_GERACAO`, `_JUIZ`). No CI, ficam em secrets e
  variables. Sem modelo, vale o padrão do servidor. Sem URL, o `--dry-run` usa o cliente
  offline, e a entrega real sai como fallback.
- **Fila e falhas:** 429 e 503 esperam o `Retry-After`, até 15 minutos somados por execução
  (`espera_fila_max_s`). Chave recusada, URL errada, servidor inalcançável depois de três
  tentativas e espera esgotada viram `ErroPermanente`, que fecha o cliente até o fim da
  execução. Um modelo inexistente fecha só aquele modelo. `allow_fallback` fica ligado: sob
  pressão, um modelo mais leve responde em vez de 503.
- **Proxy e vez na fila (adendo de 2026-11-10):** atrás de um proxy que desiste antes do modelo
  terminar (Cloudflare: 524 em 100 a 120 s), o servidor continua gerando a resposta cortada.
  Repetir o pedido só triplicava o trabalho na fila: uma execução com um modelo que raciocina
  chegou a 65 min. Por isso o 504/524 não se repete, e cada pedido espera o servidor ficar livre
  (`GET /v1/status`, opcional no contrato) antes de sair, em vez de esperar na fila dele, onde o
  tempo conta para o limite do proxy. No segundo corte, o modelo fica fora da execução
  (`ErroPermanente` com causa "lento"). As tarefas com reserva sem o LLM têm um orçamento de
  tempo próprio, e uma marca opcional (`FIATLUX_LLM_SEM_RACIOCINIO`) desliga o raciocínio
  nos pedidos (em todas as tarefas, por padrão).
- **Conferência sem inferência:** o `fiatlux configurar` consulta `GET /v1/models` para
  validar a URL, a chave, se os modelos de cada tarefa existem e estão baixados, e a janela de
  contexto (avisa abaixo de 8192 tokens; o maior pedido, o da seleção, tem cerca de 4 mil).

## Consequências

- Custo zero por token. A tabela de preços fica vazia por padrão e só serve a um servidor que
  cobre por uso. O teto mensal continua valendo como proteção.
- Mais lento: o servidor atende um pedido por vez, e a Palavra do Dia faz de 6 a 10 pedidos. Os
  workflows passaram a 45 min (diária) e 60 min (semanal).
- Modelos pequenos erram mais o formato e a verificação V1 a V8. Os portões continuam os mesmos:
  quando o modelo falha, a etapa usa a reserva (palavras-chave, consultas determinísticas,
  seleção pelo escore) ou sai o fallback seguro. A qualidade da redação com o modelo local ainda
  precisa ser avaliada.
- O agendamento no GitHub Actions só funciona se o servidor for alcançável pela internet; os
  runners não enxergam a rede local.
- Sem o SDK `anthropic`, o caminho mais longo da `.venv` caiu de cerca de 165 para 117
  caracteres no modo leve. No completo, o maior é de 150, no torch.
