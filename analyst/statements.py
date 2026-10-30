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
    "revenue": [r"(total )?(net )?(revenues?|sales|turnover)( and other income)?", r"total net sales", r"(total )?(net )?sales to customers",
                r"(total )?(net )?operating revenues?", r"revenues?,? net", r"(total )?net revenues?(,? net of interest expense)?", r"(total )?revenues and other income",
                r"total revenues,? net of interest expense( after provisions? for credit losses)?",
                r"margine di intermediazione", r"proventi operativi netti", r"net banking income", r"total operating income", r"total income",
                r"net interest(,)? (and|fee and) (other|non-?interest|commission) (banking )?(income|revenues?)", r"total net interest and non-?interest income",
                r"(totale )?ricavi( netti)?( delle vendite)?( e delle prestazioni)?", r"fatturato( netto)?", r"net revenues?",
                r"(total )?insurance revenues?", r"ricavi assicurativi( derivanti dai contratti di assicurazione emessi)?"],
    "cost_of_revenue": [r"(total )?cost of (sales|revenues?|goods sold)", r"cost of products sold", r"costo del venduto", r"costi? delle vendite"],
    "gross_profit": [r"gross (profit|margin)", r"(margine|utile) lordo"],
    "rnd": [r"research and development( expenses?| costs?)?", r"(costi|spese) (di|per) ricerca e sviluppo"],
    "operating_income": [r"operating (income|profit|loss)( \(loss\))?", r"operating \(loss\) income", r"(income|loss|\(loss\) income|income \(loss\)) from operations",
                         r"(ebit|operating result)",
                         r"risultato operativo", r"utile operativo", r"reddito operativo"],
    "pretax_income": [r"(income|profit|earnings|loss|\(loss\) income|income \(loss\))( \(loss\))? before (provision for |benefit from |\(benefit from\) provision for |provision for \(benefit from\) )?(income )?tax(es)?",
                      r"(income|earnings|profit|loss)( \(loss\))? from continuing operations before (provision|\(?benefit|income tax|tax).*",
                      r"(utile|risultato|perdita) (prima|ante) (delle )?imposte"],
    "income_tax": [r"(provision for )?income tax(es| expense)?( expense)?", r"income tax (expense|provision)( \(benefit\))?",
                   r"(provision for|benefit from|\(benefit from\) provision for|provision for \(benefit from\)) income taxes", r"imposte( sul reddito)?( dell'esercizio)?",
                   r"(provision for|benefit from|\(benefit from\) provision for|provision for \(benefit from\)) taxes( on income)?", r"taxes on income",
                   r"(income )?tax (expense|provision|benefit)( \(benefit\)| \(expense\))?",
                   r"(provision|benefit) ?/ ?\(?(benefit|provision)\)? for (income )?taxes( on income)?",
                   r"(benefit|provision) \((provision|benefit)\) for income taxes"],
    "net_income": [r"(consolidated )?net (income|profit|earnings|loss|\(loss\) income|income \(loss\)|loss \(income\)|income ?/ ?\(loss\)|earnings ?/ ?\(loss\)|\(loss\) ?/ ?income)( attributable to (?!.*(non-?controlling|minority|redeemable)).*)?",
                   r"profit for the (year|period)( attributable to owners.*)?", r"(utile|risultato) netto( dell'esercizio| di gruppo| attribuibile.*)?",
                   r"utile dell'esercizio"],
    "eps_diluted": [r"diluted (earnings|net income|net loss|eps|loss)( \(loss\))?( per (common |ordinary )?share)?( attributable to [^,]*)?( \(.*\))?",
                    r"earnings per share[ -–—]+diluted",
                    r"(?=.*diluted)(basic and diluted )?net (income|loss|earnings|\(loss\) income|income \(loss\)|loss \(income\)) per (common |ordinary )?share.*",
                    r"(?=.*diluted)(earnings|loss) per (common |ordinary )?share.*",
                    r"(?=.*diluted)(earnings|net income|net loss|income|loss)( \(loss\))? per (common |ordinary )?share.*",
                    r"diluted", r"utile (netto )?(diluito )?per azione( diluito)?( \(.*\))?"],
    "diluted_shares": [r"weighted[- ]average (number of )?(common |ordinary )?shares.*diluted.*", r"diluted (weighted[- ]average )?shares.*"],
    "opex_total": [r"total operating (expenses|costs and expenses)", r"total costs and expenses", r"(totale )?costi operativi"],
    "interest_expense": [r"interest expense", r"finance costs?", r"oneri finanziari"],
    "cash": [r"cash and cash equivalents", r"cash and equivalents", r"disponibilit[aà] liquide( e mezzi equivalenti)?"],
    "current_assets": [r"total current assets", r"(totale )?attivit[aà] correnti", r"totale attivo corrente"],
    "total_assets": [r"total assets", r"totale (attivo|attivit[aà])"],
    "current_liabilities": [r"total current liabilities", r"(totale )?passivit[aà] correnti"],
    "total_liabilities": [r"total liabilities", r"totale passivit[aà]"],
    "liab_and_equity": [r"total liabilities(,| and) .*(equity|deficit)", r"totale passivit[aà] e patrimonio netto"],
    "temp_equity": [r"(total )?redeemable (convertible )?(preferred|preference) (stock|shares)(,.*)?", r"(total )?(temporary|mezzanine) equity"],
    "equity": [r"total (stockholders|shareholders|share-holders)['’]? (equity|deficit|equity \(deficit\)|\(deficit\) equity)", r"total equity( \(deficit\))?",
               r"total deficit", r"(totale )?patrimonio netto( totale)?"],
    "cfo": [r"net cash (provided by|from|generated (by|from)|used in|provided by \(used in\)|\(used in\) provided by|used in\) provided by) operating activities",
            r"cash (flows? )?(generated )?from operating activities", r"cash generated from operations",
            r"flusso di cassa (netto )?(generato )?(da|dalle|dell'|delle) attivit[aà] operativ[ae]", r"flussi di cassa (netti )?(da|dalle) attivit[aà] operative"],
    "cfi": [r"net cash (provided by|from|used in|provided by \(used in\)|\(used in\) provided by) investing activities",
            r"cash (flows? )?(used in|from) investing activities", r"flusso di cassa (netto )?(da|dalle|dell'|delle) attivit[aà] di investimento"],
    "cff": [r"net cash (provided by|from|used in|provided by \(used in\)|\(used in\) provided by) financing activities",
            r"cash (flows? )?(used in|from) financing activities", r"flusso di cassa (netto )?(da|dalle|dell'|delle) attivit[aà] di finanziamento"],
    "fx_effect": [r"effects? of (foreign )?(currency )?exchange( rate)?( changes| fluctuations| rate changes)? on cash.*", r"effects? of exchange rate (changes|fluctuations).*", r"effects? of (changes in )?(foreign )?(currency )?exchange rates?.*",
                  r"effetto (delle )?(variazioni )?(dei )?cambi.*"],
    "cash_hfs": [r"(\(increase\)/decrease|\(increase\) decrease|increase/\(decrease\)|change) in cash.*(included in|classified as|reclassified (as|to)) (assets? )?held for sale.*",
                 r"(variazione delle )?disponibilit[aà] liquide.*(attivit[aà]|gruppi in dismissione) (possedute|destinate) (per la|alla) vendita.*"],
    "cash_change": [r"net (increase|decrease|increase \(decrease\)|\(decrease\) increase|change) in cash.*",
                    r"(increase|decrease|increase/\(decrease\)|increase \(decrease\)|\(decrease\)/increase|\(decrease\) increase) in cash,? (and )?cash equivalents.*", r"variazione (netta )?delle disponibilit[aà] liquide.*"],
    "capex": [r"(purchases?|acquisitions?|additions?|payments?) (of|to|for) property,? (plant,? )?and equipment.*",
              r"capital expenditures?", r"investimenti in immobilizzazioni materiali", r"acquisti? di immobili,? impianti e macchinari"],
    "sbc": [r"(total )?(stock|share)[- ]based (compensation|payments?)( expense)?( \(.*\))?", r"(costi|compensi) (per pagamenti )?basati su azioni"],
    "buybacks": [r"(repurchases?|purchases?) of (common |ordinary |treasury )?(stock|shares)", r"acquisto (di )?azioni proprie"],
    "dividends": [r"(cash )?dividends paid( to .*)?", r"dividendi (pagati|distribuiti)"],
}
_COMPILED = {k: [re.compile(rf"^{p}$", re.I) for p in v] for k, v in PATTERNS.items()}
PER_SHARE = {"eps_diluted"}

