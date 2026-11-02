"""O laço do SKILL.md, automatizado com o AI SDK para Python.

notícia -> fato -> candidatas -> escandir.py -> correção pelo próprio Poeta, na mesma
conversa (só versos reprovados, no máximo MAX_RODADAS rodadas) -> júri semântico entre as
aprovadas -> reescrita pelo sentido, se melhorar -> xilogravura -> folhetos/ ou descarte/ + caderno/.

`run_cordel` é um gerador assíncrono: cada etapa sai como um dict, que o
servidor repassa ao navegador via SSE.
"""

import asyncio
import base64
import contextlib
import io
import ipaddress
import json
import os
import random
import re
import socket
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Literal
from urllib.parse import urlsplit

import ai
import dotenv
import openai
import pydantic
import trafilatura
from ai.providers.openai import tools as openai_tools

from . import custos, dicionario, prompts

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import escandir  # noqa: E402  (o verificador fica intocado em scripts/)

dotenv.load_dotenv(RAIZ / ".env")
# O site está aberto para a turma: tudo (texto, imagem e consulta de custo) usa a chave do
# professor. O SDK e o cliente da OpenAI leem OPENAI_API_KEY. Sem ela, o servidor nem sobe.
os.environ["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY_PROFESSOR"]

# O hospedeiro só repassa o prompt à ferramenta de imagem e não muda o desenho: vai o
# modelo de texto mais barato (medido: US$ 0,0004 contra US$ 0,003 do gpt-5.4-mini).
IMAGE_HOST_MODEL = os.getenv("CORDEL_IMAGE_HOST_MODEL", "openai:gpt-6-luna")
# opção do seletor -> (modelo de imagem, qualidade). Custos medidos em 28/09, 1536×1024,
# com o hospedeiro gpt-6-luna: mínima ~US$ 0,004; rápida ~US$ 0,006.
IMAGENS = {
    "minima": ("gpt-image-1-mini", "low"),
    "low": ("gpt-image-2", "low"),
    "medium": ("gpt-image-2", "medium"),
}

# O que a página deixa escolher. O servidor só aceita estes valores: com o site
# aberto, a API não pode chamar outro modelo com a chave do professor.
OPCOES = {
    "texto": ["openai:gpt-6-luna"],
    "raciocinio": ["low", "medium", "high"],
    "candidatas": [1, 2, 3],
    "imagem_qualidade": ["minima"],
    "forma": list(prompts.FORMAS),
    "estrofes": [1, 2, 3, 4, 6],
    "encadeamento": ["livre", "deixa"],
    "narrador": [*prompts.NARRADORES, "sortear"],
}


# A configuração mais barata. A página abre nela e pede confirmação quando alguém
# escolhe algo mais caro. Forma, estrofes e candidatas ficam livres.
ECONOMICO = {"texto": "openai:gpt-6-luna", "raciocinio": "low", "imagem_qualidade": "minima"}


@dataclass(frozen=True)
class Config:
    """Configuração de uma geração. Viaja com a geração (não é global) para que
    duas pessoas gerando ao mesmo tempo não troquem o modelo uma da outra."""
    texto: str = os.getenv("CORDEL_TEXT_MODEL", ECONOMICO["texto"])
    raciocinio: str = os.getenv("CORDEL_REASONING", ECONOMICO["raciocinio"])
    # várias candidatas compensam o descarte: um poema fiel que trava na métrica não impede
    # a entrega, porque outra candidata pode passar
    candidatas: int = int(os.getenv("CORDEL_CANDIDATAS", "3"))
    # em xilogravura preto e branco, "low" ficou tão bom quanto "medium" e sai mais barato
    imagem_qualidade: str = os.getenv("CORDEL_IMAGE_QUALITY", ECONOMICO["imagem_qualidade"])
    forma: str = "aberta"         # tipo de sextilha pelo esquema de rima
    estrofes: int = 1
    encadeamento: str = "livre"   # "deixa": 1º verso rima com o último da estrofe anterior
    narrador: str = "observador"  # regra 10 do grupo; "sortear" = um por candidata

    @property
    def esquema(self) -> str:
        return prompts.FORMAS[self.forma][0]

    def validar(self) -> "Config":
        for campo, valor in asdict(self).items():
            if valor not in OPCOES[campo]:
                raise ValueError(f"{campo}={valor!r} não está entre {OPCOES[campo]}")
        return self


