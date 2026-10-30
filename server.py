"""Spider Analyst local server: http://127.0.0.1:8765

Listens on localhost only. Long analyses run as background jobs the page polls.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from analyst import ai, pdfreport, pipeline, pptx_report, sources, xlsx_export
from analyst.i18n import system_lang, ui

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
PORT = int(os.environ.get("SPIDER_PORT", "8765"))
MAX_UPLOAD = 400_000_000

app = FastAPI(title="Spider Analyst", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB), name="static")
pool = ThreadPoolExecutor(max_workers=3)
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


@app.middleware("http")
async def local_only(request: Request, call_next):
    # DNS-rebinding guard: only answer to localhost names
    host = (request.headers.get("host") or "").split(":")[0]
    if host not in ("127.0.0.1", "localhost", "[::1]"):
        return Response("forbidden", status_code=403)
    return await call_next(request)


@app.middleware("http")
async def no_stale_app(request: Request, call_next):
    # Safari keeps old scripts around: the app's own files are never cached
    resp = await call_next(request)
    if request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _version() -> str:
    return str(int(max(p.stat().st_mtime for p in WEB.glob("*.*"))))


@app.get("/", response_class=HTMLResponse)
def index():
    html = (WEB / "index.html").read_text(encoding="utf-8").replace("__V__", _version()).replace("__UI__", system_lang())
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- settings

@app.get("/api/status")
def status():
    cfg = sources.config()
    return {"ai": ai.available(), "ai_name": ai.provider_name(), "ai_providers": ai.status(), "sec_user_agent": sources.sec_user_agent(),
            "sec_ua_custom": bool(os.environ.get("SPIDER_SEC_UA") or cfg.get("sec_user_agent")),
            "model": ai.MODEL, "ui_lang": system_lang()}


@app.post("/api/settings")
async def settings(request: Request):
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(415, ui("JSON richiesto", "JSON required"))
    body = await request.json()
    sources.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if "sec_user_agent" in body:
        ua = str(body["sec_user_agent"]).strip()[:200]
        cfg = sources.config()
        if ua:
            cfg["sec_user_agent"] = ua
        else:
            cfg.pop("sec_user_agent", None)
        sources.CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    if "ai_provider" in body:
        pid = str(body["ai_provider"])
        if pid not in ai.PROVIDERS:
            raise HTTPException(400, ui("fornitore AI sconosciuto", "unknown AI provider"))
        key = str(body.get("ai_key") or "").strip()
        if key and (len(key) < 10 or len(key) > 300 or re.search(r"\s", key)):
            raise HTTPException(400, ui("La chiave API non sembra valida.", "The API key does not look valid."))
        model = body.get("ai_model")
        if model is not None and (len(str(model)) > 120 or re.search(r"\s", str(model).strip())):
            raise HTTPException(400, ui("Nome del modello non valido.", "Invalid model name."))
        ai.save_settings(pid, key or None, None if model is None else str(model), remove=bool(body.get("ai_remove")))
    return status()


@app.post("/api/ai/test")
def ai_test():
    """One tiny request to the AI in use, so the setup screen can tell whether it works."""
    try:
        return {"ok": True, "provider": ai.test()}
    except ai.AIError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")


def _need_ai():
    # the spider reads every document with the AI: nothing starts until one is set up
    if not ai.available():
        raise HTTPException(409, ui("Configura prima l'AI (chiave API o abbonamento) nelle impostazioni.",
                                    "Set up the AI first (API key or subscription) in Settings."))


# ---------------------------------------------------------------- search

@app.get("/api/search")
def search(q: str):
    q = q.strip()[:80]
    if not q:
        return {"sec": [], "esef": [], "market": [], "errors": []}
    out, errors = {"sec": [], "esef": [], "market": []}, []
    tasks = {"sec": lambda: sources.sec_search(q), "esef": lambda: sources.esef_entities(q, 6), "market": lambda: sources.yahoo_search(q)}
    futs = {k: pool.submit(f) for k, f in tasks.items()}
    names = {"sec": "SEC EDGAR", "esef": "filings.xbrl.org", "market": "Yahoo Finance"}
    for k, fut in futs.items():
        try:
            out[k] = fut.result(timeout=25)
        except Exception as e:
            errors.append(f"{names[k]}: {e}")
    if not out["market"]:
        out["market"] = sources.fallback_symbols(q)
        if out["market"]:
            errors = [e for e in errors if not e.startswith("Yahoo")]
    out["errors"] = errors
    return out


# ---------------------------------------------------------------- jobs

def _start(req: dict) -> str:
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "status": "running", "step": ui("In coda", "Queued"), "progress": 0.02, "error": None, "analysis_id": None, "t": time.time()}
    with jobs_lock:
        jobs[jid] = job

    def progress(step: str, p: float):
        job["step"], job["progress"] = step, p

    def work():
        try:
            a = pipeline.relang(req["id"], req["lang"], progress) if req["kind"] == "relang" else pipeline.run(req, progress)
            job.update(status="done", progress=1.0, step=ui("Pronto", "Ready"), analysis_id=a["id"])
        except sources.SourceError as e:
            job.update(status="error", error=str(e))
        except Exception as e:  # keep the server alive; show the reason
            job.update(status="error", error=ui("Errore imprevisto: ", "Unexpected error: ") + f"{type(e).__name__}: {e}")
    pool.submit(work)
    return jid


@app.post("/api/analyze")
async def analyze(request: Request):
    body = await request.json()
    kind = body.get("kind")
    if kind not in ("sec", "esef", "market", "url"):
        raise HTTPException(400, ui("tipo di richiesta non valido", "invalid request type"))
    _need_ai()
    req = {k: body[k] for k in ("kind", "query", "symbol", "url", "form", "refresh", "lang") if k in body}
    return {"job": _start({**req, "ai": True})}


@app.post("/api/relang")
async def relang(request: Request):
    body = await request.json()
    lang = body.get("lang")
    if lang not in ("it", "en") or not re.fullmatch(r"[0-9a-f]{16}", str(body.get("id", ""))):
        raise HTTPException(400, ui("richiesta non valida", "invalid request"))
    _need_ai()
    return {"job": _start({"kind": "relang", "id": body["id"], "lang": lang})}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), lang: str = Form("it")):
    _need_ai()
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, ui("File troppo grande (max 400 MB)", "File too large (max 400 MB)"))
    return {"job": _start({"kind": "upload", "data": data, "name": file.filename or "documento", "ai": True, "lang": lang})}


@app.get("/api/job/{jid}")
def job(jid: str):
    j = jobs.get(jid)
    if not j:
        raise HTTPException(404, ui("job sconosciuto", "unknown job"))
    return {k: v for k, v in j.items() if k != "t"}


# ---------------------------------------------------------------- documents

@app.get("/api/doc/{aid}")
def doc(aid: str):
    a = pipeline.load(aid)
    if not a:
        raise HTTPException(404, ui("analisi non trovata", "analysis not found"))
    return JSONResponse(a)


CSP = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; font-src data: 'self'"


@app.get("/api/doc/{aid}/view", response_class=HTMLResponse)
def view(aid: str):
    if not pipeline.load(aid):
        raise HTTPException(404)
    return FileResponse(pipeline.DOCS / aid / "view.html", media_type="text/html",
                        headers={"Content-Security-Policy": CSP, "Cache-Control": "no-store"})


@app.get("/api/doc/{aid}/img/{name}")
def doc_img(aid: str, name: str):
    if not re.fullmatch(r"[0-9a-f]{16}", aid) or not re.fullmatch(r"p\d{1,4}\.(png|jpg)", name):
        raise HTTPException(404)
    p = pipeline.DOCS / aid / "img" / name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg" if name.endswith(".jpg") else "image/png")


EXPORTS = {
    "report.pdf": ("application/pdf", "report"),
    "report.pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "slides"),
    "data.xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "data"),
}


@app.get("/api/doc/{aid}/{what}")
def export(aid: str, what: str, theme: str = "neon"):
    """The report as a PDF or a PowerPoint deck in the app's style, or the figures as an Excel workbook (made by the server)."""
    if what not in EXPORTS:
        raise HTTPException(404, ui("formato non disponibile", "format not available"))
    a = pipeline.load(aid)
    if not a:
        raise HTTPException(404, ui("analisi non trovata", "analysis not found"))
    name = re.sub(r"[^\w-]+", "-", a.get("title") or "report").strip("-").lower()[:80] or "report"
    from analyst import themes
    theme = theme if theme in themes.THEMES else themes.DEFAULT
    media, suffix = EXPORTS[what]
    data = pdfreport.build(a, theme) if what == "report.pdf" else pptx_report.build(a, theme) if what == "report.pptx" else xlsx_export.build(a)
    ext = what.rsplit(".", 1)[1]
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{name}-{suffix}-{a.get("lang", "en")}.{ext}"',
                             "Cache-Control": "no-store"})


