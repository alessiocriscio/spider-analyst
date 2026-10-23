"""Untagged financial statements (PDF / HTML, English or Italian): row labels -> metrics.

The same row of a statement holds the current and the prior year, so figures are
grouped by (page, row label); the column order comes from the years in the page
header, the scale from "(in millions)" / "(in migliaia di euro)" and the like.
The result has the shape financials.extract() produces for XBRL facts, so ratios,
checks, findings and the summary card are computed by the same code.
"""
from __future__ import annotations

import re
from typing import Optional

# metric -> label patterns (whole row label, case-insensitive). First match on the best page wins.
PATTERNS: dict[str, list[str]] = {
    "revenue": [r"(total )?(net )?(revenues?|sales|turnover)( and other income)?", r"total net sales",
                r"(totale )?ricavi( netti)?( delle vendite)?( e delle prestazioni)?", r"fatturato( netto)?", r"net revenues?"],
    "cost_of_revenue": [r"(total )?cost of (sales|revenues?|goods sold)", r"cost of products sold", r"costo del venduto", r"costi? delle vendite"],
    "gross_profit": [r"gross (profit|margin)", r"(margine|utile) lordo"],
    "rnd": [r"research and development( expenses?| costs?)?", r"(costi|spese) (di|per) ricerca e sviluppo"],
    "operating_income": [r"operating (income|profit)( \(loss\))?", r"income from operations", r"(ebit|operating result)",
                         r"risultato operativo", r"utile operativo", r"reddito operativo"],
    "pretax_income": [r"(income|profit|earnings) before (income )?tax(es)?", r"(utile|risultato) (prima|ante) (delle )?imposte"],
    "income_tax": [r"(provision for )?income tax(es| expense)?( expense)?", r"income tax (expense|provision)", r"imposte( sul reddito)?( dell'esercizio)?"],
    "net_income": [r"net (income|profit|earnings)( attributable to (shareholders|owners|equity holders|stockholders).*)?",
                   r"profit for the (year|period)( attributable to owners.*)?", r"(utile|risultato) netto( dell'esercizio| di gruppo| attribuibile.*)?",
                   r"utile dell'esercizio"],
    "eps_diluted": [r"diluted (earnings|net income|eps)( \(loss\))?( per (common |ordinary )?share)?( \(.*\))?", r"earnings per share[ -–—]+diluted",
                    r"diluted", r"utile (netto )?(diluito )?per azione( diluito)?( \(.*\))?"],
    "interest_expense": [r"interest expense", r"finance costs?", r"oneri finanziari"],
    "cash": [r"cash and cash equivalents", r"cash and equivalents", r"disponibilit[aà] liquide( e mezzi equivalenti)?"],
    "current_assets": [r"total current assets", r"(totale )?attivit[aà] correnti", r"totale attivo corrente"],
    "total_assets": [r"total assets", r"totale (attivo|attivit[aà])"],
    "current_liabilities": [r"total current liabilities", r"(totale )?passivit[aà] correnti"],
    "total_liabilities": [r"total liabilities", r"totale passivit[aà]"],
    "equity": [r"total (stockholders|shareholders|share-holders)['’]? equity", r"total equity", r"(totale )?patrimonio netto( totale)?"],
    "cfo": [r"net cash (provided by|from|generated (by|from)|used in|provided by \(used in\)) operating activities",
            r"cash (flows? )?(generated )?from operating activities", r"cash generated from operations",
            r"flusso di cassa (netto )?(generato )?(da|dalle|dell'|delle) attivit[aà] operativ[ae]", r"flussi di cassa (netti )?(da|dalle) attivit[aà] operative"],
    "capex": [r"(purchases?|acquisitions?|additions?|payments?) (of|to|for) property,? plant,? and equipment",
              r"capital expenditures?", r"investimenti in immobilizzazioni materiali", r"acquisti? di immobili,? impianti e macchinari"],
    "buybacks": [r"(repurchases?|purchases?) of (common |ordinary |treasury )?(stock|shares)", r"acquisto (di )?azioni proprie"],
    "dividends": [r"(cash )?dividends paid( to .*)?", r"dividendi (pagati|distribuiti)"],
}
_COMPILED = {k: [re.compile(rf"^{p}$", re.I) for p in v] for k, v in PATTERNS.items()}
PER_SHARE = {"eps_diluted"}

