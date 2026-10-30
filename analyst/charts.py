"""Charts for the PDF report, drawn with reportlab primitives in the app's palette.

Every chart is built only from numbers the analysis already holds: figures read
from the document (or daily prices) and ratios computed from them.
"""
from __future__ import annotations

import math
from typing import Optional

from reportlab.lib import colors
from reportlab.platypus import Flowable, KeepTogether, Paragraph, Spacer, Table, TableStyle

from . import financials as F
from .i18n import t

INK = colors.HexColor("#1d1c26")
MUTED = colors.HexColor("#6c6a7c")
GRID = colors.HexColor("#ecebf2")
LINE_SOFT = colors.HexColor("#b9b6c8")
PINK = colors.HexColor("#ff2d8f")
PRIOR = colors.HexColor("#c9c6d8")
BLUE = colors.HexColor("#3b6cff")
CYAN = colors.HexColor("#39c5e8")
UP = colors.HexColor("#0f8a5f")
DOWN = colors.HexColor("#c8323c")
AMBER = colors.HexColor("#f2b134")
VIOLET = colors.HexColor("#783bff")
SANS, SANS_B = "Helvetica", "Helvetica-Bold"
_SAFE = str.maketrans({"−": "-", "→": "->", "≈": "~", " ": " ", " ": " "})


def _s(v) -> str:
    return str(v if v is not None else "").translate(_SAFE)


def _nice_ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    if hi == lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(abs(raw)))
    step = min((1, 2, 2.5, 5, 10), key=lambda m: abs(m * mag - raw)) * mag
    start = math.floor(lo / step) * step
    ticks, v = [], start
    while v <= hi + step * 0.5:
        ticks.append(v)
        v += step
    return ticks


class Chart(Flowable):
    def __init__(self, width: float, height: float):
        super().__init__()
        self.width, self.height = width, height

    def text(self, x, y, s, size=7, color=MUTED, font=SANS, anchor="left"):
        c = self.canv
        c.setFont(font, size)
        c.setFillColor(color)
        s = _s(s)
        if anchor == "right":
            c.drawRightString(x, y, s)
        elif anchor == "center":
            c.drawCentredString(x, y, s)
        else:
            c.drawString(x, y, s)

    def legend(self, items, y):
        x = self.width
        for label, col in reversed(items):
            w = self.canv.stringWidth(_s(label), SANS, 7)
            x -= w
            self.text(x, y, label, 7, MUTED)
            x -= 10
            self.canv.setFillColor(col)
            self.canv.rect(x, y - 0.5, 7, 7, stroke=0, fill=1)
            x -= 10


class GroupedBars(Chart):
    """Current vs prior year for a few headline amounts."""

    def __init__(self, width, height, items, years, fmt):
        super().__init__(width, height)
        self.items, self.years, self.fmt = items, years, fmt

    def draw(self):
        c = self.canv
        left, bottom, top = 46, 26, self.height - 16
        vals = [v for _, cur, prev in self.items for v in (cur, prev) if v is not None]
        lo, hi = min(0, min(vals)), max(0, max(vals))
        ticks = _nice_ticks(lo, hi)
        lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
        y = lambda v: bottom + (v - lo) / (hi - lo) * (top - bottom)
        for tk in ticks:
            c.setStrokeColor(GRID); c.setLineWidth(0.5)
            c.line(left, y(tk), self.width, y(tk))
            self.text(left - 4, y(tk) - 2.5, self.fmt(tk), 6.5, MUTED, anchor="right")
        n = len(self.items)
        slot = (self.width - left) / n
        bw = min(26, slot * 0.3)
        for i, (label, cur, prev) in enumerate(self.items):
            cx = left + slot * (i + 0.5)
            for j, (v, col) in enumerate(((prev, PRIOR), (cur, PINK))):
                if v is None:
                    continue
                x = cx - bw - 1 + j * (bw + 2)
                y0, y1 = y(0), y(v)
                c.setFillColor(col)
                c.rect(x, min(y0, y1), bw, abs(y1 - y0), stroke=0, fill=1)
                if j == 1:
                    self.text(x + bw / 2, max(y0, y1) + 3, self.fmt(v), 6.5, INK, SANS_B, "center")
            self.text(cx, 12, label, 7, INK, anchor="center")
            if cur is not None and prev and cur > 0 and prev > 0:       # no growth rate across or between negatives
                g = (cur - prev) / abs(prev)
                self.text(cx, 3, F.fmt_pct(g, 1, signed=True), 6.5, UP if g >= 0 else DOWN, SANS_B, "center")
        c.setStrokeColor(INK); c.setLineWidth(0.7)
        c.line(left, y(0), self.width, y(0))
        self.legend([(self.years[1], PRIOR), (self.years[0], PINK)], self.height - 8)