# rodadas de correção antes do descarte (eram 3 até 28/09; o teto de custo continua valendo)
MAX_RODADAS = int(os.getenv("CORDEL_MAX_RODADAS", "10"))
# Teto de gasto por geração. Passou dele, a geração não chama o júri nem faz novas
# rodadas de correção: entrega o que tem. É um freio, não uma garantia exata — uma
# chamada já iniciada termina — e reserva uns centavos para a xilogravura.
TETO_USD = float(os.getenv("CORDEL_TETO_USD", "0.10"))
RESERVA_IMAGEM_USD = 0.01
# reescritas pelo sentido depois do júri, e rodadas de métrica permitidas em cada uma
MAX_REESCRITAS = 2
RODADAS_POR_REESCRITA = 4
GRAVES = {"contradiz", "inventa"}


def chave_juizo(av: dict | None) -> tuple:
    """Menor é melhor: erro de fato pesa mais que verso confuso, e os dois mais que as notas."""
    if av is None:
        return (float("inf"),)
    graves = sum(a["tipo"] in GRAVES for a in av["apontados"])
    return (graves, len(av["apontados"]), -(av["fidelidade"] + av["coerencia"]), -(av["termos"] + av["criatividade"]))

# No Railway, CORDEL_DADOS aponta para o volume montado (/data), que sobrevive
# aos deploys. Local, as pastas ficam na raiz do projeto.
DADOS = Path(os.getenv("CORDEL_DADOS") or RAIZ)
PASTAS = {nome: DADOS / nome for nome in ("folhetos", "descarte", "caderno")}


# ------------------------------------------------------------------ esquemas
class Fato(pydantic.BaseModel):
    fato: str
    titulo: str
    imagens_concretas: list[str]


class Estrofe(pydantic.BaseModel):
    finais: list[str]
    termos: list[str]  # termos do dicionário nordestino planejados para a estrofe
    versos: list[str]


class Poema(pydantic.BaseModel):
    angulo: str
    estrofes: list[Estrofe]


class VersoApontado(pydantic.BaseModel):
    estrofe: int
    n: int
    tipo: Literal["contradiz", "inventa", "sem_sentido", "termo_solto", "enchimento"]
    motivo: str


class Avaliacao(pydantic.BaseModel):
    candidata: int
    comentario: str
    apontados: list[VersoApontado]
    fidelidade: int  # as notas vêm depois dos apontados: o modelo olha os versos antes de dar nota
    coerencia: int
    termos: int
    criatividade: int


class Juizo(pydantic.BaseModel):
    avaliacoes: list[Avaliacao]


class VersoCorrigido(pydantic.BaseModel):
    estrofe: int
    n: int
    contagem: str  # vem antes do verso de propósito: obriga o modelo a contar as sílabas primeiro
    verso: str


class Correcao(pydantic.BaseModel):
    versos: list[VersoCorrigido]


# ---------------------------------------------------------------- modelo
async def gerar(
    sistema: str, usuario: str, output_type: type[pydantic.BaseModel], log: list,
    cfg: Config, etapa: str = "", conversa: list | None = None,
) -> Any:
    """Uma chamada estruturada ao modelo de texto, registrada na íntegra no log.

    `conversa` guarda os turnos anteriores de uma mesma conversa e recebe os novos. Só vai o
    texto da resposta, sem o raciocínio, para o histórico não encarecer a cada rodada."""
    model = ai.get_model(cfg.texto)
    params = ai.InferenceRequestParams(reasoning=ai.ReasoningParams(effort=cfg.raciocinio))
    anteriores = conversa or []
    t0 = time.monotonic()
    async with ai.stream(
        model,
        [ai.system_message(sistema), *anteriores, ai.user_message(usuario)],
        output_type=output_type,
        params=params,
    ) as stream:
        response_id = await _consumir(stream)
    log.append({
        "etapa": etapa,
        "modelo": cfg.texto,
        "response_id": response_id,
        "reasoning_effort": cfg.raciocinio,
        "sistema": sistema,
        "usuario": usuario,
        "turnos_anteriores": len(anteriores) // 2,
        "saida_bruta": stream.text,
        "tokens": _uso(stream.usage),
        "segundos": round(time.monotonic() - t0, 1),
    })
    if conversa is not None:
        conversa += [ai.user_message(usuario), ai.assistant_message(stream.text)]
    return stream.output


