# Guia do usuário — Fiat Lux

Este guia mostra como instalar, rodar e operar o Fiat Lux no dia a dia. O caminho mínimo para
vê-lo funcionando também está no [README](../README.md#rodando-pela-primeira-vez); aqui cada
passo vem explicado, com a saída esperada, as opções e o que fazer quando algo dá errado.

O jeito mais rápido de começar é o **script de configuração**
([seção 2](#2-instalação)): um comando instala tudo, aproveitando o que já existe, e mostra o
Fiat Lux funcionando.

**Sumário**

1. [O que o Fiat Lux entrega](#1-o-que-o-fiat-lux-entrega)
2. [Instalação](#2-instalação)
3. [Primeira execução, passo a passo](#3-primeira-execução-passo-a-passo)
4. [Entendendo a mensagem](#4-entendendo-a-mensagem)
5. [Referência de comandos](#5-referência-de-comandos)
6. [Perfis: católico, evangélico, ecumênico](#6-perfis-católico-evangélico-ecumênico)
7. [Configuração](#7-configuração)
8. [Ligando o LLM](#8-ligando-o-llm)
9. [Recebendo no Telegram](#9-recebendo-no-telegram)
10. [Agendamento](#10-agendamento)
11. [Acompanhamento e calibração](#11-acompanhamento-e-calibração)
12. [Privacidade](#12-privacidade)
13. [Problemas comuns](#13-problemas-comuns)

---

## 1. O que o Fiat Lux entrega

Todo dia, às 05:00 (fuso de Fortaleza), o Fiat Lux:

1. lê a **liturgia do dia** (celebração, tempo litúrgico, cor, ciclos e leituras);
2. coleta as **manchetes** do mundo, do Brasil e do Ceará, agrupa por história, classifica cada
   grupo numa taxonomia pastoral e calcula o **Índice de Tensão** (0 a 100) de cada escopo;
3. **busca na Bíblia** (73 livros no perfil católico, 66 no evangélico) passagens ligadas ao
   Evangelho do dia, ao tempo litúrgico e aos temas das notícias;
4. pede a um **modelo de linguagem** (no seu servidor de LLM, [seção 8](#8-ligando-o-llm))
   que escolha, entre esses candidatos, a passagem principal e duas complementares, e que
   escreva a reflexão, o ensinamento, um gesto concreto e uma oração;
5. **verifica** tudo (citações, neutralidade, sensibilidade, tamanho) antes de entregar;
6. entrega no **Telegram** e arquiva em Markdown em `saidas/`.

Aos sábados, às 17:00, sai a **Palavra da Semana**: tendência do medidor em 7 dias (com
gráfico), temas que voltaram, Evangelho do domingo, uma passagem para a semana, um plano de
leitura de 7 dias e perguntas para partilha em família ou grupo.

O princípio mais importante: **o modelo nunca digita o texto bíblico**. Ele só escolhe entre
candidatos identificados por ID, e o texto é inserido a partir da base. Se a verificação
reprovar duas vezes, sai um *fallback* seguro (Evangelho do dia + oração fixa), nunca um texto
não verificado.

## 2. Instalação

### Requisitos

| Item | Modo leve | Modo completo |
|---|---|---|
| Sistema | Windows, macOS ou Linux | idem |
| [uv](https://docs.astral.sh/uv/) | obrigatório (instala o Python 3.12 sozinho) | idem |
| Git | para clonar | idem |
| Internet | download das fontes, liturgia, notícias | + modelos do Hugging Face (~3,4 GB) |
| Disco | ~1 GB | ~6 GB |
| Busca | TF-IDF + LSA (lexical) | `multilingual-e5-base` + `bge-reranker-v2-m3` |

> **Windows:** clone o projeto num caminho curto, como `C:\projetos\Fiat-Lux`. No modo
> completo, alguns arquivos do torch têm caminhos longos que, numa pasta funda (mais de ~105
> caracteres), passam do limite de 260 caracteres do Windows. A alternativa é
> [habilitar caminhos longos](https://learn.microsoft.com/windows/win32/fileio/maximum-file-path-limitation).
> O script de configuração avisa quando o caminho está longo demais.

### Configuração automática (recomendado)

Clone o projeto (`git clone https://github.com/Icar0S/Fiat-Lux.git`) e, na pasta dele, rode:

```powershell
# Windows (PowerShell)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; .\configurar.ps1
```

```bash
# Linux / macOS
bash configurar.sh
```

O `Set-ExecutionPolicy -Scope Process` libera scripts só no terminal aberto (o Windows os
bloqueia por padrão) e não muda nada no sistema. O script faz só o que ainda falta:

| Etapa | O que faz | Se já existe |
|---|---|---|
| uv | procura no PATH e onde os instaladores costumam deixá-lo (instalador oficial, winget, scoop, chocolatey, `pip`/`pipx` de qualquer Python, conda); se não achar, instala o oficial. Põe a pasta dele no PATH do usuário | só confere |
| Dependências | `uv sync` (o uv instala o Python 3.12 se faltar); no modo completo, com o extra `ml` | só confere (menos de 1 s) |
| `.env` | cria a partir do `.env.example` | mantém como está |
| Servidor de LLM e Telegram (opcional) | pergunta a URL e a chave do servidor de LLM (a chave não aparece na tela) e **confere os dois** com `GET /v1/models`, sem gerar texto ([seção 8](#8-ligando-o-llm)); oferece configurar o Telegram ([seção 9](#9-recebendo-no-telegram)) | não pergunta de novo, mas confere o servidor outra vez |
| Base bíblica | baixa as fontes, confere o SHA-256, ingere e valida (28 checagens) | só valida |
| Índice de busca | constrói o índice do modo escolhido (lexical ou neural) | só confere |
| Demonstração | `palavra diaria --dry-run` de hoje, com a verificação V1 a V8; nada é enviado. Com o servidor respondendo, os textos são do LLM; sem servidor, ou se a conferência falhou (chave recusada, URL errada), saem do cliente offline, com textos de exemplo | gera de novo |

No fim, um resumo mostra a situação de cada item. Exemplo de um clone novo, sem servidor de LLM:

```
│ Modo            │ leve            │ busca lexical; para o completo, rode o script com -Modo completo (--completo)                    │
│ .env            │ criado          │ a partir do .env.example                                                                         │
│ LLM             │ sem servidor    │ sem ele, a Palavra do Dia de verdade sai só com o Evangelho do dia e uma oração fixa             │
│ Telegram        │ não configurado │ a mensagem fica em saidas/ (guia, seção 9)                                                       │
│ Base bíblica    │ montada         │ 28 checagens ok                                                                                  │
│ Índice de busca │ construído      │ lexical:lsa256, 16703 perícopes                                                                  │
│ Demonstração    │ ok              │ verificação 8/8 · textos de exemplo (offline) · data\cache\dry-run\2026-11-10-diaria-catolico.md │
```

Depois da tabela vem o que ainda falta para a Palavra do Dia sair completa (no exemplo, o
servidor de LLM; com a chave recusada, conferir a chave), com o que fazer. A última linha é o
veredito: `Tudo pronto.` só aparece quando nada falta.

**Modo.** Sem opção, o script usa o **completo** se os modelos neurais já estiverem instalados
na `.venv` ou baixados em `.cache/huggingface`, e o **leve** nos outros casos. Para escolher:

| PowerShell | bash | Efeito |
|---|---|---|
| `-Modo leve` / `-Modo completo` | `--leve` / `--completo` | escolhe o modo (o leve numa `.venv` completa tira o torch e troca o índice neural pelo lexical) |
| `-SemDemonstracao` | `--sem-demonstracao` | não gera a Palavra do Dia de teste |
| `-SemPerguntas` | `--sem-perguntas` | não pergunta o servidor de LLM nem o Telegram (sem terminal interativo, já não pergunta) |
| `-ReconstruirIndice` | `--reconstruir-indice` | refaz o índice mesmo que o atual sirva |

Tempos medidos em 09 e 10/11/2026 (Windows 11, CPU): clone novo no modo leve, **3 min**; máquina
já configurada no modo completo, **2 a 3 min** (só confere e gera a demonstração, com rerank
neural). O modo completo do zero leva bem mais: baixa o torch e os modelos (~3,4 GB) e constrói
o índice neural, cerca de 40 minutos em CPU.

Depois do script, o comando `uv` funciona no terminal em que ele rodou e nos próximos. **No VS
Code**, os terminais novos só enxergam o PATH novo depois que você fecha e abre o VS Code.

Se algo der errado, o script para com uma mensagem dizendo o que fazer. Corrija e rode de novo:
ele continua de onde parou. Os problemas mais comuns estão na
[seção 13](#13-problemas-comuns). Com o `uv` já no PATH, a parte do projeto também roda sozinha:
`uv run fiatlux configurar`.

### Instalação manual

Instale o uv:

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Também funciona `pip install uv`, mas a pasta em que o pip o instala pode ficar fora do PATH
(veja a [seção 13](#13-problemas-comuns)).

Clone e instale as dependências:

```bash
git clone https://github.com/Icar0S/Fiat-Lux.git
cd Fiat-Lux
uv sync               # modo leve
uv sync --extra ml    # modo completo (inclui torch e sentence-transformers)
```

Rode todos os comandos **a partir da pasta do projeto**: é de lá que o `.env` é lido. Depois,
siga a [seção 3](#3-primeira-execução-passo-a-passo).

## 3. Primeira execução, passo a passo

Se você usou o script de configuração, os passos 3.1 a 3.3 já foram feitos; esta seção explica
cada um e serve para fazê-los à mão. Os tempos abaixo foram medidos num clone limpo, em
09/11/2026, numa máquina com Windows 11.

### 3.1 Montar a base bíblica (uma vez)

```bash
uv run fiatlux biblia baixar
```

Baixa 149 arquivos (Matos Soares, Bíblia Livre, referências cruzadas e tabelas de
versificação) de commits fixos e confere o SHA-256 de cada um contra `fontes.lock.json`.
Leva cerca de 45 s. Se um arquivo vier diferente, o comando falha: as fontes nunca mudam em
silêncio.

```bash
uv run fiatlux biblia ingerir
```

Limpa o texto, separa os títulos dos salmos, resolve duplicados, alinha a versificação da
Matos Soares (Vulgata) com a numeração canônica e grava `data/processed/biblia.sqlite`. Leva
cerca de 30 s e termina assim:

```
ok: MS 35728 versículos, BLIVRE 31101; versificação ≥0,8: 99.94%; lacunas 165 (0 abertas); checagens 28/28
```

```bash
uv run fiatlux biblia validar
```

Repete as 28 checagens (contagens, âncoras de texto e de versificação) e termina com
`ok: 28 checagens`. Se alguma falhar, o código de saída é 1.

Opcional: `uv run fiatlux biblia exportar-md` gera um Markdown por capítulo em
`data/markdown/` (2.523 arquivos, compatíveis com o Obsidian).

### 3.2 Construir o índice de busca

```bash
uv run fiatlux indice construir
```

Divide a Bíblia em 16.703 perícopes e cria o índice de texto (FTS5) e o de vetores. No modo
leve (embedder lexical), leva cerca de 80 s. No modo completo:

```bash
uv run fiatlux indice construir --modelo intfloat/multilingual-e5-base
```

Na primeira vez, baixa o modelo (~1,1 GB) e calcula os vetores de todas as perícopes: cerca de
40 minutos em CPU. É feito uma vez só. No GitHub Actions, o workflow `construir-indice` publica o
índice pronto como Release, e as execuções diárias só o baixam.

### 3.3 Gerar a Palavra do Dia sem enviar nada

```bash
uv run fiatlux palavra diaria --dry-run
```

O `--dry-run` faz o pipeline inteiro, mas **não envia nem arquiva** em `saidas/` e não conta
para a idempotência. Pode ser repetido à vontade. Em cerca de 1 minuto (modo leve) você vê:

1. linhas de log com o andamento, por exemplo `noticias artigos={...} clusters=193 composto=45.0`;
2. a **mensagem completa** em Markdown;
3. o resumo final:

```
status: rascunho · llm: offline · custo: US$ 0.0000 · arquivo: …\data\cache\dry-run\2026-11-09-diaria-catolico.md
  ✅ V1
  ✅ V2
  …
  ✅ V8
  aviso: sem FIATLUX_LLM_URL: dry-run com o cliente offline (determinístico)
```

A mensagem também fica salva em `data/cache/dry-run/AAAA-MM-DD-diaria-<perfil>.md`; abra no
editor ou num visualizador de Markdown.

> **Sem servidor de LLM**, os textos escritos (olhar sobre o dia, reflexão, ensinamento, gesto e
> oração) vêm de um cliente **offline** com modelos fixos. Servem para ver o pipeline
> funcionando, não a qualidade final. A liturgia, o medidor, a busca e as citações bíblicas são
> reais. Para ter os textos de verdade, veja a [seção 8](#8-ligando-o-llm).

Experimente também:

```bash
uv run fiatlux palavra diaria --dry-run --data 2026-12-25      # outro dia (a liturgia é buscada na API)
uv run fiatlux palavra diaria --dry-run --perfil evangelico    # Bíblia Livre, 66 livros
uv run fiatlux palavra diaria --dry-run --sem-noticias         # sem coletar notícias (mais rápido)
uv run fiatlux palavra semanal --dry-run                       # Palavra da Semana (gráfico incluso)
```

### 3.4 Gerar "de verdade"

Sem `--dry-run`, a mensagem é arquivada em `saidas/AAAA/MM/AAAA-MM-DD.md` (a semanal, em
`saidas/AAAA/semanas/AAAA-Wnn.md`), registrada no banco de estado (`data/estado/estado.sqlite`)
e, se o Telegram estiver configurado, enviada:

```bash
uv run fiatlux palavra diaria               # arquiva e envia
uv run fiatlux palavra diaria --sem-envio   # arquiva, mas não envia pelo Telegram
```

Cada dia é entregue **uma vez** por destinatário (idempotência). Se rodar de novo, aparece
`já enviada para este destinatário; nada a fazer`.

## 4. Entendendo a mensagem

| Seção | O que é |
|---|---|
| Cabeçalho | data, celebração, tempo litúrgico, semana, cor e ciclos (dominical A/B/C e ferial I/II) |
| **Como está o mundo hoje** | o Índice de Tensão de cada escopo, um parágrafo sobre o dia e 2 ou 3 links das fontes |
| **Evangelho do dia** | referência e texto do lecionário (API Liturgia Diária), com números de versículo sobrescritos |
| **A Palavra para hoje** | a passagem principal escolhida (1 a 5 versículos, texto da base), seguida da reflexão |
| **Ensinamento** e **Gesto de hoje** | uma ideia para guardar e uma ação viável em 24 horas |
| **Oração** | oração curta ligada ao dia |
| **Para aprofundar** | duas passagens complementares, de preferência uma de cada testamento |
| Rodapé | atribuições obrigatórias (tradução, liturgia, notícias) e versão do pipeline |

O **Índice de Tensão** combina o tom das notícias (quando o GDELT responde), o volume em relação
aos últimos 30 dias e a gravidade dos temas principais:

| Faixa | Índice |
|---|---|
| calmo | 0 a 29 |
| atenção | 30 a 54 |
| tensão | 55 a 74 |
| crise | 75 a 100 |

Enquanto não houver 30 dias de histórico, aparece *medidor em calibração*. O índice é um
**sinal automático, não uma verdade**: a mensagem nunca lê notícias como profecia nem atribui
tragédias a castigo divino (as diretrizes completas estão no [plano, §10](../plano.md)).

## 5. Referência de comandos

Todos começam com `uv run fiatlux`. Use `--help` em qualquer nível. As opções globais são
`-v` (log detalhado) e `--json-logs` (log em JSON, útil no CI).

| Comando | O que faz | Opções úteis |
|---|---|---|
| `configurar` | prepara o que falta (`.env`, chaves, base bíblica, índice) e gera uma Palavra do Dia de teste; pode ser repetido | `--sem-demonstracao`, `--sem-perguntas`, `--reconstruir-indice` |
| `palavra diaria` | gera (e entrega) a Palavra do Dia | `--data AAAA-MM-DD`, `--perfil`, `--dry-run`, `--sem-envio`, `--sem-noticias`, `--sem-gdelt`, `--sem-rerank`, `--llm offline`, `--quieto` |
| `palavra semanal` | gera (e entrega) a Palavra da Semana | `--semana AAAA-Wnn`, `--perfil`, `--dry-run`, `--sem-envio`, `--sem-rerank` |
| `biblia baixar` / `ingerir` / `validar` | monta e confere a base bíblica | — |
| `biblia passagem "Jo 3,16-17"` | mostra uma passagem da base | — |
| `biblia relatorio` / `exportar-md` | relatório de qualidade / Markdown por capítulo | — |
| `indice construir` | perícopes, FTS5 e vetores | `--modelo`, `--embedder auto\|neural\|lexical` |
| `indice baixar-release` | baixa o índice publicado como Release (CI; usa `gh`) | — |
| `buscar "consulta"` | depura a busca | `--perfil`, `--k`, `--tempo`, `--rerank` |
| `liturgia hoje` / `dia AAAA-MM-DD` | liturgia de um dia | — |
| `liturgia prefetch` | guarda os próximos dias no cache | `--dias 1..7` |
| `liturgia canario` | teste de contrato contra a API real | — |
| `noticias coletar` | coleta, agrupa, classifica e mede | `--data`, `--sem-gdelt`, `--sem-llm`, `--llm` |
| `noticias medir` | recalcula com as notícias já coletadas (sem rede) | `--data`, `--com-llm` |
| `estado execucoes` / `mensagens` | histórico de execuções e mensagens | `--ultimos N` |
| `estado feedback` | lê as respostas 👍/👎 no Telegram | — |
| `estado percepcao DATA NOTA` | registra o quanto o dia "pesou" (0 a 100) | `--comentario` |
| `estado apagar-destinatario ID --sim` | remove mensagens e feedback de alguém (LGPD) | — |
| `estado commitar` | no CI: commita o estado e `saidas/` | `--mensagem` |
| `eval rodar` | suíte de avaliação | `--suite rapida\|completa` |

Atalhos no [justfile](../justfile), que carrega o `.env` automaticamente: `uv run just setup`,
`uv run just test`, `uv run just eval`, `uv run just diaria --dry-run`.

## 6. Perfis: católico, evangélico, ecumênico

| Perfil | Tradução | Livros | Deuterocanônicos |
|---|---|---|---|
| `catolico` (padrão) | Matos Soares (1956) | 73 | normais |
| `evangelico` | Bíblia Livre (BLIVRE) | 66 | excluídos; o Evangelho aparece como "Leitura do lecionário" |
| `ecumenico` | BLIVRE + Matos Soares nos deuterocanônicos | 73 | permitidos, com rótulo "livro deuterocanônico, aceito pela tradição católica" |

Escolha por execução (`--perfil evangelico`) ou como padrão no `.env` (`FIATLUX_PERFIL=evangelico`).
Os perfis estão em `config/perfis.yaml`.

## 7. Configuração

### `.env` (criado pelo `configurar` a partir do `.env.example`; nunca vai para o git)

| Variável | Para quê |
|---|---|
| `FIATLUX_LLM_URL` | raiz do servidor de LLM, sem `/v1` ([seção 8](#8-ligando-o-llm)) |
| `FIATLUX_LLM_CHAVE` | chave do servidor (vai como `Authorization: Bearer`); vazia se ele não pede |
| `FIATLUX_LLM_MODELO` | modelo de todas as tarefas (vazio: o padrão do servidor) |
| `FIATLUX_LLM_MODELO_GERACAO`, `…_CLASSIFICACAO`, `…_JUIZ` | modelo de uma tarefa (seleção e redação; notícias, consultas e resumo; juiz de neutralidade) |
| `TELEGRAM_BOT_TOKEN` | token do bot ([seção 9](#9-recebendo-no-telegram)) |
| `TELEGRAM_CHAT_IDS` | quem recebe (lista separada por vírgula; também é a allowlist) |
| `TELEGRAM_ADMIN_CHAT_ID` | quem recebe alertas de falha e fallback |
| `FIATLUX_PERFIL` | perfil padrão (`catolico`, `evangelico`, `ecumenico`) |
| `FIATLUX_TZ` | fuso (padrão `America/Fortaleza`) |
| `FIATLUX_CUSTO_MAX_MENSAL_USD` | teto de gasto por mês (padrão 10), para um servidor que cobre por uso; num servidor local o custo é zero |
| `FIATLUX_ESTADO` | caminho do banco de estado |
| `SMTP_*`, `EMAIL_DESTINATARIOS` | entrega opcional por e-mail |

`HF_HOME` (pasta dos modelos do Hugging Face) é lido pelo próprio Hugging Face: defina no
ambiente ou use os atalhos do `just`, que carregam o `.env`.

### Arquivos em `config/`

| Arquivo | O que ajustar |
|---|---|
| `settings.toml` | temperatura por tarefa e esperas do LLM, pesos da busca, limiares do medidor e das notícias, teto de custo |
| `fontes_noticias.yaml` | consultas do GDELT e feeds RSS por escopo (troque o Ceará pela sua região aqui e em `settings.toml`, `[geral] regiao`) |
| `taxonomia_pastoral.yaml` | categorias pastorais, palavras-chave e passagens-semente |
| `neutralidade.yaml` | partidos, termos e nomes vigiados; expressões proibidas (revise em anos eleitorais) |
| `perfis.yaml` | tradução, cânon e rótulos de cada perfil |
| `tempos_liturgicos.yaml` | descritores de cada tempo litúrgico, usados na busca |
| `correcoes_ms.tsv` | correções manuais do texto da Matos Soares, cada uma com justificativa |

## 8. Ligando o LLM

A classificação das notícias, a escolha das passagens e os textos (olhar sobre o dia, reflexão,
ensinamento, gesto e oração) vêm de um **modelo de linguagem num servidor seu**, pela API HTTP
descrita abaixo. Nada vai para APIs de LLM de terceiros: cada instalação aponta para o servidor
que quiser, e essa configuração fica só no `.env`.

1. Tenha um servidor que siga o contrato abaixo e, se ele pedir, uma chave dele.
2. Rode `uv run fiatlux configurar` e informe a URL e a chave quando ele pedir (a chave não
   aparece na tela). Ele grava as duas no `.env`, consulta `GET /v1/models` (sem gerar texto)
   para conferir a chave e os modelos e gera uma Palavra do Dia de teste com o LLM. Se o
   servidor recusar a chave ou a URL estiver errada, ele explica e deixa corrigir na hora.

   À mão, no `.env`:

   ```bash
   FIATLUX_LLM_URL=https://llm.exemplo.com   # raiz do servidor, sem /v1
   FIATLUX_LLM_CHAVE=sk-...                   # vai como Authorization: Bearer <chave>
   FIATLUX_LLM_MODELO=                        # vazio: o padrão do servidor
   FIATLUX_LLM_MODELO_GERACAO=                # opcional: outro modelo na seleção e na redação
   ```

   Também existem `FIATLUX_LLM_MODELO_CLASSIFICACAO` (notícias, consultas e resumo do
   Evangelho) e `FIATLUX_LLM_MODELO_JUIZ` (juiz de neutralidade).
3. Rode `uv run fiatlux palavra diaria --dry-run`. O resumo final passa a mostrar
   `llm: local+cache`.

### O contrato da API

| Rota | Recebe | Devolve |
|---|---|---|
| `POST /v1/chat` | `messages` (cada uma com `role` `system`, `user` ou `assistant` e `content`), `model` (opcional), `temperature`, `max_tokens` e `allow_fallback` | `content` e, quando houver, `model` (o que de fato respondeu), `tokens_in`, `tokens_out`, `fallback_applied`, `queue_wait_s` |
| `GET /v1/models` | — | `models` (cada um com `name`, `installed`, `available` e `context`) e `default` |

A autenticação é por `Authorization: Bearer <chave>`, quando o servidor pede. Fila cheia
responde **429** com `Retry-After`; servidor sob pressão, **503**; modelo desconhecido, **404**.
O Fiat Lux espera o que o servidor pede (até 15 min somados por execução, `espera_fila_max_s`)
e, sob pressão, aceita um modelo mais leve (`allow_fallback`).

A API não tem saída estruturada: o Fiat Lux põe no prompt de sistema um molde da resposta
(campos, tipos e valores aceitos), extrai o objeto da resposta (tolera raciocínio entre
`<think>`, blocos de código, texto em volta e a resposta embrulhada num único campo) e valida
com Pydantic. Fora do formato, pede de novo, explicando o erro (`tentativas_formato`).

Ajustes em `config/settings.toml`, seção `[llm]`: temperatura por tarefa (baixa onde a resposta
é uma escolha, mais alta na redação), `max_tokens` (o teto da API é 8192; modelos que raciocinam
gastam cerca de 1000 tokens antes de responder), `timeout_s` por pedido e as esperas na fila. O
maior pedido, o da seleção, tem cerca de 4 mil tokens: use modelos com janela de pelo menos 8
mil (o `configurar` avisa quando a janela é menor).

As respostas ficam em cache por hash da entrada (`data/cache/llm.sqlite`): reprocessar o mesmo
dia não chama o servidor de novo.

Sem o servidor e sem `--dry-run`, as etapas de LLM usam as reservas (classificação por
palavras-chave, consultas determinísticas, seleção pelo escore) e a mensagem sai como
**fallback** (Evangelho + oração), com um aviso explicando o motivo.

O mesmo vale quando o servidor recusa de vez: chave recusada, URL errada, servidor inalcançável,
modelo inexistente ou ocupado por tempo demais. Na primeira recusa, o Fiat Lux para de chamar o
servidor pelo resto da execução (as outras etapas vão direto às reservas) e o primeiro aviso diz
o motivo, por exemplo `aviso: LLM indisponível nesta execução: o servidor de LLM recusou a chave
(401: …)`. O alerta ao administrador no Telegram traz o mesmo motivo.

## 9. Recebendo no Telegram

1. No Telegram, fale com o [@BotFather](https://t.me/BotFather), envie `/newbot` e guarde o
   **token**.

O jeito mais fácil, a partir daqui: rode `uv run fiatlux configurar` e responda `s` em
*Configurar o Telegram agora?*. Ele confere o token, pede que você mande uma mensagem ao bot,
acha o seu `chat_id` (e o de quem mais tiver escrito ao bot), grava tudo no `.env` e manda uma
mensagem de teste. À mão, os passos são estes:

2. Abra uma conversa com o seu bot e envie qualquer mensagem (o bot só pode escrever para quem
   já falou com ele).
3. Descubra o seu `chat_id` abrindo no navegador
   `https://api.telegram.org/bot<TOKEN>/getUpdates`: é o número em `"chat":{"id":…}`.
4. No `.env`:

   ```dotenv
   TELEGRAM_BOT_TOKEN=123456:ABC…
   TELEGRAM_CHAT_IDS=123456789
   TELEGRAM_ADMIN_CHAT_ID=123456789
   ```

5. Rode `uv run fiatlux palavra diaria`. A mensagem chega em HTML, dividida em partes de até
   4.096 caracteres, sem prévia de links.

Para dar retorno, **responda** a uma mensagem do bot com 👍 ou 👎 (e um comentário, se quiser).
O `uv run fiatlux estado feedback` grava essas respostas. No GitHub Actions, ele roda depois
de cada Palavra do Dia.

## 10. Agendamento

### GitHub Actions (padrão)

Os workflows já estão em `.github/workflows/`: `diaria.yml` (05:00 de Fortaleza), `semanal.yml`
(sábado, 17:00), `ci.yml` (testes) e `construir-indice.yml` (manual). Para ativar:

1. Mantenha o repositório **privado** enquanto o status de domínio público da Matos Soares não
   for confirmado ([LICENSES-DADOS.md](../LICENSES-DADOS.md)).
2. Em *Settings → Secrets and variables → Actions*, crie os secrets `FIATLUX_LLM_URL`,
   `FIATLUX_LLM_CHAVE`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS` e `TELEGRAM_ADMIN_CHAT_ID`
   e, se quiser escolher os modelos, as variables `FIATLUX_LLM_MODELO` e
   `FIATLUX_LLM_MODELO_GERACAO`. O servidor de LLM precisa ser alcançável pela internet: os
   runners do GitHub não enxergam a sua rede local.
3. Crie a branch órfã `estado`, onde o banco de estado é guardado entre execuções:

   ```bash
   git switch --orphan estado
   git commit --allow-empty -m "estado"
   git push -u origin estado
   git switch main
   ```

4. Em *Actions*, rode **construir-indice** uma vez (publica o índice como Release `indice-latest`).
5. Teste com *Run workflow* em **palavra-diaria** (aceita uma data opcional).

Os agendamentos só rodam a partir da branch padrão (`main`). O cron do GitHub pode atrasar
alguns minutos em horários de pico.

### Na sua máquina

Windows (Agendador de Tarefas), todo dia às 05:00:

```powershell
schtasks /Create /SC DAILY /ST 05:00 /TN "Fiat Lux" /TR "cmd /c cd /d C:\projetos\Fiat-Lux && uv run fiatlux palavra diaria"
```

Linux/macOS (`crontab -e`):

```cron
0 5 * * *  cd /caminho/Fiat-Lux && uv run fiatlux palavra diaria
0 17 * * 6 cd /caminho/Fiat-Lux && uv run fiatlux palavra semanal
```

Com `systemd`, use um *timer* com `Persistent=true` para rodar ao ligar se o horário foi perdido.

## 11. Acompanhamento e calibração

- `uv run fiatlux estado execucoes --ultimos 10`: status, etapa da falha, duração e custo de
  cada execução.
- `uv run fiatlux estado mensagens`: últimas mensagens, com status (`rascunho`, `enviada`,
  `fallback`, `falhou`).
- **Calibração do medidor:** durante 30 dias, registre o quanto o dia "pesou" para você:
  `uv run fiatlux estado percepcao 2026-11-09 60`. A Fase 7 compara essa série com o índice.
- **Avaliação:** `uv run fiatlux eval rodar --suite rapida` (parser, adversariais,
  metamórficos, recuperação) ou `--suite completa` (inclui 30 dias de ponta a ponta). Os
  relatórios ficam em `eval/relatorios/`.
- **Testes:** `uv run pytest`. Os testes de integração precisam da base montada (seção 3.1);
  sem ela, são pulados.

O [runbook](runbook.md) lista o que o sistema faz sozinho em cada falha e o que fazer à mão.

## 12. Privacidade

O Fiat Lux guarda só o `chat_id` de quem recebe e, das notícias, só título, link, data e
veículo. Para atender a um pedido de remoção (LGPD):

```bash
uv run fiatlux estado apagar-destinatario <chat_id> --sim
```

## 13. Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `uv : O termo 'uv' não é reconhecido como nome de cmdlet…` (Windows) | o uv foi instalado (por exemplo, com `pip install uv`) numa pasta fora do PATH | rode o `configurar.ps1`: ele acha o uv e põe a pasta no PATH. Com a `.venv` ativada, os comandos também funcionam sem o `uv run` (ex.: `fiatlux palavra diaria --dry-run`) |
| `… não pode ser carregado porque a execução de scripts foi desabilitada neste sistema` | política de execução padrão do Windows | rode antes `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force` (vale só para o terminal aberto) |
| `uv` funciona no terminal do script, mas não num terminal novo do VS Code | o VS Code guarda o PATH de quando foi aberto | feche e abra o VS Code |
| `uv sync` falha com `Acesso negado (os error 5)` | o VS Code (ou outro programa) está usando arquivos da `.venv` | feche o VS Code e rode o script de novo |
| `LLM: o servidor de LLM recusou a chave (401: …)` | chave ausente, errada ou revogada | emita uma chave no servidor e rode o `configurar` (ele deixa colar na hora) ou edite `FIATLUX_LLM_CHAVE` no `.env`. Se a variável também estiver no ambiente do sistema, troque lá: ela vale mais que o `.env` |
| `LLM: … não existe (FIATLUX_LLM_URL é a raiz do servidor, sem /v1 no fim)` | URL errada | corrija `FIATLUX_LLM_URL` (só a raiz, como `https://llm.exemplo.com`) |
| `LLM: servidor de LLM inalcançável em …` | servidor fora do ar, rede ou URL errada | abra `<URL>/v1/ready` no navegador; deve responder `ready` |
| `LLM: o servidor não tem o modelo …` | nome de modelo errado, ou modelo ainda não baixado no servidor | troque `FIATLUX_LLM_MODELO` (ou o da tarefa) no `.env`, ou baixe o modelo no servidor; `GET /v1/models` lista os que existem |
| `resposta fora do formato em …` | o modelo não devolveu o JSON pedido, nem depois da correção | de vez em quando é normal em modelos pequenos (a etapa usa a reserva); se for sempre, use um modelo maior em `FIATLUX_LLM_MODELO_GERACAO` ou aumente `tentativas_formato` em `[llm]` |
| `aviso: GDELT recusou por limite de taxa (429); notícias só do RSS` | o GDELT limita requisições por IP | nada: o RSS cobre os três escopos; o medidor fica sem o componente de tom |
| `já enviada para este destinatário; nada a fazer` | idempotência: o dia já foi entregue | use `--dry-run` para testar; para reenviar, apague a linha em `mensagens` (runbook) |
| `uv sync` falha com `os error 3` ou caminho não encontrado em arquivos do torch (Windows) | caminho do projeto longo demais (modo completo) | clone num caminho curto ou habilite caminhos longos ([seção 2](#2-instalação)) |
| `índice não construído: rode fiatlux indice construir` | falta o passo 3.2 | rode `uv run fiatlux indice construir` |
| `biblia.sqlite ausente` | falta o passo 3.1 | rode `baixar`, `ingerir` e `validar` |
| execução diária demorada (minutos) | o rerank neural em CPU custa ~0,4 s por par, e o servidor de LLM atende um pedido por vez | normal; para testar rápido, use `--sem-rerank` (ou `--llm offline`) |
| status `fallback` | alguma etapa falhou (liturgia, LLM, verificação) | leia os `aviso:` no fim da saída (se o LLM estava fora, o primeiro diz por quê) e `fiatlux estado execucoes`; para ver o traceback de um erro inesperado, `fiatlux --verboso palavra diaria --dry-run` |
| textos genéricos, sempre parecidos | sem `FIATLUX_LLM_URL`, o dry-run usa o cliente offline (e a demonstração do `configurar` também, quando o servidor não passa na conferência) | configure o servidor ([seção 8](#8-ligando-o-llm)) |
| a liturgia de uma data não aparece | a API não tem aquela data, ou está fora do ar | o Fiat Lux usa o cache e o calendário local; `fiatlux liturgia canario` testa a API |
