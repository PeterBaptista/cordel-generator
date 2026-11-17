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
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Literal
from urllib.parse import urlsplit

import ai
import dotenv
import openai
import pydantic
import trafilatura
from ai.models.core.model import Model
from ai.providers import base as ai_base
from ai.providers.openai import tools as openai_tools

from . import custos, dicionario, prompts

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import escandir  # noqa: E402  (o verificador fica intocado em scripts/)

dotenv.load_dotenv(RAIZ / ".env")
# A chave do professor serve quem entra com login (ver contas.py). Quem preferir, ou quando a
# disciplina acabar, usa a própria chave, que vem do navegador a cada geração e nunca é
# gravada. Por isso a chave não vai para o ambiente: cada geração leva a sua (classe IA).
CHAVE_PROFESSOR = os.getenv("OPENAI_API_KEY_PROFESSOR", "").strip()


class IA:
    """Os clientes da OpenAI de uma geração, com a chave dela."""

    def __init__(self, chave: str):
        self.provider = ai_base.Provider.from_id("openai", api_key=chave)
        self._chave = chave
        self._cliente: openai.AsyncOpenAI | None = None

    def modelo(self, model_id: str) -> Model:
        provedor, _, nome = model_id.partition(":")
        if provedor != "openai" or not nome:
            raise ValueError(f"modelo fora da OpenAI: {model_id!r}")
        return Model(id=nome, provider=self.provider)

    @property
    def cliente(self) -> openai.AsyncOpenAI:
        if self._cliente is None:
            self._cliente = openai.AsyncOpenAI(api_key=self._chave)
        return self._cliente

    async def fechar(self) -> None:
        with contextlib.suppress(Exception):
            await self.provider.aclose()
        if self._cliente is not None:
            with contextlib.suppress(Exception):
                await self._cliente.close()

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
    # "noticia": o dicionário vira sugestão e o júri põe a notícia antes da forma.
    # "forma": o dicionário reprova, como era até 16/11 (a métrica reprova nas duas).
    "prioridade": ["noticia", "forma"],
}
# Com a chave do próprio usuário o gasto é dele: liberam os outros modelos e a imagem melhor.
OPCOES_CHAVE_PROPRIA = {**OPCOES, "texto": [f"openai:{m}" for m in custos.PRECOS],
                        "imagem_qualidade": list(IMAGENS)}


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
    prioridade: str = "noticia"   # o que vence quando a forma e a notícia brigam

    @property
    def esquema(self) -> str:
        return prompts.FORMAS[self.forma][0]

    def validar(self, opcoes: dict = OPCOES) -> "Config":
        for campo, valor in asdict(self).items():
            if valor not in opcoes[campo]:
                raise ValueError(f"{campo}={valor!r} não está entre {opcoes[campo]}")
        return self


# rodadas de correção antes do descarte (eram 3 até 28/09; o teto de custo continua valendo)
# Desde 17/11 depende do tamanho: 8 + 2 por estrofe (1 estrofe = 10, 6 estrofes = 20), até o teto.
MAX_RODADAS = int(os.getenv("CORDEL_MAX_RODADAS", "20"))


def rodadas_para(cfg: "Config") -> int:
    """Poema maior tem mais versos para acertar: ganha mais rodadas de correção."""
    return min(MAX_RODADAS, 8 + 2 * cfg.estrofes)
# Teto de gasto por geração. Passou dele, a geração não chama o júri nem faz novas
# rodadas de correção: entrega o que tem. É um freio, não uma garantia exata — uma
# chamada já iniciada termina — e reserva uns centavos para a xilogravura.
TETO_USD = float(os.getenv("CORDEL_TETO_USD", "0.10"))
# com a chave própria os modelos caros ficam liberados: o freio é mais folgado, mas existe
TETO_PROPRIA_USD = float(os.getenv("CORDEL_TETO_PROPRIA_USD", "0.50"))
RESERVA_IMAGEM_USD = 0.01
# reescritas pelo sentido depois do júri, e rodadas de métrica permitidas em cada uma
MAX_REESCRITAS = 2
RODADAS_POR_REESCRITA = 4
GRAVES = {"contradiz", "inventa"}
# a partir desta rodada de correção, o Poeta pensa mais (raciocínio médio): no baixo, a métrica
# ficava oscilando entre as rodadas sem fechar
RODADA_PENSAR_MAIS = 4


