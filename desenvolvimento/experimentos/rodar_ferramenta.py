"""Compara configurações de modelo/raciocínio no pipeline de texto (sem imagem)."""
import asyncio, json, os, sys
from pathlib import Path
EXP = Path(sys.argv[1]); os.environ["CORDEL_DADOS"] = str(EXP / "dados")
sys.path.insert(0, "/home/pedro/cordel-generator")
from app import workflow as w

PRECO = {"openai:gpt-5.5": (5.0, 30.0), "openai:gpt-5.4-mini": (0.75, 4.5)}
CONFIGS = {"E": ("openai:gpt-5.5", "medium", True), "F": ("openai:gpt-5.5", "low", True)}
cad = Path("/home/pedro/cordel-generator/caderno")
noticias = {}
for f in sorted(cad.glob("*.json")):
    d = json.load(open(f)); n = d.get("noticia", "")
    chave = d["fato"]["titulo"][:30]
    if n and not any(n[:200] == v[:200] for v in noticias.values()):
        noticias[chave] = n
print(len(noticias), "notícias:", list(noticias))

async def rodar(cfg, nome, texto):
    # gerar() lê as globais do módulo a cada chamada; as tarefas de uma config rodam juntas
    fim = None
    async for ev in w.run_cordel(texto, "", False):
        if ev["etapa"] == "fim": fim = ev
    log = json.load(open(EXP / "dados" / fim["arquivos"]["caderno"]))
    modelo = CONFIGS[cfg][0]; pi, po = PRECO[modelo]
    tin = sum((c.get("tokens") or {}).get("input_tokens") or 0 for c in log["chamadas"])
    tout = sum((c.get("tokens") or {}).get("output_tokens") or 0 for c in log["chamadas"])
    seg = sum(c["segundos"] for c in log["chamadas"])
    return {"cfg": cfg, "noticia": nome, "entra": fim["entra"], "rodadas": fim["rodadas"],
            "candidatas_passaram": sum(c["entra"] for c in log["candidatas"]),
            "custo": tin / 1e6 * pi + tout / 1e6 * po, "tin": tin, "tout": tout, "seg": seg,
            "versos": fim["versos"], "manchete": fim["titulo"],
            "medicoes": sum(c.get("medicoes_no_verificador", 0) for c in log["chamadas"])}

async def main():
    res = []
    for cfg, (modelo, esforco, ferr) in CONFIGS.items():
        w.TEXT_MODEL, w.REASONING, w.FERRAMENTA = modelo, esforco, ferr
        r = await asyncio.gather(*(rodar(cfg, n, t) for n, t in noticias.items()), return_exceptions=True)
        for x in r:
            if isinstance(x, Exception): print(cfg, "ERRO", x); continue
            res.append(x)
        ok = [x for x in r if not isinstance(x, Exception)]
        print(f"{cfg} {modelo} {esforco}: custo médio ${sum(x['custo'] for x in ok)/len(ok):.3f} "
              f"entra {sum(x['entra'] for x in ok)}/{len(ok)} rodadas {sum(x['rodadas'] for x in ok)} "
              f"cand.passaram {sum(x['candidatas_passaram'] for x in ok)}/{3*len(ok)} "
              f"medições {sum(x['medicoes'] for x in ok)} tempo médio {sum(x['seg'] for x in ok)/len(ok):.0f}s", flush=True)
    json.dump(res, open(EXP / "resultados_ferramenta.json", "w"), ensure_ascii=False, indent=1)
asyncio.run(main())
