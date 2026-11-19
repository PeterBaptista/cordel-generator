"""Mini servidor para testar o gerador: uv run uvicorn app.server:app --reload"""

import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
import traceback

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import cadernos, contas, criacomp, custos, dicionario, linha_do_tempo, musica, narracao, prompts
from .workflow import (CHAVE_PROFESSOR, ECONOMICO, IMAGENS, MAX_RODADAS, OPCOES, OPCOES_CHAVE_PROPRIA,
                       PASTAS, RAIZ, TETO_PROPRIA_USD, TETO_USD, Config, run_cordel)

app = FastAPI(title="Do 7 ao 6")
contas.iniciar()


@app.exception_handler(contas.ErroConta)
@app.exception_handler(narracao.ErroNarracao)
def erro_conta(_request: Request, e):
    return JSONResponse({"detail": e.mensagem}, status_code=e.status)


def _narracao(nome: str) -> str | None:
    """O link do áudio da narração, se já foi gerado."""
    return f"narracao/{nome}.mp3" if (PASTAS["narracao"] / f"{nome}.mp3").is_file() else None


def _tempos(nome: str) -> str | None:
    """O tempo de cada palavra da narração (para destacar o que está sendo dito)."""
    return f"narracao/{nome}.json" if (PASTAS["narracao"] / f"{nome}.json").is_file() else None

# Quantas gerações aparecem no cordão da home; as outras ficam em /sextilhas.
ULTIMAS = 10




class SemCacheVelho(StaticFiles):
    """O navegador confere com o servidor antes de reusar: assim ninguém fica com o script antigo."""
    async def get_response(self, path, scope):
        resposta = await super().get_response(path, scope)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta


def pagina(nome: str) -> FileResponse:
    return FileResponse(RAIZ / "app" / "static" / nome, headers={"Cache-Control": "no-cache"})


app.mount("/static", SemCacheVelho(directory=RAIZ / "app" / "static"), name="static")
for nome, pasta in PASTAS.items():
    pasta.mkdir(parents=True, exist_ok=True)
    app.mount(f"/{nome}", StaticFiles(directory=pasta), name=nome)


