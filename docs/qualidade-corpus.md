# Qualidade do corpus bíblico

> Relatório gerado por `fiatlux biblia relatorio` (não edite à mão). Fontes fixadas em `fontes.lock.json`.

## Contagens

| Tradução | Livros | Capítulos | Versículos (brutos) | Versículos (finais) |
|---|---|---|---|---|
| ms | 73 | 1334 | 35624 | 35728 |
| blivre | 66 | 1189 | 31101 | 31101 |

## Checagens

**28/28 aprovadas.**

| Checagem | OK | Detalhe |
|---|---|---|
| contagem bruta ms | ✅ | (73, 1334, 35624) (esperado (73, 1334, 35624)) |
| contagem bruta blivre | ✅ | (66, 1189, 31101) (esperado (66, 1189, 31101)) |
| âncora ms GEN 1,1 | ✅ | No princípio criou Deus o céu e a terra. |
| âncora ms GEN 1,3 | ✅ | E Deus disse: Exista a luz. E a luz existiu. |
| âncora ms PSA 22,1 | ✅ | O Senhor me apascenta: nada me falta; |
| âncora ms PSA 136,1 | ✅ | Junto dos rios de Babilônia, ali nos assentámos a chorar, lembrando-no |
| âncora ms JHN 3,16 | ✅ | Porque Deus amou de tal modo o mundo, que lhe deu seu Filho unigênito, |
| âncora blivre JHN 3,16 | ✅ | Porque Deus amou o mundo de tal maneira, que deu o seu Filho unigênito |
| âncora ms BAR 6,1 | ✅ | Por causa dos pecados que cometestes diante de Deus, sereis levados ca |
| âncora blivre PSA 23,1 | ✅ | O SENHOR é meu pastor, nada me faltará. |
| versificação PSA.22.1→PSA.23.1 | ✅ | → PSA.23.1 (tabela, 0.98) — deslocamento de capítulo (título fundido) |
| versificação PSA.9.2→PSA.9.1 | ✅ | → PSA.9.1 (tabela, 0.98) — título contado como versículo |
| versificação PSA.9.22→PSA.10.1 | ✅ | → PSA.10.1 (marcador, 0.99) — fusão Sl 9+10 na Vulgata |
| versificação PSA.50.3→PSA.51.1 | ✅ | → PSA.51.1 (tabela, 0.98) — título em dois versículos |
| versificação PSA.113.9→PSA.115.1 | ✅ | → PSA.115.1 (marcador, 0.99) — fusão Sl 114+115 |
| versificação PSA.114.1→PSA.116.1 | ✅ | → PSA.116.1 (tabela, 0.98) — divisão do Sl 116 |
| versificação PSA.115.10→PSA.116.10 | ✅ | → PSA.116.10 (tabela, 0.98) — divisão do Sl 116 (numeração continua do Sl 114) |
| versificação PSA.136.1→PSA.137.1 | ✅ | → PSA.137.1 (tabela, 0.98) — deslocamento |
| versificação PSA.138.1→PSA.139.1 | ✅ | → PSA.139.1 (tabela, 0.98) — título fundido |
| versificação PSA.146.1→PSA.147.1 | ✅ | → PSA.147.1 (tabela, 0.98) — divisão do Sl 147 |
| versificação PSA.147.12→PSA.147.12 | ✅ | → PSA.147.12 (tabela, 0.98) — divisão do Sl 147 (numeração continua do Sl 146) |
| versificação DAN.3.91→DAN.3.24 | ✅ | → DAN.3.24 (tabela, 0.98) — acréscimo grego antes (Dn 3,24-90) |
| versificação DAN.3.98→DAN.4.1 | ✅ | → DAN.4.1 (tabela, 0.98) — Dn 3,98-100 = eng 4,1-3 |
| versificação MAL.4.1→MAL.4.1 | ✅ | → MAL.4.1 (tabela, 0.98) — Malaquias com 4 capítulos |
| versificação JHN.3.16→JHN.3.16 | ✅ | → JHN.3.16 (tabela, 0.98) — identidade |
| acréscimo grego DAN.3.24 marcado | ✅ | ["deutero_trecho"] |
| acréscimo grego DAN.13.1 marcado | ✅ | ["deutero_trecho"] |
| acréscimo grego EST.11.2 marcado | ✅ | ["deutero_trecho"] |

## Versificação MS → eng

