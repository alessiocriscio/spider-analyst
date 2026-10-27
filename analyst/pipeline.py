"""Any source -> one "analysis" the web app plays back.

analysis = {
  id, kind ("ixbrl" | "market" | "pdf" | "html"), title, subtitle, source,
  pages:  [{n, title}]                      pages shown to the spider, in reading order
  cols:   {n: ["2025", "2024"]}             column headers of the live report table
  rows:   {n: [{label, cells: [fid|None]}]} live report table per page
  facts:  {fid: {label, display, value_fmt, page, key, metric}}
  total_facts, findings, card, checks, warnings, ai,
  reading: {doc_type, summary, sections: [{title, points: [{text, pages}]}], pages_read}   (AI reading)
}
The pages themselves are served as one sanitised HTML document (view.html).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable, Optional

from . import ai, financials as F, generic, ixbrl, market, reader, sources, statements
from .i18n import system_lang, t, ui, using

DOCS = sources.CACHE / "docs"
Progress = Callable[[str, float], None]

BASE_CSS = """
html,body{margin:0;background:#ececf1}
#sa-doc{padding:40px 0 120px}
.sa-page{position:relative;background:#fff;margin:0 auto 48px;width:max-content;min-width:820px;max-width:1300px;
  box-shadow:0 2px 18px rgba(0,0,0,.12);border-radius:2px}
.sa-page>.sa-pbody{padding:44px 54px;color:#111;font-family:Georgia,'Times New Roman',serif}
.sa-page.flush>.sa-pbody{padding:0}
.sa-pnum{position:absolute;top:-26px;left:0;font:500 13px system-ui,sans-serif;color:#8a8a99}
.sa-pbody img{max-width:100%}
.sa-pbody table{border-collapse:collapse}
.sheet{width:860px;font-family:system-ui,-apple-system,sans-serif}
"""


def _id(*parts) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16]


def _humanize(concept: str) -> str:
    s = concept.split(":")[-1]
    s = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    return s[:1].upper() + s[1:].lower()


def view_html(pages: list[dict], css: str, flush: bool = False) -> str:
    body = "".join(
        f'<section class="sa-page{" flush" if flush else ""}" data-page="{p["n"]}"><div class="sa-pnum">{t("Pagina", "Page")} {p["n"]}</div>'
        f'<div class="sa-pbody">{p["html"]}</div></section>' for p in pages)
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{BASE_CSS}\n{css}</style></head>'
            f'<body><main id="sa-doc">{body}</main></body></html>')


def save(a: dict, view: str) -> dict:
    d = DOCS / a["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "analysis.json").write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
    (d / "view.html").write_text(view, encoding="utf-8")
    return a


def load(aid: str) -> Optional[dict]:
    if not re.fullmatch(r"[0-9a-f]{16}", aid or ""):
        return None
    p = DOCS / aid / "analysis.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ---------------------------------------------------------------- iXBRL filings

def _fact_fmt(f: ixbrl.Fact, units: dict) -> str:
    u = units.get(f.unit or "", f.unit or "")
    if f.value is None:
        return f.display
    if "/" in u:
        return F._ps(f.value, u.split("/")[0])
    if u.lower() == "shares":
        return F.fmt_money(f.value, "").strip()
    if u.lower() == "pure":
        return F.fmt_pct(f.value)
    if re.fullmatch(r"[A-Z]{3}", u):
        return F.fmt_money(f.value, u)
    return F.fmt_num(f.value)


def from_ixbrl(data: bytes, url: str, meta: dict, use_ai: bool, progress: Progress) -> dict:
    progress(ui("Lettura del documento iXBRL", "Reading the inline XBRL document"), 0.35)
    doc = ixbrl.parse(data, url)
    progress(ui("Estrazione delle cifre", "Extracting the figures"), 0.55)
    x = F.extract(doc)
    m, cur, per = x["metrics"], x["currency"], x["periods"]
    if not m:
        raise sources.SourceError(ui("Nessuna cifra di bilancio riconosciuta nei tag XBRL di questo documento.",
                                     "No financial figures recognised in this document's XBRL tags."))
    d = F.derive(m)
    checks = F.checks(m)
    finds = F.findings(m, d, cur)
    card = F.card(m, d, cur)

    # pages: cover + the pages holding the headline figures (financial statements first)
    metric_ids = {mm["cur"]["id"]: k for k, mm in m.items()}
    metric_ids.update({mm["prev"]["id"]: k for k, mm in m.items() if mm.get("prev")})
    weight: dict[int, float] = {}
    for k, mm in m.items():
        p = mm["cur"]["page"]
        weight[p] = weight.get(p, 0) + (3 if k in ("revenue", "net_income", "eps_diluted", "cfo", "capex", "total_assets") else 1)
    cover = next((i + 1 for i, t in enumerate(doc.page_text) if len(t) > 150), None) or next((i + 1 for i, t in enumerate(doc.page_text) if t), 1)
    best = sorted(weight, key=lambda p: -weight[p])[:6]
    shown = sorted({cover, *best})

    facts, rows, cols = {}, {}, {}
    y_cur = str(per.end.year) if per.end else t("Corrente", "Current")
    y_prev = str(per.end.year - 1) if per.end else t("Precedente", "Prior")
    for p in shown:
        cols[p] = [y_cur, y_prev]
        table: dict[str, list] = {}
        order: list[str] = []
        on_page = [f for f in doc.facts if f.page == p and f.value is not None and f.context in doc.contexts]
        on_page.sort(key=lambda f: (f.id not in metric_ids, doc.contexts[f.context].dimensional, f.id))
        for f in on_page:
            role = per.role(f)
            key = metric_ids.get(f.id)
            label = F.label(key) if key else (f.row_label or _humanize(f.concept))
            facts[f.id] = {"label": label, "display": f.display, "value_fmt": _fact_fmt(f, doc.units), "page": p,
                           "key": bool(key), "metric": key, "role": role}
            if role and not doc.contexts[f.context].dimensional:
                rk = f.row_label or label
                if rk not in table:
                    table[rk] = [None, None]
                    order.append(rk)
                slot = 0 if role == "cur" else 1
                if table[rk][slot] is None:
                    table[rk][slot] = f.id
        rows[p] = [{"label": k, "cells": table[k]} for k in order]

    company = doc.info.get("EntityRegistrantName") or doc.info.get("NameOfReportingEntityOrOtherMeansOfIdentification") or meta.get("company", "")
    form = doc.info.get("DocumentType") or meta.get("form", "")
    mn = market.months()
    period = (t(f"{per.end.day} {mn[per.end.month - 1]} {per.end.year}", f"{mn[per.end.month - 1]} {per.end.day}, {per.end.year}")
              if per.end else doc.info.get("DocumentPeriodEndDate", ""))
    reading = None
    if use_ai and ai.available():
        progress(_reading_step(), 0.65)
        texts = doc.page_text
        try:
            reading = reader.read(f"{company} {form} {period}", {i + 1: texts[i] for i in reader.choose_pages(texts)},
                                  len(texts), known=_ai_data(m, d, cur))
        except Exception as e:  # network/API errors: keep the deterministic findings
            meta.setdefault("warnings", []).append(_ai_warning(e))
        if reading and len(reading["findings"]) >= 3:
            finds = reading["findings"]
    ai_used = bool(reading)

    used = set()
    for p in shown:
        used.update(c for cl in re.findall(r'class="([^"]+)"', doc.pages[p - 1]) for c in cl.split())
    view = view_html([{"n": p, "html": doc.pages[p - 1]} for p in shown], ixbrl.filter_css(doc.css, used),
                     flush=_is_paged_layout(doc.pages[shown[-1] - 1]))
    a = {
        "id": meta["id"], "kind": "ixbrl",
        "title": company or t("Documento", "Document"),
        "subtitle": " · ".join(x for x in (form, t(f"periodo chiuso il {period}", f"period ended {period}") if period else "", meta.get("source_label", "")) if x),
        "source": meta.get("url", url),
        "currency": cur,
        "pages": [{"n": p, "title": next((h["text"] for h in doc.headings if h["page"] == p), t(f"Pagina {p}", f"Page {p}"))} for p in shown],
        "total_pages": len(doc.pages),
        "cols": cols, "rows": rows, "facts": facts, "total_facts": len(doc.facts),
        "headings": [h for h in doc.headings if h["page"] in shown],
        "findings": finds[:6], "card": card, "card_findings": finds[:3], "checks": checks,
        "warnings": doc.warnings + meta.get("warnings", []), "ai": ai_used, "ai_provider": ai.provider_name() if ai_used else "",
        "fin": _fin_data(m, d, cur, [y_cur, y_prev]), "reading": _public(reading),
    }
    return save(a, view)


def _reading_step() -> str:
    return ui(f"{ai.provider_name()} legge il documento (può richiedere un minuto)",
              f"{ai.provider_name()} is reading the document (this can take a minute)")


def _ai_warning(e: Exception) -> str:
    return t("AI non disponibile: ", "AI unavailable: ") + (str(e)[:240] if isinstance(e, ai.AIError) else type(e).__name__)


def _public(reading: Optional[dict]) -> Optional[dict]:
    if not reading:
        return None
    return {k: reading[k] for k in ("doc_type", "summary", "sections", "pages_read")}


def _fin_data(m: dict, d: dict, cur: str, years: list) -> dict:
    """Raw numbers behind the report charts (values as read, ratios derived from them)."""
    return {
        "currency": cur, "years": years,
        "metrics": {k: {"label": F.label(k), "cur": mm["cur"]["value"], "prev": mm["prev"]["value"] if mm.get("prev") else None,
                        "page": mm["cur"]["page"], "kind": F.METRICS[k][2]} for k, mm in m.items()},
        "derived": {"cur": d["cur"], "prev": d["prev"], "growth": d["growth"]},
    }


def _is_paged_layout(page_html: str) -> bool:
    return "pageView" in page_html[:400] or "position:absolute" in page_html[:2000].replace(" ", "")


def _ai_data(m: dict, d: dict, cur: str) -> dict:
    data = {}
    for k, mm in m.items():
        it = F.METRICS[k][1]
        for which, tag in (("cur", "current year"), ("prev", "prior year")):
            if mm.get(which):
                data[f"{k}_{which}"] = {"label": f"{it} ({tag})", "display": F.fmt_value(k, mm[which]["value"], cur), "pages": [mm[which]["page"]]}
    ratios = {"fcf": ("Free cash flow", F.fmt_money), "gross_margin": ("Gross margin %", F.fmt_pct), "operating_margin": ("Operating margin %", F.fmt_pct),
              "net_margin": ("Net margin %", F.fmt_pct), "interest_coverage": ("Interest coverage (times)", lambda v: F.fmt_num(v, 1)),
              "current_ratio": ("Current ratio", lambda v: F.fmt_num(v, 2)), "return_pct_fcf": ("Share of FCF returned to shareholders", F.fmt_pct),
              "debt_to_assets": ("Debt / assets", F.fmt_pct), "equity_multiplier": ("Assets / equity", lambda v: F.fmt_num(v, 1))}
    pages_of = {"fcf": ("cfo", "capex"), "gross_margin": ("revenue",), "operating_margin": ("operating_income",), "net_margin": ("net_income",),
                "interest_coverage": ("interest_expense",), "current_ratio": ("current_assets",), "return_pct_fcf": ("buybacks", "dividends"),
                "debt_to_assets": ("total_assets",), "equity_multiplier": ("total_assets", "equity")}
    for k, (label, fmt) in ratios.items():
        for which, tag in (("cur", "current year"), ("prev", "prior year")):
            v = d[which].get(k)
            if v is None:
                continue
            disp = fmt(v, cur) if fmt is F.fmt_money else fmt(v)
            data[f"{k}_{which}"] = {"label": f"{label} ({tag})", "display": disp, "pages": F._pages(m, *pages_of[k], which=which)}
    for k, v in d["growth"].items():
        if v is not None:
            pk = ("cfo", "capex") if k == "fcf" else (k,)
            data[f"growth_{k}"] = {"label": f"Year-on-year change, {F.METRICS.get(k, ('', 'Free cash flow'))[1]}", "display": F.fmt_pct(v, signed=True), "pages": F._pages(m, *pk)}
    return data


# ---------------------------------------------------------------- market sheet

def from_market(symbol: str, meta: dict, progress: Progress, use_ai: bool = False) -> dict:
    progress(ui("Scarico lo storico prezzi", "Downloading the price history"), 0.3)
    hist = sources.price_history(symbol)
    progress(ui("Calcolo rendimenti e rischio", "Computing returns and risk"), 0.6)
    r = market.build(hist)
    n = len(r["pages"])
    titles = {h["page"]: h["text"] for h in reversed(r["headings"])}
    facts, rows, cols = {}, {}, {}
    for f in r["facts"]:
        facts[f["id"]] = {"label": f["label"], "display": f["display"], "value_fmt": f["display"], "page": f["page"],
                          "key": f["key"], "metric": None, "role": "cur"}
        rows.setdefault(f["page"], []).append({"label": f["label"].replace("Rendimento ", "") if f["page"] in (2, 3) else f["label"], "cells": [f["id"]]})
    for p in range(1, n + 1):
        cols[p] = [t("Valore", "Value")]
        rows.setdefault(p, [])
    view = view_html([{"n": i + 1, "html": f'<div class="sheet">{h}</div>'} for i, h in enumerate(r["pages"])], market.CSS)
    finds, ai_used, warns = r["findings"], False, []
    if use_ai and ai.available():
        progress(ui(f"{ai.provider_name()} commenta i dati", f"{ai.provider_name()} is commenting on the data"), 0.8)
        data = {str(f["id"]): {"label": f["label"], "display": f["display"], "pages": [f["page"]]} for f in r["facts"]}
        try:
            obs = ai.observations(f"{r['title']} — {r['subtitle']}", data)
        except Exception as e:
            obs = []
            warns.append(_ai_warning(e))
        if len(obs) >= 3:
            finds, ai_used = obs, True
    a = {
        "id": meta["id"], "kind": "market", "title": r["title"], "subtitle": r["subtitle"] + t(" · fonte ", " · source ") + hist.get("source", "Yahoo Finance"),
        "source": f"https://finance.yahoo.com/quote/{symbol}" if hist.get("source", "Yahoo Finance") == "Yahoo Finance" else f"https://exchange.coinbase.com/trade/{hist['symbol']}", "currency": r["currency"],
        "pages": [{"n": p, "title": titles.get(p, t(f"Pagina {p}", f"Page {p}"))} for p in range(1, n + 1)], "total_pages": n,
        "cols": cols, "rows": rows, "facts": facts, "total_facts": len(r["facts"]), "headings": r["headings"],
        "findings": finds[:6], "card": r["card"], "card_findings": finds[:3], "checks": r["checks"],
        "warnings": warns, "ai": ai_used, "ai_provider": ai.provider_name() if ai_used else "", "series": r["series"],
    }
    return save(a, view)


# ---------------------------------------------------------------- PDF / plain HTML

def from_generic(data: bytes, name: str, url: Optional[str], meta: dict, use_ai: bool, progress: Progress) -> dict:
    is_pdf = data[:5] == b"%PDF-"
    progress(ui("Lettura delle pagine", "Reading the pages"), 0.3)
    reading: dict = {}

    def choose(texts: list[str]) -> Optional[list[int]]:
        # the AI reads the document first; the spider then shows the pages holding what it found
        if not (use_ai and ai.available()):
            return None
        progress(_reading_step(), 0.4)
        try:
            res = reader.read(name, {i + 1: texts[i] for i in reader.choose_pages(texts)}, len(texts))
        except Exception as e:
            meta.setdefault("warnings", []).append(_ai_warning(e))
            return None
        if not res:
            meta.setdefault("warnings", []).append(t("L'AI non ha dato una risposta utilizzabile.", "The AI gave no usable answer."))
            return None
        reading.update(res)
        return _shown_pages(texts, res["figures"])

    if is_pdf:
        g = generic.pdf_document(data, DOCS / meta["id"] / "img", f"/api/doc/{meta['id']}/img", choose=choose)
    else:
        g = generic.html_document(data, url, choose=choose)
    progress(ui("Preparo il report", "Preparing the report"), 0.85)
    if not g["facts"] and not reading:
        raise sources.SourceError(ui("Non ho trovato cifre leggibili in questo documento (un PDF scansionato senza testo?).",
                                     "No readable figures in this document (a scanned PDF without text?)."))
    facts = {f["id"]: {"label": f["label"], "display": f["display"], "value_fmt": f["display"], "page": f["page"],
                       "key": f["key"], "metric": None, "role": "cur"} for f in g["facts"]}
    first_heading = next((h["text"] for h in g["headings"] if h["page"] == g["pages"][0]["n"]), "") if g["pages"] else ""
    title = reading.get("company") or (g.get("title") if (g.get("title") or "").lower() not in ("", "untitled") else
                                       ((g.get("info") or {}).get("EntityRegistrantName") or meta.get("company") or first_heading or name))
    ai_used = bool(reading)
    fact_of: dict[int, int] = {}
    if ai_used:
        fact_of = _match_figures(reading["figures"], g["facts"])
        for f in facts.values():
            f["key"] = False
        for i, fid in fact_of.items():
            facts[fid].update(label=reading["figures"][i]["label"], key=True)
    finds = reading.get("findings") or []
    kind_label = reading.get("doc_type") or (t("Bilancio", "Financial statements") if not ai_used else t("Documento", "Document"))
    pages_note = t(f"{g['total_pages']} pagine", f"{g['total_pages']} pages")
    how = t("letto da ", "read by ") + ai.provider_name() if ai_used else t("estrazione euristica", "heuristic extraction")
    common = {"id": meta["id"], "kind": "pdf" if is_pdf else "html", "title": title,
              "subtitle": " · ".join(x for x in (kind_label, pages_note, how) if x),
              "source": url or name, "total_pages": g["total_pages"], "total_facts": len(g["facts"]),
              "headings": g["headings"], "facts": facts,
              "pages": [{"n": p["n"], "title": next((h["text"] for h in g["headings"] if h["page"] == p["n"]), t(f"Pagina {p['n']}", f"Page {p['n']}"))} for p in g["pages"]],
              "warnings": meta.get("warnings", []) + ([] if ai_used or not use_ai or ai.available() else
                                                      [t("Nessuna AI configurata: cifre scelte con regole euristiche.", "No AI configured: figures chosen by heuristic rules.")]),
              "ai": ai_used, "ai_provider": ai.provider_name() if ai_used else "", "reading": _public(reading)}
    view = view_html(g["pages"], g["css"], flush=is_pdf)

    # statements: rows recognised by their labels, or the statement items the AI named
    x = _statement_metrics(g)
    if not x and ai_used:
        x = _ai_metrics(reading, fact_of)
    if x:
        stmt = _statement_view(g, facts, finds, x, ai_marked=ai_used)
        return save({**stmt, **common}, view)

    keyed = [next(f for f in g["facts"] if f["id"] == fact_of[i]) for i in sorted(fact_of)] if ai_used else \
        sorted((f for f in g["facts"] if facts[f["id"]]["key"]), key=lambda f: -f["score"])
    if not finds:
        finds = [{"text": f"{facts[f['id']]['label']}: {f['display']}.", "pages": [f["page"]]} for f in keyed[:6]]
    card = [{"key": str(f["id"]), "it": _short(facts[f["id"]]["label"]), "en": "", "display": f["display"], "yoy_display": "", "pages": [f["page"]]}
            for f in keyed[:4]]
    if not card and ai_used:          # figures read by the AI on pages that are not shown
        card = [{"key": f"f{i}", "it": _short(g2["label"]), "en": "", "display": g2["value"], "yoy_display": "", "pages": [g2["page"]]}
                for i, g2 in enumerate(reading["figures"][:4])]
    rows, cols = {}, {}
    for p in g["pages"]:
        cols[p["n"]] = [t("Valore", "Value")]
        rows[p["n"]] = [{"label": facts[f["id"]]["label"], "cells": [f["id"]]} for f in g["facts"] if f["page"] == p["n"] and facts[f["id"]]["key"]]
    a = {**common, "currency": reading.get("currency", ""), "cols": cols, "rows": rows,
         "findings": finds[:6], "card": card, "card_findings": finds[:3],
         "checks": [{"name": t("Ogni cifra mostrata compare nel testo della pagina", "Every figure shown appears in the page text"),
                     "ok": True, "pages": [], "detail": ""}]}
    return save(a, view)


def _shown_pages(texts: list[str], figures: list[dict]) -> list[int]:
    """The cover, the pages holding most of the figures the AI found, then the densest pages (0-based)."""
    count: dict[int, int] = {}
    for f in figures:
        if 1 <= f["page"] <= len(texts):
            count[f["page"] - 1] = count.get(f["page"] - 1, 0) + 1
    first = next((i for i, t in enumerate(texts) if t.strip()), 0)
    shown = [first] + [p for p in sorted(count, key=lambda p: (-count[p], p)) if p != first][:generic.MAX_PAGES_SHOWN - 1]
    for p in generic.best_pages(texts):
        if len(shown) >= generic.MAX_PAGES_SHOWN:
            break
        if p not in shown:
            shown.append(p)
    return sorted(shown)


def _match_figures(figures: list[dict], found: list[dict]) -> dict[int, int]:
    """AI figure index -> id of the figure on the same page showing the same number."""
    out, used = {}, set()
    for i, g in enumerate(figures):
        want = ai.numbers_in(g["value"])
        same = [f for f in found if f["page"] == g["page"] and f["id"] not in used and ai.numbers_in(f["display"]) == want]
        if same:
            f = max(same, key=lambda f: f["score"])
            out[i] = f["id"]
            used.add(f["id"])
    return out


def _statement_metrics(g: dict) -> Optional[dict]:
    texts = {p["n"]: t for p, t in zip(g["pages"], g["page_text"])}
    x = statements.extract(g["facts"], texts)
    if len(x["metrics"]) < 3 or not ({"revenue", "net_income"} & set(x["metrics"])):
        return None
    return x


def _ai_metrics(reading: dict, fact_of: dict[int, int]) -> Optional[dict]:
    m = reader.metrics_from(reading["figures"], fact_of)
    if len(m) < 3 or not ({"revenue", "net_income"} & set(m)):
        return None
    cur_p = next((g["period"] for g in reading["figures"] if g["role"] == "current" and g["period"]), "")
    prev_p = next((g["period"] for g in reading["figures"] if g["role"] == "prior" and g["period"]), "")
    return {"metrics": m, "currency": reading.get("currency", ""), "years": (cur_p, prev_p) if cur_p and prev_p else None}


def _statement_view(g: dict, facts: dict, ai_finds: list, x: dict, ai_marked: bool = False) -> dict:
    """Financial statements without XBRL tags: same card, checks and findings as iXBRL."""
    m, cur = x["metrics"], x["currency"]
    d = F.derive(m)
    y_cur, y_prev = (str(x["years"][0]), str(x["years"][1])) if x["years"] else (t("Anno corrente", "Current year"), t("Anno precedente", "Prior year"))
    rows: dict = {}
    for key, mm in m.items():
        for which in ("cur", "prev"):
            if mm.get(which):
                f = facts[mm[which]["id"]]
                f.update(label=F.label(key), key=True, metric=key, role=which,
                         value_fmt=F.fmt_value(key, mm[which]["value"], cur))
        p = mm["cur"]["page"]
        rows.setdefault(p, []).append({"label": F.label(key), "cells": [mm["cur"]["id"], mm["prev"]["id"] if mm.get("prev") else None]})
    # other figures the AI marked stay in the table of their page
    for fid, f in facts.items():
        if ai_marked and f["key"] and not f.get("metric"):
            rows.setdefault(f["page"], []).append({"label": f["label"], "cells": [fid, None]})
    finds = ai_finds or F.findings(m, d, cur)
    return {"currency": cur, "cols": {p["n"]: [y_cur, y_prev] for p in g["pages"]},
            "rows": {p["n"]: rows.get(p["n"], []) for p in g["pages"]},
            "findings": finds[:6], "card_findings": finds[:3], "card": F.card(m, d, cur), "checks": F.checks(m),
            "fin": _fin_data(m, d, cur, [y_cur, y_prev])}


def _short(label: str, n: int = 38) -> str:
    if len(label) <= n:
        return label
    return label[:n].rsplit(" ", 1)[0] + "…"


def is_ixbrl(data: bytes) -> bool:
    head = data[:400_000]
    return b"ix:nonFraction" in head or b"ix:nonfraction" in head or b"inlineXBRL" in head


# ---------------------------------------------------------------- entry points

def run(req: dict, progress: Progress) -> dict:
    """req: {"kind": "sec"|"esef"|"market"|"url"|"upload"|"upload_ref", "lang": "it"|"en", ...}"""
    lang = req.get("lang") if req.get("lang") in ("it", "en") else system_lang()
    if req["kind"] == "upload":
        # keep the file so the report can be rebuilt in the other language
        sha = hashlib.sha256(req["data"]).hexdigest()
        up = DOCS / "uploads" / f"{sha}.bin"
        if not up.exists():
            up.parent.mkdir(parents=True, exist_ok=True)
            up.write_bytes(req["data"])
        req = {**req, "kind": "upload_ref", "sha": sha}
        req.pop("data")
    if req["kind"] == "upload_ref":
        up = DOCS / "uploads" / f"{req.get('sha', '')}.bin"
        if not re.fullmatch(r"[0-9a-f]{64}", req.get("sha", "")) or not up.exists():
            raise sources.SourceError(ui("Il file caricato non è più disponibile: caricalo di nuovo.", "The uploaded file is no longer available: upload it again."))
        data = up.read_bytes()
    else:
        data = None
    ref = {k: v for k, v in req.items() if k in ("kind", "query", "symbol", "url", "form", "ai", "sha", "name")}
    with using(lang):
        a = _run(req, data, lang, progress)
    if a.get("lang") != lang or a.get("req") != ref:
        a["lang"], a["req"] = lang, ref
        (DOCS / a["id"] / "analysis.json").write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
    return a


def relang(aid: str, lang: str, progress: Progress) -> dict:
    a = load(aid)
    if not a or not a.get("req"):
        raise sources.SourceError(ui("Analisi non trovata: rifai la ricerca.", "Analysis not found: search again."))
    return run({**a["req"], "lang": lang}, progress)


def _run(req: dict, data: Optional[bytes], lang: str, progress: Progress) -> dict:
    use_ai = bool(req.get("ai"))
    kind = req["kind"]
    if kind == "sec":
        progress(ui("Cerco il bilancio su SEC EDGAR", "Looking for the filing on SEC EDGAR"), 0.08)
        f = sources.sec_latest(req["query"], req.get("form")) if not req.get("url") else {"url": req["url"], "form": req.get("form", "")}
        aid = _id("sec", f["url"], use_ai, lang)
        if (hit := load(aid)) and not req.get("refresh"):
            return hit
        progress(ui(f"Scarico il {f.get('form') or 'documento'} da sec.gov", f"Downloading the {f.get('form') or 'document'} from sec.gov"), 0.18)
        data = sources.fetch(f["url"], ttl=None)
        meta = {"id": aid, "url": f["url"], "form": f.get("form", ""), "company": f.get("company", ""), "source_label": "SEC EDGAR"}
        if is_ixbrl(data):
            return from_ixbrl(data, f["url"], meta, use_ai, progress)
        # registration statements (S-1, F-1, 424B prospectuses) are often not tagged
        return from_generic(data, f.get("company") or f["url"].rsplit("/", 1)[-1], f["url"], meta, use_ai, progress)
    if kind == "esef":
        progress(ui("Cerco la relazione ESEF su filings.xbrl.org", "Looking for the ESEF report on filings.xbrl.org"), 0.08)
        f = sources.esef_latest(req["query"]) if not req.get("url") else {"url": req["url"]}
        aid = _id("esef", f["url"], use_ai, lang)
        if (hit := load(aid)) and not req.get("refresh"):
            return hit
        progress(ui("Scarico la relazione annuale (può pesare decine di MB)", "Downloading the annual report (it can be tens of MB)"), 0.18)
        data = sources.fetch(f["url"], ttl=None)
        meta = {"id": aid, "url": f["url"], "form": "ESEF", "company": f.get("company", ""), "source_label": "ESEF · filings.xbrl.org"}
        return from_ixbrl(data, f["url"], meta, use_ai, progress)
    if kind == "market":
        sym = req["symbol"].strip()
        aid = _id("market", sym.upper(), _today(), use_ai, lang)
        if (hit := load(aid)) and not req.get("refresh"):
            return hit
        return from_market(sym, {"id": aid}, progress, use_ai)
    if kind == "url":
        url = req["url"].strip()
        if not re.match(r"^https?://", url):
            raise sources.SourceError(ui("Indirizzo non valido: deve iniziare con http:// o https://", "Invalid address: it must start with http:// or https://"))
        aid = _id("url", url, use_ai, lang)
        if (hit := load(aid)) and not req.get("refresh"):
            return hit
        progress(ui("Scarico il documento", "Downloading the document"), 0.15)
        data = sources.fetch(url, ttl=7 * sources.DAY)
        meta = {"id": aid, "url": url, "source_label": re.sub(r"^https?://([^/]+).*$", r"\1", url)}
        if is_ixbrl(data):
            return from_ixbrl(data, url, meta, use_ai, progress)
        return from_generic(data, url.rsplit("/", 1)[-1] or url, url, meta, use_ai, progress)
    if kind == "upload_ref":
        aid = _id("upload", req["sha"], use_ai, lang)
        if (hit := load(aid)) and not req.get("refresh"):
            return hit
        meta = {"id": aid, "url": req.get("name", ""), "source_label": t("file caricato", "uploaded file")}
        if is_ixbrl(data):
            return from_ixbrl(data, None, meta, use_ai, progress)
        return from_generic(data, req.get("name", "documento"), None, meta, use_ai, progress)
    raise sources.SourceError(ui(f"Tipo di richiesta sconosciuto: {kind}", f"Unknown request type: {kind}"))


def _today() -> str:
    from datetime import date
    return date.today().isoformat()