# ------------------------------------------------------------------ contas
def _ip(request: Request) -> str:
    # atrás do proxy do Railway, o IP de quem pediu é o primeiro do X-Forwarded-For
    return (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()


def _https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def usuario_atual(request: Request) -> dict | None:
    return contas.da_sessao(request.cookies.get(contas.COOKIE))


def admin(usuario: dict | None = Depends(usuario_atual)) -> dict:
    if not usuario or not usuario["admin"]:
        raise HTTPException(403, "Só o professor (admin) abre esta página.")
    return usuario


def _so_json(request: Request) -> None:
    """Pedido de outro site não manda JSON sem permissão do navegador (CORS): com isso e o
    cookie SameSite=Lax, ninguém gera nem muda conta em nome de quem está logado."""
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(415, "Mande o pedido em JSON.")


def _logar(resposta: Response, request: Request, usuario: dict) -> dict:
    resposta.set_cookie(contas.COOKIE, contas.abrir_sessao(usuario["id"]), max_age=contas.SESSAO_DIAS * 86400,
                        httponly=True, samesite="lax", secure=_https(request), path="/")
    return usuario


class Cadastro(BaseModel):
    convite: str = ""
    login: str
    nome: str
    senha: str


class Entrada(BaseModel):
    login: str
    senha: str


@app.post("/api/cadastro", dependencies=[Depends(_so_json)])
def cadastro(dados: Cadastro, request: Request, resposta: Response):
    return _logar(resposta, request, contas.cadastrar(dados.convite, dados.login, dados.nome, dados.senha, _ip(request)))


@app.post("/api/entrar", dependencies=[Depends(_so_json)])
def entrar(dados: Entrada, request: Request, resposta: Response):
    return _logar(resposta, request, contas.entrar(dados.login, dados.senha, _ip(request)))


@app.post("/api/sair")
def sair(request: Request, resposta: Response):
    contas.fechar_sessao(request.cookies.get(contas.COOKIE))
    resposta.delete_cookie(contas.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/eu")
def eu(usuario: dict | None = Depends(usuario_atual)):
    """Quem está logado, a cota de hoje, e se o site ainda tem a chave do professor."""
    pub = contas.publico()
    base = {"chave_professor": bool(CHAVE_PROFESSOR), "cadastro_aberto": bool(contas.CONVITE) or pub["cadastro"],
            "cadastro_livre": pub["cadastro"], "publico": pub,
            "narracao_professor": bool(narracao.CHAVE_PROFESSOR)}
    if not usuario:
        return {"logado": False, **base}
    return {"logado": True, **usuario, "usadas_hoje": contas.usadas_hoje(usuario["id"]), **base}


@app.get("/admin")
def admin_pagina():
    return pagina("admin.html")


class ConfigSite(BaseModel):
    cadastro_livre: bool | None = None
    openai_publica: bool | None = None
    eleven_publica: bool | None = None
    eleven_voz: bool | None = None
    eleven_musica: bool | None = None


@app.get("/api/admin/config")
def admin_config(_: dict = Depends(admin)):
    return {"config": contas.config(), "tem_openai": bool(CHAVE_PROFESSOR), "tem_eleven": bool(narracao.CHAVE_PROFESSOR),
            "tem_convite": bool(contas.CONVITE)}


@app.post("/api/admin/config", dependencies=[Depends(_so_json)])
def admin_mudar_config(dados: ConfigSite, _: dict = Depends(admin)):
    return {"config": contas.mudar_config({k: v for k, v in dados.model_dump().items() if v is not None})}


@app.get("/api/admin/usuarios")
def admin_usuarios(_: dict = Depends(admin)):
    return {"usuarios": contas.listar(), "cota_padrao": contas.COTA_DIA, "teto_por_geracao": TETO_USD}


class NovoUsuario(BaseModel):
    login: str
    nome: str
    senha: str


class Mudanca(BaseModel):
    bloqueado: bool | None = None
    cota: int | None = None
    cota_padrao: bool = False
    senha: str | None = None


@app.post("/api/admin/usuarios", dependencies=[Depends(_so_json)])
def admin_criar(dados: NovoUsuario, _: dict = Depends(admin)):
    return contas.criar(dados.login, dados.nome, dados.senha)


@app.post("/api/admin/usuarios/{usuario_id}", dependencies=[Depends(_so_json)])
def admin_alterar(usuario_id: int, dados: Mudanca, quem: dict = Depends(admin)):
    if usuario_id == quem["id"] and dados.bloqueado:
        raise HTTPException(422, "Você não pode bloquear a própria conta.")
    contas.alterar(usuario_id, dados.bloqueado, dados.cota, dados.senha, dados.cota_padrao)
    return {"ok": True}


class Pedido(BaseModel):
    autor: str = ""
    noticia: str = ""
    url: str = ""
    com_imagem: bool = True
    config: dict = {}


@app.get("/")
def home():
    return pagina("home.html")


@app.get("/gerador")
def gerador():
    return pagina("index.html")


@app.get("/geracao/{nome}")
def geracao_pagina(nome: str):
    return pagina("index.html")


@app.get("/api/geracao/{nome}")
def geracao(nome: str):
    """Os eventos de uma geração, para a página remontar a linha do tempo."""
    if not re.fullmatch(r"[\w-]{1,120}", nome) or not (f := PASTAS["caderno"] / f"{nome}.json").is_file():
        raise HTTPException(404, "Essa geração não está no caderno.")
    log = json.loads(f.read_text(encoding="utf-8"))
    evs, reconstruido = linha_do_tempo.eventos(log, nome)
    cfg, _ = cadernos.config(log)
    return {"id": nome, "eventos": evs, "reconstruido": reconstruido, "config": cfg,
            "inicio": cadernos.hora(log.get("inicio")), "autor": log.get("autor"), "narracao": _narracao(nome),
            "narracao_tempos": _tempos(nome), "narracao_voz": _voz_da_narracao(log),
            "musica": _musica(nome), "anteriores": _anteriores(log)}


_narrando: dict[str, asyncio.Lock] = {}


class PedidoNarracao(BaseModel):
    refazer: bool = False  # só admin: gera de novo; a anterior vai para o histórico
    voz: str | None = None  # uma das narracao.VOZES; sem ela, a padrão


class PedidoMusica(BaseModel):
    refazer: bool = False
    estilo: str = "ia"
    clima: str = "ia"
    andamento: str = "ia"
    instrumentos: str = "ia"


@app.get("/api/vozes")
def vozes():
    """As vozes de narração, com a amostra de cada uma (a mesma estrofe), e as opções da música."""
    return {"vozes": narracao.catalogo(), "padrao": narracao.PADRAO, "musica": musica.opcoes()}


def _voz_da_narracao(log: dict) -> str | None:
    """A voz da narração atual (a última gravada)."""
    ns = log.get("narracoes") or []
    k = ns[-1].get("preset") if ns else None
    return narracao.VOZES[k]["nome"] if k in narracao.VOZES else None


def _musica(nome: str) -> str | None:
    return f"narracao/{nome}.musica.mp3" if (PASTAS["narracao"] / f"{nome}.musica.mp3").is_file() else None


def _anteriores(log: dict) -> dict:
    """Narrações e músicas que foram refeitas: continuam ouvíveis, no histórico."""
    def lista(chave, rotulo):
        return [{"url": n["arquivo"], "quando": n.get("quando"), "creditos": n.get("creditos"),
                 "descricao": rotulo(n)} for n in log.get(chave) or [] if n.get("arquivo")]
    return {"narracoes": lista("narracoes", lambda n: narracao.VOZES.get(n.get("preset"), {}).get("nome") or "voz antiga"),
            "musicas": lista("musicas", lambda n: n.get("resumo") or "música")}


def _caderno(nome: str) -> Path:
    if not re.fullmatch(r"[\w-]{1,120}", nome) or not (f := PASTAS["caderno"] / f"{nome}.json").is_file():
        raise HTTPException(404, "Essa geração não está no caderno.")
    return f


def _chave_eleven(request: Request, usuario: dict | None, o_que: str) -> str:
    """A chave da ElevenLabs desta chamada: a da pessoa (cabeçalho) ou, só para admin, a do professor."""
    chave = (request.headers.get("x-elevenlabs-key") or "").strip()
    if chave and not narracao.CHAVE_OK.fullmatch(chave):
        raise HTTPException(422, "Essa chave não parece uma chave da ElevenLabs.")
    if chave:
        return chave
    if not narracao.CHAVE_PROFESSOR:
        raise HTTPException(402, "Este site não tem chave da ElevenLabs. Coloque a sua em Configurações.")
    pub = contas.publico()
    liberado = pub["voz"] if o_que == "narração" else pub["musica"]
    if (not usuario or not usuario["admin"]) and not liberado:
        raise HTTPException(403, f"A {o_que} com a chave do professor é só para o professor. "
                                 "Coloque a sua chave da ElevenLabs em Configurações.")
    return narracao.CHAVE_PROFESSOR


def _arquivar(atual: Path, rotulo: str) -> str | None:
    """Tira a versão atual do caminho (sem apagar): vai para narracao/arquivo/, com a hora."""
    if not atual.is_file():
        return None
    pasta = PASTAS["narracao"] / "arquivo"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{rotulo}-{datetime.now():%Y%m%d-%H%M%S-%f}.mp3"
    atual.replace(destino)
    return f"narracao/arquivo/{destino.name}"


def _registrar(f: Path, chave_lista: str, entrada: dict, arquivo_anterior: str | None) -> None:
    """Acrescenta a gravação ao caderno (para o custo ir a /logs) e marca onde a anterior foi parar."""
    log = json.loads(f.read_text(encoding="utf-8"))
    lista = log.setdefault(chave_lista, [])
    if arquivo_anterior:
        for antiga in reversed(lista):
            if not antiga.get("arquivo"):
                antiga["arquivo"] = arquivo_anterior
                break
    lista.append(entrada)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(f)


@app.post("/api/narracao/{nome}", dependencies=[Depends(_so_json)])
async def narrar(nome: str, request: Request, pedido: PedidoNarracao | None = None,
                 usuario: dict | None = Depends(usuario_atual)):
    """Gera a narração da sextilha. Já gerada, devolve o link sem gastar nada. O admin pode
    refazer: a anterior não é apagada, vai para o histórico."""
    f = _caderno(nome)
    refazer = bool(pedido and pedido.refazer)
    if refazer and not (usuario and usuario["admin"]):
        raise HTTPException(403, "Só o professor pode refazer uma narração.")
    if (url := _narracao(nome)) and not refazer:
        return {"url": url, "tempos": _tempos(nome), "nova": False,
                "voz": _voz_da_narracao(json.loads(f.read_text(encoding="utf-8")))}
    chave = _chave_eleven(request, usuario, "narração")
    estrofes = cadernos.estrofes(json.loads(f.read_text(encoding="utf-8")), "estrofes_finais")
    if not estrofes:
        raise HTTPException(422, "Essa geração não tem versos para narrar.")
    async with _narrando.setdefault(nome, asyncio.Lock()):  # dois cliques não pagam duas vezes
        if (url := _narracao(nome)) and not refazer:
            return {"url": url, "tempos": _tempos(nome), "nova": False,
                    "voz": _voz_da_narracao(json.loads(f.read_text(encoding="utf-8")))}
        k_voz, preset = narracao.voz(pedido.voz if pedido else None)
        audio, creditos, tempos = await narracao.sintetizar(estrofes, chave, preset)
        PASTAS["narracao"].mkdir(parents=True, exist_ok=True)
        anterior = _arquivar(PASTAS["narracao"] / f"{nome}.mp3", nome)
        velho = PASTAS["narracao"] / f"{nome}.json"
        if anterior and velho.is_file():  # os tempos da anterior vão junto, com o mesmo nome
            velho.replace(PASTAS["narracao"] / anterior.removeprefix("narracao/").replace(".mp3", ".json"))
        tmp = PASTAS["narracao"] / f"{nome}.mp3.tmp"
        tmp.write_bytes(audio)
        tmp.replace(PASTAS["narracao"] / f"{nome}.mp3")
        if tempos:
            (PASTAS["narracao"] / f"{nome}.json").write_text(json.dumps(tempos, ensure_ascii=False), encoding="utf-8")
        else:
            velho.unlink(missing_ok=True)
        # o caderno registra a narração, para o custo dela aparecer em /logs (nunca a chave)
        _registrar(f, "narracoes", {
            "quando": datetime.now().astimezone().isoformat(timespec="seconds"), "creditos": creditos,
            "modelo": preset["modelo"], "voz": preset["voz"], "preset": k_voz,
            "duracao": (tempos or {}).get("duracao"),
            "chave": "professor" if chave == narracao.CHAVE_PROFESSOR else "propria",
            "por": usuario["login"] if usuario else None}, anterior)
    return {"url": _narracao(nome), "tempos": _tempos(nome), "nova": True, "creditos": creditos,
            "voz": preset["nome"]}


@app.post("/api/musica/{nome}", dependencies=[Depends(_so_json)])
async def musicar(nome: str, request: Request, pedido: PedidoMusica | None = None,
                  usuario: dict | None = Depends(usuario_atual)):
    """A música de fundo da narração: instrumental, do tamanho dela. Precisa da narração antes."""
    f = _caderno(nome)
    pedido = pedido or PedidoMusica()
    for campo, valores in (("estilo", musica.ESTILOS), ("clima", musica.CLIMAS),
                           ("andamento", musica.ANDAMENTOS), ("instrumentos", musica.INSTRUMENTOS)):
        if getattr(pedido, campo) not in valores:
            raise HTTPException(422, f"{campo} inválido.")
    if pedido.refazer and not (usuario and usuario["admin"]):
        raise HTTPException(403, "Só o professor pode refazer a música.")
    if (url := _musica(nome)) and not pedido.refazer:
        return {"url": url, "nova": False}
    if not _narracao(nome):
        raise HTTPException(409, "Narre a sextilha antes: a música toca por trás do narrador.")
    chave = _chave_eleven(request, usuario, "música")
    log = json.loads(f.read_text(encoding="utf-8"))
    duracao = next((n.get("duracao") for n in reversed(log.get("narracoes") or []) if n.get("duracao")), None)
    if not duracao and (t := PASTAS["narracao"] / f"{nome}.json").is_file():
        duracao = json.loads(t.read_text(encoding="utf-8")).get("duracao")
    duracao = duracao or 15 * max(1, len(cadernos.estrofes(log, "estrofes_finais")))
    titulo = (log.get("fato") or {}).get("titulo") or nome
    async with _narrando.setdefault(f"{nome}:musica", asyncio.Lock()):
        if (url := _musica(nome)) and not pedido.refazer:
            return {"url": url, "nova": False}
        escolha = pedido.model_dump(exclude={"refazer"})
        audio, creditos, segundos, texto = await musica.compor(titulo, escolha, duracao, chave)
        PASTAS["narracao"].mkdir(parents=True, exist_ok=True)
        anterior = _arquivar(PASTAS["narracao"] / f"{nome}.musica.mp3", f"{nome}-musica")
        tmp = PASTAS["narracao"] / f"{nome}.musica.mp3.tmp"
        tmp.write_bytes(audio)
        tmp.replace(PASTAS["narracao"] / f"{nome}.musica.mp3")
        resumo = ", ".join(v for v in escolha.values() if v != "ia") or "a IA escolheu"
        _registrar(f, "musicas", {
            "quando": datetime.now().astimezone().isoformat(timespec="seconds"), "creditos": creditos,
            "segundos": segundos, "modelo": musica.MODELO, "escolha": escolha, "resumo": resumo, "prompt": texto,
            "chave": "professor" if chave == narracao.CHAVE_PROFESSOR else "propria",
            "por": usuario["login"] if usuario else None}, anterior)
    return {"url": _musica(nome), "nova": True, "creditos": creditos, "segundos": segundos, "resumo": resumo}


@app.get("/sextilhas")
def sextilhas():
    return pagina("sextilhas.html")


@app.get("/api/dicionario")
def dicionario_publico():
    """Os termos que a página marca nos versos, com o sentido de cada um. "viu", "tá" e
    "sabe" ficam de fora: quase sempre são só os verbos comuns."""
    return [{"termo": t["termo"], "sentido": t["sentido"], "formas": sorted(t["formas"])}
            for t in dicionario.carregar()
            if t["tipo"] != "fatica" or dicionario.normalizar(t["termo"]) in dicionario.FATICAS_VERIFICADAS]


@app.get("/saude")
def saude():
    return {"ok": True}


@app.get("/api/colecao")
def colecao():
    """O que a home pública mostra: só texto, imagem e forma, sem prompts nem custos."""
    itens = []
    for f, log in _cadernos():
        cfg, _ = cadernos.config(log)
        arq = log.get("arquivos") or {}
        if not arq.get("texto") or not (PASTAS["caderno"].parent / arq["texto"]).exists():
            continue
        fato = log.get("fato") or {}
        itens.append({
            "id": f.stem, "inicio": cadernos.hora(log.get("inicio")), "entra": bool(log.get("entra")),
            "autor": log.get("autor"),
            "manchete": fato.get("titulo") or f.stem,
            "estrofes": cadernos.estrofes(log, "estrofes_finais"),
            "imagem": arq.get("imagem"), "texto": arq.get("texto"),
            "url": log.get("url"), "fonte": log.get("fonte"), "narracao": _narracao(f.stem),
            "narracao_tempos": _tempos(f.stem), "musica": _musica(f.stem),
            "motivo": log.get("motivo"), "rodadas": log.get("rodadas_de_correcao"),
            "forma": {k: cfg.get(k) for k in ("forma", "estrofes", "encadeamento", "narrador")},
        })
    # o que o grupo gerou segue o eixo: só notícias do CriaComp News, e da mesma notícia
    # fica a versão mais recente. O que a turma gera entra sempre, com o nome de quem gerou.
    grupo = [i for i in itens if not i["autor"] and criacomp.tem(i["url"])]
    recentes = {}
    for i in sorted((i for i in grupo if i["entra"]), key=lambda i: i["inicio"] or ""):
        recentes[criacomp.normalizar(i["url"])] = i
    turma = [i for i in itens if i["autor"] and i["entra"]]
    ultimas = sorted([*recentes.values(), *turma], key=lambda i: i["inicio"] or "", reverse=True)[:ULTIMAS]
    descarte = sorted((i for i in grupo if not i["entra"]), key=lambda i: i["inicio"] or "", reverse=True)
    return {"colecao": ultimas, "descarte": descarte}


@app.get("/logs")
def logs_pagina():
    return pagina("logs.html")


def _cadernos():
    return cadernos.ler(PASTAS["caderno"])


def _arquivos(f, log: dict) -> dict:
    return {**(log.get("arquivos") or {}), "caderno": f"caderno/{f.name}"}


@app.get("/api/logs")
def logs():
    """Uma linha por geração, com o custo recalculado a partir dos tokens do caderno."""
    geracoes = []
    for f, log in _cadernos():
        custo = custos.resumo(log)
        chamadas = []
        for c, cc in zip(log.get("chamadas", []), custo["chamadas"]):
            t = c.get("tokens") or {}
            chamadas.append({
                "etapa": cc["etapa"], "modelo": c.get("modelo", ""),
                "entrada": t.get("input_tokens"), "saida": t.get("output_tokens"),
                "raciocinio": t.get("reasoning_tokens"), "imagem": c.get("tokens_imagem"),
                "custo": cc["total"], "imagem_medida": cc["imagem_medida"],
                "segundos": c.get("segundos"), "response_id": c.get("response_id"),
            })
        config, _ = cadernos.config(log)
        geracoes.append({
            "id": f.stem, "inicio": cadernos.hora(log.get("inicio")), "fim": cadernos.hora(log.get("fim")),
            "config": config,
            "manchete": (log.get("fato") or {}).get("titulo") or f.stem,
            "url": log.get("url"), "entra": log.get("entra"),
            "rodadas": log.get("rodadas_de_correcao"),
            "candidatas": len(log.get("candidatas") or []) or 1,
            "texto": custo["texto"], "imagem": custo["imagem"], "total": custo["total"],
            "narracao": custo["narracao"], "creditos_narracao": custo["creditos_narracao"],
            "narracoes": [{k: n.get(k) for k in ("quando", "creditos", "modelo", "chave")} for n in log.get("narracoes", [])],
            "musicas": [{k: n.get(k) for k in ("quando", "creditos", "segundos", "resumo", "chave")} for n in log.get("musicas", [])],
            "imagem_medida": custo["imagem_medida"], "tem_imagem": custo["tem_imagem"],
            "chamadas": chamadas,
            "arquivos": _arquivos(f, log),
        })
    return {"geracoes": geracoes, "precos_conferidos_em": "28/09/2026",
            "eleven_usd_por_1k": custos.ELEVEN_USD_POR_1K_CREDITOS}


@app.get("/historico")
def historico_pagina():
    return pagina("historico.html")


@app.get("/api/historico")
def historico():
    """As sextilhas geradas, com os parâmetros que as produziram."""
    itens = []
    for f, log in _cadernos():
        config, deduzida = cadernos.config(log)
        fato = log.get("fato") or {}
        # antes das várias estrofes, o caderno guardava uma lista plana de versos
        estrofes = log.get("estrofes_finais") or ([log["versos_finais"]] if log.get("versos_finais") else [])
        escolhida = (log.get("escolhida") or {}).get("indice")
        candidatas = log.get("candidatas") or []
        itens.append({
            "id": f.stem, "inicio": cadernos.hora(log.get("inicio")), "autor": log.get("autor"),
            "manchete": fato.get("titulo") or f.stem, "fato": fato.get("fato"),
            "url": log.get("url"), "fonte": log.get("fonte"), "origem": log.get("origem"),
            "config": config, "config_deduzida": deduzida,
            "estrofes": estrofes, "entra": log.get("entra"), "motivo": log.get("motivo"),
            "rodadas": log.get("rodadas_de_correcao"), "duvidas": log.get("duvidas_para_o_grupo") or [],
            "angulo": candidatas[escolhida]["angulo"] if escolhida is not None and escolhida < len(candidatas) else None,
            "justificativa": (log.get("escolhida") or {}).get("justificativa"),
            "custo": custos.resumo(log)["total"], "narracao": _narracao(f.stem), "narracao_tempos": _tempos(f.stem), "musica": _musica(f.stem),
            "arquivos": _arquivos(f, log),
        })
    return {"itens": itens}


@app.get("/api/config")
def config():
    from dataclasses import asdict
    return {"padrao": asdict(Config()), "economico": ECONOMICO, "opcoes": OPCOES,
            "opcoes_chave_propria": OPCOES_CHAVE_PROPRIA, "max_rodadas": MAX_RODADAS,
            "teto": TETO_USD, "teto_propria": TETO_PROPRIA_USD,
            "imagens": {k: {"modelo": m, "qualidade": q} for k, (m, q) in IMAGENS.items()},
            "precos": {m: {"entrada": e, "saida": o} for m, (e, _, o) in custos.PRECOS.items()},
            "formas": {nome: {"esquema": esq, "regra": regra} for nome, (esq, regra) in prompts.FORMAS.items()},
            "narradores": prompts.NARRADORES}


CHAVE_OK = re.compile(r"sk-[A-Za-z0-9_\-]{20,300}")
# uma geração por vez por pessoa: abrir várias abas não multiplica o gasto. A trava vence
# sozinha: se a página fechar antes do streaming começar, o finally abaixo nem roda.
gerando: dict = {}
TRAVA_SEGUNDOS = 15 * 60


@app.post("/api/cordel", dependencies=[Depends(_so_json)])
async def cordel(pedido: Pedido, request: Request, usuario: dict | None = Depends(usuario_atual)):
    """Com a chave do próprio usuário (cabeçalho X-OpenAI-Key), não precisa de conta: o gasto
    é dele. Sem ela, gera com a chave do professor, e aí precisa entrar e ter cota."""
    chave_propria = (request.headers.get("x-openai-key") or "").strip()
    if chave_propria and not CHAVE_OK.fullmatch(chave_propria):
        raise HTTPException(422, "Essa chave não parece uma chave da OpenAI (começa com sk-).")
    anonimo = False
    if not chave_propria:
        if not CHAVE_PROFESSOR:
            raise HTTPException(402, "Este site não tem mais a chave do professor. Coloque a sua nas configurações.")
        if not usuario:
            if not contas.config()["openai_publica"]:
                raise HTTPException(401, "Entre com sua conta para gerar com a chave do professor.")
            anonimo = True  # o professor liberou a chave para todos: conta por IP
    autor = usuario["nome"] if usuario else " ".join(pedido.autor.split())
    if not autor or len(autor) > 60:
        raise HTTPException(422, "Coloque seu nome (até 60 caracteres) para gerar.")
    opcoes = OPCOES_CHAVE_PROPRIA if chave_propria else OPCOES
    try:
        cfg = Config(**{k: v for k, v in pedido.config.items() if k in opcoes}).validar(opcoes)
    except (TypeError, ValueError) as e:
        raise HTTPException(422, f"Configuração inválida: {e}") from None
    uso, trava = None, None
    if not chave_propria:
        trava = f"ip:{_ip(request)}" if anonimo else usuario["id"]
        if time.time() - gerando.get(trava, 0) < TRAVA_SEGUNDOS:
            raise HTTPException(429, "Você já tem uma geração em andamento. Espere ela terminar.")
        uso = contas.reservar_ip(_ip(request)) if anonimo else contas.reservar(usuario)
        gerando[trava] = time.time()
    chave = chave_propria or CHAVE_PROFESSOR

    def sem_chave(texto: str) -> str:
        # uma mensagem de erro nunca devolve a chave, nem pedaço dela
        return texto.replace(chave, "sk-…") if chave else texto

    async def eventos():
        fim, gastou = None, False
        try:
            async for ev in run_cordel(pedido.noticia, pedido.url, pedido.com_imagem, cfg, autor,
                                       chave=chave, chave_propria=bool(chave_propria)):
                gastou = gastou or ev.get("etapa") != "noticia"  # a notícia não abrir não custa nada
                if ev.get("etapa") == "fim":
                    fim = ev
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            traceback.print_exc()
            yield f"data: {json.dumps({'etapa': 'erro', 'erro': sem_chave(f'{type(e).__name__}: {e}')})}\n\n"
        finally:
            if uso is not None:
                gerando.pop(trava, None)
                if gastou:
                    contas.concluir(uso, fim and fim["arquivos"].get("caderno"), fim and (fim.get("custo") or {}).get("total"))
                else:
                    contas.cancelar(uso)

    return StreamingResponse(eventos(), media_type="text/event-stream")