class MarginBars(Chart):
    """Margins as horizontal bars, current vs prior."""

    def __init__(self, width, height, items, years):
        super().__init__(width, height)
        self.items, self.years = items, years

    def draw(self):
        c = self.canv
        left, right = 92, self.width - 34
        vals = [abs(v) for _, cur, prev in self.items for v in (cur, prev) if v is not None]
        hi = max(vals + [0.01])
        row = (self.height - 18) / max(len(self.items), 1)
        for i, (label, cur, prev) in enumerate(self.items):
            y0 = self.height - 18 - row * (i + 1) + row * 0.2
            self.text(0, y0 + row * 0.3, label, 7.5, INK)
            for j, (v, col) in enumerate(((cur, PINK), (prev, PRIOR))):
                if v is None:
                    continue
                h = row * 0.3
                yy = y0 + row * 0.33 - j * (h + 1.5)
                w = max(0.5, abs(v) / hi * (right - left))
                c.setFillColor(col if v >= 0 else DOWN)
                c.rect(left, yy, w, h, stroke=0, fill=1)
                self.text(left + w + 3, yy + 1, F.fmt_pct(v), 6.5, INK if j == 0 else MUTED, SANS_B if j == 0 else SANS)
        self.legend([(self.years[1], PRIOR), (self.years[0], PINK)], self.height - 8)


class Waterfall(Chart):
    """Where the operating cash went: CFO, capex, FCF, buybacks, dividends, what is left."""

    def __init__(self, width, height, steps, fmt):
        super().__init__(width, height)
        self.steps, self.fmt = steps, fmt

    def draw(self):
        c = self.canv
        left, bottom, top = 46, 22, self.height - 10
        running, spans = 0.0, []
        for label, v, kind in self.steps:
            if kind == "total":
                spans.append((label, 0, v, kind))
                running = v
            else:
                spans.append((label, running, running + v, kind))
                running += v
        vals = [x for _, a, b, _ in spans for x in (a, b)]
        lo, hi = min(0, min(vals)), max(vals)
        ticks = _nice_ticks(lo, hi)
        lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
        y = lambda v: bottom + (v - lo) / (hi - lo) * (top - bottom)
        for tk in ticks:
            c.setStrokeColor(GRID); c.setLineWidth(0.5)
            c.line(left, y(tk), self.width, y(tk))
            self.text(left - 4, y(tk) - 2.5, self.fmt(tk), 6.5, MUTED, anchor="right")
        slot = (self.width - left) / len(spans)
        bw = slot * 0.56
        prev_top = None
        for i, (label, a, b, kind) in enumerate(spans):
            x = left + slot * i + (slot - bw) / 2
            col = BLUE if kind == "total" else (DOWN if b < a else UP)
            c.setFillColor(col)
            c.rect(x, y(min(a, b)), bw, max(0.6, abs(y(b) - y(a))), stroke=0, fill=1)
            if prev_top is not None:
                c.setStrokeColor(MUTED); c.setLineWidth(0.4); c.setDash(1.5, 1.5)
                c.line(x - (slot - bw), y(prev_top), x, y(prev_top))
                c.setDash()
            prev_top = b
            val = b - a if kind != "total" else b
            self.text(x + bw / 2, y(max(a, b)) + 3, self.fmt(val), 6.5, INK, SANS_B, "center")
            self.text(x + bw / 2, 8, label, 6.8, INK, anchor="center")
        c.setStrokeColor(INK); c.setLineWidth(0.7)
        c.line(left, y(0), self.width, y(0))


