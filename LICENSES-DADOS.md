# Licenças e atribuições das fontes de dados

O código do Fiat Lux está sob a licença MIT ([LICENSE](LICENSE)). As fontes de dados abaixo
têm licenças próprias. Elas são baixadas por `fiatlux biblia baixar`, fixadas por commit SHA e
SHA-256 em [fontes.lock.json](fontes.lock.json), e **não são redistribuídas neste repositório**
(ficam em `data/`, ignorada pelo git). A exceção são pequenas amostras usadas como fixtures de
teste, listadas no fim deste arquivo.

| Fonte | Uso | Licença | Atribuição obrigatória |
|---|---|---|---|
| [`Dancrf/biblia-db`](https://github.com/Dancrf/biblia-db) @ `c5feeff` | Bíblia Sagrada, trad. Pe. Manuel de Matos Soares (1956), 73 livros | **Não declarada** — ver abaixo | "Bíblia Sagrada, trad. Pe. Manuel de Matos Soares (1956)" |
| [`Projeto-Euaggelion/biblia.publica`](https://github.com/Projeto-Euaggelion/biblia.publica) @ `7231974` | Bíblia Livre (BLIVRE), 66 livros | BLIVRE: CC BY; projeto: CC BY-SA 4.0 | "Bíblia Livre (BLIVRE), © Diego Santos, Mario Sérgio e Marco Teles, Creative Commons Atribuição" (rodapé de toda mensagem que a cita) |
| [`scrollmapper/bible_databases`](https://github.com/scrollmapper/bible_databases) @ `59b18c5` | Referências cruzadas (`sources/extras/cross_references.txt`) | MIT (repositório); dados de referências cruzadas do [OpenBible.info](https://www.openbible.info/labs/cross-references/), CC BY | "Referências cruzadas: OpenBible.info (CC BY)" |
| [`ubsicap/versification_json`](https://github.com/ubsicap/versification_json) @ `0833abd` | Tabelas de versificação `eng`, `org`, `vul`, `lxx` | MIT | aviso de copyright mantido em `src/fiat_lux/biblia/dados/LICENSE-ubsicap-versification` |
| API [`liturgia.up.railway.app/v2`](https://github.com/Dancrf/liturgia-diaria) | Liturgia diária (celebração, cor, leituras, orações) | Não oficial; os textos do lecionário pertencem à **CNBB** | "Leituras: Liturgia Diária" |
| [GDELT DOC 2.0](https://www.gdeltproject.org/) | Notícias (metadados), volume e tom | Uso livre com atribuição | "Dados de notícias: The GDELT Project" |
| RSS: Google News, BBC News Brasil, g1, Agência Brasil, Vatican News | Notícias (somente título, link, data e veículo) | Termos de cada veículo | links para as fontes em cada mensagem |
| Modelos [`intfloat/multilingual-e5-base`](https://huggingface.co/intfloat/multilingual-e5-base) e [`BAAI/bge-reranker-v2-m3`](https://huggingface.co/BAAI/bge-reranker-v2-m3) | Embeddings e rerank (extra `[ml]`) | MIT / Apache-2.0 | — |

## Matos Soares: status a confirmar (plano §13.3)

O repositório de origem não declara licença. Pelas informações levantadas, o Pe. Manuel de
Matos Soares faleceu em 1957; pela regra brasileira (70 anos contados de 1º de janeiro do ano
seguinte à morte), a tradução entraria em domínio público em **01/01/2028**, e a edição de 1956
pode conter revisões de terceiros. Até a confirmação, **o repositório deve permanecer privado**
e o uso é pessoal. Para publicar antes disso: usar a BLIVRE como texto exibido no perfil
católico (ou só referências), ou obter confirmação do titular ou da editora. *Isto não é parecer
jurídico.*

## Textos litúrgicos (plano §13.4)

Os textos do lecionário vêm de uma API não oficial e pertencem à CNBB. O uso pessoal é
tranquilo; numa versão pública, exiba **só as referências** e um link para a fonte oficial.

## Notícias (plano §13.5)

Guardamos só metadados (título, URL, data, domínio). Nenhum corpo de artigo é armazenado nem
reproduzido; as mensagens trazem um resumo próprio e neutro e os links.

## Amostras versionadas como fixtures de teste

- `tests/fixtures/liturgia/*.json`: 4 dias da API de liturgia (uso pessoal, testes de contrato).
- `tests/fixtures/noticias/2026-11-09.json` e `google_news_ceara.xml`: metadados de manchetes
  de um dia (título, link, data, veículo) para testes offline.
- `tests/fixtures/vrs/`: `eng.json` e `vul.json` da ubsicap (MIT), com a licença.
- `eval/golden/referencias.yaml`: só as **referências** bíblicas das leituras de 2026–2027.
