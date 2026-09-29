# Do 7 ao 6: A Semana em Sextilha

Notícias de IA contadas em cordel. Projeto Autoral — Criatividade Computacional
(IF866), CIn/UFPE, 2026.2.

## O eixo

Cinco folhetos de cordel, cada um recontando uma notícia de IA da semana.
A restrição é formal e verificável: sextilha em redondilha maior — seis versos de
sete sílabas poéticas, rima ABCBDB — conferida por um verificador de escansão.
Repete-se a forma; varia a notícia.

O parágrafo completo está em [`EIXO.md`](EIXO.md).

## Estrutura

| Pasta | O que tem |
|---|---|
| `folhetos/` | os artefatos que entraram na coleção |
| `descarte/` | o que ficou de fora, com o motivo no topo de cada arquivo |
| `scripts/` | `escandir.py`, o verificador de métrica e rima; `caderno.py`, que gera `caderno/REGISTRO.md` |
| `CADERNO-DE-BORDO.md` | ferramentas, encadeamento, o que a máquina não deu conta, e os campos do grupo |
| `caderno/` | um JSON por geração, `REGISTRO.md` (registro por artefato, gerado) e `metrica.csv` |
| `desenvolvimento/` | gerações de teste e experimentos de modelo feitos ao construir o gerador (não são coleção) |

## Verificador

Python 3, sem dependências, roda offline.

```bash
python3 scripts/escandir.py --verso "O robô chegou na feira"
python3 scripts/escandir.py folhetos/*.txt --csv caderno/metrica.csv
```

## Gerador (AI SDK para Python + OpenAI)

O laço do [`SKILL.md`](SKILL.md) automatizado com o [AI SDK para Python](https://ai-python.dev/docs):
notícia → fato → sextilha → `escandir.py` → correção só dos versos reprovados (máx. 3 rodadas)
→ xilogravura → `folhetos/` ou `descarte/`, com o registro completo em `caderno/<slug>.json`
(prompts na íntegra, modelo, parâmetros, saída bruta e relatório de cada rodada).

A notícia entra por **link** (o servidor extrai o texto da matéria com `trafilatura`) ou
por **texto colado**. Se o link não abrir (bloqueio, paywall, página sem matéria), a tela
pede para colar o texto. O folheto sai no formato "Notícias em Cordel": manchete, xilogravura
horizontal e a sextilha, com botão para baixar o cartaz em PNG.

```bash
cp .env.example .env        # coloque a OPENAI_API_KEY
uv sync
uv run uvicorn app.server:app --reload
# abra http://localhost:8000
```

| Arquivo | O que faz |
|---|---|
| `app/workflow.py` | o laço; chama o verificador `scripts/escandir.py` sem modificá-lo |
| `app/prompts.py` | todos os prompts, para irem na íntegra ao caderno de bordo |
| `app/server.py` | FastAPI; `POST /api/cordel` devolve as etapas por SSE |
| `app/static/index.html` | a página de teste |

Na página dá para escolher o modelo de texto (famílias GPT-5, 5.4, 5.5, 5.6 e 6, com o
preço ao lado), o nível de raciocínio, quantas candidatas gerar e a qualidade da
xilogravura. O servidor só aceita os modelos da tabela em `app/custos.py`.

Também dá para escolher a forma do poema:

| Tipo de sextilha | Rima | Quem rima |
|---|---|---|
| aberta (padrão) | ABCBDB | 2, 4 e 6; os ímpares ficam livres |
| solta | ABABCD | 1 com 3, 2 com 4; 5 e 6 livres |
| corrida | AABCCB | 1 com 2, 3 com 6, 4 com 5 |
| desencontrada | ABBAAB | 1, 4 e 5; e 2, 3 e 6 |

com 1 a 6 estrofes, livres ou **em deixa** (como na cantoria: o 1º verso de cada estrofe
rima com o último da anterior). Fontes: [Francisco Martins, "Aprendendo sobre cordel:
sextilha"](https://franciscomartinsescritor.blogspot.com/2019/08/aprendndo-sobre-cordel-sextilha.html),
[Cordel na Educação](https://www.cordelnaeducacao.com.br/dicas-de-cordel/modalidades-de-estrofes-que-podem-ser-encontradas-no-cordel),
[Repentistas: sextilha](https://repentistas.identidadessonoras.org/modalidades/sextilha/).
A sextilha "fechada" (rimam todos os versos) ficou de fora porque as fontes não dizem
em que ordem.

O `escandir.py` verifica arquivos com várias estrofes (separadas por linha em branco)
e lê o esquema de uma linha `# esquema: AABCCB` no arquivo, ou de `--esquema`.

Em `/historico` ficam todas as sextilhas geradas (as que entraram e as de descarte),
cada uma no cartaz com a ficha dos parâmetros que a produziram: modelo, raciocínio,
candidatas, tipo de sextilha, estrofes, encadeamento, xilogravura, correções e custo.
Dá para filtrar e reabrir o gerador com os mesmos parâmetros.

Em `/logs` fica o custo de cada geração, estimado pelos tokens do caderno: por etapa,
com o `response_id` para abrir a chamada no painel da OpenAI.

O script não decide o que entra: o que ele marca com `?` aparece na tela e no JSON
como `duvidas_para_o_grupo`.
