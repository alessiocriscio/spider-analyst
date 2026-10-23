"""Price history -> a generated "market sheet" document the spider can read.

For instruments without a financial statement (crypto, indices, currencies,
commodities, ETFs, funds) the document is built from daily prices: a chart,
calendar-year and monthly returns, volatility and drawdowns. Every number is a
tagged figure (data-f) exactly like the facts of an iXBRL filing.
"""
from __future__ import annotations

import html
import math
from datetime import date

from .financials import _it, art, fmt_pct

MONTHS = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
TYPE_IT = {"CRYPTOCURRENCY": "Criptovaluta", "EQUITY": "Azione", "ETF": "ETF", "MUTUALFUND": "Fondo", "INDEX": "Indice",
           "CURRENCY": "Valuta", "FUTURE": "Future / materia prima", "MONEYMARKET": "Monetario"}


def _price(v: float, cur: str = "") -> str:
    dec = 2 if v >= 1 else 4 if v >= 0.01 else 8
    s = _it(f"{v:,.{dec}f}")
    return f"{s} {cur}".strip()


class Sheet:
    """Accumulates figures and headings while the HTML is written."""

    def __init__(self):
        self.facts: list[dict] = []
        self.headings: list[dict] = []
        self.page = 1

    def f(self, label: str, value: float, display: str, kind: str = "pct", col: str = "Valore", cls: str = "") -> str:
        fid = len(self.facts)
        self.facts.append({"id": fid, "label": label, "value": value, "display": display, "page": self.page, "kind": kind, "col": col})
        c = "xf" + (f" {cls}" if cls else "")
        return f'<span class="{c}" data-f="{fid}">{html.escape(display)}</span>'

    def h(self, text: str, tag: str = "h2") -> str:
        hid = len(self.headings)
        self.headings.append({"id": hid, "text": text, "page": self.page})
        return f'<{tag} data-h="{hid}">{html.escape(text)}</{tag}>'


def _returns(points):
    return [(points[i][0], points[i][1] / points[i - 1][1] - 1) for i in range(1, len(points)) if points[i - 1][1] > 0]


def _periods_per_year(points) -> float:
    d0, d1 = date.fromisoformat(points[0][0]), date.fromisoformat(points[-1][0])
    years = max((d1 - d0).days / 365.25, 1 / 12)
    return min(max((len(points) - 1) / years, 50), 366)


def _drawdown(points):
    peak, peak_d = points[0][1], points[0][0]
    worst, w_peak, w_trough = 0.0, points[0][0], points[0][0]
    series = []
    for d, v in points:
        if v > peak:
            peak, peak_d = v, d
        dd = v / peak - 1
        series.append((d, dd))
        if dd < worst:
            worst, w_peak, w_trough = dd, peak_d, d
    recovered = None
    if worst < 0:
        pk = next(v for d, v in points if d == w_peak)
        recovered = next((d for d, v in points if d > w_trough and v >= pk), None)
    return worst, w_peak, w_trough, recovered, series


def _last_by(points, keyf):
    out = {}
    for d, v in points:
        out[keyf(d)] = (d, v)
    return out


