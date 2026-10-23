import { Spider, thread } from "./spider.js";

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
  show("loading"); loadingReset(`Carico ${f.name}`);
  try { const { job } = await api("/api/upload", { method: "POST", body: fd }); await follow(job); } catch (err) { loadingError(err.message); }
}

async function start(req) {
  req.ai = $("#opt-ai").checked;
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

// seconds: stop on a figure / key figure / heading, walking factor, hop limits, finale step
const PACES = {
  normale: { fig: 0.28, key: 0.7, head: 0.45, walk: 0.034, minHop: 0.12, maxHop: 1.4, cam: 4, obs: 1600 },
  veloce: { fig: 0.1, key: 0.3, head: 0.2, walk: 0.015, minHop: 0.06, maxHop: 0.6, cam: 7, obs: 1000 },
  turbo: { fig: 0.04, key: 0.14, head: 0.1, walk: 0.008, minHop: 0.03, maxHop: 0.35, cam: 10, obs: 600 },
};
$("#dur2").innerHTML = $("#opt-dur").innerHTML;
$("#dur2").addEventListener("change", () => { $("#opt-dur").value = $("#dur2").value; state.director?.restart(); });
$("#back").addEventListener("click", () => { state.director?.stop(); show("home"); loadRecent(); });
$("#play").addEventListener("click", () => state.director?.toggle());
$("#restart").addEventListener("click", () => state.director?.restart());

async function openAnalysis(id) {
  const a = await api("/api/doc/" + id);
  state.analysis = a;
  show("reader");
  $("#dur2").value = $("#opt-dur").value;
  $("#r-title").textContent = a.title;
  $("#r-sub").textContent = a.subtitle;
  $("#r-m").textContent = a.total_facts.toLocaleString("it-IT");
  $("#r-warn").textContent = (a.warnings || []).join(" ");
  state.director?.stop();
  await new Promise((res) => { iframe.onload = res; iframe.src = `/api/doc/${id}/view`; });
  state.director = new Director(a);
  state.director.restart();
}

function fmtPages(pages) {
  if (!pages?.length) return "";
  return (pages.length > 1 ? "pp. " : "p. ") + pages.join(", ");
}

class Director {
  constructor(a) {
    this.a = a;
    this.doc = iframe.contentDocument;
    this.spider = new Spider(28);
    this.raf = 0;
    this.playing = false;
    this.measure();
    this.spider.snap = (x, y, r) => this.wordAt(x, y, r);
    this.spider.onStep = (r) => this.touched.push({ r, t: this.clock });
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
    this.buildStops();
  }

  relayout() {
    const W = stage.clientWidth, H = stage.clientHeight, dpr = devicePixelRatio || 1;
    for (const cv of [marksCv, spiderCv]) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    // fit the widest page
    const pageW = Math.max(...[...this.doc.querySelectorAll(".sa-page")].map((p) => p.getBoundingClientRect().width), 600);
    this.scale = Math.min(1.15, (W - 24) / pageW);
    this.W = W; this.H = H; this.dpr = dpr;
    this.spider.size = 32 / this.scale;
    if (!this.playing && this.timeline) this.frame(performance.now(), true);
  }

  rectOf(el) {
    const r = el.getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  }

  buildStops() {
    const a = this.a, stops = [];
    const sections = [...this.doc.querySelectorAll(".sa-page")];
    sections.forEach((sec, si) => {
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
      if (si === 0) this.firstPageRect = this.rectOf(sec);
    });
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
        return { x: rr.left, y: rr.top, w: rr.width, h: rr.height };
      }
    }
    return null;
  }

  // every figure is visited; the pace only changes how long the spider stops and how fast it runs
  plan(pace) {
    const P = PACES[pace] || PACES.veloce;
    const stops = this.allStops;
    const dwell = (s) => s.type === "h" ? P.head : s.type === "page" ? P.head : s.fact.key ? P.key : P.fig;
    const pts = stops.map((s) => this.anchor(s));
    let prev = { x: pts[0].x - 140, y: pts[0].y - 160 };
    let t = 0;
    this.timeline = stops.map((s, i) => {
      const d = Math.hypot(pts[i].x - prev.x, pts[i].y - prev.y);
      prev = pts[i];
      // walking time grows with sqrt(distance): short hops are quick and page jumps don't drag
      const travel = Math.min(P.maxHop, Math.max(P.minHop, P.walk * Math.sqrt(d)));
      const seg = { s, p: pts[i], t0: t, t1: t + travel, t2: t + travel + dwell(s) };
      t = seg.t2;
      return seg;
    });
    this.start0 = { x: pts[0].x - 140, y: pts[0].y - 160 };
    this.planned = new Set(stops.filter((x) => x.type === "f").map((x) => String(x.id)));
    this.total = t;
    this.pace = P;
  }

  anchor(s) {
    const sz = this.spider.size;
    if (s.type === "page") return { x: s.r.x + 80, y: s.r.y + 60 };
    if (s.type === "h") return { x: s.r.x - sz * 0.4, y: s.r.y + s.r.h / 2 - sz * 1.1 };
    return { x: s.r.x + s.r.w / 2, y: s.r.y - sz * 1.25 };
  }

  // caret position -> the word under a foot
  wordAt(x, y, r) {
    const d = this.doc;
    let node, off;
    if (d.caretRangeFromPoint) {
      const c = d.caretRangeFromPoint(x, y);
      if (!c) return null;
      node = c.startContainer; off = c.startOffset;
    } else if (d.caretPositionFromPoint) {
      const c = d.caretPositionFromPoint(x, y);
      if (!c) return null;
      node = c.offsetNode; off = c.offset;
    } else return null;
    if (!node || node.nodeType !== 3) return null;
    const txt = node.data;
    let a = off, b = off;
    while (a > 0 && !/\s/.test(txt[a - 1])) a--;
    while (b < txt.length && !/\s/.test(txt[b])) b++;
    if (b <= a) return null;
    const range = d.createRange();
    range.setStart(node, a); range.setEnd(node, b);
    const rr = range.getBoundingClientRect();
    if (!rr.width || rr.width > 400) return null;
    const cx = Math.max(rr.left + 2, Math.min(x, rr.right - 2)), cy = rr.top + rr.height * 0.55;
    if (Math.hypot(cx - x, cy - y) > r) return null;
    return { x: cx, y: cy, rect: { x: rr.left, y: rr.top, w: rr.width, h: rr.height } };
  }

  restart() {
    this.stop();
    $("#finale").hidden = true; $("#finale").innerHTML = "";
    this.paceName = $("#opt-dur").value;
    this.relayout();
    this.plan(this.paceName);
    this.clock = 0; this.idx = -1; this.touched = []; this.marks = []; this.threads = []; this.done = false;
    this.count = 0; this.page = null;
    $("#r-n").textContent = "0";
    $("#r-other-list").innerHTML = "";
    $("#r-sec-title").textContent = "";
    $("#r-table thead").innerHTML = ""; $("#r-table tbody").innerHTML = "";
    this.cam = { x: 0, y: Math.max(0, this.start0.y - 120) };
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
        return { x: prev.x + (g.p.x - prev.x) * e, y: prev.y + (g.p.y - prev.y) * e, moving: true, from: prev, to: g.p };
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

    // arrivals
    while (this.timeline && this.idx + 1 < this.timeline.length && t >= this.timeline[this.idx + 1].t1) {
      this.idx++;
      this.arrive(this.timeline[this.idx]);
    }
    const pos = this.bodyAt(t);
    const seg = this.timeline?.[this.idx];
    const face = seg && t < seg.t2 ? Math.atan2(seg.s.r.y + seg.s.r.h / 2 - pos.y, seg.s.r.x + seg.s.r.w / 2 - pos.x) : null;
    if (!still) this.spider.update(pos.x, pos.y, dt, face);

    // camera follows the spider (smoothly), clamped to the document
    const s = this.scale, vw = this.W / s, vh = this.H / s;
    const tx = Math.max(0, Math.min(this.docW - vw, this.spider.x - vw * 0.5));
    const ty = Math.max(0, Math.min(this.docH - vh, this.spider.y - vh * 0.42));
    const k = still || reduced ? 1 : Math.min(1, dt * this.pace.cam);
    this.cam.x += (Math.max(0, tx) - this.cam.x) * k;
    this.cam.y += (ty - this.cam.y) * k;
    if (this.docW * s <= this.W) this.cam.x = -(this.W / s - this.docW) / 2;
    layer.style.transform = `scale(${s}) translate(${-this.cam.x}px, ${-this.cam.y}px)`;

    this.draw(pos);

    if (!this.done && this.timeline && t > this.total + 0.6) {
      this.done = true;
      this.finale();
    }
    if (this.playing) this.raf = requestAnimationFrame((tt) => this.frame(tt));
  }

  arrive(g) {
    const s = g.s, now = this.clock;
    if (s.first && s.page !== this.page) this.enterPage(s.page);
    if (s.type === "h") {
      this.marks.push({ kind: "pill", r: s.r, t: now });
      return;
    }
    if (s.type !== "f") return;
    this.marks.push({ kind: "box", r: s.r, t: now, key: s.fact.key });
    if (s.label) this.marks.push({ kind: "hl", r: s.label, t: now });
    this.threads.push({ to: { x: s.r.x + s.r.w / 2, y: s.r.y + s.r.h / 2 }, t: now, key: s.fact.key });
    this.count++;
    $("#r-n").textContent = this.count.toLocaleString("it-IT");
    this.report(s);
  }

  enterPage(n) {
    this.page = n;
    const a = this.a, p = a.pages.find((x) => x.n === n);
    $("#r-sec-title").textContent = `${p ? p.title : "Pagina " + n} · p. ${n}`;
    const cols = a.cols[n] || ["Valore"];
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
    li.innerHTML = `<span>${esc(s.fact.label)}</span><b>${esc(s.fact.value_fmt)}</b><i>p. ${s.page}</i>`;
    const list = $("#r-other-list");
    list.prepend(li);
    while (list.children.length > 400) list.lastChild.remove();
  }

  draw(pos) {
    const s = this.scale, dpr = this.dpr, px = 1 / s;
    const set = (ctx) => { ctx.setTransform(dpr * s, 0, 0, dpr * s, -this.cam.x * s * dpr, -this.cam.y * s * dpr); };
    // marks layer (multiplied onto the page)
    const m = marksCv.getContext("2d");
    m.setTransform(1, 0, 0, 1, 0, 0);
    m.clearRect(0, 0, marksCv.width, marksCv.height);
    set(m);
    const now = this.clock;
    this.touched = this.touched.filter((w) => now - w.t < 1.4);
    for (const w of this.touched) {
      const a = 1 - (now - w.t) / 1.4;
      m.fillStyle = `rgba(255,46,136,${0.18 * a})`;
      m.strokeStyle = `rgba(255,46,136,${0.85 * a})`;
      m.lineWidth = 1 * px;
      m.fillRect(w.r.x - 1, w.r.y - 1, w.r.w + 2, w.r.h + 2);
      m.strokeRect(w.r.x - 1, w.r.y - 1, w.r.w + 2, w.r.h + 2);
    }
    for (const mk of this.marks) {
      const age = now - mk.t, grow = Math.min(1, age / 0.25);
      if (mk.kind === "hl") {
        m.fillStyle = "rgba(255,228,92,0.85)";
        m.fillRect(mk.r.x - 2, mk.r.y, (mk.r.w + 4) * grow, mk.r.h);
      } else if (mk.kind === "pill") {
        m.fillStyle = "rgba(255,46,136,0.22)";
        roundRect(m, mk.r.x - 6, mk.r.y - 3, (mk.r.w + 12) * grow, mk.r.h + 6, (mk.r.h + 6) / 2);
        m.fill();
      } else {
        m.fillStyle = mk.key ? "rgba(255,46,136,0.20)" : "rgba(255,46,136,0.10)";
        m.strokeStyle = "#ff2e88";
        m.lineWidth = (mk.key ? 2 : 1.3) * px;
        const pad = 2 + (1 - grow) * 6;
        m.fillRect(mk.r.x - pad, mk.r.y - pad, mk.r.w + pad * 2, mk.r.h + pad * 2);
        m.strokeRect(mk.r.x - pad, mk.r.y - pad, mk.r.w + pad * 2, mk.r.h + pad * 2);
      }
    }
    // spider layer
    const c = spiderCv.getContext("2d");
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, spiderCv.width, spiderCv.height);
    set(c);
    // abseiling: a long vertical move hangs from a thread
    if (pos.moving && pos.to.y - pos.from.y > 500) thread(c, { x: pos.from.x, y: pos.from.y - 40 }, this.spider.spinneret(), px, 0.9);
    const life = (th) => th.key ? Math.min(2.2, this.pace.key * 4) : Math.min(1.1, this.pace.fig * 5);
    this.threads = this.threads.filter((th) => now - th.t < life(th));
    for (const th of this.threads) {
      const life = th.key ? Math.min(2.2, this.pace.key * 4) : Math.min(1.1, this.pace.fig * 5);
      thread(c, this.spider.mouth(), th.to, px, Math.min(1, (life - (now - th.t)) / 0.4));
    }
    this.spider.draw(c, px);
  }

  async finale() {
    const a = this.a, box = $("#finale");
    box.hidden = false;
    const finds = a.findings || [];
    const per = reduced ? 300 : this.pace.obs;
    if (finds.length) {
      box.innerHTML = `<div class="obs"><h2>Osservazioni chiave</h2><ol>${finds.map((f) =>
        `<li>${esc(f.text)} <span class="pg">${fmtPages(f.pages)}</span></li>`).join("")}</ol></div>`;
      for (const li of box.querySelectorAll("li")) { await sleep(60); li.classList.add("in"); await sleep(per); }
      await sleep(per * 0.6);
    }
    const passed = (a.checks || []).filter((c) => c.ok).length;
    const tiles = (a.card || []).map((t) => {
      const y = t.yoy_display ? `<div class="y ${t.yoy_display.startsWith("+") ? "up" : "down"}">${esc(t.yoy_display)} sull'anno</div>` : "";
      return `<div class="tile"><div class="l">${esc(t.it)}</div><div class="v">${esc(t.display)}</div>${y}<span class="pg">${fmtPages(t.pages)}</span></div>`;
    }).join("");
    box.innerHTML = `<div class="card"><h2>${esc(a.title)}</h2><p class="sub">${esc(a.subtitle)}</p>
      <div class="tiles">${tiles}</div>
      <ul>${(a.card_findings || []).map((f) => `<li>${esc(f.text)} <span class="pg">${fmtPages(f.pages)}</span></li>`).join("")}</ul>
      <div class="foot"><span><b>${this.count.toLocaleString("it-IT")}</b> cifre lette · <b>${passed}</b> controlli su ${(a.checks || []).length} superati</span>
      <span>${a.ai ? "Osservazioni di Claude, verificate sulle cifre" : "Calcoli deterministici sulle cifre del documento"}</span></div></div>`;
    await sleep(40);
    box.querySelector(".card").classList.add("in");
    this.stop();
    $("#play").textContent = "Rivedi";
  }
}

function roundRect(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

// ------------------------------------------------------------------ hero spider (home)

function hero() {
  const cv = $("#hero-spider"), ctx = cv.getContext("2d"), dpr = devicePixelRatio || 1;
  cv.width = 220 * dpr; cv.height = 150 * dpr; cv.style.width = "220px"; cv.style.height = "150px";
  const sp = new Spider(22);
  sp.place(110, 80, -0.25);
  let last = performance.now(), t = 0;
  const loop = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000); last = now; t += dt;
    if (!$("#home").hidden) {
      const x = 110 + Math.sin(t * 0.7) * 26, y = 80 + Math.sin(t * 1.1) * 8;
      sp.update(x, y, dt, -0.25);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, 220, 150);
      sp.draw(ctx, 1);
    }
    if (!reduced) requestAnimationFrame(loop);
  };
  if (reduced) { sp.draw(ctx, 1); return; }
  requestAnimationFrame(loop);
}

refreshStatus();
loadRecent();
hero();
const deep = new URLSearchParams(location.search).get("doc");
if (deep) openAnalysis(deep);
