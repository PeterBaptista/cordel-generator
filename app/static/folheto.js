// O cartaz "Notícias em Cordel": montagem e exportação em PNG, compartilhadas
// pelo gerador e pelo histórico. Precisa do html-to-image carregado antes.

const SETA = (espelhar) => `<svg class="seta" viewBox="0 0 22 10"${espelhar ? ' style="transform:scaleX(-1)"' : ""}><path d="M0 5 L8 0 L6 5 L8 10 Z M9 5 L17 0 L15 5 L17 10 Z" fill="currentColor"/></svg>`;
const escFolheto = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// o mesmo HTML do cartaz do gerador, a partir dos dados salvos de uma geração
function folhetoHTML({ manchete, imagem, estrofes, fonte, autor }) {
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
    ${autor ? `<div class="autor">gerado por ${escFolheto(autor)}</div>` : ""}
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
  el.classList.add("exportando");
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
    el.classList.remove("exportando");
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

// ---- as palavras do dicionário nordestino: marcadas nos versos, com o sentido ao passar o mouse

const DICIONARIO = fetch("/api/dicionario").then((r) => r.json()).then((termos) => {
  const porForma = new Map();
  for (const t of termos) for (const f of t.formas) porForma.set(f, t);
  // as expressões maiores primeiro: "se avexe não" ganha de "avexe"
  const formas = [...porForma.keys()].sort((a, b) => b.length - a.length)
    .map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "[^a-z0-9]+"));
  return { porForma, busca: new RegExp(`(?<![a-z0-9])(?:${formas.join("|")})(?![a-z0-9])`, "g") };
}).catch(() => null); // sem dicionário, os versos só ficam sem marcação

// Mesmo comprimento do original (uma letra por letra), para a posição achada valer nos dois.
const semAcento = (texto) => Array.from(texto, (c) => {
  const n = c.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  return n.length === c.length && /^[a-z0-9]+$/.test(n) ? n : " ".repeat(c.length);
}).join("");

function trechosDoVerso(verso, dic) {
  const achados = [];
  for (const m of semAcento(verso).matchAll(dic.busca)) {
    const t = dic.porForma.get(m[0].replace(/ +/g, " "));
    if (t) achados.push({ inicio: m.index, fim: m.index + m[0].length, termo: t });
  }
  return achados;
}

// foco: false no cordão, para o teclado não parar em cada palavra de dez folhetos.
async function marcarTermos(raiz, { foco = true } = {}) {
  const dic = await DICIONARIO;
  if (!dic) return;
  const passeio = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => n.parentElement.closest(".versos") && !n.parentElement.closest(".termo")
      ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT });
  const nos = [];
  while (passeio.nextNode()) nos.push(passeio.currentNode);
  for (const no of nos) {
    const achados = trechosDoVerso(no.data, dic);
    if (!achados.length) continue;
    const pedacos = document.createDocumentFragment();
    let pos = 0;
    for (const { inicio, fim, termo } of achados) {
      pedacos.append(no.data.slice(pos, inicio));
      const s = document.createElement("span");
      s.className = "termo"; s.textContent = no.data.slice(inicio, fim);
      s.dataset.termo = termo.termo; s.dataset.sentido = termo.sentido;
      if (foco) s.tabIndex = 0;
      pedacos.append(s);
      pos = fim;
    }
    pedacos.append(no.data.slice(pos));
    no.replaceWith(pedacos);
  }
}

// Os termos de um folheto inteiro, sem repetir, na ordem em que aparecem.
async function termosDoFolheto(estrofes) {
  const dic = await DICIONARIO;
  if (!dic) return [];
  const vistos = new Map();
  for (const vs of estrofes) for (const v of vs) for (const a of trechosDoVerso(v, dic)) vistos.set(a.termo.termo, a.termo);
  return [...vistos.values()];
}

// Um só balão para a página toda. Fica dentro do <dialog> quando ele está aberto,
// porque o resto da página fica por baixo dele.
const dicaTermo = (() => {
  const dica = document.createElement("div");
  dica.id = "dica-termo"; dica.setAttribute("role", "tooltip");
  let atual = null;
  const esconder = () => { dica.remove(); atual?.classList.remove("ativo"); atual?.removeAttribute("aria-describedby"); atual = null; };
  const mostrar = (el) => {
    if (el === atual) return;
    esconder(); atual = el;
    dica.innerHTML = ""; const b = document.createElement("b"); b.textContent = el.dataset.termo;
    dica.append(b, el.dataset.sentido);
    (el.closest("dialog") || document.body).append(dica);
    el.classList.add("ativo"); el.setAttribute("aria-describedby", dica.id);
    const r = el.getBoundingClientRect(), d = dica.getBoundingClientRect();
    const cima = r.top - d.height - 10;
    dica.style.top = `${cima >= 8 ? cima : r.bottom + 10}px`;
    dica.style.left = `${Math.max(12, Math.min(r.left + r.width / 2 - d.width / 2, innerWidth - d.width - 12))}px`;
  };
  document.addEventListener("pointerover", (e) => { if (e.pointerType === "mouse" && e.target.closest?.(".termo")) mostrar(e.target.closest(".termo")); });
  document.addEventListener("pointerout", (e) => { if (e.pointerType === "mouse" && e.target.closest?.(".termo") === atual) esconder(); });
  document.addEventListener("focusin", (e) => { if (e.target.closest?.(".termo")) mostrar(e.target.closest(".termo")); });
  document.addEventListener("focusout", (e) => { if (e.target.closest?.(".termo") === atual) esconder(); });
  // no celular não há mouse: o toque abre, e tocar fora fecha
  document.addEventListener("click", (e) => { const t = e.target.closest?.(".termo"); if (t) mostrar(t); else if (atual) esconder(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && atual) esconder(); });
  addEventListener("scroll", esconder, { capture: true, passive: true });
  return { esconder };
})();
