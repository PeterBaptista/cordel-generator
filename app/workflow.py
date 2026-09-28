"""O laço do SKILL.md, automatizado com o AI SDK para Python.

notícia -> fato -> sextilha -> escandir.py -> correção (só versos reprovados,
no máximo 3 rodadas) -> xilogravura -> folhetos/ ou descarte/ + caderno/.

`run_cordel` é um gerador assíncrono: cada etapa sai como um dict, que o
servidor repassa ao navegador via SSE.
"""

import asyncio
import base64
import contextlib
import io
import json
import os
import random
import re
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

import ai
import dotenv
import pydantic
import trafilatura
from ai.providers.openai import tools as openai_tools

from . import prompts

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import escandir  # noqa: E402  (o verificador fica intocado em scripts/)

dotenv.load_dotenv(RAIZ / ".env")

TEXT_MODEL = os.getenv("CORDEL_TEXT_MODEL", "openai:gpt-5.5")
IMAGE_HOST_MODEL = os.getenv("CORDEL_IMAGE_HOST_MODEL", "openai:gpt-5.4-mini")
IMAGE_MODEL = os.getenv("CORDEL_IMAGE_MODEL", "gpt-image-2")
# em xilogravura preto e branco, "low" ficou tão bom quanto "medium" e sai mais barato
IMAGE_QUALITY = os.getenv("CORDEL_IMAGE_QUALITY", "low")
REASONING = os.getenv("CORDEL_REASONING", "medium")
CANDIDATAS = int(os.getenv("CORDEL_CANDIDATAS", "3"))
MAX_RODADAS = 3

# No Railway, CORDEL_DADOS aponta para o volume montado (/data), que sobrevive
# aos deploys. Local, as pastas ficam na raiz do projeto.
DADOS = Path(os.getenv("CORDEL_DADOS") or RAIZ)
PASTAS = {nome: DADOS / nome for nome in ("folhetos", "descarte", "caderno")}


# ------------------------------------------------------------------ esquemas
class Fato(pydantic.BaseModel):
    fato: str
    titulo: str
    imagens_concretas: list[str]


class Sextilha(pydantic.BaseModel):
    angulo: str
    rimas: list[str]
    versos: list[str]


class Escolha(pydantic.BaseModel):
    escolhida: int
    justificativa: str


class VersoCorrigido(pydantic.BaseModel):
    n: int
    verso: str


class Correcao(pydantic.BaseModel):
    versos: list[VersoCorrigido]


# ---------------------------------------------------------------- modelo
async def gerar(
    sistema: str, usuario: str, output_type: type[pydantic.BaseModel], log: list
) -> Any:
    """Uma chamada estruturada ao modelo de texto, registrada na íntegra no log."""
    model = ai.get_model(TEXT_MODEL)
    params = ai.InferenceRequestParams(reasoning=ai.ReasoningParams(effort=REASONING))
    t0 = time.monotonic()
    async with ai.stream(
        model,
        [ai.system_message(sistema), ai.user_message(usuario)],
        output_type=output_type,
        params=params,
    ) as stream:
        async for _ in stream:
            pass
    log.append({
        "modelo": TEXT_MODEL,
        "reasoning_effort": REASONING,
        "sistema": sistema,
        "usuario": usuario,
        "saida_bruta": stream.text,
        "tokens": _uso(stream.usage),
        "segundos": round(time.monotonic() - t0, 1),
    })
    return stream.output


async def gerar_xilogravura(fato: Fato, log: list) -> bytes | None:
    """Imagem pela ferramenta image_generation da OpenAI (provider tool do SDK)."""
    prompt = prompts.prompt_xilogravura(fato.fato, fato.imagens_concretas)
    tool = openai_tools.image_generation(
        model=IMAGE_MODEL, size="1536x1024", quality=IMAGE_QUALITY, output_format="png"
    )
    params = ai.InferenceRequestParams(
        tool_calling=ai.ToolCallingParams(tool_choice=ai.ToolChoiceMode.REQUIRED)
    )
    t0 = time.monotonic()
    async with ai.stream(
        ai.get_model(IMAGE_HOST_MODEL), [ai.user_message(prompt)],
        tools=[tool], params=params,
    ) as stream:
        async for _ in stream:
            pass
    log.append({
        "modelo": f"{IMAGE_HOST_MODEL} + image_generation({IMAGE_MODEL}, {IMAGE_QUALITY})",
        "usuario": prompt,
        "tokens": _uso(stream.usage),
        "segundos": round(time.monotonic() - t0, 1),
    })
    for f in stream.message.files:
        if f.media_type.startswith("image/"):
            data = f.data
            return data if isinstance(data, bytes) else base64.b64decode(data.split(",")[-1])
    return None