@app.get("/api/original")
def original(kind: str, query: str = "", symbol: str = ""):
    """The original document behind a search result: the SEC filing, the ESEF report, or the price history as CSV."""
    try:
        if kind == "sec":
            f = sources.sec_latest(query)
            data = sources.fetch(f["url"], ttl=None)
            ext = f["url"].rsplit(".", 1)[-1].lower() if "." in f["url"].rsplit("/", 1)[-1] else "htm"
            name = f"{f.get('ticker') or query}-{f.get('form', 'filing')}-{f.get('period') or f.get('filed', '')}.{ext}"
            media = "text/html" if ext in ("htm", "html") else "application/octet-stream"
        elif kind == "esef":
            f = sources.esef_latest(query)
            data = sources.fetch(f["url"], ttl=None)
            fname = f["url"].rsplit("/", 1)[-1] or "report.xhtml"
            name, media = fname, "application/xhtml+xml" if fname.endswith(("xhtml", "html")) else "application/octet-stream"
        elif kind == "market":
            h = sources.price_history(symbol)
            lines = ["date,close,currency,source"] + [f"{d},{v:.8g},{h.get('currency', '')},{h.get('source', '')}" for d, v in h["points"]]
            data = ("\n".join(lines) + "\n").encode()
            name, media = f"{h['symbol']}-daily-prices.csv", "text/csv"
        else:
            raise HTTPException(400, ui("richiesta non valida", "invalid request"))
    except sources.SourceError as e:
        raise HTTPException(502, str(e))
    safe = re.sub(r"[^\w.^=-]+", "-", name).strip("-") or "document"
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{safe}"'})


