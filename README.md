# Fiat Lux

> *Dixitque Deus: Fiat lux. Et facta est lux.*
> "E Deus disse: Exista a luz. E a luz existiu." (Gn 1,3, trad. Matos Soares)

Assistente diário e semanal da Palavra de Deus. Segue o calendário litúrgico católico, mede o
"clima" das notícias (mundo, Brasil e Ceará) e propõe a passagem bíblica e o ensinamento mais
adequados ao momento, com **citação fiel e verificável**.

**📖 [Guia do usuário](docs/guia-do-usuario.md)**: instalação, comandos, configuração,
e-mail, agendamento e problemas comuns, passo a passo.

Outros documentos: [plano](plano.md) · [decisões de arquitetura (ADRs)](docs/adr/) ·
[runbook de operação](docs/runbook.md) · [changelog](CHANGELOG.md) ·
[licenças dos dados](LICENSES-DADOS.md)

## Como funciona

1. **Liturgia do dia**: celebração, tempo litúrgico, cor, ciclos e leituras (API + calendário local).
2. **Medidor de notícias**: coleta (GDELT + RSS), deduplica, agrupa por história, classifica
   numa taxonomia pastoral e calcula o **Índice de Tensão** (0 a 100) por escopo.
3. **Busca híbrida (RAG)** no corpus bíblico completo (73 livros no perfil católico, 66 no
   evangélico), ancorada no Evangelho do dia.
4. **Seleção em conjunto fechado**: o LLM (num servidor seu, pela API HTTP; nada vai para APIs
   de terceiros) só escolhe entre candidatos identificados por ID; **o texto bíblico nunca é
   digitado pelo modelo**, ele é inserido a partir da base.
5. **Verificação** (V1 a V8) antes de qualquer entrega; se algo falhar, sai o *fallback* seguro
   (Evangelho do dia + oração fixa).
6. **Entrega** por e-mail e arquivo Markdown em `saidas/` (o Telegram está provisoriamente
   desligado).

## Rodando pela primeira vez

Você vê o Fiat Lux funcionando em cerca de **5 minutos**, sem servidor de LLM e sem e-mail (no
"modo leve"). Os tempos abaixo foram medidos num clone limpo, em 09/11/2026.

### Jeito mais fácil: um comando

Clone o projeto (`git clone https://github.com/Icar0S/Fiat-Lux.git`) e, **dentro da pasta**, rode:

**Windows (PowerShell)**

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; .\configurar.ps1
```

A primeira parte só libera scripts **neste** terminal (o Windows os bloqueia por padrão) e não
muda nada no sistema.

**Linux / macOS**

```bash
bash configurar.sh
```

O script faz só o que ainda falta, então pode ser repetido à vontade:

1. acha o `uv` (inclusive um instalado com `pip` numa pasta fora do PATH) ou instala o oficial, e
   o põe no PATH;
2. instala o Python 3.12 e as dependências (`uv sync`);
3. cria o `.env` e, se você quiser, pergunta o servidor de LLM (URL e chave) e o e-mail que
   envia a mensagem (entra na sua conta e manda um e-mail de teste antes de gravar). O servidor é
   conferido sem gerar texto (`GET /v1/models`): chave recusada, URL errada ou modelo que
   falta aparecem aqui, com o que fazer;
4. monta a base bíblica e o índice de busca;
5. gera a Palavra do Dia de hoje com `--dry-run` (nada é enviado), com um indicador animado da
   etapa e do tempo, e mostra um resumo; o painel final diz se está tudo pronto ou o que falta.

O modo é escolhido sozinho: **completo** se os modelos neurais já estiverem instalados ou
baixados, senão **leve**. Para escolher, use `.\configurar.ps1 -Modo completo` (ou `-Modo leve`);
no Linux/macOS, `bash configurar.sh --completo`. Há também `-SemDemonstracao`, `-SemPerguntas` e
`-ReconstruirIndice` (no `.sh`: `--sem-demonstracao`, `--sem-perguntas`, `--reconstruir-indice`).
Quem já tem o `uv` no PATH pode rodar direto `uv run fiatlux configurar`.

Medido em 09/11/2026: **3 min** num clone novo (modo leve) e **2 min** numa máquina já
configurada no modo completo, em que o script só confere tudo e gera a demonstração.

### Passo a passo manual

O mesmo que o script faz, um comando por vez.

#### 1. Pré-requisitos

- **Git** e conexão com a internet.
- **[uv](https://docs.astral.sh/uv/)**, que instala o Python 3.12 sozinho:
  - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - ou `pip install uv` (se depois o terminal disser que `uv` não é reconhecido, a pasta do pip
    ficou fora do PATH: o `configurar.ps1` resolve isso)
- **Windows:** clone num caminho curto, como `C:\projetos\Fiat-Lux`. No modo completo, numa
  pasta funda, alguns arquivos do torch passam do limite de 260 caracteres do Windows.

#### 2. Instalar

```bash
git clone https://github.com/Icar0S/Fiat-Lux.git
cd Fiat-Lux
uv sync
```

Rode todos os comandos **a partir da pasta do projeto** (é de lá que o `.env` é lido).

#### 3. Montar a base bíblica e o índice (uma vez, cerca de 3 minutos)

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

#### 4. Ver funcionando

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
  aviso: sem FIATLUX_LLM_URL: dry-run com o cliente offline (determinístico)
```

