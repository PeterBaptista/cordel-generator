"""Mini servidor para testar o gerador: uv run uvicorn app.server:app --reload"""

import base64
import json
import re
from datetime import datetime
import os
import secrets
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import custos, prompts
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


def _cadernos():
    """Os cadernos de bordo, do mais novo ao mais antigo."""
    for f in sorted(PASTAS["caderno"].glob("*.json"), reverse=True):
        try:
            yield f, json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue


def _config(log: dict) -> tuple[dict, bool]:
    """Os parâmetros da geração. Cadernos anteriores aos seletores não os guardavam:
    aí deduz das chamadas registradas e avisa (segundo valor = deduzida)."""
    if log.get("config"):
        # configs de antes dos tipos de sextilha: só existia 1 estrofe aberta e livre
        return {"forma": "aberta", "estrofes": 1, "encadeamento": "livre", **log["config"]}, False
    chamadas = log.get("chamadas", [])
    texto = next((c for c in chamadas if "image_generation" not in c.get("modelo", "")), {})
    xilo = next((c for c in chamadas if "image_generation" in c.get("modelo", "")), None)
    qualidade = None
    if xilo:
        m = re.search(r"image_generation\([^,)]+, (\w+)\)", xilo["modelo"])
        qualidade = m.group(1) if m else "medium"  # antes do seletor, era sempre medium
    return {"texto": texto.get("modelo"), "raciocinio": texto.get("reasoning_effort"),
            "candidatas": len(log.get("candidatas") or []) or 1, "imagem_qualidade": qualidade,
            "forma": "aberta", "estrofes": 1, "encadeamento": "livre",
            "com_imagem": xilo is not None}, True


def _hora(iso: str | None) -> str | None:
    """Cadernos antigos guardavam a hora sem fuso, no relógio da máquina que os
    escreveu (esta mesma): completa com o fuso daqui para o navegador converter."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).astimezone().isoformat(timespec="seconds")
    except ValueError:
        return iso


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
        config, _ = _config(log)
        geracoes.append({
            "id": f.stem, "inicio": _hora(log.get("inicio")), "fim": _hora(log.get("fim")),
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
        config, deduzida = _config(log)
        fato = log.get("fato") or {}
        # antes das várias estrofes, o caderno guardava uma lista plana de versos
        estrofes = log.get("estrofes_finais") or ([log["versos_finais"]] if log.get("versos_finais") else [])
        escolhida = (log.get("escolhida") or {}).get("indice")
        candidatas = log.get("candidatas") or []
        itens.append({
            "id": f.stem, "inicio": _hora(log.get("inicio")),
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
    return {"padrao": asdict(Config()), "opcoes": OPCOES, "imagem": IMAGE_MODEL,
            "precos": {m: {"entrada": e, "saida": o} for m, (e, _, o) in custos.PRECOS.items()},
            "formas": {nome: {"esquema": esq, "regra": regra} for nome, (esq, regra) in prompts.FORMAS.items()}}


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