def chave_juizo(av: dict | None, prioridade: str = "noticia") -> tuple:
    """Menor é melhor: erro de fato pesa mais que tudo, depois a notícia que ficou faltando.
    Com prioridade na notícia, fidelidade e coerência vêm antes dos versos apontados; com
    prioridade na forma, é como era: os apontados, depois as notas."""
    if av is None:
        return (float("inf"),)
    graves = sum(a["tipo"] in GRAVES for a in av["apontados"])
    faltando = len(av.get("faltando") or [])
    if prioridade == "noticia":
        return (graves, faltando, -av["fidelidade"], -av["coerencia"], len(av["apontados"]),
                -(av["termos"] + av["criatividade"]))
    return (graves, faltando, len(av["apontados"]), -(av["fidelidade"] + av["coerencia"]),
            -(av["termos"] + av["criatividade"]))

# No Railway, CORDEL_DADOS aponta para o volume montado (/data), que sobrevive
# aos deploys. Local, as pastas ficam na raiz do projeto.
DADOS = Path(os.getenv("CORDEL_DADOS") or RAIZ)
PASTAS = {nome: DADOS / nome for nome in ("folhetos", "descarte", "caderno")}


# ------------------------------------------------------------------ esquemas
class Fato(pydantic.BaseModel):
    fato: str
    # o que quem nunca leu a notícia precisa saber: o poema tem de contar tudo isto sozinho,
    # sem contar com a manchete (cadernos de antes de 16/11 não têm)
    essencial: list[str] = []
    titulo: str
    imagens_concretas: list[str]


class Estrofe(pydantic.BaseModel):
    cobre: list[str] = []  # os pontos essenciais que a estrofe conta (vem no plano, antes dos versos)
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
    # pontos essenciais que quem lê só o poema (sem a manchete) não fica sabendo
    faltando: list[str] = []
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
    # outras versões do mesmo verso: o verificador testa todas e fica com a que passa
    alternativas: list[str] = []


class Correcao(pydantic.BaseModel):
    versos: list[VersoCorrigido]


# ---------------------------------------------------------------- modelo
async def gerar(
    sistema: str, usuario: str, output_type: type[pydantic.BaseModel], log: list,
    cfg: Config, etapa: str = "", conversa: list | None = None, *, ia: IA,
) -> Any:
    """Uma chamada estruturada ao modelo de texto, registrada na íntegra no log.

    `conversa` guarda os turnos anteriores de uma mesma conversa e recebe os novos. Só vai o
    texto da resposta, sem o raciocínio, para o histórico não encarecer a cada rodada."""
    model = ia.modelo(cfg.texto)
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


async def uso_da_imagem(response_id: str | None, ia: IA) -> dict | None:
    """O SDK só repassa o uso do modelo hospedeiro; a geração da imagem é cobrada à
    parte e aparece em tool_usage.image_gen da resposta, que buscamos pelo id."""
    if not response_id:
        return None
    try:
        r = await ia.cliente.responses.retrieve(response_id)
        ig = (r.model_dump().get("tool_usage") or {}).get("image_gen") or {}
    except openai.OpenAIError:
        return None
    ent = ig.get("input_tokens_details") or {}
    sai = ig.get("output_tokens_details") or {}
    return {"texto_entrada": ent.get("text_tokens") or 0,
            "imagem_entrada": ent.get("image_tokens") or 0,
            "imagem_saida": sai.get("image_tokens") or ig.get("output_tokens") or 0}


