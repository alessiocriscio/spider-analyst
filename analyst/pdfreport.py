"""The downloadable report as a PDF, drawn directly with reportlab (no browser needed).

Same look as the app (in the theme chosen there): a summary card with the headline
figures and what they are compared with, the AI's summary, the key findings, a
table of financial highlights, charts over time, what the AI understood section by
section, ratios, the arithmetic checks that were possible, and how it was read.
No pages of raw figures: every number shown is there because it says something.
"""
from __future__ import annotations

import io
import threading
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (CondPageBreak, Flowable, ListFlowable, ListItem, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from . import charts
from .i18n import t, using

INK, MUTED, LINE, PINK, BLUE, CYAN, UP, DOWN = (colors.HexColor(c) for c in
                                                ("#1d1c26", "#6c6a7c", "#d6d4e0", "#ff2d8f", "#3b6cff", "#3fd4f5", "#0f8a5f", "#c8323c"))
ZEBRA = colors.HexColor("#fafafd")
ACCENT_HEX = "#ff2d8f"
LABELS: dict = {}                      # page number -> page number as printed, for the report being built
_LOCK = threading.Lock()
SERIF, SERIF_B, SANS, SANS_B = "Times-Roman", "Times-Bold", "Helvetica", "Helvetica-Bold"

# the standard PDF fonts cover Windows-1252 only
_SAFE = str.maketrans({"−": "-", "→": "->", "≈": "~", "✓": "", "✗": "", " ": " ", " ": " "})


def _x(s) -> str:
    return escape(str(s if s is not None else "").translate(_SAFE))


def _plist(pages) -> str:
    return ", ".join(str(LABELS.get(str(p)) or LABELS.get(p) or p) for p in pages)


def _pages(pages) -> str:
    if not pages:
        return ""
    return ("pp. " if len(pages) > 1 else "p. ") + _plist(pages)


def _tag(pages) -> str:
    return f' <font color="{ACCENT_HEX}" size="8"><b>{_x(_pages(pages))}</b></font>' if pages else ""


S = {
    "brand": ParagraphStyle("brand", fontName=SANS, fontSize=8.5, textColor=MUTED, leading=11),
    "title": ParagraphStyle("title", fontName=SERIF_B, fontSize=22, leading=25, textColor=INK),
    "sub": ParagraphStyle("sub", fontName=SANS, fontSize=8.5, leading=11, textColor=MUTED),
    "tl": ParagraphStyle("tl", fontName=SANS, fontSize=7.5, leading=9, textColor=MUTED),
    "tv": ParagraphStyle("tv", fontName=SANS_B, fontSize=15, leading=18, textColor=INK),
    "ty": ParagraphStyle("ty", fontName=SANS_B, fontSize=7.5, leading=9.5),
    "h2": ParagraphStyle("h2", fontName=SERIF_B, fontSize=14, leading=17, textColor=INK, spaceBefore=12, spaceAfter=2),
    "h3": ParagraphStyle("h3", fontName=SERIF_B, fontSize=11, leading=14, textColor=INK, spaceBefore=8, spaceAfter=3),
    "body": ParagraphStyle("body", fontName=SERIF, fontSize=10.5, leading=14, textColor=INK, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName=SANS, fontSize=9, leading=12, textColor=INK),
    "cell": ParagraphStyle("cell", fontName=SANS, fontSize=8.5, leading=10.5, textColor=INK),
    "foot": ParagraphStyle("foot", fontName=SANS, fontSize=7.5, leading=10, textColor=MUTED),
    "lead": ParagraphStyle("lead", fontName=SERIF, fontSize=12, leading=16.5, textColor=INK),
    "tx": ParagraphStyle("tx", fontName=SANS, fontSize=7, leading=9, textColor=MUTED),
    "group": ParagraphStyle("group", fontName=SANS_B, fontSize=8, leading=10, textColor=INK),
}


class Rule(Flowable):
    def __init__(self, width, thick=1.4, color=INK):
        super().__init__()
        self.width, self.thick, self.color = width, thick, color
        self.height = thick + 6

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thick)
        self.canv.line(0, 5, self.width, 5)


