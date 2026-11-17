"""Narração da sextilha pela ElevenLabs, com voz de sotaque nordestino.

A chave do professor (ELEVENLABS_API_KEY) só serve às contas de admin; quem mais quiser
ouvir põe a própria chave nas Configurações do site, e ela vai num cabeçalho a cada pedido,
sem ser gravada. O áudio fica no volume (narracao/<id>.mp3): gerado uma vez, qualquer um
ouve de graça depois.

Voz, modelo e marcação de sotaque vêm do ambiente para trocar sem mexer no código. As vozes
foram escolhidas na biblioteca pública da ElevenLabs pelo sotaque declarado (17/11).
"""

import asyncio
import base64
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


def montar(estrofes: list[list[str]]) -> tuple[str, list[tuple[int, int, int, int, str]]]:
    """O texto enviado (cada verso termina em pausa curta, cada estrofe em pausa longa, como se
    recita cordel) e onde cada verso ficou nele: (estrofe, verso, início no texto, recuo do
    verso na tela, verso limpo). É assim que o tempo de cada letra volta para a palavra na tela."""
    corpo = f"{MARCACAO}\n" if MARCACAO and MODELO.startswith(("eleven_v3", "eleven_v4")) else ""
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


def texto(estrofes: list[list[str]]) -> str:
    return montar(estrofes)[0]


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


def custo(estrofes: list[list[str]]) -> int:
    """Créditos estimados: 1 por caractere (0,5 nos modelos turbo/flash)."""
    meio = any(k in MODELO for k in ("turbo", "flash", "conversational"))
    return round(len(texto(estrofes)) * (0.5 if meio else 1))


def _sintetizar(corpo: str, chave: str) -> tuple[bytes, dict | None, int | None]:
    """O áudio, o tempo de cada letra (variante with-timestamps, mesmo preço) e o custo cobrado."""
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOZ}/with-timestamps?output_format=mp3_44100_128",
        json.dumps({"text": corpo, "model_id": MODELO}).encode(),
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


async def sintetizar(estrofes: list[list[str]], chave: str) -> tuple[bytes, int, dict | None]:
    """O áudio, os créditos que custou (os cobrados, ou a estimativa) e o tempo de cada palavra."""
    corpo, posicoes = montar(estrofes)
    if len(corpo) > MAX_CARACTERES:
        raise ErroNarracao(422, f"O poema é longo demais para narrar ({len(corpo)} caracteres).")
    audio, alinhamento, cobrado = await asyncio.to_thread(_sintetizar, corpo, chave)
    return audio, cobrado if cobrado is not None else custo(estrofes), tempos_das_palavras(alinhamento, corpo, posicoes)
