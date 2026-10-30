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
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlencode

import httpx
from lxml import html as lxml_html

from .i18n import system_lang, ui

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("SPIDER_DATA_DIR", ROOT / ".data"))
CONFIG_FILE = Path.home() / ".spider-analyst" / "config.json"
DEFAULT_SEC_UA = "SpiderAnalyst/1.0 (local research tool; spider-analyst@example.com)"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
SEC_FORMS = ("10-K", "10-K/A", "20-F", "40-F", "10-Q", "S-1", "S-1/A", "F-1", "F-1/A", "424B4", "424B1")
REG_FORMS = ("424B4", "424B1", "S-1/A", "S-1", "F-1/A", "F-1")        # IPO prospectuses and registration statements
# the documents a user can pick: annual and quarterly reports, results releases (8-K item 2.02), prospectuses
DOC_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "8-K") + REG_FORMS
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


MAX_DOC = 400_000_000          # the largest ESEF reports run past 120 MB, mostly embedded images


def fetch(url: str, *, ttl: Optional[float] = DAY, max_bytes: int = MAX_DOC) -> bytes:
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
        for attempt in range(4):
            with client().stream("GET", url, headers=headers) as r:
                if r.status_code in (429, 502, 503) and attempt < 3:
                    # busy or rate-limited (filings.xbrl.org, SEC): wait as asked, then try again
                    try:
                        wait = min(20.0, float(r.headers.get("retry-after") or 0)) or 1.5 * 2 ** attempt
                    except ValueError:
                        wait = 1.5 * 2 ** attempt
                    time.sleep(wait)
                    continue
                if r.status_code >= 400:
                    raise SourceError(ui(f"{host} ha risposto {r.status_code} per {url}", f"{host} answered {r.status_code} for {url}"))
                chunks, size = [], 0
                for c in r.iter_bytes():
                    size += len(c)
                    if size > max_bytes:
                        raise SourceError(ui(f"Documento troppo grande (> {max_bytes // 1_000_000} MB): {url}", f"Document too large (> {max_bytes // 1_000_000} MB): {url}"))
                    chunks.append(c)
                break
    except httpx.HTTPError as e:
        if p.exists():                                  # offline: stale cache is better than nothing
            return p.read_bytes()
        raise SourceError(ui(f"Impossibile raggiungere {host}: {e}", f"Cannot reach {host}: {e}")) from e
    data = b"".join(chunks)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(data)
    try:
        tmp.replace(p)
    except OSError:          # Windows: the cached file is open in another thread; keep the old copy
        tmp.unlink(missing_ok=True)
    return data


def fetch_json(url: str, ttl: Optional[float] = DAY):
    try:
        return json.loads(fetch(url, ttl=ttl))
    except ValueError as e:
        raise SourceError(ui(f"Risposta non valida da {url}", f"Invalid response from {url}")) from e


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
    out = [c for _, _, c in scored[:limit]]
    if len(q) >= 3 and len(out) < limit:
        # companies without a ticker (e.g. before an IPO) only show up in EDGAR full-text search
        try:
            known = {c["cik"] for c in out}
            out += [c for c in sec_registrants(query) if c["cik"] not in known][:limit - len(out)]
        except (SourceError, ValueError, KeyError, TypeError):
            pass
    return out


