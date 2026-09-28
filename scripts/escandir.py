#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
escandir.py - verificador de metrica e rima para sextilhas de cordel.

A sextilha de cordel: 6 versos, 7 silabas poeticas cada (redondilha maior),
rima ABCBDB (os versos 2, 4 e 6 rimam entre si; 1, 3 e 5 sao livres).

Uso:
    python3 escandir.py --verso "O robo chegou na feira"
    python3 escandir.py ../folhetos/*.txt
    python3 escandir.py ../folhetos/*.txt --csv ../caderno/metrica.csv

Marcas opcionais dentro do verso, para o poeta forcar uma leitura:
    _   junta com a palavra anterior   ("poema _a cor")
    |   separa um ditongo              ("sau|dade")

O script NAO decide poesia. Ele conta. Onde a escansao e ambigua
(ditongo crescente, elisao sobre vogal tonica) ele marca com "?" e
quem decide e o grupo.
"""

import sys, re, csv, glob, unicodedata

VOGAIS  = "aeiouaeiouaeoaoau"  # placeholder, reescrito abaixo
VOGAIS  = "aeiou" + "áéíóú" + "âêô" + "ãõ" + "à" + "ü"
AGUDOS  = "áéíóúâêôà"
NASAIS  = "ãõ"
FRACAS  = "iuíúü"

MONOS_ATONOS = {
    "o","a","os","as","um","uns","uma","umas","de","do","da","dos","das",
    "em","no","na","nos","nas","ao","aos","aà","à","às","e","ou",
    "que","se","me","te","lhe","lhes","vos","com","por","per","pra","pro",
    "num","numa","mas","nem","ne","seu","sua","meu","teu","tua",
}

INSEP = {"br","bl","cr","cl","dr","fr","fl","gr","gl","pr","pl","tr","tl",
         "vr","vl","ch","lh","nh","gu","qu"}

def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")

def so_letras(p):
    return re.sub(r"[^a-z" + VOGAIS + r"ç]", "", p.lower())

# ------------------------------------------------------------------ silabas
def silabas(palavra):
    """Divide em silabas gramaticais. Devolve (silabas, duvidas)."""
    bruto = palavra.lower()
    hiatos = {m.start() - i for i, m in enumerate(re.finditer(r"\|", bruto))}
    p = so_letras(bruto)
    if not p:
        return [], []

    nucleos, duvidas = [], []
    tem_acento = any(c in AGUDOS or c in NASAIS for c in p)
    i = 0
    while i < len(p):
        if p[i] not in VOGAIS:
            i += 1
            continue
        ini, j = i, i + 1
        offglide = False          # ja consumiu uma semivogal depois da forte
        while j < len(p) and p[j] in VOGAIS:
            a, b = p[j-1], p[j]
            if j in hiatos:
                break
            if j >= 2 and a == "u" and p[j-2] in "qg":   # qu-, gu-: u grafico
                j += 1; continue
            if offglide:                                 # "praia" = prai + a
                break
            if a in NASAIS and b in "eo":                # -ao, -ae, -oe
                j += 1; offglide = True; continue
            if a not in FRACAS and b in "iu":            # ditongo decrescente
                j += 1; offglide = True; continue
            if a in "iu" and b in "iu":                  # iu, ui
                j += 1; offglide = True; continue
            if a in "iu" and b not in FRACAS:            # ditongo crescente
                resto = p[j+1:]
                no_fim = re.match(r"^[smn]?$", resto) is not None
                if no_fim and not tem_acento:
                    break                                # "prometia" = ti + a
                duvidas.append(u"'%s' pode virar hiato" % p[ini:j+1])
                j += 1; continue
            break                                        # hiato
        nucleos.append((ini, j))
        i = j

    if not nucleos:
        return [p], duvidas

    sils, ini = [], 0
    for k in range(len(nucleos) - 1):
        fim_v, ini_v = nucleos[k][1], nucleos[k+1][0]
        cons = p[fim_v:ini_v]
        n = len(cons)
        if n == 0:
            corte = ini_v
        elif n == 1:
            corte = fim_v
        elif n == 2:
            corte = fim_v if cons in INSEP else fim_v + 1
        else:
            corte = fim_v + n - 2 if cons[-2:] in INSEP else fim_v + n - 1
        sils.append(p[ini:corte]); ini = corte
    sils.append(p[ini:])
    return [s for s in sils if s], duvidas

# -------------------------------------------------------------- tonicidade
OXITONA_FIM = ("r","l","z","x","n","i","u","im","um","ins","uns","is","us")

def indice_tonica(palavra):
    """Indice 0-based da silaba tonica. -1 = monossilabo atono."""
    p = so_letras(palavra)
    sils, _ = silabas(palavra)
    if not sils:
        return -1
    if len(sils) == 1:
        return -1 if sem_acento(p) in MONOS_ATONOS else 0
    for i, s in enumerate(sils):
        if any(c in AGUDOS for c in s):
            return i
    for i, s in enumerate(sils):
        if any(c in NASAIS for c in s):
            return i
    if p.endswith(("am","em","ens","ams")):
        return len(sils) - 2
    for fim in sorted(OXITONA_FIM, key=len, reverse=True):
        if p.endswith(fim):
            return len(sils) - 1
    return len(sils) - 2

# ---------------------------------------------------------------- escansao
def escandir(verso):
    """Devolve (n_silabas_poeticas, silabas_marcadas, duvidas)."""
    duvidas = []
    palavras = [w for w in re.split(r"\s+", verso.strip()) if so_letras(w)]
    if not palavras:
        return 0, [], []

    # unidades: [texto, tonica?, inicio_de_palavra?, forca_juntar?]
    unidades = []
    for w in palavras:
        forca = w.startswith("_")
        limpo = w.strip("_")
        sils, dv = silabas(limpo)
        duvidas += ["%s: %s" % (so_letras(limpo), d) for d in dv]
        it = indice_tonica(limpo)
        for k, s in enumerate(sils):
            unidades.append([s, k == it, k == 0, forca and k == 0])

    fundidas = []
    for u in unidades:
        if fundidas and u[2]:                     # so entre palavras
            ant = fundidas[-1]
            term_vogal  = ant[0][-1] in VOGAIS
            comeca_vog  = bool(re.match(r"^h?[" + VOGAIS + r"]", u[0]))
            if u[3] or (term_vogal and comeca_vog):
                if u[3] or not ant[1]:            # anterior atona -> funde
                    fundidas[-1] = [ant[0] + "_" + u[0], ant[1] or u[1], ant[2], False]
                    continue
                duvidas.append("elisao opcional em '%s %s' (a anterior e tonica)"
                               % (ant[0], u[0]))
        fundidas.append(list(u))

    ult = max((i for i, f in enumerate(fundidas) if f[1]), default=len(fundidas) - 1)
    marcadas = []
    for i, f in enumerate(fundidas):
        s = f[0].upper() if f[1] else f[0]
        marcadas.append("(%s)" % s if i > ult else s)
    return ult + 1, marcadas, duvidas

# -------------------------------------------------------------------- rima
def chave_rima(verso):
    """(consoante, toante) a partir da vogal tonica da ultima palavra."""
    palavras = [w for w in re.split(r"\s+", verso.strip()) if so_letras(w)]
    if not palavras:
        return "", ""
    ult = so_letras(palavras[-1])
    sils, _ = silabas(ult)
    it = indice_tonica(ult)
    if it < 0:
        it = len(sils) - 1
    cauda = sem_acento("".join(sils[it:]))
    m = re.search(r"[aeiou]", cauda)
    if m:
        cauda = cauda[m.start():]
    cons = (cauda.replace("z", "s").replace("ss", "s")
                 .replace("rr", "r").replace("ao", "am"))
    toante = "".join(c for c in cons if c in "aeiou")
    return cons, toante

# ---------------------------------------------------------------- sextilha
def verificar(texto, metro=7, esquema="ABCBDB"):
    versos = [v for v in texto.splitlines() if v.strip()]
    linhas, metrica_ok = [], True
    for i, v in enumerate(versos):
        n, marc, dv = escandir(v)
        ok = (n == metro)
        metrica_ok &= ok
        linhas.append({"n": i + 1, "verso": v.strip(), "silabas": n, "ok": ok,
                       "escansao": " / ".join(marc), "duvidas": "; ".join(dv)})

    grupos = {}
    for i, v in enumerate(versos):
        if i < len(esquema):
            grupos.setdefault(esquema[i], []).append((i + 1, v))

    rimas, rimas_ok = [], True
    for letra, itens in grupos.items():
        if len(itens) < 2:
            continue
        chaves = [chave_rima(v) for _, v in itens]
        consoante = len({c for c, _ in chaves}) == 1
        toante    = len({t for _, t in chaves}) == 1
        estado = "consoante" if consoante else ("toante" if toante else "SEM RIMA")
        if not (consoante or toante):
            rimas_ok = False
        rimas.append({"letra": letra, "versos": [n for n, _ in itens],
                      "estado": estado, "chaves": [c for c, _ in chaves]})

    entra = metrica_ok and rimas_ok and len(versos) == 6
    return linhas, rimas, entra

def imprimir(nome, texto, metro=7, esquema="ABCBDB"):
    linhas, rimas, entra = verificar(texto, metro, esquema)
    print("\n=== %s ===" % nome)
    if len(linhas) != 6:
        print("  ! %d versos (a sextilha pede 6)" % len(linhas))
    for l in linhas:
        print("  %s v%d [%d] %s" % ("ok" if l["ok"] else "XX", l["n"], l["silabas"], l["verso"]))
        print("         %s" % l["escansao"])
        if l["duvidas"]:
            print("       ? %s" % l["duvidas"])
    for r in rimas:
        print("  rima %s (versos %s): %s  %s" % (r["letra"], r["versos"], r["estado"], r["chaves"]))
    print("  --> %s" % ("ENTRA na colecao" if entra else "DESCARTE (ver acima)"))
    return linhas, rimas, entra

# --------------------------------------------------------------------- cli
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(0)
    if args[0] == "--verso":
        v = " ".join(args[1:])
        n, marc, dv = escandir(v)
        print("[%d] %s" % (n, v))
        print("     %s" % " / ".join(marc))
        if dv: print("   ? %s" % "; ".join(dv))
        print("     rima: %s" % (chave_rima(v),))
        sys.exit(0)
    csv_out = None
    if "--csv" in args:
        k = args.index("--csv"); csv_out = args[k+1]; args = args[:k] + args[k+2:]
    arquivos = sorted({f for a in args for f in glob.glob(a)})
    if not arquivos:
        print("nenhum arquivo encontrado"); sys.exit(1)
    todas, aprovados = [], 0
    for f in arquivos:
        linhas, rimas, entra = imprimir(f, open(f, encoding="utf-8").read())
        aprovados += 1 if entra else 0
        for l in linhas:
            l["arquivo"] = f; todas.append(l)
    print("\n%d de %d folhetos passaram." % (aprovados, len(arquivos)))
    if csv_out and todas:
        with open(csv_out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["arquivo","n","verso","silabas","ok","escansao","duvidas"])
            w.writeheader(); w.writerows(todas)
        print("CSV: %s" % csv_out)
