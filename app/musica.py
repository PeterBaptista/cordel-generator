"""Música de fundo para a narração, pela API de música da ElevenLabs (Eleven Music).

Toca baixinho por trás do narrador, então é sempre instrumental e do tamanho da narração
(mais uns segundos de respiro). Custa ~900 créditos por minuto (15 por segundo), bem mais que a
narração: por isso o tamanho é limitado por MAX_SEGUNDOS. As mesmas regras de chave da
narração valem aqui: a do professor só para admin; os outros usam a própria.

Quem gera escolhe estilo, clima, andamento e instrumentos, ou deixa a IA da ElevenLabs escolher
a partir do assunto da notícia ("ia" em tudo).
"""

import asyncio
import json
import os
import urllib.error
import urllib.request

from .narracao import ErroNarracao

MODELO = os.getenv("CORDEL_MUSICA_MODELO", "music_v1")
CREDITOS_POR_SEGUNDO = 15  # "Eleven Music: 900 credits per minute" (página de preços, 19/11)
MIN_SEGUNDOS, MAX_SEGUNDOS = 10, int(os.getenv("CORDEL_MUSICA_MAX_SEGUNDOS", "120"))
FOLGA_SEGUNDOS = 3  # a música começa junto e termina um pouco depois da última palavra

# o que a tela oferece; "ia" deixa a escolha com o modelo
ESTILOS = {
    "ia": None,
    "baiao": "baião (Brazilian Northeastern baião)",
    "forro": "forró pé-de-serra",
    "xote": "xote, slow and swaying",
    "repente": "repente / viola caipira, like a cordel cantoria",
    "aboio": "aboio-inspired, open and pastoral, sertão landscape",
    "maracatu": "maracatu-inspired percussion, soft",
}
CLIMAS = {"ia": None, "alegre": "joyful, playful", "epico": "epic, wide, like a ballad of the sertão",
          "melancolico": "melancholic, nostalgic", "tenso": "tense, suspenseful", "calmo": "calm, warm"}
ANDAMENTOS = {"ia": None, "lento": "slow tempo (around 70 BPM)", "medio": "medium tempo (around 95 BPM)",
              "rapido": "fast tempo (around 120 BPM)"}
INSTRUMENTOS = {"ia": None, "sanfona": "accordion (sanfona), zabumba and triangle",
                "viola": "viola caipira and pandeiro", "rabeca": "rabeca (folk fiddle) and pífano (fife)",
                "percussao": "light zabumba, triangle and agogô only"}

BASE = ("Instrumental background music to sit under a spoken Brazilian cordel recitation. "
        "No vocals, no singing. Keep it soft and low in the mix, with steady dynamics, so the voice stays clear.")


def opcoes() -> dict:
    return {"estilo": list(ESTILOS), "clima": list(CLIMAS), "andamento": list(ANDAMENTOS),
            "instrumentos": list(INSTRUMENTOS), "max_segundos": MAX_SEGUNDOS,
            "creditos_por_segundo": CREDITOS_POR_SEGUNDO}


def prompt(titulo: str, escolha: dict) -> str:
    """O texto pedido ao modelo. O assunto vai sempre; o resto, só o que a pessoa escolheu."""
    partes = [BASE, f"The poem is about: {titulo}."]
    pedidos = [d[escolha.get(k) or "ia"] for k, d in
               (("estilo", ESTILOS), ("clima", CLIMAS), ("andamento", ANDAMENTOS), ("instrumentos", INSTRUMENTOS))
               if d.get(escolha.get(k) or "ia")]
    if pedidos:
        partes.append("Style: " + "; ".join(pedidos) + ".")
    if not escolha.get("estilo") or escolha.get("estilo") == "ia":
        partes.append("Choose freely the Brazilian Northeastern genre, instruments, mood and tempo that best fit the story.")
    return " ".join(partes)


def segundos_para(duracao_narracao: float) -> int:
    return int(min(MAX_SEGUNDOS, max(MIN_SEGUNDOS, round(duracao_narracao + FOLGA_SEGUNDOS))))


def custo(segundos: int) -> int:
    return segundos * CREDITOS_POR_SEGUNDO


def _compor(texto: str, segundos: int, chave: str) -> tuple[bytes, int | None]:
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128",
        json.dumps({"prompt": texto, "music_length_ms": segundos * 1000, "model_id": MODELO,
                    "force_instrumental": True}).encode(),
        {"xi-api-key": chave, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            cobrado = r.headers.get("character-cost")
            return r.read(), int(cobrado) if cobrado and cobrado.isdigit() else None
    except urllib.error.HTTPError as e:
        try:
            detalhe = json.loads(e.read()).get("detail")
            detalhe = detalhe.get("message") if isinstance(detalhe, dict) else detalhe
        except ValueError:
            detalhe = None
        if e.code == 401:
            raise ErroNarracao(401, "A ElevenLabs recusou a chave. Confira a chave em Configurações.") from None
        if e.code in (402, 429) or "quota" in str(detalhe).lower() or "credit" in str(detalhe).lower():
            raise ErroNarracao(402, "A conta da ElevenLabs está sem créditos para música (ou no limite de pedidos).") from None
        if e.code == 403:
            raise ErroNarracao(403, f"A ElevenLabs não liberou música para esta conta: {detalhe or 'sem detalhe'}") from None
        raise ErroNarracao(502, f"A ElevenLabs não gerou a música ({e.code}): {detalhe or 'sem detalhe'}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErroNarracao(504, f"Não consegui falar com a ElevenLabs: {e}") from None


async def compor(titulo: str, escolha: dict, duracao_narracao: float, chave: str) -> tuple[bytes, int, int, str]:
    """O áudio, os créditos (cobrados, ou a estimativa), os segundos e o prompt usado."""
    seg = segundos_para(duracao_narracao)
    texto = prompt(titulo, escolha)
    audio, cobrado = await asyncio.to_thread(_compor, texto, seg, chave)
    return audio, cobrado if cobrado is not None else custo(seg), seg, texto
