"""Spider Analyst local server: http://127.0.0.1:8765

Listens on localhost only. Long analyses run as background jobs the page polls.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from analyst import ai, pipeline, sources

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
PORT = int(os.environ.get("SPIDER_PORT", "8765"))
MAX_UPLOAD = 80_000_000

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


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- settings

@app.get("/api/status")
def status():
    cfg = sources.config()
    return {"ai": ai.available(), "ai_key": bool(ai.api_key()), "sec_user_agent": sources.sec_user_agent(),
            "sec_ua_custom": bool(os.environ.get("SPIDER_SEC_UA") or cfg.get("sec_user_agent")),
            "ffmpeg": bool(shutil.which("ffmpeg")), "model": ai.MODEL}


@app.post("/api/settings")
async def settings(request: Request):
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(415, "JSON richiesto")
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
    if "anthropic_key" in body:
        key = str(body["anthropic_key"]).strip()
        if key and not re.fullmatch(r"sk-ant-[\w-]{20,}", key):
            raise HTTPException(400, "La chiave Anthropic deve iniziare con sk-ant-")
        if key:
            ai.KEY_FILE.write_text(key)
            os.chmod(ai.KEY_FILE, 0o600)
        elif ai.KEY_FILE.exists():
            ai.KEY_FILE.unlink()
    return status()


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
    out["errors"] = errors
    return out


# ---------------------------------------------------------------- jobs

def _start(req: dict) -> str:
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "status": "running", "step": "In coda", "progress": 0.02, "error": None, "analysis_id": None, "t": time.time()}
    with jobs_lock:
        jobs[jid] = job

    def progress(step: str, p: float):
        job["step"], job["progress"] = step, p

    def work():
        try:
            a = pipeline.run(req, progress)
            job.update(status="done", progress=1.0, step="Pronto", analysis_id=a["id"])
        except sources.SourceError as e:
            job.update(status="error", error=str(e))
        except Exception as e:  # keep the server alive; show the reason
            job.update(status="error", error=f"Errore imprevisto: {type(e).__name__}: {e}")
    pool.submit(work)
    return jid


@app.post("/api/analyze")
async def analyze(request: Request):
    body = await request.json()
    kind = body.get("kind")
    if kind not in ("sec", "esef", "market", "url"):
        raise HTTPException(400, "kind non valido")
    req = {k: body[k] for k in ("kind", "query", "symbol", "url", "form", "ai", "refresh") if k in body}
    return {"job": _start(req)}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), use_ai: bool = Form(False)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File troppo grande (max 80 MB)")
    return {"job": _start({"kind": "upload", "data": data, "name": file.filename or "documento", "ai": use_ai})}


@app.get("/api/job/{jid}")
def job(jid: str):
    j = jobs.get(jid)
    if not j:
        raise HTTPException(404, "job sconosciuto")
    return {k: v for k, v in j.items() if k != "t"}


# ---------------------------------------------------------------- documents

@app.get("/api/doc/{aid}")
def doc(aid: str):
    a = pipeline.load(aid)
    if not a:
        raise HTTPException(404, "analisi non trovata")
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
    if not re.fullmatch(r"[0-9a-f]{16}", aid) or not re.fullmatch(r"p\d{1,4}\.png", name):
        raise HTTPException(404)
    p = pipeline.DOCS / aid / "img" / name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


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


# ---------------------------------------------------------------- recording

@app.post("/api/convert")
async def convert(file: UploadFile = File(...)):
    """WebM from the browser recorder -> MP4 (H.264/AAC) with ffmpeg."""
    ff = shutil.which("ffmpeg")
    if not ff:
        raise HTTPException(501, "ffmpeg non installato: il video resta in WebM (installa con: brew install ffmpeg)")
    tmp = Path(tempfile.mkdtemp(prefix="spider-"))
    src, dst = tmp / "in.webm", tmp / "spider-analyst.mp4"
    with open(src, "wb") as fh:
        while chunk := await file.read(1 << 20):
            fh.write(chunk)
    cmd = [ff, "-y", "-loglevel", "error", "-i", str(src), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-r", "30", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "128k", str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0 or not dst.exists():
        shutil.rmtree(tmp, True)
        raise HTTPException(500, f"ffmpeg: {proc.stderr[-400:]}")
    return FileResponse(dst, media_type="video/mp4", filename="spider-analyst.mp4",
                        background=BackgroundTask(shutil.rmtree, tmp, True))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
