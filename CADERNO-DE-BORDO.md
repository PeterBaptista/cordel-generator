# Caderno de bordo — Projeto Autoral

> **Critério da disciplina:** outra pessoa da turma consegue refazer este caminho
> lendo isto? Prompt resumido não é prompt. Escreva na íntegra.

**Grupo:** ✍️ Grupo: nomes
**Modalidade:** ✍️ Grupo: texto | imagem. O gerador produz os dois (a sextilha e a
xilogravura); a planilha pede uma só (ver `EIXO.md`, "O que ainda falta vocês decidirem").
**Período de produção:** 28/09/2026. O gerador foi construído e testado durante o dia;
as 5 gerações do grupo registradas até agora vão de 11:54 a 21:11 (horário de Brasília).

> **Como ler este caderno.** Os campos marcados **✍️ Grupo** só o grupo pode escrever:
> são decisões e memórias que não estão em nenhum registro. Todo o resto vem dos
> registros automáticos do gerador. O **registro por artefato** (prompts na íntegra,
> saídas brutas, relatórios do verificador, correções, custos) está em
> [`caderno/REGISTRO.md`](caderno/REGISTRO.md), gerado por `scripts/caderno.py` a partir de
> `caderno/*.json`. Depois de gerar a coleção final, rode `uv run python scripts/caderno.py`
> de novo.

---

## 1. Ferramentas e configuração

| Item | Valor |
|---|---|
| Modelo / versão (texto) | **gpt-6-luna** (padrão atual), raciocínio médio. O folheto 01 usou **gpt-5.5** com 3 candidatas, antes da troca. O modelo de cada chamada está no registro; o snapshot exato de cada resposta aparece no painel de logs da OpenAI, pelo `response_id`. |
| Modelo / versão (imagem) | Padrão atual: **gpt-image-1-mini**, qualidade `low`, 1536×1024 (opção "mínima", ~US$ 0,004 por imagem), chamado como ferramenta (`image_generation`) pelo **gpt-6-luna**. Os folhetos 01 a 05 usaram **gpt-image-2** `low` chamado pelo **gpt-5.4-mini** (~US$ 0,009). As opções "rápida" (gpt-image-2 low) e "detalhada" (gpt-image-2 medium) continuam no seletor. |
| Interface | API da OpenAI via **AI SDK para Python** (pacote `ai` 0.7.0), num site próprio (FastAPI) rodando localmente e no Railway |
| Temperatura / top_p | Não configurados. Os modelos de raciocínio da OpenAI não aceitam temperatura. O painel da OpenAI registrou `top_p` 0,98 na chamada da imagem, que é o padrão do serviço, não uma escolha nossa. |
| Semente fixa | **Não há.** A API usada não aceita semente para esses modelos: a mesma notícia gera versos diferentes a cada vez. A variedade é controlada pelo **narrador** escolhido (seletor; com "sortear", um ângulo por candidata) e a reprodutibilidade vem de registrar tudo (prompt, saída bruta, `response_id`), não de repetir a geração. |
| Script verificador | `scripts/escandir.py` (métrica e rima), mais critérios no gerador: palavra final repetida, ligação em deixa e as regras 1, 3, 7 e 9 do grupo (ver "Regras do grupo" abaixo) |
| Dicionário nordestino | `dados/dicionario_nordestino.csv`: 158 termos (108 palavras, 45 expressões, 5 partículas fáticas), com a fonte de cada um |
| Rodou offline? | O verificador sim (Python puro). A geração não: depende da API paga da OpenAI, a uns **US$ 0,01 a 0,02 por folheto** com o padrão atual (custos em `/logs` e no registro). |

**Por que esta ferramenta e não outra:** precisávamos de quatro capacidades.
(1) **Saída estruturada**: o modelo devolve JSON com as palavras finais planejadas e os
versos, que o verificador lê sem interpretar texto livre.
(2) **Texto e imagem na mesma interface**, para a xilogravura sair da mesma notícia e ficar
no mesmo registro.
(3) **Registro completo de cada chamada** (prompt de sistema e de usuário, saída bruta,
tokens, `response_id`): é o que torna este caderno possível sem copiar nada à mão.
(4) **Controle de custo por geração**: um teto de US$ 0,10 interrompe correções e júri
quando é atingido.
Não conseguimos fixar semente nem temperatura, e o registro completo compensa isso.