async def _consumir(stream) -> str | None:
    """Esvazia o stream e devolve o response_id da OpenAI (para cruzar com os logs dela)."""
    response_id = None
    async for ev in stream:
        if isinstance(ev, ai.events.StreamEnd):
            response_id = ev.response_id
    return response_id


async def uso_da_imagem(response_id: str | None) -> dict | None:
    """O SDK só repassa o uso do modelo hospedeiro; a geração da imagem é cobrada à
    parte e aparece em tool_usage.image_gen da resposta, que buscamos pelo id."""
    if not response_id:
        return None
    try:
        r = await openai.AsyncOpenAI().responses.retrieve(response_id)
        ig = (r.model_dump().get("tool_usage") or {}).get("image_gen") or {}
    except openai.OpenAIError:
        return None
    ent = ig.get("input_tokens_details") or {}
    sai = ig.get("output_tokens_details") or {}
    return {"texto_entrada": ent.get("text_tokens") or 0,
            "imagem_entrada": ent.get("image_tokens") or 0,
            "imagem_saida": sai.get("image_tokens") or ig.get("output_tokens") or 0}


async def gerar_xilogravura(fato: Fato, log: list, cfg: Config) -> bytes | None:
    """Imagem pela ferramenta image_generation da OpenAI (provider tool do SDK)."""
    prompt = prompts.prompt_xilogravura(fato.fato, fato.imagens_concretas)
    modelo_imagem, qualidade = IMAGENS[cfg.imagem_qualidade]
    tool = openai_tools.image_generation(
        model=modelo_imagem, size="1536x1024", quality=qualidade, output_format="png"
    )
    params = ai.InferenceRequestParams(
        tool_calling=ai.ToolCallingParams(tool_choice=ai.ToolChoiceMode.REQUIRED)
    )
    t0 = time.monotonic()
    async with ai.stream(
        ai.get_model(IMAGE_HOST_MODEL), [ai.user_message(prompt)],
        tools=[tool], params=params,
    ) as stream:
        response_id = await _consumir(stream)
    log.append({
        "etapa": "xilogravura",
        "modelo": f"{IMAGE_HOST_MODEL} + image_generation({modelo_imagem}, {qualidade})",
        "modelo_imagem": modelo_imagem,
        "response_id": response_id,
        "usuario": prompt,
        "tokens": _uso(stream.usage),
        "tokens_imagem": await uso_da_imagem(response_id),
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


def _endereco_publico(url: str) -> bool:
    """Com o site aberto, ninguém pode mandar o servidor ler a rede interna do Railway."""
    try:
        infos = socket.getaddrinfo(urlsplit(url).hostname, None)
    except (OSError, UnicodeError, ValueError):
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0].split("%")[0]).is_global for i in infos)


async def obter_noticia(url: str) -> dict:
    """Baixa a página e extrai o texto da matéria. Falha -> o usuário cola o texto."""
    if not re.match(r"^https?://", url):
        raise NoticiaIndisponivel("o link precisa começar com http:// ou https://")
    if not await asyncio.to_thread(_endereco_publico, url):
        raise NoticiaIndisponivel("esse endereço não é de um site público")
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


def medir(versos: list[str], esquema: str = "ABCBDB", nome: str = "sextilha") -> dict:
    """Roda o escandir.py numa estrofe e devolve o resultado + o relatório como o
    CLI imprime, somado ao critério extra de palavra final repetida."""
    texto = "\n".join(versos)
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        linhas, rimas, entra_script = escandir.imprimir(nome, texto, esquema=esquema)
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


def ligacoes_em_deixa(estrofes: list[list[str]]) -> list[dict]:
    """Deixa da cantoria: da 2ª estrofe em diante, o 1º verso rima com o último
    verso da estrofe anterior (com palavra diferente)."""
    res = []
    for e in range(1, len(estrofes)):
        if not estrofes[e] or not estrofes[e - 1]:
            continue
        ant, pri = estrofes[e - 1][-1], estrofes[e][0]
        (c1, t1), (c2, t2) = escandir.chave_rima(ant), escandir.chave_rima(pri)
        estado = ("mesma palavra" if palavra_final(ant) == palavra_final(pri)
                  else "consoante" if c1 == c2 else "toante" if t1 == t2 else "SEM RIMA")
        res.append({"estrofe": e + 1, "estado": estado, "chaves": [c1, c2],
                    "ok": estado in ("consoante", "toante")})
    return res


