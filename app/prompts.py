"""Prompts do gerador, derivados do SKILL.md (escandir-sextilha).

Ficam num arquivo separado para irem na integra ao caderno de bordo.
"""

SISTEMA_FATO = """\
Você lê notícias de IA para um grupo que as reconta em cordel.
Extraia da notícia:
- fato: o acontecimento em UMA frase curta, concreta, sem jargão.
- essencial: de 3 a 5 pontos que quem NUNCA leu a notícia precisa saber para entendê-la:
  quem fez, o que fez, onde ou quando, e o número ou a consequência principal. Cada ponto
  curto e concreto, com o nome próprio quando houver ("a Meta", "em Pernambuco", "10%").
- titulo: a manchete do folheto, no estilo de jornal popular: curta (até 8 palavras),
  informativa, direta (ex.: "Nordeste tem maior chuva dos últimos 30 anos").
- imagens_concretas: 3 a 5 imagens visuais concretas e narráveis que a notícia sugere
  (pessoas, objetos, lugares, ações), boas para uma xilogravura. Nada abstrato.
Não invente fatos que não estão na notícia."""

# Os tipos de sextilha pelo esquema de rima (fontes: blogs e oficinas de cordel,
# ver README). A "fechada" (rimam todos os versos) ficou de fora: as fontes não
# dizem em que ordem, e o verificador precisa de um esquema exato.
from . import dicionario

FORMAS = {
    "aberta": ("ABCBDB", "os versos 2, 4 e 6 rimam entre si; 1, 3 e 5 são livres"),
    "solta": ("ABABCD", "o verso 1 rima com o 3 e o 2 rima com o 4; 5 e 6 são livres"),
    "corrida": ("AABCCB", "o 1 rima com o 2, o 3 rima com o 6 e o 4 rima com o 5"),
    "desencontrada": ("ABBAAB", "os versos 1, 4 e 5 rimam entre si, e os versos 2, 3 e 6 "
                                "rimam entre si com outra rima"),
}


def regras_do_grupo(prioridade: str = "forma", dicionario_texto: str | None = None) -> str:
    """As regras do grupo (as de número 1, 3, 7 e 9 o verificador confere) e o dicionário.
    Com a prioridade na notícia, as do dicionário (3 e 7) viram sugestão."""
    sugestao = prioridade == "noticia"
    regra3 = ("""3. Sempre que couber sem tirar informação do verso, um termo do dicionário nordestino
   abaixo a cada 2 versos. É sugestão: o verificador só avisa, não reprova.""" if sugestao else
              """3. Pelo menos um termo do dicionário nordestino abaixo a cada 2 versos (versos 1 e 2,
   3 e 4, 5 e 6). O verificador confere.""")
    regra7 = ("""7. Se couber sem atrapalhar a notícia, uma EXPRESSÃO do dicionário por estrofe (as de
   mais de uma palavra, como "caixa dos peito"). É sugestão: o verificador só avisa.""" if sugestao else
              """7. Cada estrofe tem pelo menos uma EXPRESSÃO do dicionário (as de mais de uma
   palavra, como "caixa dos peito"). O verificador confere.""")
    return f"""\
Regras do grupo:
1. Pronome sempre antes do verbo ("me disse", "se foi"). Nunca ênclise ("disse-me")
   nem mesóclise ("dir-lhe-ei"). O verificador reprova.
{regra3}
4. As outras palavras no mesmo tom popular dos termos do dicionário: nada de palavra
   difícil, técnica ou de jornal.
5. Sem sair da formalidade do cordel: nada de gíria de internet nem palavrão.
{regra7}
8. Vocativo (chamar alguém: "seu moço", "minha gente", "meu fi") só no início ou no
   fim do verso, nunca no meio.
9. Partícula fática (né, viu, visse, tá, sabe) só no início ou no fim do verso.
11. Use a concordância da fala popular, de propósito: plural marcado só na primeira
   palavra ("os menino", "as coisa", "caixa dos peito"). Isso não é erro a corrigir.
12. Cada termo do dicionário entra no sentido dado e amarrado ao resto do verso, nunca
   solto só para constar (ruim: "Cão chupando manga, / Tem viagem que se alonga",
   em que o termo não diz nada ali).

Dicionário nordestino (termo — sentido):

{dicionario_texto or dicionario.texto_para_prompt()}"""


