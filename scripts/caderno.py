#!/usr/bin/env python3
"""caderno.py - gera caderno/REGISTRO.md a partir dos cadernos de bordo (caderno/*.json).

Cada geração do site grava um JSON com tudo o que aconteceu: a notícia, os
parâmetros, cada chamada ao modelo (prompt de sistema e de usuário na íntegra,
saída bruta, tokens, response_id), cada rodada do verificador e o custo. Este
script transforma isso no "registro por artefato" do caderno de bordo.

Uso:
    uv run python scripts/caderno.py              # caderno/*.json -> caderno/REGISTRO.md
    uv run python scripts/caderno.py outra/pasta  # outra pasta de cadernos

Não edite o REGISTRO.md à mão: rode o script de novo depois de gerar mais
folhetos. O que só o grupo sabe (por que a notícia entrou, o que foi feito na
mão, as decisões sobre os "?") fica no CADERNO-DE-BORDO.md.
"""

import hashlib
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from app import cadernos, custos  # noqa: E402

NOMES_ESFORCO = {"low": "baixo", "medium": "médio", "high": "alto"}
ESQUEMAS = {"aberta": "ABCBDB", "solta": "ABABCD", "corrida": "AABCCB", "desencontrada": "ABBAAB"}


def quando(iso: str | None) -> str:
    h = cadernos.hora(iso)
    return datetime.fromisoformat(h).strftime("%d/%m/%Y %H:%M") if h else "—"


def usd(v: float) -> str:
    return f"US$ {v:.4f}".replace(".", ",")


def bloco(texto: str, lingua: str = "text") -> str:
    # cerca com mais crases que qualquer sequência dentro do texto
    cerca = "`" * max(3, max((len(s) for s in texto.split("\n") if set(s) == {"`"}), default=0) + 1)
    return f"{cerca}{lingua}\n{texto.rstrip()}\n{cerca}"


def poema(estrofes: list[list[str]]) -> str:
    return "\n\n".join("\n".join(vs) for vs in estrofes)


def rotulo(e: int, n: int, total: int) -> str:
    return f"E{e}.{n}" if total > 1 else f"v{n}"


class Sistemas:
    """Os prompts de sistema se repetem entre chamadas: cada texto distinto vai uma
    vez, na íntegra, no apêndice (S1, S2, ...) e as chamadas apontam para ele."""

    def __init__(self):
        self.ids: dict[str, str] = {}
        self.textos: list[tuple[str, str, str]] = []  # (id, texto, onde apareceu primeiro)

    def id(self, texto: str, onde: str) -> str:
        chave = hashlib.sha1(texto.encode()).hexdigest()
        if chave not in self.ids:
            self.ids[chave] = f"S{len(self.ids) + 1}"
            self.textos.append((self.ids[chave], texto, onde))
        return self.ids[chave]


