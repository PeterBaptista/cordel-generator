"""A lista de notícias do CriaComp News (o eixo: a coleção só usa notícias dela).

Lê a lista do repositório da disciplina e guarda por uma hora; se o GitHub não
responder, usa a cópia em dados/criacomp_2026-2-NEWS.md.
"""

import re
import time
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/filipecalegario/criacomp/main/2026-2-NEWS.md"
COPIA = Path(__file__).resolve().parent.parent / "dados" / "criacomp_2026-2-NEWS.md"
VALIDADE = 3600
_cache: dict = {"quando": 0.0, "links": frozenset()}


def normalizar(url: str | None) -> str:
    """Compara links sem parâmetros, barra final, maiúsculas nem o sufixo .amp."""
    u = re.sub(r"[?#].*$", "", url or "").rstrip("/").lower()
    return re.sub(r"\.amp$", "", u)


def _extrair(texto: str) -> frozenset:
    return frozenset(normalizar(u) for u in re.findall(r"\((https?://[^)\s]+)\)", texto))


def links() -> frozenset:
    if time.time() - _cache["quando"] < VALIDADE and _cache["links"]:
        return _cache["links"]
    try:
        texto = urllib.request.urlopen(URL, timeout=5).read().decode("utf-8")
        _cache.update(quando=time.time(), links=_extrair(texto))
    except OSError:
        _cache.update(quando=time.time(), links=_extrair(COPIA.read_text(encoding="utf-8")))
    return _cache["links"]


def tem(url: str | None) -> bool:
    return bool(url) and normalizar(url) in links()