# O leitor do folheto vê a manchete em cima do poema, e o Poeta tendia a contar com ela:
# o poema ficava com o clima da notícia e sem a notícia. Vale nas duas prioridades.
SEM_MANCHETE = """\
O poema conta a notícia sozinho. Quem lê pode não ter visto a manchete, e nunca leu a
matéria: não conte com o título para dar a informação. Todos os pontos essenciais dados
(quem fez, o quê, onde ou quando, o número) têm de estar nos versos, com os nomes
principais. Um verso que só dá o clima ("é novidade de espantar") não informa nada."""

PRIORIDADES = {
    "noticia": """\
Prioridade desta geração: a NOTÍCIA. Quando as exigências brigarem, vale esta ordem:
1. contar os pontos essenciais, com fidelidade e de um jeito que se entenda;
2. a métrica e a rima, que o verificador confere;
3. o dicionário nordestino e o tom regional, que são tempero: use quando couberem
   sem tirar informação do verso.""",
    "forma": """\
Prioridade desta geração: a FORMA. A métrica, a rima e as regras do dicionário são
conferidas e obrigatórias, sem deixar de contar os pontos essenciais.""",
}


def sistema_poema(forma: str, estrofes: int, encadeamento: str, prioridade: str = "forma",
                  dicionario_texto: str | None = None) -> str:
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
transformam em causo. Escreva {quantas} sobre o fato dado, na voz do narrador pedido.

{SEM_MANCHETE}

{PRIORIDADES[prioridade]}

A forma, obrigatória em cada estrofe:
- Sextilha: exatamente 6 versos.
- Métrica: 7 sílabas poéticas por verso (redondilha maior). Conta-se até a última
  sílaba tônica; vogal final de uma palavra se funde com a vogal (ou H) inicial da
  seguinte; ditongo vale uma sílaba.
- Sextilha {forma}, rima {esquema}: {regra}. De preferência rima consoante
  (igual a partir da vogal tônica).
{narrativa}{deixa}
Planeje antes de escrever:
- angulo: em uma frase, como o narrador vai contar a notícia.
- para cada estrofe, cobre: os pontos essenciais que ela vai contar. Somadas, as
  estrofes cobrem todos.
- para cada estrofe, finais: as 6 palavras finais dos versos, seguindo o esquema
  {esquema}. Palavras que rimam têm que ser DIFERENTES (ex.: sertão / razão /
  clarão). Repetir a mesma palavra final é proibido: o verificador reprova.
- para cada estrofe, termos: os termos do dicionário que você vai usar nela
  (veja as regras 3 e 7: {"quando couberem" if prioridade == "noticia" else "pelo menos um a cada 2 versos, e pelo menos uma expressão de mais de uma palavra"}).
Depois escreva os versos terminando nessas palavras e usando esses termos.

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
- Sem título, sem numeração.

