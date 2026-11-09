# Fiat Lux

> *Dixitque Deus: Fiat lux. Et facta est lux.*
> "E Deus disse: Exista a luz. E a luz existiu." (Gn 1,3, trad. Matos Soares)

Assistente diário e semanal da Palavra de Deus. Segue o calendário litúrgico católico, mede o
"clima" das notícias (mundo, Brasil e Ceará) e propõe a passagem bíblica e o ensinamento mais
adequados ao momento, com **citação fiel e verificável**.

**📖 [Guia do usuário](docs/guia-do-usuario.md)**: instalação, comandos, configuração,
Telegram, agendamento e problemas comuns, passo a passo.

Outros documentos: [plano](plano.md) · [decisões de arquitetura (ADRs)](docs/adr/) ·
[runbook de operação](docs/runbook.md) · [changelog](CHANGELOG.md) ·
[licenças dos dados](LICENSES-DADOS.md)

## Como funciona

1. **Liturgia do dia**: celebração, tempo litúrgico, cor, ciclos e leituras (API + calendário local).
2. **Medidor de notícias**: coleta (GDELT + RSS), deduplica, agrupa por história, classifica
   numa taxonomia pastoral e calcula o **Índice de Tensão** (0 a 100) por escopo.
3. **Busca híbrida (RAG)** no corpus bíblico completo (73 livros no perfil católico, 66 no
   evangélico), ancorada no Evangelho do dia.
4. **Seleção em conjunto fechado**: o LLM só escolhe entre candidatos identificados por ID;
   **o texto bíblico nunca é digitado pelo modelo**, ele é inserido a partir da base.
5. **Verificação** (V1 a V8) antes de qualquer entrega; se algo falhar, sai o *fallback* seguro
   (Evangelho do dia + oração fixa).
6. **Entrega** por Telegram e arquivo Markdown em `saidas/`.

## Rodando pela primeira vez

Você vê o Fiat Lux funcionando em cerca de **5 minutos**, sem chave de API e sem Telegram (no
"modo leve"). Os tempos abaixo foram medidos num clone limpo, em 09/11/2026.

### 1. Pré-requisitos