# ---- regras do grupo que dá para conferir por código (as outras vão no prompt)
# aplicadas a cada palavra com hífen inteira: "disse-me" (ênclise), "dir-lhe-ei" (mesóclise)
CLITICOS = "me|te|se|lhe|lhes|nos|vos|o|a|os|as|lo|la|los|las|no|na|nas"
PRONOME_COM_HIFEN = re.compile(rf"\w+(-({CLITICOS}))+(-\w+)?", re.I)
# compostos com hífen que parecem ênclise mas são substantivos
COMPOSTOS = {"bem-te-vi", "bem-te-vis", "disse-me-disse", "bem-me-quer", "mal-me-quer", "louva-a-deus"}


def versos_livres(esquema: str) -> list[int]:
    """Versos que não rimam com nenhum outro no esquema (ABCBDB -> 1, 3, 5)."""
    return [n for n, letra in enumerate(esquema, 1) if esquema.count(letra) == 1]


def regras_do_grupo(estrofes: list[list[str]], cfg: "Config") -> list[dict]:
    """Regras 1, 3, 7 e 9 do grupo. Quando a falta é de um par ou de uma estrofe
    (regras 3 e 7), marca um verso que não rima, para a correção não quebrar a rima."""
    livres = versos_livres(cfg.esquema)
    achados = []

    def escolher(e: int, candidatos: list[int]) -> int:
        # prefere verso livre; na deixa, o 1º verso (da 2ª estrofe em diante) está preso à rima
        presos = {1} if cfg.encadeamento == "deixa" and e > 1 else set()
        return next((n for n in candidatos if n in livres and n not in presos),
                    next((n for n in candidatos if n not in presos), candidatos[0]))

    for e, vs in enumerate(estrofes, 1):
        for n, v in enumerate(vs, 1):
            pron = [p for p in re.findall(r"\w+(?:-\w+)+", v)
                    if p.lower() not in COMPOSTOS and PRONOME_COM_HIFEN.fullmatch(p)]
            if pron:
                achados.append({"estrofe": e, "n": n, "regra": 1,
                                "motivo": f"ênclise/mesóclise: {', '.join(dict.fromkeys(pron))}"})
            if fat := dicionario.faticas_fora_da_ponta(v):
                achados.append({"estrofe": e, "n": n, "regra": 9,
                                "motivo": f"partícula fática no meio do verso: {', '.join(fat)}"})
        for a in range(0, len(vs) - 1, 2):
            par = [a + 1, a + 2]
            if not any(dicionario.termos_no_verso(vs[n - 1]) for n in par):
                achados.append({"estrofe": e, "n": escolher(e, par), "regra": 3,
                                "motivo": f"nenhum termo do dicionário nos versos {par[0]} e {par[1]}"})
        if vs and not any(dicionario.termos_no_verso(v, ("expressao",)) for v in vs):
            achados.append({"estrofe": e, "n": escolher(e, list(range(1, len(vs) + 1))), "regra": 7,
                            "motivo": "a estrofe não tem nenhuma expressão de mais de uma palavra do dicionário"})
    return achados


def medir_poema(estrofes: list[list[str]], cfg: "Config") -> dict:
    """Mede cada estrofe no escandir.py com o esquema escolhido, e a deixa entre elas."""
    unica = len(estrofes) == 1
    medidas = [medir(vs, cfg.esquema, "sextilha" if unica else f"estrofe {e}")
               for e, vs in enumerate(estrofes, 1)]
    deixa = ligacoes_em_deixa(estrofes) if cfg.encadeamento == "deixa" else []
    regras = regras_do_grupo(estrofes, cfg)
    reprovados = sorted({(e, n) for e, m in enumerate(medidas, 1) for n in versos_reprovados(m)}
                        | {(d["estrofe"], 1) for d in deixa if not d["ok"]}
                        | {(r["estrofe"], r["n"]) for r in regras})
    forma_ok = len(estrofes) == cfg.estrofes and all(len(vs) == 6 for vs in estrofes)
    relatorio = "\n\n".join(m["relatorio"] for m in medidas)
    if deixa:
        relatorio += "\n\n  deixa (1º verso rima com o último da estrofe anterior):\n" + "\n".join(
            f"  {'ok' if d['ok'] else 'XX'} estrofe {d['estrofe']}: {d['estado']} {d['chaves']}"
            for d in deixa)
    if regras:
        relatorio += "\n\n  regras do grupo:\n" + "\n".join(
            f"  XX estrofe {r['estrofe']}, verso {r['n']} (regra {r['regra']}): {r['motivo']}" for r in regras)
    return {"medidas": medidas, "deixa": deixa, "regras": regras, "reprovados": reprovados, "forma_ok": forma_ok,
            "entra": forma_ok and all(m["entra"] for m in medidas) and all(d["ok"] for d in deixa) and not regras,
            "relatorio": relatorio}