# ------------------------------------------------------------- notícia
class NoticiaIndisponivel(Exception):
    pass


async def obter_noticia(url: str) -> dict:
    """Baixa a página e extrai o texto da matéria. Falha -> o usuário cola o texto."""
    if not re.match(r"^https?://", url):
        raise NoticiaIndisponivel("o link precisa começar com http:// ou https://")
    html = await asyncio.to_thread(trafilatura.fetch_url, url)
    if not html:
        raise NoticiaIndisponivel("não consegui baixar a página (bloqueio, paywall ou link fora do ar)")
    bruto = await asyncio.to_thread(
        trafilatura.extract, html, output_format="json", with_metadata=True, url=url)
    dados = json.loads(bruto) if bruto else {}
    texto = (dados.get("text") or "").strip()
    if len(texto) < 200:
        raise NoticiaIndisponivel("a página não tem texto de matéria que eu consiga extrair")
    return {"titulo": dados.get("title") or "", "fonte": dados.get("sitename") or "",
            "data": dados.get("date") or "", "texto": texto[:8000]}


# ------------------------------------------------------------- verificador
def palavra_final(verso: str) -> str:
    palavras = verso.split()
    return escandir.sem_acento(escandir.so_letras(palavras[-1])) if palavras else ""


def palavras_repetidas(versos: list[str]) -> list[dict]:
    """Critério extra, fora do escandir.py: o script aceita 'Pequim' rimando com
    'Pequim' como rima consoante perfeita. Aqui a palavra final repetida reprova."""
    vistos, problemas = {}, []
    for n, v in enumerate(versos, 1):
        w = palavra_final(v)
        if w and w in vistos:
            problemas.append({"n": n, "motivo": f"repete a palavra final '{w}' do verso {vistos[w]}"})
        vistos.setdefault(w, n)
    return problemas


def medir(versos: list[str]) -> dict:
    """Roda o escandir.py e devolve o resultado + o relatório como o CLI imprime,
    somado ao critério extra de palavra final repetida."""
    texto = "\n".join(versos)
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        linhas, rimas, entra_script = escandir.imprimir("sextilha", texto)
    relatorio = saida.getvalue().strip()
    extras = palavras_repetidas(versos)
    if extras:
        relatorio += "\n  critério extra (palavra final repetida):\n" + "\n".join(
            f"  XX v{e['n']} {e['motivo']}" for e in extras)
    return {"linhas": linhas, "rimas": rimas, "extras": extras,
            "entra_script": entra_script, "entra": entra_script and not extras,
            "relatorio": relatorio}


def versos_reprovados(medida: dict) -> list[int]:
    """Versos fora da métrica, mais os versos que quebram uma rima."""
    ruins = {l["n"] for l in medida["linhas"] if not l["ok"]}
    for r in medida["rimas"]:
        if r["estado"] != "SEM RIMA":
            continue
        # fica a rima da maioria; sem maioria, preserva o primeiro verso do grupo
        chave, freq = Counter(r["chaves"]).most_common(1)[0]
        if freq == 1:
            chave = r["chaves"][0]
        ruins |= {n for n, c in zip(r["versos"], r["chaves"]) if c != chave}
    ruins |= {e["n"] for e in medida["extras"]}
    return sorted(ruins)


def motivo_descarte(medida: dict, n_versos: int) -> str:
    partes = []
    if n_versos != 6:
        partes.append(f"{n_versos} versos (a sextilha pede 6)")
    partes += [f"verso {l['n']} com {l['silabas']} sílabas"
               for l in medida["linhas"] if not l["ok"]]
    partes += [f"rima {r['letra']} quebrou ({', '.join(r['chaves'])})"
               for r in medida["rimas"] if r["estado"] == "SEM RIMA"]
    partes += [f"verso {e['n']} {e['motivo']}" for e in medida["extras"]]
    return "; ".join(partes) + f" — resistiu a {MAX_RODADAS} rodadas de correção."