SCALES = [
    (r"in (u\.s\. )?(\$ )?billions|in miliardi|\((us)?\$ ?billions?\)|\$ ?in billions", 1e9),
    (r"in (u\.s\. )?(\$ )?millions|\$ ?in millions|in milioni|milioni di euro|€ ?million|eur(o)? millions?|in millions of"
     r"|\((us|u\.s\.)?\$ ?millions?\b|\(millions(,| of| except|\))|\bmillions, except|\$ ?millions?\)|\(in \$ ?millions?|dollars in millions|amounts in millions", 1e6),
    (r"in thousands|in migliaia|migliaia di euro|€ ?thousands?|eur(o)? thousands?|in thousands of"
     r"|\((us|u\.s\.)?\$ ?thousands?\b|\(thousands(,| of| except|\))|\bthousands, except|\(in \$ ?thousands?|dollars in thousands|amounts in thousands", 1e3),
]


def _clean(label: str) -> str:
    s = label.lower().replace("’", "'").strip(" :.,;")
    s = re.sub(r"\s*\((note|nota) ?\d+\)|\s+\d{1,2}$", "", s)        # note references
    s = re.sub(r"(?<=[a-z\)'])\((\d{1,2}|[a-h])\)|[*†‡]+", "", s)          # footnote marks: "net loss(2)", "total assets(a)"
    s = re.sub(r"\s\(([a-h]|\d{1,2})\)$", "", s)                            # "cost of sales (a)"
    s = re.sub(r"^(voce |item )?\d{1,3}(\.|\))\s*|^(voce |item )?\d{1,3}\s+|^[a-z]\)\s+", "", s)  # line numbers: "120. margine di intermediazione"
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
    ys = header_years(text)
    if len(ys) < 2:
        return None
    return max(ys), max(ys) - 1


