"""O dicionário nordestino (dados/dicionario_nordestino.csv) e as buscas nele.

Usado pelas regras do grupo: ≥1 termo a cada 2 versos (regra 3), uma expressão de
mais de uma palavra por estrofe (regra 7) e partícula fática só na ponta do verso
(regra 9). O texto do dicionário também vai no prompt, com o sentido de cada termo,
para o modelo usar o termo em contexto (regra 12).
"""

import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "dados" / "dicionario_nordestino.csv"

# "viu", "tá" e "sabe" também são verbos comuns ("o povo viu"); conferir a posição
# deles reprovaria versos normais. Só as inequívocas têm a posição verificada.
FATICAS_VERIFICADAS = {"ne", "visse"}


def normalizar(texto: str) -> str:
    """minúsculas, sem acento, hífen e pontuação viram espaço."""
    s = unicodedata.normalize("NFD", texto.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _flexoes(forma: str) -> set[str]:
    """Plural e gênero simples de uma palavra solta (arretado -> arretada, arretados...)."""
    f = {forma}
    if " " in forma:
        return f
    if forma.endswith("o"):
        f |= {forma[:-1] + "a", forma + "s", forma[:-1] + "as"}
    elif forma.endswith("a"):
        f |= {forma + "s"}
    elif forma[-1:] in "eiu":
        f |= {forma + "s"}
    return f


@lru_cache(maxsize=1)
def carregar() -> tuple[dict, ...]:
    linhas = [l for l in ARQUIVO.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    termos = []
    for r in csv.DictReader(linhas):
        formas = {normalizar(x) for x in [r["termo"], *r["variantes"].split("|")] if x.strip()}
        formas = set().union(*(_flexoes(x) for x in formas))
        termos.append({**r, "formas": frozenset(formas)})
    return tuple(termos)


def termos_no_verso(verso: str, tipos=("palavra", "expressao")) -> list[str]:
    """Os termos do dicionário presentes no verso (palavra ou expressão inteira)."""
    alvo = f" {normalizar(verso)} "
    return [t["termo"] for t in carregar()
            if t["tipo"] in tipos and any(f" {f} " in alvo for f in t["formas"])]


def faticas_fora_da_ponta(verso: str) -> list[str]:
    """Partículas fáticas inequívocas que não estão na 1ª nem na última palavra."""
    palavras = normalizar(verso).split()
    return [p for i, p in enumerate(palavras) if p in FATICAS_VERIFICADAS and 0 < i < len(palavras) - 1]


def texto_para_prompt() -> str:
    """O dicionário como lista para o prompt: 'termo — sentido', por tipo."""
    blocos = []
    for tipo, titulo in [("palavra", "Palavras"), ("expressao", "Expressões (mais de uma palavra)"),
                         ("fatica", "Partículas fáticas (só no início ou no fim do verso)")]:
        itens = [f"- {t['termo']} — {t['sentido']}" for t in carregar() if t["tipo"] == tipo]
        blocos.append(f"{titulo}:\n" + "\n".join(itens))
    return "\n\n".join(blocos)


# ---- rodízio: sem ele, o Poeta voltava sempre aos mesmos termos ("terreiro", "magote").
# Cada candidata vê no prompt só um sorteio do dicionário, em que quem apareceu muito nas
# últimas gerações tem menos chance; o verificador continua aceitando o dicionário inteiro.
SORTEIO = {"palavra": 25, "expressao": 12}


def usos_recentes(estrofes_por_geracao) -> dict[str, int]:
    """Quantas vezes cada termo apareceu nos poemas dados (uma lista de poemas)."""
    usos: dict[str, int] = {}
    for estrofes in estrofes_por_geracao:
        for vs in estrofes or []:
            for v in vs:
                for t in termos_no_verso(v):
                    usos[t] = usos.get(t, 0) + 1
    return usos


def sortear(usos: dict[str, int], rng) -> dict:
    """Um sorteio sem repetição, com peso 1/(1+usos), por tipo. As fáticas vão todas."""
    escolhidos = {}
    for tipo, k in SORTEIO.items():
        pool = [t for t in carregar() if t["tipo"] == tipo]
        # amostragem ponderada sem reposição (Efraimidis-Spirakis): chave = u^(1/peso)
        chave = {t["termo"]: rng.random() ** (1 + usos.get(t["termo"], 0)) for t in pool}
        escolhidos[tipo] = sorted(pool, key=lambda t: -chave[t["termo"]])[:k]
    gastos = [t for t, n in sorted(usos.items(), key=lambda x: -x[1]) if n >= 2][:8]
    return {"termos": [t["termo"] for ts in escolhidos.values() for t in ts], "evitar": gastos,
            "texto": _texto(escolhidos, gastos)}


def _texto(escolhidos: dict, gastos: list[str]) -> str:
    blocos = []
    for tipo, titulo in [("palavra", "Palavras"), ("expressao", "Expressões (mais de uma palavra)")]:
        blocos.append(f"{titulo}:\n" + "\n".join(f"- {t['termo']} — {t['sentido']}" for t in escolhidos[tipo]))
    faticas = [t for t in carregar() if t["tipo"] == "fatica"]
    blocos.append("Partículas fáticas (só no início ou no fim do verso):\n"
                  + "\n".join(f"- {t['termo']} — {t['sentido']}" for t in faticas))
    texto = ("Para esta geração, foram sorteados estes termos do dicionário. Use os daqui; "
             "variar é parte do trabalho.\n\n" + "\n\n".join(blocos))
    if gastos:
        texto += ("\n\nJá apareceram demais nas últimas gerações, evite: " + ", ".join(gastos) + ".")
    return texto