def secao(num: int, f: Path, log: dict, sistemas: Sistemas) -> str:
    cfg, deduzida = cadernos.config(log)
    fato = log.get("fato") or {}
    titulo = fato.get("titulo") or f.stem
    finais = cadernos.estrofes(log, "estrofes_finais")
    total = len(finais)
    custo = custos.resumo(log)
    rodadas = log.get("rodadas") or []
    ini, fim = cadernos.hora(log.get("inicio")), cadernos.hora(log.get("fim"))
    dur = (datetime.fromisoformat(fim) - datetime.fromisoformat(ini)).seconds if ini and fim else None
    L = []
    a = L.append

    a(f"## Folheto {num:02d} — {titulo}\n")
    a(f"**{'Entrou na coleção' if log.get('entra') else 'Descarte'}**"
      + (f" · motivo registrado pelo gerador: {log['motivo']}" if log.get("motivo") else ""))
    a("")
    if log.get("url"):
        a(f"- **Notícia de origem:** [{log.get('titulo') or log['url']}]({log['url']})"
          + (f" ({log['fonte']})" if log.get("fonte") else ""))
    else:
        a("- **Notícia de origem:** texto colado na página (está na íntegra no prompt do fato, abaixo)")
    a(f"- **Quando:** {quando(log.get('inicio'))}" + (f", {dur // 60} min {dur % 60:02d} s" if dur is not None else ""))
    a(f"- **Arquivos:** `{log.get('arquivos', {}).get('texto', '—')}`"
      + (f", `{log['arquivos']['imagem']}`" if log.get("arquivos", {}).get("imagem") else "")
      + f", `caderno/{f.name}`")
    a(f"- **Rodadas de correção até o resultado:** {log.get('rodadas_de_correcao', '—')}"
      + (f" (parou no teto de custo antes de: {log['parou_no_teto']})" if log.get("parou_no_teto") else ""))
    a(f"- **Custo estimado:** {usd(custo['total'])} (texto {usd(custo['texto'])}, imagem {usd(custo['imagem'])}"
      + ("" if custo["imagem_medida"] else "; uso da imagem não registrado nesta geração") + ")")
    a("")

    a("**Modelo, semente e parâmetros**" + (" (deduzidos do caderno: a geração é anterior aos seletores)" if deduzida else ""))
    a("")
    a("| Parâmetro | Valor |\n|---|---|")
    forma = cfg.get("forma") or "aberta"
    linhas = [
        ("Modelo de texto", (cfg.get("texto") or "—").replace("openai:", "")),
        ("Esforço de raciocínio", NOMES_ESFORCO.get(cfg.get("raciocinio"), cfg.get("raciocinio") or "—")),
        ("Semente / temperatura", "não existem nesta API para modelos de raciocínio (ver seção 1)"),
        ("Candidatas", cfg.get("candidatas", "—")),
        ("Sextilha", f"{forma} ({ESQUEMAS.get(forma, '?')})"),
        ("Estrofes", f"{cfg.get('estrofes', 1)}" + (", em deixa" if cfg.get("encadeamento") == "deixa" else "")),
        ("Narrador", {"observador": "observador em 1ª pessoa (regra 10)", "sortear": "sorteado entre os ângulos"}
         .get(cfg.get("narrador"), cfg.get("narrador") or "—")),
        ("Xilogravura", "não gerada" if cfg.get("com_imagem") is False
         else f"{ {'minima': 'gpt-image-1-mini, qualidade low', 'low': 'gpt-image-2, qualidade low', 'medium': 'gpt-image-2, qualidade medium'}.get(cfg.get('imagem_qualidade'), cfg.get('imagem_qualidade') or '—') }, 1536×1024"),
    ]
    a("\n".join(f"| {k} | {v} |" for k, v in linhas))
    a("")

    a("**Fato extraído (etapa 1)**\n")
    a(f"> {fato.get('fato', '—')}\n>\n> imagens: {'; '.join(fato.get('imagens_concretas') or [])}\n")

    cands = log.get("candidatas") or []
    if len(cands) > 1:
        esc = (log.get("escolhida") or {})
        a(f"**Candidatas** (escolhida: {esc.get('indice', 0) + 1}; {esc.get('justificativa', '')})\n")
        for i, c in enumerate(cands, 1):
            estado = "passou" if c.get("entra") else f"reprovados: {c.get('reprovados')}"
            a(f"{i}. *{c.get('angulo')}* — {estado}\n")
            a(bloco(poema(cadernos.estrofes(c))))
            a("")
    elif cands:
        a(f"**Ângulo sorteado:** {cands[0].get('angulo')}\n")

    a("**Prompts na íntegra** (cada chamada ao modelo, na ordem em que foi registrada)\n")
    for k, c in enumerate(log.get("chamadas") or [], 1):
        etapa = custos.etapa(c)
        t = c.get("tokens") or {}
        cab = (f"{k}. {etapa} — {c.get('modelo', '')}"
               + (f", raciocínio {c['reasoning_effort']}" if c.get("reasoning_effort") else "")
               + f" · {t.get('input_tokens', '—')} tokens de entrada, {t.get('output_tokens', '—')} de saída"
               + (f" ({t['reasoning_tokens']} de raciocínio)" if t.get("reasoning_tokens") else "")
               + (f" · {c['segundos']} s" if c.get("segundos") is not None else ""))
        a(f"<details><summary>{cab}</summary>\n")
        if c.get("response_id"):
            a(f"`response_id`: `{c['response_id']}` (abre no painel de logs da OpenAI)\n")
        if c.get("sistema"):
            a(f"**Sistema:** prompt **{sistemas.id(c['sistema'], f'folheto {num:02d}, {etapa}')}** (na íntegra no Apêndice A)\n")
        a("**Usuário:**\n")
        a(bloco(c.get("usuario", "")))
        if c.get("saida_bruta"):
            a("\n**Saída bruta:**\n")
            a(bloco(c["saida_bruta"], "json"))
        if c.get("tokens_imagem"):
            ti = c["tokens_imagem"]
            a(f"\nUso da geração da imagem: {ti.get('texto_entrada')} tokens de texto, "
              f"{ti.get('imagem_saida')} tokens de imagem.")
        a("\n</details>\n")

    if rodadas:
        a("**Primeira versão e relatório do verificador (rodada 0)**\n")
        a(bloco(poema(cadernos.estrofes(rodadas[0]))))
        a("")
        a(bloco(rodadas[0].get("relatorio", "")))
        a("")
    for r_ant, r in zip(rodadas, rodadas[1:]):
        ant, novo = cadernos.estrofes(r_ant), cadernos.estrofes(r)
        mud = [f"- {rotulo(e, n, len(novo))}: ~~{va}~~ → **{vn}**"
               for e, (ea, en) in enumerate(zip(ant, novo), 1)
               for n, (va, vn) in enumerate(zip(ea, en), 1) if va != vn]
        a(f"**Correção {r.get('rodada')}** (o modelo só pode reescrever os versos reprovados)\n")
        a("\n".join(mud) if mud else "- nenhuma mudança aceita")
        a(f"\n<details><summary>relatório do verificador depois da correção {r.get('rodada')}</summary>\n")
        a(bloco(r.get("relatorio", "")))
        a("\n</details>\n")

    a("**Versão final**\n")
    a(bloco(poema(finais)))
    a("")
    duv = log.get("duvidas_para_o_grupo") or []
    if duv:
        a("**Ambiguidades marcadas com `?` pelo verificador** (a decisão fica no CADERNO-DE-BORDO.md)\n")
        a("\n".join(f"- {rotulo(d.get('estrofe', 1), d['n'], total)}: {d['duvida']}" for d in duv))
        a("")
    return "\n".join(L)


