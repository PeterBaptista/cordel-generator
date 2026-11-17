"""Narração da sextilha pela ElevenLabs, com voz de sotaque nordestino.

A chave do professor (ELEVENLABS_API_KEY) só serve às contas de admin; quem mais quiser
ouvir põe a própria chave nas Configurações do site, e ela vai num cabeçalho a cada pedido,
sem ser gravada. O áudio fica no volume (narracao/<id>.mp3): gerado uma vez, qualquer um
ouve de graça depois.

Quem narra escolhe a voz no site, entre as de VOZES (com a amostra de cada uma); o padrão
vem de CORDEL_VOZ_PADRAO. As vozes foram escolhidas na biblioteca pública da ElevenLabs pelo
sotaque nordestino declarado (17/11).
"""

import asyncio
import base64
import json
import os
import re
import urllib.error
import urllib.request

CHAVE_PROFESSOR = os.getenv("ELEVENLABS_API_KEY", "").strip()
# os modelos v3 e v4 aceitam marcação de voz entre colchetes; ela puxa o sotaque e o ritmo
MARCACAO = "[strong Northeastern Brazilian accent, cordel reciter, rhythmic]"

# a amostra de cada uma é a mesma estrofe (Rec'n'Play), em app/static/vozes/
VOZES = {
    "cicero-sotaque": {"nome": "Cicero, sotaque reforçado", "voz": "bOfmGBubwU6YlrKXeRkh", "modelo": "eleven_v4",
                       "marcacao": True, "sobre": "jovem, nordestino, com a marcação de sotaque forte e ritmo de cordel"},
    "anderson-sotaque": {"nome": "Anderson Carlos, sotaque reforçado", "voz": "SAA76GSoxwYgqvFLpT5j", "modelo": "eleven_v4",
                         "marcacao": True, "sobre": "meia-idade, nordestino, voz de narrador, com a marcação de sotaque"},
    "cicero": {"nome": "Cicero", "voz": "bOfmGBubwU6YlrKXeRkh", "modelo": "eleven_v4_turbo", "marcacao": False,
               "sobre": "jovem, nordestino, conversado (metade do custo)"},
    "andre": {"nome": "Andre Ambrosio", "voz": "npTHTbBmWiNxOlMiBxaa", "modelo": "eleven_v4_turbo", "marcacao": False,
              "sobre": "meia-idade, nordestino (metade do custo)"},
    "michael": {"nome": "Michael Almeida", "voz": "UP5aPvvfM4UCXZrr3fdX", "modelo": "eleven_v4_turbo", "marcacao": False,
                "sobre": "jovem, cearense (metade do custo)"},
    "anderson": {"nome": "Anderson Carlos", "voz": "SAA76GSoxwYgqvFLpT5j", "modelo": "eleven_v4_turbo", "marcacao": False,
                 "sobre": "meia-idade, nordestino, voz de narrador (metade do custo)"},
}
AMOSTRAS = {"cicero-sotaque": "cicero-v4-sotaque", "anderson-sotaque": "anderson-v4-sotaque", "cicero": "cicero-v4turbo",
            "andre": "andre-v4turbo", "michael": "michael-v4turbo", "anderson": "anderson-v4turbo"}
PADRAO = os.getenv("CORDEL_VOZ_PADRAO", "cicero-sotaque")
if PADRAO not in VOZES:
    PADRAO = "cicero-sotaque"


def voz(chave: str | None) -> tuple[str, dict]:
    """A voz pedida, ou a padrão."""
    k = chave if chave in VOZES else PADRAO
    return k, VOZES[k]


def catalogo() -> list[dict]:
    return [{"id": k, "nome": v["nome"], "sobre": v["sobre"], "amostra": f"static/vozes/{AMOSTRAS[k]}.mp3",
             "metade": "turbo" in v["modelo"], "padrao": k == PADRAO} for k, v in VOZES.items()]
MAX_CARACTERES = 2500  # 6 estrofes dão uns 1.300; o resto é folga, não convite

CHAVE_OK = re.compile(r"[A-Za-z0-9_\-]{20,200}")