YEAR = re.compile(r"(?<![\d,.$])((?:19|20)\d\d)(?![\d,.%])")
STATEMENT_TITLE = re.compile(
    r"consolidated (balance sheets?|statements? of (financial (position|condition)|operations|income|earnings|comprehensive (income|loss)|cash flows?))"
    r"|statements? of (operations|income|earnings|cash flows?|financial position)|balance sheets?|income statements?"
    r"|conto economico|stato patrimoniale|rendiconto finanziario|situazione patrimoniale", re.I)
MONTHS_RE = r"(january|february|march|april|may|june|july|august|september|october|november|december)"
MONTH_NO = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
DATE_RE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+((?:19|20)\d\d)\b", re.I)
QUARTER_RE = re.compile(r"\b(?:([1-4])Q\s?['’]?(\d{2}|\d{4})|Q([1-4])\s?['’]?(\d{2}|\d{4}))\b")


def header_quarters(text: str) -> list[tuple[int, int]]:
    """Quarter codes heading the columns ("1Q23 4Q22 … 1Q22", "Q2 2023 Q2 2022") as (year, quarter)."""
    out, last = [], None
    for m in QUARTER_RE.finditer(text[:2500]):
        q = int(m.group(1) or m.group(3))
        y = int(m.group(2) or m.group(4))
        y = y + 2000 if y < 100 else y
        if last is not None and m.start() - last > 45:
            if len(out) >= 2:
                break
            out = []
        out.append((y, q))
        last = m.start()
    return out if len(out) >= 2 and len(set(out)) > 1 else []