---

## 2. O encadeamento

Uma notícia até o folheto pronto, no site (`/`):

| # | Etapa | Automático ou manual |
|---|---|---|
| 0 | **Escolher a notícia** e colar o link (o servidor extrai o texto com `trafilatura`) ou o texto | **Manual** (grupo) |
| 0b | **Escolher os parâmetros** no site: modelo, raciocínio, candidatas, tipo de sextilha, estrofes, encadeamento, qualidade da imagem | **Manual** (grupo) |
| 1 | **Fato**: o modelo resume a notícia em uma frase, uma manchete e 3 a 5 imagens concretas | Automático |
| 2 | **Poema**: o modelo planeja as palavras finais e os termos do dicionário de cada estrofe e escreve os versos, na voz do narrador escolhido, seguindo as regras do grupo. Com mais de uma candidata, elas rodam em paralelo | Automático |
| 2b | **Júri** (só com 2 ou 3 candidatas): o modelo escolhe a melhor, preferindo as aprovadas pelo verificador | Automático |
| 3 | **Verificador**: `escandir.py` mede cada estrofe (7 sílabas, esquema de rima), mais palavra final repetida, a ligação em deixa e as regras 1, 3, 7 e 9 do grupo | Automático |
| 4 | **Correção**: o modelo reescreve **só os versos reprovados** (os aprovados são bloqueados), até 10 rodadas (3 até 28/09, quando os folhetos 01–05 foram gerados) ou até o teto de custo | Automático |
| 5 | **Xilogravura**: gerada em paralelo com o texto, a partir do fato | Automático |
| 6 | **Registro**: aprovado vai para `folhetos/`, reprovado para `descarte/` com o motivo na primeira linha; tudo no `caderno/<id>.json` | Automático |
| 7 | **Decidir as ambiguidades `?`** que o verificador marca (seção 3) | **Manual** (grupo) |
| 8 | **Escolher quais folhetos formam a coleção** entre os aprovados | **Manual** (grupo) |

O verificador decide o que **não** entra (métrica ou rima reprovada vai para `descarte/`).
Entre os que passam, a escolha é do grupo.

Os prompts de cada etapa estão na íntegra em `caderno/REGISTRO.md`; os de sistema, no
Apêndice A de lá. O código dos prompts é `app/prompts.py`.

---

## 3. Registro por artefato

O registro completo de cada geração está em **[`caderno/REGISTRO.md`](caderno/REGISTRO.md)**:
notícia de origem, parâmetros, fato extraído, cada prompt na íntegra com a saída bruta,
primeira versão, relatório do verificador em cada rodada, versos trocados em cada
correção, versão final e custo. As métricas verso a verso estão em
[`caderno/metrica.csv`](caderno/metrica.csv) (`escandir.py folhetos/2026*.txt --csv`).

Resumo das gerações do grupo até agora:

| # | Folheto | Resultado | Modelo | Forma | Correções | Custo |
|---|---|---|---|---|---|---|
| 01 | Meta lança Tamagotchi com inteligência artificial | entrou | gpt-5.5 (3 candidatas) | aberta, 1 estrofe | 0 | US$ 0,361 |
| 02 | Amador resolve desafio matemático com IA | entrou | gpt-6-luna | aberta, 1 estrofe | 3 | US$ 0,012 |
| 03 | Trump anuncia Força de IA nos EUA | entrou | gpt-6-luna | aberta, 4 estrofes | 3 | US$ 0,016 |
| 04 | Turismo rural cresce 10% em Pernambuco | entrou | gpt-6-luna | aberta, 1 estrofe | 2 | US$ 0,013 |
| 05 | Turismo rural cresce 10% em Pernambuco | **descarte**: estrofe 1, verso 1 com 8 sílabas, resistiu a 3 rodadas | gpt-6-luna, raciocínio baixo | aberta, 3 estrofes | 3 | US$ 0,011 |

> ⚠️ Os folhetos 04 e 05 **não são notícia de IA**: tratam de turismo rural. O eixo
> declarado fala em "notícias de IA da semana". ✍️ Grupo: decidam se entram, e se não,
> registrem como descarte de notícia.

**O que só o grupo sabe, por folheto:**