class ErroNarracao(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


def montar(estrofes: list[list[str]], preset: dict | None = None) -> tuple[str, list[tuple[int, int, int, int, str]]]:
    """O texto enviado (cada verso termina em pausa curta, cada estrofe em pausa longa, como se
    recita cordel) e onde cada verso ficou nele: (estrofe, verso, início no texto, recuo do
    verso na tela, verso limpo). É assim que o tempo de cada letra volta para a palavra na tela."""
    preset = preset or voz(None)[1]
    corpo = f"{MARCACAO}\n" if preset["marcacao"] and preset["modelo"].startswith(("eleven_v3", "eleven_v4")) else ""
    posicoes, primeira = [], True
    for e, vs in enumerate(estrofes):
        versos = [(n, v, re.sub(r"[\s,;:.]+$", "", v.strip())) for n, v in enumerate(vs) if v.strip()]
        if not versos:
            continue
        if not primeira:
            corpo += "\n\n"
        primeira = False
        for k, (n, v, limpo) in enumerate(versos):
            posicoes.append((e, n, len(corpo), len(v) - len(v.lstrip()), limpo))
            corpo += limpo + ("." if k == len(versos) - 1 else ",\n")
    return corpo, posicoes


def texto(estrofes: list[list[str]], preset: dict | None = None) -> str:
    return montar(estrofes, preset)[0]


def tempos_das_palavras(alinhamento: dict | None, corpo: str, posicoes: list) -> dict | None:
    """[estrofe, verso, início, fim (no texto do verso na tela), segundo inicial, segundo final]
    de cada palavra. Se o alinhamento não bater letra a letra com o texto, não arrisca: a página
    estima pela duração do áudio."""
    letras = (alinhamento or {}).get("characters") or []
    ini = (alinhamento or {}).get("character_start_times_seconds") or []
    fim = (alinhamento or {}).get("character_end_times_seconds") or []
    if "".join(letras) != corpo or not (len(ini) == len(fim) == len(corpo)):
        return None
    palavras = []
    for e, n, comeco, recuo, limpo in posicoes:
        for m in re.finditer(r"\S+", limpo):
            a, b = m.span()
            palavras.append([e, n, recuo + a, recuo + b, round(ini[comeco + a], 3), round(fim[comeco + b - 1], 3)])
    return {"versao": 1, "duracao": round(fim[-1], 3) if fim else 0, "palavras": palavras}


def custo(estrofes: list[list[str]], preset: dict | None = None) -> int:
    """Créditos estimados: 1 por caractere (0,5 nos modelos turbo/flash); a marcação não é cobrada."""
    preset = preset or voz(None)[1]
    meio = any(k in preset["modelo"] for k in ("turbo", "flash", "conversational"))
    falado = len(texto(estrofes, preset)) - (len(MARCACAO) + 1 if preset["marcacao"] else 0)
    return round(falado * (0.5 if meio else 1))


def _sintetizar(corpo: str, chave: str, preset: dict) -> tuple[bytes, dict | None, int | None]:
    """O áudio, o tempo de cada letra (variante with-timestamps, mesmo preço) e o custo cobrado."""
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{preset['voz']}/with-timestamps?output_format=mp3_44100_128",
        json.dumps({"text": corpo, "model_id": preset["modelo"]}).encode(),
        {"xi-api-key": chave, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            # a ElevenLabs diz quantos créditos a chamada custou; sem o cabeçalho, fica a estimativa
            cobrado = r.headers.get("character-cost")
            d = json.load(r)
            return (base64.b64decode(d["audio_base64"]), d.get("alignment"),
                    int(cobrado) if cobrado and cobrado.isdigit() else None)
    except urllib.error.HTTPError as e:
        try:
            detalhe = json.loads(e.read()).get("detail")
            detalhe = detalhe.get("message") if isinstance(detalhe, dict) else detalhe
        except ValueError:
            detalhe = None
        if e.code == 401:
            raise ErroNarracao(401, "A ElevenLabs recusou a chave. Confira a chave em Configurações.") from None
        if e.code in (402, 429) or "quota" in str(detalhe).lower():
            raise ErroNarracao(402, "A conta da ElevenLabs está sem créditos (ou no limite de pedidos).") from None
        raise ErroNarracao(502, f"A ElevenLabs não gerou o áudio ({e.code}): {detalhe or 'sem detalhe'}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErroNarracao(504, f"Não consegui falar com a ElevenLabs: {e}") from None


async def sintetizar(estrofes: list[list[str]], chave: str, preset: dict) -> tuple[bytes, int, dict | None]:
    """O áudio, os créditos que custou (os cobrados, ou a estimativa) e o tempo de cada palavra."""
    corpo, posicoes = montar(estrofes, preset)
    if len(corpo) > MAX_CARACTERES:
        raise ErroNarracao(422, f"O poema é longo demais para narrar ({len(corpo)} caracteres).")
    audio, alinhamento, cobrado = await asyncio.to_thread(_sintetizar, corpo, chave, preset)
    return (audio, cobrado if cobrado is not None else custo(estrofes, preset),
            tempos_das_palavras(alinhamento, corpo, posicoes))