def header_dates(text: str, years: list[int]) -> list:
    """The full date of each column when the header prints it ("June 2, 2023  December 2, 2022")."""
    from datetime import date
    import calendar
    out = []
    for m in DATE_RE.finditer(text[:2500]):
        mo = MONTH_NO[m.group(1).lower()[:3]]
        y = int(m.group(3))
        out.append(date(y, mo, min(int(m.group(2)), calendar.monthrange(y, mo)[1])))
        if len(out) >= len(years):
            break
    if len(out) >= 2 and [d.year for d in out[:len(years)]] == years[:len(out)]:
        return out
    # "January 28,  January 29," on one line and "2023  2022" on the next: pair them in order
    # where the run of column years starts (a year in the page heading comes earlier and is not it)
    hits = [(x.start(), int(x.group(1))) for x in YEAR.finditer(text[:2500])]
    first_year = None
    for i in range(len(hits) - len(years) + 1):
        seq = hits[i:i + len(years)]
        if [y for _, y in seq] == years and all(b[0] - a[0] <= 45 for a, b in zip(seq, seq[1:])):
            first_year = seq[0][0]
            break
    if first_year is None:
        return []
    mds = re.findall(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?(?!\s*,?\s*(?:19|20)\d\d)",
                     text[max(0, first_year - 200):first_year], re.I)
    if len(mds) < len(years):
        return []
    mds = mds[-len(years):]
    try:
        return [date(y, MONTH_NO[mo.lower()[:3]], min(int(d), calendar.monthrange(y, MONTH_NO[mo.lower()[:3]])[1])) for (mo, d), y in zip(mds, years)]
    except ValueError:
        return []


