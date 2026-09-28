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

from . import custos
from .workflow import IMAGE_MODEL, OPCOES, PASTAS, RAIZ, Config, run_cordel

app = FastAPI(title="Do 7 ao 6")

# No ar, cada folheto gasta a chave da OpenAI: com CORDEL_SENHA definida,
# a página pede senha (HTTP Basic, qualquer usuário). Sem ela, fica aberta (uso local).
SENHA = os.getenv("CORDEL_SENHA", "")


@app.middleware("http")
async def exigir_senha(request: Request, call_next):
    if SENHA and request.url.path != "/saude":
        auth = request.headers.get("authorization", "")
        try:
            _, _, dada = base64.b64decode(auth.removeprefix("Basic ")).decode().partition(":")
        except ValueError:
            dada = ""
        if not (auth.startswith("Basic ") and secrets.compare_digest(dada, SENHA)):
            return Response(status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Noticias em Cordel"'})
    return await call_next(request)
for nome, pasta in PASTAS.items():
    pasta.mkdir(parents=True, exist_ok=True)
    app.mount(f"/{nome}", StaticFiles(directory=pasta), name=nome)


class Pedido(BaseModel):
    noticia: str = ""
    url: str = ""
    com_imagem: bool = True
    config: dict = {}


@app.get("/")
def index():
    return FileResponse(RAIZ / "app" / "static" / "index.html")


@app.get("/saude")
def saude():
    return {"ok": True}


@app.get("/logs")
def logs_pagina():
    return FileResponse(RAIZ / "app" / "static" / "logs.html")


@app.get("/api/logs")
def logs():
    """Uma linha por geração, com o custo recalculado a partir dos tokens do caderno."""
    geracoes = []
    for f in sorted(PASTAS["caderno"].glob("*.json"), reverse=True):
        try:
            log = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
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
        arquivos = log.get("arquivos") or {}
        # cadernos anteriores aos seletores não guardavam a config: deduz das chamadas
        texto = next((c for c in log.get("chamadas", []) if "image_generation" not in c.get("modelo", "")), {})
        config = log.get("config") or {"texto": texto.get("modelo"), "raciocinio": texto.get("reasoning_effort")}
        geracoes.append({
            "id": f.stem, "inicio": log.get("inicio"), "fim": log.get("fim"),
            "config": config,
            "manchete": (log.get("fato") or {}).get("titulo") or f.stem,
            "url": log.get("url"), "entra": log.get("entra"),
            "rodadas": log.get("rodadas_de_correcao"),
            "candidatas": len(log.get("candidatas") or []) or 1,
            "texto": custo["texto"], "imagem": custo["imagem"], "total": custo["total"],
            "imagem_medida": custo["imagem_medida"], "tem_imagem": custo["tem_imagem"],
            "chamadas": chamadas,
            "arquivos": {**arquivos, "caderno": f"caderno/{f.name}"},
        })
    return {"geracoes": geracoes, "precos_conferidos_em": "28/09/2026"}


@app.get("/api/config")
def config():
    from dataclasses import asdict
    return {"padrao": asdict(Config()), "opcoes": OPCOES, "imagem": IMAGE_MODEL,
            "precos": {m: {"entrada": e, "saida": o} for m, (e, _, o) in custos.PRECOS.items()}}


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
