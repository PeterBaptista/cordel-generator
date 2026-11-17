"""Contas da turma: quem gera com a chave do professor precisa entrar.

- Cadastro com o código de convite da turma (CORDEL_CONVITE). Sem convite configurado,
  só o professor cria contas, pela página /admin.
- Admin: os logins em CORDEL_ADMINS (separados por vírgula).
- Cota: CORDEL_COTA_DIA gerações por dia (dia de Recife) por pessoa, com a chave do professor.
  Quem usa a própria chave não gasta cota (e nem precisa de conta).
- Senha em scrypt (biblioteca padrão), sessão em cookie httponly; o banco guarda só o
  hash do token da sessão.

Tudo num SQLite no mesmo volume dos cadernos (CORDEL_DADOS no Railway).
"""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .workflow import DADOS

BANCO = DADOS / "contas.sqlite3"
CONVITE = os.getenv("CORDEL_CONVITE", "").strip()
ADMINS = {a.strip().lower() for a in os.getenv("CORDEL_ADMINS", "").split(",") if a.strip()}
COTA_DIA = int(os.getenv("CORDEL_COTA_DIA", "10"))
SESSAO_DIAS = 30
COOKIE = "cordel_sessao"
FUSO = ZoneInfo("America/Recife")

# usuário simples ("ana.silva") ou e-mail ("ana@cin.ufpe.br")
LOGIN_OK = re.compile(r"^(?:[a-z0-9._-]{3,30}|[a-z0-9._%+-]{1,64}@[a-z0-9.-]{1,190}\.[a-z]{2,24})$")

_trava = threading.Lock()


