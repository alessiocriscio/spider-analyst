import { Spider, pingLine } from "./spider.js";

// any unexpected error is shown on screen instead of leaving a still spider
function showError(msg) {
  let bar = document.getElementById("errbar");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "errbar";
    document.body.append(bar);
  }
  bar.textContent = "Qualcosa non ha funzionato: " + msg + " — ricarica la pagina (Cmd+R). Se si ripete, manda questo messaggio.";
}
window.addEventListener("error", (e) => showError(e.message || String(e.error)));
window.addEventListener("unhandledrejection", (e) => showError(e.reason?.message || String(e.reason)));

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}
const postJSON = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function show(id) {
  for (const s of document.querySelectorAll(".screen")) s.hidden = s.id !== id;
}

// ------------------------------------------------------------------ home

const state = { status: null, analysis: null, director: null };

async function refreshStatus() {
  try { state.status = await api("/api/status"); } catch { state.status = null; }
  const ai = $("#opt-ai");
  ai.disabled = !state.status?.ai;
  ai.parentElement.title = state.status?.ai ? "" : "Aggiungi una chiave API Anthropic nelle impostazioni";
  if (!state.status?.ai) ai.checked = false;
}

let searchSeq = 0;
$("#search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#q").value.trim();
  if (!q) return;
  const seq = ++searchSeq;
  const box = $("#results");
  box.innerHTML = `<p class="empty">Cerco «${esc(q)}» su SEC EDGAR, filings.xbrl.org e Yahoo Finance…</p>`;
  let res;
  try { res = await api("/api/search?q=" + encodeURIComponent(q)); } catch (err) {
    box.innerHTML = `<p class="error">${esc(err.message)}</p>`; return;
  }
  if (seq !== searchSeq) return;
  box.innerHTML = renderResults(res);
});

