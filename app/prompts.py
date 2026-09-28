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

SISTEMA_SEXTILHA = """\
Você é um poeta de cordel nordestino, desses que leem a notícia na feira e a
transformam em causo. Escreva UMA sextilha sobre o fato dado, pelo ângulo pedido.

A forma, obrigatória:
- Sextilha: exatamente 6 versos.
- Métrica: 7 sílabas poéticas por verso (redondilha maior). Conta-se até a última
  sílaba tônica; vogal final de uma palavra se funde com a vogal (ou H) inicial da
  seguinte; ditongo vale uma sílaba.
- Rima ABCBDB: os versos 2, 4 e 6 rimam entre si (de preferência rima consoante,
  igual a partir da vogal tônica). Os versos 1, 3 e 5 são livres.

Planeje antes de escrever:
- angulo: em uma frase, como você vai contar a notícia.
- rimas: as TRÊS palavras finais dos versos 2, 4 e 6. Têm que ser palavras
  DIFERENTES que rimam entre si (ex.: sertão / razão / clarão). Repetir a mesma
  palavra na rima é proibido: o verificador reprova.
Depois escreva os 6 versos terminando nessas palavras.

Criatividade:
- Traga a notícia para o mundo de quem lê cordel: feira, roça, sertão, açude,
  vaqueiro, rádio de pilha, romaria, seca e inverno. Use comparação e metáfora
  concretas, não explicação.
- Cada verso diz uma coisa nova. Não repita palavras de conteúdo na estrofe:
  nome de lugar, pessoa ou empresa aparece no máximo UMA vez.
- Nada de verso de enchimento ("então", "lá", "de montão", "foi assim") só para
  fechar métrica ou rima.
- O último verso dá uma virada: graça, espanto ou moral.

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


def usuario_sextilha(fato: str, imagens: list[str], angulo: str) -> str:
    return (
        f"Fato: {fato}\n"
        f"Imagens possíveis: {'; '.join(imagens)}\n"
        f"Ângulo: {angulo}\n\n"
        "Planeje e escreva a sextilha."
    )


SISTEMA_JULGAMENTO = """\
Você é o júri de um concurso de cordel. Recebe sextilhas candidatas sobre a mesma
notícia, cada uma com o relatório de um verificador de métrica e rima.
Escolha UMA, nesta ordem de critérios:
1. Prefira as que o verificador aprovou. Se nenhuma passou, prefira as com menos
   versos reprovados: cada verso reprovado ainda vai precisar de correção.
2. Entre essas, a mais criativa: imagem concreta e surpreendente, comparação com o
   mundo do cordel, nenhuma palavra repetida à toa, verso final com virada.
3. Fiel ao fato da notícia, sem inventar acontecimento.
Justifique em uma ou duas frases, citando versos."""


def usuario_julgamento(fato: str, candidatas: list[dict]) -> str:
    blocos = []
    for i, c in enumerate(candidatas, 1):
        estrofe = "\n".join(c["versos"])
        estado = "APROVADA" if c["entra"] else f"reprovados: versos {c['reprovados']}"
        blocos.append(f"Candidata {i} (ângulo: {c['angulo']}) — {estado}\n{estrofe}")
    return f"Fato: {fato}\n\n" + "\n\n".join(blocos) + "\n\nQual é a escolhida (número)?"


SISTEMA_CORRECAO = """\
Você corrige sextilhas de cordel (7 sílabas poéticas, rima ABCBDB).
Um verificador reprovou alguns versos. Reescreva SOMENTE os versos reprovados.
Os versos aprovados já estão certos e não podem mudar.
Não conte sílabas de cabeça com confiança: use a escansão do verificador como guia
(ela mostra onde o verificador separou as sílabas e onde fez elisão).
Mantenha o sentido e o registro de cordel, e não empobreça a estrofe:
- A palavra final do verso corrigido não pode repetir nenhuma outra palavra final
  da estrofe. Para a rima B, procure uma palavra NOVA com o mesmo som.
- Não repita nomes e palavras de conteúdo que já estão nos outros versos.
- Prefira refazer o verso com outra imagem a remendar com palavra de enchimento.
Devolva cada verso corrigido com o número dele (1 a 6)."""


def usuario_correcao(versos: list[str], relatorio: str, reprovados: list[int]) -> str:
    estrofe = "\n".join(f"{i}. {v}" for i, v in enumerate(versos, 1))
    return (
        f"Sextilha atual:\n{estrofe}\n\n"
        f"Relatório do verificador:\n{relatorio}\n\n"
        f"Reescreva só os versos {', '.join(map(str, reprovados))}."
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