| # | Por que esta notícia entrou | O que foi feito na mão | Ambiguidades `?` do verificador e a decisão |
|---|---|---|---|
| 01 | ✍️ Grupo | ✍️ Grupo (se nada, escrevam "nada") | nenhuma marcada |
| 02 | ✍️ Grupo | ✍️ Grupo | v1 "notícia": 'ia' pode virar hiato → ✍️ decisão |
| 03 | ✍️ Grupo | ✍️ Grupo | E1.1 "anúncio" ('io' hiato?) · E1.2 elisão opcional em "foi às" · E1.4 "potência" ('ia' hiato?) · E2.1 "prédios" ('io' hiato?) · E4.1 elisão opcional em "céu a" · E4.4 elisão opcional em "não há" → ✍️ decisão |
| 04 | ✍️ Grupo | ✍️ Grupo | nenhuma marcada |
| 05 | ✍️ Grupo (descarte) | ✍️ Grupo | E2.1 elisão opcional em "vai o" · E2.5 "viajante" ('ia' hiato?) → ✍️ decisão |

**Critério de descarte adicionado durante a produção** (✍️ Grupo: confirmem ou retirem):
uma palavra final **repetida** reprova o verso. O `escandir.py` aceita "Pequim" rimando
com "Pequim" como rima consoante perfeita. Numa geração de teste o modelo fechou os
versos 2, 4 e 6 com a mesma palavra ("Pequim") para acertar a rima; o critério foi
criado por causa disso e fica no gerador (`app/workflow.py`, `palavras_repetidas`),
fora do verificador.

**Regras do grupo** (enviadas por um colega em 28/09, valem para toda geração a partir de
então; ✍️ Grupo: citem-nas no EIXO.md, que é de vocês). As que o código confere reprovam o
verso e mandam para correção, como a métrica; as outras vão no prompt e nos critérios do júri.

| # | Regra | Como é aplicada |
|---|---|---|
| 1 | Sem mesóclise nem ênclise | **verificada**: palavra com hífen + pronome ("disse-me", "dir-lhe-ei"); compostos como "bem-te-vi" não contam |
| 2 | Não gerar imagem | a xilogravura já é opcional (caixa "gerar xilogravura"); a modalidade é decisão do grupo |
| 3 | ≥1 termo do dicionário nordestino a cada 2 versos | **verificada** contra o dicionário, par a par (1–2, 3–4, 5–6) |
| 4 | As outras palavras no mesmo tom | prompt + júri |
| 5 | Não desviar da formalidade do cordel | prompt |
| 6 | 6 estrofes | seletor Estrofes (de 1 a 6) |
| 7 | Cada estrofe com um termo de mais de uma palavra | **verificada**: ≥1 expressão do dicionário por estrofe |
| 8 | Vocativo só no início ou fim do verso | prompt + júri (detectar vocativo exigiria análise sintática) |
| 9 | Partícula fática só no início ou fim do verso | **verificada** para "né" e "visse"; "viu", "tá" e "sabe" também são verbos comuns, então ficam só no prompt |
| 10 | Narrador observador em 1ª pessoa, roteiro fixo | seletor Narrador; padrão "observador" (onde eu estava → o que vi → o que ouvi dizer → o que penso) |
| 11 | Erros de flexão de número de propósito | prompt; a correção é instruída a não "consertá-los" |
| 12 | Termo do dicionário em contexto, nunca solto | prompt (cada termo vai com o sentido) + júri |

O **dicionário** foi montado pelo assistente de IA **para o grupo revisar** (✍️ Grupo: tirem,
acrescentem, corrijam). Fontes: Gilberto Albuquerque, *Dicionário de Termos Nordestinos*
(publicado no site de Jessier Quirino); Dicionário Popular, "190 gírias e expressões
nordestinas"; Terra, "Dicionário de nordestinês"; Made in Brasilis, "Gírias nordestinas". Só
entrou termo encontrado em pelo menos uma fonte (13 lembrados de memória ficaram de fora,
como "xodó" e "chamego"); o sentido é uma glosa curta escrita pelo assistente, não copiada.
Termos vulgares ou pejorativos das fontes foram excluídos, assim como palavras que em
português comum significam outra coisa ("abuso", "pisa"). O script está em
`desenvolvimento/dicionario/montar.py`.