class BalanceStack(Chart):
    """Assets against liabilities and equity, current and prior year."""

    def __init__(self, width, height, cols, fmt):
        super().__init__(width, height)
        self.cols, self.fmt = cols, fmt          # [(label, [(part, value, colour), ...]), ...]

    def draw(self):
        c = self.canv
        bottom, top = 26, self.height - 32
        hi = max(sum(max(v, 0) for _, v, _ in parts) for _, parts in self.cols) or 1
        slot = self.width / len(self.cols)
        bw = min(38, slot * 0.5)
        legend = {}
        for i, (label, parts) in enumerate(self.cols):
            x = slot * i + (slot - bw) / 2
            yy = bottom
            for part, v, col in parts:
                if v <= 0:
                    continue
                h = v / hi * (top - bottom)
                c.setFillColor(col)
                c.rect(x, yy, bw, h, stroke=0, fill=1)
                if h > 11:
                    self.text(x + bw / 2, yy + h / 2 - 2.5, self.fmt(v), 6, colors.white, SANS_B, "center")
                yy += h
                legend[part] = col
            head, _, when = label.partition("\n")          # "Assets" over "Jun 30, 2025"
            self.text(x + bw / 2, 13, head, 7, INK, anchor="center")
            if when:
                self.text(x + bw / 2, 4, when, 6.3, MUTED, anchor="center")
        lx, ly = 0, self.height - 10
        for part, col in legend.items():
            w = 14 + c.stringWidth(_s(part), SANS, 6.8) + 8
            if lx and lx + w > self.width:
                lx, ly = 0, ly - 10
            c.setFillColor(col)
            c.rect(lx, ly, 7, 7, stroke=0, fill=1)
            self.text(lx + 10, ly + 0.5, part, 6.8)
            lx += w


class LineArea(Chart):
    """Daily price (or drawdown) line with a light area underneath."""

    def __init__(self, width, height, points, fmt, color=PINK, zero_top=False):
        super().__init__(width, height)
        self.points, self.fmt, self.color, self.zero_top = points, fmt, color, zero_top

    def draw(self):
        c = self.canv
        left, bottom, top = 50, 16, self.height - 6
        vals = [p[1] for p in self.points]
        lo, hi = min(vals), max(vals)
        if self.zero_top:
            hi = 0
        ticks = _nice_ticks(lo, hi)
        lo, hi = (min(lo, ticks[0]), hi if self.zero_top else max(hi, ticks[-1]))
        if hi == lo:
            hi = lo + 1
        n = len(self.points)
        X = lambda i: left + (self.width - left) * i / max(n - 1, 1)
        Y = lambda v: bottom + (v - lo) / (hi - lo) * (top - bottom)
        for tk in ticks:
            if lo <= tk <= hi:
                c.setStrokeColor(GRID); c.setLineWidth(0.5)
                c.line(left, Y(tk), self.width, Y(tk))
                self.text(left - 4, Y(tk) - 2.5, self.fmt(tk), 6.5, MUTED, anchor="right")
        base = Y(hi) if self.zero_top else bottom
        p = c.beginPath()
        p.moveTo(X(0), base)
        for i, (_, v) in enumerate(self.points):
            p.lineTo(X(i), Y(v))
        p.lineTo(X(n - 1), base)
        p.close()
        c.setFillColor(self.color)
        c.setFillAlpha(0.13)
        c.drawPath(p, stroke=0, fill=1)
        c.setFillAlpha(1)
        line = c.beginPath()
        for i, (_, v) in enumerate(self.points):
            (line.moveTo if i == 0 else line.lineTo)(X(i), Y(v))
        c.setStrokeColor(self.color); c.setLineWidth(1.1)
        c.drawPath(line, stroke=1, fill=0)
        years, last = [], None
        for i, (d, _) in enumerate(self.points):
            if d[:4] != last:
                years.append((i, d[:4]))
                last = d[:4]
        step = max(1, math.ceil(len(years) / 10))
        for k, (i, yr) in enumerate(years[1:]):
            if k % step == 0:
                self.text(X(i), 4, yr, 6.5, MUTED, anchor="center")


