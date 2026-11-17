"""A linha do tempo de uma geração, para a página /geracao/<id>.

Desde 16/11 o caderno guarda os eventos que foram à tela (`eventos`): a página só os
toca de novo. Os cadernos de antes não têm; aí os eventos são remontados do que o
caderno guardou (candidatas, rodadas, júri, reescritas), e a escansão é refeita pelo
verificador, que é determinístico. As regras do grupo podem ter mudado desde então.
"""

from dataclasses import fields

from . import cadernos
from .workflow import Config, medir_poema

CAMPOS_CONFIG = {f.name for f in fields(Config)}


def eventos(log: dict, nome: str) -> tuple[list[dict], bool]:
    """(eventos, reconstruido)"""
    if log.get("eventos"):
        return log["eventos"], False
    return reconstruir(log, nome), True


def _escansao(estrofes: list[list[str]], cfg: Config, candidata: int, rodada: int) -> dict:
    mp = medir_poema(estrofes, cfg)
    return {"etapa": "escansao", "candidata": candidata, "rodada": rodada, "estrofes": estrofes,
            "medidas": [{k: m[k] for k in ("linhas", "rimas", "extras", "entra")} for m in mp["medidas"]],
            "deixa": mp["deixa"], "regras": mp["regras"], "sugestoes": mp["sugestoes"], "entra": mp["entra"],
            "reprovados": mp["reprovados"], "relatorio": mp["relatorio"]}


def _mudancas(antes: list[list[str]], depois: list[list[str]]) -> list[dict]:
    return [{"estrofe": e, "n": n, "antes": a, "depois": d}
            for e, (va, vd) in enumerate(zip(antes, depois), 1)
            for n, (a, d) in enumerate(zip(va, vd), 1) if a != d]


def reconstruir(log: dict, nome: str) -> list[dict]:
    dados, _ = cadernos.config(log)
    # cadernos antigos não tinham prioridade: o dicionário reprovava
    cfg = Config(**{"prioridade": "forma", **{k: v for k, v in dados.items() if k in CAMPOS_CONFIG and v is not None}})
    ev: list[dict] = []
    noticia = log.get("noticia") or ""
    if noticia:
        ev.append({"etapa": "noticia", "status": "ok", "url": log.get("url"), "trecho": noticia[:600],
                   "caracteres": len(noticia), "origem": log.get("origem") or "texto colado",
                   "titulo": log.get("titulo") or "", "fonte": log.get("fonte") or ""})
    fato = log.get("fato") or {}
    if fato:
        ev.append({"etapa": "fato", "status": "ok", "fato": fato.get("fato", ""), "titulo": fato.get("titulo", ""),
                   "essencial": fato.get("essencial") or [], "imagens_concretas": fato.get("imagens_concretas") or []})

    candidatas = log.get("candidatas") or []
    escolhida = (log.get("escolhida") or {}).get("indice") or 0
    if not candidatas:  # antes das candidatas, havia um poema só, com as rodadas no topo
        primeira = (log.get("rodadas") or [{}])[0]
        candidatas = [{"angulo": "", "estrofes": cadernos.estrofes(primeira) or cadernos.estrofes(log, "estrofes_finais"),
                       "rodadas": log.get("rodadas") or []}]
    for c in candidatas:
        c.setdefault("estrofes", cadernos.estrofes(c))
        c.setdefault("entra", c.get("entra_final", False))
        c.setdefault("forma_ok", True)
        # com uma estrofe só, os cadernos antigos guardavam o número do verso, sem a estrofe
        for k in ("reprovados", "reprovados_final"):
            c[k] = [[1, r] if isinstance(r, int) else r for r in c.get(k) or []]
    # antes de 17/11 o limite era fixo em 10 rodadas
    ev.append({"etapa": "candidatas", "status": "ok", "candidatas": candidatas, "max_rodadas": 10})

    for i, c in enumerate(candidatas):
        rodadas = c.get("rodadas") or (log.get("rodadas") if i == escolhida else None) or [{"rodada": 0, "estrofes": c["estrofes"]}]
        anterior = None
        for r in rodadas:
            estrofes = cadernos.estrofes(r)
            if not estrofes:
                continue
            if anterior is not None:
                ev.append({"etapa": "correcao", "candidata": i, "status": "ok", "rodada": r.get("rodada"),
                           "mudancas": _mudancas(anterior, estrofes)})
            ev.append(_escansao(estrofes, cfg, i, r.get("rodada", 0)))
            anterior = estrofes

    finais = cadernos.estrofes(log, "estrofes_finais")
    juizo = log.get("juizo") or {}
    ev.append({"etapa": "julgamento", "status": "ok", "escolhida": escolhida,
               "justificativa": (log.get("escolhida") or {}).get("justificativa") or "",
               "estrofes": (candidatas[escolhida].get("final") if escolhida < len(candidatas) else None) or finais,
               "aprovadas": [i for i, c in enumerate(candidatas) if c.get("entra_final", c.get("entra"))],
               "avaliacoes": [{"candidata": int(i), **av} for i, av in juizo.items()]})
    for r in log.get("reescritas") or []:
        ev.append({"etapa": "sentido", "status": "ok", "volta": r.get("volta"), "aceita": r.get("aceita"),
                   "mudancas": r.get("mudancas") or [], "estrofes": r.get("estrofes") or finais,
                   "avaliacao": r.get("avaliacao")})

    arquivos = {**(log.get("arquivos") or {}), "caderno": f"caderno/{nome}.json"}
    if arquivos.get("imagem") or log.get("erro_imagem"):
        ev.append({"etapa": "xilogravura", "status": "ok" if arquivos.get("imagem") else "erro",
                   "url": arquivos.get("imagem"), "erro": log.get("erro_imagem")})
    ev.append({"etapa": "fim", "id": nome, "entra": bool(log.get("entra")), "motivo": log.get("motivo"),
               "titulo": fato.get("titulo") or nome, "autor": log.get("autor"), "url": log.get("url"),
               "fonte": log.get("fonte"), "avaliacao": log.get("avaliacao_final"), "estrofes": finais,
               "rodadas": log.get("rodadas_de_correcao"), "duvidas": log.get("duvidas_para_o_grupo") or [],
               "arquivos": arquivos, "custo": log.get("custo_estimado_usd")})
    return ev