def sec_registrants(name: str, limit: int = 5) -> list[dict]:
    """Filers whose name contains `name` and who filed a prospectus or annual report (EDGAR full-text search)."""
    url = "https://efts.sec.gov/LATEST/search-index?" + urlencode({"q": f'"{name.strip()}"', "forms": ",".join(REG_FORMS + ("10-K", "20-F"))})
    data = fetch_json(url, ttl=DAY)
    out, seen = [], set()
    for h in (data.get("hits") or {}).get("hits") or []:
        src = h.get("_source") or {}
        for cik, dn in zip(src.get("ciks") or [], src.get("display_names") or []):
            nm = re.sub(r"\s*\(CIK \d+\)\s*$", "", dn)
            nm = re.sub(r"\s*\([A-Z0-9.,\- ]{1,20}\)\s*$", "", nm).strip()          # tickers in brackets
            if not cik.isdigit() or int(cik) in seen or name.strip().lower() not in nm.lower():
                continue
            seen.add(int(cik))
            out.append({"cik": int(cik), "ticker": "", "name": nm, "form": src.get("form", ""), "filed": src.get("file_date", "")})
    return out[:limit]


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
            "items": (rec.get("items") or [""] * (i + 1))[i] or "",
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
        raise SourceError(ui(f"Nessuna società SEC trovata per «{query}».", f"No SEC company found for \"{query}\"."))
    every = sec_filings(c["cik"])
    if form:
        filings = [f for f in every if f["form"] == form]
    else:
        # the annual report; before an IPO, the latest prospectus or registration statement
        filings = ([f for f in every if f["ixbrl"] and f["form"] in ("10-K", "20-F", "40-F")]
                   or [f for f in every if f["form"] in REG_FORMS] or [f for f in every if f["ixbrl"]])
    if not filings:
        raise SourceError(ui(f"Nessun bilancio annuale o prospetto disponibile su EDGAR per {c.get('name') or query}.",
                              f"No annual report or prospectus available on EDGAR for {c.get('name') or query}."))
    return filings[0]


def _sec_what(form: str) -> str:
    base = form.split("/")[0]
    amended = ui(" (modifica)", " (amendment)") if form.endswith("/A") else ""
    what = {"10-K": ui("Bilancio annuale", "Annual report"), "20-F": ui("Bilancio annuale", "Annual report"),
            "40-F": ui("Bilancio annuale", "Annual report"), "10-Q": ui("Relazione trimestrale", "Quarterly report"),
            "8-K": ui("Comunicato sui risultati", "Results release")}.get(base) or ui("Prospetto", "Prospectus")
    return what + amended


def sec_documents(query: str, limit: int = 40) -> dict:
    """The company's filings to choose from, newest first; 8-Ks only when they announce results (item 2.02)."""
    c = sec_lookup(query)
    if not c:
        raise SourceError(ui(f"Nessuna società SEC trovata per «{query}».", f"No SEC company found for \"{query}\"."))
    docs = [f for f in sec_filings(c["cik"], DOC_FORMS) if f["form"] != "8-K" or "2.02" in f["items"].split(",")]
    for f in docs:
        f["what"] = _sec_what(f["form"])
    return {"company": (docs[0]["company"] if docs else "") or c.get("name", ""), "documents": docs[:limit]}


SEC_DOC_URL = re.compile(r"^https://www\.sec\.gov/Archives/edgar/data/(\d+)/(\d{18})/[\w.-]+$")


def sec_release(url: str) -> str:
    """An 8-K's results release is its exhibit 99.1, listed in the filing index next to the cover document."""
    m = SEC_DOC_URL.match(url)
    if not m:
        return url
    cik, acc = m.group(1), m.group(2)
    index = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{acc[:10]}-{acc[10:12]}-{acc[12:]}-index.htm"
    root = lxml_html.fromstring(fetch(index, ttl=None))
    rows = []
    for tr in root.iter("tr"):
        cells = [c for c in tr if isinstance(c.tag, str) and c.tag in ("td", "th")]
        link = tr.find(".//a[@href]")
        if len(cells) >= 4 and link is not None:
            rows.append(("".join(cells[3].itertext()).strip().upper(), link.get("href").replace("/ix?doc=", "")))
    best = next((h for typ, h in rows if typ == "EX-99.1"), None) or next((h for typ, h in rows if typ.startswith("EX-99")), None)
    if not best or not best.lower().endswith((".htm", ".html", ".pdf", ".txt")):
        raise SourceError(ui("Questo 8-K non contiene un comunicato sui risultati (allegato 99).", "This 8-K has no results release (exhibit 99)."))
    return best if best.startswith("http") else "https://www.sec.gov" + best


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


