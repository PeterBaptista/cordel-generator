"""Narração da sextilha pela ElevenLabs, com voz de sotaque nordestino.

A chave do professor (ELEVENLABS_API_KEY) só serve às contas de admin; quem mais quiser
ouvir põe a própria chave nas Configurações do site, e ela vai num cabeçalho a cada pedido,
sem ser gravada. O áudio fica no volume (narracao/<id>.mp3): gerado uma vez, qualquer um
ouve de graça depois.

Voz, modelo e marcação de sotaque vêm do ambiente para trocar sem mexer no código. As vozes
foram escolhidas na biblioteca pública da ElevenLabs pelo sotaque declarado (17/11).
"""

import asyncio
import json
import os
import re
import urllib.error
import urllib.request

CHAVE_PROFESSOR = os.getenv("ELEVENLABS_API_KEY", "").strip()
VOZ = os.getenv("CORDEL_VOZ", "bOfmGBubwU6YlrKXeRkh")  # Cicero: "authentic Northeastern Brazilian accent"
MODELO = os.getenv("CORDEL_VOZ_MODELO", "eleven_v4")
# os modelos v3 e v4 aceitam marcação de voz entre colchetes; ela puxa o sotaque e o ritmo
MARCACAO = os.getenv("CORDEL_VOZ_MARCACAO", "[strong Northeastern Brazilian accent, cordel reciter, rhythmic]")
MAX_CARACTERES = 2500  # 6 estrofes dão uns 1.300; o resto é folga, não convite

CHAVE_OK = re.compile(r"[A-Za-z0-9_\-]{20,200}")


class ErroNarracao(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


def texto(estrofes: list[list[str]]) -> str:
    """Cada verso termina em pausa curta e cada estrofe em pausa longa, como se recita cordel."""
    blocos = []
    for vs in estrofes:
        versos = [re.sub(r"[\s,;:.]+$", "", v.strip()) for v in vs if v.strip()]
        if versos:
            blocos.append(",\n".join(versos) + ".")
    corpo = "\n\n".join(blocos)
    if MARCACAO and MODELO.startswith(("eleven_v3", "eleven_v4")):
        corpo = f"{MARCACAO}\n{corpo}"
    return corpo


def custo(estrofes: list[list[str]]) -> int:
    """Créditos estimados: 1 por caractere (0,5 nos modelos turbo/flash)."""
    meio = any(k in MODELO for k in ("turbo", "flash", "conversational"))
    return round(len(texto(estrofes)) * (0.5 if meio else 1))


def _sintetizar(corpo: str, chave: str) -> tuple[bytes, int | None]:
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOZ}?output_format=mp3_44100_128",
        json.dumps({"text": corpo, "model_id": MODELO}).encode(),
        {"xi-api-key": chave, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            # a ElevenLabs diz quantos créditos a chamada custou; sem o cabeçalho, fica a estimativa
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
        if e.code in (402, 429) or "quota" in str(detalhe).lower():
            raise ErroNarracao(402, "A conta da ElevenLabs está sem créditos (ou no limite de pedidos).") from None
        raise ErroNarracao(502, f"A ElevenLabs não gerou o áudio ({e.code}): {detalhe or 'sem detalhe'}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErroNarracao(504, f"Não consegui falar com a ElevenLabs: {e}") from None


async def sintetizar(estrofes: list[list[str]], chave: str) -> tuple[bytes, int]:
    """O áudio e os créditos que custou (os cobrados, ou a estimativa se a API não disser)."""
    corpo = texto(estrofes)
    if len(corpo) > MAX_CARACTERES:
        raise ErroNarracao(422, f"O poema é longo demais para narrar ({len(corpo)} caracteres).")
    audio, cobrado = await asyncio.to_thread(_sintetizar, corpo, chave)
    return audio, cobrado if cobrado is not None else custo(estrofes)
