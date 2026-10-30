"""The report as a PowerPoint deck (16:9) for presentations at work.

Charts are native PowerPoint charts (the numbers stay editable), every slide says where its figures are
printed in the document ("p. F-7") and where the document comes from. Same content as the PDF report:
headline figures, findings, results against the comparative period, trend, margins, balance sheet, cash,
the statements at a glance, what the AI understood, the checks, how it was read.
"""
from __future__ import annotations

import io
import re
from datetime import date

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from . import charts, themes
from . import financials as F
from .i18n import t, using
from .pdfreport import HIGHLIGHTS

W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.6)
TITLE_FONT, BODY_FONT = "Georgia", "Calibri"
INK, MUTED, LINE, SOFT, UP, DOWN = ("1D1C26", "6C6A7C", "D6D4E0", "F6F5FA", "0F8A5F", "C8323C")


def _rgb(hex6: str) -> RGBColor:
    return RGBColor.from_string(hex6.lstrip("#").upper())


class Deck:
    def __init__(self, a: dict, theme: str):
        self.a = a
        self.pal = themes.palette(theme)
        self.labels = {str(k): v for k, v in (a.get("page_labels") or {}).items()}
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = W, H
        self.n = 0

    # ------------------------------------------------------------ primitives

    def pages(self, pages) -> str:
        pages = [p for p in pages or [] if p]
        if not pages:
            return ""
        return ("pp. " if len(pages) > 1 else "p. ") + ", ".join(str(self.labels.get(str(p)) or p) for p in pages)

    def text(self, slide, x, y, w, h, runs, size=14, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font=BODY_FONT):
        """runs: a string, or paragraphs as lists of (text, {bold, color, size, italic})."""
        tb = slide.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = Inches(0.05)
        paras = [[(runs, {})]] if isinstance(runs, str) else runs
        for i, para in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            for s, st in para:
                r = p.add_run()
                r.text = s
                r.font.name = st.get("font", font)
                r.font.size = Pt(st.get("size", size))
                r.font.bold = st.get("bold", False)
                r.font.italic = st.get("italic", False)
                r.font.color.rgb = _rgb(st.get("color", INK))
            if para and para[0][1].get("space"):
                p.space_after = Pt(para[0][1]["space"])
        return tb

    def slide(self, title: str, note: str = ""):
        """A blank slide with its title, an accent rule and the footer."""
        self.n += 1
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.text(s, MARGIN, Inches(0.35), W - 2 * MARGIN, Inches(0.7), [[(title, {"size": 28, "bold": True, "font": TITLE_FONT})]])
        bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGIN, Inches(1.08), Inches(0.9), Emu(38000))
        bar.fill.solid()
        bar.fill.fore_color.rgb = _rgb(self.pal["accent"])
        bar.line.fill.background()
        foot = f"Spider Analyst  ·  {self.a.get('title', '')}" + (f"  ·  {note}" if note else "")
        self.text(s, MARGIN, H - Inches(0.5), W - 2 * MARGIN - Inches(0.6), Inches(0.3), [[(foot, {"size": 10, "color": MUTED})]])
        self.text(s, W - MARGIN - Inches(0.6), H - Inches(0.5), Inches(0.6), Inches(0.3), [[(str(self.n), {"size": 10, "color": MUTED})]],
                  align=PP_ALIGN.RIGHT)
        return s

    def source(self, slide, pages, y=None):
        """Where the figures on this slide are printed."""
        tag = self.pages(pages)
        if not tag:
            return
        y = y if y is not None else H - Inches(0.85)
        self.text(slide, MARGIN, y, W - 2 * MARGIN, Inches(0.3),
                  [[(t("Fonte: ", "Source: "), {"size": 11, "color": MUTED}), (f"{self._doc()}, {tag}", {"size": 11, "color": self.pal["accent"], "bold": True})]])

    def _doc(self) -> str:
        """What the page numbers refer to: "Form S-1", "Form 10-K", or the kind of document."""
        head = (self.a.get("subtitle") or "").split(" · ")[0]
        if re.match(r"(Form|Modulo|Bilancio|Financial statements)\b", head):
            return head
        return t("relazione finanziaria", "financial report") if self.a.get("kind") == "ixbrl" else t("documento", "document")

    def bullets(self, slide, items, x, y, w, h, size=16):
        """items: (text, pages); the page reference follows each point in the accent colour."""
        paras = []
        for text, pages in items:
            tag = self.pages(pages)
            run = [("•  ", {"size": size, "color": self.pal["accent"], "bold": True, "space": 10}), (text, {"size": size})]
            if tag:
                run.append(("  " + tag, {"size": size - 4, "color": self.pal["accent"], "bold": True}))
            paras.append(run)
        self.text(slide, x, y, w, h, paras)

    def chart(self, slide, kind, x, y, w, h, cats, series, fmt="#,##0.0", colors=None, legend=True, labels=True):
        cd = CategoryChartData()
        cd.categories = cats
        for name, vals in series:
            cd.add_series(name, vals, number_format=fmt)
        ch = slide.shapes.add_chart(kind, x, y, w, h, cd).chart
        ch.has_title = False
        ch.font.size = Pt(12)
        ch.font.name = BODY_FONT
        ch.has_legend = legend and len(series) > 1
        if ch.has_legend:
            ch.legend.position = XL_LEGEND_POSITION.BOTTOM
            ch.legend.include_in_layout = False
        plot = ch.plots[0]
        colors = colors or [self.pal["accent"], self.pal["prior"], self.pal["accent2"], self.pal["accent3"]]
        line = kind in (XL_CHART_TYPE.LINE, XL_CHART_TYPE.LINE_MARKERS)
        if not line:
            plot.gap_width = 70
            plot.overlap = -15 if len(series) > 1 else 0
        if labels:
            plot.has_data_labels = True
            dl = plot.data_labels
            dl.number_format, dl.number_format_is_linked = fmt, False
            dl.font.size = Pt(11)
            dl.position = XL_LABEL_POSITION.OUTSIDE_END
        for i, ser in enumerate(plot.series):
            col = _rgb(colors[i % len(colors)])
            if line:
                ser.smooth = False
                ser.format.line.color.rgb = col
                ser.format.line.width = Pt(2)
                ser.marker.style = XL_MARKER_STYLE.NONE
            else:
                ser.format.fill.solid()
                ser.format.fill.fore_color.rgb = col
                ser.invert_if_negative = False
        va = ch.value_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = _rgb("ECEBF2")
        va.tick_labels.font.size = Pt(11)
        va.tick_labels.font.color.rgb = _rgb(MUTED)
        va.tick_labels.number_format, va.tick_labels.number_format_is_linked = fmt.replace(".0", "") if "%" not in fmt else "0%", False
        va.format.line.fill.background()
        ca = ch.category_axis
        ca.tick_labels.font.size = Pt(12)
        ca.format.line.color.rgb = _rgb(INK)
        ca.has_major_gridlines = False
        ca.tick_label_position = XL_TICK_LABEL_POSITION.LOW          # labels stay clear of negative bars
        if kind == XL_CHART_TYPE.BAR_CLUSTERED:
            ca.reverse_order = True                                    # first item on top, as listed
        return ch

    def table(self, slide, rows, x, y, w, widths, size=14, header=True, colors=None, left=1):
        """rows of strings; colors: {(r, c): hex} for coloured cells (changes, OK/NO); the first `left` columns align left."""
        colors = colors or {}
        rh = Inches(0.42)
        gt = slide.shapes.add_table(len(rows), len(rows[0]), x, y, w, rh * len(rows))
        tbl = gt.table
        tbl.first_row = header
        tbl.horz_banding = False
        total = sum(widths)
        for i, cw in enumerate(widths):
            tbl.columns[i].width = int(w * cw / total)
        for r, row in enumerate(rows):
            tbl.rows[r].height = rh
            for c, val in enumerate(row):
                cell = tbl.cell(r, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(SOFT if (header and r == 0) else ("FFFFFF" if r % 2 else "FAFAFD"))
                cell.margin_left = cell.margin_right = Inches(0.08)
                cell.margin_top = cell.margin_bottom = Inches(0.03)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                tf = cell.text_frame
                tf.word_wrap = True
                p = tf.paragraphs[0]
                p.alignment = PP_ALIGN.LEFT if c < left else PP_ALIGN.RIGHT
                run = p.add_run()
                run.text = str(val)
                run.font.size = Pt(size)
                run.font.name = BODY_FONT
                run.font.bold = (header and r == 0) or (c == 1 and r > 0 and len(row) > 2)
                run.font.color.rgb = _rgb(colors.get((r, c), MUTED if header and r == 0 else INK))
        return gt

    # ------------------------------------------------------------ slides

    def cover(self):
        self.n += 1
        a = self.a
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.35), H)
        band.fill.solid()
        band.fill.fore_color.rgb = _rgb(self.pal["accent"])
        band.line.fill.background()
        self.text(s, Inches(1.1), Inches(2.2), W - Inches(2.2), Inches(1.4), [[(a.get("title") or "", {"size": 44, "bold": True, "font": TITLE_FONT})]],
                  anchor=MSO_ANCHOR.BOTTOM)
        self.text(s, Inches(1.1), Inches(3.7), W - Inches(2.2), Inches(0.8), [[(a.get("subtitle") or "", {"size": 18, "color": MUTED})]])
        today = date.today()
        from .market import months
        mn = months()
        when = t(f"{today.day} {mn[today.month - 1]} {today.year}", f"{mn[today.month - 1]} {today.day}, {today.year}")
        self.text(s, Inches(1.1), H - Inches(1.4), W - Inches(2.2), Inches(0.8),
                  [[("Spider Analyst", {"size": 14, "bold": True}), (f"  ·  {t('Report', 'Report')}  ·  {when}", {"size": 14, "color": MUTED})],
                   [(t("Fonte: ", "Source: ") + (a.get("source") or ""), {"size": 11, "color": MUTED})]])

    def headline(self):
        a = self.a
        tiles = a.get("card") or []
        if not tiles:
            return
        s = self.slide(t("I numeri chiave", "Headline figures"))
        n = min(4, len(tiles))
        gap = Inches(0.25)
        tw = int((W - 2 * MARGIN - gap * (n - 1)) / n)
        lang = a.get("lang") or "en"
        for i, tile in enumerate(tiles[:4]):
            x, y, h = MARGIN + i * (tw + gap), Inches(1.5), Inches(2.6)
            box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, tw, h)
            box.adjustments[0] = 0.06
            box.fill.solid()
            box.fill.fore_color.rgb = _rgb("FFFFFF")
            box.line.color.rgb = _rgb(LINE)
            label = tile.get("en") if lang == "en" and tile.get("en") else tile.get("it")
            paras = [[(label or "", {"size": 14, "color": MUTED, "space": 4})],
                     [(tile.get("display") or "—", {"size": 32, "bold": True, "space": 2})]]
            if tile.get("exact"):
                paras.append([(tile["exact"], {"size": 12, "color": MUTED, "space": 6})])
            yoy, vs = tile.get("yoy_display") or "", tile.get("vs") or ""
            if yoy:
                paras.append([(yoy, {"size": 15, "bold": True, "color": UP if yoy.startswith("+") else DOWN}),
                              ("  " + (("vs " + vs) if vs else t("sull'anno", "year on year")), {"size": 12, "color": MUTED})])
            elif tile.get("prev_display"):
                paras.append([(f"{t('era', 'was')} {tile['prev_display']}" + (f" ({vs})" if vs else ""), {"size": 13, "color": MUTED})])
            if tile.get("note"):
                paras.append([(tile["note"], {"size": 11, "italic": True, "color": MUTED})])
            if tile.get("pages"):
                paras.append([(self.pages(tile["pages"]), {"size": 12, "bold": True, "color": self.pal["accent"]})])
            self.text(s, x + Inches(0.15), y + Inches(0.15), tw - Inches(0.3), h - Inches(0.3), paras)
        rd = a.get("reading") or {}
        checks = a.get("checks") or []
        if rd.get("summary"):
            self.text(s, MARGIN, Inches(4.45), W - 2 * MARGIN, Inches(2.0), [[(rd["summary"], {"size": 16, "font": TITLE_FONT})]])
        elif checks:
            ok = sum(1 for c in checks if c.get("ok"))
            self.text(s, MARGIN, Inches(4.45), W - 2 * MARGIN, Inches(0.6),
                      [[(t(f"{ok} controlli aritmetici superati su {len(checks)}", f"{ok} of {len(checks)} arithmetic checks pass"), {"size": 16})]])

    def findings(self):
        finds = self.a.get("findings") or []
        for i in range(0, min(len(finds), 12), 6):
            s = self.slide(t("Osservazioni chiave", "Key findings") + (t(" (segue)", " (cont.)") if i else ""))
            self.bullets(s, [(f.get("text", ""), f.get("pages")) for f in finds[i:i + 6]], MARGIN, Inches(1.45), W - 2 * MARGIN, H - Inches(2.3))

    def results(self):
        fin = self.a.get("fin")
        if not fin:
            return
        m, d, cur = fin["metrics"], fin["derived"], fin.get("currency", "")
        years = [str(y) for y in fin.get("years") or [t("Corrente", "Current"), t("Precedente", "Prior")]]
        val = lambda k, w="cur": (m.get(k) or {}).get(w)
        items = [(lbl, val(k), val(k, "prev"), (m.get(k) or {}).get("page")) for k, lbl in (
            ("revenue", t("Ricavi", "Revenue")), ("gross_profit", t("Margine lordo", "Gross profit")),
            ("operating_income", t("Risultato operativo", "Operating income")), ("net_income", t("Risultato netto", "Net income")),
            ("cfo", t("Cassa operativa", "Operating cash flow"))) if val(k) is not None]
        if d["cur"].get("fcf") is not None:
            items.append(("Free cash flow", d["cur"]["fcf"], d["prev"].get("fcf"), (m.get("cfo") or {}).get("page")))
        if len(items) < 2:
            return
        div, unit = _scale(max(abs(v) for _, c, p, _ in items for v in (c, p) if v is not None), cur)
        s = self.slide(t(f"Risultati: {years[0]} e {years[1]}", f"Results: {years[0]} vs {years[1]}") if len(years) > 1 else t("Risultati", "Results"))
        series = [(years[0], [_n(c, div) for _, c, _, _ in items])]
        if len(years) > 1 and any(p is not None for _, _, p, _ in items):
            series.append((years[1], [_n(p, div) for _, _, p, _ in items]))
        self.chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, MARGIN, Inches(1.45), W - 2 * MARGIN, Inches(4.9), [lbl for lbl, *_ in items], series)
        self.text(s, W - MARGIN - Inches(4), Inches(1.2), Inches(4), Inches(0.3), [[(unit, {"size": 11, "color": MUTED})]], align=PP_ALIGN.RIGHT)
        self.source(s, sorted({p for *_, p in items if p}))

    def trend(self):
        fin = self.a.get("fin") or {}
        series = fin.get("series") or {}
        periods = (fin.get("periods") or {}).get("flow") or []
        cur = fin.get("currency", "")
        parts = []
        for key, title in (("revenue", t("Ricavi nel tempo", "Revenue over time")), ("net_income", t("Risultato netto nel tempo", "Net income over time"))):
            pts = series.get(key) or []
            annual = [p for p in pts if p.get("months") == 12][-5:]
            interim = sorted((p for p in pts if p.get("months") not in (12, None) and p["label"] in periods[:2]), key=lambda p: p["end"])
            items = annual + interim
            if len(items) >= 3:
                parts.append((title, items))
        if not parts:
            return
        s = self.slide(t("Andamento nel tempo", "Over time"))
        half = int((W - 2 * MARGIN - Inches(0.4)) / len(parts))
        top = max(abs(p["value"]) for _, items in parts for p in items)
        div, unit = _scale(top, cur)
        for i, (title, items) in enumerate(parts):
            x = MARGIN + i * (half + Inches(0.4))
            self.text(s, x, Inches(1.35), half, Inches(0.4), [[(title, {"size": 16, "bold": True}), (f"  {unit}", {"size": 11, "color": MUTED})]])
            colors = [self.pal["accent"] if p.get("months") == 12 else self.pal["accent2"] for p in items]
            ch = self.chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, x, Inches(1.8), half, Inches(4.6), [p["label"] for p in items],
                            [(title, [_n(p["value"], div) for p in items])], legend=False)
            for j, pt in enumerate(ch.plots[0].series[0].points):
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = _rgb(colors[j])
        self.source(s, [((fin.get("metrics") or {}).get(k) or {}).get("page") for k in ("revenue", "net_income")])

    def margins_and_balance(self):
        fin = self.a.get("fin")
        if not fin:
            return
        m, d, cur = fin["metrics"], fin["derived"], fin.get("currency", "")
        years = [str(y) for y in fin.get("years") or ["", ""]]
        stock = [str(y) for y in ((fin.get("periods") or {}).get("stock") or years)]
        margins = [(lbl, d["cur"].get(k), d["prev"].get(k)) for k, lbl in (
            ("gross_margin", t("Margine lordo", "Gross margin")), ("operating_margin", t("Margine operativo", "Operating margin")),
            ("net_margin", t("Margine netto", "Net margin")), ("fcf_margin", t("Margine FCF", "FCF margin"))) if d["cur"].get(k) is not None]
        # a loss many times revenue makes a margin chart unreadable: those stay in the ratio table
        margins = [x for x in margins if abs(x[1]) <= 1.5 and (x[2] is None or abs(x[2]) <= 1.5)]
        val = lambda k, w="cur": (m.get(k) or {}).get(w)
        bal = [(lbl, val(k), val(k, "prev"), (m.get(k) or {}).get("page")) for k, lbl in (
            ("total_assets", t("Attivo", "Assets")), ("total_liabilities", t("Passivo", "Liabilities")),
            ("temp_equity", t("Privilegiate", "Redeemable pref.")), ("equity", t("Patrimonio netto", "Equity"))) if val(k) is not None]
        if not bal and d["cur"].get("total_liabilities") is not None and val("total_assets") is not None:
            bal = [(t("Attivo", "Assets"), val("total_assets"), val("total_assets", "prev"), m["total_assets"].get("page")),
                   (t("Passivo", "Liabilities"), d["cur"]["total_liabilities"], d["prev"].get("total_liabilities"), None)]
        parts = [p for p in (("m", margins) if margins else None, ("b", bal) if len(bal) >= 2 else None) if p]
        if not parts:
            return
        s = self.slide(t("Margini e stato patrimoniale", "Margins and balance sheet") if len(parts) == 2 else
                       t("Margini", "Margins") if parts[0][0] == "m" else t("Stato patrimoniale", "Balance sheet"))
        half = int((W - 2 * MARGIN - Inches(0.4)) / len(parts))
        pages = []
        for i, (kind, items) in enumerate(parts):
            x = MARGIN + i * (half + Inches(0.4))
            if kind == "m":
                self.text(s, x, Inches(1.35), half, Inches(0.4), [[(t("Margini", "Margins"), {"size": 16, "bold": True})]])
                series = [(years[0], [c for _, c, _ in items])]
                if any(p is not None for _, _, p in items) and len(years) > 1:
                    series.append((years[1], [p for _, _, p in items]))
                self.chart(s, XL_CHART_TYPE.BAR_CLUSTERED, x, Inches(1.8), half, Inches(4.6), [lbl for lbl, *_ in items], series, fmt="0.0%")
                pages += [(m.get("revenue") or {}).get("page")]
            else:
                div, unit = _scale(max(abs(v) for _, c, p, _ in items for v in (c, p) if v is not None), cur)
                self.text(s, x, Inches(1.35), half, Inches(0.4), [[(t("Stato patrimoniale", "Balance sheet"), {"size": 16, "bold": True}),
                                                                  (f"  {unit}", {"size": 11, "color": MUTED})]])
                series = [(stock[0], [_n(c, div) for _, c, _, _ in items])]
                if len(stock) > 1 and any(p is not None for _, _, p, _ in items):
                    series.append((stock[1], [_n(p, div) for _, _, p, _ in items]))
                self.chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, x, Inches(1.8), half, Inches(4.6), [lbl for lbl, *_ in items], series)
                pages += [p for *_, p in items]
        self.source(s, sorted({p for p in pages if p}))

    def cash(self):
        fin = self.a.get("fin")
        if not fin:
            return
        m, cur = fin["metrics"], fin.get("currency", "")
        val = lambda k: (m.get(k) or {}).get("cur")
        cfo, capex = val("cfo"), val("capex")
        if cfo is None or capex is None:
            return
        steps = [(t("Cassa operativa", "Operating cash flow"), cfo), ("Capex", -abs(capex)), ("Free cash flow", cfo - abs(capex))]
        for k, lbl in (("buybacks", t("Riacquisti", "Buybacks")), ("dividends", t("Dividendi", "Dividends"))):
            if val(k):
                steps.append((lbl, -abs(val(k))))
        div, unit = _scale(max(abs(v) for _, v in steps), cur)
        years = [str(y) for y in fin.get("years") or [""]]
        s = self.slide(t("Dove va la cassa", "Where the cash goes") + (f" · {years[0]}" if years[0] else ""))
        colors = [self.pal["accent3"], DOWN, self.pal["accent"]] + [self.pal["amber"]] * (len(steps) - 3)
        ch = self.chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, MARGIN, Inches(1.45), W - 2 * MARGIN, Inches(4.9), [lbl for lbl, _ in steps],
                        [(t("Cassa", "Cash"), [_n(v, div) for _, v in steps])], legend=False)
        for j, pt in enumerate(ch.plots[0].series[0].points):
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = _rgb(colors[j])
        self.text(s, W - MARGIN - Inches(4), Inches(1.2), Inches(4), Inches(0.3), [[(unit, {"size": 11, "color": MUTED})]], align=PP_ALIGN.RIGHT)
        self.source(s, sorted({(m.get(k) or {}).get("page") for k in ("cfo", "capex", "buybacks", "dividends") if (m.get(k) or {}).get("page")}))

    def highlights(self):
        fin = self.a.get("fin") or {}
        m, cur, d = fin.get("metrics") or {}, fin.get("currency", ""), fin.get("derived") or {}
        if len(m) < 3:
            return
        per = fin.get("periods") or {}
        flow = per.get("flow") or [str(y) for y in fin.get("years") or ["", ""]]
        stock = per.get("stock") or flow
        for name, kind, keys in HIGHLIGHTS:
            labels = stock if kind == "stock" else flow
            rows = [[t(*name), labels[0] if labels else "", labels[1] if len(labels) > 1 else "", t("Variazione", "Change"), t("Pagina", "Page")]]
            colors, pages = {}, []
            for k in keys:
                if k == "fcf":
                    c, p, pg = (d.get("cur") or {}).get("fcf"), (d.get("prev") or {}).get("fcf"), (m.get("cfo") or {}).get("page")
                    lbl, fmt = t("Free cash flow (calcolato)", "Free cash flow (computed)"), (lambda v: F.fmt_money(v, cur))
                elif k in m:
                    c, p, pg = m[k]["cur"], m[k]["prev"], m[k].get("page")
                    lbl = t("Perdita netta", "Net loss") if k == "net_income" and c is not None and c < 0 else F.label(k)
                    fmt = lambda v, k=k: F.fmt_value(k, v, cur)
                else:
                    continue
                if c is None:
                    continue
                chg, col = _change(c, p)
                if col:
                    colors[(len(rows), 3)] = col
                rows.append([lbl, fmt(c), fmt(p) if p is not None else "—", chg, self.pages([pg])])
                pages.append(pg)
            if len(rows) < 3:
                continue
            s = self.slide(t("I numeri in sintesi", "Financial highlights") + f" · {t(*name)}")
            self.table(s, rows[:12], MARGIN, Inches(1.45), W - 2 * MARGIN, [4.2, 1.6, 1.6, 1.3, 1.3], colors=colors)

    def ratios(self):
        rows = charts.ratios_rows(self.a)
        if not rows:
            return
        yrs = [str(y) for y in (self.a.get("fin") or {}).get("years") or ["", ""]]
        data = [[t("Indicatore", "Ratio"), yrs[0], yrs[1] if len(yrs) > 1 else "", t("Variazione", "Change")]]
        colors = {}
        for lbl, cur, prev, chg in rows[:12]:
            if chg.startswith("+"):
                colors[(len(data), 3)] = UP
            elif chg.startswith("-"):
                colors[(len(data), 3)] = DOWN
            data.append([lbl, cur, prev, chg])
        s = self.slide(t("Indicatori chiave", "Key ratios"))
        self.table(s, data, MARGIN, Inches(1.45), W - 2 * MARGIN, [4.5, 1.6, 1.6, 1.6], colors=colors)

    def market(self):
        sr = self.a.get("series")
        if not sr:
            return
        cur = sr.get("currency", "")
        pts = sr.get("points") or []
        if len(pts) >= 10:
            step = max(1, len(pts) // 260)
            thin = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
            s = self.slide(t("Andamento del prezzo", "Price history") + (f" ({cur})" if cur else ""))
            self.chart(s, XL_CHART_TYPE.LINE, MARGIN, Inches(1.45), W - 2 * MARGIN, Inches(5.2),
                       [date.fromisoformat(d[:10]) for d, _ in thin], [(t("Prezzo", "Price"), [v for _, v in thin])], fmt="#,##0.00", labels=False)
        annual = sr.get("annual") or []
        stats = charts.market_stats_rows(self.a)
        if annual or stats:
            s = self.slide(t("Rendimento e rischio", "Return and risk"))
            half = int((W - 2 * MARGIN - Inches(0.4)) / 2)
            if annual:
                self.text(s, MARGIN, Inches(1.35), half, Inches(0.4), [[(t("Rendimenti per anno solare", "Calendar-year returns"), {"size": 16, "bold": True})]])
                ch = self.chart(s, XL_CHART_TYPE.COLUMN_CLUSTERED, MARGIN, Inches(1.8), half, Inches(4.6), [str(y) for y, *_ in annual],
                                [(t("Rendimento", "Return"), [r for _, r, *_ in annual])], fmt="0%", legend=False)
                for j, pt in enumerate(ch.plots[0].series[0].points):
                    pt.format.fill.solid()
                    pt.format.fill.fore_color.rgb = _rgb(UP if annual[j][1] >= 0 else DOWN)
            if stats:
                self.table(s, [[lbl, v, extra] for lbl, v, extra in stats], MARGIN + half + Inches(0.4), Inches(1.8), half, [3, 1.4, 2], size=13, header=False)

    def understood(self):
        rd = self.a.get("reading") or {}
        secs = [sec for sec in rd.get("sections") or [] if sec.get("points")]
        for i in range(0, len(secs), 2):
            s = self.slide(t("Cosa ha capito l'AI", "What the AI understood") + (f" · {rd['doc_type']}" if rd.get("doc_type") else ""))
            half = int((W - 2 * MARGIN - Inches(0.4)) / 2)
            for j, sec in enumerate(secs[i:i + 2]):
                x = MARGIN + j * (half + Inches(0.4))
                self.text(s, x, Inches(1.35), half, Inches(0.45), [[(sec.get("title", ""), {"size": 18, "bold": True, "font": TITLE_FONT})]])
                self.bullets(s, [(p.get("text", ""), p.get("pages")) for p in sec["points"][:5]], x, Inches(1.9), half, H - Inches(2.8), size=14)

    def checks(self):
        checks = self.a.get("checks") or []
        if not checks:
            return
        rows = [["", t("Controllo", "Check"), t("Esito", "Result"), t("Pagine", "Pages")]]
        colors = {}
        for c in checks:
            colors[(len(rows), 0)] = UP if c.get("ok") else DOWN
            rows.append(["OK" if c.get("ok") else "NO", c.get("name", ""),
                         t("quadra", "balances") if c.get("ok") else (c.get("detail") or t("non quadra", "does not balance")), self.pages(c.get("pages"))])
        s = self.slide(t("Controlli aritmetici", "Arithmetic checks"))
        self.table(s, rows, MARGIN, Inches(1.45), W - 2 * MARGIN, [0.6, 6.4, 3.2, 1.2], colors=colors, left=2)

    def how(self):
        a = self.a
        rd = a.get("reading") or {}
        lines = []
        if a.get("total_pages"):
            lines.append(t(f"Documento di {a['total_pages']} pagine.", f"A {a['total_pages']}-page document."))
        if rd.get("pages_read"):
            lines.append(t(f"{a.get('ai_provider') or 'L’AI'} ha letto {len(rd['pages_read'])} pagine; ogni numero che cita è confrontato con il documento.",
                           f"{a.get('ai_provider') or 'The AI'} read {len(rd['pages_read'])} pages; every number it cites is matched to the document."))
        per = (a.get("fin") or {}).get("periods") or {}
        if len(per.get("flow") or []) > 1:
            lines.append(t(f"Confronto: {per['flow'][0]} con {per['flow'][1]}; stato patrimoniale al {(per.get('stock') or [''])[0]}.",
                           f"Comparison: {per['flow'][0]} against {per['flow'][1]}; balance sheet as of {(per.get('stock') or [''])[0]}."))
        if a.get("kind") == "ixbrl":
            lines.append(t("Le cifre vengono dai tag XBRL del documento; rapporti e free cash flow sono calcolati.",
                           "Figures come from the document's XBRL tags; ratios and free cash flow are computed."))
        elif a.get("kind") == "market":
            lines.append(t("Rendimenti, volatilità e drawdown sono calcolati dallo storico dei prezzi giornalieri.",
                           "Returns, volatility and drawdowns are computed from the daily price history."))
        else:
            lines.append(t("Le cifre vengono dalle tabelle del documento, con il periodo della loro colonna; rapporti e free cash flow sono calcolati.",
                           "Figures come from the document's tables, with the period of their column; ratios and free cash flow are computed."))
        lines += list(a.get("warnings") or [])[:3]
        s = self.slide(t("Come è stato letto", "How it was read"))
        self.bullets(s, [(ln, None) for ln in lines], MARGIN, Inches(1.45), W - 2 * MARGIN, Inches(4), size=16)
        self.text(s, MARGIN, H - Inches(1.4), W - 2 * MARGIN, Inches(0.7),
                  [[(t("Fonte: ", "Source: "), {"size": 12, "color": MUTED}), (a.get("source") or "", {"size": 12})],
                   [(t("Generato da Spider Analyst. Non è una consulenza finanziaria.", "Generated by Spider Analyst. Not financial advice."),
                     {"size": 11, "color": MUTED, "italic": True})]])


def _n(v, div):
    return None if v is None else round(v / div, 2)


def _scale(top: float, cur: str) -> tuple[float, str]:
    """Divisor and unit for a chart's values: "USD billions" / "miliardi di USD"."""
    cur = cur or ""
    for div, it, en in ((1e9, "miliardi", "billions"), (1e6, "milioni", "millions"), (1e3, "migliaia", "thousands")):
        if top >= div * 1.5:
            return div, (t(f"{it} di {cur}", f"{cur} {en}") if cur else t(it, en))
    return 1.0, cur


def _change(c, p):
    if p is None or p == 0 or c is None:
        return "", None
    if (c < 0) != (p < 0) or p < 0:
        return "n/m", MUTED
    g = (c - p) / abs(p)
    return F.fmt_pct(g, signed=True), (UP if g >= 0 else DOWN)


def build(a: dict, theme: str = "neon") -> bytes:
    with using(a.get("lang") or "en"):
        dk = Deck(a, theme)
        dk.cover()
        dk.headline()
        dk.findings()
        if a.get("kind") == "market" or a.get("series"):
            dk.market()
        else:
            dk.results()
            dk.trend()
            dk.margins_and_balance()
            dk.cash()
            dk.highlights()
            dk.ratios()
        dk.understood()
        dk.checks()
        dk.how()
        buf = io.BytesIO()
        dk.prs.save(buf)
        return buf.getvalue()