def header_years(text: str) -> list[int]:
    """The years heading the columns, in their order: the first run of two or more different years printed close
    together ("2017 2018 2019", "June 30, 2023 July 1, 2022", "2023 2022 2023 2022")."""
    # a line made of years is the column header, even under a dateline that names them too
    # ("Fiscal years ended December 31, 2022, December 25, 2021 and …" / "2022 2021 2020")
    for line in text[:2500].splitlines():
        toks = line.replace("$", " ").split()
        ys = [int(x) for x in toks if YEAR.fullmatch(x)]
        if len(ys) >= 2 and len(set(ys)) > 1 and all(YEAR.fullmatch(x) or x.lower() in ("note", "notes", "nota", "note:", "%", "change") for x in toks):
            return ys
    run: list[tuple[int, int]] = []
    for m in YEAR.finditer(text[:2500]):
        pos, y = m.start(), int(m.group(1))
        if run and pos - run[-1][0] <= 45 and abs(y - run[-1][1]) <= 3:
            run.append((pos, y))
            continue
        if len(run) >= 2 and len({v for _, v in run}) > 1:
            break
        run = [(pos, y)]
    ys = [y for _, y in run] if len(run) >= 2 and len({v for _, v in run}) > 1 else []
    if ys:
        # a dateline just above the header names the years in prose ("Years Ended May 31, 2023, 2022 and 2021"
        # reads as 2022 2021): the header right after it, with a later year, is the one
        later = header_years(text[run[-1][0] + 4:run[0][0] + 400]) if run[-1][0] + 4 < len(text) else []
        if later and max(later) > max(ys):
            return later
    # a dateline running into the header ("… 2022, 2021, and 2020  2022 2021 2020" read as 2020 2022 2021 2020):
    # columns are in order (2022 2021 2020), or the same block twice (2023 2022 2023 2022)
    def ordered(v):
        mono = lambda s: len(s) >= 2 and (all(a > b for a, b in zip(s, s[1:])) or all(a < b for a, b in zip(s, s[1:])))
        return mono(v) or (len(v) % 2 == 0 and v[:len(v) // 2] == v[len(v) // 2:] and mono(v[:len(v) // 2]))
    while len(ys) > 3 and not ordered(ys) and ordered(ys[1:]):
        ys = ys[1:]
    return ys


def page_period(text: str) -> dict:
    """What the columns of a statement page are: their length in months (None for a balance sheet date) and end."""
    lo = text[:2500].lower()
    months = None
    for pat, m in ((r"three months|(twelve|thirteen|sixteen|12|13|16) weeks|quarters? ended|(first|second|third|fourth) quarter|tre mesi|trimestre", 3),
                   (r"six months|(twenty-four|twenty-six|24|26) weeks|half[- ]year|sei mesi|semestre", 6),
                   (r"nine months|(thirty-six|thirty-nine|thirty-six|36|39|40) weeks|nove mesi", 9),
                   (r"years? ended|fiscal years? ended|twelve months|(fifty-two|fifty-three|52|53) weeks|esercizio", 12)):
        pos = re.search(pat, lo)
        if pos and (months is None or pos.start() < months[1]):
            months = (m, pos.start())
    md = re.search(r"(?:ended|ending|as of|as at|at)\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b", lo)
    fq = re.search(r"\b(first|second|third|fourth)[- ]quarter\b", lo)
    instant = months is None and bool(re.search(r"balance sheet|financial position|as of|as at|stato patrimoniale|situazione patrimoniale", lo))
    if md is None and instant:
        # a balance sheet headed by its date alone: "BALANCE SHEETS (In millions) June 30, 2023 2022"
        md = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b", lo[:400])
    return {"months": months[0] if months else None, "month": MONTH_NO[md.group(1)] if md else 12,
            "day": int(md.group(2)) if md else 31, "instant": instant,
            "fiscal_q": ["first", "second", "third", "fourth"].index(fq.group(1)) + 1 if fq and not md else None}


# which statement each item belongs to: its figure is taken from that statement when the document has it
IS_KEYS = {"revenue", "cost_of_revenue", "gross_profit", "rnd", "opex_total", "operating_income", "pretax_income", "income_tax",
           "net_income", "profit_total", "eps_diluted", "diluted_shares", "interest_expense"}
CF_KEYS = {"cfo", "cfi", "cff", "capex", "buybacks", "dividends", "sbc", "cash_change", "fx_effect", "cash_hfs"}
IS_TITLE = re.compile(r"statements? of (consolidated )?(operations|income|earnings|comprehensive (income|loss))|income statements?|conto economico", re.I)
CF_TITLE = re.compile(r"statements? of (consolidated )?cash flows?|cash flows? statements?|rendiconto finanziario", re.I)
BS_TITLE = re.compile(r"balance sheets?|statements? of (consolidated )?financial (position|condition)|stato patrimoniale|situazione patrimoniale", re.I)


def _line_rank(key: str, label: str) -> int:
    """Between two lines of the same statement: total revenue before net sales, the result attributable to
    the company before the result including minority interests."""
    if key == "revenue":
        return 2 if label.startswith("total") else 1
    if key == "net_income":
        return 2 if "attributable to" in label else 1
    return 0


def statement_of(key: str) -> str:
    return "is" if key in IS_KEYS else "cf" if key in CF_KEYS else "bs"


def page_statement(text: str) -> str:
    head = text[:700]
    for kind, rx in (("cf", CF_TITLE), ("bs", BS_TITLE), ("is", IS_TITLE)):
        if rx.search(head):
            return kind
    return ""


HEADER_NEAR = re.compile(r"(quarters?|years?|months|weeks|periods?) ended|\(in (millions|thousands|billions)|\((millions|thousands|dollars)|esercizio|migliaia|milioni", re.I)


def statement_start(text: str) -> int:
    """Where a statement printed lower on the page begins (a release's text above its statement of earnings):
    its title followed by its column header. 0 when the page opens with it, or holds none."""
    if STATEMENT_TITLE.search(text[:700]):
        return 0
    for m in STATEMENT_TITLE.finditer(text):
        if HEADER_NEAR.search(text[m.end():m.end() + 250]):
            return m.start()
    return 0


def statement_pages(texts: list[str]) -> list[int]:
    """0-based pages of the primary statements (income, balance sheet, cash flows): a page titled as one near its
    top and full of figures; consolidated before parent-company, the statement itself before its analysis or notes.
    For each statement: the first such page and the fullest one (they differ when a summary or a guarantor's
    statements share the title)."""
    best: dict[str, tuple] = {}
    first: dict[str, tuple] = {}
    for i, t in enumerate(texts):
        t = t[statement_start(t):]
        head = t[:300]
        kind = page_statement(head)
        if not kind or re.search(r"analysis of|notes to|discussion and analysis|report of independent|exhibits and financial statement schedules", head, re.I):
            continue
        title = STATEMENT_TITLE.search(t[:700])
        if not title or not (HEADER_NEAR.search(t[title.end():title.end() + 300]) or header_years(t[title.end():title.end() + 300])):
            continue                                   # a title with its column header under it, not a mention
        figs = len(re.findall(r"\(?\d[\d,]{2,}\)?", t))
        if figs < 12:
            continue
        rank = (not re.search(r"parent company|registrant|capogruppo", head, re.I), "consolidat" in head.lower(),
                not re.search(r"comprehensive", head, re.I), figs)
        if kind not in best or rank > best[kind][0]:
            best[kind] = (rank, i)
        if kind not in first or rank[:3] > first[kind][0]:
            first[kind] = (rank[:3], i)
    return sorted({i for _, i in best.values()} | {i for _, i in first.values()})


def _is_note_ref(f: dict) -> bool:
    return bool(re.fullmatch(r"\d{1,2}", f["display"].strip()))


def _drop_note_ref(nums: list, years: list) -> list:
    """A "Note" column before the amounts ("Net sales  4  12,450  11,200"): a small whole number in front of
    more figures than the page has year columns. A two-digit amount in its own column stays."""
    if len(nums) >= 2 and _is_note_ref(nums[0]):
        cols = len(years) if len(years) >= 2 else 2
        if len(nums) > cols:
            return nums[1:]
    return nums


def _amounts(nums: list, key: str) -> list:
    """Drop "% of sales" and "% change" columns printed between the amounts (one decimal, at most 100), and keep
    amounts and per-share figures apart when one label heads both ("Net income attributable to …" over the
    amount and, again, over earnings per share; "Diluted" over EPS and over the share count)."""
    per_share = [f for f in nums if re.fullmatch(r"\(?-?\d{1,3}\.\d{2,3}\)?", f["display"].strip("$€£ "))]
    if per_share and len(per_share) < len(nums):
        nums = per_share if key in PER_SHARE else [f for f in nums if f not in per_share]
    if key in PER_SHARE or len(nums) < 3:
        return nums
    pct = [f for f in nums if re.fullmatch(r"\(?-?\d{1,3}\.\d\)?%?", f["display"].strip("$ ")) and abs(f["value"]) <= 100]
    if pct and len(pct) < len(nums) and all(re.search(r"\d,\d{3}|^\(?\$?\s?\d+\)?$", f["display"].strip()) for f in nums if f not in pct):
        return [f for f in nums if f not in pct]
    return nums


def _columns(nums: list, years: list, quarters: Optional[list] = None) -> tuple:
    """(current, comparative) figure of a row, by the years (or quarter codes) heading the page's columns."""
    if quarters and len(nums) >= len(quarters):
        top = max(quarters)
        cur_i = quarters.index(top)
        same = (top[0] - 1, top[1])                       # the same quarter a year earlier
        prev_i = quarters.index(same) if same in quarters else None
        return nums[cur_i], (nums[prev_i] if prev_i is not None else None)
    if len(years) >= 2 and len(nums) >= len(years):
        top = max(years)
        cur_i = years.index(top)
        prev_i = years.index(top - 1) if top - 1 in years else None
        return nums[cur_i], (nums[prev_i] if prev_i is not None else None)
    if len(years) >= 2 and years[0] < years[-1]:          # ascending columns, some cells empty: the last ones
        return nums[-1], (nums[-2] if len(nums) > 1 else None)
    return nums[0], (nums[1] if len(nums) > 1 else None)


def extract(facts: list[dict], page_text: dict[int, str]) -> dict:
    """facts: [{id, label, value, display, page}] -> {"metrics", "currency", "years", "periods"} like financials.extract()."""
    # the column header, period and scale of a page are those of the statement on it, wherever it starts
    page_text = {p: t[statement_start(t):] for p, t in page_text.items()}
    from datetime import date
    import calendar
    from . import financials as F
    from .tables import period_label
    from .i18n import lang
    groups: dict[tuple[int, str], list[dict]] = {}
    for f in facts:
        groups.setdefault((f["page"], f["label"]), []).append(f)
    found: dict[str, list] = {}
    for (page, label), fs in groups.items():
        key = match(label)
        if not key:
            continue
        nums = sorted(fs, key=lambda f: f["id"])
        nums = _amounts(_drop_note_ref(nums, header_years(page_text.get(page, ""))), key)
        if key == "eps_diluted" and _clean(label) == "diluted" and not any(re.search(r"\d[.,]\d\d$", f["display"].strip("()$ ")) for f in nums):
            continue                                       # a bare "Diluted" row of share counts, not earnings per share
        if not nums:
            continue
        found.setdefault(key, []).append((page, nums, _clean(label)))
    # statements are the pages titled as such, then the pages where most metrics were recognised
    page_hits: dict[int, int] = {}
    for key, cands in found.items():
        for page, *_ in cands:
            page_hits[page] = page_hits.get(page, 0) + 1
    def title_score(t: str) -> int:
        head = t[:700].lower()
        if not STATEMENT_TITLE.search(head):
            return 0
        if re.search(r"parent company|condensed financial information of (the )?registrant|schedule i\b|capogruppo|separate financial statements|bilancio separato", head):
            return 1
        return 3 if "consolidated" in head or "consolidat" in head else 2
    titled = {p: title_score(t) for p, t in page_text.items()}
    kind_of = {p: page_statement(t) for p, t in page_text.items()}

    metrics, years = {}, None
    head: dict[str, dict] = {}
    for key, cands in found.items():
        page, nums, _ = max(cands, key=lambda c: (titled.get(c[0], 0) >= 2 and kind_of.get(c[0]) == statement_of(key), titled.get(c[0], 0),
                                                   kind_of.get(c[0]) == statement_of(key), page_hits[c[0]], _line_rank(key, c[2]),
                                                   len(c[1]) >= 2, -c[0]))
        has_statement = any(k == statement_of(key) and titled.get(p, 0) >= 2 for p, k in kind_of.items())
        if has_statement and kind_of.get(page) != statement_of(key) and len(nums) < 2:
            continue                                   # a lone figure elsewhere (a segment's) is not the statement's line
        text = page_text.get(page, "")
        ys = header_years(text)
        qs = header_quarters(text)
        cur_f, prev_f = _columns(nums, ys, qs)
        scale = 1.0 if key in PER_SHARE else page_scale(text)
        kind = F.METRICS[key][2] if key in F.METRICS else "flow"
        if kind == "shares" and not re.search(r"shares? in (thousands|millions)|in (thousands|millions), except per share", text[:2500], re.I):
            scale = 1.0

        def fd(f):
            v = abs(f["value"]) if key in ("capex", "buybacks", "dividends", "cost_of_revenue", "rnd", "interest_expense", "income_tax") else f["value"]
            return {"id": f["id"], "value": v * scale, "display": f["display"], "page": f["page"], "concept": "", "unit": ""}

        metrics[key] = {"key": key, "kind": "ps" if key in PER_SHARE else kind, "cur": fd(cur_f),
                        "prev": fd(prev_f) if prev_f and prev_f is not cur_f else None}
        side = "stock" if kind == "stock" else "flow"
        if (ys or qs) and side not in head:
            head[side] = {**page_period(text), "years": ys or [y for y, _ in qs], "quarters": qs, "dates": header_dates(text, ys) if ys else []}
        if ys and years is None:
            years = (max(ys), max(ys) - 1)
    periods = {}
    for side, h in head.items():
        if h["quarters"]:
            (y, q) = max(h["quarters"])
            periods[side] = [f"{q}Q{str(y)[2:]}", f"{q}Q{str(y - 1)[2:]}" if (y - 1, q) in h["quarters"] else ""]
            continue
        top = max(h["years"])

        def end(y):
            # the date printed over the column when there is one, else the period's month and day
            for d in h["dates"]:
                if d.year == y:
                    return d
            return date(y, h["month"], min(h["day"], calendar.monthrange(y, h["month"])[1]))
        if side == "stock":
            periods[side] = [period_label(None, end(top), lang()), period_label(None, end(top - 1), lang()) if top - 1 in h["years"] else ""]
        elif h.get("fiscal_q") and (h["months"] or 3) == 3:
            # "Second Quarter 2023 / 2022" without dates: the company's own quarter
            q = h["fiscal_q"]
            periods[side] = [f"Q{q} {top}" if lang() == "en" else f"{q}° trim. {top}", f"Q{q} {top - 1}" if lang() == "en" else f"{q}° trim. {top - 1}"]
        else:
            months = h["months"] or 12
            periods[side] = [period_label(months, end(top), lang()), period_label(months, end(top - 1), lang())]
    cur = next((page_currency(page_text.get(m["cur"]["page"], "")) for m in metrics.values()), "")
    return {"metrics": metrics, "currency": cur, "years": years, "periods": periods or None}