class YearBars(Chart):
    """Calendar-year returns, green up, red down."""

    def __init__(self, width, height, annual):
        super().__init__(width, height)
        self.annual = annual

    def draw(self):
        c = self.canv
        left, bottom, top = 40, 16, self.height - 12
        vals = [r for _, r, _ in self.annual]
        lo, hi = min(0, min(vals)), max(0, max(vals))
        ticks = _nice_ticks(lo, hi)
        lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
        Y = lambda v: bottom + (v - lo) / (hi - lo) * (top - bottom)
        for tk in ticks:
            c.setStrokeColor(GRID); c.setLineWidth(0.5)
            c.line(left, Y(tk), self.width, Y(tk))
            self.text(left - 4, Y(tk) - 2.5, F.fmt_pct(tk, 0), 6.5, MUTED, anchor="right")
        slot = (self.width - left) / len(self.annual)
        bw = slot * 0.6
        for i, (yr, r, partial) in enumerate(self.annual):
            x = left + slot * i + (slot - bw) / 2
            c.setFillColor(UP if r >= 0 else DOWN)
            if partial:
                c.setFillAlpha(0.45)
            c.rect(x, min(Y(0), Y(r)), bw, abs(Y(r) - Y(0)), stroke=0, fill=1)
            c.setFillAlpha(1)
            self.text(x + bw / 2, (Y(r) + 3) if r >= 0 else (Y(r) - 8), F.fmt_pct(r, 0, True), 6, INK, SANS_B, "center")
            self.text(x + bw / 2, 5, yr + ("*" if partial else ""), 6.5, MUTED, anchor="center")
        c.setStrokeColor(INK); c.setLineWidth(0.7)
        c.line(left, Y(0), self.width, Y(0))


class Heatmap(Chart):
    """Monthly returns: rows are years, columns months, colour by sign and size."""

    def __init__(self, width, height, monthly, month_names):
        super().__init__(width, height)
        self.monthly, self.months = monthly, month_names

    def draw(self):
        c = self.canv
        years = sorted({k[:4] for k in self.monthly}, reverse=True)
        left, top = 30, self.height - 12
        cw = (self.width - left) / 12
        rh = min(16, (top - 2) / max(len(years), 1))
        span = max([abs(v) for v in self.monthly.values()] + [0.01])
        for j, m in enumerate(self.months):
            self.text(left + cw * (j + 0.5), top + 3, m, 6.5, MUTED, anchor="center")
        for i, yr in enumerate(years):
            yy = top - rh * (i + 1)
            self.text(0, yy + rh / 2 - 2.5, yr, 7, INK)
            for j in range(12):
                v = self.monthly.get(f"{yr}-{j + 1:02d}")
                if v is None:
                    continue
                k = min(1.0, abs(v) / span) ** 0.6
                base = (15, 138, 95) if v >= 0 else (200, 50, 60)
                col = colors.Color(*(1 - k * (1 - ch / 255) for ch in base))
                c.setFillColor(col)
                c.rect(left + cw * j + 0.6, yy + 0.6, cw - 1.2, rh - 1.2, stroke=0, fill=1)
                self.text(left + cw * (j + 0.5), yy + rh / 2 - 2.3, F.fmt_pct(v, 1, True), 5.6,
                          colors.white if k > 0.55 else INK, anchor="center")


# ---------------------------------------------------------------- sections

class SeriesBars(Chart):
    """One amount over several periods: fiscal years, then the latest interim period and its comparative."""

    def __init__(self, width, height, items, fmt):
        super().__init__(width, height)
        self.items, self.fmt = items, fmt            # [(label, value, is_interim)]

    def draw(self):
        c = self.canv
        left, bottom, top = 46, 24, self.height - 12
        vals = [v for _, v, _ in self.items]
        lo, hi = min(0, min(vals)), max(0, max(vals))
        ticks = _nice_ticks(lo, hi)
        lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
        y = lambda v: bottom + (v - lo) / (hi - lo) * (top - bottom)
        for tk in ticks:
            c.setStrokeColor(GRID); c.setLineWidth(0.5)
            c.line(left, y(tk), self.width, y(tk))
            self.text(left - 4, y(tk) - 2.5, self.fmt(tk), 6.5, MUTED, anchor="right")
        n = len(self.items)
        gap = 14 if any(i for *_, i in self.items) and not all(i for *_, i in self.items) else 0
        slot = (self.width - left - gap) / n
        bw = min(34, slot * 0.6)
        prev_interim = None
        x0 = left
        last_annual = max((i for i, (*_, it) in enumerate(self.items) if not it), default=-1)
        for i, (label, v, interim) in enumerate(self.items):
            if prev_interim is False and interim:
                x0 += gap
                c.setStrokeColor(LINE_SOFT); c.setDash(2, 2)
                c.line(x0 - gap / 2, bottom - 4, x0 - gap / 2, top)
                c.setDash()
            prev_interim = interim
            cx = x0 + slot * 0.5
            y0, y1 = y(0), y(v)
            c.setFillColor(PINK if interim and i == n - 1 else CYAN if interim else BLUE if i == last_annual else PRIOR)
            c.rect(cx - bw / 2, min(y0, y1), bw, abs(y1 - y0), stroke=0, fill=1)
            self.text(cx, max(y0, y1) + 3, self.fmt(v), 6.5, INK, SANS_B, "center")
            # long period names on two lines: "Esercizio" / "2025", "1° sem." / "2026"
            words = label.rsplit(" ", 1)
            if len(words) == 2 and self.canv.stringWidth(label, SANS, 6.8) > slot - 4:
                self.text(cx, 11, words[0], 6.3, MUTED, anchor="center")
                self.text(cx, 3, words[1], 6.8, INK, anchor="center")
            else:
                self.text(cx, 7, label, 6.8, INK, anchor="center")
            x0 += slot
        c.setStrokeColor(INK); c.setLineWidth(0.7)
        c.line(left, y(0), self.width, y(0))