{regras_do_grupo(prioridade, dicionario_texto)}"""


# Quem conta a notícia. "observador" é a regra 10 do grupo (narrador em 1ª pessoa,
# roteiro fixo); os outros são os ângulos de antes. Com "sortear", cada candidata
# sai por um diferente: é daí que vem a variedade entre candidatas, já que os
# modelos de raciocínio não aceitam temperatura.
NARRADORES = {
    "observador": ("narrador observador em 1ª pessoa: um \"eu\" que presenciou o acontecimento "
                   "e conta o que viu, sempre com o mesmo roteiro, nesta ordem, do começo ao fim "
                   "do cordel: (1) onde eu estava; (2) o que eu vi acontecer; (3) o que ouvi o povo "
                   "dizer; (4) o que eu penso disso. Com uma estrofe, os quatro passos cabem nela; "
                   "com mais, distribua-os entre as estrofes, na mesma ordem"),
    "feira": "como um causo contado na feira, com humor e exagero",
    "sertanejo": "pelo olhar de um sertanejo desconfiado, que compara a novidade com a vida na roça",
    "cantador": "como cantador que anuncia uma notícia de longe, com espanto e maravilha",
    "conselho": "como conselho de gente velha, terminando numa moral",
}


def lista_essencial(essencial: list[str]) -> str:
    return "\n".join(f"- {p}" for p in essencial)


def amarra(fato: str, essencial: list[str]) -> str:
    """O que a correção e a reescrita não podem perder."""
    pontos = f"\nE, lendo só o poema, sem a manchete, dá para saber:\n{lista_essencial(essencial)}" if essencial else ""
    return f"O poema tem de continuar contando isto, com quem fez o quê e os nomes principais: {fato}{pontos}"


def usuario_poema(fato: str, essencial: list[str], imagens: list[str], narrador: str, noticia: str) -> str:
    pontos = f"Pontos essenciais (todos têm de estar nos versos):\n{lista_essencial(essencial)}\n" if essencial else ""
    return (
        f"Notícia original (a fonte dos fatos; não copie as frases dela):\n{noticia}\n\n"
        f"Fato: {fato}\n"
        f"{pontos}"
        f"Imagens possíveis: {'; '.join(imagens)}\n"
        f"Narrador: {narrador}\n\n"
        "Planeje e escreva."
    )


def poema_em_texto(estrofes: list[list[str]], numerar: bool = False) -> str:
    return "\n\n".join(
        "\n".join(f"E{e}.{n} {v}" if numerar else v for n, v in enumerate(vs, 1))
        for e, vs in enumerate(estrofes, 1))


SISTEMA_JUIZ = f"""\
Você é o júri de um concurso de cordel. Recebe a notícia e poemas em sextilhas sobre ela,
todos já aprovados por um verificador de métrica e rima, que não entende o sentido.
Avalie CADA poema, usando o número dele em `candidata`.

Leia cada poema como quem NÃO viu a manchete nem a notícia: só os versos. O folheto mostra
um título em cima, mas o poema tem de contar a notícia sozinho.

Aponte em `apontados` só os versos com problema concreto, com o motivo em uma frase:
- contradiz: afirma o contrário do que a notícia diz.
- inventa: afirma um acontecimento, número ou nome da notícia que ela não traz.
- sem_sentido: não dá para entender o verso, ou quem faz o quê nele, mesmo lendo os vizinhos.
- termo_solto: termo do dicionário abaixo fora do sentido dado, ou solto só para constar.
- enchimento: o verso não acrescenta nada, só fecha métrica ou rima.

Não são problema, e não devem ser apontados:
- A voz do gênero: o narrador "eu" que presenciou tudo, o que ele ouviu o povo dizer, a feira,
  o sertão, a comparação e a metáfora. É ficção do cordel, não invenção de fato.
- O que a notícia traz, mesmo fora do resumo: confira na notícia antes de marcar `inventa`.
- A concordância popular ("os menino") e a fala do dicionário.
- Gosto pessoal: se o verso funciona, deixe.

Em `faltando`, copie cada ponto essencial dado que quem lê só o poema não fica sabendo
(porque não está lá, ou está tão vago que não dá para saber). Lista vazia se estão todos.

Depois dê as notas de 1 a 5:
- fidelidade: lendo só o poema, 5 = conta o fato e os pontos essenciais, com quem fez o quê e
  os nomes principais; 3 = só o assunto; 1 = não dá para saber qual é a notícia, ou há erro de fato.
- coerencia: 5 = quem lê só o poema entende a notícia e cada verso segue do anterior;
  3 = há versos soltos; 1 = é uma lista de frases sem ligação.
- termos: 5 = os termos do dicionário estão no sentido certo e amarrados ao verso; 1 = soltos.
- criatividade: 5 = imagem concreta e surpreendente, final com virada; 1 = lugar-comum.
Em `comentario`, justifique em uma ou duas frases, citando versos.

Dicionário nordestino (termo — sentido):