function renderResults(res) {
  const parts = [];
  if (res.sec.length) parts.push(group("Bilancio annuale USA", "SEC EDGAR: 10-K, 20-F o 40-F più recente", res.sec.map((c) =>
    hit({ kind: "sec", query: c.ticker || String(c.cik) }, c.name, c.ticker, "Legge il bilancio"))));
  if (res.esef.length) parts.push(group("Relazione annuale europea", "ESEF da filings.xbrl.org", res.esef.map((e) =>
    hit({ kind: "esef", query: e.lei }, e.name, e.country, "Legge la relazione"))));
  if (res.market.length) parts.push(group("Mercati", "Scheda generata dallo storico prezzi Yahoo Finance", res.market.map((m) =>
    hit({ kind: "market", symbol: m.symbol }, m.name, m.symbol, `${m.type_it}${m.exchange ? " · " + m.exchange : ""}`))));
  if (!parts.length) parts.push(`<p class="empty">Nessun risultato. Prova con il ticker (es. MSFT, RACE.MI, BTC-USD) o carica direttamente il documento.</p>`);
  for (const e of res.errors || []) parts.push(`<p class="note">${esc(e)}</p>`);
  return parts.join("");
}
function group(title, src, items) {
  return `<div class="group"><h3>${esc(title)} <span class="src">· ${esc(src)}</span></h3>${items.slice(0, 6).join("")}</div>`;
}
function hit(req, name, tk, what) {
  return `<button class="hit" type="button" data-req='${esc(JSON.stringify(req))}'><b>${esc(name)}</b><span class="tk">${esc(tk || "")}</span><span class="what">${esc(what)}</span></button>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest(".hit[data-req]");
  if (b) start(JSON.parse(b.dataset.req));
  const r = e.target.closest(".hit[data-open]");
  if (r) openAnalysis(r.dataset.open);
});

$("#url-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const url = $("#url").value.trim();
  if (url) start({ kind: "url", url });
});

const drop = $("#drop"), file = $("#file");
drop.addEventListener("click", () => file.click());
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); file.click(); } });
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
file.addEventListener("change", () => { if (file.files[0]) upload(file.files[0]); });

async function upload(f) {
  const fd = new FormData();
  fd.append("file", f);
  fd.append("use_ai", $("#opt-ai").checked ? "true" : "false");
  fd.append("lang", $("#opt-lang").value);
  show("loading"); loadingReset(`Carico ${f.name}`);
  try { const { job } = await api("/api/upload", { method: "POST", body: fd }); await follow(job); } catch (err) { loadingError(err.message); }
}

async function start(req) {
  req.ai = $("#opt-ai").checked;
  req.lang = $("#opt-lang").value;
  show("loading"); loadingReset("Preparo il documento");
  try { const { job } = await postJSON("/api/analyze", req); await follow(job); } catch (err) { loadingError(err.message); }
}

function loadingReset(step) {
  $("#load-step").textContent = step; $("#load-bar").style.width = "2%";
  $("#load-error").hidden = true; $("#load-back").hidden = true;
}
function loadingError(msg) {
  $("#load-error").textContent = msg; $("#load-error").hidden = false; $("#load-back").hidden = false;
  $("#load-step").textContent = "La lettura non è partita";
}
$("#load-back").addEventListener("click", () => { show("home"); loadRecent(); });

async function follow(job) {
  for (;;) {
    const j = await api("/api/job/" + job);
    $("#load-step").textContent = j.step;
    $("#load-bar").style.width = Math.round(j.progress * 100) + "%";
    if (j.status === "done") return openAnalysis(j.analysis_id);
    if (j.status === "error") return loadingError(j.error);
    await sleep(500);
  }
}

async function loadRecent() {
  try {
    const list = await api("/api/recent");
    $("#recent").innerHTML = list.length ? `<h3>Letti di recente</h3>` + list.map((a) =>
      `<button class="hit" type="button" data-open="${esc(a.id)}"><b>${esc(a.title)}</b><span class="what">${esc(a.subtitle)}</span></button>`).join("") : "";
  } catch { /* server not ready */ }
}

// settings
$("#open-settings").addEventListener("click", async () => {
  await refreshStatus();
  $("#set-ua").value = state.status?.sec_ua_custom ? state.status.sec_user_agent : "";
  $("#set-key").value = "";
  $("#key-state").textContent = state.status?.ai_key ? "Chiave salvata. Lascia vuoto per non cambiarla; scrivi «rimuovi» per cancellarla." :
    "Serve solo per le osservazioni scritte da Claude. Senza chiave tutto il resto funziona.";
  $("#set-msg").hidden = true;
  $("#settings").showModal();
});
$("#set-save").addEventListener("click", async () => {
  const body = { sec_user_agent: $("#set-ua").value.trim() };
  const k = $("#set-key").value.trim();
  if (k === "rimuovi") body.anthropic_key = "";
  else if (k) body.anthropic_key = k;
  try { await postJSON("/api/settings", body); await refreshStatus(); $("#settings").close(); }
  catch (err) { $("#set-msg").textContent = err.message; $("#set-msg").hidden = false; }
});

// ------------------------------------------------------------------ reader

const iframe = $("#doc"), stage = $("#stage"), layer = $("#doc-layer");
const marksCv = $("#marks"), spiderCv = $("#spider");

// Report wording in the two report languages (the interface itself stays Italian)
const I18N = {
  it: {
    of: "di", read: "cifre lette", other: "Altre cifre lette dal ragno", obs: "Osservazioni chiave", yoy: "sull'anno",
    page: "Pagina", p: "p.", pp: "pp.", checks: "controlli superati su", foot_ai: "Osservazioni di Claude, verificate sulle cifre",
    foot_det: "Calcoli deterministici sulle cifre del documento", pages_some: (l, n) => `Pagine lette: ${l} di ${n} (quelle con i prospetti e le cifre principali)`,
    pages_all: (n) => `Pagine lette: tutte (${n})`, report: "Report", source: "Fonte", made: "Generato da Spider Analyst il",
    figures: "Cifre lette", value: "Valore", label: "Voce", controls: "Controlli aritmetici", ok: "superato", ko: "non superato",
    print: "Per salvarlo in PDF: File → Stampa → Salva come PDF.", locale: "it-IT",
  },
  en: {
    of: "of", read: "figures read", other: "Other figures the spider read", obs: "Key findings", yoy: "year on year",
    page: "Page", p: "p.", pp: "pp.", checks: "checks passed out of", foot_ai: "Findings by Claude, checked against the figures",
    foot_det: "Deterministic calculations on the document's figures", pages_some: (l, n) => `Pages read: ${l} of ${n} (the statements and key figures)`,
    pages_all: (n) => `Pages read: all (${n})`, report: "Report", source: "Source", made: "Generated by Spider Analyst on",
    figures: "Figures read", value: "Value", label: "Item", controls: "Arithmetic checks", ok: "passed", ko: "failed",
    print: "To save as PDF: File → Print → Save as PDF.", locale: "en-US",
  },
};
const L = () => I18N[state.analysis?.lang] || I18N.it;

// pacing: base seconds per stop, compressed for long documents, never by skipping figures
const BASE = { fig: 0.28, key: 0.7, head: 0.45, walk: 0.034, minHop: 0.12, maxHop: 1.4 };
const targetSeconds = (n) => Math.max(20, Math.min(120, 10 + n * 0.22));

// neon highlight palette of the reference clips
const FX_PAL = [
  { bg: "#FF00D4", fg: "#1b0024" }, { bg: "#39DFFF", fg: "#06222b" }, { bg: "#43FFA0", fg: "#062b17" },
  { bg: "#FF8650", fg: "#2b0e00" }, { bg: "#FFD34D", fg: "#2b2100" }, { bg: "#783BFF", fg: "#ffffff" }];
const FX_INK = ["#FF00D4", "#00B3E0", "#00C46A", "#FF6A2B", "#E0A800", "#783BFF"];
const FX_FONTS = ["ui-monospace, Menlo, monospace", "Georgia, 'Times New Roman', serif", "-apple-system, Helvetica, Arial, sans-serif"];
const FX_CAP = { accent: 3, strip: 1, fill: 9 }, FX_MAX = 34;
const FILLER = /^(the|a|an|and|or|of|to|in|on|for|by|as|at|is|was|were|be|that|this|with|from|which|its|their|our|we|it|are|has|have|had|not|no|any|all|such|other|per|il|lo|la|i|gli|le|di|da|in|con|su|per|tra|fra|e|o|del|della|dei|delle|che|un|una)$/i;
const MONTH = /^(January|February|March|April|May|June|July|August|September|October|November|December|gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)$/i;
const hash = (s) => { let h = 7; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return h; };
const easeOutBack = (t) => 1 + 2.9 * Math.pow(t - 1, 3) + 1.9 * Math.pow(t - 1, 2);

$("#back").addEventListener("click", () => { state.director?.stop(); show("home"); loadRecent(); });
$("#play").addEventListener("click", () => state.director?.toggle());
$("#restart").addEventListener("click", () => state.director?.restart());
$("#download").addEventListener("click", () => state.analysis && downloadReport(state.analysis));
$("#lang2").addEventListener("change", async () => {
  const a = state.analysis, lang = $("#lang2").value;
  $("#opt-lang").value = lang;
  if (!a || a.lang === lang) return;
  state.director?.stop();
  show("loading"); loadingReset(lang === "en" ? "Preparing the English report" : "Preparo il report in italiano");
  try { const { job } = await postJSON("/api/relang", { id: a.id, lang }); await follow(job); } catch (err) { loadingError(err.message); }
});

async function openAnalysis(id) {
  const a = await api("/api/doc/" + id);
  state.analysis = a;
  show("reader");
  const T = L();
  $("#lang2").value = a.lang || "it";
  $("#r-title").textContent = a.title;
  $("#r-sub").textContent = a.subtitle;
  $("#r-of").textContent = T.of;
  $("#r-read").textContent = T.read;
  $("#r-other-title").textContent = T.other;
  $("#r-m").textContent = Object.keys(a.facts).length.toLocaleString(T.locale);
  const shown = a.pages.map((p) => p.n);
  $("#r-pages").textContent = a.total_pages > shown.length ? T.pages_some(shown.join(", "), a.total_pages) : T.pages_all(a.total_pages);
  $("#r-warn").textContent = (a.warnings || []).join(" ");
  state.director?.stop();
  await new Promise((res) => { iframe.onload = res; iframe.src = `/api/doc/${id}/view`; });
  state.director = new Director(a);
  state.director.restart();
}

function fmtPages(pages) {
  if (!pages?.length) return "";
  const T = L();
  return (pages.length > 1 ? T.pp + " " : T.p + " ") + pages.join(", ");
}

class Director {
  constructor(a) {
    this.a = a;
    this.doc = iframe.contentDocument;
    this.raf = 0;
    this.playing = false;
    this.measure();
    this.spider = new Spider(this.U);
    this.spider.wordNear = (x, y, r) => this.wordNear(x, y, r);
    this.spider.onLand = (w) => this.touch(w);
    new ResizeObserver(() => this.relayout()).observe(stage);
  }

  measure() {
    const d = this.doc, root = d.documentElement;
    const main = d.getElementById("sa-doc");
    this.docW = Math.max(main.scrollWidth, root.scrollWidth);
    iframe.style.width = this.docW + "px";
    this.docH = root.scrollHeight;
    iframe.style.height = this.docH + "px";
    this.docH = root.scrollHeight;
    iframe.style.height = this.docH + "px";
    this.buildWords();
    this.buildStops();
  }

  // every word on the pages with its box: feet land on them, pings and highlights pick them
  buildWords() {
    const d = this.doc, root = d.getElementById("sa-doc");
    const walker = d.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => n.parentElement && n.parentElement.closest("style,script,.sa-pnum") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    const range = d.createRange(), words = [];
    let node;
    outer: while ((node = walker.nextNode())) {
      const re = /\S+/g;
      let m;
      while ((m = re.exec(node.data))) {
        range.setStart(node, m.index); range.setEnd(node, m.index + m[0].length);
        const r = range.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) continue;
        words.push({ t: m[0], x: r.left, y: r.top, w: r.width, h: r.height, cx: r.left + r.width / 2, cy: r.top + r.height / 2 });
        if (words.length >= 40000) break outer;
      }
    }
    words.sort((p, q) => p.cy - q.cy);
    const rows = [];
    for (const w of words) {
      const row = rows[rows.length - 1];
      if (row && Math.abs(row.cy - w.cy) < Math.min(row.h, w.h) * 0.5) row.els.push(w);
      else rows.push({ cy: w.cy, y: w.y, h: w.h, els: [w] });
    }
    for (const r of rows) r.els.sort((p, q) => p.x - q.x);
    this.words = words; this.rows = rows;
    const hs = words.map((w) => w.h).sort((p, q) => p - q);
    const lh = hs.length ? hs[hs.length >> 1] : 16;
    this.U = Math.max(0.45, Math.min(2.2, lh / 16));
  }

  rowIndexAt(y) {
    const rows = this.rows;
    let lo = 0, hi = rows.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (rows[m].cy < y) lo = m + 1; else hi = m; }
    return lo;
  }

  wordNear(x, y, r) {
    let best = null, bd = r;
    for (let i = this.rowIndexAt(y - r); i < this.rows.length && this.rows[i].cy <= y + r; i++) {
      for (const w of this.rows[i].els) {
        const d = Math.hypot(w.cx - x, w.cy - y);
        if (d < bd) { bd = d; best = w; }
      }
    }
    return best ? { x: best.cx, y: best.cy, word: best } : null;
  }

  relayout() {
    const W = stage.clientWidth, H = stage.clientHeight, dpr = devicePixelRatio || 1;
    for (const cv of [marksCv, spiderCv]) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    const pageW = Math.max(...[...this.doc.querySelectorAll(".sa-page")].map((p) => p.getBoundingClientRect().width), 600);
    this.scale = Math.min(1.15, (W - 24) / pageW);
    this.W = W; this.H = H; this.dpr = dpr;
    if (!this.playing && this.timeline) this.frame(performance.now(), true);
  }

  rectOf(el) {
    const r = el.getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  }

  buildStops() {
    const a = this.a, stops = [];
    for (const sec of this.doc.querySelectorAll(".sa-page")) {
      const n = +sec.dataset.page;
      const items = [];
      for (const el of sec.querySelectorAll("[data-h]")) {
        const range = this.doc.createRange();
        range.selectNodeContents(el);
        const rr = range.getBoundingClientRect(), r = { x: rr.left, y: rr.top, w: rr.width, h: rr.height };
        if (r.w > 2 && r.h > 2) items.push({ type: "h", el, r, text: el.textContent.trim(), page: n });
      }
      for (const el of sec.querySelectorAll("[data-f]")) {
        const f = a.facts[el.dataset.f];
        if (!f) continue;
        const r = this.rectOf(el);
        if (r.w < 2 || r.h < 2) continue;
        items.push({ type: "f", el, r, id: el.dataset.f, fact: f, page: n, label: this.rowLabelRect(el) });
      }
      // reading order: rows top to bottom, left to right within a row
      items.sort((p, q) => (Math.abs(p.r.y - q.r.y) < 6 ? p.r.x - q.r.x : p.r.y - q.r.y));
      if (!items.length) items.push({ type: "page", r: this.rectOf(sec), page: n });
      items[0].first = true;
      stops.push(...items);
    }
    this.allStops = stops;
  }

  rowLabelRect(el) {
    const tr = el.closest("tr");
    if (!tr) return null;
    for (const td of tr.children) {
      if (td.contains(el)) break;
      const t = td.textContent.trim();
      if ((t.match(/\p{L}/gu) || []).length >= 3) {
        const range = this.doc.createRange();
        range.selectNodeContents(td);
        const rr = range.getBoundingClientRect();
        return { x: rr.left, y: rr.top, w: rr.width, h: rr.height, text: t };
      }
    }
    return null;
  }

  // every figure is visited; the pace adapts to how many there are
  plan() {
    const stops = this.allStops;
    const pts = stops.map((s) => this.anchor(s));
    const dwell = (s) => s.type === "h" || s.type === "page" ? BASE.head : s.fact.key ? BASE.key : BASE.fig;
    let prev = { x: pts[0].x, y: pts[0].y - 160 * this.U };
    const legs = stops.map((s, i) => {
      const d = Math.hypot(pts[i].x - prev.x, pts[i].y - prev.y);
      prev = pts[i];
      return [Math.min(BASE.maxHop, Math.max(BASE.minHop, BASE.walk * Math.sqrt(d))), dwell(s)];
    });
    const natural = legs.reduce((t, [p, q]) => t + p + q, 0);
    const figures = stops.filter((s) => s.type === "f").length;
    const k = Math.max(0.12, Math.min(1, targetSeconds(figures) / natural));
    let t = 0;
    this.timeline = stops.map((s, i) => {
      const seg = { s, p: pts[i], t0: t, t1: t + legs[i][0] * k, t2: t + (legs[i][0] + legs[i][1]) * k };
      t = seg.t2;
      return seg;
    });
    this.start0 = { x: pts[0].x, y: pts[0].y - 160 * this.U };
    this.planned = new Set(stops.filter((x) => x.type === "f").map((x) => String(x.id)));
    this.total = t;
    const mul = Math.min(2.6, 1 / Math.sqrt(k));
    this.pace = { k, mul, cam: Math.min(10, 4 * mul), obs: Math.max(800, 1600 / mul) };
    this.spider.speed = mul;
  }

  // the body stops just above what it reads, head pointing at it
  anchor(s) {
    const U = this.U;
    if (s.type === "page") return { x: s.r.x + 120 * U, y: s.r.y + 60 * U };
    if (s.type === "h") return { x: s.r.x + Math.min(s.r.w / 2, 60 * U), y: s.r.y + s.r.h / 2 - 34 * U };
    return { x: s.r.x + s.r.w / 2, y: s.r.y + s.r.h / 2 - 34 * U };
  }

  restart() {
    this.stop();
    $("#finale").hidden = true; $("#finale").innerHTML = "";
    this.relayout();
    this.plan();
    this.clock = 0; this.idx = -1; this.marks = []; this.touched = []; this.fx = []; this.pings = []; this.flashes = [];
    this.acc = { small: 0, fill: 0, accent: 0, strip: 0 };
    this.nextPink = 0; this.nextCyan = 0.13; this.done = false;
    this.count = 0; this.page = null;
    $("#r-n").textContent = "0";
    $("#r-other-list").innerHTML = "";
    $("#r-sec-title").textContent = "";
    $("#r-table thead").innerHTML = ""; $("#r-table tbody").innerHTML = "";
    this.cam = { x: 0, y: Math.max(0, this.start0.y - 200) };
    this.spider.place(this.start0.x, this.start0.y, Math.PI / 2);
    this.playing = true;
    $("#play").textContent = "Pausa";
    this.last = performance.now();
    this.raf = requestAnimationFrame((t) => this.frame(t));
  }

  stop() {
    cancelAnimationFrame(this.raf);
    this.playing = false;
    $("#play").textContent = "Avvia";
  }

  toggle() {
    if (this.done) return this.restart();
    if (this.playing) return this.stop();
    this.playing = true; $("#play").textContent = "Pausa";
    this.last = performance.now();
    this.raf = requestAnimationFrame((t) => this.frame(t));
  }

  bodyAt(t) {
    const tl = this.timeline;
    let prev = this.start0;
    for (let i = 0; i < tl.length; i++) {
      const g = tl[i];
      if (t < g.t0) return prev;
      if (t < g.t1) {
        const u = (t - g.t0) / (g.t1 - g.t0), e = u < 0.5 ? 2 * u * u : 1 - (-2 * u + 2) ** 2 / 2;
        return { x: prev.x + (g.p.x - prev.x) * e, y: prev.y + (g.p.y - prev.y) * e };
      }
      if (t < g.t2) return g.p;
      prev = g.p;
    }
    return prev;
  }

  frame(now, still = false) {
    const dt = still ? 0 : Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    if (!still) this.clock += dt;
    const t = this.clock;

    while (this.timeline && this.idx + 1 < this.timeline.length && t >= this.timeline[this.idx + 1].t1) {
      this.idx++;
      this.arrive(this.timeline[this.idx]);
    }
    const goal = this.bodyAt(t);
    const seg = this.timeline?.[this.idx];
    const face = seg && t < seg.t2 ? Math.atan2(seg.s.r.y + seg.s.r.h / 2 - this.spider.y, seg.s.r.x + seg.s.r.w / 2 - this.spider.x) : null;
    if (!still) {
      this.spider.update(goal, dt, face);
      if (!this.done) { this.scan(t); this.fxTick(dt); }
    }

    // camera follows the spider, clamped to the document
    const s = this.scale, vw = this.W / s, vh = this.H / s;
    const tx = Math.max(0, Math.min(this.docW - vw, this.spider.x - vw * 0.5));
    const ty = Math.max(0, Math.min(this.docH - vh, this.spider.y - vh * 0.42));
    const k = still || reduced ? 1 : Math.min(1, dt * this.pace.cam);
    this.cam.x += (Math.max(0, tx) - this.cam.x) * k;
    this.cam.y += (ty - this.cam.y) * k;
    if (this.docW * s <= this.W) this.cam.x = -(this.W / s - this.docW) / 2;
    layer.style.transform = `scale(${s}) translate(${-this.cam.x}px, ${-this.cam.y}px)`;

    this.draw();

    if (!this.done && this.timeline && t > this.total + 0.6) {
      this.done = true;
      this.finale();
    }
    if (this.playing) this.raf = requestAnimationFrame((tt) => this.frame(tt));
  }

  // continuous scan between figures: a pink ping and a cyan sight line to words just ahead
  scan(t) {
    const mul = this.pace.mul;
    if (t >= this.nextPink) {
      const w = this.pickAhead(true);
      if (w) { this.ping(w, "#ff2d8f", 0.38 / mul); if (Math.random() < 0.35) this.fxOn(this.single(w), Math.random() < 0.5 ? "ink" : "outline"); }
      this.nextPink = t + 0.26 / mul;
    }
    if (t >= this.nextCyan) {
      const w = this.pickAhead(false);
      if (w) this.ping(w, "#27c8ff", 0.38 / mul);
      this.nextCyan = t + 0.3 / mul;
    }
  }

  ping(w, color, dur) {
    this.pings.push({ to: { x: w.cx, y: w.cy }, t0: this.clock, dur, color });
    this.flashes.push({ w, t0: this.clock, dur: dur * 1.2, color });
  }

  pickAhead(preferNumbers) {
    const sp = this.spider, U = this.U, hd = sp.head(12), h = sp.heading;
    const cands = [];
    for (let i = this.rowIndexAt(hd.y - 60 * U); i < this.rows.length && this.rows[i].cy < hd.y + 260 * U; i++) {
      for (const w of this.rows[i].els) {
        const dx = w.cx - hd.x, dy = w.cy - hd.y, d = Math.hypot(dx, dy);
        if (d < 40 * U || d > 260 * U) continue;
        if ((dx * Math.cos(h) + dy * Math.sin(h)) / d < -0.2) continue;   // only in front
        let sc = Math.random() * 2 + Math.min(2, w.t.length / 5);
        if (preferNumbers && /\d/.test(w.t)) sc += 3;
        cands.push([sc, w]);
      }
    }
    if (!cands.length) return null;
    cands.sort((p, q) => q[0] - p[0]);
    return cands[Math.floor(Math.random() * Math.min(4, cands.length))][1];
  }

  touch(w) {
    // feet outline the words they land on; the newest 24 stay, older ones fade
    this.touched.push({ w, t0: this.clock, ink: FX_INK[this.touched.length % FX_INK.length] });
    if (this.touched.length > 40) this.touched.shift();
  }

  single(w) { return { els: [w], text: w.t, score: 1 }; }

  // phrases worth marking on one line, scored by meaning (labels, amounts, dates, names)
  rowCands(row) {
    if (row._c) return row._c;
    const els = row.els, tx = els.map((w) => w.t);
    const isNum = (t) => /^[(\-−$€£]*\d[\d.,]*%?\)?$/.test(t) && t.replace(/\D/g, "").length >= 2;
    const isCap = (t) => /^[\p{Lu}“"(]/u.test(t);
    const out = [];
    const add = (i, j, score, kind) => { if (j > i) out.push({ els: els.slice(i, j), text: tx.slice(i, j).join(" "), score, kind }); };
    let k = 0;
    while (k < els.length && !isNum(tx[k]) && !/^\d+$/.test(tx[k]) && !/^[$€£]$/.test(tx[k])) k++;
    const label = tx.slice(0, k).join(" ");
    if (k >= 1 && label.replace(/[^\p{L}]/gu, "").length >= 6 && isCap(tx[0])) {
      const heading = k === els.length && k <= 9 && tx.slice(0, k).filter((t) => !FILLER.test(t)).every(isCap);
      add(0, Math.min(k, 9), heading ? 4 : k >= 2 ? 3 : 2, heading ? "heading" : "label");
    }
    for (let i = 0; i < els.length; i++) {
      const t = tx[i];
      if (/^[$€£]$/.test(t) && isNum(tx[i + 1] || "")) { add(i, i + 2, 3, "amount"); i++; continue; }
      if (isNum(t)) { add(i, i + 1, t.replace(/\D/g, "").length >= 3 || /[$€%]/.test(t) ? 3 : 1, "amount"); continue; }
      if (MONTH.test(t)) {
        let j = i + 1;
        while (j < els.length && j < i + 3 && /^\d{1,4},?$/.test(tx[j])) j++;
        if (j > i + 1) { add(i, j, 3, "date"); i = j - 1; continue; }
      }
      if (/^(19|20)\d\d$/.test(t)) { add(i, i + 1, 2, "date"); continue; }
      if (i >= k && isCap(t) && !FILLER.test(t) && t.length > 2) {
        let j = i + 1;
        while (j < els.length && j < i + 6 && (isCap(tx[j]) || (FILLER.test(tx[j]) && isCap(tx[j + 1] || ""))) && !isNum(tx[j])) j++;
        if (j - i >= 2) { add(i, j, 2, "name"); i = j - 1; continue; }
      }
      if (t.replace(/[^\p{L}]/gu, "").length >= 4 && !FILLER.test(t)) add(i, i + 1, 1, "word");
    }
    row._c = out;
    return out;
  }

  fxTick(dt) {
    const ms = dt * 1000;
    this.fx = this.fx.filter((o) => { o.age += ms; if (o.age >= o.ttl) { o.els.forEach((w) => { if (w._fx === o) w._fx = null; }); return false; } return true; });
    const U = this.U, by = this.spider.y, mul = this.pace.mul;
    const near = [];
    for (let i = this.rowIndexAt(by - 70 * U); i < this.rows.length && this.rows[i].cy < by + 140 * U; i++) near.push(this.rows[i]);
    if (!near.length) return;
    const pick = (min, extra = () => true) => {
      const pool = [];
      for (const rw of near) for (const c of this.rowCands(rw)) if (c.score >= min && extra(c) && !c.els.some((w) => w._fx)) pool.push(c);
      if (!pool.length) return null;
      let tot = 0; pool.forEach((c) => tot += c.score * c.score);
      let r = Math.random() * tot;
      for (const c of pool) { r -= c.score * c.score; if (r <= 0) return c; }
      return pool[pool.length - 1];
    };
    const acc = this.acc;
    acc.small += dt * 4.2 * mul; acc.fill += dt * 1.3 * mul; acc.accent += dt * 0.55 * mul; acc.strip += dt * 0.17 * mul;
    while (acc.small >= 1) { acc.small -= 1; const c = pick(1); if (c) this.fxOn(c, Math.random() < 0.55 ? "outline" : "ink"); }
    while (acc.fill >= 1) { acc.fill -= 1; const c = pick(2); if (c) this.fxOn(c, "fill"); }
    while (acc.accent >= 1) { acc.accent -= 1; const c = pick(3); if (c) this.fxOn(c, "accent"); }
    while (acc.strip >= 1) { acc.strip -= 1; const c = pick(3, (x) => x.els.length >= 3 && x.text.length >= 14); if (c) this.fxOn(c, "strip"); }
  }

  fxOn(c, kind) {
    if (!c || c.els.some((w) => w._fx)) return;
    const count = (k) => this.fx.filter((o) => o.kind === k).length;
    if (FX_CAP[kind] && count(kind) >= FX_CAP[kind]) kind = kind === "strip" ? "accent" : "fill";
    if (kind === "accent" && count("accent") >= FX_CAP.accent) kind = "fill";
    if (kind === "fill" && count("fill") >= FX_CAP.fill) kind = "outline";
    const x1 = Math.min(...c.els.map((w) => w.x)), y1 = Math.min(...c.els.map((w) => w.y));
    const x2 = Math.max(...c.els.map((w) => w.x + w.w)), y2 = Math.max(...c.els.map((w) => w.y + w.h));
    const key = c.text + "|" + Math.round(y1), ci = hash(key) % FX_PAL.length;
    const o = { kind, els: c.els, text: c.text, r: { x: x1, y: y1, w: x2 - x1, h: y2 - y1 }, pal: FX_PAL[ci], ink: FX_INK[ci],
      font: FX_FONTS[hash(key + "f") % 3], age: 0 };
    if (kind === "outline") o.ttl = 2600 + Math.random() * 1800;
    else if (kind === "ink") o.ttl = 3200 + Math.random() * 1800;
    else if (kind === "fill") o.ttl = 4200 + Math.random() * 2200;
    else if (kind === "accent") {
      o.target = c.text.length <= 12 && Math.random() < 0.35 ? 3 : 1.8 + Math.random() * 0.7;
      const room = (this.docW - 10 - o.r.x) / Math.max(1, o.r.w + 8);
      o.target = Math.min(o.target, room);
      o.solid = Math.random() < 0.6;
      o.hold = 2000 + Math.random() * 1000; o.ttl = o.hold + 3500 + Math.random() * 1500;
      if (o.target < 1.4) { o.kind = "fill"; o.ttl = 4200 + Math.random() * 2200; }
    } else if (kind === "strip") {
      o.angle = (Math.random() < 0.15 ? 90 : 18 + Math.random() * 12) * (Math.random() < 0.5 ? -1 : 1);
      o.hold = 2600; o.ttl = 5200;
    }
    c.els.forEach((w) => { w._fx = o; });
    this.fx.push(o);
    while (this.fx.length > FX_MAX) { const old = this.fx.shift(); old.els.forEach((w) => { if (w._fx === old) w._fx = null; }); }
  }

  arrive(g) {
    const s = g.s;
    if (s.first && s.page !== this.page) this.enterPage(s.page);
    if (s.type === "h") { this.marks.push({ kind: "head", r: s.r, t: this.clock }); return; }
    if (s.type !== "f") return;
    this.marks.push({ kind: "found", r: s.r, t: this.clock, key: s.fact.key });
    if (s.label) this.marks.push({ kind: "label", r: s.label, t: this.clock });
    // the pink line to the figure being read
    this.pings.push({ to: { x: s.r.x + s.r.w / 2, y: s.r.y + s.r.h / 2 }, t0: this.clock, dur: Math.max(0.3, 0.6 / this.pace.mul), color: "#ff2d8f", width: 2 });
    this.count++;
    $("#r-n").textContent = this.count.toLocaleString(L().locale);
    this.report(s);
  }

  enterPage(n) {
    this.page = n;
    const a = this.a, p = a.pages.find((x) => x.n === n), T = L();
    $("#r-sec-title").textContent = `${p ? p.title : T.page + " " + n} · ${T.p} ${n}`;
    const cols = a.cols[n] || [T.value];
    $("#r-table thead").innerHTML = `<tr><th></th>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>`;
    const rows = (a.rows[n] || []).filter((r) => r.cells.some((fid) => fid !== null && this.planned.has(String(fid))));
    this.rowOf = new Map();
    $("#r-table tbody").innerHTML = rows.map((r, i) => {
      r.cells.forEach((fid, j) => fid !== null && this.rowOf.set(String(fid), [i, j]));
      return `<tr data-i="${i}"><td>${esc(r.label)}</td>${r.cells.map(() => `<td class="wait">·</td>`).join("")}</tr>`;
    }).join("");
  }

  report(s) {
    const pos = this.rowOf?.get(String(s.id));
    if (pos) {
      const tr = $(`#r-table tbody tr[data-i="${pos[0]}"]`);
      const td = tr.children[pos[1] + 1];
      td.textContent = s.fact.value_fmt; td.classList.remove("wait");
      for (const h of document.querySelectorAll("#r-table tr.hot")) h.classList.remove("hot");
      tr.classList.add("hot");
      tr.scrollIntoView({ block: "nearest" });
      return;
    }
    const li = document.createElement("li");
    li.innerHTML = `<span>${esc(s.fact.label)}</span><b>${esc(s.fact.value_fmt)}</b><i>${L().p} ${s.page}</i>`;
    const list = $("#r-other-list");
    list.prepend(li);
    while (list.children.length > 400) list.lastChild.remove();
  }

  draw() {
    const s = this.scale, dpr = this.dpr, now = this.clock;
    const set = (ctx) => { ctx.setTransform(dpr * s, 0, 0, dpr * s, -this.cam.x * s * dpr, -this.cam.y * s * dpr); };

    // persistent marks, multiplied onto the page
    const m = marksCv.getContext("2d");
    m.setTransform(1, 0, 0, 1, 0, 0);
    m.clearRect(0, 0, marksCv.width, marksCv.height);
    set(m);
    for (const mk of this.marks) {
      const grow = Math.min(1, (now - mk.t) / 0.2);
      if (mk.kind === "label") {
        m.fillStyle = "rgba(255,211,77,0.9)";
        m.fillRect(mk.r.x - 2, mk.r.y, (mk.r.w + 4) * grow, mk.r.h);
      } else if (mk.kind === "head") {
        m.fillStyle = "rgba(57,223,255,0.45)";
        m.fillRect(mk.r.x - 3, mk.r.y - 1, (mk.r.w + 6) * grow, mk.r.h + 2);
      } else {
        m.fillStyle = mk.key ? "rgba(255,0,212,0.30)" : "rgba(255,45,143,0.16)";
        m.strokeStyle = "#ff2d8f";
        m.lineWidth = mk.key ? 1.8 : 1.2;
        const pad = 1.5 + (1 - grow) * 5;
        m.fillRect(mk.r.x - pad, mk.r.y - pad, mk.r.w + pad * 2, mk.r.h + pad * 2);
        m.strokeRect(mk.r.x - pad, mk.r.y - pad, mk.r.w + pad * 2, mk.r.h + pad * 2);
      }
    }
    // flashes of the words being pinged
    this.flashes = this.flashes.filter((f) => now - f.t0 < f.dur);
    for (const f of this.flashes) {
      m.fillStyle = f.color === "#27c8ff" ? "rgba(39,200,255,0.32)" : "rgba(255,45,143,0.32)";
      m.fillRect(f.w.x - 1, f.w.y - 1, f.w.w + 2, f.w.h + 2);
      m.strokeStyle = f.color; m.lineWidth = 1;
      m.strokeRect(f.w.x - 1, f.w.y - 1, f.w.w + 2, f.w.h + 2);
    }

    // live layer: word outlines, neon highlights, pings, spider
    const c = spiderCv.getContext("2d");
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, spiderCv.width, spiderCv.height);
    set(c);
    const recent = this.touched.slice(-24);
    for (const tw of recent) {
      const a = Math.min(1, (now - tw.t0) / 0.15);
      c.globalAlpha = a; c.strokeStyle = tw.ink; c.lineWidth = 1.2;
      c.strokeRect(tw.w.x - 1.5, tw.w.y - 1, tw.w.w + 3, tw.w.h + 2);
    }
    c.globalAlpha = 1;
    for (const o of this.fx) this.drawFx(c, o);
    this.pings = this.pings.filter((p) => now - p.t0 < p.dur);
    const hd = this.spider.head(12);
    for (const p of this.pings) pingLine(c, hd, p.to, (now - p.t0) / p.dur, p.color, p.width || 1.6);
    this.spider.draw(c);
  }

  drawFx(c, o) {
    const r = o.r, act = Math.min(1, o.age / 200);
    let sc = 1, rot = 0, op = 1;
    if (o.kind === "accent") {
      if (o.age < o.hold) sc = 0.7 + (o.target - 0.7) * easeOutBack(act);
      else { const u = Math.min(1, (o.age - o.hold) / 350); sc = o.target + (1 - o.target) * (u * u * (3 - 2 * u)); }
    } else if (o.kind === "strip") {
      sc = 0.85 + 0.3 * easeOutBack(act);
      const u = Math.min(1, Math.max(0, (o.age - 120) / 1600));
      rot = o.angle * (u * u * (3 - 2 * u)) * Math.PI / 180;
    } else if (o.kind === "fill") sc = 0.85 + 0.2 * easeOutBack(act);
    else op = act;
    const left = o.ttl - o.age;
    if (left < 600) op = Math.max(0, left / 600);
    c.save();
    c.globalAlpha = op;
    c.translate(r.x - 2, r.y + r.h / 2);
    c.rotate(rot); c.scale(sc, sc);
    const fs = r.h * 0.82, h = r.h + 2;
    if (o.kind === "outline") {
      c.strokeStyle = o.ink; c.lineWidth = 1.5;
      c.strokeRect(0, -h / 2, r.w + 4, h);
    } else {
      c.font = `${o.kind === "accent" ? 700 : 600} ${fs}px ${o.font}`;
      const tw = Math.max(r.w, c.measureText(o.text).width) + 6;
      let bg = "#fff", fg = o.ink;
      if (o.kind === "fill" || o.kind === "strip" || (o.kind === "accent" && o.solid)) { bg = o.pal.bg; fg = o.pal.fg; }
      if (o.kind === "strip") { c.shadowColor = "rgba(0,0,0,.18)"; c.shadowBlur = 8; c.shadowOffsetY = 2; }
      c.fillStyle = bg; c.fillRect(0, -h / 2, tw, h);
      c.shadowColor = "transparent";
      c.fillStyle = fg; c.textBaseline = "middle";
      c.fillText(o.text, 3, 0.5);
    }
    c.restore();
  }

  async finale() {
    const a = this.a, box = $("#finale"), T = L();
    box.hidden = false;
    const finds = a.findings || [];
    const per = reduced ? 300 : this.pace.obs;
    if (finds.length) {
      box.innerHTML = `<div class="obs"><h2>${esc(T.obs)}</h2><ol>${finds.map((f) =>
        `<li>${esc(f.text)} <span class="pg">${fmtPages(f.pages)}</span></li>`).join("")}</ol></div>`;
      for (const li of box.querySelectorAll("li")) { await sleep(60); li.classList.add("in"); await sleep(per); }
      await sleep(per * 0.6);
    }
    box.innerHTML = cardHTML(a, this.count);
    await sleep(40);
    box.querySelector(".card").classList.add("in");
    this.stop();
    $("#play").textContent = "Rivedi";
  }
}