def motivo_descarte(mp: dict, estrofes: list[list[str]], cfg: "Config") -> str:
    partes = []
    if len(estrofes) != cfg.estrofes:
        partes.append(f"{len(estrofes)} estrofes (pedidas {cfg.estrofes})")
    for e, (vs, m) in enumerate(zip(estrofes, mp["medidas"]), 1):
        pref = "" if len(estrofes) == 1 else f"estrofe {e}, "
        if len(vs) != 6:
            partes.append(f"{pref}{len(vs)} versos (a sextilha pede 6)")
        partes += [f"{pref}verso {l['n']} com {l['silabas']} sílabas"
                   for l in m["linhas"] if not l["ok"]]
        partes += [f"{pref}rima {r['letra']} quebrou ({', '.join(r['chaves'])})"
                   for r in m["rimas"] if r["estado"] == "SEM RIMA"]
        partes += [f"{pref}verso {x['n']} {x['motivo']}" for x in m["extras"]]
    partes += [f"deixa da estrofe {d['estrofe']}: {d['estado']}" for d in mp["deixa"] if not d["ok"]]
    partes += [f"estrofe {r['estrofe']}, verso {r['n']}: regra {r['regra']} ({r['motivo']})" for r in mp["regras"]]
    return "; ".join(partes) + f" — resistiu a {MAX_RODADAS} rodadas de correção."


