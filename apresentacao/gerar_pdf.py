"""Gera apresentacao/Do7ao6.pdf a partir de apresentacao/slides.html.

    uv run --no-project --with playwright python apresentacao/gerar_pdf.py

Usa o Google Chrome instalado. Serve a pasta por HTTP porque o navegador não deixa a
página ler imagens/colecao.json direto do disco.
"""
import asyncio, functools, http.server, threading
from pathlib import Path
from playwright.async_api import async_playwright

PASTA = Path(__file__).resolve().parent
SAIDA = PASTA / "Do7ao6.pdf"
# cópia servida pelo site (a home linka para ela; a pasta apresentacao/ não sobe para o Railway)
COPIA_SITE = PASTA.parent / "app" / "static" / "Do7ao6.pdf"

def servir() -> int:
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(PASTA))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]

async def main():
    porta = servir()
    async with async_playwright() as p:
        nav = await p.chromium.launch(channel="chrome", headless=True)
        pag = await nav.new_page(viewport={"width": 1280, "height": 720})
        await pag.goto(f"http://127.0.0.1:{porta}/slides.html", wait_until="networkidle")
        await pag.wait_for_selector("body[data-pronto='1']")
        await pag.evaluate("document.fonts.ready")
        await pag.pdf(path=str(SAIDA), width="1280px", height="720px", print_background=True,
                      margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        await nav.close()
    COPIA_SITE.write_bytes(SAIDA.read_bytes())
    print(SAIDA, "e", COPIA_SITE)

asyncio.run(main())