function cardHTML(a, count) {
  const T = L(), lang = a.lang || "it";
  const passed = (a.checks || []).filter((c) => c.ok).length;
  const tiles = (a.card || []).map((t) => {
    const y = t.yoy_display ? `<div class="y ${t.yoy_display.startsWith("+") ? "up" : "down"}">${esc(t.yoy_display)} ${esc(T.yoy)}</div>` : "";
    return `<div class="tile"><div class="l">${esc(lang === "en" && t.en ? t.en : t.it)}</div><div class="v">${esc(t.display)}</div>${y}<span class="pg">${fmtPages(t.pages)}</span></div>`;
  }).join("");
  return `<div class="card"><h2>${esc(a.title)}</h2><p class="sub">${esc(a.subtitle)}</p>
    <div class="tiles">${tiles}</div>
    <ul>${(a.card_findings || []).map((f) => `<li>${esc(f.text)} <span class="pg">${fmtPages(f.pages)}</span></li>`).join("")}</ul>
    <div class="foot"><span><b>${count.toLocaleString(T.locale)}</b> ${esc(T.read)} · <b>${passed}</b> ${esc(T.checks)} ${(a.checks || []).length}</span>
    <span>${esc(a.ai ? T.foot_ai : T.foot_det)}</span></div></div>`;
}

