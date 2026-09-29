"""Gera relatorio/Relatorio_Do7ao6.pdf a partir de relatorio/relatorio.html.

    uv run --no-project --with playwright python relatorio/gerar_pdf.py
"""
import asyncio, functools, http.server, threading
from pathlib import Path
from playwright.async_api import async_playwright

PASTA = Path(__file__).resolve().parent
SAIDA = PASTA / "Relatorio_Do7ao6.pdf"
COPIA_SITE = PASTA.parent / "app" / "static" / "Relatorio_Do7ao6.pdf"

def servir() -> int:
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(PASTA))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]

async def main():
    porta = servir()
    async with async_playwright() as p:
        nav = await p.chromium.launch(channel="chrome", headless=True)
        pag = await nav.new_page()
        await pag.goto(f"http://127.0.0.1:{porta}/relatorio.html", wait_until="networkidle")
        await pag.wait_for_selector("body[data-pronto='1']")
        await pag.evaluate("document.fonts.ready")
        # margens de 2,54 cm como no Google Docs, com o número da página no rodapé
        await pag.pdf(path=str(SAIDA), format="A4", print_background=True,
                      margin={"top": "25.4mm", "right": "25.4mm", "bottom": "25.4mm", "left": "25.4mm"},
                      display_header_footer=True, header_template="<span></span>",
                      footer_template='<div style="width:100%;font:9px Arial;text-align:right;padding-right:25.4mm">'
                                      '<span class="pageNumber"></span></div>')
        await nav.close()
    COPIA_SITE.write_bytes(SAIDA.read_bytes())
    print(SAIDA)

asyncio.run(main())
