// O cartaz "Notícias em Cordel": montagem e exportação em PNG, compartilhadas
// pelo gerador e pelo histórico. Precisa do html-to-image carregado antes.

const SETA = (espelhar) => `<svg class="seta" viewBox="0 0 22 10"${espelhar ? ' style="transform:scaleX(-1)"' : ""}><path d="M0 5 L8 0 L6 5 L8 10 Z M9 5 L17 0 L15 5 L17 10 Z" fill="currentColor"/></svg>`;
const escFolheto = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// o mesmo HTML do cartaz do gerador, a partir dos dados salvos de uma geração
function folhetoHTML({ manchete, imagem, estrofes, fonte }) {
  const versos = estrofes.map((vs) => `<div class="estrofe-c">${vs.map((v) => `<div>${escFolheto(v)}</div>`).join("")}</div>`).join("");
  return `<div class="folheto"><div class="moldura">
    <div class="cab">Notícias em Cordel</div>
    <div class="sub">${SETA(false)}O que o mundo vive, em verso e em xilogravura${SETA(true)}</div>
    <div class="div"><span class="estrela">✸</span></div>
    <div class="manchete">${escFolheto(manchete)}</div>
    <div class="div" style="margin-top:0"><span class="estrela">✸</span></div>
    <div class="xilo">${imagem ? `<img alt="" src="${escFolheto(imagem)}">` : "<span>sem xilogravura</span>"}</div>
    <div class="versos">${versos}</div>
    <div class="rodape">${SETA(true)}<span class="estrela">✸</span>${SETA(false)}</div>
    <div class="fonte">${fonte ? `fonte: ${escFolheto(fonte)}` : ""}</div>
  </div></div>`;
}

// Espera a imagem carregar. Não usa img.decode(): no Chrome ele nunca resolve para
// uma imagem posicionada fora da tela, que é o caso do cartaz montado pelo histórico.
const carregada = (img) => img.complete && img.naturalWidth
  ? Promise.resolve()
  : new Promise((ok, falha) => { img.onload = ok; img.onerror = () => falha(new Error("a xilogravura não carregou")); });

// Exporta um cartaz já na página. O PNG original da xilogravura (~2,5 MB) deixa o
// html-to-image lento (~30 s); uma cópia reduzida em JPEG, só durante a
// exportação, faz o mesmo em ~2 s.
async function baixarFolheto(el, nome) {
  const img = el.querySelector(".xilo img"), orig = img?.src;
  try {
    if (img) {
      await carregada(img);
      const c = document.createElement("canvas");
      c.width = 1200; c.height = Math.round(1200 * img.naturalHeight / img.naturalWidth);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      const pronta = new Promise((ok) => { img.onload = ok; });
      img.src = c.toDataURL("image/jpeg", 0.9); await pronta;
    }
    const url = await htmlToImage.toPng(el, { pixelRatio: 2, backgroundColor: "#f4efe3" });
    const a = document.createElement("a"); a.href = url; a.download = `${nome}-folheto.png`; a.click();
  } finally {
    if (img) img.src = orig;
  }
}

// Monta um cartaz em tamanho cheio fora da tela, exporta e remove.
async function baixarFolhetoDe(dados, nome) {
  const caixa = document.createElement("div");
  caixa.style.cssText = "position:fixed; left:-10000px; top:0; width:420px;";
  caixa.innerHTML = folhetoHTML(dados);
  document.body.appendChild(caixa);
  try {
    await document.fonts.ready;
    await baixarFolheto(caixa.firstElementChild, nome);
  } finally {
    caixa.remove();
  }
}