// ------------------------------------------------------------------ downloadable report

function downloadReport(a) {
  const T = L(), lang = a.lang || "it";
  const cell = (fid) => fid === null || fid === undefined ? "" : esc(a.facts[fid]?.value_fmt ?? "");
  const tables = a.pages.map((p) => {
    const rows = a.rows[p.n] || [];
    if (!rows.length) return "";
    const cols = a.cols[p.n] || [T.value];
    return `<h3>${esc(p.title)} <span class="pg">${T.p} ${p.n}</span></h3><table><tr><th>${esc(T.label)}</th>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>` +
      rows.map((r) => `<tr><td>${esc(r.label)}</td>${r.cells.map((f) => `<td class="n">${cell(f)}</td>`).join("")}</tr>`).join("") + "</table>";
  }).join("");
  const inRows = new Set(Object.values(a.rows).flat().flatMap((r) => r.cells).filter((x) => x !== null).map(String));
  const others = Object.entries(a.facts).filter(([id]) => !inRows.has(String(id)));
  const otherHTML = others.length ? `<h3>${esc(T.other)}</h3><table>` + others.map(([, f]) =>
    `<tr><td>${esc(f.label)}</td><td class="n">${esc(f.value_fmt)}</td><td class="pg">${T.p} ${f.page}</td></tr>`).join("") + "</table>" : "";
  const checks = (a.checks || []).map((c) => `<li>${c.ok ? "✓" : "✗"} ${esc(c.name)} — ${esc(c.ok ? T.ok : T.ko)}${c.detail && !c.ok ? " (" + esc(c.detail) + ")" : ""}</li>`).join("");
  const today = new Date().toLocaleDateString(T.locale, { day: "numeric", month: "long", year: "numeric" });
  const html = `<!doctype html><html lang="${lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(a.title)} — Spider Analyst</title><style>
body{font:15px/1.5 -apple-system,Helvetica,Arial,sans-serif;color:#1d1c26;max-width:860px;margin:32px auto;padding:0 20px}
h1{font:700 32px/1.1 Charter,Georgia,serif;margin:0 0 4px}h2{font:700 21px Charter,Georgia,serif;margin:30px 0 10px}
h3{font:600 16px Charter,Georgia,serif;margin:22px 0 6px}.sub{color:#6c6a7c;margin:0 0 6px}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:16px}.tile{border:1px solid #d6d4e0;border-radius:6px;padding:10px 12px}
.l{font-size:12px;color:#6c6a7c}.v{font:700 22px/1.2 -apple-system,Helvetica,sans-serif}.up{color:#0f8a5f;font-weight:600;font-size:13px}.down{color:#c8323c;font-weight:600;font-size:13px}
.pg{color:#ff2d8f;font-size:12px;font-weight:600;white-space:nowrap}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
td,th{border-bottom:1px solid #eee;padding:4px 6px;text-align:left}th{color:#6c6a7c;font-weight:500}.n{text-align:right;white-space:nowrap}
li{margin:0 0 6px}.foot{color:#6c6a7c;font-size:12px;margin-top:30px;border-top:1px solid #d6d4e0;padding-top:10px}
@media print{body{margin:0}.noprint{display:none}}@media(max-width:640px){.tiles{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<h1>${esc(a.title)}</h1><p class="sub">${esc(a.subtitle)}</p>
<p class="sub">${esc(T.source)}: ${/^https?:/.test(a.source || "") ? `<a href="${esc(a.source)}">${esc(a.source)}</a>` : esc(a.source || "")}</p>
<div class="tiles">${(a.card || []).map((t) => `<div class="tile"><div class="l">${esc(lang === "en" && t.en ? t.en : t.it)}</div><div class="v">${esc(t.display)}</div>${t.yoy_display ? `<div class="${t.yoy_display.startsWith("+") ? "up" : "down"}">${esc(t.yoy_display)} ${esc(T.yoy)}</div>` : ""}<span class="pg">${fmtPages(t.pages)}</span></div>`).join("")}</div>
<h2>${esc(T.obs)}</h2><ol>${(a.findings || []).map((f) => `<li>${esc(f.text)} <span class="pg">${fmtPages(f.pages)}</span></li>`).join("")}</ol>
${checks ? `<h2>${esc(T.controls)}</h2><ul>${checks}</ul>` : ""}
<h2>${esc(T.figures)} (${Object.keys(a.facts).length})</h2>${tables}${otherHTML}
<p class="foot">${esc(T.made)} ${esc(today)}. ${esc(a.ai ? T.foot_ai : T.foot_det)}. <span class="noprint">${esc(T.print)}</span></p>
</body></html>`;
  const name = (a.title || "report").normalize("NFD").replace(/[^\w]+/g, "-").replace(/^-|-$/g, "").toLowerCase();
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${name}-report-${lang}.html`;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 10000);
}

// ------------------------------------------------------------------ hero spider (home)

function hero() {
  const cv = $("#hero-spider"), ctx = cv.getContext("2d"), dpr = devicePixelRatio || 1;
  cv.width = 220 * dpr; cv.height = 150 * dpr; cv.style.width = "220px"; cv.style.height = "150px";
  const sp = new Spider(0.42);
  sp.place(110, 75, Math.PI / 2);
  let last = performance.now(), t = 0;
  const loop = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000); last = now; t += dt;
    if (!$("#home").hidden) {
      sp.update({ x: 110 + Math.sin(t * 0.8) * 30, y: 75 + Math.sin(t * 1.3) * 10 }, dt, Math.PI / 2);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, 220, 150);
      sp.draw(ctx);
    }
    if (!reduced) requestAnimationFrame(loop);
  };
  if (reduced) { sp.draw(ctx); return; }
  requestAnimationFrame(loop);
}

// the reader relies on Chromium behaviour; Safari and Firefox get a clear notice instead of a silent spider
const isChromium = !!navigator.userAgentData || /\b(Chrome|Chromium|Edg|OPR|Brave)\//.test(navigator.userAgent);
if (!isChromium) $("#browser-warn").hidden = false;

refreshStatus();
loadRecent();
hero();
const deep = new URLSearchParams(location.search).get("doc");
if (deep) openAnalysis(deep);