# ---------------------------------------------------------------- o laço
async def run_cordel(
    noticia: str = "", url: str = "", com_imagem: bool = True
) -> AsyncIterator[dict]:
    noticia, url = noticia.strip(), url.strip()
    log: dict = {"inicio": datetime.now().isoformat(timespec="seconds"),
                 "url": url or None, "chamadas": [], "rodadas": []}
    chamadas = log["chamadas"]

    # 0. a notícia: o texto colado vale; sem texto, busca pelo link
    if noticia:
        origem = {"origem": "texto colado", "titulo": "", "fonte": ""}
    elif url:
        yield {"etapa": "noticia", "status": "rodando", "url": url}
        try:
            baixada = await obter_noticia(url)
        except NoticiaIndisponivel as e:
            yield {"etapa": "noticia", "status": "erro", "url": url,
                   "erro": f"{e}. Copie e cole o texto da notícia."}
            return
        noticia = f"{baixada['titulo']}\n\n{baixada['texto']}".strip()
        origem = {"origem": "link", **{k: baixada[k] for k in ("titulo", "fonte", "data")}}
    else:
        yield {"etapa": "noticia", "status": "erro", "erro": "Cole um link ou o texto da notícia."}
        return
    log.update(noticia=noticia, **origem)
    yield {"etapa": "noticia", "status": "ok", "url": url or None,
           "trecho": noticia[:600], "caracteres": len(noticia), **origem}

    # 1. fato
    yield {"etapa": "fato", "status": "rodando"}
    fato: Fato = await gerar(prompts.SISTEMA_FATO, noticia, Fato, chamadas)
    log["fato"] = fato.model_dump()
    yield {"etapa": "fato", "status": "ok", **fato.model_dump()}

    # 5. a xilogravura só depende do fato: roda em paralelo com o laço do texto
    imagem_task = None
    if com_imagem:
        imagem_task = asyncio.create_task(gerar_xilogravura(fato, chamadas))
        yield {"etapa": "xilogravura", "status": "rodando"}

    # 2. candidatas: várias sextilhas em paralelo, cada uma por um ângulo
    angulos = random.sample(prompts.ANGULOS, min(CANDIDATAS, len(prompts.ANGULOS)))
    yield {"etapa": "candidatas", "status": "rodando", "angulos": angulos}
    geradas = await asyncio.gather(*(
        gerar(prompts.SISTEMA_SEXTILHA,
              prompts.usuario_sextilha(fato.fato, fato.imagens_concretas, a),
              Sextilha, chamadas)
        for a in angulos), return_exceptions=True)
    candidatas = []
    for a, g in zip(angulos, geradas):
        if isinstance(g, BaseException):
            log.setdefault("erros_candidatas", []).append(f"{a}: {g}")
            continue
        vs = [v.strip() for v in g.versos if v.strip()]
        m = medir(vs)
        candidatas.append({"angulo": a, "plano": g.angulo, "rimas": g.rimas, "versos": vs,
                           "entra": m["entra"], "reprovados": versos_reprovados(m)})
    if not candidatas:
        raise RuntimeError("nenhuma candidata foi gerada: " + "; ".join(log["erros_candidatas"]))
    log["candidatas"] = candidatas
    yield {"etapa": "candidatas", "status": "ok", "candidatas": candidatas}

    # 2b. júri: escolhe a mais criativa entre as que o verificador prefere
    validas = [i for i, c in enumerate(candidatas) if len(c["versos"]) == 6] or [0]
    escolhida, justificativa = validas[0], "única candidata com 6 versos"
    if len(validas) > 1:
        yield {"etapa": "julgamento", "status": "rodando"}
        juri: Escolha = await gerar(
            prompts.SISTEMA_JULGAMENTO,
            prompts.usuario_julgamento(fato.fato, [candidatas[i] for i in validas]),
            Escolha, chamadas,
        )
        if 1 <= juri.escolhida <= len(validas):
            escolhida, justificativa = validas[juri.escolhida - 1], juri.justificativa
        else:
            justificativa = f"júri respondeu {juri.escolhida}, fora da lista; fica a primeira"
    log["escolhida"] = {"indice": escolhida, "justificativa": justificativa}
    yield {"etapa": "julgamento", "status": "ok", "escolhida": escolhida,
           "justificativa": justificativa}
    versos = list(candidatas[escolhida]["versos"])

    # 3-4. escandir e corrigir só o que foi reprovado, no máximo 3 rodadas
    rodada = 0
    while True:
        medida = medir(versos)
        reprovados = versos_reprovados(medida)
        log["rodadas"].append({"rodada": rodada, "versos": list(versos),
                               "relatorio": medida["relatorio"]})
        yield {"etapa": "escansao", "rodada": rodada, "versos": versos,
               "linhas": medida["linhas"], "rimas": medida["rimas"],
               "extras": medida["extras"], "entra": medida["entra"], "reprovados": reprovados,
               "relatorio": medida["relatorio"]}
        if medida["entra"] or rodada >= MAX_RODADAS or len(versos) != 6 or not reprovados:
            break
        rodada += 1
        yield {"etapa": "correcao", "status": "rodando", "rodada": rodada,
               "reprovados": reprovados}
        corr: Correcao = await gerar(
            prompts.SISTEMA_CORRECAO,
            prompts.usuario_correcao(versos, medida["relatorio"], reprovados),
            Correcao, chamadas,
        )
        mudancas = []
        for c in corr.versos:
            # só aceita troca nos versos reprovados: o que passou fica
            if c.n in reprovados and c.verso.strip():
                mudancas.append({"n": c.n, "antes": versos[c.n - 1], "depois": c.verso.strip()})
                versos[c.n - 1] = c.verso.strip()
        yield {"etapa": "correcao", "status": "ok", "rodada": rodada, "mudancas": mudancas}

    # 6. registro
    entra = medida["entra"]
    slug = _slug(fato.titulo)
    pasta = PASTAS["folhetos" if entra else "descarte"]
    texto = "\n".join(versos) + "\n"
    motivo = None
    if not entra:
        motivo = motivo_descarte(medida, len(versos))
        texto = f"# DESCARTADA: {motivo}\n" + texto
    for p in PASTAS.values():
        p.mkdir(parents=True, exist_ok=True)
    (pasta / f"{slug}.txt").write_text(texto, encoding="utf-8")
    arquivos = {"texto": f"{pasta.name}/{slug}.txt"}

    if imagem_task:
        try:
            png = await imagem_task
        except Exception as e:  # a imagem falhar não derruba o folheto
            png = None
            log["erro_imagem"] = str(e)
        if png:
            (pasta / f"{slug}.png").write_bytes(png)
            arquivos["imagem"] = f"{pasta.name}/{slug}.png"
        yield {"etapa": "xilogravura", "status": "ok" if png else "erro",
               "url": arquivos.get("imagem"), "erro": log.get("erro_imagem")}

    duvidas = [{"n": l["n"], "duvida": l["duvidas"]} for l in medida["linhas"] if l["duvidas"]]
    log.update(fim=datetime.now().isoformat(timespec="seconds"), entra=entra,
               motivo=motivo, versos_finais=versos, duvidas_para_o_grupo=duvidas,
               rodadas_de_correcao=rodada, arquivos=arquivos)
    (PASTAS["caderno"] / f"{slug}.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    arquivos["caderno"] = f"caderno/{slug}.json"

    yield {"etapa": "fim", "entra": entra, "motivo": motivo, "titulo": fato.titulo,
           "url": url or None, "fonte": origem["fonte"],
           "versos": versos, "rodadas": rodada, "duvidas": duvidas, "arquivos": arquivos}


# ------------------------------------------------------------------- util
def _uso(u) -> dict | None:
    if u is None:
        return None
    return {k: getattr(u, k, None) for k in ("input_tokens", "output_tokens", "reasoning_tokens")}


def _slug(titulo: str) -> str:
    s = unicodedata.normalize("NFD", titulo.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:48] or "folheto"
    return f"{datetime.now():%Y%m%d-%H%M%S}-{s}"