class Card(Flowable):
    """Black-bordered card with the pink offset shadow, holding a table."""

    def __init__(self, content: Table, width: float):
        super().__init__()
        self.content, self.width = content, width
        self.pad = 12

    def wrap(self, aw, ah):
        _, h = self.content.wrapOn(self.canv, self.width - 2 * self.pad - 5, ah)
        self.height = h + 2 * self.pad + 5
        return self.width, self.height

    def draw(self):
        c, w, h = self.canv, self.width - 5, self.height - 5
        c.setFillColor(PINK)
        c.roundRect(5, 0, w, h, 7, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setStrokeColor(INK)
        c.setLineWidth(1.6)
        c.roundRect(0, 5, w, h, 7, stroke=1, fill=1)
        self.content.drawOn(c, self.pad, 5 + self.pad)


def _spider_icon(c, x, y):
    c.saveState()
    c.setStrokeColor(CYAN)
    c.setLineWidth(0.8)
    for sx in (-1, 1):
        for i, (dx, dy) in enumerate(((7, 4), (8, 1), (8, -3), (6, -6))):
            hx, hy = x, y + 3 - i * 2.2
            kx, ky = hx + sx * dx * 0.6, hy + 3
            fx, fy = hx + sx * dx, hy + dy - 3
            c.line(hx, hy, kx, ky)
            c.line(kx, ky, fx, fy)
            c.setFillColor(PINK)
            c.circle(fx, fy, 0.7, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#0b0d12"))
    c.setStrokeColor(BLUE)
    c.roundRect(x - 2, y - 6, 4, 11, 1, stroke=1, fill=1)
    c.setFillColor(colors.HexColor("#4fe3ff"))
    c.circle(x, y - 7.5, 1.3, stroke=0, fill=1)
    c.restoreState()


def build(a: dict, theme: str = "neon") -> bytes:
    from . import themes
    lang = a.get("lang") or "en"
    with _LOCK, using(lang):              # colours and page labels are module state while one report is drawn
        themes.apply(theme)
        LABELS.clear()
        LABELS.update({str(k): v for k, v in (a.get("page_labels") or {}).items()})
        try:
            return _build(a, lang)
        finally:
            LABELS.clear()


class Lead(Flowable):
    """The AI's summary: a paragraph on a soft background with an accent bar."""

    def __init__(self, para: Paragraph, width: float):
        super().__init__()
        self.para, self.width = para, width

    def wrap(self, aw, ah):
        _, h = self.para.wrap(self.width - 26, ah)
        self.height = h + 20
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(colors.HexColor("#f6f5fa"))
        c.roundRect(0, 0, self.width, self.height, 6, stroke=0, fill=1)
        c.setFillColor(PINK)
        c.rect(0, 0, 4, self.height, stroke=0, fill=1)
        self.para.drawOn(c, 16, 10)


HIGHLIGHTS = (
    (("Conto economico", "Income statement"), "flow",
     ("revenue", "cost_of_revenue", "gross_profit", "rnd", "opex_total", "operating_income", "pretax_income", "income_tax", "net_income", "eps_diluted")),
    (("Stato patrimoniale", "Balance sheet"), "stock",
     ("cash", "current_assets", "total_assets", "current_liabilities", "total_liabilities", "temp_equity", "equity")),
    (("Flussi di cassa", "Cash flows"), "flow", ("cfo", "capex", "fcf", "cfi", "cff", "cash_change", "sbc")),
)


def _highlights(a: dict, W: float):
    """Income statement, balance sheet and cash flow at a glance: the latest period against its comparative."""
    from . import financials as F
    fin = a.get("fin") or {}
    m, cur = fin.get("metrics") or {}, fin.get("currency", "")
    if len(m) < 3:
        return None
    per = fin.get("periods") or {}
    flow = per.get("flow") or [str(y) for y in fin.get("years") or ["", ""]]
    stock = per.get("stock") or flow
    d = fin.get("derived") or {}
    widths = [W - 4 * 62 - 44, 62, 62, 62, 44 + 62]
    data, style = [], []
    for (name, kind, keys) in HIGHLIGHTS:
        rows = []
        for k in keys:
            if k == "fcf":
                c, p = (d.get("cur") or {}).get("fcf"), (d.get("prev") or {}).get("fcf")
                lbl, pages = t("Free cash flow (calcolato)", "Free cash flow (computed)"), [x for x in ((m.get("cfo") or {}).get("page"),) if x]
                fmt = lambda v: F.fmt_money(v, cur)
            elif k in m:
                c, p, pages = m[k]["cur"], m[k]["prev"], [m[k]["page"]]
                lbl = F.label(k)
                if k == "net_income" and c is not None and c < 0:
                    lbl = t("Perdita netta", "Net loss")
                fmt = (lambda v, k=k: F.fmt_value(k, v, cur))
            else:
                continue
            if c is None:
                continue
            if p is None or p == 0:
                chg, col = "", INK
            elif (c < 0) != (p < 0) or p < 0:
                chg, col = "n/m", MUTED
            else:
                g = (c - p) / abs(p)
                chg, col = F.fmt_pct(g, signed=True), (UP if g >= 0 else DOWN)
            rows.append([Paragraph(_x(lbl), S["cell"]), Paragraph(f"<para alignment='right'><b>{_x(fmt(c))}</b></para>", S["cell"]),
                         Paragraph(f"<para alignment='right'>{_x(fmt(p)) if p is not None else '—'}</para>", S["cell"]),
                         Paragraph(f"<para alignment='right'><font color='#{col.hexval()[2:]}'>{_x(chg)}</font></para>", S["cell"]),
                         Paragraph(f"<para alignment='right'>{_tag(pages)}</para>", S["cell"])])
        if not rows:
            continue
        labels = stock if kind == "stock" else flow
        r0 = len(data)
        data.append([Paragraph(_x(t(*name)), S["group"])] +
                     [Paragraph(f"<para alignment='right'><font color='#6c6a7c'>{_x(h)}</font></para>", S["tx"])
                      for h in (labels[0] if labels else "", labels[1] if len(labels) > 1 else "", t("Variazione", "Change"), "")])
        style += [("LINEBELOW", (0, r0), (-1, r0), 0.8, INK), ("TOPPADDING", (0, r0), (-1, r0), 8 if r0 else 2)]
        data += rows
    if not data:
        return None
    tbl = Table(data, colWidths=widths)
    tbl.setStyle(TableStyle(style + [("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#ecebf2")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                                     ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]))
    return tbl


def _build(a: dict, lang: str) -> bytes:
    from . import financials as F
    buf = io.BytesIO()
    W = A4[0] - 28 * mm
    today = date.today()
    from .market import months
    mn = months()
    today_s = t(f"{today.day} {mn[today.month - 1]} {today.year}", f"{mn[today.month - 1]} {today.day}, {today.year}")

    def first_page(c, doc):
        _spider_icon(c, 14 * mm + 6, A4[1] - 14 * mm - 6)
        c.setFont(SANS_B, 8.5)
        c.setFillColor(INK)
        c.drawString(14 * mm + 18, A4[1] - 14 * mm - 9, "Spider Analyst")
        c.setFont(SANS, 8.5)
        c.setFillColor(MUTED)
        c.drawString(14 * mm + 84, A4[1] - 14 * mm - 9, f"·  {t('Report', 'Report')}  ·  {today_s}")
        later_pages(c, doc)

    def later_pages(c, doc):
        c.setFont(SANS, 7.5)
        c.setFillColor(MUTED)
        c.drawRightString(A4[0] - 14 * mm, 9 * mm, f"{_x(a.get('title', ''))}  ·  {doc.page}")

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=24 * mm, bottomMargin=16 * mm,
                            title=f"{a.get('title', '')} — Spider Analyst", author="Spider Analyst")
    story = []

    # summary card: headline figures, what they are compared with, where they are printed
    tiles = []
    for tile in a.get("card", []):
        label = tile.get("en") if lang == "en" and tile.get("en") else tile.get("it")
        cell = [Paragraph(_x(label), S["tl"]), Paragraph(_x(tile.get("display")), S["tv"])]
        if tile.get("exact"):
            cell.append(Paragraph(_x(tile["exact"]), S["tl"]))
        yoy, vs = tile.get("yoy_display") or "", tile.get("vs") or ""
        if yoy:
            col = "#0f8a5f" if yoy.startswith("+") else "#c8323c"
            cell.append(Paragraph(f'<font color="{col}">{_x(yoy)}</font> <font color="#6c6a7c">{_x(("vs " + vs) if vs else t("sull’anno", "year on year"))}</font>', S["ty"]))
        elif tile.get("prev_display"):
            cell.append(Paragraph(f'<font color="#6c6a7c">{_x(t("era", "was"))} {_x(tile["prev_display"])}{_x(" (" + vs + ")" if vs else "")}</font>', S["ty"]))
        if tile.get("note"):
            cell.append(Paragraph(f"<i>{_x(tile['note'])}</i>", S["tl"]))
        if tile.get("pages"):
            cell.append(Paragraph(_tag(tile["pages"]), S["tl"]))
        tiles.append(cell)
    inner_w = W - 2 * 12 - 5
    rows = [[Paragraph(_x(a.get("title")), S["title"])], [Paragraph(_x(a.get("subtitle")), S["sub"])], [Spacer(1, 8)]]
    if tiles:
        n = len(tiles)
        gap = 6
        tw = (inner_w - gap * (n - 1)) / n
        cells, widths = [], []
        for i, tl in enumerate(tiles):
            one = Table([[tl]], colWidths=[tw])
            one.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                                     ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
            cells.append(one)
            widths.append(tw)
            if i < n - 1:
                cells.append("")
                widths.append(gap)
        row = Table([cells], colWidths=widths)
        row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                 ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                 ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        rows.append([row])
    checks = a.get("checks", [])
    passed = sum(1 for c in checks if c.get("ok"))
    nfig = len(a.get("facts", {}))
    left_note = f"<b>{nfig}</b> {t('cifre lette', 'figures read')} · " + (
        f"<b>{passed}</b> {t('controlli superati su', 'checks passed out of')} {len(checks)}" if checks else
        t("nessun controllo aritmetico possibile su queste cifre", "no arithmetic check possible on these figures"))
    ai_note = (t("Testi di {p}; ogni numero citato è confrontato con il documento", "Text by {p}; every number it cites is matched to the document")
               .format(p=a.get("ai_provider") or "AI") if a.get("ai") else
               t("Calcoli deterministici sulle cifre del documento", "Deterministic calculations on the document's figures"))
    foot = Table([[Paragraph(left_note, S["foot"]), Paragraph(_x(ai_note), ParagraphStyle("fr", parent=S["foot"], alignment=2))]],
                 colWidths=[inner_w * 0.5, inner_w * 0.5])
    foot.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.6, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    rows += [[Spacer(1, 8)], [foot]]
    card = Table(rows, colWidths=[inner_w])
    card.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story += [Card(card, W), Spacer(1, 12)]

    def h2(text):
        # a section title never ends a page alone, and a long table may start under it and continue overleaf
        story.extend([CondPageBreak(110), Paragraph(_x(text), S["h2"]), Rule(W)])

    h3 = lambda text: Paragraph(_x(text), S["h3"])
    rd = a.get("reading") or {}

    # in short: the AI's summary
    if rd.get("summary"):
        story += [Lead(Paragraph(_x(rd["summary"]), S["lead"]), W), Spacer(1, 4)]

    finds = a.get("findings", [])
    if finds:
        h2(t("Osservazioni chiave", "Key findings"))
        story.append(ListFlowable([ListItem(Paragraph(_x(f.get("text")) + _tag(f.get("pages")), S["body"]), leftIndent=14)
                                   for f in finds], bulletType="1", bulletFontName=SERIF, bulletFontSize=10, leftIndent=14))

    hl = _highlights(a, W)
    if hl is not None:
        h2(t("I numeri in sintesi", "Financial highlights"))
        story.append(hl)

    visuals = charts.trend_section(a, W, h3) + charts.financial_section(a, W, h3) + charts.market_section(a, W, h3)
    if visuals:
        h2(t("Grafici", "Charts"))
        story.extend(visuals)

    # what the AI understood, theme by theme
    if rd.get("sections"):
        h2(t("Cosa ha capito l'AI", "What the AI understood") + (f" · {rd['doc_type']}" if rd.get("doc_type") else ""))
        for sec in rd["sections"]:
            head = h3(sec.get("title", ""))
            head.keepWithNext = True
            story.append(head)
            story.append(ListFlowable([ListItem(Paragraph(_x(p.get("text")) + _tag(p.get("pages")), S["body"]), leftIndent=12)
                                       for p in sec.get("points") or []], bulletType="bullet", start="•", leftIndent=12))

    ratios = charts.ratios_rows(a)
    if ratios:
        yrs = [str(y) for y in (a.get("fin") or {}).get("years") or ["", ""]]
        head = [t("Indicatore", "Ratio"), yrs[0], yrs[1] if len(yrs) > 1 else "", t("Variazione", "Change")]
        data = [[Paragraph(f"<font color='#6c6a7c'>{_x(h)}</font>" if i == 0 else f"<para alignment='right'><font color='#6c6a7c'>{_x(h)}</font></para>", S["cell"])
                 for i, h in enumerate(head)]]
        for lbl, cur, prev, chg in ratios:
            col = "#0f8a5f" if chg.startswith("+") else "#c8323c" if chg.startswith("-") else "#1d1c26"
            data.append([Paragraph(_x(lbl), S["cell"]), Paragraph(f"<para alignment='right'><b>{_x(cur)}</b></para>", S["cell"]),
                         Paragraph(f"<para alignment='right'>{_x(prev)}</para>", S["cell"]),
                         Paragraph(f"<para alignment='right'><font color='{col}'>{_x(chg)}</font></para>", S["cell"])])
        h2(t("Indicatori chiave", "Key ratios"))
        story.append(_table(data, W, 3))
    stats = charts.market_stats_rows(a)
    if stats:
        data = [[Paragraph(_x(lbl), S["cell"]), Paragraph(f"<para alignment='right'><b>{_x(v)}</b></para>", S["cell"]),
                 Paragraph(f"<para alignment='right'><font color='#6c6a7c'>{_x(extra)}</font></para>", S["cell"])] for lbl, v, extra in stats]
        h2(t("Rendimento e rischio", "Return and risk"))
        story.append(_table(data, W, 2, header=False))

    # the arithmetic checks that were possible
    if checks:
        h2(t("Controlli aritmetici", "Arithmetic checks"))
        data = []
        for c in checks:
            mark = '<font color="#0f8a5f"><b>OK</b></font>' if c.get("ok") else '<font color="#c8323c"><b>NO</b></font>'
            res = t("quadra", "balances") if c.get("ok") else _x(c.get("detail") or t("non quadra", "does not balance"))
            data.append([Paragraph(mark, S["cell"]), Paragraph(_x(c.get("name")), S["cell"]),
                         Paragraph(f"<para alignment='right'><font color='#6c6a7c'>{res}</font></para>", S["cell"]),
                         Paragraph(f"<para alignment='right'>{_tag(c.get('pages'))}</para>", S["cell"])])
        tbl = Table(data, colWidths=[26, W - 26 - 90 - 70, 90, 70])
        tbl.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#ecebf2")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(tbl)

    # how it was read
    h2(t("Come è stato letto", "How it was read"))
    shown = [p["n"] for p in a.get("pages", [])]
    lines = []
    if a.get("total_pages"):
        lines.append(t(f"Documento di {a['total_pages']} pagine; il ragno ha mostrato le pagine {_plist(shown)}.",
                       f"A {a['total_pages']}-page document; the spider showed pages {_plist(shown)}."))
    if rd.get("pages_read"):
        lines.append(t(f"{a.get('ai_provider') or 'L’AI'} ha letto {len(rd['pages_read'])} pagine (sintesi, analisi della gestione, prospetti).",
                       f"{a.get('ai_provider') or 'The AI'} read {len(rd['pages_read'])} pages (summary, management's discussion, statements)."))
    if (a.get("fin") or {}).get("periods"):
        pf = a["fin"]["periods"].get("flow") or []
        if len(pf) > 1 and pf[1]:
            lines.append(t(f"Confronto: {pf[0]} con {pf[1]}, lo stesso periodo dell'anno prima; stato patrimoniale al {(a['fin']['periods'].get('stock') or [''])[0]}.",
                           f"Comparison: {pf[0]} against {pf[1]}, the same period a year earlier; balance sheet as of {(a['fin']['periods'].get('stock') or [''])[0]}."))
    if a.get("kind") == "market":
        lines.append(t("Scheda generata dallo storico dei prezzi giornalieri: rendimenti, volatilità e drawdown sono calcolati.",
                       "Sheet generated from the daily price history: returns, volatility and drawdowns are computed."))
    elif a.get("kind") == "ixbrl":
        lines.append(t("Le cifre vengono dai tag XBRL del documento, con il loro periodo; i rapporti e il free cash flow sono calcolati.",
                       "Figures come from the document's XBRL tags, with their periods; ratios and free cash flow are computed."))
    else:
        lines.append(t("Le cifre vengono dalle tabelle del documento, lette con l'intestazione di colonna (il periodo); "
                       "i rapporti e il free cash flow sono calcolati.",
                       "Figures come from the document's tables, read with their column headers (the period); "
                       "ratios and free cash flow are computed."))
    lines += list(a.get("warnings") or [])
    for ln in lines:
        story += [Paragraph(_x(ln), S["small"]), Spacer(1, 2)]
    src = a.get("source") or ""
    story += [Spacer(1, 10), Paragraph(f"{t('Fonte', 'Source')}: {_x(src)}", S["foot"]),
              Paragraph(f"{t('Generato da Spider Analyst il', 'Generated by Spider Analyst on')} {today_s}. {_x(ai_note)}.", S["foot"])]
    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    return buf.getvalue()


def _table(data, width, ncols, header=True):
    num_w = min(80, width * 0.18)
    tbl = Table(data, colWidths=[width - num_w * ncols] + [num_w] * ncols, repeatRows=1 if header else 0)
    style = [("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#ecebf2")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    start = 1 if header else 0
    for i in range(start, len(data)):
        if (i - start) % 2 == 1:
            style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    tbl.setStyle(TableStyle(style))
    return tbl
