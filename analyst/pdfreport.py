"""The downloadable report as a PDF, drawn directly with reportlab (no browser needed).

Same look as the app: a summary card with a black border and a pink offset shadow,
four tiles with year-on-year change and page, findings with pink page tags,
arithmetic checks, and every figure read with its page.
"""
from __future__ import annotations

import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (Flowable, KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from .i18n import t, using

INK, MUTED, LINE, PINK, BLUE, CYAN, UP, DOWN = (colors.HexColor(c) for c in
                                                ("#1d1c26", "#6c6a7c", "#d6d4e0", "#ff2d8f", "#3b6cff", "#3fd4f5", "#0f8a5f", "#c8323c"))
ZEBRA = colors.HexColor("#fafafd")
SERIF, SERIF_B, SANS, SANS_B = "Times-Roman", "Times-Bold", "Helvetica", "Helvetica-Bold"

# the standard PDF fonts cover Windows-1252 only
_SAFE = str.maketrans({"−": "-", "→": "->", "≈": "~", "✓": "", "✗": "", " ": " ", " ": " "})


def _x(s) -> str:
    return escape(str(s if s is not None else "").translate(_SAFE))


def _pages(pages) -> str:
    if not pages:
        return ""
    return ("pp. " if len(pages) > 1 else "p. ") + ", ".join(str(p) for p in pages)


def _tag(pages) -> str:
    return f' <font color="#ff2d8f" size="8"><b>{_pages(pages)}</b></font>' if pages else ""


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
}


class Rule(Flowable):
    def __init__(self, width, thick=1.4, color=INK):
        super().__init__()
        self.width, self.thick, self.color = width, thick, color
        self.height = thick + 2

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thick)
        self.canv.line(0, 1, self.width, 1)


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


def build(a: dict) -> bytes:
    lang = a.get("lang") or "en"
    with using(lang):
        return _build(a, lang)


