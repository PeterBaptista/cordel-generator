"""Mini servidor para testar o gerador: uv run uvicorn app.server:app --reload"""

import json
import os
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import cadernos, criacomp, custos, dicionario, prompts
from .workflow import ECONOMICO, IMAGENS, MAX_RODADAS, OPCOES, PASTAS, RAIZ, Config, run_cordel

app = FastAPI(title="Do 7 ao 6")

# Quantas gerações aparecem no cordão da home; as outras ficam em /sextilhas.
ULTIMAS = 10




class SemCacheVelho(StaticFiles):
    """O navegador confere com o servidor antes de reusar: assim ninguém fica com o script antigo."""
    async def get_response(self, path, scope):
        resposta = await super().get_response(path, scope)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta


def pagina(nome: str) -> FileResponse:
    return FileResponse(RAIZ / "app" / "static" / nome, headers={"Cache-Control": "no-cache"})


app.mount("/static", SemCacheVelho(directory=RAIZ / "app" / "static"), name="static")
for nome, pasta in PASTAS.items():
    pasta.mkdir(parents=True, exist_ok=True)
    app.mount(f"/{nome}", StaticFiles(directory=pasta), name=nome)


class Pedido(BaseModel):
    autor: str = ""
    noticia: str = ""
    url: str = ""
    com_imagem: bool = True
    config: dict = {}


@app.get("/")
def home():
    return pagina("home.html")


@app.get("/gerador")
def gerador():
    return pagina("index.html")


@app.get("/sextilhas")
def sextilhas():
    return pagina("sextilhas.html")


@app.get("/api/dicionario")
def dicionario_publico():
    """Os termos que a página marca nos versos, com o sentido de cada um. "viu", "tá" e
    "sabe" ficam de fora: quase sempre são só os verbos comuns."""
    return [{"termo": t["termo"], "sentido": t["sentido"], "formas": sorted(t["formas"])}
            for t in dicionario.carregar()
            if t["tipo"] != "fatica" or dicionario.normalizar(t["termo"]) in dicionario.FATICAS_VERIFICADAS]


@app.get("/saude")
def saude():
    return {"ok": True}


@app.get("/api/colecao")
def colecao():
    """O que a home pública mostra: só texto, imagem e forma, sem prompts nem custos."""
    itens = []
    for f, log in _cadernos():
        cfg, _ = cadernos.config(log)
        arq = log.get("arquivos") or {}
        if not arq.get("texto") or not (PASTAS["caderno"].parent / arq["texto"]).exists():
            continue
        fato = log.get("fato") or {}
        itens.append({
            "id": f.stem, "inicio": cadernos.hora(log.get("inicio")), "entra": bool(log.get("entra")),
            "autor": log.get("autor"),
            "manchete": fato.get("titulo") or f.stem,
            "estrofes": cadernos.estrofes(log, "estrofes_finais"),
            "imagem": arq.get("imagem"), "texto": arq.get("texto"),
            "url": log.get("url"), "fonte": log.get("fonte"),
            "motivo": log.get("motivo"), "rodadas": log.get("rodadas_de_correcao"),
            "forma": {k: cfg.get(k) for k in ("forma", "estrofes", "encadeamento", "narrador")},
        })
    # o que o grupo gerou segue o eixo: só notícias do CriaComp News, e da mesma notícia
    # fica a versão mais recente. O que a turma gera entra sempre, com o nome de quem gerou.
    grupo = [i for i in itens if not i["autor"] and criacomp.tem(i["url"])]
    recentes = {}
    for i in sorted((i for i in grupo if i["entra"]), key=lambda i: i["inicio"] or ""):
        recentes[criacomp.normalizar(i["url"])] = i
    turma = [i for i in itens if i["autor"] and i["entra"]]
    ultimas = sorted([*recentes.values(), *turma], key=lambda i: i["inicio"] or "", reverse=True)[:ULTIMAS]
    descarte = sorted((i for i in grupo if not i["entra"]), key=lambda i: i["inicio"] or "", reverse=True)
    return {"colecao": ultimas, "descarte": descarte}


@app.get("/logs")
def logs_pagina():
    return pagina("logs.html")


def _cadernos():
    return cadernos.ler(PASTAS["caderno"])


def _arquivos(f, log: dict) -> dict:
    return {**(log.get("arquivos") or {}), "caderno": f"caderno/{f.name}"}


