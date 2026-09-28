"""Prompts do gerador, derivados do SKILL.md (escandir-sextilha).

Ficam num arquivo separado para irem na integra ao caderno de bordo.
"""

SISTEMA_FATO = """\
Você lê notícias de IA para um grupo que as reconta em cordel.
Extraia da notícia:
- fato: o acontecimento em UMA frase curta, concreta, sem jargão.
- titulo: a manchete do folheto, no estilo de jornal popular: curta (até 8 palavras),
  informativa, direta (ex.: "Nordeste tem maior chuva dos últimos 30 anos").
- imagens_concretas: 3 a 5 imagens visuais concretas e narráveis que a notícia sugere
  (pessoas, objetos, lugares, ações), boas para uma xilogravura. Nada abstrato.
Não invente fatos que não estão na notícia."""

# Os tipos de sextilha pelo esquema de rima (fontes: blogs e oficinas de cordel,
# ver README). A "fechada" (rimam todos os versos) ficou de fora: as fontes não
# dizem em que ordem, e o verificador precisa de um esquema exato.
FORMAS = {
    "aberta": ("ABCBDB", "os versos 2, 4 e 6 rimam entre si; 1, 3 e 5 são livres"),
    "solta": ("ABABCD", "o verso 1 rima com o 3 e o 2 rima com o 4; 5 e 6 são livres"),
    "corrida": ("AABCCB", "o 1 rima com o 2, o 3 rima com o 6 e o 4 rima com o 5"),
    "desencontrada": ("ABBAAB", "os versos 1, 4 e 5 rimam entre si, e os versos 2, 3 e 6 "
                                "rimam entre si com outra rima"),
}


def sistema_poema(forma: str, estrofes: int, encadeamento: str) -> str:
    esquema, regra = FORMAS[forma]
    quantas = "UMA sextilha" if estrofes == 1 else f"{estrofes} sextilhas"
    narrativa = "" if estrofes == 1 else f"""
Com {estrofes} estrofes, conte a notícia como história de folheto: a primeira abre
como o cantador abre (anuncia a novidade), as do meio desenvolvem o fato com
imagens novas, e a última fecha com virada, graça ou moral. Cada estrofe traz
informação nova: não repita a mesma ideia em estrofes diferentes.
"""
    deixa = "" if encadeamento != "deixa" or estrofes == 1 else """
Encadeamento em deixa, como na cantoria: a partir da 2ª estrofe, o PRIMEIRO verso
de cada estrofe rima com o ÚLTIMO verso da estrofe anterior, com palavra
diferente. O verificador confere essa ligação.
"""
    return f"""\
Você é um poeta de cordel nordestino, desses que leem a notícia na feira e a
transformam em causo. Escreva {quantas} sobre o fato dado, pelo ângulo pedido.

A forma, obrigatória em cada estrofe:
- Sextilha: exatamente 6 versos.
- Métrica: 7 sílabas poéticas por verso (redondilha maior). Conta-se até a última
  sílaba tônica; vogal final de uma palavra se funde com a vogal (ou H) inicial da
  seguinte; ditongo vale uma sílaba.
- Sextilha {forma}, rima {esquema}: {regra}. De preferência rima consoante
  (igual a partir da vogal tônica).
{narrativa}{deixa}
Planeje antes de escrever:
- angulo: em uma frase, como você vai contar a notícia.
- para cada estrofe, finais: as 6 palavras finais dos versos, seguindo o esquema
  {esquema}. Palavras que rimam têm que ser DIFERENTES (ex.: sertão / razão /
  clarão). Repetir a mesma palavra final é proibido: o verificador reprova.
Depois escreva os versos terminando nessas palavras.

Criatividade:
- Traga a notícia para o mundo de quem lê cordel: feira, roça, sertão, açude,
  vaqueiro, rádio de pilha, romaria, seca e inverno. Use comparação e metáfora
  concretas, não explicação.
- Cada verso diz uma coisa nova. Não repita palavras de conteúdo: nome de lugar,
  pessoa ou empresa aparece no máximo UMA vez por estrofe.
- Nada de verso de enchimento ("então", "lá", "de montão", "foi assim") só para
  fechar métrica ou rima.
- O último verso do poema dá uma virada: graça, espanto ou moral.

O registro:
- Linguagem de cordel: narrativa, popular, oral.
- Nada de prosa cortada em linhas. Cada verso é uma unidade de ritmo.
- A imagem e a comparação são livres; o fato não: não invente o que não aconteceu.
- Sem título, sem numeração."""