**Testes de desenvolvimento.** Enquanto o gerador era construído, 9 gerações de teste e
um experimento de modelos foram rodados com notícias de exemplo. Não são artefatos da
coleção e ficam em [`desenvolvimento/`](desenvolvimento/); o experimento está descrito
em [`desenvolvimento/experimentos/README.md`](desenvolvimento/experimentos/README.md).

---

## 4. As skills de ideação (quatro linhas, obrigatório)

✍️ **Grupo.** Só vocês sabem quando usaram cada skill e o que ela mudou. Nenhum registro
do gerador cobre isso, e escrever por vocês seria inventar o processo.

| Skill | Quando usamos | O que mudou no que estávamos fazendo | Onde atrapalhou |
|---|---|---|---|
| abrir-o-leque | ✍️ | ✍️ | ✍️ |
| afiar-o-eixo | ✍️ | ✍️ | ✍️ |
| derrubar-a-ideia | ✍️ | ✍️ | ✍️ |
| escutar-a-reuniao | ✍️ | ✍️ | ✍️ |

> "Atrapalhou" é resposta boa. Se ficar em branco ou virar elogio, não ensina nada
> a quem escreveu as skills.

---

## 5. O que a máquina não deu conta

Observado nos registros e nos experimentos de 28/09 (números em
`desenvolvimento/experimentos/README.md`):

- **Métrica de primeira.** Mesmo o modelo mais caro do experimento (gpt-5.5, raciocínio médio) acertou
  as 7 sílabas em todos os versos em só **3 de 12** candidatas. Todo folheto do grupo com
  gpt-6-luna precisou de 2 ou 3 rodadas de correção. Com gpt-5.4-mini e raciocínio alto,
  só 1 de 4 folhetos passou depois de 3 rodadas. Contar sílaba poética continua fora do
  alcance do modelo sem o verificador.
- **Rima pela saída mais fácil.** Para acertar a rima B, o modelo repetiu a mesma palavra
  ("Pequim" nos versos 2, 4 e 6). O verificador aceitava; foi preciso um critério novo.
- **Fato distorcido nos modelos baratos.** Num teste, o gpt-5.4-mini escreveu "dez por
  cento" onde a notícia dizia 90%. Com raciocínio baixo, o gpt-5.5 generalizou
  ("computador" no lugar de "modelo de linguagem"). O júri cego preferiu o gpt-5.5 com
  raciocínio médio em 18 de 20 comparações.
- **Métrica contra sentido.** Com o verificador como ferramenta do próprio modelo, 12 de
  12 candidatas passaram na métrica, mas versos perderam o sentido ("Alunos miram
  jardim / Gigante chuta capim"). O júri preferiu os versos sem ferramenta.
- **Versos genéricos no modelo padrão.** O gpt-6-luna passa na métrica com poucas
  correções, mas às vezes cai no genérico ("A banca virou besteira"). Ele não foi
  comparado às cegas com os outros (a conta ficou sem crédito).
- **Texto e logotipo na xilogravura.** Sem proibição explícita, a imagem saiu com placas
  escritas ("FEIRA LIVRE"); depois da proibição, ainda apareceu um símbolo parecido com
  logotipo de empresa. A qualidade `medium` puxou para gravura em metal; a `low` ficou
  mais próxima da xilogravura.
- **Custo no raciocínio.** No folheto 01 (gpt-5.5), 91% do custo de texto foram tokens
  de raciocínio, não os versos.

- **Termo presente não é termo com sentido.** As regras 3 e 7 são conferidas pela
  presença do termo, e o modelo às vezes enfia o termo só para passar: no primeiro
  teste com as regras (gpt-6-luna, raciocínio baixo), saiu "Robô tem caixa dos peito" e
  "Na feira, caixa dos peito espanta". Isso fere a regra 12, que o código não consegue
  conferir; só o júri pesa, e o júri só roda com 2 ou mais candidatas.

✍️ Grupo: acrescentem o que vocês viram nas gerações da coleção.

---

## 6. O que faríamos diferente

✍️ **Grupo.** Curto e honesto, incluindo o que o cronograma custou ao projeto.

Pontos dos registros que podem ajudar:
- O modelo padrão (gpt-6-luna) foi escolhido por custo, sem teste cego de qualidade.
- Os experimentos de modelo (~US$ 6) esgotaram os créditos da conta no meio dos testes.
- As 5 gerações do grupo foram feitas no último dia antes da entrega (28/09, das 11:54
  às 21:11), e 2 delas não são notícia de IA.
