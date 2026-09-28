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