def _svg_line(series, w=720, h=260, color="#ff3d8b", fill=True, zero=False, fmt=lambda v: _it(f"{v:,.0f}")):
    vals = [v for _, v in series]
    lo, hi = min(vals), max(vals)
    if zero:
        hi = max(hi, 0)
    if hi == lo:
        hi = lo + 1
    pad = 70
    n = len(series)
    step = max(1, n // 600)
    pts = []
    for i in range(0, n, step):
        x = pad + (w - pad - 8) * i / max(n - 1, 1)
        y = 8 + (h - 30) * (1 - (series[i][1] - lo) / (hi - lo))
        pts.append(f"{x:.1f},{y:.1f}")
    path = " ".join(pts)
    area = f'<polygon points="{pad},{h - 22} {path} {w - 8},{h - 22}" fill="{color}" opacity="0.12"/>' if fill else ""
    ticks = ""
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        y = 8 + (h - 30) * (1 - k / 4)
        ticks += f'<line x1="{pad}" x2="{w - 8}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e5e5e5"/><text x="{pad - 4}" y="{y + 4:.1f}" text-anchor="end">{html.escape(fmt(v))}</text>'
    years, last = "", None
    for i, (d, _) in enumerate(series):
        if d[:4] != last and i > 0:
            x = pad + (w - pad - 8) * i / max(n - 1, 1)
            years += f'<text x="{x:.1f}" y="{h - 6}" text-anchor="middle">{d[:4]}</text>'
        last = d[:4]
    if years.count("<text") > 12:          # long history: label every few years
        keep = years.split("</text>")
        k = math.ceil(len(keep) / 10)
        years = "</text>".join(t for j, t in enumerate(keep) if j % k == 0 or not t.strip())
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" class="chart">{ticks}{area}'
            f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="1.8"/>{years}</svg>')


def build(hist: dict, now: date | None = None) -> dict:
    pts = hist["points"]
    cur = hist.get("currency", "")
    name, sym = hist.get("name") or hist["symbol"], hist["symbol"]
    typ = TYPE_IT.get((hist.get("type") or "").upper(), hist.get("type") or "Strumento")
    S = Sheet()
    last_d, last_v = pts[-1]
    rets = _returns(pts)
    ppy = _periods_per_year(pts)
    logr = [math.log(1 + r) for _, r in rets if r > -1]
    vol = (sum((x - sum(logr) / len(logr)) ** 2 for x in logr) / max(len(logr) - 1, 1)) ** 0.5 * math.sqrt(ppy) if len(logr) > 2 else None
    worst, dd_peak, dd_trough, recovered, dd_series = _drawdown(pts)
    ath_v = max(v for _, v in pts)
    ath_d = next(d for d, v in pts if v == ath_v)
    from_ath = last_v / ath_v - 1
    last_dt = date.fromisoformat(last_d)

    def back(days):
        target = date.fromordinal(last_dt.toordinal() - days).isoformat()
        prev = [p for p in pts if p[0] <= target]
        return prev[-1] if prev and (date.fromisoformat(prev[-1][0]) - date.fromisoformat(target)).days > -10 else None

    horizon = {}
    for label, days in (("1 mese", 30), ("1 anno", 365), ("3 anni", 3 * 365), ("5 anni", 5 * 365), ("10 anni", 3652)):
        p = back(days)
        if p:
            tot = last_v / p[1] - 1
            yrs = days / 365.25
            horizon[label] = (tot, (1 + tot) ** (1 / yrs) - 1 if yrs >= 1 and tot > -1 else None)
    ytd_base = [p for p in pts if p[0] < f"{last_dt.year}-01-01"]
    ytd = last_v / ytd_base[-1][1] - 1 if ytd_base else None
    wk = [v for d, v in pts if d >= date.fromordinal(last_dt.toordinal() - 365).isoformat()]
    hi52, lo52 = max(wk), min(wk)

    # calendar years and months
    ye = _last_by(pts, lambda d: d[:4])
    me = _last_by(pts, lambda d: d[:7])
    years = sorted(ye)
    annual = []
    for i, y in enumerate(years):
        base = ye[years[i - 1]][1] if i else pts[0][1]
        partial = (i == 0 and pts[0][0][5:] > "01-10") or y == str(last_dt.year)
        annual.append((y, ye[y][1] / base - 1, partial))
    months = sorted(me)
    monthly = {}
    for i, mth in enumerate(months):
        base = me[months[i - 1]][1] if i else pts[0][1]
        if i == 0 and pts[0][0][8:] > "05":
            continue
        monthly[mth] = me[mth][1] / base - 1
    pos_months = sum(1 for v in monthly.values() if v > 0) / len(monthly) if monthly else None
    best_m = max(monthly.items(), key=lambda x: x[1]) if monthly else None
    worst_m = min(monthly.items(), key=lambda x: x[1]) if monthly else None
    full_years = [(y, r) for y, r, p in annual if not p]
    best_y = max(full_years, key=lambda x: x[1]) if full_years else None
    worst_y = min(full_years, key=lambda x: x[1]) if full_years else None

    def mlabel(m):
        return f"{MONTHS[int(m[5:7]) - 1]} {m[:4]}"

    def dlabel(d):
        return f"{int(d[8:10])} {MONTHS[int(d[5:7]) - 1]} {d[:4]}"

    pc = lambda v: fmt_pct(v, 1, signed=True)
    cls = lambda v: "pos" if v is not None and v >= 0 else "neg"
    pages = []

    # page 1: overview
    S.page = 1
    rows = [("Ultimo prezzo", S.f("Ultimo prezzo", last_v, _price(last_v, cur), "price")),
            ("Data", html.escape(dlabel(last_d)))]
    if ytd is not None:
        rows.append(("Da inizio anno", S.f("Rendimento da inizio anno", ytd, pc(ytd), cls=cls(ytd))))
    for label, (tot, ann) in horizon.items():
        cell = S.f(f"Rendimento {label}", tot, pc(tot), cls=cls(tot))
        if ann is not None and label != "1 anno":
            cell += f' <small>(annuo {S.f(f"Rendimento annuo {label}", ann, pc(ann), cls=cls(ann))})</small>'
        rows.append((f"Rendimento {label}", cell))
    rows.append(("Massimo 52 settimane", S.f("Massimo 52 settimane", hi52, _price(hi52, cur), "price")))
    rows.append(("Minimo 52 settimane", S.f("Minimo 52 settimane", lo52, _price(lo52, cur), "price")))
    rows.append(("Massimo storico", S.f("Massimo storico", ath_v, _price(ath_v, cur), "price") + f" <small>({dlabel(ath_d)})</small>"))
    rows.append(("Distanza dal massimo", S.f("Distanza dal massimo storico", from_ath, pc(from_ath), cls=cls(from_ath))))
    p1 = (f'<div class="kicker">Scheda di mercato · {html.escape(typ)} · {html.escape(hist.get("exchange") or "")}</div>'
          + S.h(f"{name} ({sym})", "h1")
          + f'<p class="sub">Dati giornalieri dal {dlabel(pts[0][0])} al {dlabel(last_d)} · {len(pts):,} osservazioni · valuta {html.escape(cur or "n.d.")}</p>'.replace(",", ".")
          + S.h("Andamento del prezzo")
          + _svg_line(pts, fmt=lambda v: _price(v))
          + S.h("Dati principali")
          + "<table>" + "".join(f"<tr><td>{a}</td><td class='num'>{b}</td></tr>" for a, b in rows) + "</table>")
    pages.append(p1)

    # page 2: calendar-year returns
    S.page = 2
    trs = "".join(
        f"<tr><td>{y}{' <small>(parziale)</small>' if partial else ''}</td><td class='num'>{S.f(f'Rendimento {y}', r, pc(r), col='Anno', cls=cls(r))}</td></tr>"
        for y, r, partial in reversed(annual))
    p2 = S.h("Rendimenti per anno solare", "h1") + "<table><tr><th>Anno</th><th class='num'>Rendimento</th></tr>" + trs + "</table>"
    pages.append(p2)

    # page 3: monthly grid (last 8 years)
    S.page = 3
    yrs = sorted({m[:4] for m in monthly})[-8:]
    head = "<tr><th>Anno</th>" + "".join(f"<th>{m}</th>" for m in MONTHS) + "</tr>"
    body = ""
    for y in reversed(yrs):
        cells = ""
        for k in range(1, 13):
            key = f"{y}-{k:02d}"
            if key in monthly:
                v = monthly[key]
                cells += f"<td class='num'>{S.f(f'Rendimento {mlabel(key)}', v, fmt_pct(v, 1, True), col='Mese', cls=cls(v))}</td>"
            else:
                cells += "<td></td>"
        body += f"<tr><td>{y}</td>{cells}</tr>"
    p3 = S.h("Rendimenti mensili", "h1") + f"<table class='grid'>{head}{body}</table>"
    if pos_months is not None:
        p3 += (f"<p>Mesi positivi: {S.f('Mesi positivi', pos_months, fmt_pct(pos_months, 0))} su {len(monthly)}. "
               f"Mese migliore: {mlabel(best_m[0])} ({S.f('Mese migliore', best_m[1], pc(best_m[1]), cls='pos')}); "
               f"peggiore: {mlabel(worst_m[0])} ({S.f('Mese peggiore', worst_m[1], pc(worst_m[1]), cls='neg')}).</p>")
    pages.append(p3)

    # page 4: risk
    S.page = 4
    risk_rows = []
    if vol is not None:
        risk_rows.append(("Volatilità annualizzata", S.f("Volatilità annualizzata", vol, fmt_pct(vol))))
    risk_rows.append(("Massimo drawdown", S.f("Massimo drawdown", worst, pc(worst), cls="neg")
                      + f" <small>({dlabel(dd_peak)} → {dlabel(dd_trough)})</small>"))
    risk_rows.append(("Recupero", html.escape(dlabel(recovered)) if recovered else "non ancora recuperato"))
    if best_y:
        risk_rows.append(("Anno migliore", f"{best_y[0]}: " + S.f("Anno migliore", best_y[1], pc(best_y[1]), cls="pos")))
        risk_rows.append(("Anno peggiore", f"{worst_y[0]}: " + S.f("Anno peggiore", worst_y[1], pc(worst_y[1]), cls=cls(worst_y[1]))))
    worst_day = min(rets, key=lambda x: x[1])
    best_day = max(rets, key=lambda x: x[1])
    risk_rows.append(("Giorno peggiore", f"{dlabel(worst_day[0])}: " + S.f("Giorno peggiore", worst_day[1], pc(worst_day[1]), cls="neg")))
    risk_rows.append(("Giorno migliore", f"{dlabel(best_day[0])}: " + S.f("Giorno migliore", best_day[1], pc(best_day[1]), cls="pos")))
    p4 = (S.h("Rischio", "h1") + S.h("Drawdown dal massimo precedente")
          + _svg_line(dd_series, color="#c0392b", zero=True, fmt=lambda v: fmt_pct(v, 0))
          + "<table>" + "".join(f"<tr><td>{a}</td><td class='num'>{b}</td></tr>" for a, b in risk_rows) + "</table>"
          + "<p class='note'>Rendimenti calcolati sui prezzi di chiusura rettificati (dividendi e frazionamenti inclusi quando disponibili). "
            "La volatilità usa i rendimenti logaritmici giornalieri. Fonte: Yahoo Finance.</p>")
    pages.append(p4)

    # findings and card
    finds = []
    if "1 anno" in horizon:
        t = horizon["1 anno"][0]
        finds.append({"text": f"{sym} {'ha guadagnato' if t >= 0 else 'ha perso'} {art(fmt_pct(abs(t)), False)} nell'ultimo anno.", "pages": [1]})
    if vol is not None:
        finds.append({"text": f"Volatilità annualizzata {art(fmt_pct(vol))}" + (": oscillazioni molto ampie." if vol > 0.5 else "."), "pages": [4]})
    finds.append({"text": f"Il calo massimo dal picco è stato {art(fmt_pct(abs(worst)))} ({dlabel(dd_peak)} → {dlabel(dd_trough)}), "
                          + (f"recuperato il {dlabel(recovered)}." if recovered else "non ancora recuperato."), "pages": [4]})
    if from_ath < -0.05:
        finds.append({"text": f"Il prezzo è inferiore {art(fmt_pct(abs(from_ath)))} al massimo storico ({dlabel(ath_d)}).", "pages": [1]})
    else:
        finds.append({"text": f"Il prezzo è vicino al massimo storico ({dlabel(ath_d)}).", "pages": [1]})
    if best_y:
        finds.append({"text": f"Anno migliore {best_y[0]} ({pc(best_y[1])}), peggiore {worst_y[0]} ({pc(worst_y[1])}).", "pages": [2]})
    if pos_months is not None:
        finds.append({"text": f"Mesi in positivo: {fmt_pct(pos_months, 0)} su {len(monthly)} mesi osservati.", "pages": [3]})
    for k in ("5 anni", "10 anni"):
        if k in horizon and horizon[k][1] is not None:
            finds.append({"text": f"Rendimento annuo composto a {k}: {pc(horizon[k][1])}.", "pages": [1]})
            break

    tiles = [{"key": "price", "it": "Ultimo prezzo", "en": "Last price", "display": _price(last_v, cur), "yoy_display": "", "pages": [1]}]
    if "1 anno" in horizon:
        tiles.append({"key": "r1y", "it": "Rendimento 1 anno", "en": "1-year return", "display": pc(horizon["1 anno"][0]), "yoy_display": "", "pages": [1]})
    if vol is not None:
        tiles.append({"key": "vol", "it": "Volatilità annua", "en": "Volatility", "display": fmt_pct(vol), "yoy_display": "", "pages": [4]})
    tiles.append({"key": "mdd", "it": "Max drawdown", "en": "Max drawdown", "display": pc(worst), "yoy_display": "", "pages": [4]})

    key_labels = {"Ultimo prezzo", "Rendimento 1 anno", "Volatilità annualizzata", "Massimo drawdown", "Rendimento da inizio anno",
                  "Distanza dal massimo storico"}
    for f in S.facts:
        f["key"] = f["label"] in key_labels
    checks = [{"name": "Prezzi giornalieri senza buchi oltre 10 giorni", "ok": _gaps_ok(pts), "pages": [1], "detail": ""},
              {"name": "Rendimenti mensili composti = rendimento annuo", "ok": _months_consistent(annual, monthly), "pages": [2, 3], "detail": ""}]
    return {
        "title": f"{name} ({sym})",
        "subtitle": f"{typ} · scheda di mercato al {dlabel(last_d)}",
        "currency": cur,
        "pages": pages,
        "facts": S.facts,
        "headings": S.headings,
        "findings": finds,
        "card": tiles,
        "checks": checks,
    }


def _gaps_ok(pts) -> bool:
    ds = [date.fromisoformat(d) for d, _ in pts]
    return all((b - a).days <= 10 for a, b in zip(ds, ds[1:]))


def _months_consistent(annual, monthly) -> bool:
    for y, r, partial in annual:
        ms = [v for k, v in monthly.items() if k.startswith(y)]
        if partial or len(ms) != 12:
            continue
        prod = 1.0
        for v in ms:
            prod *= 1 + v
        if abs(prod - 1 - r) > 1e-6:
            return False
    return True


CSS = """
.sheet h1{font:700 30px/1.15 Georgia,serif;margin:6px 0 10px}
.sheet h2{font:700 19px/1.2 Georgia,serif;margin:28px 0 10px;color:#222}
.sheet .kicker{font:500 13px system-ui;color:#888}
.sheet .sub{color:#666;margin:0 0 8px}
.sheet table{border-collapse:collapse;width:100%;font:14px/1.4 system-ui,sans-serif}
.sheet td,.sheet th{border-bottom:1px solid #eee;padding:6px 8px;text-align:left}
.sheet .num{text-align:right;font-variant-numeric:tabular-nums}
.sheet .grid td,.sheet .grid th{font-size:12px;padding:5px 4px;text-align:right}
.sheet .grid td:first-child,.sheet .grid th:first-child{text-align:left}
.sheet .pos{color:#13804b}.sheet .neg{color:#c0392b}
.sheet small{color:#888}
.sheet .note{color:#888;font-size:12px;margin-top:20px}
.sheet .chart{display:block;max-width:100%;height:auto;font:11px system-ui;fill:#999}
"""
