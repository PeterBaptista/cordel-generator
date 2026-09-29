"""Leitura dos cadernos de bordo (caderno/*.json), compartilhada pelo servidor
(histórico e logs) e pelo scripts/caderno.py, que gera o registro em Markdown.
Não depende do FastAPI nem da chave da OpenAI."""

import json
import re
from datetime import datetime
from pathlib import Path


def ler(pasta: Path):
    """Os cadernos de bordo de uma pasta, do mais novo ao mais antigo."""
    for f in sorted(pasta.glob("*.json"), reverse=True):
        try:
            yield f, json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue


def config(log: dict) -> tuple[dict, bool]:
    """Os parâmetros da geração. Cadernos anteriores aos seletores não os guardavam:
    aí deduz das chamadas registradas e avisa (segundo valor = deduzida)."""
    if log.get("config"):
        # configs de antes dos tipos de sextilha: só existia 1 estrofe aberta e livre
        return {"forma": "aberta", "estrofes": 1, "encadeamento": "livre", "narrador": "sortear",
                **log["config"]}, False
    chamadas = log.get("chamadas", [])
    texto = next((c for c in chamadas if "image_generation" not in c.get("modelo", "")), {})
    xilo = next((c for c in chamadas if "image_generation" in c.get("modelo", "")), None)
    qualidade = None
    if xilo:
        m = re.search(r"image_generation\([^,)]+, (\w+)\)", xilo["modelo"])
        qualidade = m.group(1) if m else "medium"  # antes do seletor, era sempre medium
    return {"texto": texto.get("modelo"), "raciocinio": texto.get("reasoning_effort"),
            "candidatas": len(log.get("candidatas") or []) or 1, "imagem_qualidade": qualidade,
            "forma": "aberta", "estrofes": 1, "encadeamento": "livre", "narrador": "sortear",
            "com_imagem": xilo is not None}, True


def hora(iso: str | None) -> str | None:
    """Cadernos antigos guardavam a hora sem fuso, no relógio da máquina que os
    escreveu (esta mesma): completa com o fuso daqui para o navegador converter."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).astimezone().isoformat(timespec="seconds")
    except ValueError:
        return iso


def estrofes(obj: dict, chave: str = "estrofes") -> list[list[str]]:
    """Antes das várias estrofes, os cadernos guardavam uma lista plana de versos."""
    if obj.get(chave):
        return obj[chave]
    plano = obj.get("versos") or obj.get("versos_finais")
    return [plano] if plano else []