# ---------------------------------------------------------------- o laço
async def run_cordel(
    noticia: str = "", url: str = "", com_imagem: bool = True, cfg: Config | None = None,
    autor: str = "",
) -> AsyncIterator[dict]:
    cfg = (cfg or Config()).validar()
    noticia, url = noticia.strip(), url.strip()
    log: dict = {"inicio": _agora(), "autor": autor or None,
                 "url": url or None, "config": {**asdict(cfg), "com_imagem": com_imagem},
                 "chamadas": [], "rodadas": []}
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
    fato: Fato = await gerar(prompts.SISTEMA_FATO, noticia, Fato, chamadas, cfg, "fato")
    log["fato"] = fato.model_dump()
    yield {"etapa": "fato", "status": "ok", **fato.model_dump()}

    # 5. a xilogravura só depende do fato: roda em paralelo com o laço do texto
    imagem_task = None
    if com_imagem:
        imagem_task = asyncio.create_task(gerar_xilogravura(fato, chamadas, cfg))
        yield {"etapa": "xilogravura", "status": "rodando"}

    # 2. candidatas: várias sextilhas em paralelo, cada uma por um ângulo
    # narrador fixo: todas as candidatas com ele; "sortear": um diferente por candidata
    angulos = (random.sample(list(prompts.NARRADORES.values()), min(cfg.candidatas, len(prompts.NARRADORES)))
               if cfg.narrador == "sortear" else [prompts.NARRADORES[cfg.narrador]] * cfg.candidatas)
    yield {"etapa": "candidatas", "status": "rodando", "angulos": angulos}
    sistema_poeta = prompts.sistema_poema(cfg.forma, cfg.estrofes, cfg.encadeamento)
    # uma conversa por candidata: quem corrige depois é o mesmo Poeta que escreveu
    conversas = [[] for _ in angulos]
    geradas = await asyncio.gather(*(
        gerar(sistema_poeta,
              prompts.usuario_poema(fato.fato, fato.imagens_concretas, a, noticia),
              Poema, chamadas, cfg, "candidata", conversa=c)
        for a, c in zip(angulos, conversas)), return_exceptions=True)
    candidatas, conversas_ok = [], []
    for a, g, c in zip(angulos, geradas, conversas):
        if isinstance(g, BaseException):
            log.setdefault("erros_candidatas", []).append(f"{a}: {g}")
            continue
        conversas_ok.append(c)
        ests = [[v.strip() for v in e.versos if v.strip()] for e in g.estrofes]
        mp = medir_poema(ests, cfg)
        candidatas.append({"angulo": a, "plano": g.angulo, "finais": [e.finais for e in g.estrofes],
                           "estrofes": ests, "entra": mp["entra"], "forma_ok": mp["forma_ok"],
                           "reprovados": mp["reprovados"]})
    if not candidatas:
        raise RuntimeError("nenhuma candidata foi gerada: " + "; ".join(log["erros_candidatas"]))
    log["candidatas"] = candidatas
    yield {"etapa": "candidatas", "status": "ok", "candidatas": candidatas}

    teto_texto = TETO_USD - (RESERVA_IMAGEM_USD if com_imagem else 0)
    def estourou() -> bool:
        return custos.resumo(log)["total"] >= teto_texto

    # 3-4. escandir e corrigir cada candidata, em paralelo, antes do júri: ele só deve ler o
    # texto que pode ser publicado. Cada correção continua a conversa do Poeta daquela
    # candidata, com a notícia, o narrador, o plano e as tentativas anteriores à vista.
    fila: asyncio.Queue = asyncio.Queue()
    resultados: list[dict] = [{"estrofes": [list(vs) for vs in c["estrofes"]], "rodada": 0, "rodadas": []}
                              for c in candidatas]

    async def corrigir(i: int, limite: int) -> None:
        res = resultados[i]
        estrofes = res["estrofes"]
        while True:
            rodada = res["rodada"]
            mp = res["mp"] = medir_poema(estrofes, cfg)
            reprovados = mp["reprovados"]
            res["rodadas"].append({"rodada": rodada, "estrofes": [list(vs) for vs in estrofes],
                                   "relatorio": mp["relatorio"]})
            fila.put_nowait({
                "etapa": "escansao", "candidata": i, "rodada": rodada, "estrofes": [list(vs) for vs in estrofes],
                "medidas": [{k: m[k] for k in ("linhas", "rimas", "extras", "entra")} for m in mp["medidas"]],
                "deixa": mp["deixa"], "regras": mp["regras"], "entra": mp["entra"], "reprovados": reprovados,
                "relatorio": mp["relatorio"]})
            if mp["entra"] or rodada >= limite or not mp["forma_ok"] or not reprovados:
                return
            if estourou():
                log["parou_no_teto"] = f"correção {rodada + 1}"
                fila.put_nowait({"etapa": "teto", "onde": f"correção {rodada + 1}",
                                 "gasto": custos.resumo(log)["total"], "teto": TETO_USD})
                return
            rodada = res["rodada"] = rodada + 1
            fila.put_nowait({"etapa": "correcao", "candidata": i, "status": "rodando", "rodada": rodada,
                             "reprovados": reprovados})
            corr: Correcao = await gerar(
                sistema_poeta,
                prompts.usuario_correcao(estrofes, mp["relatorio"], reprovados, fato.fato),
                Correcao, chamadas, cfg, "correção", conversa=conversas_ok[i],
            )
            mudancas = []
            alvo = set(reprovados)
            for c in corr.versos:
                # só aceita troca nos versos reprovados: o que passou fica
                if (c.estrofe, c.n) in alvo and c.verso.strip():
                    antes = estrofes[c.estrofe - 1][c.n - 1]
                    estrofes[c.estrofe - 1][c.n - 1] = c.verso.strip()
                    mudancas.append({"estrofe": c.estrofe, "n": c.n, "antes": antes, "depois": c.verso.strip()})
            fila.put_nowait({"etapa": "correcao", "candidata": i, "status": "ok", "rodada": rodada,
                             "mudancas": mudancas})

    async def rodar(i: int, limite: int) -> None:
        try:
            await corrigir(i, limite)
        except Exception as e:  # uma candidata falhar não derruba as outras
            resultados[i]["erro"] = str(e)
            log.setdefault("erros_correcao", []).append(f"candidata {i + 1}: {e}")
        finally:
            fila.put_nowait(None)

    async def corrigindo(limites: dict[int, int]) -> AsyncIterator[dict]:
        tarefas = [asyncio.create_task(rodar(i, limite)) for i, limite in limites.items()]
        try:
            abertas = len(tarefas)
            while abertas:
                ev = await fila.get()
                if ev is None:
                    abertas -= 1
                else:
                    yield ev
        finally:  # quem gerava fechou a página: não continua gastando
            for t in tarefas:
                t.cancel()

    async with contextlib.aclosing(corrigindo({i: MAX_RODADAS for i in range(len(candidatas))})) as eventos:
        async for ev in eventos:
            yield ev

    if all("erro" in r for r in resultados):
        raise RuntimeError("a correção falhou em todas as candidatas: " + "; ".join(log["erros_correcao"]))
    for c, r in zip(candidatas, resultados):
        c.update(final=r["estrofes"], entra_final=r["mp"]["entra"], rodadas_de_correcao=r["rodada"],
                 rodadas=r["rodadas"], reprovados_final=r["mp"]["reprovados"])

    # 4b. júri: lê só as aprovadas, já corrigidas, numa chamada à parte da conversa do Poeta.
    # Ele não descarta nada: dá as notas, aponta versos, e o código escolhe pela chave_juizo.
    async def avaliar(indices: list[int]) -> dict[int, dict]:
        juizo: Juizo = await gerar(
            prompts.SISTEMA_JUIZ,
            prompts.usuario_juizo(noticia, fato.fato, [(candidatas[i]["angulo"], resultados[i]["estrofes"]) for i in indices]),
            Juizo, chamadas, cfg, "júri",
        )
        notas = {}
        for av in juizo.avaliacoes:
            if 1 <= av.candidata <= len(indices):
                i = indices[av.candidata - 1]
                ests = resultados[i]["estrofes"]
                d = av.model_dump(exclude={"candidata"})
                d["apontados"] = [a for a in d["apontados"]
                                  if 1 <= a["estrofe"] <= len(ests) and 1 <= a["n"] <= len(ests[a["estrofe"] - 1])]
                notas[i] = d
        return notas

    aprovadas = [i for i, r in enumerate(resultados) if r["mp"]["entra"]]
    # sem aprovada, o registro do descarte fica com a que chegou mais perto
    escolhida = aprovadas[0] if aprovadas else min(
        range(len(resultados)),
        key=lambda i: (not resultados[i]["mp"]["forma_ok"], len(resultados[i]["mp"]["reprovados"])))
    justificativa = ("nenhuma candidata passou; fica a que chegou mais perto" if not aprovadas
                     else "sem júri: fica a primeira aprovada")
    avaliacoes: dict[int, dict] = {}
    if aprovadas and estourou():
        log["parou_no_teto"] = "júri"
        yield {"etapa": "teto", "onde": "júri", "gasto": custos.resumo(log)["total"], "teto": TETO_USD}
    elif aprovadas:
        yield {"etapa": "julgamento", "status": "rodando"}
        try:
            avaliacoes = await avaliar(aprovadas)
        except Exception as e:  # o júri falhar não derruba um folheto já aprovado
            log["erro_juri"] = str(e)
        if avaliacoes:
            escolhida = min(aprovadas, key=lambda i: chave_juizo(avaliacoes.get(i)))
            if escolhida in avaliacoes:
                justificativa = avaliacoes[escolhida]["comentario"]
    log["escolhida"] = {"indice": escolhida, "justificativa": justificativa}
    log["juizo"] = {str(i): av for i, av in avaliacoes.items()}
    res = resultados[escolhida]
    yield {"etapa": "julgamento", "status": "ok", "escolhida": escolhida, "justificativa": justificativa,
           "estrofes": res["estrofes"], "aprovadas": aprovadas,
           "avaliacoes": [{"candidata": i, **av} for i, av in avaliacoes.items()]}

    # 4c. reescrita pelo sentido: o Poeta refaz os versos apontados, na conversa dele. A nova
    # versão só fica se passar no escandir e melhorar a avaliação; se não, volta a anterior.
    avaliacao = avaliacoes.get(escolhida)
    log["reescritas"] = []
    for volta in range(1, MAX_REESCRITAS + 1):
        if not avaliacao or not avaliacao["apontados"]:
            break
        if estourou():
            log["parou_no_teto"] = f"reescrita {volta}"
            yield {"etapa": "teto", "onde": f"reescrita {volta}", "gasto": custos.resumo(log)["total"], "teto": TETO_USD}
            break
        apontados = avaliacao["apontados"]
        antes = {"estrofes": [list(vs) for vs in res["estrofes"]], "mp": res["mp"], "rodada": res["rodada"],
                 "rodadas": list(res["rodadas"])}
        yield {"etapa": "sentido", "status": "rodando", "volta": volta, "apontados": apontados}
        registro = {"volta": volta, "apontados": apontados, "mudancas": [], "aceita": False}
        nova = None
        try:
            corr: Correcao = await gerar(
                sistema_poeta, prompts.usuario_sentido(res["estrofes"], apontados, fato.fato),
                Correcao, chamadas, cfg, "sentido", conversa=conversas_ok[escolhida],
            )
            alvo = {(a["estrofe"], a["n"]) for a in apontados}
            for c in corr.versos:
                if (c.estrofe, c.n) in alvo and c.verso.strip():
                    registro["mudancas"].append({"estrofe": c.estrofe, "n": c.n, "antes": res["estrofes"][c.estrofe - 1][c.n - 1],
                                                 "depois": c.verso.strip()})
                    res["estrofes"][c.estrofe - 1][c.n - 1] = c.verso.strip()
            if registro["mudancas"]:
                limite = res["rodada"] + RODADAS_POR_REESCRITA
                async with contextlib.aclosing(corrigindo({escolhida: limite})) as eventos:
                    async for ev in eventos:
                        yield ev
                if res["mp"]["entra"] and "erro" not in res and not estourou():
                    nova = (await avaliar([escolhida])).get(escolhida)
        except Exception as e:  # a reescrita falhar não derruba um folheto já aprovado
            registro["erro"] = str(e)
        registro["aceita"] = nova is not None and chave_juizo(nova) < chave_juizo(avaliacao)
        registro["avaliacao"], registro["estrofes"] = nova, [list(vs) for vs in res["estrofes"]]
        log["reescritas"].append(registro)
        if registro["aceita"]:
            avaliacao = nova
        else:
            res.pop("erro", None)
            res.update(antes)
        yield {"etapa": "sentido", "status": "ok", "volta": volta, "aceita": registro["aceita"],
               "mudancas": registro["mudancas"], "estrofes": res["estrofes"], "avaliacao": avaliacao}
        if not registro["aceita"]:
            break

    candidatas[escolhida].update(final=res["estrofes"], entra_final=res["mp"]["entra"], rodadas_de_correcao=res["rodada"],
                                 rodadas=res["rodadas"], reprovados_final=res["mp"]["reprovados"])
    estrofes, mp, rodada = res["estrofes"], res["mp"], res["rodada"]
    log["rodadas"] = res["rodadas"]
    log["avaliacao_final"] = avaliacao

    # 6. registro
    entra = mp["entra"]
    slug = _slug(fato.titulo)
    pasta = PASTAS["folhetos" if entra else "descarte"]
    # o cabeçalho diz ao escandir.py qual esquema conferir
    forma = f"sextilha {cfg.forma}, {cfg.estrofes} estrofe(s)" + (", em deixa" if cfg.encadeamento == "deixa" else "")
    texto = f"# esquema: {cfg.esquema}\n# forma: {forma}\n" + prompts.poema_em_texto(estrofes) + "\n"
    motivo = None
    if not entra:
        motivo = motivo_descarte(mp, estrofes, cfg)
        if len(candidatas) > 1:
            motivo = f"nenhuma das {len(candidatas)} candidatas passou; a mais próxima: {motivo}"
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

    duvidas = [{"estrofe": e, "n": l["n"], "duvida": l["duvidas"]}
               for e, m in enumerate(mp["medidas"], 1) for l in m["linhas"] if l["duvidas"]]
    log.update(fim=_agora(), entra=entra,
               motivo=motivo, estrofes_finais=estrofes, duvidas_para_o_grupo=duvidas,
               rodadas_de_correcao=rodada, arquivos=arquivos)
    custo = custos.resumo(log)
    log["custo_estimado_usd"] = {k: round(v, 5) for k, v in custo.items() if k in ("texto", "imagem", "total")}
    (PASTAS["caderno"] / f"{slug}.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    arquivos["caderno"] = f"caderno/{slug}.json"

    yield {"etapa": "fim", "entra": entra, "motivo": motivo, "titulo": fato.titulo, "autor": autor or None,
           "url": url or None, "fonte": origem["fonte"], "avaliacao": avaliacao,
           "estrofes": estrofes, "rodadas": rodada, "duvidas": duvidas, "arquivos": arquivos,
           "custo": log["custo_estimado_usd"]}


# ------------------------------------------------------------------- util
def _agora() -> str:
    """Hora com fuso (ex.: +00:00 no Railway), para o navegador converter para o
    horário de quem está vendo. Sem fuso, o navegador leria como hora local."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _uso(u) -> dict | None:
    if u is None:
        return None
    return {k: getattr(u, k, None) for k in ("input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens")}


def _slug(titulo: str) -> str:
    s = unicodedata.normalize("NFD", titulo.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:48] or "folheto"
    return f"{datetime.now():%Y%m%d-%H%M%S}-{s}"