def esef_documents(query: str) -> dict:
    """Every report filings.xbrl.org has for the issuer (one per period and language), newest first."""
    ents = esef_entities(query)
    if not ents:
        raise SourceError(ui(f"Nessun emittente ESEF trovato per «{query}» su filings.xbrl.org.", f"No ESEF issuer found for \"{query}\" on filings.xbrl.org."))
    ent = ents[0]
    seen, docs = set(), []
    for f in esef_filings(ent["lei"]):
        key = (f["period"], f["lang"])
        if key in seen:
            continue
        seen.add(key)
        year = f["period"][:4]
        f.update(company=ent["name"], what=ui(f"Relazione finanziaria annuale {year}", f"Annual financial report {year}"))
        docs.append(f)
    return {"company": ent["name"], "documents": docs}


ESEF_DOC_URL = re.compile(r"^https://filings\.xbrl\.org/[\w./%-]+$")


def esef_latest(query: str) -> dict:
    ents = esef_entities(query)
    if not ents:
        raise SourceError(ui(f"Nessun emittente ESEF trovato per «{query}» su filings.xbrl.org.", f"No ESEF issuer found for \"{query}\" on filings.xbrl.org."))
    ent = ents[0]
    fil = esef_filings(ent["lei"])
    if not fil:
        raise SourceError(ui(f"Nessuna relazione ESEF pubblicata per {ent['name']}.", f"No ESEF report published for {ent['name']}."))
    best = fil[0]
    best["company"] = ent["name"]
    return best


# ---------------------------------------------------------------- Yahoo Finance

QUOTE_TYPES = {
    "EQUITY": "Azione", "ETF": "ETF", "MUTUALFUND": "Fondo", "INDEX": "Indice", "CURRENCY": "Valuta",
    "CRYPTOCURRENCY": "Crypto", "FUTURE": "Future", "OPTION": "Opzione", "MONEYMARKET": "Monetario",
}
QUOTE_TYPES_EN = {
    "EQUITY": "Stock", "ETF": "ETF", "MUTUALFUND": "Fund", "INDEX": "Index", "CURRENCY": "Currency",
    "CRYPTOCURRENCY": "Crypto", "FUTURE": "Future", "OPTION": "Option", "MONEYMARKET": "Money market",
}


YQ_HOSTS = ("https://query2.finance.yahoo.com", "https://query1.finance.yahoo.com")
_crumb: Optional[str] = None
_crumb_lock = threading.Lock()
# common names, used when Yahoo's own search is unavailable
ALIASES = {
    "bitcoin": "BTC-USD", "btc": "BTC-USD", "ethereum": "ETH-USD", "eth": "ETH-USD", "solana": "SOL-USD", "xrp": "XRP-USD",
    "oro": "GC=F", "gold": "GC=F", "argento": "SI=F", "silver": "SI=F", "petrolio": "CL=F", "oil": "CL=F", "brent": "BZ=F",
    "s&p 500": "^GSPC", "s&p500": "^GSPC", "sp500": "^GSPC", "nasdaq": "^IXIC", "nasdaq 100": "^NDX", "dow jones": "^DJI",
    "ftse mib": "FTSEMIB.MI", "dax": "^GDAXI", "euro stoxx 50": "^STOXX50E", "nikkei": "^N225",
    "euro dollaro": "EURUSD=X", "eurusd": "EURUSD=X", "eur/usd": "EURUSD=X", "sterlina": "GBPEUR=X", "yen": "JPY=X",
}


_yahoo: Optional[object] = None


def yahoo_client():
    """Yahoo blocks clients whose TLS handshake is not a browser's (HTTP 429): curl_cffi impersonates Chrome.
    Falls back to the plain httpx client if curl_cffi is not installed."""
    global _yahoo
    if _yahoo is None:
        try:
            from curl_cffi import requests as cffi
            _yahoo = cffi.Session(impersonate="chrome", timeout=30)
        except ImportError:
            _yahoo = client()
    return _yahoo