- Versículos protocanônicos da MS (sem títulos e acréscimos gregos): **31062**
- Mapeados: **99.99%**
- Mapeados com confiança ≥ 0,8: **99.94%** (meta ≥ 99%)

Métodos: tabela 34827, alinhamento 517, marcador 35


Mapeamentos de baixa confiança (15; primeiros 40):

| MS | eng | Método | Conf. |
|---|---|---|---|
| LEV.15.21 | LEV.15.21 | tabela | 0.70 |
| NUM.16.42 | NUM.16.42 | tabela | 0.70 |
| DEU.6.12 | DEU.6.12 | tabela | 0.70 |
| JDG.5.32 | JDG.5.31 | tabela | 0.70 |
| 1SA.20.43 | 1SA.20.42 | tabela | 0.70 |
| JOB.12.25 | JOB.12.25 | tabela | 0.70 |
| JOB.38.32 | JOB.38.33 | alinhamento | 0.60 |
| JOB.38.34 | JOB.38.34 | tabela | 0.70 |
| PSA.59.1 | PSA.60.1 | tabela | 0.70 |
| SNG.7.13 | SNG.7.13 | tabela | 0.70 |
| ISA.9.21 | ISA.9.21 | tabela | 0.70 |
| LAM.5.5 | LAM.5.5 | tabela | 0.70 |
| HOS.2.23 | HOS.2.23 | tabela | 0.70 |
| 1CO.9.9 | 1CO.9.9 | tabela | 0.70 |
| PHP.1.16 | PHP.1.16 | tabela | 0.70 |

Versículos da BLIVRE sem par na MS: 41 (ex.: GEN.49.32, EXO.38.25, EXO.39.21, EXO.39.22, NUM.15.12, NUM.15.16, NUM.20.22, NUM.27.6, JOS.20.9, JOS.21.36, JOS.21.38, JOS.24.19, RUT.1.19, 1SA.22.20, 1CH.11.33)


## Títulos de salmos (MS)

versiculo_so_titulo: 63, fundido_separado: 56


## Lacunas (versículos ausentes na numeração da MS)

Total: **165**. Nos livros prioritários (Evangelhos, Salmos, Sapienciais, Profetas maiores): 154, das quais **154** corrigidas ou aceitas (100%).

| Status | Tipo | Qtde |
|---|---|---|
| aceita | ausente | 9 |
| aceita | fundido | 56 |
| corrigida | fundido | 100 |

## Divisões automáticas de versículos fundidos

100 aplicadas de 104 candidatas.

