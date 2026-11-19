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
notícia → fato → 3 candidatas → `escandir.py` → correção só dos versos reprovados, pelo próprio Poeta e na mesma conversa (8 + 2 por estrofe, até 20 rodadas) → júri semântico entre as aprovadas → reescrita pelo sentido, se melhorar
→ xilogravura → `folhetos/` ou `descarte/`, com o registro completo em `caderno/<slug>.json`
(prompts na íntegra, modelo, parâmetros, saída bruta e relatório de cada rodada).
Na correção, o Poeta manda cada verso consertado com mais duas alternativas, e o verificador
fica com a que passa. A partir da 4ª rodada, a correção usa raciocínio médio. Candidata com
estrutura errada (número de estrofes ou de versos) recebe até 2 pedidos de "refaça" antes de
ir para correção, em vez do descarte direto.

A notícia entra por **link** (o servidor extrai o texto da matéria com `trafilatura`) ou
por **texto colado**. Se o link não abrir (bloqueio, paywall, página sem matéria), a tela
pede para colar o texto. O folheto sai no formato "Notícias em Cordel": manchete, xilogravura
horizontal e a sextilha, com botão para baixar o cartaz em PNG.

```bash
cp .env.example .env        # coloque a OPENAI_API_KEY
uv sync
uv run uvicorn app.server:app --reload
# abra http://localhost:8000 (home) e http://localhost:8000/gerador
```

| Arquivo | O que faz |
|---|---|
| `app/static/home.html` | a home pública: a coleção no cordão, o descarte e os itens da entrega |
| `app/workflow.py` | o laço; chama o verificador `scripts/escandir.py` sem modificá-lo |
| `app/prompts.py` | todos os prompts, para irem na íntegra ao caderno de bordo |
| `app/server.py` | FastAPI; `POST /api/cordel` devolve as etapas por SSE |
| `app/static/index.html` | a página de teste |

Na página dá para escolher o modelo de texto (famílias GPT-5, 5.4, 5.5, 5.6 e 6, com o
preço ao lado), o nível de raciocínio, quantas candidatas gerar e a qualidade da
xilogravura. O servidor só aceita os modelos da tabela em `app/custos.py`.
A página sempre abre na configuração mais barata (gpt-6-luna, raciocínio baixo,
xilogravura mínima: gpt-image-1-mini). Escolher algo mais caro, ou gerar com algo mais caro, abre um aviso
com o preço e a opção de voltar ao mais barato. Forma, estrofes e candidatas mudam
sem aviso.

Toda geração segue as **regras do grupo** (sem ênclise ou mesóclise, termos do dicionário
nordestino (2 por estrofe na prioridade notícia; um a cada 2 versos na forma), uma expressão por estrofe, partícula fática só na ponta do verso,
concordância popular, narrador em 1ª pessoa…). As que dá para conferir por código reprovam o
verso e mandam para correção; a lista completa, com o que é conferido e o que é só pedido, está
no `CADERNO-DE-BORDO.md`. O dicionário fica em `dados/dicionario_nordestino.csv` (158 termos,
com a fonte de cada um) e pode ser editado pelo grupo.

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

**Páginas.** A home (`/`) é o link da entrega, com as
10 gerações mais recentes que passaram no verificador penduradas no cordão, o descarte do grupo
com o motivo e os cinco itens do PA 1. Em `/sextilhas` ficam todas as sextilhas geradas, com o
nome de quem gerou, e cada uma abre em `/geracao/<id>`: a linha do tempo da geração (fato,
candidatas, escansões, correções com antes/depois, júri, reescritas), que dá para reproduzir
passo a passo. Desde 16/11 o caderno guarda os eventos que foram à tela; os antigos são remontados.

**Quem gera e com qual chave** (`app/contas.py`):

| | Chave do professor | Chave própria |
|---|---|---|
| Precisa de conta | sim (cadastro com `CORDEL_CONVITE`, ou o admin cria em `/admin`) | não; basta o nome |
| Limite | `CORDEL_COTA_DIA` gerações/dia por pessoa (10), uma por vez, teto `CORDEL_TETO_USD` | teto `CORDEL_TETO_PROPRIA_USD` |
| Modelos | só `gpt-6-luna` e `gpt-image-1-mini` | todos da tabela de `app/custos.py` |

A chave própria fica em Configurações, no `localStorage` do navegador; vai num cabeçalho
`X-OpenAI-Key` a cada geração e o servidor não a grava (o caderno só diz `"chave": "propria"`).
Sem `OPENAI_API_KEY_PROFESSOR`, o site continua no ar e pede a chave própria. O professor
(`CORDEL_ADMINS`) vê em `/admin` o gasto de cada conta, muda a cota, bloqueia e troca senhas.
Contas, sessões e usos ficam em `contas.sqlite3`, no volume de dados (`CORDEL_DADOS`).