def _yahoo_get(url: str, headers: dict):
    try:
        return yahoo_client().get(url, headers=headers)
    except Exception as e:                    # httpx or curl_cffi network errors
        raise ConnectionError(str(e)) from e


def _yahoo_headers(accept: str) -> dict:
    h = {"Accept": accept, "Accept-Language": "en-US,en;q=0.9", "Referer": "https://finance.yahoo.com/"}
    if yahoo_client() is client():           # curl_cffi sends Chrome's own User-Agent
        h["User-Agent"] = BROWSER_UA
    return h


def _yahoo_crumb(host: str) -> Optional[str]:
    """Yahoo may also want its consent cookie and a crumb: get them once."""
    global _crumb
    with _crumb_lock:
        if _crumb:
            return _crumb
        h = _yahoo_headers("text/html,application/json;q=0.9,*/*;q=0.8")
        try:
            _yahoo_get("https://fc.yahoo.com", h)          # sets the A3 cookie (the page itself is a 404)
        except ConnectionError:
            pass
        try:
            r = _yahoo_get(f"{host}/v1/test/getcrumb", h)
            if r.status_code == 200 and r.text and "<" not in r.text and len(r.text) < 40:
                _crumb = r.text.strip()
        except ConnectionError:
            pass
        return _crumb


def yahoo_json(path: str, params: dict, ttl: float):
    """GET a Yahoo Finance JSON endpoint with cache, both hosts, cookie+crumb and a short backoff."""
    key = "yahoo:" + path + "?" + urlencode(sorted(params.items()))
    p = _cache_path(key)
    if p.exists() and time.time() - p.stat().st_mtime < ttl:
        return json.loads(p.read_bytes())
    h = _yahoo_headers("application/json,text/plain,*/*")
    last = None
    for attempt in range(4):
        host = YQ_HOSTS[attempt % 2]
        q = dict(params)
        if _crumb:
            q["crumb"] = _crumb
        try:
            r = _yahoo_get(f"{host}{path}?" + urlencode(q), h)
        except ConnectionError as e:
            last = str(e)[:80]
            continue
        if r.status_code == 200:
            data = json.loads(r.content)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(r.content)
            return data
        if r.status_code == 404:
            try:
                return json.loads(r.content)
            except ValueError:
                return {}
        last = str(r.status_code)
        if r.status_code in (401, 403, 429) and not _crumb:
            _yahoo_crumb(host)
        time.sleep(0.6 * (attempt + 1))
    if p.exists():                                    # stale cache beats an error
        return json.loads(p.read_bytes())
    if last == "429":
        raise SourceError(ui("Yahoo Finance sta limitando le richieste (429). Riprova tra qualche minuto.",
                             "Yahoo Finance is rate-limiting requests (429). Try again in a few minutes."))
    raise SourceError(ui(f"Yahoo Finance non risponde ({last}).", f"Yahoo Finance is not responding ({last})."))


# ---------------------------------------------------------------- Coinbase (crypto fallback, public, no key)

CRYPTO = re.compile(r"^([A-Z0-9]{2,10})-(USD|EUR|GBP|USDT|USDC|BTC)$")