| Ref (MS) | sim1 | sim2 | Aplicada | Início da 2ª parte |
|---|---|---|---|---|
| GEN 15,3 | 0.26 | 0.30 | sim | Imediatamente o Senhor lhe dirigiu a palavra, dizendo: este não será o teu herde |
| JOS 5,3 | 0.09 | 0.40 | não | Todos os varões dentre o povo, que tinham saído do Egipto, todos os homens de gu |
| JOS 22,3 | 0.41 | 0.68 | sim | Agora, visto que o Senhor vosso Deus deu repouso e paz aos vossos irmãos, como l |
| 2KI 19,21 | 0.48 | 0.62 | sim | A quem insultaste, contra quem blasfemaste? Contra quem levantaste a tua voz? A  |
| 1CH 5,1 | 0.59 | 0.31 | sim | quanto a Judá, que era o mais valente de todos os seus irmãos, da sua estirpe sa |
| EZR 8,2 | 0.72 | 0.43 | sim | dos filhos de David, Hato, que descendia de Sequenias; dos filhos de Faros, Zaca |
| PSA 36,15 | 0.51 | 0.32 | sim | Mais vale o pouco ao justo, que as muitas riquezas aos ímpios, |
| PRO 1,4 | 0.30 | 0.21 | sim | O sábio, ouvindo (estas sentenças), ficará mais sábio, e o que as entender adqui |
| PRO 1,24 | 0.32 | 0.33 | sim | visto que desprezastes todos os meus conselhos, e não fizestes caso das minhas r |
| PRO 1,26 | 0.43 | 0.34 | sim | quando vos assaltar o terror, quando cair sobre vós, como furacão, o terror, qua |
| PRO 2,4 | 0.47 | 0.70 | sim | então compreenderás o temor do Senhor, e chegarás ao conhecimento de Deus. |
| PRO 2,6 | 0.25 | 0.27 | sim | Ele reserva a salvação para os justos, protege os que caminham rectamente, |
| PRO 3,1 | 0.42 | 0.49 | sim | porque eles te acrescentarão longos dias, anos de vida, e prosperidade. |
| PRO 3,4 | 0.45 | 0.44 | sim | Tem confiança no Senhor de todo o teu coração, e não te estribes na tua prudênci |
| PRO 3,24 | 0.40 | 0.13 | sim | Não receies nenhum terror imprevisto, nem a ruína reservada aos ímpios, quando v |
| PRO 3,26 | 0.35 | 0.15 | sim | Não recuses um benefício ao que dele precisa, se estiver em teu poder concedê-lo |
| PRO 4,4 | 0.47 | 0.65 | sim | Adquire sabedoria, adquire, a todo o custo, inteligência; não te esqueças nem te |
| PRO 4,21 | 0.18 | 0.71 | sim | porque são vida para os que as acham, saúde para todo o seu corpo. |
| PRO 4,24 | 0.58 | 0.33 | sim | Os teus olhos olhem direitos, a tua vista preceda os teus passos. |
| PRO 5,1 | 0.53 | 0.25 | sim | para conservares a reflexão e manteres em teus lábios a ciência. |
| PRO 5,21 | 0.40 | 0.29 | sim | O ímpio é presa das suas próprias iniquidades, e é ligado com as cadeias dos seu |
| PRO 6,1 | 0.70 | 0.37 | sim | com as palavras saídas de teus lábios te meteste no laço, e ficaste preso pela t |
| PRO 6,6 | 0.27 | 0.28 | sim | Não tendo ela guia, nem inspector, nem príncipe, |
| PRO 6,21 | 0.34 | 0.45 | sim | Quando andares, eles te acompanharão, quando dormires, eles te guardarão, e, ao  |
| PRO 6,24 | 0.37 | 0.52 | sim | Não cobice o teu coração a sua formosura, nem te deixes prender dos seus olhares |
| PRO 7,1 | 0.33 | 0.46 | sim | Filho, observa os meus mandamentos, e viverás; (guarda) a minha lei como a menin |
| PRO 7,4 | 0.64 | 0.56 | sim | e chama à inteligência tua amiga, para que te guardem da mulher estranha, da alh |
| PRO 7,6 | 0.49 | 0.13 | sim | e vi uns incautos, e (entre eles) notei um jovem insensato, |
| PRO 7,21 | 0.38 | 0.18 | sim | Ele segue-a logo, como um boi que é levado para o açougue, como um veado colhido |
| PRO 8,1 | 0.38 | 0.46 | sim | No mais alto e elevado das eminências, ao longo do caminho, nas encruzilhadas el |
| PRO 8,4 | 0.40 | 0.19 | sim | Aprendei, ó inexperientes, a prudência, e vós, insensatos, tomai inteligência. |
| PRO 8,6 | 0.32 | 0.33 | sim | A minha boca publicará a verdade, e os meus lábios detestarão o ímpio. |
| PRO 8,26 | 0.47 | 0.39 | sim | Quando ele preparava os céus, eu estava presente; quando, por uma lei inviolável |
| PRO 9,1 | 0.50 | 0.33 | sim | Imolou as suas vitimas, preparou o vinho, pôs a sua mesa. |
| PRO 9,4 | 0.10 | 0.50 | não | Vinde, comei o pão que eu vos dou, bebei o vinho que vos preparei. |
| PRO 9,6 | 0.28 | 0.26 | sim | Aquele que corrige o mofador, atraí o escárnio sobre si, e aquele que repreende  |
| PRO 10,21 | 0.62 | 0.22 | sim | A bênção do Senhor faz os (homens) ricos; a nossa fadiga não junta nada. |
| PRO 10,24 | 0.34 | 0.19 | sim | O ímpio desaparecerá como um turbilhão que passa; mas o justo fica em fundamento |
| PRO 10,26 | 0.65 | 0.37 | sim | O temor do Senhor prolonga os dias, porém os anos dos ímpios serão abreviados. |
| PRO 11,6 | 0.23 | 0.40 | sim | Quando morre o ímpio, desaparece toda a sua esperança; e a expectativa dos iníqu |
| PRO 11,21 | 0.21 | 0.29 | sim | Um anel de oiro no focinho dum porco, tal é a mulher formosa mas insensata. |
| PRO 11,26 | 0.44 | 0.36 | sim | Aquele que faz o bem, bens atrai (sobre si); aquele porém que busca fazer o mal, |
| PRO 12,1 | 0.40 | 0.21 | sim | Aquele que é bom terá do Senhor graça; mas o maldoso é por ele condenado. |
| PRO 12,4 | 0.39 | 0.48 | sim | Os pensamentos dos justos são cheios de justiça, mas os conselhos dos ímpios são |
| PRO 12,6 | 0.22 | 0.36 | sim | Os maus são derrubados, não subsistirão; mas a casa dos justos permanecerá firme |
| PRO 13,1 | 0.29 | 0.38 | sim | O homem (justo) será saciado de bens pelo fruto da sua boca; o desejo dos pérfid |
| PRO 14,6 | 0.36 | 0.22 | sim | Afasta-te do homem insensato, pois ele não conhece os ditames da prudência. |
| PRO 14,21 | 0.53 | 0.25 | sim | Os que praticam o mal, acaso não se transviam? A misericórdia e a verdade são pa |
| PRO 14,26 | 0.35 | 0.45 | sim | O temor do Senhor é uma fonte de vida, que afasta dos laços da morte. |
| PRO 15,1 | 0.30 | 0.42 | sim | A língua dos sábios torna amável a ciência; da boca dos insensatos derrama-se a  |
| PRO 15,6 | 0.36 | 0.36 | sim | Os lábios dos sábios difundirão a ciência; não assim o coração dos insensatos. |
| PRO 15,24 | 0.08 | 0.46 | não | O Senhor demolirá a casa dos soberbos, e firmará os limites da viúva. |
| PRO 15,26 | 0.24 | 0.29 | sim | Aquele que vai atrás da avareza perturba a sua casa; o que porém aborrece os sub |
| PRO 16,1 | 0.33 | 0.81 | sim | Todos os caminhos do homem são puros a seus olhos, mas o Senhor pesa os espírito |
| PRO 16,21 | 0.53 | 0.15 | sim | o que é doce no falar receberá coisas maiores. A sabedoria é uma fonte de vida p |
| PRO 16,24 | 0.46 | 0.57 | sim | (Às vezes) um caminho parece direito ao homem, e contudo o seu termo é a morte. |
| PRO 16,26 | 0.48 | 0.30 | sim | O homem ímpio cava a desgraça, e nos seus lábios se vai ateando o fogo. |
| PRO 17,1 | 0.37 | 0.40 | sim | O servo prudente prevalecerá sobre o filho insensato (do seu amo), e partilhará  |
| PRO 17,4 | 0.40 | 0.54 | sim | Aquele que despreza o pobre, insulta o seu Criador, e o que se alegra com a ruín |
| PRO 17,6 | 0.72 | 0.24 | sim | Palavras finas não convêm ao insensato, e ainda menos a um príncipe palavras men |