def main():
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "caderno"
    itens = sorted(cadernos.ler(pasta), key=lambda x: cadernos.hora(x[1].get("inicio")) or "")
    sistemas = Sistemas()
    secoes = [secao(i, f, log, sistemas) for i, (f, log) in enumerate(itens, 1)]

    resumo = ["| # | Folheto | Quando | Resultado | Modelo | Forma | Correções | Custo |",
              "|---|---|---|---|---|---|---|---|"]
    for i, (f, log) in enumerate(itens, 1):
        cfg, _ = cadernos.config(log)
        forma = cfg.get("forma") or "aberta"
        resumo.append(
            f"| {i:02d} | {(log.get('fato') or {}).get('titulo') or f.stem} | {quando(log.get('inicio'))} "
            f"| {'entrou' if log.get('entra') else 'descarte'} | {(cfg.get('texto') or '—').replace('openai:', '')} "
            f"| {forma}, {cfg.get('estrofes', 1)} estr.{' em deixa' if cfg.get('encadeamento') == 'deixa' else ''} "
            f"| {log.get('rodadas_de_correcao', '—')} | {usd(custos.resumo(log)['total'])} |")
    total = sum(custos.resumo(log)["total"] for _, log in itens)

    apendice = ["## Apêndice A — Prompts de sistema, na íntegra\n",
                "Cada texto distinto aparece uma vez. Mudaram ao longo do desenvolvimento "
                "(forma da sextilha, número de estrofes, critério de palavra repetida); "
                "por isso há mais de um.\n"]
    for sid, texto, onde in sistemas.textos:
        apendice.append(f"### {sid} (primeiro uso: {onde})\n")
        apendice.append(bloco(texto))
        apendice.append("")

    saida = pasta / "REGISTRO.md"
    saida.write_text("\n".join([
        "# Registro por artefato\n",
        f"> Gerado por `scripts/caderno.py` a partir de `{pasta.relative_to(RAIZ) if pasta.is_relative_to(RAIZ) else pasta}/*.json` "
        f"em {datetime.now():%d/%m/%Y %H:%M}. **Não edite à mão**: rode o script de novo. "
        "O que só o grupo sabe fica no [CADERNO-DE-BORDO.md](../CADERNO-DE-BORDO.md).\n",
        f"{len(itens)} gerações, custo total estimado {usd(total)}.\n",
        "\n".join(resumo), "",
        *secoes,
        "\n".join(apendice),
    ]) + "\n", encoding="utf-8")
    print(f"{saida}: {len(itens)} gerações, {len(sistemas.textos)} prompts de sistema distintos")


if __name__ == "__main__":
    main()