def _build(a: dict, lang: str) -> bytes:
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

    # summary card
    tiles = []
    for tile in a.get("card", []):
        label = tile.get("en") if lang == "en" and tile.get("en") else tile.get("it")
        cell = [Paragraph(_x(label), S["tl"]), Paragraph(_x(tile.get("display")), S["tv"])]
        yoy = tile.get("yoy_display") or ""
        if yoy:
            col = "#0f8a5f" if yoy.startswith("+") else "#c8323c"
            cell.append(Paragraph(f'<font color="{col}">{_x(yoy)} {t("sull’anno", "year on year")}</font>', S["ty"]))
        if tile.get("pages"):
            cell.append(Paragraph(f'<font color="#ff2d8f"><b>{_pages(tile["pages"])}</b></font>', S["tl"]))
        tiles.append(cell)
    inner_w = W - 2 * 12 - 5
    rows = [[Paragraph(_x(a.get("title")), S["title"])], [Paragraph(_x(a.get("subtitle")), S["sub"])], [Spacer(1, 8)]]
    if tiles:
        n = len(tiles)
        gap = 6
        tw = (inner_w - gap * (n - 1)) / n
        # each tile is its own boxed cell, with gaps between them
        cells = []
        for i, tl in enumerate(tiles):
            one = Table([[tl]], colWidths=[tw])
            one.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                                     ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
            cells.append(one)
            if i < n - 1:
                cells.append("")
        widths = []
        for i in range(n):
            widths.append(tw)
            if i < n - 1:
                widths.append(gap)
        row = Table([cells], colWidths=widths)
        row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                 ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                 ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        rows.append([row])
    passed = sum(1 for c in a.get("checks", []) if c.get("ok"))
    nfig = len(a.get("facts", {}))
    ai_note = (t("Osservazioni di {p}, verificate sulle cifre", "Findings by {p}, checked against the figures").format(p=a.get("ai_provider") or "AI")
               if a.get("ai") else t("Calcoli deterministici sulle cifre del documento", "Deterministic calculations on the document's figures"))
    foot = Table([[Paragraph(f"<b>{nfig}</b> {t('cifre lette', 'figures read')} · <b>{passed}</b> "
                             f"{t('controlli superati su', 'checks passed out of')} {len(a.get('checks', []))}", S["foot"]),
                   Paragraph(_x(ai_note), ParagraphStyle("fr", parent=S["foot"], alignment=2))]], colWidths=[inner_w * 0.5, inner_w * 0.5])
    foot.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.6, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    rows += [[Spacer(1, 8)], [foot]]
    card = Table(rows, colWidths=[inner_w])
    card.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story += [Card(card, W), Spacer(1, 10)]

    def h2(text):
        story.extend([Paragraph(_x(text), S["h2"]), Rule(W), Spacer(1, 4)])

    # findings
    finds = a.get("findings", [])
    if finds:
        h2(t("Osservazioni chiave", "Key findings"))
        story.append(ListFlowable([ListItem(Paragraph(_x(f.get("text")) + _tag(f.get("pages")), S["body"]), leftIndent=14)
                                   for f in finds], bulletType="1", bulletFontName=SERIF, bulletFontSize=10, leftIndent=14))

    # checks
    checks = a.get("checks", [])
    if checks:
        h2(t("Controlli aritmetici", "Arithmetic checks"))
        for c in checks:
            mark = '<font color="#0f8a5f"><b>OK</b></font>' if c.get("ok") else '<font color="#c8323c"><b>NO</b></font>'
            res = t("superato", "passed") if c.get("ok") else t("non superato", "failed")
            extra = f" ({_x(c.get('detail'))})" if c.get("detail") and not c.get("ok") else ""
            story.append(Paragraph(f"{mark}  {_x(c.get('name'))} — {res}{extra}", S["small"]))
            story.append(Spacer(1, 2))

    # every figure read
    facts = a.get("facts", {})
    h2(f"{t('Cifre lette', 'Figures read')} ({len(facts)})")
    in_rows = set()
    for page in a.get("pages", []):
        rows_p = a.get("rows", {}).get(str(page["n"])) or a.get("rows", {}).get(page["n"]) or []
        if not rows_p:
            continue
        cols = a.get("cols", {}).get(str(page["n"])) or a.get("cols", {}).get(page["n"]) or [t("Valore", "Value")]
        data = [[Paragraph(f"<font color='#6c6a7c'>{t('Voce', 'Item')}</font>", S["cell"])] +
                [Paragraph(f"<para alignment='right'><font color='#6c6a7c'>{_x(c)}</font></para>", S["cell"]) for c in cols]]
        for r in rows_p:
            line = [Paragraph(_x(r.get("label")), S["cell"])]
            for fid in r.get("cells", []):
                if fid is not None:
                    in_rows.add(str(fid))
                val = facts.get(str(fid), {}).get("value_fmt", "") if fid is not None else ""
                line.append(Paragraph(f"<para alignment='right'>{_x(val)}</para>", S["cell"]))
            data.append(line)
        story.append(KeepTogether([Paragraph(_x(page.get("title")) + _tag([page["n"]]), S["h3"]), _table(data, W, len(cols))]))
    others = [(fid, f) for fid, f in facts.items() if str(fid) not in in_rows]
    if others:
        data = [[Paragraph(_x(f.get("label")), S["cell"]), Paragraph(f"<para alignment='right'>{_x(f.get('value_fmt'))}</para>", S["cell"]),
                 Paragraph(f"<para alignment='right'><font color='#ff2d8f'><b>p. {f.get('page')}</b></font></para>", S["cell"])]
                for _, f in others]
        story.append(Paragraph(t("Altre cifre lette dal ragno", "Other figures the spider read"), S["h3"]))
        story.append(_table(data, W, 2, header=False))

    src = a.get("source") or ""
    story += [Spacer(1, 12), Paragraph(f"{t('Fonte', 'Source')}: {_x(src)}", S["foot"]),
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