def coinbase_history(symbol: str, years: int = 10) -> dict:
    sym = symbol.upper()
    if not CRYPTO.match(sym):
        raise SourceError(f"{symbol}: not a crypto pair")
    from datetime import datetime, timedelta, timezone
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows: dict[str, float] = {}
    for _ in range(int(years * 365 / 300) + 1):          # 300 daily candles per request
        start = end - timedelta(days=300)
        url = (f"https://api.exchange.coinbase.com/products/{sym}/candles?granularity=86400"
               f"&start={start.strftime('%Y-%m-%dT%H:%M:%SZ')}&end={end.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        try:
            batch = json.loads(fetch(url, ttl=6 * 3600))
        except (SourceError, ValueError):
            break
        if not isinstance(batch, list) or not batch:
            break
        for c in batch:                                   # [time, low, high, open, close, volume]
            rows[datetime.fromtimestamp(c[0], tz=timezone.utc).date().isoformat()] = float(c[4])
        end = start
    if len(rows) < 20:
        raise SourceError(ui(f"Nessuno storico prezzi per {symbol}.", f"No price history for {symbol}."))
    base, quote_cur = sym.split("-")
    return {"symbol": sym, "name": base, "currency": quote_cur, "type": "CRYPTOCURRENCY", "exchange": "Coinbase",
            "points": sorted(rows.items()), "source": "Coinbase"}


def price_history(symbol: str) -> dict:
    """Daily prices: Yahoo Finance, or Coinbase for crypto pairs when Yahoo is unavailable."""
    try:
        h = yahoo_history(symbol)
        h.setdefault("source", "Yahoo Finance")
        return h
    except SourceError as e:
        if CRYPTO.match(symbol.strip().upper()):
            try:
                return coinbase_history(symbol.strip())
            except SourceError:
                pass
        raise e


def looks_like_symbol(q: str) -> bool:
    q = q.strip()
    return bool(re.fullmatch(r"\^?[A-Za-z0-9.]{1,12}([-=][A-Za-z]{1,5})?", q)) and (q.isupper() or any(c in q for c in "^=-."))


def fallback_symbols(query: str) -> list[dict]:
    q = query.strip()
    out = []
    sym = ALIASES.get(q.lower())
    if sym:
        out.append({"symbol": sym, "name": q.title(), "type": "", "type_label": ui("Scheda di mercato", "Market sheet"), "exchange": ""})
    if looks_like_symbol(q) and q.upper() != sym:
        out.append({"symbol": q.upper(), "name": q.upper(), "type": "", "type_label": ui("Scheda di mercato", "Market sheet"), "exchange": ""})
    return out


def yahoo_search(query: str, limit: int = 10) -> list[dict]:
    q = query.strip()
    if not q:
        return []
    data = yahoo_json("/v1/finance/search", {"q": q, "quotesCount": limit, "newsCount": 0, "listsCount": 0}, ttl=DAY)
    out = []
    for r in data.get("quotes", []):
        sym = r.get("symbol")
        if not sym:
            continue
        out.append({
            "symbol": sym,
            "name": r.get("longname") or r.get("shortname") or sym,
            "type": r.get("quoteType", ""),
            "type_label": (QUOTE_TYPES if system_lang() == "it" else QUOTE_TYPES_EN).get(r.get("quoteType", ""), r.get("typeDisp") or r.get("quoteType", "")),
            "exchange": r.get("exchDisp") or r.get("exchange", ""),
        })
    return out


def yahoo_history(symbol: str, years: int = 10) -> dict:
    rng = "max" if years > 10 else f"{years}y"
    data = yahoo_json(f"/v8/finance/chart/{quote(symbol, safe='')}",
                      {"range": rng, "interval": "1d", "includeAdjustedClose": "true", "events": "div,splits"}, ttl=6 * 3600)
    res = (data.get("chart") or {}).get("result") or []
    if not res:
        err = (data.get("chart") or {}).get("error") or {}
        raise SourceError(ui(f"Nessuno storico prezzi per {symbol}: {err.get('description', 'simbolo sconosciuto')}",
                              f"No price history for {symbol}: {err.get('description', 'unknown symbol')}"))
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
        raise SourceError(ui(f"Storico prezzi troppo corto per {symbol}.", f"Price history too short for {symbol}."))
    meta = r.get("meta", {})
    return {
        "symbol": meta.get("symbol", symbol),
        "name": meta.get("longName") or meta.get("shortName") or symbol,
        "currency": meta.get("currency", ""),
        "type": meta.get("instrumentType", ""),
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName", ""),
        "points": points,
    }