SCALES = [
    (r"in (u\.s\. )?(\$ )?billions|in miliardi", 1e9),
    (r"in (u\.s\. )?(\$ )?millions|\$ ?in millions|in milioni|milioni di euro|€ ?million|eur(o)? millions?|in millions of", 1e6),
    (r"in thousands|in migliaia|migliaia di euro|€ ?thousands?|eur(o)? thousands?|in thousands of", 1e3),
]


def _clean(label: str) -> str:
    s = label.lower().replace("’", "'").strip(" :.,;")
    s = re.sub(r"\s*\((note|nota) ?\d+\)|\s+\d{1,2}$", "", s)        # note references
    s = re.sub(r"[\$€£]", "", s)
    return re.sub(r"\s+", " ", s).strip(" :.,;")


def match(label: str) -> Optional[str]:
    s = _clean(label)
    if not s:
        return None
    for key, pats in _COMPILED.items():
        if any(p.match(s) for p in pats):
            return key
    return None


def page_scale(text: str) -> float:
    t = text.lower()
    for pat, k in SCALES:
        if re.search(pat, t):
            return k
    return 1.0


def page_currency(text: str) -> str:
    counts = {"USD": len(re.findall(r"\$|\bUSD\b|u\.s\. dollars", text, re.I)),
              "EUR": len(re.findall(r"€|\bEUR\b|\beuros?\b", text, re.I)),
              "GBP": len(re.findall(r"£|\bGBP\b", text))}
    cur, n = max(counts.items(), key=lambda x: x[1])
    return cur if n else ""


def column_years(text: str) -> Optional[tuple[int, int]]:
    m = re.search(r"(?<!\d)((?:19|20)\d\d)\D{0,40}?((?:19|20)\d\d)(?!\d)", text)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return (a, b) if abs(a - b) == 1 else None


def _is_note_ref(f: dict) -> bool:
    return bool(re.fullmatch(r"\d{1,2}", f["display"].strip()))


def extract(facts: list[dict], page_text: dict[int, str]) -> dict:
    """facts: [{id, label, value, display, page}] -> {"metrics", "currency", "years"} like financials.extract()."""
    groups: dict[tuple[int, str], list[dict]] = {}
    for f in facts:
        groups.setdefault((f["page"], f["label"]), []).append(f)
    found: dict[str, list] = {}
    for (page, label), fs in groups.items():
        key = match(label)
        if not key:
            continue
        nums = [f for f in fs if not _is_note_ref(f)] if len(fs) > 2 else fs
        nums.sort(key=lambda f: f["id"])
        if not nums:
            continue
        found.setdefault(key, []).append((page, nums))
    # statements are the pages where most metrics were recognised
    page_hits: dict[int, int] = {}
    for key, cands in found.items():
        for page, _ in cands:
            page_hits[page] = page_hits.get(page, 0) + 1

    metrics, years = {}, None
    for key, cands in found.items():
        page, nums = max(cands, key=lambda c: (page_hits[c[0]], len(c[1]) >= 2, -c[0]))
        text = page_text.get(page, "")
        yrs = column_years(text)
        order = nums if not yrs or yrs[0] > yrs[1] else list(reversed(nums[:2]))
        scale = 1.0 if key in PER_SHARE else page_scale(text)
        cur_f = order[0]
        prev_f = order[1] if len(order) > 1 else None

        def fd(f):
            v = abs(f["value"]) if key in ("capex", "buybacks", "dividends", "cost_of_revenue", "rnd", "interest_expense", "income_tax") else f["value"]
            return {"id": f["id"], "value": v * scale, "display": f["display"], "page": f["page"], "concept": "", "unit": ""}

        metrics[key] = {"key": key, "kind": "ps" if key in PER_SHARE else "flow", "cur": fd(cur_f), "prev": fd(prev_f) if prev_f else None}
        if yrs and years is None:
            years = (max(yrs), min(yrs))
    cur = next((page_currency(page_text.get(m["cur"]["page"], "")) for m in metrics.values()), "")
    return {"metrics": metrics, "currency": cur, "years": years}
