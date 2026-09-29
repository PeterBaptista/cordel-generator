# Experimentos de 28/09/2026: modelo, raciocínio e custo

Feitos durante o desenvolvimento do gerador, para decidir o modelo padrão.
São testes do gerador, **não artefatos da coleção**. As gerações de teste
ficam em `desenvolvimento/{caderno,folhetos,descarte}`.

## Texto: 6 configurações nas mesmas 4 notícias

O pipeline completo de texto (fato → 3 candidatas por ângulo → júri →
verificador → até 3 correções), sem imagem, rodou nas mesmas 4 notícias
(robô da feira, modelo que joga xadrez, Google e chips no espaço, futebol de robôs
na China). Script: `rodar.py` (A–D) e `rodar_ferramenta.py` (E–F). Dados brutos:
`modelos-A-B-C-D.json` e `modelos-E-F-ferramenta.json`.

| Config | Modelo | Raciocínio | Custo médio/folheto | Entraram | Correções (total) | Candidatas aprovadas de primeira |
|---|---|---|---|---|---|---|
| A | gpt-5.5 | médio | US$ 0,364 | 4/4 | 2 | 3/12 |
| B | gpt-5.5 | baixo | US$ 0,126 | 4/4 | 2 | 2/12 |
| C | gpt-5.4-mini | médio | US$ 0,120 | 4/4 | 4 | 2/12 |
| D | gpt-5.4-mini | alto | US$ 0,286 | 1/4 | 9 | 1/12 |
| E | gpt-5.5 + verificador como ferramenta | médio | US$ 0,326 | 4/4 | 0 | 12/12 |
| F | gpt-5.5 + verificador como ferramenta | baixo | US$ 0,197 | 4/4 | 0 | 12/12 |

Em E e F cada candidata era um agente que podia chamar o `escandir.py` para medir
os próprios versos antes de responder.

## Qualidade: júri cego

Um júri (gpt-5.5, raciocínio médio) recebeu, para cada notícia, as sextilhas
finais das configurações com os rótulos embaralhados, e as ordenou por fidelidade
ao fato, criatividade, registro de cordel e virada final. Script: `juri.py`
(A × B × C, 2 julgamentos por notícia) e `juri2.py` (A × E × F, 3 por notícia).
Pontos: 3 para o 1º lugar, 2 para o 2º, 1 para o 3º. O resultado foi impresso
no terminal e é transcrito aqui:

| Comparação | Pontos | 1º lugar |
|---|---|---|
| A × B × C | A 23 · B 12 · C 13 | A em 7 de 8 julgamentos |
| A × E × F | A 35 · E 20 · F 17 | A em 11 de 12 julgamentos |

Motivos mais citados pelo júri: B e C generalizaram ou erraram o fato (C escreveu
"dez por cento" onde a notícia dizia 90%; B trocou "modelo de linguagem" por
"computador"); E e F acertaram a métrica mas perderam sentido ("Alunos miram
jardim / Gigante chuta capim").

**Limites:** 4 notícias só; o júri é o mesmo modelo da configuração A, o que pode
favorecê-la.

## Imagem: qualidade da xilogravura

O mesmo prompt de xilogravura (notícia do Google) rodou em três configurações
(`img.py`): `imagem-gpt-image-2-low.png`, `imagem-gpt-image-2-medium.png` e
`imagem-gpt-image-1-mini-medium.png`. O `low` ficou mais próximo da xilogravura de
cordel (figuras em silhueta, sem logotipo); o `medium` parece gravura em metal e
desenhou um símbolo parecido com logotipo. Custo medido do `low`, lendo o
`tool_usage` da resposta: ~US$ 0,006 pela imagem, ~US$ 0,009 com o modelo que
chama a ferramenta.

## O que foi decidido a partir daqui

- Imagem: `gpt-image-2` em qualidade `low`.
- Texto: o grupo pediu custo máximo de ~US$ 0,10 por geração e os modelos mais
  baratos. O padrão virou **gpt-6-luna** (US$ 0,50/M de saída), 1 candidata, com
  teto de US$ 0,10 por geração. O gpt-6-luna **não entrou neste experimento**: a
  conta ficou sem crédito logo depois, e ele foi adotado sem comparação cega
  com os outros.

## Imagem abaixo de `low` (28/09, mais tarde)

A ferramenta de imagem não tem qualidade abaixo de `low`. O custo caiu por outros dois
caminhos, medidos lendo o `tool_usage` de cada resposta (mesmo prompt, notícia do Trump):

| Modelo de imagem | Tamanho | Hospedeiro | Tokens de imagem | Total |
|---|---|---|---|---|
| gpt-image-2 low (padrão anterior) | 1536×1024 | gpt-5.4-mini | ~158 | ~US$ 0,0088 |
| gpt-image-2 low | 1024×1024 | gpt-5.4-mini | 196 | US$ 0,0095 |
| gpt-image-1-mini low | 1024×1024 | gpt-5.4-mini | 272 | US$ 0,0052 |
| gpt-image-1-mini low | 1536×1024 | gpt-5.4-mini | 400 | US$ 0,0067 |
| **gpt-image-1-mini low** | **1536×1024** | **gpt-6-luna** | 400 | **US$ 0,0043** |

O modelo que "hospeda" a ferramenta só repassa o prompt, mas era metade do custo; trocá-lo
pelo gpt-6-luna não mudou o desenho. O 1024×1024 sairia cortado no cartaz 3:2. Ficou como
opção "mínima" e padrão: gpt-image-1-mini, low, 1536×1024, hospedeiro gpt-6-luna.