- **Git** e conexão com a internet.
- **[uv](https://docs.astral.sh/uv/)**, que instala o Python 3.12 sozinho:
  - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - ou `pip install uv`
- **Windows:** clone num caminho curto, como `C:\projetos\Fiat-Lux`. Numa pasta muito funda,
  alguns arquivos do SDK da Anthropic passam do limite de 260 caracteres do Windows.

### 2. Instalar

```bash
git clone https://github.com/Icar0S/Fiat-Lux.git
cd Fiat-Lux
uv sync
```

Rode todos os comandos **a partir da pasta do projeto** (é de lá que o `.env` é lido).

### 3. Montar a base bíblica e o índice (uma vez, cerca de 3 minutos)

```bash
uv run fiatlux biblia baixar      # 149 arquivos fixados por commit + SHA-256 (~45 s)
uv run fiatlux biblia ingerir     # limpeza, versificação e lacunas (~30 s)
uv run fiatlux biblia validar     # 28 checagens; termina com "ok: 28 checagens"
uv run fiatlux indice construir   # 16.703 perícopes + índice de busca (~80 s)
```

O `ingerir` termina com:

```
ok: MS 35728 versículos, BLIVRE 31101; versificação ≥0,8: 99.94%; lacunas 165 (0 abertas); checagens 28/28
```

### 4. Ver funcionando

```bash
uv run fiatlux palavra diaria --dry-run
```

Em cerca de 1 minuto, o Fiat Lux busca a liturgia de hoje, coleta algumas centenas de manchetes,
calcula o Índice de Tensão, busca as passagens, escolhe, redige, **verifica** e imprime a
mensagem completa. O final da saída é assim:

```
status: rascunho · llm: offline · custo: US$ 0.0000 · arquivo: …\data\cache\dry-run\2026-11-09-diaria-catolico.md
  ✅ V1
  …
  ✅ V8
  aviso: sem ANTHROPIC_API_KEY: dry-run com o cliente offline (determinístico)
```

A mensagem também fica salva em `data/cache/dry-run/`. Nada é enviado, e o `--dry-run` pode ser
repetido à vontade.

> Sem chave de API, os textos escritos (reflexão, oração etc.) vêm de um cliente **offline** com
> modelos fixos: servem para ver o pipeline, não a qualidade final. A liturgia, o medidor, a
> busca e as citações bíblicas são reais.

Experimente também:

```bash
uv run fiatlux palavra diaria --dry-run --data 2026-12-25     # outro dia
uv run fiatlux palavra diaria --dry-run --perfil evangelico   # Bíblia Livre, 66 livros
uv run fiatlux palavra semanal --dry-run                      # Palavra da Semana, com gráfico
uv run fiatlux biblia passagem "Jo 3,16-17"                   # consulta à base
uv run fiatlux buscar "Deus consola os aflitos"               # depuração da busca
uv run fiatlux noticias coletar                               # só o medidor de notícias
uv run fiatlux estado execucoes                               # histórico: status, duração, custo
```

### 5. Com os textos do Claude

```bash
cp .env.example .env              # PowerShell: Copy-Item .env.example .env
```

Preencha `ANTHROPIC_API_KEY=` no `.env` e rode de novo `uv run fiatlux palavra diaria --dry-run`.
O resumo passa a mostrar `llm: anthropic+cache` e o custo. O Haiku 5.5 classifica as notícias e
o Sonnet 5.5 escolhe, redige e julga. A estimativa do plano é de poucos centavos de dólar por
dia, com teto mensal de US$ 10 (`FIATLUX_CUSTO_MAX_MENSAL_USD`).

### 6. Modo completo (qualidade de produção)

```bash
uv sync --extra ml
uv run fiatlux indice construir --modelo intfloat/multilingual-e5-base
```

Instala `torch` e `sentence-transformers` e baixa os modelos `multilingual-e5-base` (~1,1 GB,
agora) e `bge-reranker-v2-m3` (~2,3 GB, na primeira Palavra do Dia). O índice neural leva cerca
de **40 minutos em CPU**, uma vez só (no GitHub Actions, o `construir-indice.yml` publica o índice
pronto como Release). Neste modo, a busca é mais precisa (tabela em [Avaliação](#avaliação)), e
cada Palavra do Dia leva cerca de **3 minutos em CPU**, por causa do rerank neural. Use
`--sem-rerank` para testar mais rápido.

### 7. Receber no Telegram e agendar

Crie um bot com o [@BotFather](https://t.me/BotFather), preencha `TELEGRAM_BOT_TOKEN` e
`TELEGRAM_CHAT_IDS` no `.env` e rode **sem** `--dry-run`:

```bash
uv run fiatlux palavra diaria     # arquiva em saidas/AAAA/MM/ e envia pelo Telegram
```

Cada dia é entregue uma vez por destinatário. Para agendar (GitHub Actions ou na sua máquina),
veja o [guia do usuário](docs/guia-do-usuario.md#10-agendamento).

## Configuração

| Onde | O quê |
|---|---|
| `.env` (nunca versionado) | `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS` (allowlist), `TELEGRAM_ADMIN_CHAT_ID`, `FIATLUX_PERFIL`, `FIATLUX_CUSTO_MAX_MENSAL_USD` |
| `config/settings.toml` | modelos e esforço por tarefa, pesos da busca e do medidor, preços e teto de custo |
| `config/fontes_noticias.yaml` | consultas GDELT e feeds RSS por escopo (região inclusa) |
| `config/taxonomia_pastoral.yaml` | categorias pastorais, palavras-chave e passagens-semente |
| `config/perfis.yaml` | `catolico` (Matos Soares, 73 livros), `evangelico` (BLIVRE, 66), `ecumenico` |
| `config/neutralidade.yaml` | partidos, termos e nomes vigiados (V5); expressões proibidas (V6) |
| `config/correcoes_ms.tsv` | correções manuais do texto da Matos Soares, com justificativa |

Detalhes de cada variável e arquivo no [guia](docs/guia-do-usuario.md#7-configuração).

## Operação no GitHub Actions

| Workflow | Quando | O que faz |
|---|---|---|
| `ci.yml` | push na `main` e PRs | ruff, mypy, testes, corpus, índice lexical e suíte rápida de avaliação |
| `diaria.yml` | 05:00 (Fortaleza) | Palavra do Dia + feedback; commita o estado na branch `estado` e a mensagem em `saidas/` |
| `semanal.yml` | sábado, 17:00 | Palavra da Semana (gráfico, plano de leitura, perguntas) |
| `construir-indice.yml` | manual | reconstrói `biblia.sqlite` e publica como Release `indice-latest` |

Para colocar no ar: mantenha o repositório **privado** (ver [Licenças](#licenças)), crie os
segredos `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS` e
`TELEGRAM_ADMIN_CHAT_ID`, crie a branch órfã `estado`, rode `construir-indice.yml` uma vez e fixe
as actions por SHA (hoje estão por tag). O passo a passo está no
[guia](docs/guia-do-usuario.md#github-actions-padrão).

## Avaliação

```bash
uv run pytest                                # testes (os de integração exigem a base do passo 3)
uv run fiatlux eval rodar --suite rapida     # ou --suite completa; relatórios em eval/relatorios/
```

Resultado em 09/11/2026 (embeddings `multilingual-e5-base`, LLM offline):

| Componente | Métrica | Resultado | Meta do plano |
|---|---|---|---|
| Parser de referências | acurácia em 1.560 referências reais (2026–2027) | **100%** | 100% |
| Versificação | protocanônicos da MS com confiança ≥ 0,8 | **99,94%** | ≥ 99% |
| Recuperação (católico, rerank lexical → neural) | acerto@10 · recall@10 · nDCG@10 · MRR | 0,85 → **0,90** · 0,29 → 0,33 · 0,35 → 0,42 · 0,68 → **0,81** | recall@10 ≥ 0,80; nDCG@10 ≥ 0,60 |
| Recuperação (evangélico, rerank lexical → neural) | acerto@10 · recall@10 · nDCG@10 · MRR | 0,975 → **0,975** · 0,34 → 0,36 · 0,42 → 0,46 · 0,80 → **0,85** | idem |
| Adversariais | casos aprovados | **15/15** | 100% |
| Metamórficos | MR1, MR3, MR4, MR6 | **todos passam** | — |
| E2E (30 dias congelados) | citações inválidas · taxa de fallback | **0 · 0%** | 0 · < 5% |

*acerto@10* é a fração de consultas com ao menos uma passagem aceitável entre as 10 primeiras;
*recall@10* é a fração de **todas** as passagens aceitáveis encontradas. O golden de recuperação
(v0, 40 casos) ainda precisa de revisão por um segundo leitor. O cross-encoder custa cerca de
0,4 s por par em CPU (detalhes no [ADR-010](docs/adr/010-multilingual-e5-base.md)).

## Limitações conhecidas

- O GDELT respondeu 429 a todas as requisições a partir do IP de desenvolvimento; o RSS cobre os
  três escopos, e o medidor fica sem o componente de tom (usa volume e gravidade).
- A recuperação ainda está abaixo das metas de recall e nDCG do plano (tabela acima).
- A qualidade da redação com o Claude ainda não foi avaliada: todos os testes de ponta a ponta
  usaram o cliente offline.
- Itens que dependem de pessoas: anotação de 200 pares de duplicatas e 200 clusters, calibração
  do juiz com 2 avaliadores, 30 dias de percepção registrada (`fiatlux estado percepcao`) para
  calibrar o Índice de Tensão, revisão teológica amostral mensal.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `src/fiat_lux/biblia` | catálogo de 73 livros (USFM), ingestão, limpeza, versificação, referências, exportação MD |
| `src/fiat_lux/liturgia` | cliente da API, calendário litúrgico local, serviço com cache e fallback |
| `src/fiat_lux/noticias` | GDELT, RSS, normalização, dedup, clusterização, classificação e medidor |
| `src/fiat_lux/rag` | perícopes, embeddings, índice FTS5 + vetores, busca híbrida, rerank, boosts, recorte |
| `src/fiat_lux/llm` | `LLMClient` (Protocol), cliente Claude, cliente offline, cache, prompts versionados |
| `src/fiat_lux/agente` | contexto do dia, consultas, seleção, redação, verificação, fallback, semanal |
| `src/fiat_lux/entrega` | templates, Markdown, Telegram, e-mail |
| `src/fiat_lux/orquestracao` | pipelines diário e semanal |
| `config/` | parâmetros, fontes de notícias, taxonomia pastoral, perfis, tempos litúrgicos |
| `eval/` | conjuntos de referência (golden) e relatórios |
| `docs/` | guia do usuário, ADRs, relatório de qualidade do corpus, runbook |

## Licenças

Código sob MIT ([LICENSE](LICENSE)). Cada fonte de dados tem licença e atribuição próprias:
veja [LICENSES-DADOS.md](LICENSES-DADOS.md). O status de domínio público da tradução
Matos Soares ainda não foi confirmado (plano §13.3), por isso o repositório deve permanecer
**privado** até essa confirmação.

O tom de notícias do GDELT é uma medida automática (léxico e tradução de máquina): o Índice de
Tensão é um **sinal**, não uma verdade.