class ErroConta(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


@contextmanager
def _db():
    BANCO.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(BANCO, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        with _trava, con:
            yield con
    finally:
        con.close()


def iniciar() -> None:
    with _db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY, login TEXT UNIQUE NOT NULL, nome TEXT NOT NULL,
            senha TEXT NOT NULL, criado TEXT NOT NULL, bloqueado INTEGER NOT NULL DEFAULT 0,
            cota INTEGER  -- NULL = a cota padrão
        );
        CREATE TABLE IF NOT EXISTS sessoes (
            token TEXT PRIMARY KEY, usuario INTEGER NOT NULL, expira REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS usos (
            id INTEGER PRIMARY KEY, usuario INTEGER NOT NULL, quando REAL NOT NULL,
            caderno TEXT, custo REAL
        );
        CREATE INDEX IF NOT EXISTS usos_por_usuario ON usos (usuario, quando);
        """)


# ------------------------------------------------------------------ senha
def _hash(senha: str, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${sal.hex()}${h.hex()}"


def _confere(senha: str, guardado: str) -> bool:
    try:
        _, sal, h = guardado.split("$")
        return hmac.compare_digest(_hash(senha, bytes.fromhex(sal)).split("$")[2], h)
    except ValueError:
        return False


# hash de uma senha qualquer, para o login de quem não existe levar o mesmo tempo
_HASH_FALSO = _hash(secrets.token_hex(8))


def _validar(login: str, nome: str, senha: str) -> tuple[str, str]:
    login, nome = login.strip().lower(), " ".join(nome.split())
    if not LOGIN_OK.fullmatch(login):
        raise ErroConta(422, "Use um e-mail ou um usuário de 3 a 30 letras minúsculas, números, ponto, hífen ou _.")
    if not 1 <= len(nome) <= 60:
        raise ErroConta(422, "Coloque seu nome (até 60 caracteres): ele sai impresso no folheto.")
    if not 8 <= len(senha) <= 200:
        raise ErroConta(422, "A senha precisa ter pelo menos 8 caracteres.")
    return login, nome


# ------------------------------------------------------------- tentativas
# Freio contra quem tenta adivinhar senha: 8 erros em 15 minutos, por IP e por login.
_erros: dict[str, deque] = defaultdict(deque)
JANELA, MAX_ERROS = 15 * 60, 8


def _bloqueado(*chaves: str) -> bool:
    agora = time.time()
    for k in chaves:
        fila = _erros[k]
        while fila and fila[0] < agora - JANELA:
            fila.popleft()
        if len(fila) >= MAX_ERROS:
            return True
    return False


def _errou(*chaves: str) -> None:
    for k in chaves:
        _erros[k].append(time.time())


# ---------------------------------------------------------------- contas
def _publico(u: sqlite3.Row) -> dict:
    return {"id": u["id"], "login": u["login"], "nome": u["nome"], "admin": u["login"] in ADMINS,
            "bloqueado": bool(u["bloqueado"]), "cota": u["cota"] if u["cota"] is not None else COTA_DIA}


def criar(login: str, nome: str, senha: str) -> dict:
    login, nome = _validar(login, nome, senha)
    with _db() as con:
        try:
            con.execute("INSERT INTO usuarios (login, nome, senha, criado) VALUES (?, ?, ?, ?)",
                        (login, nome, _hash(senha), datetime.now(FUSO).isoformat(timespec="seconds")))
        except sqlite3.IntegrityError:
            raise ErroConta(409, "Esse usuário já existe. Escolha outro, ou entre com ele.") from None
        return _publico(con.execute("SELECT * FROM usuarios WHERE login = ?", (login,)).fetchone())


def cadastrar(convite: str, login: str, nome: str, senha: str, ip: str) -> dict:
    if not CONVITE:
        raise ErroConta(403, "O cadastro está fechado. Peça uma conta ao professor.")
    if _bloqueado(f"ip:{ip}"):
        raise ErroConta(429, "Muitas tentativas. Espere uns minutos e tente de novo.")
    if not hmac.compare_digest(convite.strip().encode(), CONVITE.encode()):
        _errou(f"ip:{ip}")
        raise ErroConta(403, "Código de convite errado. Ele é passado pelo professor na aula.")
    return criar(login, nome, senha)


def entrar(login: str, senha: str, ip: str) -> dict:
    login = login.strip().lower()
    if _bloqueado(f"ip:{ip}", f"login:{login}"):
        raise ErroConta(429, "Muitas tentativas. Espere uns minutos e tente de novo.")
    with _db() as con:
        u = con.execute("SELECT * FROM usuarios WHERE login = ?", (login,)).fetchone()
    if not _confere(senha, u["senha"] if u else _HASH_FALSO) or not u:
        _errou(f"ip:{ip}", f"login:{login}")
        raise ErroConta(401, "Usuário ou senha errados.")
    if u["bloqueado"]:
        raise ErroConta(403, "Esta conta foi bloqueada pelo professor.")
    return _publico(u)


def abrir_sessao(usuario_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with _db() as con:
        con.execute("DELETE FROM sessoes WHERE expira < ?", (time.time(),))
        con.execute("INSERT INTO sessoes VALUES (?, ?, ?)",
                    (hashlib.sha256(token.encode()).hexdigest(), usuario_id, time.time() + SESSAO_DIAS * 86400))
    return token


def fechar_sessao(token: str | None) -> None:
    if token:
        with _db() as con:
            con.execute("DELETE FROM sessoes WHERE token = ?", (hashlib.sha256(token.encode()).hexdigest(),))


def da_sessao(token: str | None) -> dict | None:
    if not token:
        return None
    with _db() as con:
        u = con.execute("""SELECT u.* FROM sessoes s JOIN usuarios u ON u.id = s.usuario
                           WHERE s.token = ? AND s.expira > ?""",
                        (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    return _publico(u) if u and not u["bloqueado"] else None


# ------------------------------------------------------------------ cota
def _inicio_do_dia() -> float:
    agora = datetime.now(FUSO)
    return agora.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def usadas_hoje(usuario_id: int) -> int:
    with _db() as con:
        return con.execute("SELECT COUNT(*) FROM usos WHERE usuario = ? AND quando >= ?",
                           (usuario_id, _inicio_do_dia())).fetchone()[0]


def reservar(usuario: dict) -> int:
    """Conta a geração antes de começar: assim duas abas ao mesmo tempo não furam a cota."""
    with _db() as con:
        usadas = con.execute("SELECT COUNT(*) FROM usos WHERE usuario = ? AND quando >= ?",
                             (usuario["id"], _inicio_do_dia())).fetchone()[0]
        if usadas >= usuario["cota"]:
            amanha = (datetime.now(FUSO) + timedelta(days=1)).strftime("%d/%m")
            raise ErroConta(429, f"Você já usou as {usuario['cota']} gerações de hoje com a chave do "
                                 f"professor. A cota volta em {amanha}, ou use a sua própria chave nas configurações.")
        return con.execute("INSERT INTO usos (usuario, quando) VALUES (?, ?)",
                           (usuario["id"], time.time())).lastrowid


def concluir(uso_id: int, caderno: str | None, custo: float | None) -> None:
    with _db() as con:
        con.execute("UPDATE usos SET caderno = ?, custo = ? WHERE id = ?", (caderno, custo, uso_id))


def cancelar(uso_id: int) -> None:
    """A geração parou antes de chamar a OpenAI (a notícia não abriu): não conta na cota."""
    with _db() as con:
        con.execute("DELETE FROM usos WHERE id = ?", (uso_id,))


# ----------------------------------------------------------------- admin
def listar() -> list[dict]:
    inicio = _inicio_do_dia()
    with _db() as con:
        linhas = con.execute("""
            SELECT u.*, COUNT(g.id) AS geracoes, COALESCE(SUM(g.custo), 0) AS gasto,
                   SUM(CASE WHEN g.quando >= ? THEN 1 ELSE 0 END) AS hoje, MAX(g.quando) AS ultima
            FROM usuarios u LEFT JOIN usos g ON g.usuario = u.id
            GROUP BY u.id ORDER BY u.login""", (inicio,)).fetchall()
    return [{**_publico(u), "criado": u["criado"], "geracoes": u["geracoes"], "gasto": round(u["gasto"], 4),
             "hoje": u["hoje"] or 0,
             "ultima": datetime.fromtimestamp(u["ultima"], FUSO).isoformat(timespec="minutes") if u["ultima"] else None}
            for u in linhas]


def alterar(usuario_id: int, bloqueado: bool | None = None, cota: int | None = None,
            senha: str | None = None, cota_padrao: bool = False) -> None:
    with _db() as con:
        if bloqueado is not None:
            con.execute("UPDATE usuarios SET bloqueado = ? WHERE id = ?", (int(bloqueado), usuario_id))
            if bloqueado:
                con.execute("DELETE FROM sessoes WHERE usuario = ?", (usuario_id,))
        if cota is not None or cota_padrao:
            if cota is not None and not 0 <= cota <= 1000:
                raise ErroConta(422, "A cota vai de 0 a 1000 gerações por dia.")
            con.execute("UPDATE usuarios SET cota = ? WHERE id = ?", (None if cota_padrao else cota, usuario_id))
        if senha is not None:
            if not 8 <= len(senha) <= 200:
                raise ErroConta(422, "A senha precisa ter pelo menos 8 caracteres.")
            con.execute("UPDATE usuarios SET senha = ? WHERE id = ?", (_hash(senha), usuario_id))
            con.execute("DELETE FROM sessoes WHERE usuario = ?", (usuario_id,))
