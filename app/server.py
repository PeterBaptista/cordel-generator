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

from .workflow import IMAGE_MODEL, PASTAS, RAIZ, TEXT_MODEL, run_cordel

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


@app.get("/")
def index():
    return FileResponse(RAIZ / "app" / "static" / "index.html")


@app.get("/saude")
def saude():
    return {"ok": True}


@app.get("/api/config")
def config():
    return {"texto": TEXT_MODEL, "imagem": IMAGE_MODEL}


@app.post("/api/cordel")
async def cordel(pedido: Pedido):
    async def eventos():
        try:
            async for ev in run_cordel(pedido.noticia, pedido.url, pedido.com_imagem):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            traceback.print_exc()
            yield f"data: {json.dumps({'etapa': 'erro', 'erro': f'{type(e).__name__}: {e}'})}\n\n"

    return StreamingResponse(eventos(), media_type="text/event-stream")