async def gerar_xilogravura(fato: Fato, log: list, cfg: Config, ia: IA) -> bytes | None:
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
        ia.modelo(IMAGE_HOST_MODEL), [ai.user_message(prompt)],
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
        "tokens_imagem": await uso_da_imagem(response_id, ia),
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
        if cfg.prioridade == "noticia":
            # com a notícia em primeiro, a estrofe precisa de TERMOS_POR_ESTROFE termos, em qualquer
            # verso: um a cada 2 versos tirava o sentido; só sugerir, e o modelo largava o dicionário
            termos = {t for v in vs for t in dicionario.termos_no_verso(v)}
            if vs and len(termos) < TERMOS_POR_ESTROFE:
                sem_termo = [n for n, v in enumerate(vs, 1) if not dicionario.termos_no_verso(v)]
                # prefere um verso livre e sem termo; se não houver, qualquer verso livre (trocar um
                # verso que rima arrisca quebrar a rima)
                todos = list(range(1, len(vs) + 1))
                alvo3 = [n for n in sem_termo if n in livres] or [n for n in todos if n in livres] or sem_termo or todos
                achados.append({"estrofe": e, "n": escolher(e, alvo3), "regra": 3,
                                "motivo": f"a estrofe tem {len(termos)} termo(s) do dicionário; pede {TERMOS_POR_ESTROFE}"})
        else:
            for a in range(0, len(vs) - 1, 2):
                par = [a + 1, a + 2]
                if not any(dicionario.termos_no_verso(vs[n - 1]) for n in par):
                    achados.append({"estrofe": e, "n": escolher(e, par), "regra": 3,
                                    "motivo": f"nenhum termo do dicionário nos versos {par[0]} e {par[1]}"})
        if vs and not any(dicionario.termos_no_verso(v, ("expressao",)) for v in vs):
            achados.append({"estrofe": e, "n": escolher(e, list(range(1, len(vs) + 1))), "regra": 7,
                            "motivo": "a estrofe não tem nenhuma expressão de mais de uma palavra do dicionário"})
    return achados


# na prioridade notícia, só a expressão por estrofe (regra 7) vira sugestão; o termo por
# estrofe (regra 3, mais branda) continua reprovando: sem ele, o modelo largava o dicionário
REGRAS_SUGERIDAS = {7}
TERMOS_POR_ESTROFE = 2


# o modelo às vezes cola a contagem no fim do verso ("Trump anunciou força = 7"), e o
# verificador contava isso como verso de 7 sílabas
_CONTAGEM_COLADA = re.compile(r"\s*(?:=\s*\d{1,2}|\(\s*\d{1,2}\s*\))\s*$")


def limpar_verso(v: str) -> str:
    return _CONTAGEM_COLADA.sub("", (v or "").strip()).strip()


def aplicar_correcao(estrofes: list[list[str]], corr: "Correcao", alvo: set, cfg: "Config") -> list[dict]:
    """Troca os versos do alvo pela melhor das versões que o Poeta mandou: para cada verso,
    testa a principal e as alternativas no verificador e fica com a que deixa menos versos
    reprovados (no empate, a principal). Muda `estrofes` no lugar e devolve as mudanças."""
    validos = [c for c in corr.versos
               if (c.estrofe, c.n) in alvo and 1 <= c.estrofe <= len(estrofes) and 1 <= c.n <= len(estrofes[c.estrofe - 1])]
    antes_de = {(c.estrofe, c.n): estrofes[c.estrofe - 1][c.n - 1] for c in validos}
    # primeiro todas as versões principais: um par de rimas reescrito junto é testado já junto
    for c in validos:
        if limpar_verso(c.verso):
            estrofes[c.estrofe - 1][c.n - 1] = limpar_verso(c.verso)
    mudancas = []
    for c in validos:
        opcoes = list(dict.fromkeys(limpar_verso(v) for v in [c.verso, *c.alternativas] if limpar_verso(v)))
        if not opcoes:
            continue
        antes = antes_de[(c.estrofe, c.n)]

        def nota(opcao: str) -> tuple:
            estrofes[c.estrofe - 1][c.n - 1] = opcao
            mp = medir_poema(estrofes, cfg)
            return ((c.estrofe, c.n) in mp["reprovados"], len(mp["reprovados"]))

        notas = [nota(o) for o in opcoes]
        melhor = opcoes[min(range(len(opcoes)), key=lambda i: (notas[i], i))]
        estrofes[c.estrofe - 1][c.n - 1] = melhor
        mudancas.append({"estrofe": c.estrofe, "n": c.n, "antes": antes, "depois": melhor,
                         "testadas": len(opcoes), "escolhida": opcoes.index(melhor)})
    return mudancas


def medir_poema(estrofes: list[list[str]], cfg: "Config") -> dict:
    """Mede cada estrofe no escandir.py com o esquema escolhido, e a deixa entre elas."""
    unica = len(estrofes) == 1
    medidas = [medir(vs, cfg.esquema, "sextilha" if unica else f"estrofe {e}")
               for e, vs in enumerate(estrofes, 1)]
    deixa = ligacoes_em_deixa(estrofes) if cfg.encadeamento == "deixa" else []
    regras = regras_do_grupo(estrofes, cfg)
    sugestoes = [r for r in regras if r["regra"] in REGRAS_SUGERIDAS] if cfg.prioridade == "noticia" else []
    regras = [r for r in regras if r not in sugestoes]
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
    if sugestoes:
        relatorio += "\n\n  sugestões do dicionário (não reprovam: a prioridade é a notícia):\n" + "\n".join(
            f"  ~~ estrofe {r['estrofe']}, verso {r['n']} (regra {r['regra']}): {r['motivo']}" for r in sugestoes)
    return {"medidas": medidas, "deixa": deixa, "regras": regras, "sugestoes": sugestoes, "reprovados": reprovados, "forma_ok": forma_ok,
            "entra": forma_ok and all(m["entra"] for m in medidas) and all(d["ok"] for d in deixa) and not regras,
            "relatorio": relatorio}