**Narração** (`app/narracao.py`). Cada sextilha pode ser narrada pela ElevenLabs, com voz de
sotaque nordestino. Quem narra escolhe a voz no site (em Configurações ou ao lado do botão de
narrar), ouvindo a amostra de cada uma: a mesma estrofe, em `app/static/vozes/`. São 6 vozes da
biblioteca da ElevenLabs com sotaque nordestino declarado; as "de sotaque reforçado" usam o modelo
`eleven_v4` com a marcação `[strong Northeastern Brazilian accent, cordel reciter, rhythmic]`, e
as outras, o `eleven_v4_turbo` (metade do crédito). O padrão vem de `CORDEL_VOZ_PADRAO`
(`cicero-sotaque`). Enquanto o áudio toca, o cartaz destaca o verso e a palavra que estão sendo
ditos, pelo tempo de cada letra que a ElevenLabs devolve. A chave do professor (`ELEVENLABS_API_KEY`) só serve às contas de admin,
que também podem refazer uma narração; os outros põem a própria chave em Configurações (fica no
navegador e vai no cabeçalho `X-ElevenLabs-Key`, sem ser gravada). O MP3 fica em `narracao/`, no
volume: gerado uma vez, qualquer um ouve de graça, e sobrevive aos deploys. Os créditos de cada
narração ficam no caderno (`narracoes`) e aparecem em `/logs`, convertidos em dólar por
`CORDEL_ELEVEN_USD_POR_1K`.

**Música de fundo** (`app/musica.py`). Depois da narração, dá para criar uma música instrumental
pela Eleven Music, do tamanho da narração (até `CORDEL_MUSICA_MAX_SEGUNDOS`, 120 s), que toca
junto com ela a 25% do volume. Quem gera escolhe estilo, clima, andamento e instrumentos, ou deixa
"a IA escolhe" e o modelo decide pelo assunto. Custa ~15 créditos por segundo. As mesmas regras de
chave da narração valem aqui. Narração ou música refeitas não somem: vão para
`narracao/arquivo/` e aparecem em "gravações anteriores"; todas entram no custo em `/logs`.

**Configurações do site** (`/admin`, só admin): cadastro livre (sem convite), OpenAI para todos
(gerar sem conta, com a cota diária por IP), e ElevenLabs para todos, separada em voz e música.
Ficam no `contas.sqlite3`; o professor e os admins continuam podendo tudo.

**O gerador** mostra, durante a geração, uma barra fixa no topo com as etapas na horizontal, o que
a IA está fazendo e a porcentagem; o cartaz destaca a etapa atual. As etapas têm modo simplificado
e avançado, e a opção "seguir" rola sozinha para o que está acontecendo. No celular, o cartaz vem
antes e as etapas abrem por cima da página.

**Prioridade** (padrão: a notícia). Com "a notícia", o poema tem de contar sozinho os pontos
essenciais que a etapa do fato extrai, sem contar com a manchete. Desde 17/11 são 2 pontos
(1 estrofe), 3 (2 estrofes) ou 4 (3 ou mais), cada um com até 6 palavras, número arredondado e
sem sigla ou faixa. Métrica e rima seguem reprovando. O dicionário também: cada estrofe precisa
de pelo menos 2 termos diferentes, em qualquer verso; só a expressão por estrofe (regra 7) fica
como sugestão. O júri escolhe pela fidelidade antes da forma. Com "a forma", o dicionário reprova
como antes (um termo a cada 2 versos). Nas duas, o júri lista em `faltando` o ponto essencial que
não aparece de jeito nenhum no poema (ponto simplificado conta como presente), e isso dispara a
reescrita pelo sentido.

**Rodízio do dicionário.** Cada candidata recebe no prompt um sorteio de 25 palavras e 12
expressões, com peso menor para os termos que mais apareceram nas últimas 30 gerações, e a lista
dos mais gastos como "evite". O verificador continua aceitando o dicionário inteiro.

Em `/historico` ficam todas as sextilhas geradas (as que entraram e as de descarte),
cada uma no cartaz com a ficha dos parâmetros que a produziram: modelo, raciocínio,
candidatas, tipo de sextilha, estrofes, encadeamento, xilogravura, correções e custo.
Dá para filtrar e reabrir o gerador com os mesmos parâmetros.

Em `/logs` fica o custo de cada geração, estimado pelos tokens do caderno: por etapa,
com o `response_id` para abrir a chamada no painel da OpenAI.

O script não decide o que entra: o que ele marca com `?` aparece na tela e no JSON
como `duvidas_para_o_grupo`.
