import asyncio, json, random, sys
sys.path.insert(0, "/home/pedro/cordel-generator")
import ai, pydantic
from app import workflow as w
S = sys.argv[1]
r = [x for x in json.load(open(f"{S}/exp/resultados.json")) if x["cfg"] == "A"] + json.load(open(f"{S}/exp/resultados_ferramenta.json"))
noticias = {json.load(open(p))["fato"]["titulo"][:30]: json.load(open(p))["fato"]["fato"]
            for p in __import__("glob").glob("/home/pedro/cordel-generator/caderno/*.json")}

class Ranking(pydantic.BaseModel):
    ordem: list[str]
    fidelidade_problemas: list[str]
    comentario: str

SIS = """Você é júri de cordel. Receberá sextilhas anônimas sobre o mesmo fato.
Ordene da melhor para a pior considerando: fidelidade ao fato (erro factual pesa muito),
criatividade (imagem concreta, comparação com o mundo do cordel, surpresa), registro de
cordel, fluência oral, e virada no último verso. Liste em fidelidade_problemas os rótulos
que distorcem o fato e o quê."""

async def julgar(n, rodada):
    xs = [x for x in r if x["noticia"] == n and x["cfg"] in "AEF"]
    random.Random(rodada * 97 + len(n)).shuffle(xs)
    rot = {chr(80 + i): x["cfg"] for i, x in enumerate(xs)}  # P, Q, R
    corpo = "\n\n".join(f"Sextilha {k}:\n" + "\n".join(x["versos"]) for k, x in zip(rot, xs))
    rk = await w.gerar(SIS, f"Fato: {noticias.get(n, n)}\n\n{corpo}", Ranking, [])
    return n, [rot.get(k.strip()[-1], "?") for k in rk.ordem], [p for p in rk.fidelidade_problemas], rot

async def main():
    w.TEXT_MODEL, w.REASONING = "openai:gpt-5.5", "medium"
    ns = list(dict.fromkeys(x["noticia"] for x in r))
    res = await asyncio.gather(*(julgar(n, k) for n in ns for k in range(3)))
    pontos = {"A": 0, "E": 0, "F": 0}
    for n, ordem, prob, rot in res:
        for i, c in enumerate(ordem):
            if c in pontos: pontos[c] += 3 - i
        print(n, "->", " > ".join(ordem), "| problemas:", "; ".join(p for p in prob)[:200], "| rótulos:", rot)
    print("PONTOS (3=1º lugar):", pontos)
asyncio.run(main())