## Duplicados resolvidos

| Ref | Ocorrências | Método | Detalhe |
|---|---|---|---|
| JOS 8,9 | 2 | manual | 1ª ocorrência tem o erro "entro"; a 2ª, "entre" |
| 2SA 22,48 | 2 | identico | mantida a 1ª |
| EZR 6,14 | 2 | copia_espuria | descartada(s) 1 cópia(s) de EZR 4,14 |
| EZR 6,15 | 2 | copia_espuria | descartada(s) 1 cópia(s) de EZR 4,15 |
| EZR 6,16 | 2 | copia_espuria | descartada(s) 1 cópia(s) de EZR 4,16 |
| EZR 6,17 | 2 | copia_espuria | descartada(s) 1 cópia(s) de EZR 4,17 |
| EZR 6,18 | 2 | copia_espuria | descartada(s) 1 cópia(s) de EZR 4,18 |
| EZR 6,19 | 3 | copia_espuria | descartada(s) 1 cópia(s) de EZR 4,19 |
| EZR 6,20 | 2 | copia_espuria | descartada(s) 1 cópia(s) de EZR 4,20 |
| EZR 6,21 | 2 | copia_espuria | descartada(s) 1 cópia(s) de EZR 4,21 |
| EZR 6,22 | 2 | copia_espuria | descartada(s) 1 cópia(s) de EZR 4,22 |
| EST 1,12 | 2 | manual | recusa de Vasti (2ª) precede a ira do rei (1ª), como em Est 1,12 |
| JOB 34,20 | 2 | manual | 2ª ocorrência ("Deus não teme os grandes.") é resumo editorial |
| PSA 106,43 | 2 | quase_identico | mantida a 1ª; revisar |
| PSA 118,126 | 2 | manual | 1ª ocorrência tem "E tempo"; a 2ª, "É tempo" |
| SIR 10,26 | 2 | identico | mantida a 1ª |
| DAN 2,28 | 2 | manual | "Mas no céu há um Deus..." precede "O teu sonho e as visões..." |
| DAN 13,15 | 2 | identico | mantida a 1ª |
| HOS 11,1 | 2 | manual | na Vulgata, Os 11,1 começa com o fim de 10,15 ("Desde a aurora...") |
| LUK 9,41 | 2 | manual | 2ª ocorrência é nota de rodapé ("Ver nota Mt. 18, 19.") |
| ROM 8,26 | 2 | identico | mantida a 1ª |

