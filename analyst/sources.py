"""Network access with a disk cache (.data/).

SEC EDGAR     company list, submissions, filing documents (10-K, 10-Q, 20-F, 40-F)
ESEF          filings.xbrl.org: European annual reports in inline XBRL
Yahoo Finance search across every asset class and daily price history

SEC asks for a User-Agent that identifies the caller: set SPIDER_SEC_UA or
"sec_user_agent" in ~/.spider-analyst/config.json. The default is generic.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlencode

import httpx

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("SPIDER_DATA_DIR", ROOT / ".data"))
CONFIG_FILE = Path.home() / ".spider-analyst" / "config.json"
DEFAULT_SEC_UA = "SpiderAnalyst/1.0 (local research tool; spider-analyst@example.com)"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
SEC_FORMS = ("10-K", "10-K/A", "20-F", "40-F", "10-Q")
DAY = 86400


class SourceError(Exception):
    pass


def config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        return {}


def sec_user_agent() -> str:
    return os.environ.get("SPIDER_SEC_UA") or config().get("sec_user_agent") or DEFAULT_SEC_UA


_client: Optional[httpx.Client] = None
_last_sec = 0.0


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=httpx.Timeout(60, connect=15), follow_redirects=True, http2=False)
    return _client


def _cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode()).hexdigest()[:24]
    return CACHE / "http" / h[:2] / h


def fetch(url: str, *, ttl: Optional[float] = DAY, max_bytes: int = 120_000_000) -> bytes:
    """GET with disk cache. ttl=None caches forever (filed documents never change)."""
    p = _cache_path(url)
    if p.exists() and (ttl is None or time.time() - p.stat().st_mtime < ttl):
        return p.read_bytes()
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url)
    headers = {"Accept-Encoding": "gzip, deflate"}
    if host.endswith("sec.gov"):
        global _last_sec
        wait = 0.12 - (time.time() - _last_sec)      # SEC fair access: max 10 requests/s
        if wait > 0:
            time.sleep(wait)
        _last_sec = time.time()
        headers["User-Agent"] = sec_user_agent()
    else:
        headers["User-Agent"] = BROWSER_UA
    try:
        with client().stream("GET", url, headers=headers) as r:
            if r.status_code >= 400:
                raise SourceError(f"{host} ha risposto {r.status_code} per {url}")
            chunks, size = [], 0
            for c in r.iter_bytes():
                size += len(c)
                if size > max_bytes:
                    raise SourceError(f"Documento troppo grande (> {max_bytes // 1_000_000} MB): {url}")
                chunks.append(c)
    except httpx.HTTPError as e:
        if p.exists():                                  # offline: stale cache is better than nothing
            return p.read_bytes()
        raise SourceError(f"Impossibile raggiungere {host}: {e}") from e
    data = b"".join(chunks)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(p)
    return data


def fetch_json(url: str, ttl: Optional[float] = DAY):
    try:
        return json.loads(fetch(url, ttl=ttl))
    except ValueError as e:
        raise SourceError(f"Risposta non valida da {url}") from e


# ---------------------------------------------------------------- SEC EDGAR

def sec_companies() -> list[dict]:
    data = fetch_json("https://www.sec.gov/files/company_tickers.json", ttl=7 * DAY)
    rows = data.values() if isinstance(data, dict) else data
    return [{"cik": int(r["cik_str"]), "ticker": r["ticker"], "name": r["title"]} for r in rows]


def sec_lookup(query: str) -> Optional[dict]:
    q = query.strip().upper()
    if q.isdigit():
        return {"cik": int(q), "ticker": "", "name": ""}
    comps = sec_companies()
    for c in comps:
        if c["ticker"] == q or c["ticker"] == q.replace(".", "-"):
            return c
    for c in comps:
        if c["name"].upper() == q:
            return c
    return None


def sec_search(query: str, limit: int = 8) -> list[dict]:
    q = query.strip().upper()
    if not q:
        return []
    scored = []
    for c in sec_companies():
        t, n = c["ticker"], c["name"].upper()
        if t == q:
            s = 0
        elif n.startswith(q):
            s = 1
        elif t.startswith(q):
            s = 2
        elif q in n:
            s = 3
        else:
            continue
        scored.append((s, len(n), c))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [c for _, _, c in scored[:limit]]


def sec_filings(cik: int, forms=SEC_FORMS) -> list[dict]:
    sub = fetch_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", ttl=DAY)
    rec = sub.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(rec.get("form", [])):
        if form not in forms:
            continue
        acc = rec["accessionNumber"][i]
        doc = rec["primaryDocument"][i]
        if not doc:
            continue
        out.append({
            "source": "sec",
            "form": form,
            "filed": rec["filingDate"][i],
            "period": rec.get("reportDate", [""] * (i + 1))[i],
            "ixbrl": bool(rec.get("isInlineXBRL", [0] * (i + 1))[i]),
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}",
            "company": sub.get("name", ""),
            "ticker": (sub.get("tickers") or [""])[0],
        })
    return out


def sec_latest(query: str, form: Optional[str] = None) -> dict:
    c = sec_lookup(query)
    if not c:
        raise SourceError(f"Nessuna società SEC trovata per «{query}».")
    filings = [f for f in sec_filings(c["cik"]) if f["ixbrl"]]
    if form:
        filings = [f for f in filings if f["form"] == form]
    else:
        annual = [f for f in filings if f["form"] in ("10-K", "20-F", "40-F")]
        filings = annual or filings
    if not filings:
        raise SourceError(f"Nessun bilancio iXBRL disponibile su EDGAR per {c.get('name') or query}.")
    return filings[0]


# ---------------------------------------------------------------- ESEF (filings.xbrl.org)

XBRL_ORG = "https://filings.xbrl.org"


def esef_entities(name: str, limit: int = 8) -> list[dict]:
    name = name.strip()
    if not name:
        return []
    if re.fullmatch(r"[0-9A-Z]{20}", name.upper()):          # LEI
        flt = [{"name": "identifier", "op": "eq", "val": name.upper()}]
    else:
        flt = [{"name": "name", "op": "ilike", "val": f"%{name}%"}]
    url = f"{XBRL_ORG}/api/entities?" + urlencode({"filter": json.dumps(flt), "page[size]": limit})
    out = []
    for e in fetch_json(url, ttl=7 * DAY).get("data", []):
        a = e.get("attributes", {})
        lei = a.get("identifier") or e.get("id")
        if lei:
            out.append({"lei": lei, "name": a.get("name", ""), "country": a.get("country", "")})
    # shortest name first: "Ferrari N.V." before "Ferrari Group plc"
    out.sort(key=lambda x: len(x["name"]))
    return out[:limit]


def esef_filings(lei: str) -> list[dict]:
    data = fetch_json(f"{XBRL_ORG}/api/entities/{quote(lei)}/filings?page[size]=50", ttl=DAY)
    out = []
    for f in data.get("data", []):
        a = f.get("attributes", {})
        rep = a.get("report_url")
        if not rep:
            continue
        out.append({
            "source": "esef",
            "form": "ESEF",
            "period": a.get("period_end", ""),
            "filed": (a.get("date_added") or "")[:10],
            "url": rep if rep.startswith("http") else XBRL_ORG + rep,
            "errors": a.get("error_count", 0),
            "lang": a.get("language") or "",
        })
    out.sort(key=lambda x: (x["period"], x["filed"]), reverse=True)
    return out


def esef_latest(query: str) -> dict:
    ents = esef_entities(query)
    if not ents:
        raise SourceError(f"Nessun emittente ESEF trovato per «{query}» su filings.xbrl.org.")
    ent = ents[0]
    fil = esef_filings(ent["lei"])
    if not fil:
        raise SourceError(f"Nessuna relazione ESEF pubblicata per {ent['name']}.")
    best = fil[0]
    best["company"] = ent["name"]
    return best


# ---------------------------------------------------------------- Yahoo Finance

YQ = "https://query1.finance.yahoo.com"
QUOTE_TYPES = {
    "EQUITY": "Azione", "ETF": "ETF", "MUTUALFUND": "Fondo", "INDEX": "Indice", "CURRENCY": "Valuta",
    "CRYPTOCURRENCY": "Crypto", "FUTURE": "Future", "OPTION": "Opzione", "MONEYMARKET": "Monetario",
}


def yahoo_search(query: str, limit: int = 10) -> list[dict]:
    q = query.strip()
    if not q:
        return []
    url = f"{YQ}/v1/finance/search?" + urlencode({"q": q, "quotesCount": limit, "newsCount": 0, "listsCount": 0})
    data = fetch_json(url, ttl=DAY)
    out = []
    for r in data.get("quotes", []):
        sym = r.get("symbol")
        if not sym:
            continue
        out.append({
            "symbol": sym,
            "name": r.get("longname") or r.get("shortname") or sym,
            "type": r.get("quoteType", ""),
            "type_it": QUOTE_TYPES.get(r.get("quoteType", ""), r.get("typeDisp") or r.get("quoteType", "")),
            "exchange": r.get("exchDisp") or r.get("exchange", ""),
        })
    return out


def yahoo_history(symbol: str, years: int = 10) -> dict:
    rng = "max" if years > 10 else f"{years}y"
    url = f"{YQ}/v8/finance/chart/{quote(symbol)}?" + urlencode({"range": rng, "interval": "1d", "includeAdjustedClose": "true", "events": "div,splits"})
    data = fetch_json(url, ttl=6 * 3600)
    res = (data.get("chart") or {}).get("result") or []
    if not res:
        err = (data.get("chart") or {}).get("error") or {}
        raise SourceError(f"Nessuno storico prezzi per {symbol}: {err.get('description', 'simbolo sconosciuto')}")
    r = res[0]
    ts = r.get("timestamp") or []
    q = (r.get("indicators", {}).get("quote") or [{}])[0]
    adj = (r.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
    closes = adj or q.get("close") or []
    from datetime import datetime, timezone
    points = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        points.append((datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat(), float(c)))
    if len(points) < 20:
        raise SourceError(f"Storico prezzi troppo corto per {symbol}.")
    meta = r.get("meta", {})
    return {
        "symbol": meta.get("symbol", symbol),
        "name": meta.get("longName") or meta.get("shortName") or symbol,
        "currency": meta.get("currency", ""),
        "type": meta.get("instrumentType", ""),
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName", ""),
        "points": points,
    }