def motivo_descarte(mp: dict, estrofes: list[list[str]], cfg: "Config") -> str:  # noqa: C901
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
    if not mp["forma_ok"]:
        return "; ".join(partes) + " — a estrutura veio errada mesmo depois de pedir para refazer."
    return "; ".join(partes) + f" — resistiu a {rodadas_para(cfg)} rodadas de correção."


# ---------------------------------------------------------------- o laço
async def run_cordel(
    noticia: str = "", url: str = "", com_imagem: bool = True, cfg: Config | None = None,
    autor: str = "", *, chave: str, chave_propria: bool = False,
) -> AsyncIterator[dict]:
    """Roda uma geração com a chave dada. Cada evento que vai à tela também vai para o
    caderno (`eventos`), com o segundo em que saiu: é dele que a página /geracao/<id>
    remonta a linha do tempo depois."""
    cfg = (cfg or Config()).validar(OPCOES_CHAVE_PROPRIA if chave_propria else OPCOES)
    ia, eventos, t0 = IA(chave), [], time.monotonic()
    try:
        async with contextlib.aclosing(_run_cordel(noticia, url, com_imagem, cfg, autor, ia,
                                                   chave_propria, eventos)) as etapas:
            async for ev in etapas:
                eventos.append({**ev, "t": round(time.monotonic() - t0, 1)})
                yield ev
    finally:
        await ia.fechar()