Edições manuais: 1CH 1,10: dividir (1Cr 1,11 = "Mesraim gerou Ludim..."); 1CH 10,26: mover ("Os mais valentes do exército eram: Asael..." é 1Cr 11,26 (gerava 11 lacunas falsas em 1Cr 10)); EST 16,6: dividir (Est 16,7 (Vulg. "Quae res et ex veteribus probatur historiis")); PRO 6,26: dividir (Pv 6,27); PRO 11,24: dividir (Pv 11,25); PRO 24,1: dividir (Pv 24,2); PRO 24,4: dividir (Pv 24,5); SNG 4,6: dividir (Ct 4,7); WIS 12,6: dividir (Sb 12,7 (Vulg. "ut dignam perciperent...")); SIR 1,31: dividir (Eclo 1,32 (Vulg. "execratio autem peccatoribus")); SIR 10,21: dividir (Eclo 10,22); SIR 17,1: dividir (Eclo 17,2 (Vulg. "Et iterum convertit illum")); SIR 19,6: dividir (Eclo 19,7); SIR 22,1: dividir (Eclo 22,2); SIR 23,21: dividir (Eclo 23,22); SIR 23,24: dividir (Eclo 23,25); SIR 28,6: dividir (Eclo 28,7 (Vulg. "tabitudo enim et mors")); SIR 30,21: dividir (Eclo 30,22); SIR 30,22: dividir (Eclo 30,23 (encadeada com a anterior)); SIR 34,26: dividir (Eclo 34,27); SIR 39,4: dividir (Eclo 39,5); SIR 45,4: dividir (Eclo 45,5); SIR 46,4: dividir (Eclo 46,5); SIR 50,4: dividir (Eclo 50,5); SIR 50,6: dividir (Eclo 50,7 (Vulg. "Et quasi sol refulgens")); SIR 51,21: dividir (Eclo 51,22); JER 18,4: dividir (Jr 18,5); JER 31,24: substituir (artefato de OCR)


## Limpeza (ocorrências por regra)

- **ms**: ver_nota 1721, espaco_antes_pontuacao 377, marcador_hebraico 35, espaco_antes_fecha 20, espacos 18, sublinhado 15, espaco_apos_abre 14, hifen_invisivel 13, nota_numerica_final 12, aspas_simples_tipograficas 11, colchetes_chaves 8, marcador_nota_chave 3, parenteses_vazios 1, asterisco 1

- **blivre**: aspas_duplas_tipograficas 3831, aspas_simples_tipograficas 756, nota_numerica_final 138, espaco_antes_pontuacao 116, espaco_antes_fecha 5, espaco_apos_abre 4, colchetes_chaves 2


## Arquivos por livro × `biblia.json` (MS)

67 de 73 livros com diferenças (não usados como fonte).

