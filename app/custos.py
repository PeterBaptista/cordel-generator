"""Custo estimado de cada geração, a partir dos tokens registrados no caderno.

Preços em US$ por 1M de tokens, tier standard, conferidos em
https://developers.openai.com/api/docs/pricing em 28/09/2026. Se a OpenAI mudar
os preços, atualize esta tabela: o custo é recalculado a cada leitura do log.
"""

PRECOS = {
    # modelo: (entrada, entrada em cache, saída) — também é a lista do seletor da página
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-5.6-sol": (4.00, 0.40, 20.00),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.5": (5.00, 0.50, 30.00),
    "gpt-5.4": (2.50, 0.25, 15.00),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
    "gpt-5-mini": (0.25, 0.025, 2.00),
    "gpt-5-nano": (0.05, 0.005, 0.40),
}
# a ferramenta de imagem cobra texto e imagem separados
PRECOS_IMAGEM = {
    # modelo: (texto de entrada, imagem de entrada, imagem de saída)
    "gpt-image-2": (5.00, 8.00, 30.00),
}

ETAPAS = {
    "Você lê notícias": "fato",
    "Você é um poeta": "candidata",
    "Você é o júri": "júri",
    "Você corrige": "correção",
}


def _modelo(nome: str) -> str:
    """'openai:gpt-5.5 (…)' -> 'gpt-5.5'"""
    return nome.split(":")[-1].split(" ")[0]


def etapa(chamada: dict) -> str:
    if "etapa" in chamada:
        return chamada["etapa"]
    if "image_generation" in chamada.get("modelo", ""):
        return "xilogravura"
    sistema = chamada.get("sistema", "")
    return next((v for k, v in ETAPAS.items() if sistema.startswith(k)), "outra")


def custo_chamada(chamada: dict) -> dict:
    """Custo de uma chamada: modelo de texto + (se houver) a geração da imagem."""
    t = chamada.get("tokens") or {}
    modelo = _modelo(chamada.get("modelo", ""))
    entrada, cache, saida = PRECOS.get(modelo, (0, 0, 0))
    cacheados = t.get("cache_read_tokens") or 0
    texto = (((t.get("input_tokens") or 0) - cacheados) * entrada
             + cacheados * cache + (t.get("output_tokens") or 0) * saida) / 1e6

    imagem, medida = 0.0, True
    if etapa(chamada) == "xilogravura":
        ti = chamada.get("tokens_imagem")
        if ti:
            p_txt, p_img_in, p_img_out = PRECOS_IMAGEM.get(chamada.get("modelo_imagem", "gpt-image-2"),
                                                           PRECOS_IMAGEM["gpt-image-2"])
            imagem = (ti.get("texto_entrada", 0) * p_txt + ti.get("imagem_entrada", 0) * p_img_in
                      + ti.get("imagem_saida", 0) * p_img_out) / 1e6
        else:
            medida = False  # geração antiga: o uso da imagem não foi registrado
    return {"etapa": etapa(chamada), "texto": texto, "imagem": imagem,
            "total": texto + imagem, "imagem_medida": medida}


def resumo(log: dict) -> dict:
    chamadas = [custo_chamada(c) for c in log.get("chamadas", [])]
    # a chamada da xilogravura (hospedeiro + imagem) conta inteira como imagem
    xilo = [c for c in chamadas if c["etapa"] == "xilogravura"]
    return {
        "texto": sum(c["total"] for c in chamadas if c["etapa"] != "xilogravura"),
        "imagem": sum(c["total"] for c in xilo),
        "tem_imagem": bool(xilo),
        "total": sum(c["total"] for c in chamadas),
        "imagem_medida": all(c["imagem_medida"] for c in chamadas),
        "chamadas": chamadas,
    }