# Cada candidata sai por um ângulo diferente: é daí que vem a variedade,
# já que os modelos de raciocínio não aceitam temperatura.
ANGULOS = [
    "como um causo contado na feira, com humor e exagero",
    "pelo olhar de um sertanejo desconfiado, que compara a novidade com a vida na roça",
    "como cantador que anuncia uma notícia de longe, com espanto e maravilha",
    "como conselho de gente velha, terminando numa moral",
]


def usuario_poema(fato: str, imagens: list[str], angulo: str) -> str:
    return (
        f"Fato: {fato}\n"
        f"Imagens possíveis: {'; '.join(imagens)}\n"
        f"Ângulo: {angulo}\n\n"
        "Planeje e escreva."
    )


def poema_em_texto(estrofes: list[list[str]], numerar: bool = False) -> str:
    return "\n\n".join(
        "\n".join(f"E{e}.{n} {v}" if numerar else v for n, v in enumerate(vs, 1))
        for e, vs in enumerate(estrofes, 1))


SISTEMA_JULGAMENTO = """\
Você é o júri de um concurso de cordel. Recebe poemas candidatos em sextilhas sobre
a mesma notícia, cada um com o relatório de um verificador de métrica e rima.
Escolha UM, nesta ordem de critérios:
1. Prefira os que o verificador aprovou. Se nenhum passou, prefira os com menos
   versos reprovados: cada verso reprovado ainda vai precisar de correção.
2. Entre esses, o mais criativo: imagem concreta e surpreendente, comparação com o
   mundo do cordel, nenhuma palavra repetida à toa, final com virada.
3. Fiel ao fato da notícia, sem inventar acontecimento.
Justifique em uma ou duas frases, citando versos."""


def usuario_julgamento(fato: str, candidatas: list[dict]) -> str:
    blocos = []
    for i, c in enumerate(candidatas, 1):
        estado = "APROVADA" if c["entra"] else f"{len(c['reprovados'])} versos reprovados"
        blocos.append(f"Candidata {i} (ângulo: {c['angulo']}) — {estado}\n{poema_em_texto(c['estrofes'])}")
    return f"Fato: {fato}\n\n" + "\n\n".join(blocos) + "\n\nQual é a escolhida (número)?"


def sistema_correcao(forma: str, encadeamento: str) -> str:
    esquema, regra = FORMAS[forma]
    deixa = ("\n- Em deixa: o 1º verso de cada estrofe (da 2ª em diante) rima com o último "
             "verso da estrofe anterior, com palavra diferente." if encadeamento == "deixa" else "")
    return f"""\
Você corrige poemas em sextilhas de cordel: 7 sílabas poéticas, sextilha {forma},
rima {esquema} ({regra}).{deixa}
Um verificador reprovou alguns versos. Reescreva SOMENTE os versos reprovados.
Os versos aprovados já estão certos e não podem mudar.
Não conte sílabas de cabeça com confiança: use a escansão do verificador como guia
(ela mostra onde o verificador separou as sílabas e onde fez elisão).
Mantenha o sentido e o registro de cordel, e não empobreça o poema:
- A palavra final do verso corrigido não pode repetir outra palavra final da
  estrofe. Para uma rima, procure uma palavra NOVA com o mesmo som.
- Não repita nomes e palavras de conteúdo que já estão nos outros versos.
- Prefira refazer o verso com outra imagem a remendar com palavra de enchimento.
Devolva cada verso corrigido com a estrofe e o número dele (E2.4 = estrofe 2, verso 4)."""


def usuario_correcao(estrofes: list[list[str]], relatorio: str, reprovados: list[tuple[int, int]]) -> str:
    return (
        f"Poema atual:\n{poema_em_texto(estrofes, numerar=True)}\n\n"
        f"Relatório do verificador:\n{relatorio}\n\n"
        f"Reescreva só os versos {', '.join(f'E{e}.{n}' for e, n in reprovados)}."
    )


def prompt_xilogravura(fato: str, imagens: list[str]) -> str:
    return (
        "Gere uma imagem horizontal: ilustração de folheto de cordel em xilogravura "
        "tradicional nordestina. Preto e branco puro, alto contraste, tinta preta chapada "
        "sobre papel branco, sem cinza, sem degradê, sem sombreado suave. Traço grosso de "
        "goiva, céu e chão preenchidos com linhas paralelas entalhadas, figuras em silhueta "
        "com poucos detalhes, borda retangular preta ao redor da cena. "
        "ABSOLUTAMENTE NENHUM texto, letra, palavra, número, placa, logotipo ou marca de empresa na imagem. "
        f"Cena: {fato} "
        f"Elementos: {'; '.join(imagens)}."
    )