A mensagem também fica salva em `data/cache/dry-run/`. Nada é enviado, e o `--dry-run` pode ser
repetido à vontade.

> Sem servidor de LLM, os textos escritos (reflexão, oração etc.) vêm de um cliente **offline** com
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

#### 5. Com o servidor de LLM

O Fiat Lux fala com um servidor de LLM seu pela API HTTP: `POST /v1/chat` (mensagens, modelo,
temperatura, `max_tokens`) e `GET /v1/models`, com `Authorization: Bearer <chave>`. O contrato
completo está no [guia](docs/guia-do-usuario.md#8-ligando-o-llm); qualquer servidor que o siga
serve. No `.env` (que nunca vai para o git):

```bash
FIATLUX_LLM_URL=https://llm.exemplo.com   # raiz do servidor, sem /v1
FIATLUX_LLM_CHAVE=sk-...                   # vazia se o servidor não pede
FIATLUX_LLM_MODELO=                        # vazio: o padrão do servidor
FIATLUX_LLM_MODELO_GERACAO=                # opcional: outro modelo na seleção e na redação
```

Ou rode `uv run fiatlux configurar`, que pergunta a URL e a chave e confere as duas. Depois,
`uv run fiatlux palavra diaria --dry-run` passa a mostrar `llm: local+cache`. A API não tem
saída estruturada: um molde da resposta vai no prompt, e a resposta é validada (e pedida de
novo, com o erro explicado, quando vem fora do formato). Num servidor local, o custo é zero.

#### 6. Modo completo (qualidade de produção)

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

#### 7. Receber por e-mail e agendar

Configure o e-mail com `.\configurar.ps1 -Email` (ou `uv run fiatlux configurar --email`; no Gmail,
com uma senha de app: [guia, seção 9](docs/guia-do-usuario.md#9-recebendo-por-e-mail)) e rode
**sem** `--dry-run`:

```bash
uv run fiatlux palavra diaria     # arquiva em saidas/AAAA/MM/ e envia por e-mail
```

Cada dia é entregue uma vez por destinatário. Para agendar (GitHub Actions ou na sua máquina),
veja o [guia do usuário](docs/guia-do-usuario.md#10-agendamento).

## Configuração

| Onde | O quê |
|---|---|
| `.env` (nunca versionado) | `FIATLUX_LLM_URL`, `FIATLUX_LLM_CHAVE`, `FIATLUX_LLM_MODELO…`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USUARIO`, `SMTP_SENHA`, `EMAIL_DESTINATARIOS`, `EMAIL_ADMIN`, `FIATLUX_PERFIL` (o Telegram, provisoriamente desligado: `TELEGRAM_*`) |
| `config/settings.toml` | temperatura por tarefa e esperas do LLM, pesos da busca e do medidor, teto de custo |
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
segredos `FIATLUX_LLM_URL`, `FIATLUX_LLM_CHAVE` e os do e-mail (`SMTP_HOST`, `SMTP_PORT`,
`SMTP_USUARIO`, `SMTP_SENHA`, `EMAIL_DESTINATARIOS`; o servidor de LLM precisa ser alcançável
pela internet), crie a
branch órfã `estado`, rode `construir-indice.yml` uma vez e fixe as actions por SHA (hoje estão
por tag). O passo a passo está no
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
- A qualidade da redação com o LLM local ainda não foi avaliada: todos os testes de ponta a
  ponta usaram o cliente offline. Modelos pequenos erram mais o formato JSON e a verificação
  (V1 a V8); quando isso acontece, a etapa usa a reserva ou sai o fallback.
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
| `src/fiat_lux/llm` | `LLMClient` (Protocol), cliente do servidor de LLM (HTTP), cliente offline, cache, prompts versionados |
| `src/fiat_lux/agente` | contexto do dia, consultas, seleção, redação, verificação, fallback, semanal |
| `src/fiat_lux/entrega` | templates, Markdown, e-mail, Telegram |
| `src/fiat_lux/orquestracao` | pipelines diário e semanal |
| `src/fiat_lux/instalacao.py` | regras do `fiatlux configurar`: o que já existe, o que falta, edição do `.env` |
| `configurar.ps1`, `configurar.sh` | configuração em um comando (Windows / Linux e macOS) |
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