@app.get("/api/logs")
def logs():
    """Uma linha por geração, com o custo recalculado a partir dos tokens do caderno."""
    geracoes = []
    for f, log in _cadernos():
        custo = custos.resumo(log)
        chamadas = []
        for c, cc in zip(log.get("chamadas", []), custo["chamadas"]):
            t = c.get("tokens") or {}
            chamadas.append({
                "etapa": cc["etapa"], "modelo": c.get("modelo", ""),
                "entrada": t.get("input_tokens"), "saida": t.get("output_tokens"),
                "raciocinio": t.get("reasoning_tokens"), "imagem": c.get("tokens_imagem"),
                "custo": cc["total"], "imagem_medida": cc["imagem_medida"],
                "segundos": c.get("segundos"), "response_id": c.get("response_id"),
            })
        config, _ = cadernos.config(log)
        geracoes.append({
            "id": f.stem, "inicio": cadernos.hora(log.get("inicio")), "fim": cadernos.hora(log.get("fim")),
            "config": config,
            "manchete": (log.get("fato") or {}).get("titulo") or f.stem,
            "url": log.get("url"), "entra": log.get("entra"),
            "rodadas": log.get("rodadas_de_correcao"),
            "candidatas": len(log.get("candidatas") or []) or 1,
            "texto": custo["texto"], "imagem": custo["imagem"], "total": custo["total"],
            "imagem_medida": custo["imagem_medida"], "tem_imagem": custo["tem_imagem"],
            "chamadas": chamadas,
            "arquivos": _arquivos(f, log),
        })
    return {"geracoes": geracoes, "precos_conferidos_em": "28/09/2026"}


@app.get("/historico")
def historico_pagina():
    return pagina("historico.html")


@app.get("/api/historico")
def historico():
    """As sextilhas geradas, com os parâmetros que as produziram."""
    itens = []
    for f, log in _cadernos():
        config, deduzida = cadernos.config(log)
        fato = log.get("fato") or {}
        # antes das várias estrofes, o caderno guardava uma lista plana de versos
        estrofes = log.get("estrofes_finais") or ([log["versos_finais"]] if log.get("versos_finais") else [])
        escolhida = (log.get("escolhida") or {}).get("indice")
        candidatas = log.get("candidatas") or []
        itens.append({
            "id": f.stem, "inicio": cadernos.hora(log.get("inicio")), "autor": log.get("autor"),
            "manchete": fato.get("titulo") or f.stem, "fato": fato.get("fato"),
            "url": log.get("url"), "fonte": log.get("fonte"), "origem": log.get("origem"),
            "config": config, "config_deduzida": deduzida,
            "estrofes": estrofes, "entra": log.get("entra"), "motivo": log.get("motivo"),
            "rodadas": log.get("rodadas_de_correcao"), "duvidas": log.get("duvidas_para_o_grupo") or [],
            "angulo": candidatas[escolhida]["angulo"] if escolhida is not None and escolhida < len(candidatas) else None,
            "justificativa": (log.get("escolhida") or {}).get("justificativa"),
            "custo": custos.resumo(log)["total"],
            "arquivos": _arquivos(f, log),
        })
    return {"itens": itens}


@app.get("/api/config")
def config():
    from dataclasses import asdict
    return {"padrao": asdict(Config()), "economico": ECONOMICO, "opcoes": OPCOES, "max_rodadas": MAX_RODADAS,
            "imagens": {k: {"modelo": m, "qualidade": q} for k, (m, q) in IMAGENS.items()},
            "precos": {m: {"entrada": e, "saida": o} for m, (e, _, o) in custos.PRECOS.items()},
            "formas": {nome: {"esquema": esq, "regra": regra} for nome, (esq, regra) in prompts.FORMAS.items()},
            "narradores": prompts.NARRADORES}


@app.post("/api/cordel")
async def cordel(pedido: Pedido):
    autor = " ".join(pedido.autor.split())
    if not autor or len(autor) > 60:
        raise HTTPException(422, "Coloque seu nome (até 60 caracteres) para gerar.")

    async def eventos():
        try:
            cfg = Config(**{k: v for k, v in pedido.config.items() if k in OPCOES})
            async for ev in run_cordel(pedido.noticia, pedido.url, pedido.com_imagem, cfg, autor):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            traceback.print_exc()
            yield f"data: {json.dumps({'etapa': 'erro', 'erro': f'{type(e).__name__}: {e}'})}\n\n"

    return StreamingResponse(eventos(), media_type="text/event-stream")