| Livro | Nome no arquivo | Divergentes | Só no arquivo | Só no biblia.json |
|---|---|---|---|---|
| LEV | Levítico | 22 | 0 | 0 |
| NUM | Números | 33 | 0 | 0 |
| DEU | Deuteronómio | 24 | 0 | 0 |
| JOS | Livro de Josué | 17 | 0 | 0 |
| JDG | Livro dos Juízes | 29 | 0 | 0 |
| RUT | Livro de Rute | 3 | 0 | 0 |
| 1SA | Livro Primeiro de Samuel | 38 | 0 | 0 |
| 2SA | Livro Segundo de Samuel | 16 | 0 | 0 |
| 1KI | Livro Primeiro dos Reis | 8 | 0 | 0 |
| 2KI | Livro Segundo dos Reis | 1 | 0 | 0 |
| 1CH | Livro Primeiro das Crónicas | 1 | 0 | 0 |
| EZR | Livro de Esdras | 5 | 0 | 0 |
| NEH | Livro de Neemias | 4 | 0 | 0 |
| TOB | Livro de Tobias | 4 | 0 | 0 |
| JDT | Livro de Judit | 3 | 0 | 0 |
| EST | Livro de Ester | 8 | 0 | 0 |
| 1MA | Livro Primeiro dos Macabeus | 10 | 0 | 0 |
| 2MA | Livro Segundo dos Macabeus | 9 | 0 | 0 |
| JOB | Livro de Job (Jó) | 43 | 0 | 0 |
| PSA | Salmos | 107 | 0 | 0 |
| PRO | Livro dos Provérbios | 62 | 0 | 0 |
| ECC | Livro do Eclesiaste | 26 | 0 | 0 |
| SNG | Cânticos dos Cânticos | 32 | 0 | 0 |
| WIS | Livro da Sabedoria | 65 | 0 | 0 |
| SIR | Eclesiástico | 121 | 0 | 0 |
| ISA | Profecia de Isaías | 102 | 0 | 0 |
| JER | Profecia de Jeremias | 25 | 0 | 0 |
| LAM | Trenos ou Lamentações de Jeremias | 9 | 0 | 0 |
| BAR | Profecia de Baruch | 14 | 0 | 0 |
| EZK | Profecia de Ezequiel | 55 | 0 | 0 |
| DAN | Profecia de Daniel | 51 | 0 | 0 |
| HOS | Oseias | 35 | 0 | 0 |
| JOL | Profecia de Joel | 6 | 0 | 0 |
| AMO | Profecia de Amós | 6 | 0 | 0 |
| JON | Profecia de Jonas | 1 | 0 | 0 |
| MIC | Profecia de Miqueias | 6 | 0 | 0 |
| NAM | Profecia de Naum | 2 | 0 | 0 |
| HAB | Profecia de Habucuc | 4 | 0 | 0 |
| ZEP | Profecia de Sofonias | 8 | 0 | 0 |
| HAG | Profecia de Ageu | 4 | 0 | 0 |
| ZEC | Profecia de Zacarias | 40 | 0 | 0 |
| MAL | Profecia de Malaquias | 10 | 0 | 0 |
| MAT | Evangelho segundo S. Mateus | 58 | 0 | 0 |
| MRK | Evangelho segundo S. Marcos | 53 | 0 | 0 |
| LUK | Evangelho segundo S. Lucas | 78 | 0 | 0 |
| JHN | Evangelho segundo S. João | 28 | 0 | 0 |
| ACT | Actos dos Apóstolos | 63 | 0 | 0 |
| ROM | Epístola aos Romanos | 83 | 0 | 0 |
| 1CO | Primeira Epístola aos Coríntios | 45 | 0 | 0 |
| 2CO | Segunda Epístola aos Coríntios | 24 | 0 | 0 |
| GAL | Epístola aos Galatas | 11 | 0 | 0 |
| EPH | Epístola aos Efésios | 17 | 0 | 0 |
| PHP | Epístola aos Filipenses | 6 | 0 | 0 |
| COL | Epístola aos Colossenses | 10 | 0 | 0 |
| 1TH | Primeira Epístola aos Tessalonicenses | 7 | 0 | 0 |
| 2TH | Segunda Epístola aos Tessalonicenses | 4 | 0 | 0 |
| 1TI | Primeira Epístola a Timóteo | 8 | 0 | 0 |
| 2TI | Segunda Epístola a Timóteo | 10 | 0 | 0 |
| TIT | Epístola a Títo | 4 | 0 | 0 |
| HEB | Epístola aos Hebreus | 33 | 0 | 0 |
| JAS | Epístola de S. Tiago | 14 | 0 | 0 |
| 1PE | Primeira Epístola de S. Pedro | 10 | 0 | 0 |
| 2PE | Segunda Epístola de S. Pedro | 8 | 0 | 0 |
| 1JN | Primeira Epístola de S. João | 10 | 0 | 0 |
| 2JN | Segunda Epístolas de S. João | 1 | 0 | 0 |
| JUD | Epístola de S. Judas | 1 | 0 | 0 |
| REV | Apocalipse de S. João | 80 | 0 | 0 |


Referências cruzadas importadas: 344799.
