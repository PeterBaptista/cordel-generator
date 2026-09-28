---
name: escandir-sextilha
description: Produz e verifica sextilhas de cordel (6 versos, 7 sílabas poéticas, rima ABCBDB) a partir de uma notícia. Usa um script de escansão como juiz da métrica, e separa o que entra na coleção do que vira descarte. Use durante a produção do Projeto Autoral, depois que o eixo estiver declarado.
---

# escandir-sextilha

Você está ajudando um grupo da disciplina Criatividade Computacional (IF866, CIn-UFPE)
a produzir os artefatos do **Projeto Autoral**: folhetos de cordel feitos a partir de
notícias de IA da semana.

Esta skill **não escolhe a notícia e não decide o que entra na coleção**. Ela escreve,
mede, corrige e entrega o resultado medido. Quem decide é o grupo.

## A forma

- **Sextilha**: 6 versos.
- **Métrica**: 7 sílabas poéticas por verso (redondilha maior).
- **Rima**: ABCBDB — os versos 2, 4 e 6 rimam entre si. Os versos 1, 3 e 5 são livres.

Sílaba poética não é sílaba gramatical. A contagem vai até a **última sílaba tônica**
do verso, vogal final de uma palavra se funde com vogal (ou H) inicial da seguinte,
e ditongo vale uma sílaba só. Não conte de cabeça: **rode o script**.

## O laço

1. **Leia a notícia** que o grupo passou. Extraia o fato em uma frase.
2. **Escreva a sextilha.** Uma só, sem variações, sem pedir aprovação no meio.
3. **Meça**, sempre, antes de mostrar qualquer coisa:
   ```bash
   python3 scripts/escandir.py folhetos/<nome>.txt
   ```
4. **Corrija apenas os versos reprovados.** Não reescreva a estrofe inteira: o verso
   que passou já está certo, e refazê-lo costuma quebrá-lo.
5. **Repita no máximo 3 vezes.** Se na terceira ainda houver verso fora, **pare**.
   Entregue como está, diga qual verso resistiu e por quê. A tentativa que falhou é
   material do caderno de bordo, não lixo.
6. **Salve as versões descartadas** em `descarte/`, com o motivo em uma linha.

## Como ler o relatório do script

- `ok v3 [7]` — verso 3 tem 7 sílabas, passou.
- `XX v4 [6]` — verso 4 tem 6, falta uma. Reescreva **só ele**.
- `? elisao opcional em 'gou u'` — ponto ambíguo: a escansão aceita as duas leituras.
  **Não é erro.** Quem decide é o grupo, e a decisão vai para o caderno de bordo.
- `rima B (versos [2, 4, 6]): SEM RIMA` — o ABCBDB quebrou.
- `consoante` é rima plena (som igual a partir da tônica); `toante` rima só nas vogais,
  e é aceita no cordel tradicional, mas o grupo precisa saber que aceitou.

Para forçar uma leitura dentro do verso, use as marcas:
`_` junta com a palavra anterior, `|` separa um ditongo.

## O que você não faz

**Não escolhe a notícia.** O recorte é a parte autoral do trabalho.

**Não decide o descarte.** Você aponta o que reprovou; se uma estrofe fora da métrica
entra na coleção assim mesmo, essa decisão é do grupo, e precisa de motivo escrito.

**Não conta sílabas sem rodar o script.** Modelos de linguagem trabalham com tokens,
não com sílabas. Contar "de cabeça" produz erro com aparência de confiança.

**Não inventa o que aconteceu.** O caderno de bordo registra o processo real,
inclusive as tentativas ruins. Não escreva um histórico que não ocorreu.

## No fim de cada folheto

Registre, no caderno de bordo: o prompt **na íntegra**, o modelo e a versão, a semente
e os parâmetros, quantas rodadas de correção foram necessárias, quais versos você
corrigiu na mão, e o que o script marcou com `?` e como o grupo decidiu.
