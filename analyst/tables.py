"""HTML tables -> rows, columns and the period of each column.

Untagged filings (an S-1 prospectus, a plain-HTML annual report) print their
statements as <table>s whose header says what each column is: "Year Ended
December 31, 2025", "Six Months Ended June 30, 2026", "As of June 30, 2026",
"$ Change", "Pro Forma". Reading the header turns every number into
(row, period, value), which is what is needed to compare the right periods:
the latest one against the same period a year earlier.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from . import statements
from .generic import parse_loose

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS.update({"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6, "luglio": 7,
               "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12})
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
NUM_CELL = re.compile(r"^\(?-?\s*\d[\d,.]*\)?%?$")
DASHES = {"—", "–", "-", "−", "—%", "*"}
# statement items whose sign is presentation only (always an outflow / a cost)
ABS_KEYS = {"capex", "buybacks", "dividends", "cost_of_revenue", "rnd", "interest_expense", "opex_total"}


@dataclass
class Column:
    idx: int
    header: str
    months: Optional[int] = None          # length of a period column; None for a point in time
    end: Optional[date] = None
    instant: bool = False
    skip: bool = False                    # change, percentage, pro forma, as adjusted


@dataclass
class Cell:
    text: str
    value: Optional[float]
    el: object
    pct: bool = False


@dataclass
class Row:
    label: str
    cells: dict[int, Cell]


@dataclass
class Table:
    page: int
    columns: dict[int, Column]
    rows: list[Row]
    scale: float = 1.0
    shares_scaled: bool = False
    shares_scale: float = 0.0             # when the unit line gives shares their own scale
    percent: bool = False
    caption: str = ""
    keys: set = field(default_factory=set)


def _text(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext()).replace("\xa0", " ")).strip()


def _num(text: str) -> tuple[Optional[float], bool]:
    """Cell text -> (value, is percentage). Currency signs and spaces are ignored; a dash is nil (0)."""
    s = re.sub(r"[\$€£¥]|USD|EUR|\s", "", text)
    if s in DASHES:
        return 0.0, s.endswith("%")
    if not NUM_CELL.match(s) or not re.search(r"\d", s):
        return None, False
    v = parse_loose(s.rstrip("%"))
    return v, s.endswith("%")


def _rows(table) -> list[list[tuple[int, int, object]]]:
    """[(first column, span, td)] per row, with rowspans carried down."""
    out, carry = [], {}
    trs = [tr for tr in table.iter("tr") if next((a for a in tr.iterancestors("table")), None) is table]
    for r, tr in enumerate(trs):
        cells, col = [], 0
        for td in tr:
            if not isinstance(td.tag, str) or td.tag.lower() not in ("td", "th"):
                continue
            while carry.get((r, col)):
                col += 1
            try:
                span = max(1, min(50, int(td.get("colspan") or 1)))
                rs = max(1, min(50, int(td.get("rowspan") or 1)))
            except ValueError:
                span, rs = 1, 1
            cells.append((col, span, td))
            for k in range(1, rs):
                for c in range(col, col + span):
                    carry[(r + k, c)] = True
            col += span
        out.append(cells)
    return out


def _period(h: str) -> tuple[Optional[int], Optional[date], bool, bool]:
    """Column header -> (months, end date, instant, skip)."""
    lo = h.lower()
    if re.search(r"change|variance|increase|decrease|%|percent|pro forma|as adjusted|adjustments?", lo):
        return None, None, False, True
    years = re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", lo)
    if not years:
        return None, None, False, False
    y = int(years[-1])
    md = re.findall(rf"\b({MONTH_RE})\.?\s+(\d{{1,2}})\b", lo)
    mo = re.findall(rf"\b({MONTH_RE})\b", lo)
    month = MONTHS[md[-1][0]] if md else (MONTHS[mo[-1]] if mo else 12)
    q = re.search(r"\bq([1-4])\b|\b([1-4])q\b", lo)
    h = re.search(r"\bh([12])\b|\b([12])h\b", lo)
    if q and not md:                      # "Q2 2026": a calendar quarter
        n = int(q.group(1) or q.group(2))
        return 3, date(y, 3 * n, calendar.monthrange(y, 3 * n)[1]), False, False
    if h and not md:                      # "H1 2026": a calendar half
        n = int(h.group(1) or h.group(2))
        return 6, date(y, 6 * n, calendar.monthrange(y, 6 * n)[1]), False, False
    day = int(md[-1][1]) if md else calendar.monthrange(y, month)[1]
    try:
        end = date(y, month, min(day, calendar.monthrange(y, month)[1]))
    except ValueError:
        return None, None, False, False
    months = None
    if re.search(r"twelve months|12 months|years? ended|year ending|fiscal( year)?|\bfy\b|esercizio", lo):
        months = 12
    elif re.search(r"nine months|9 months|nove mesi", lo):
        months = 9
    elif re.search(r"six months|6 months|half[- ]year|first half|sei mesi|semestre", lo):
        months = 6
    elif re.search(r"three months|3 months|quarter|tre mesi|trimestre", lo):
        months = 3
    instant = months is None and bool(re.search(r"\bas of\b|\bas at\b|\bat\b|balance|al \d", lo) or md)
    if months is None and not instant:
        months = 12                      # a bare year column: a fiscal year
    return months, end, instant, False


def _caption(table) -> str:
    """Text just before the table (unit lines such as "(in millions)")."""
    bits, el = [], table
    for _ in range(6):
        prev = el.getprevious()
        while prev is None and el.getparent() is not None:
            el = el.getparent()
            prev = el.getprevious()
        if prev is None:
            break
        bits.insert(0, _text(prev))
        el = prev
        if sum(len(b) for b in bits) > 300:
            break
    return " ".join(bits)[-300:]


def parse_table(table, page: int) -> Optional[Table]:
    grid = _rows(table)
    texts = [[(c, s, td, _text(td)) for c, s, td in row] for row in grid]

    def label_of(row):
        for c, s, td, tx in row:
            if sum(ch.isalpha() for ch in tx) >= 3 and _num(tx)[0] is None:
                return c, tx
        return None, ""

    def years_only(row) -> bool:
        nums = [tx for c, s, td, tx in row if _num(tx)[0] is not None and tx.strip() not in DASHES]
        return bool(nums) and all(re.fullmatch(r"(19|20)\d\d", tx.strip()) for tx in nums)

    first_data = None
    for i, row in enumerate(texts):
        lc, lab = label_of(row)
        if years_only(row):              # "(in millions)  2023  2024  2025": the header line of the years
            continue
        if lab and any(c > lc and _num(tx)[0] is not None and tx.strip() not in DASHES for c, s, td, tx in row):
            first_data = i
            break
    if first_data is None:
        return None
    header = texts[:first_data]

    def head(col: int) -> str:
        parts = []
        for row in header:
            for c, s, td, tx in row:
                if c <= col < c + s and tx:
                    parts.append(tx)
        return " ".join(parts)

    columns: dict[int, Column] = {}
    rows: list[Row] = []
    for row in texts[first_data:]:
        lc, lab = label_of(row)
        if not lab:
            continue
        cells = {}
        for c, s, td, tx in row:
            if c <= lc or not tx:
                continue
            v, pct = _num(tx)
            if v is None:
                continue
            cells[c] = Cell(tx, v, td, pct)
            if c not in columns:
                h = head(c) or head(c - 1) or head(c + 1)
                months, end, instant, skip = _period(h)
                columns[c] = Column(c, h, months, end, instant, skip)
        rows.append(Row(_clean_label(lab), cells))
    if not rows or not columns:
        return None
    unit_text = (_caption(table) + " " + " ".join(tx for row in header for *_, tx in row)).lower()
    t = Table(page, columns, rows, statements.page_scale(unit_text), caption=unit_text[-200:])
    t.shares_scaled = "except share" not in unit_text and "except per share" not in unit_text and t.scale > 1 and "share" in unit_text
    if re.search(r"shares?( amounts?| data| counts?)?,?( which)? (are )?(reflected |presented |shown )?in thousands|thousands of shares|shares in thousands", unit_text):
        t.shares_scaled, t.shares_scale = True, 1e3
    head_text = " ".join(tx for row in header for *_, tx in row).lower()
    pct_hint = r"percentage of (total )?(net )?revenue|% of (total )?(net )?revenue|as a percentage|in percentuale"
    values = [cl for r in rows for cl in r.cells.values() if cl.value is not None]
    small = sum(1 for cl in values if abs(cl.value) <= 200 and "$" not in cl.text)
    # the hint in the header decides; in the text before the table (another table's caption?) only if the values fit
    t.percent = bool(re.search(pct_hint, head_text)) or (bool(re.search(pct_hint, unit_text)) and values and small >= 0.8 * len(values))
    if not t.percent:
        for r in rows:
            if statements.match(r.label) == "revenue":
                vals = [cl.value for cl in r.cells.values() if cl.value is not None]
                t.percent = len(vals) >= 2 and all(abs(v - 100) < 1e-9 for v in vals)
                break
    for r in rows:
        if t.percent:
            for cl in r.cells.values():
                cl.pct = True
        k = statements.match(r.label)
        if k:
            t.keys.add(k)
    return t


def _clean_label(s: str) -> str:
    s = re.sub(r"(?<=[A-Za-z\)])\(\d{1,2}\)", "", s)          # footnote marks: "Net loss(2)"
    s = re.sub(r"\s*\((?:\d{1,2}|[a-z])\)(?=\s|$)", "", s)
    return re.sub(r"[*†‡]+$", "", s).strip(" :")


def page_tables(root, page: int) -> list[Table]:
    out = []
    for tb in root.iter("table"):
        if next((a for a in tb.iterancestors("table")), None) is not None:
            continue
        t = parse_table(tb, page)
        if t:
            out.append(t)
    return out


# ---------------------------------------------------------------- periods

def period_label(months: Optional[int], end: Optional[date], lang: str) -> str:
    if end is None:
        return ""
    mon = calendar.month_abbr[end.month]
    mon_it = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"][end.month - 1]
    if months is None:
        return f"{end.day} {mon_it} {end.year}" if lang == "it" else f"{mon} {end.day}, {end.year}"
    if months == 12:
        return (f"Esercizio {end.year}" if end.month == 12 else f"Esercizio al {mon_it} {end.year}") if lang == "it" else \
            (f"FY{end.year}" if end.month == 12 else f"FY to {mon} {end.year}")
    if months == 6 and end.month in (6, 12):
        return f"{'H1' if end.month == 6 else 'H2'} {end.year}" if lang == "en" else f"{'1° sem.' if end.month == 6 else '2° sem.'} {end.year}"
    # a quarter is not named "Q2" here: a fiscal year may not follow the calendar (Apple's Q3 ends in June)
    return f"{months}M to {mon} {end.year}" if lang == "en" else f"{months} mesi al {mon_it} {end.year}"


def _kind(t: Table) -> str:
    """Which statement a table is, from the lines it holds."""
    if {"cfo", "cfi", "cff", "cash_change"} & t.keys:
        return "cf"
    if {"total_assets", "total_liabilities", "current_assets"} & t.keys:
        return "bs"
    return "is" if {"revenue", "net_income", "operating_income", "eps_diluted"} & t.keys else ""


def _year_before(a: date, b: date) -> bool:
    return 350 <= (a - b).days <= 380


def extract(tables: list[Table], lang: str) -> dict:
    """Metrics from statement tables, comparing the latest period with the same period a year earlier.

    Returns {"metrics": {key: {"key", "kind", "cur", "prev"}}, "periods": {...}, "series": {key: [...]}}
    where cur/prev carry the table cell ("el") instead of a fact id; the caller links them."""
    from . import financials as F
    obs: dict[str, list] = {}
    for ti, t in enumerate(tables):
        if t.percent:
            continue
        seen = set()
        for r in t.rows:
            key = statements.match(r.label)
            if not key or key in seen or key not in F.METRICS or not r.cells:     # section headings have no figures
                continue
            kind = F.METRICS[key][2]
            for c, cl in r.cells.items():
                col = t.columns.get(c)
                if not col or col.skip or col.end is None or cl.value is None or cl.pct:
                    continue
                if (kind == "stock") != col.instant:
                    continue
                scale = 1.0 if kind == "ps" or (kind == "shares" and not t.shares_scaled) else \
                    (t.shares_scale or t.scale) if kind == "shares" else t.scale
                v = abs(cl.value) if key in ABS_KEYS else cl.value
                obs.setdefault(key, []).append({"ti": ti, "key": key, "months": col.months, "end": col.end, "value": v * scale,
                                                "display": cl.text, "page": t.page, "el": cl.el})
            seen.add(key)
    if not obs:
        return {"metrics": {}, "periods": {}, "series": {}}

    # the latest period with most figures (flows), the latest balance sheet date (stocks)
    flows = [o for k, os in obs.items() if F.METRICS[k][2] != "stock" for o in os]
    stocks = [o for k, os in obs.items() if F.METRICS[k][2] == "stock" for o in os]
    cur_flow = prev_flow = cur_inst = prev_inst = None
    if flows:
        last = max(o["end"] for o in flows)
        recent = [o for o in flows if (last - o["end"]).days <= 5]
        counts: dict[int, int] = {}
        for o in recent:
            counts[o["months"]] = counts.get(o["months"], 0) + 1
        months = max(counts, key=lambda m: (counts[m], m))
        cur_flow = (months, last)
        prevs = sorted({o["end"] for o in flows if o["months"] == months and _year_before(last, o["end"])}, reverse=True)
        prev_flow = (months, prevs[0]) if prevs else None
    if stocks:
        cur_inst = max(o["end"] for o in stocks)
        earlier = sorted({o["end"] for o in stocks if 60 <= (cur_inst - o["end"]).days <= 400}, reverse=True)
        yb = [e for e in earlier if _year_before(cur_inst, e)]
        # interim balance sheets compare with the last year end
        ye = [e for e in earlier if e.month == 12 and e.day == 31]
        prev_inst = (ye[0] if ye else (yb[0] if yb else (earlier[0] if earlier else None)))

    def pick(os_, months, end, other=None):
        hit = [o for o in os_ if o["months"] == months and abs((o["end"] - end).days) <= 5]
        if not hit:
            return None
        # same value printed in the summary, MD&A and statements: cite the table that also holds the comparative
        # period, then the one with most statement lines
        both = {o["ti"] for o in os_ if other and o["months"] == other[0] and abs((o["end"] - other[1]).days) <= 5}
        return max(hit, key=lambda o: (o["ti"] in both, _kind(tables[o["ti"]]) == statements.statement_of(o["key"]),
                                       len(tables[o["ti"]].keys), -o["page"]))

    metrics, series = {}, {}
    for key, os_ in obs.items():
        kind = F.METRICS[key][2]
        if kind == "stock":
            cur = pick(os_, None, cur_inst, (None, prev_inst) if prev_inst else None) if cur_inst else None
            prev = pick(os_, None, prev_inst, (None, cur_inst)) if prev_inst and cur else None
        else:
            cur = pick(os_, *cur_flow, prev_flow) if cur_flow else None
            prev = pick(os_, *prev_flow, cur_flow) if prev_flow and cur else None
        if cur:
            metrics[key] = {"key": key, "kind": kind, "cur": cur, "prev": prev}
        uniq = {}
        for o in os_:
            uniq.setdefault((o["months"], o["end"]), o)
        series[key] = [{"label": period_label(m, e, lang), "months": m, "end": e.isoformat(), "value": o["value"]}
                       for (m, e), o in sorted(uniq.items(), key=lambda x: (x[0][1], -(x[0][0] or 0)))]
    periods = {
        "flow": [period_label(*cur_flow, lang), period_label(*prev_flow, lang) if prev_flow else ""] if cur_flow else None,
        "stock": [period_label(None, cur_inst, lang), period_label(None, prev_inst, lang) if prev_inst else ""] if cur_inst else None,
    }
    return {"metrics": metrics, "periods": periods, "series": series}

