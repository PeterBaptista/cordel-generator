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
| `scripts/` | `escandir.py`, o verificador de métrica e rima |
| `CADERNO-DE-BORDO.md` | prompts na íntegra, sementes, parâmetros, o que foi na mão |

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

Em `/logs` fica o custo de cada geração, estimado pelos tokens do caderno: por etapa,
com o `response_id` para abrir a chamada no painel da OpenAI.

O script não decide o que entra: o que ele marca com `?` aparece na tela e no JSON
como `duvidas_para_o_grupo`.