@app.get("/api/recent")
def recent():
    out = []
    if pipeline.DOCS.exists():
        for d in sorted(pipeline.DOCS.iterdir(), key=lambda p: -p.stat().st_mtime)[:12]:
            a = pipeline.load(d.name)
            if a:
                out.append({"id": a["id"], "title": a["title"], "subtitle": a["subtitle"], "kind": a["kind"]})
    return out


IMG_TYPES = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"GIF8": "image/gif"}


@app.get("/api/asset")
def asset(u: str):
    """Images referenced by filings (logos, charts), only from the filing hosts."""
    host = urlparse(u).hostname or ""
    if urlparse(u).scheme != "https" or host not in ixbrl_hosts():
        raise HTTPException(403)
    try:
        data = sources.fetch(u, ttl=None, max_bytes=15_000_000)
    except sources.SourceError:
        raise HTTPException(404)
    mt = next((t for sig, t in IMG_TYPES.items() if data.startswith(sig)), None)
    if mt is None and data.lstrip()[:5].lower() in (b"<?xml", b"<svg "):
        return Response(status_code=415)    # SVG may carry scripts: not served
    if mt is None:
        raise HTTPException(415)
    return Response(data, media_type=mt, headers={"Cache-Control": "max-age=86400"})


def ixbrl_hosts():
    from analyst.ixbrl import ASSET_HOSTS
    return ASSET_HOSTS


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
