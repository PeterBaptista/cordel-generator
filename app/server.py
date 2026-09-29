"""Mini servidor para testar o gerador: uv run uvicorn app.server:app --reload"""

import base64
import json
import os
import secrets
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import cadernos, custos, prompts
from .workflow import ECONOMICO, IMAGENS, MAX_RODADAS, OPCOES, PASTAS, RAIZ, Config, run_cordel

app = FastAPI(title="Do 7 ao 6")

# No ar, cada folheto gasta a chave da OpenAI: com CORDEL_SENHA definida, o gerador,
# o histórico, os logs e os cadernos pedem senha (HTTP Basic, qualquer usuário). A home
# com a coleção fica aberta: é o link da entrega. Sem CORDEL_SENHA, tudo aberto (uso local).
SENHA = os.getenv("CORDEL_SENHA", "")
PUBLICO = {"/", "/saude", "/api/colecao", "/static/home.html", "/static/folheto.css", "/static/folheto.js",
           "/static/Do7ao6.pdf"}
PUBLICO_PREFIXOS = ("/folhetos/", "/descarte/")  # os textos e imagens da coleção e do descarte

# Quais folhetos aparecem na coleção da home, na ordem: ids dos cadernos separados por
# vírgula (ex.: 20260928-154345-amador-resolve-desafio-matematico-com-ia). Vazio: todos
# os que passaram no verificador.
COLECAO = [i.strip() for i in os.getenv("CORDEL_COLECAO", "").split(",") if i.strip()]


def publico(caminho: str) -> bool:
    return caminho in PUBLICO or caminho.startswith(PUBLICO_PREFIXOS)


@app.middleware("http")
async def exigir_senha(request: Request, call_next):
    if SENHA and not publico(request.url.path):
        auth = request.headers.get("authorization", "")
        try:
            _, _, dada = base64.b64decode(auth.removeprefix("Basic ")).decode().partition(":")
        except ValueError:
            dada = ""
        if not (auth.startswith("Basic ") and secrets.compare_digest(dada, SENHA)):
            return Response(status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Noticias em Cordel"'})
    return await call_next(request)
app.mount("/static", StaticFiles(directory=RAIZ / "app" / "static"), name="static")
for nome, pasta in PASTAS.items():
    pasta.mkdir(parents=True, exist_ok=True)
    app.mount(f"/{nome}", StaticFiles(directory=pasta), name=nome)


class Pedido(BaseModel):
    noticia: str = ""
    url: str = ""
    com_imagem: bool = True
    config: dict = {}


@app.get("/")
def home():
    return FileResponse(RAIZ / "app" / "static" / "home.html")


@app.get("/gerador")
def gerador():
    return FileResponse(RAIZ / "app" / "static" / "index.html")


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
            "manchete": fato.get("titulo") or f.stem,
            "estrofes": cadernos.estrofes(log, "estrofes_finais"),
            "imagem": arq.get("imagem"), "texto": arq.get("texto"),
            "url": log.get("url"), "fonte": log.get("fonte"),
            "motivo": log.get("motivo"), "rodadas": log.get("rodadas_de_correcao"),
            "forma": {k: cfg.get(k) for k in ("forma", "estrofes", "encadeamento", "narrador")},
        })
    entraram = [i for i in itens if i["entra"]]
    if COLECAO:
        por_id = {i["id"]: i for i in entraram}
        entraram = [por_id[i] for i in COLECAO if i in por_id]
    else:
        entraram.sort(key=lambda i: i["inicio"] or "")
    return {"colecao": entraram, "descarte": [i for i in itens if not i["entra"]],
            "curada": bool(COLECAO)}


@app.get("/logs")
def logs_pagina():
    return FileResponse(RAIZ / "app" / "static" / "logs.html")


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
    return FileResponse(RAIZ / "app" / "static" / "historico.html")


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
            "id": f.stem, "inicio": cadernos.hora(log.get("inicio")),
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
    async def eventos():
        try:
            cfg = Config(**{k: v for k, v in pedido.config.items() if k in OPCOES})
            async for ev in run_cordel(pedido.noticia, pedido.url, pedido.com_imagem, cfg):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            traceback.print_exc()
            yield f"data: {json.dumps({'etapa': 'erro', 'erro': f'{type(e).__name__}: {e}'})}\n\n"

    return StreamingResponse(eventos(), media_type="text/event-stream")
