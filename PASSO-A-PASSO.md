# Passo a passo — do zero à entrega

**Hoje é segunda, 28/09.** O PA 1 venceu em 24/09 e o bloco fecha em 01/10.
Este plano cabe em dois dias.

---

## Passo 0 — Antes de tudo, falem com o professor (10 min, hoje)

Mensagem curta no Classroom: onde vocês estão, que o eixo está fechado, que a
coleção está em produção, e a pergunta de como ele quer tratar a entrega atrasada.
Confirmem também em qual data vocês apresentam, 29/09 ou 01/10.

Façam isso **antes** de produzir. A resposta pode mudar o tamanho da coleção.

---

## Passo 1 — Montar a pasta (5 min)

Descompacte o material e crie um repositório no GitHub:

```
projeto-autoral/
├── README.md              <- o eixo, em uma página
├── EIXO.md
├── CADERNO-DE-BORDO.md
├── scripts/escandir.py
├── folhetos/              <- os 5 artefatos que entram
└── descarte/              <- tudo que ficou de fora, com o motivo
```

```bash
git init && git add -A && git commit -m "projeto autoral: estrutura e verificador"
```

O repositório público resolve a hospedagem que o Classroom pede.

---

## Passo 2 — Testar o verificador (2 min)

Não precisa instalar nada. É Python puro, sem nenhuma dependência externa, e roda
offline — o que também satisfaz a regra da disciplina de não depender de ferramenta paga.

```bash
python3 scripts/escandir.py --verso "O robô chegou na feira"
python3 scripts/escandir.py folhetos/exemplo-teste.txt descarte/exemplo-descartado.txt
```

O primeiro comando mostra a escansão de um verso. O segundo mostra uma sextilha que
passa e uma que é descartada, para vocês reconhecerem os dois relatórios.

**Apaguem os dois arquivos de exemplo antes de entregar.** Eles são meus, de teste,
e não fazem parte da coleção de vocês.

---

## Passo 3 — Escolher as 5 notícias (30 min, hoje)

Do arquivo `2026-2-NEWS.md` do repositório da disciplina, que é a lista curada de
links discutidos em aula. Usar essa fonte amarra a coleção à disciplina e já dá
resposta pronta para "por que estas notícias".

Anotem, para cada uma, **por que ela entrou**. Uma linha basta. E guardem duas ou três
notícias que vocês consideraram e descartaram: isso também é descarte.

---

## Passo 4 — Instalar a skill e gerar (o resto de hoje)

**No Claude Code:**
```bash
mkdir -p .claude/skills/escandir-sextilha
cp SKILL.md .claude/skills/escandir-sextilha/
```

**No OpenCode:**
```bash
mkdir -p .agents/skills/escandir-sextilha
cp SKILL.md .agents/skills/escandir-sextilha/
```

**Em qualquer chat, sem instalar nada:** cole o conteúdo do `SKILL.md` como primeira
mensagem da conversa. Funciona igual, e é assim que as skills do professor também
foram escritas para funcionar.

Depois, um folheto por vez:

```bash
python3 scripts/escandir.py folhetos/noticia-01.txt
```

**Regra de ouro:** corrija **só o verso reprovado**. O verso que passou já está certo,
e refazer a estrofe inteira costuma quebrá-lo.

**Guardem tudo desde o primeiro prompt.** O caderno de bordo é impossível de
reconstruir depois, e é onde a nota se separa. Preencham enquanto geram, não no fim.

---

## Passo 5 — Fechar o descarte (30 min, amanhã)

Cada arquivo em `descarte/` ganha uma linha de motivo no topo:

```
# DESCARTADA: verso 4 com 6 sílabas, resistiu a 3 rodadas de correção.
# DESCARTADA: rima B quebrou — "nova" não rima com "decisão".
# DESCARTADA: notícia abstrata demais, não virou acontecimento narrável.
```

Guardem também o **caso de fronteira**: a estrofe que quase entrou. É ali que o
critério de vocês fica visível. Grupo que aproveita tudo costuma não ter eixo nenhum.

---

## Passo 6 — Rodar a verificação final e gerar o relatório (10 min)

```bash
python3 scripts/escandir.py folhetos/*.txt --csv caderno/metrica.csv
```

O CSV com verso, contagem e escansão de cada linha é uma prova objetiva de que a
restrição foi aplicada. Anexem ao caderno de bordo.

---

## Passo 7 — Entregar (20 min)

Confiram os cinco itens do PA 1 antes de enviar:

- [ ] **A coleção** — os 5 folhetos, do jeito que vocês querem que sejam vistos
- [ ] **O eixo declarado** — um parágrafo, reescrito com as palavras de vocês
- [ ] **O descarte comentado** — o que ficou de fora e por qual critério
- [ ] **O caderno de bordo** — prompts na íntegra, sementes, parâmetros, encadeamento,
      o que foi feito na mão, e as quatro linhas sobre as skills
- [ ] **O material da apresentação** — os slides, mesmo que vocês só apresentem depois

Entrega pelo Classroom, com o link do repositório. A Galeria é só do Portfólio
individual e não recebe projeto de grupo.

---

## Passo 8 — Na apresentação

Levem uma **gravação de tela** da demonstração como reserva. Rodar o verificador ao
vivo, mostrando um folheto sendo reprovado e corrigido, é a demonstração mais forte
que vocês têm: mostra a restrição funcionando, e não só declarada.

E preparem a resposta para a pergunta óbvia: *"a métrica é uma restrição da forma, mas
o que nela é de vocês e não de qualquer grupo que escolhesse cordel?"*

---

## Um extra que pode valer nota

O professor diz que **pull request aceito no repositório da disciplina conta como
Experimento no Portfólio**, desde que venha com a Peça correspondente: o que você quis
mudar, o que testou, o que aconteceu, o que aprendeu.

Um verificador de escansão em português é exatamente o tipo de coisa que cabe na pasta
`skills/`. Isso é individual, não do grupo — e é uma nota a mais por um trabalho que
vocês já vão ter feito.