async def _run_cordel(
    noticia: str, url: str, com_imagem: bool, cfg: Config, autor: str, ia: IA,
    chave_propria: bool, ja_enviados: list,
) -> AsyncIterator[dict]:
    noticia, url = noticia.strip(), url.strip()
    teto = TETO_PROPRIA_USD if chave_propria else TETO_USD
    # só diz de quem foi a chave, nunca a chave
    log: dict = {"inicio": _agora(), "autor": autor or None,
                 "url": url or None, "config": {**asdict(cfg), "com_imagem": com_imagem},
                 "chave": "propria" if chave_propria else "professor",
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
    fato: Fato = await gerar(prompts.SISTEMA_FATO, prompts.usuario_fato(noticia, cfg.estrofes), Fato, chamadas, cfg, "fato", ia=ia)
    log["fato"] = fato.model_dump()
    yield {"etapa": "fato", "status": "ok", **fato.model_dump()}

    # 5. a xilogravura só depende do fato: roda em paralelo com o laço do texto
    imagem_task = None
    if com_imagem:
        imagem_task = asyncio.create_task(gerar_xilogravura(fato, chamadas, cfg, ia))
        yield {"etapa": "xilogravura", "status": "rodando"}

    # 2. candidatas: várias sextilhas em paralelo, cada uma por um ângulo
    # narrador fixo: todas as candidatas com ele; "sortear": um diferente por candidata
    angulos = (random.sample(list(prompts.NARRADORES.values()), min(cfg.candidatas, len(prompts.NARRADORES)))
               if cfg.narrador == "sortear" else [prompts.NARRADORES[cfg.narrador]] * cfg.candidatas)
    yield {"etapa": "candidatas", "status": "rodando", "angulos": angulos}
    # cada candidata vê um sorteio diferente do dicionário, puxado para os termos menos usados
    usos = dicionario.usos_recentes(_poemas_recentes())
    sorteios = [dicionario.sortear(usos, random) for _ in angulos]
    log["dicionario"] = {"mais_usados": dict(sorted(usos.items(), key=lambda x: -x[1])[:12]),
                         "sorteios": [{k: d[k] for k in ("termos", "evitar")} for d in sorteios]}
    sistemas = [prompts.sistema_poema(cfg.forma, cfg.estrofes, cfg.encadeamento, cfg.prioridade, d["texto"])
                for d in sorteios]
    # uma conversa por candidata: quem corrige depois é o mesmo Poeta que escreveu
    conversas = [[] for _ in angulos]
    geradas = await asyncio.gather(*(
        gerar(sp,
              prompts.usuario_poema(fato.fato, fato.essencial, fato.imagens_concretas, a, noticia),
              Poema, chamadas, cfg, "candidata", conversa=c, ia=ia)
        for a, c, sp in zip(angulos, conversas, sistemas)), return_exceptions=True)
    candidatas, conversas_ok, sistemas_ok = [], [], []
    # o Poeta às vezes erra a estrutura (1 estrofe em vez de 2, 5 versos em vez de 6), e forma
    # errada não tem correção verso a verso: pede para refazer, na mesma conversa
    async def estrutura(g, c, sp):
        for _ in range(2):
            if isinstance(g, BaseException) or _forma_certa(_versos_de(g), cfg):
                return g
            if custos.resumo(log)["total"] >= teto - (RESERVA_IMAGEM_USD if com_imagem else 0):
                return g
            try:
                g = await gerar(sp, prompts.pedido_estrutura(cfg.estrofes, [len(e) for e in _versos_de(g)]),
                                Poema, chamadas, cfg, "estrutura", conversa=c, ia=ia)
            except Exception as e:  # noqa: BLE001 — fica a tentativa anterior
                log.setdefault("erros_candidatas", []).append(f"estrutura: {e}")
                return g
        return g
    geradas = await asyncio.gather(*(estrutura(g, c, sp) for g, c, sp in zip(geradas, conversas, sistemas)))
    for a, g, c, sp in zip(angulos, geradas, conversas, sistemas):
        if isinstance(g, BaseException):
            log.setdefault("erros_candidatas", []).append(f"{a}: {g}")
            continue
        conversas_ok.append(c)
        sistemas_ok.append(sp)
        ests = _versos_de(g)
        mp = medir_poema(ests, cfg)
        candidatas.append({"angulo": a, "plano": g.angulo, "finais": [e.finais for e in g.estrofes],
                           "estrofes": ests, "entra": mp["entra"], "forma_ok": mp["forma_ok"],
                           "reprovados": mp["reprovados"]})
    if not candidatas:
        raise RuntimeError("nenhuma candidata foi gerada: " + "; ".join(log["erros_candidatas"]))
    log["candidatas"] = candidatas
    yield {"etapa": "candidatas", "status": "ok", "candidatas": candidatas, "max_rodadas": rodadas_para(cfg)}

    teto_texto = teto - (RESERVA_IMAGEM_USD if com_imagem else 0)
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
                "deixa": mp["deixa"], "regras": mp["regras"], "sugestoes": mp["sugestoes"], "entra": mp["entra"], "reprovados": reprovados,
                "relatorio": mp["relatorio"]})
            if mp["entra"] or rodada >= limite or not mp["forma_ok"] or not reprovados:
                return
            if estourou():
                log["parou_no_teto"] = f"correção {rodada + 1}"
                fila.put_nowait({"etapa": "teto", "onde": f"correção {rodada + 1}",
                                 "gasto": custos.resumo(log)["total"], "teto": teto})
                return
            rodada = res["rodada"] = rodada + 1
            fila.put_nowait({"etapa": "correcao", "candidata": i, "status": "rodando", "rodada": rodada,
                             "reprovados": reprovados})
            cfg_rodada = (replace(cfg, raciocinio="medium")
                          if rodada >= RODADA_PENSAR_MAIS and cfg.raciocinio == "low" else cfg)
            corr: Correcao = await gerar(
                sistemas_ok[i],
                prompts.usuario_correcao(estrofes, mp["relatorio"], reprovados, fato.fato, fato.essencial),
                Correcao, chamadas, cfg_rodada, "correção", conversa=conversas_ok[i], ia=ia,
            )
            # só aceita troca nos versos reprovados: o que passou fica
            mudancas = aplicar_correcao(estrofes, corr, set(reprovados), cfg)
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

    async with contextlib.aclosing(corrigindo({i: rodadas_para(cfg) for i in range(len(candidatas))})) as eventos:
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
            prompts.usuario_juizo(noticia, fato.fato, fato.essencial,
                                  [(candidatas[i]["angulo"], resultados[i]["estrofes"]) for i in indices]),
            Juizo, chamadas, cfg, "júri", ia=ia,
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
        yield {"etapa": "teto", "onde": "júri", "gasto": custos.resumo(log)["total"], "teto": teto}
    elif aprovadas:
        yield {"etapa": "julgamento", "status": "rodando"}
        try:
            avaliacoes = await avaliar(aprovadas)
        except Exception as e:  # o júri falhar não derruba um folheto já aprovado
            log["erro_juri"] = str(e)
        if avaliacoes:
            escolhida = min(aprovadas, key=lambda i: chave_juizo(avaliacoes.get(i), cfg.prioridade))
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
        if not avaliacao or not (avaliacao["apontados"] or avaliacao.get("faltando")):
            break
        if estourou():
            log["parou_no_teto"] = f"reescrita {volta}"
            yield {"etapa": "teto", "onde": f"reescrita {volta}", "gasto": custos.resumo(log)["total"], "teto": teto}
            break
        apontados, faltando = avaliacao["apontados"], avaliacao.get("faltando") or []
        antes = {"estrofes": [list(vs) for vs in res["estrofes"]], "mp": res["mp"], "rodada": res["rodada"],
                 "rodadas": list(res["rodadas"])}
        yield {"etapa": "sentido", "status": "rodando", "volta": volta, "apontados": apontados, "faltando": faltando}
        registro = {"volta": volta, "apontados": apontados, "faltando": faltando, "mudancas": [], "aceita": False}
        nova = None
        try:
            corr: Correcao = await gerar(
                sistemas_ok[escolhida], prompts.usuario_sentido(res["estrofes"], apontados, faltando, fato.fato, fato.essencial),
                Correcao, chamadas, cfg, "sentido", conversa=conversas_ok[escolhida], ia=ia,
            )
            # para contar o que falta, o Poeta pode mexer em qualquer verso; se não, só nos apontados
            alvo = ({(e, n) for e, vs in enumerate(res["estrofes"], 1) for n in range(1, len(vs) + 1)}
                    if faltando else {(a["estrofe"], a["n"]) for a in apontados})
            registro["mudancas"] = aplicar_correcao(res["estrofes"], corr, alvo, cfg)
            if registro["mudancas"]:
                limite = res["rodada"] + RODADAS_POR_REESCRITA
                async with contextlib.aclosing(corrigindo({escolhida: limite})) as eventos:
                    async for ev in eventos:
                        yield ev
                if res["mp"]["entra"] and "erro" not in res and not estourou():
                    nova = (await avaliar([escolhida])).get(escolhida)
        except Exception as e:  # a reescrita falhar não derruba um folheto já aprovado
            registro["erro"] = str(e)
        registro["aceita"] = nova is not None and chave_juizo(nova, cfg.prioridade) < chave_juizo(avaliacao, cfg.prioridade)
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
    fim = {"etapa": "fim", "id": slug, "entra": entra, "motivo": motivo, "titulo": fato.titulo, "autor": autor or None,
           "url": url or None, "fonte": origem["fonte"], "avaliacao": avaliacao,
           "estrofes": estrofes, "rodadas": rodada, "duvidas": duvidas,
           "arquivos": {**arquivos, "caderno": f"caderno/{slug}.json"},
           "custo": log["custo_estimado_usd"]}
    log["eventos"] = [*ja_enviados, fim]
    (PASTAS["caderno"] / f"{slug}.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    yield fim


# ------------------------------------------------------------------- util
def _versos_de(g: "Poema") -> list[list[str]]:
    return [[limpar_verso(v) for v in e.versos if limpar_verso(v)] for e in g.estrofes]


def _forma_certa(estrofes: list[list[str]], cfg: Config) -> bool:
    return len(estrofes) == cfg.estrofes and all(len(vs) == 6 for vs in estrofes)


RECENTES = 30


def _poemas_recentes() -> list[list[list[str]]]:
    """Os poemas finais das últimas gerações, para o rodízio do dicionário."""
    poemas = []
    for f in sorted(PASTAS["caderno"].glob("*.json"), reverse=True)[:RECENTES]:
        with contextlib.suppress(OSError, ValueError):
            poemas.append(json.loads(f.read_text(encoding="utf-8")).get("estrofes_finais") or [])
    return poemas


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
    base = f"{datetime.now():%Y%m%d-%H%M%S}-{s}"
    # duas pessoas gerando a mesma notícia no mesmo segundo não podem sobrescrever uma à outra
    slug, n = base, 2
    while (PASTAS["caderno"] / f"{slug}.json").exists():
        slug, n = f"{base}-{n}", n + 1
    return slug