def trend_section(a: dict, width: float, h3) -> list:
    """Revenue and net income over the periods the document prints: years, then the latest interim pair."""
    fin = a.get("fin") or {}
    series = fin.get("series") or {}
    periods = (fin.get("periods") or {}).get("flow") or []
    money = _money_fmt(fin.get("currency", ""))
    out = []
    for key, title in (("revenue", t("Ricavi nel tempo", "Revenue over time")), ("net_income", t("Risultato netto nel tempo", "Net income over time"))):
        pts = series.get(key) or []
        annual = [p for p in pts if p.get("months") == 12][-5:]
        interim = [p for p in pts if p.get("months") not in (12, None) and p["label"] in periods[:2]]
        interim.sort(key=lambda p: p["end"])
        items = [(p["label"], p["value"], False) for p in annual] + [(p["label"], p["value"], True) for p in interim]
        if len(items) >= 3:
            out.append([h3(title), SeriesBars((width - 12) / 2, 150, items, money)])
    if len(out) == 2:
        return [_pair(out[0], out[1], width), Spacer(1, 6)]
    return [x for part in out for x in (KeepTogether(part), Spacer(1, 6))]


def _money_fmt(cur: str):
    return lambda v: F.fmt_money(v, cur)


def _pair(left_flow, right_flow, width, gap=12):
    tbl = Table([[left_flow, right_flow]], colWidths=[(width - gap) / 2 + gap, (width - gap) / 2])
    tbl.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), gap),
                             ("RIGHTPADDING", (1, 0), (1, 0), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return tbl


def financial_section(a: dict, width: float, h3) -> list:
    fin = a.get("fin")
    if not fin:
        return []
    m, d, cur = fin["metrics"], fin["derived"], fin["currency"]
    years = [str(y) for y in fin.get("years") or [t("Corrente", "Current"), t("Precedente", "Prior")]]
    money = _money_fmt(cur)
    val = lambda k, w="cur": (m.get(k) or {}).get(w)
    out = []

    items = [(lbl, val(k), val(k, "prev")) for k, lbl in (("revenue", t("Ricavi", "Revenue")), ("gross_profit", t("Margine lordo", "Gross profit")),
                                                         ("operating_income", t("Utile operativo", "Operating inc.")),
                                                         ("net_income", t("Utile netto", "Net income")), ("cfo", t("Cassa operativa", "Operating CF")))
             if val(k) is not None]
    if d["cur"].get("fcf") is not None:
        items.append(("Free cash flow", d["cur"]["fcf"], d["prev"].get("fcf")))
    if len(items) >= 2:
        out += [KeepTogether([h3(t(f"Risultati: {years[0]} e {years[1]}", f"Results: {years[0]} vs {years[1]}")),
                              GroupedBars(width, 150, items, years, money)]), Spacer(1, 6)]

    margins = [(lbl, d["cur"].get(k), d["prev"].get(k)) for k, lbl in (
        ("gross_margin", t("Margine lordo", "Gross margin")), ("operating_margin", t("Margine operativo", "Operating margin")),
        ("net_margin", t("Margine netto", "Net margin")), ("fcf_margin", t("Margine FCF", "FCF margin")),
        ("rnd_ratio", t("R&S / ricavi", "R&D / revenue"))) if d["cur"].get(k) is not None]
    half = (width - 12) / 2
    left = right = None
    if margins:
        left = [h3(t("Margini", "Margins")), MarginBars(half, 22 + 26 * len(margins), margins, years)]
    ta, ca, tl, cl, eq = val("total_assets"), val("current_assets"), d["cur"].get("total_liabilities"), val("current_liabilities"), val("equity")
    stock_years = [str(y) for y in ((fin.get("periods") or {}).get("stock") or years)]
    if ta and eq is not None and (eq < 0 or val("temp_equity") is not None):
        # a deficit or redeemable preferred stock does not stack: compare the blocks side by side
        items = [(lbl, val(k), val(k, "prev")) for k, lbl in (
            ("total_assets", t("Attivo", "Assets")), ("total_liabilities", t("Passivo", "Liabilities")),
            ("temp_equity", t("Privilegiate", "Redeemable pref.")), ("equity", t("Patrimonio netto", "Equity"))) if val(k) is not None]
        right = [h3(t("Stato patrimoniale", "Balance sheet")), GroupedBars((width - 12) / 2, max(160, 22 + 26 * len(margins)), items, stock_years, money)]
    elif ta and eq is not None:
        cols = []
        for w, yr in (("cur", stock_years[0]), ("prev", stock_years[1] if len(stock_years) > 1 else "")):
            a_, c_, l_, cl_, e_ = val("total_assets", w), val("current_assets", w), d[w].get("total_liabilities"), val("current_liabilities", w), val("equity", w)
            if not a_ or e_ is None:
                continue
            cols.append((t("Attivo", "Assets") + "\n" + yr, [(t("Attivo corrente", "Current assets"), c_ or 0, CYAN),
                                                       (t("Attivo non corrente", "Non-current assets"), a_ - (c_ or 0), BLUE)]))
            if l_ is not None:
                cols.append((t("Passivo e PN", "Liab. & equity") + "\n" + yr,
                             [(t("Passivo corrente", "Current liabilities"), cl_ or 0, AMBER),
                              (t("Passivo non corrente", "Non-current liabilities"), l_ - (cl_ or 0), colors.HexColor("#e07a2f")),
                              (t("Patrimonio netto", "Equity"), e_, VIOLET)]))
        if cols:
            right = [h3(t("Stato patrimoniale", "Balance sheet")), BalanceStack(half, max(160, 22 + 26 * len(margins)), cols, money)]
    if left and right:
        out += [_pair(left, right, width), Spacer(1, 6)]
    else:
        for part in (left, right):
            if part:
                out += [KeepTogether(part), Spacer(1, 6)]

    cfo, capex = val("cfo"), val("capex")
    if cfo is not None and capex is not None:
        steps = [(t("Cassa operativa", "Operating CF"), cfo, "total"), ("Capex", -abs(capex), "delta"),
                 ("Free cash flow", cfo - abs(capex), "total")]
        if val("buybacks"):
            steps.append((t("Riacquisti", "Buybacks"), -abs(val("buybacks")), "delta"))
        if val("dividends"):
            steps.append((t("Dividendi", "Dividends"), -abs(val("dividends")), "delta"))
        if len(steps) > 3:
            steps.append((t("Restante", "Remaining"), cfo - abs(capex) - abs(val("buybacks") or 0) - abs(val("dividends") or 0), "total"))
        out += [KeepTogether([h3(t("Dove va la cassa", "Where the cash goes")), Waterfall(width, 140, steps, money)]), Spacer(1, 6)]
    return out


def ratios_rows(a: dict) -> list:
    """(label, current, prior, change) for the ratio table."""
    fin = a.get("fin")
    if not fin:
        return []
    d = fin["derived"]
    pct = lambda v: F.fmt_pct(v) if v is not None else "—"
    times = lambda v: (F._it(f"{v:.1f}") + "x") if v is not None else "—"
    rows = []
    for k, lbl, fmt, is_pct in (
            ("gross_margin", t("Margine lordo", "Gross margin"), pct, True),
            ("operating_margin", t("Margine operativo", "Operating margin"), pct, True),
            ("net_margin", t("Margine netto", "Net margin"), pct, True),
            ("fcf_margin", t("Margine free cash flow", "Free cash flow margin"), pct, True),
            ("rnd_ratio", t("R&S su ricavi", "R&D to revenue"), pct, True),
            ("tax_rate", t("Aliquota fiscale effettiva", "Effective tax rate"), pct, True),
            ("interest_coverage", t("Copertura interessi", "Interest coverage"), times, False),
            ("current_ratio", "Current ratio", times, False),
            ("debt_to_assets", t("Debito / attivo", "Debt to assets"), pct, True),
            ("equity_multiplier", t("Attivo / patrimonio netto", "Assets to equity"), times, False),
            ("return_pct_fcf", t("FCF restituito agli azionisti", "FCF returned to shareholders"), pct, True),
            ("sbc_pct_fcf", t("Compensi in azioni / FCF", "Stock comp. to FCF"), pct, True)):
        cur, prev = d["cur"].get(k), d["prev"].get(k)
        if cur is None:
            continue
        if prev is None:
            chg = ""
        elif is_pct:
            delta = (cur - prev) * 100
            chg = ("+" if delta >= 0 else "-") + F._it(f"{abs(delta):.1f}") + t(" pt", " pt")
        else:
            delta = cur - prev
            chg = ("+" if delta >= 0 else "-") + F._it(f"{abs(delta):.1f}") + "x"
        rows.append((lbl, fmt(cur), fmt(prev) if prev is not None else "—", chg))
    return rows


def market_section(a: dict, width: float, h3) -> list:
    sr = a.get("series")
    if not sr:
        return []
    from .market import _price, months
    out = []
    cur = sr.get("currency", "")
    if sr.get("points"):
        top = max(v for _, v in sr["points"])
        axis = (lambda v: F.fmt_num(v, 0)) if top >= 100 else (lambda v: F.fmt_num(v, 2)) if top >= 1 else (lambda v: _price(v))
        out += [KeepTogether([h3(t("Andamento del prezzo", "Price history") + (f" ({cur})" if cur else "")),
                              LineArea(width, 150, sr["points"], axis)]), Spacer(1, 6)]
    half = (width - 12) / 2
    left = right = None
    if sr.get("annual"):
        left = [h3(t("Rendimenti per anno solare", "Calendar-year returns")), YearBars(half, 140, sr["annual"])]
    if sr.get("drawdown"):
        right = [h3(t("Drawdown dal massimo", "Drawdown from the high")),
                 LineArea(half, 140, sr["drawdown"], lambda v: F.fmt_pct(v, 0), color=DOWN, zero_top=True)]
    if left and right:
        out += [_pair(left, right, width), Spacer(1, 6)]
    if sr.get("monthly"):
        nyears = len({k[:4] for k in sr["monthly"]})
        out += [KeepTogether([h3(t("Rendimenti mensili", "Monthly returns")), Heatmap(width, 16 + 15 * nyears, sr["monthly"], months())]),
                Spacer(1, 6)]
    return out


def market_stats_rows(a: dict) -> list:
    sr = a.get("series") or {}
    st = sr.get("stats") or {}
    rows = []
    pc = lambda v: F.fmt_pct(v, 1, signed=True) if v is not None else "—"
    if st.get("ytd") is not None:
        rows.append((t("Da inizio anno", "Year to date"), pc(st["ytd"]), ""))
    for key in ("1m", "1y", "3y", "5y", "10y"):
        h = (st.get("horizon") or {}).get(key)
        if h:
            rows.append((t("Rendimento ", "Return ") + h[0], pc(h[1]), (t("annuo ", "annualised ") + pc(h[2])) if h[2] is not None and key not in ("1m", "1y") else ""))
    if st.get("vol") is not None:
        rows.append((t("Volatilità annualizzata", "Annualised volatility"), F.fmt_pct(st["vol"]), ""))
    if st.get("max_dd") is not None:
        rows.append((t("Massimo drawdown", "Maximum drawdown"), pc(st["max_dd"]), ""))
    if st.get("from_ath") is not None:
        rows.append((t("Distanza dal massimo storico", "From the all-time high"), pc(st["from_ath"]), ""))
    if st.get("pos_months") is not None:
        rows.append((t("Mesi positivi", "Positive months"), F.fmt_pct(st["pos_months"], 0), ""))
    return rows