{dicionario.texto_para_prompt()}"""


def usuario_juizo(noticia: str, fato: str, essencial: list[str], poemas: list[tuple[str, list[list[str]]]]) -> str:
    blocos = [f"Candidata {i} (ângulo: {angulo})\n{poema_em_texto(estrofes, numerar=True)}"
              for i, (angulo, estrofes) in enumerate(poemas, 1)]
    pontos = f"Pontos essenciais:\n{lista_essencial(essencial)}\n\n" if essencial else ""
    return f"Notícia:\n{noticia}\n\nFato: {fato}\n\n{pontos}" + "\n\n".join(blocos) + "\n\nAvalie cada candidata."


PEDIDO_SENTIDO = """\
O poema passou na métrica e na rima, mas um leitor apontou problemas de sentido nestes
versos. Reescreva SOMENTE eles, resolvendo o problema de cada um:"""


PEDIDO_FALTANDO = """\
Quem lê só o poema, sem a manchete, não fica sabendo destes pontos essenciais da notícia.
Conte-os trocando o mínimo de versos: de preferência os apontados acima, os de enchimento ou
os que só dão o clima. Diga a estrofe e o número de cada verso que trocar:"""


def usuario_sentido(estrofes: list[list[str]], apontados: list[dict], faltando: list[str],
                    fato: str, essencial: list[str]) -> str:
    lista = "\n".join(f"- E{a['estrofe']}.{a['n']} ({a['tipo']}): {a['motivo']}" for a in apontados)
    pedido = f"{PEDIDO_SENTIDO}\n{lista}\n\n" if apontados else ""
    if faltando:
        pedido += f"{PEDIDO_FALTANDO}\n{lista_essencial(faltando)}\n\n"
    return (
        f"{pedido}"
        "Confira cada verso novo com a notícia e com os versos vizinhos. Continue com 7 sílabas e na "
        "mesma rima: preencha `contagem` antes do verso, e mantenha a palavra final sempre que ela não "
        "for o problema. Os termos do dicionário seguem as regras 3 e 7, no sentido dado.\n\n"
        f"{amarra(fato, essencial)}\n\n"
        f"Poema atual:\n{poema_em_texto(estrofes, numerar=True)}"
    )


# Vai na mesma conversa em que o Poeta escreveu: a forma, as regras e o dicionário já estão
# no sistema dele, e a notícia, o narrador e o plano estão nos turnos anteriores.
PEDIDO_CORRECAO = """\
Um verificador reprovou alguns versos do seu poema. Reescreva SOMENTE os versos reprovados.
Os versos aprovados já estão certos e não podem mudar.
Não conte sílabas de cabeça com confiança: use a escansão do verificador como guia
(ela mostra onde o verificador separou as sílabas e onde fez elisão).
Conserte a forma sem mudar o que o poema conta:
- Confira cada verso novo com a notícia: nada de trocar o fato por causa da rima ou da
  métrica. Se o fato não couber assim, diga o mesmo com outras palavras.
- Mantenha o narrador e o ângulo que você planejou, e faça o verso novo seguir o sentido
  dos versos vizinhos.
- Não volte a uma tentativa que o verificador já reprovou nesta conversa.
- A palavra final do verso corrigido não pode repetir outra palavra final da
  estrofe. Para uma rima, procure uma palavra NOVA com o mesmo som.
- Não repita nomes e palavras de conteúdo que já estão nos outros versos.
- Prefira refazer o verso com outra imagem a remendar com palavra de enchimento.
- Se a falta for de termo ou expressão do dicionário (regras 3 e 7), reescreva o verso
  indicado usando um termo que caiba no sentido.
- A concordância popular ("os menino") é de propósito: não conserte.
Devolva cada verso corrigido com a estrofe e o número dele (E2.4 = estrofe 2, verso 4).
Antes de escrever o verso, preencha `contagem`: separe as sílabas poéticas com hífens e
numere até a última tônica (ex.: "Na-fei-ra-do-meu-ser-TÃO = 7"). Se não der 7, troque as
palavras e conte de novo: em `verso` só entra o que deu 7."""


def usuario_correcao(
    estrofes: list[list[str]], relatorio: str, reprovados: list[tuple[int, int]], fato: str,
    essencial: list[str] = (),
) -> str:
    return (
        f"{PEDIDO_CORRECAO}\n\n"
        f"{amarra(fato, list(essencial))}\n\n"
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
