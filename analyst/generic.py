"""Untagged documents: PDF (KID, prospectus, factsheet, whitepaper, annual report) and plain HTML.

There are no XBRL tags here, so figures are found heuristically: every number on
the page is a candidate, labelled with the words before it on the same line (or
the table row it sits in) and ranked by financial keywords. The AI reader can pick
the pages to show from the full text (choose=...) and then names the figures that
matter (see reader.py), always checked against the page text.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from statistics import median
from typing import Callable, Optional

from lxml import etree, html as lxml_html

from . import ixbrl

KEYWORDS = {
    # weight 3: headline figures
    "ricavi": 3, "fatturato": 3, "revenue": 3, "revenues": 3, "net sales": 3, "utile netto": 3, "net income": 3, "net profit": 3,
    "risultato netto": 3, "ebitda": 3, "ebit": 3, "free cash flow": 3, "eps": 3, "per azione": 3, "per share": 3,
    "indicatore sintetico di rischio": 3, "summary risk indicator": 3, "sri": 3, "spese correnti": 3, "ongoing charges": 3,
    "ter": 3, "costi totali": 3, "total costs": 3, "cedola": 3, "coupon": 3, "rendimento": 3, "yield": 3, "nav": 3,
    "total supply": 3, "max supply": 3, "market cap": 3, "capitalizzazione": 3,
    # weight 2
    "utile": 2, "profit": 2, "margine": 2, "margin": 2, "cassa": 2, "cash": 2, "debito": 2, "debt": 2, "indebitamento": 2,
    "patrimonio": 2, "equity": 2, "dividend": 2, "dividendo": 2, "performance": 2, "return": 2, "scenario": 2, "costi": 2,
    "costs": 2, "commission": 2, "fee": 2, "fees": 2, "volatilit": 2, "rischio": 2, "risk": 2, "scadenza": 2, "maturity": 2,
    "prezzo": 2, "price": 2, "supply": 2, "token": 2, "emission": 2, "crescita": 2, "growth": 2, "perdita": 2, "loss": 2,
    "attivo": 2, "assets": 2, "liabilities": 2, "passivit": 2, "investimenti": 2, "capex": 2, "operating": 2, "operativ": 2,
    # weight 1
    "totale": 1, "total": 1, "anno": 1, "year": 1, "periodo": 1, "period": 1, "netto": 1, "net": 1, "lordo": 1, "gross": 1,
}
NUM_RE = re.compile(r"^[(\-−–+]?(?:[€$£¥]|EUR|USD)?\s?\d[\d.,'’ ]*%?\)?$")
INLINE_NUM = re.compile(r"(?<![\w.,])[(\-−–+]?(?:[€$£¥]\s?)?\d{1,3}(?:[.,'’ ]\d{3})+(?![\d])(?:[.,]\d+)?%?\)?|(?<![\w.,])[(\-−–+]?(?:[€$£¥]\s?)?\d+(?:[.,]\d+)?%?\)?")
MONTH_END = re.compile(r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
                       r"|gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\.?\s*$", re.I)
MAX_PAGES_SHOWN = 8
MAX_FACTS_PAGE = 400
# choose(all page texts) -> 0-based indexes of the pages to show, or None for the built-in choice
Chooser = Optional[Callable[[list[str]], Optional[list[int]]]]


def parse_loose(t: str) -> Optional[float]:
    s = t.strip().replace("−", "-").replace("–", "-").replace("’", "").replace("'", "").replace(" ", "").replace(" ", "")
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = re.sub(r"[^\d.,]", "", s)
    if not s or not any(c.isdigit() for c in s):
        return None
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(",", ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        parts = s.split(sep)
        if len(parts) > 2 or (len(parts[-1]) == 3 and parts[0] not in ("0", "")):
            s = s.replace(sep, "")
        else:
            s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def is_figure(token: str, allow_digit: bool = False) -> bool:
    t = token.strip()
    if not NUM_RE.match(t) or len(t) > 24:
        return False
    digits = re.sub(r"\D", "", t)
    if not digits:
        return False
    # years, footnote marks and lone small integers are rarely the figures we want
    if re.fullmatch(r"(19|20)\d\d", t):
        return False
    if re.fullmatch(r"\d", t) and not allow_digit:
        return False
    return True


def score_label(label: str) -> int:
    lo = " " + label.lower() + " "
    best = 0
    for k, w in KEYWORDS.items():
        if len(k) <= 3:
            if re.search(rf"\b{re.escape(k)}\b", lo):
                best = max(best, w)
        elif k in lo:
            best = max(best, w)
    return best


# ---------------------------------------------------------------- PDF

def pdf_document(data: bytes, img_dir: Path, img_url: str, choose: Chooser = None) -> dict:
    """PDF -> page images + transparent word layer (so the spider can stand on words)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    n = len(pdf)
    if n == 0:
        raise ValueError("PDF senza pagine")
    # 1) choose the pages from plain text (fast); 2) word boxes only for the chosen pages
    sizes, texts = [], []
    for i in range(n):
        page = pdf[i]
        sizes.append(page.get_size())
        tp = page.get_textpage()
        texts.append(tp.get_text_range() or "")
        tp.close()
        page.close()
    picked = choose(texts) if choose else None
    chosen = sorted(set(picked)) if picked else best_pages(texts)
    pages_words = {}
    for i in chosen:
        page = pdf[i]
        tp = page.get_textpage()
        pages_words[i] = _words(tp, sizes[i][1])
        tp.close()
        page.close()

    img_dir.mkdir(parents=True, exist_ok=True)
    out_pages, facts, headings, page_text = [], [], [], []
    for i in chosen:
        w, h = sizes[i]
        scale = 96 / 72
        bmp = pdf[i].render(scale=2.0)
        bmp.to_pil().convert("RGB").save(img_dir / f"p{i + 1}.jpg", quality=88)   # JPEG: ~50x faster than PNG
        words = pages_words[i]
        figs = {id(f["word"]): f for f in _label_figures(words)}
        keep = sorted(figs.values(), key=lambda f: -f["score"])[:MAX_FACTS_PAGE]
        keep_ids = {id(f["word"]) for f in keep}
        hsize = median([wd["h"] for wd in words]) if words else 10
        spans = []
        line_heads = _heading_lines(words, hsize)
        for wd in words:
            style = (f"left:{wd['x'] * scale:.1f}px;top:{wd['y'] * scale:.1f}px;width:{wd['w'] * scale:.1f}px;"
                     f"height:{wd['h'] * scale:.1f}px;font-size:{wd['h'] * scale * 0.92:.1f}px")
            attrs = ""
            if id(wd) in keep_ids:
                f = figs[id(wd)]
                fid = len(facts)
                facts.append({"id": fid, "label": f["label"] or "Cifra", "value": f["value"], "display": wd["t"], "page": i + 1,
                              "kind": "num", "col": "Valore", "key": f["score"] >= 2, "score": f["score"]})
                attrs = f' class="w xf" data-f="{fid}"'
            elif id(wd) in line_heads:
                hid = len(headings)
                headings.append({"id": hid, "text": line_heads[id(wd)], "page": i + 1})
                attrs = f' class="w" data-h="{hid}"'
            else:
                attrs = ' class="w"'
            spans.append(f'<span{attrs} style="{style}">{html.escape(wd["t"])}</span>')
        out_pages.append({
            "n": i + 1,
            "html": (f'<div class="pdfpage" style="width:{w * scale:.0f}px;height:{h * scale:.0f}px">'
                     f'<img src="{img_url}/p{i + 1}.jpg" alt="">{"".join(spans)}</div>'),
        })
        page_text.append(" ".join(wd["t"] for wd in words))
    title = (pdf.get_metadata_dict().get("Title") or "").strip()
    pdf.close()
    return {"pages": out_pages, "facts": facts, "headings": headings, "page_text": page_text,
            "total_pages": n, "title": title, "css": PDF_CSS}


def best_pages(texts: list[str], n: int = MAX_PAGES_SHOWN) -> list[int]:
    """The first page and the pages that look like they hold the figures that matter (0-based)."""
    cand = sorted(((_score_text(txt), i) for i, txt in enumerate(texts)), reverse=True)
    first = next((i for i, t in enumerate(texts) if t.strip()), 0)
    return sorted({first} | {i for sc, i in cand[:n - 1] if sc > 0})


def _score_text(text: str) -> float:
    """How much a page looks like it holds the figures that matter (plain text, no layout)."""
    from . import statements
    score, nfig = 0.0, 0
    for line in text.splitlines():
        label: list[str] = []
        row_figs = 0
        for tok in line.split():
            if is_figure(tok, allow_digit=True):
                sc = score_label(" ".join(label[-9:]))
                if re.fullmatch(r"\d", tok) and sc < 3:
                    continue
                score += sc + (0.5 if tok.endswith("%") else 0)
                nfig += 1
                row_figs += 1
            elif not re.fullmatch(r"[\W\d]+", tok):
                label.append(tok)
        if row_figs and label and statements.match(" ".join(label)):
            score += 2                                     # a financial statement row
    return score + 0.1 * nfig


def _words(tp, page_h: float) -> list[dict]:
    n = tp.count_chars()
    if n <= 0:
        return []
    text = tp.get_text_range(0, n)
    per_char = len(text) != n
    words, cur, box = [], [], None

    def flush():
        nonlocal cur, box
        if cur and box:
            t = "".join(cur).strip()
            if t:
                x0, y0, x1, y1 = box
                words.append({"t": t, "x": x0, "y": page_h - y1, "w": max(x1 - x0, 1), "h": max(y1 - y0, 4)})
        cur, box = [], None

    for i in range(n):
        ch = tp.get_text_range(i, 1) if per_char else text[i]
        if not ch or ch.isspace() or ch in "\r\n\x02":
            flush()
            continue
        l, b, r, t = tp.get_charbox(i, loose=True)
        if r - l <= 0 and t - b <= 0:
            continue
        if box:
            bh = max(box[3] - box[1], t - b, 1)
            cy = (b + t) / 2
            if l - box[2] > 0.8 * bh or not (box[1] - 1 <= cy <= box[3] + 1):
                flush()
        cur.append(ch)
        box = [l, b, r, t] if box is None else [min(box[0], l), min(box[1], b), max(box[2], r), max(box[3], t)]
    flush()
    return words


def _lines(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for wd in sorted(words, key=lambda w: (round(w["y"] + w["h"] / 2), w["x"])):
        cy = wd["y"] + wd["h"] / 2
        for ln in lines[-4:]:
            ref = ln[0]
            if abs(ref["y"] + ref["h"] / 2 - cy) < 0.5 * min(ref["h"], wd["h"]):
                ln.append(wd)
                break
        else:
            lines.append([wd])
    for ln in lines:
        ln.sort(key=lambda w: w["x"])
    return lines


def _label_figures(words: list[dict]) -> list[dict]:
    out = []
    lines = _lines(words)
    for li, ln in enumerate(lines):
        # a 1-2 digit number on a row of formatted amounts is a note reference, not a figure
        amounts = sum(1 for w in ln if is_figure(w["t"]) and re.search(r"\d[.,]\d", w["t"]))
        for k, wd in enumerate(ln):
            if not is_figure(wd["t"], allow_digit=True):
                continue
            if amounts >= 2 and re.fullmatch(r"\d{1,2}", wd["t"]):
                continue
            if k > 0 and re.fullmatch(r"\d{1,2},?", wd["t"]) and MONTH_END.search(ln[k - 1]["t"]):
                continue                                  # "June 30": a date, not a figure
            label_words = [w["t"] for w in ln[:k] if not is_figure(w["t"]) and not re.fullmatch(r"[\W\d]+", w["t"])][-9:]
            label = " ".join(label_words)
            if not label and li > 0:
                label = " ".join(w["t"] for w in lines[li - 1] if not is_figure(w["t"]))[:80]
            v = parse_loose(wd["t"])
            if v is None:
                continue
            sc = score_label(label)
            if re.fullmatch(r"\d", wd["t"]) and sc < 3:
                continue
            if wd["t"].endswith("%"):
                sc += 0.5
            out.append({"word": wd, "label": label[:90], "value": v, "score": sc})
    return out


def _heading_lines(words: list[dict], hsize: float) -> dict[int, str]:
    out = {}
    for ln in _lines(words):
        t = " ".join(w["t"] for w in ln)
        if ln[0]["h"] >= hsize * 1.35 and 4 <= len(t) <= 90 and sum(c.isalpha() for c in t) >= 0.6 * len(t):
            out[id(ln[0])] = t
        if len(out) >= 6:
            break
    return out


PDF_CSS = """
.pdfpage{position:relative;background:#fff;margin:0 auto}
.pdfpage img{position:absolute;left:0;top:0;width:100%;height:100%;user-select:none;pointer-events:none}
.pdfpage .w{position:absolute;color:transparent;white-space:pre;line-height:1;font-family:sans-serif;overflow:hidden}
"""


# ---------------------------------------------------------------- HTML (no XBRL tags)

def html_document(data: bytes, base_url: Optional[str], choose: Chooser = None) -> dict:
    """Plain HTML: pages, the figures on the pages shown, and the statement tables read with their periods.

    choose(all page texts, table metrics) may pick the pages to show (0-based); the pages holding the
    headline figures are always among them."""
    from . import tables
    from .i18n import lang
    doc = ixbrl.parse(data, base_url)          # sanitises and splits pages; no facts in plain HTML
    frags = [lxml_html.fragment_fromstring(page or "<div></div>", create_parent="div") for page in doc.pages]
    tbls = [tb for pi, fr in enumerate(frags, start=1) for tb in tables.page_tables(fr, pi)]
    fin = tables.extract(tbls, lang())

    key_pages: list[int] = []
    for k in ("revenue", "net_income", "cfo", "total_assets", "eps_diluted", "cash", "operating_income"):
        mm = fin["metrics"].get(k)
        if mm and mm["cur"]["page"] - 1 not in key_pages:
            key_pages.append(mm["cur"]["page"] - 1)
    picked = choose(doc.page_text, fin, doc.page_labels) if choose else None
    if not picked:
        picked = best_pages(doc.page_text)
    shown = list(dict.fromkeys(key_pages[:4] + sorted(picked)))[:MAX_PAGES_SHOWN + 2]
    chosen = sorted({p + 1 for p in shown if 0 <= p < len(frags)})

    cell_of = {}                               # td -> (table, column) of the tables on the pages shown
    for tb in tbls:
        if tb.page in chosen:
            for r in tb.rows:
                for c, cl in r.cells.items():
                    cell_of[id(cl.el)] = (tb, tb.columns.get(c), r.label)
    facts, pages_out = [], []
    for pi in chosen:
        frag = frags[pi - 1]
        figs = _wrap_numbers(frag)
        figs.sort(key=lambda f: -f["score"])
        keep = figs[:MAX_FACTS_PAGE]
        keep_el = {id(f["el"]) for f in keep}
        for f in figs:
            el = f["el"]
            if id(el) not in keep_el:
                _unwrap(el)
                continue
            fid = len(facts)
            el.set("data-f", str(fid))
            td = next((a for a in el.iterancestors() if isinstance(a.tag, str) and a.tag.lower() in ("td", "th")), None)
            tb, col, row_label = cell_of.get(id(td), (None, None, ""))
            pct = bool(tb and (tb.percent or f["text"].endswith("%")))
            period = tables.period_label(col.months if not col.instant else None, col.end, lang()) if col and col.end and not col.skip else ""
            label = row_label or f["label"] or "Cifra"
            facts.append({"id": fid, "label": label + (" (% " + ("dei ricavi" if lang() == "it" else "of revenue") + ")" if tb and tb.percent else ""),
                          "value": f["value"], "display": f["text"], "page": pi, "period": period, "pct": pct,
                          "kind": "num", "col": "Valore", "key": f["score"] >= 2 and not (tb and tb.percent), "score": f["score"]})
        inner = "".join(etree.tostring(c, method="html", encoding="unicode", with_tail=True) for c in frag)
        pages_out.append({"n": pi, "html": (frag.text and html.escape(frag.text) or "") + inner})

    # the statement figures become facts the spider reads: link each table cell to its figure
    for mm in fin["metrics"].values():
        for which in ("cur", "prev"):
            o = mm.get(which)
            if not o:
                continue
            el = o.pop("el", None)
            span = next((x for x in el.iter() if isinstance(x.tag, str) and x.get("data-f") is not None), None) if el is not None else None
            o.update(id=int(span.get("data-f")) if span is not None and o["page"] in chosen else None, concept="", unit="")
    used = set(re.findall(r'class="([^"]+)"', "".join(p["html"] for p in pages_out)))
    used = {c for cl in used for c in cl.split()}
    headings = [h for h in doc.headings if h["page"] in chosen]
    return {"pages": pages_out, "facts": facts, "headings": headings,
            "page_text": [doc.page_text[p["n"] - 1] for p in pages_out], "all_text": doc.page_text, "total_pages": len(doc.pages),
            "title": "", "css": ixbrl.filter_css(doc.css, used), "info": doc.info, "fin": fin,
            "page_labels": {i + 1: lb for i, lb in enumerate(doc.page_labels) if lb}}


def _unwrap(el):
    parent = el.getparent()
    text = (el.text or "") + (el.tail or "")
    prev = el.getprevious()
    if prev is not None:
        prev.tail = (prev.tail or "") + text
    else:
        parent.text = (parent.text or "") + text
    parent.remove(el)


def _before(s: str, a: int, el, where: str) -> str:
    """Up to 30 characters printed just before a number (text nodes split by layout included)."""
    ctx = s[:a]
    if not ctx.strip():
        if where == "tail":
            ctx = "".join(el.itertext())
        else:
            prev = el.getprevious()
            ctx = "".join(prev.itertext()) + (prev.tail or "") if prev is not None else (el.getparent().text or "" if el.getparent() is not None else "")
    return ctx[-30:]


def _noise(s: str, a: int, b: int, tok: str, el, where: str) -> bool:
    """Numbers that are not figures: days of a date, footnote marks, par values."""
    before = _before(s, a, el, where)
    if re.fullmatch(r"\d{1,2},?", tok) and MONTH_END.search(before):
        return True                                       # "June 30"
    if re.fullmatch(r"\(\d{1,2}\)", tok):
        if before[-1:].isalnum() or before[-1:] in (")", "’", "'", "%"):
            return True                                   # "Net loss(2)"
        cell = next((x for x in [el] + list(el.iterancestors()) if isinstance(x.tag, str) and x.tag.lower() in ("td", "th")), None)
        if cell is None or re.sub(r"[\s$€£\xa0]", "", "".join(cell.itertext())) != tok:
            return True                                   # "(1)" in running text is a note, in a cell alone it is −1
    if re.search(r"par value( of)?\s*$", before, re.I) or re.match(r"\s*par value", s[b:b + 14], re.I):
        return True
    if tok.endswith(")") and not tok.startswith("(") or re.search(r"\b(note|nota|item|section|rule|page)\s*$", before, re.I):
        return True                                       # "(Note 13)", "Item 7"
    if re.fullmatch(r"\(\d{3}\)", tok) and re.match(r"\s?\d{3}[-.\s]\d{4}", s[b:b + 10]):
        return True                                       # phone number "(650) 555-0100"
    in_cell = any(isinstance(x.tag, str) and x.tag.lower() in ("td", "th") for x in [el] + list(el.iterancestors()))
    if not in_cell and re.fullmatch(r"\d{5,}", tok):
        return True                                       # ZIP codes, registration numbers: figures carry separators
    return False


def _wrap_numbers(root) -> list[dict]:
    """Wrap every figure in a text node with <span class="xf">; return them with a label."""
    figs = []
    targets = []
    for el in root.iter():
        if not isinstance(el.tag, str) or el.tag in ("style", "script", "svg"):
            continue
        if el.text and re.search(r"\d", el.text):
            targets.append((el, "text"))
        if el.tail and re.search(r"\d", el.tail) and el is not root:
            targets.append((el, "tail"))
    for el, where in targets:
        s = el.text if where == "text" else el.tail
        pieces, last = [], 0
        for m in INLINE_NUM.finditer(s):
            tok = m.group().strip()
            if not is_figure(tok) or _noise(s, m.start(), m.end(), tok, el, where):
                continue
            pieces.append((m.start(), m.end(), tok))
        if not pieces:
            continue
        spans = []
        before = s[:pieces[0][0]]
        for k, (a, b, tok) in enumerate(pieces):
            sp = etree.Element("span")
            sp.set("class", "xf")
            sp.text = s[a:b]
            nxt = pieces[k + 1][0] if k + 1 < len(pieces) else len(s)
            sp.tail = s[b:nxt]
            spans.append((sp, s[:a], tok))
        if where == "text":
            el.text = before
            for idx, (sp, _, _) in enumerate(spans):
                el.insert(idx, sp)
        else:
            parent = el.getparent()
            el.tail = before
            pos = parent.index(el)
            for idx, (sp, _, _) in enumerate(spans):
                parent.insert(pos + 1 + idx, sp)
        for sp, pre, tok in spans:
            label = ixbrl._row_label(sp)
            if not label:
                words = re.findall(r"[^\W\d_][\w'’%-]*", pre)[-9:]
                label = " ".join(words)
            v = parse_loose(tok)
            if v is None:
                _unwrap(sp)
                continue
            sc = score_label(label) + (0.5 if tok.endswith("%") else 0)
            figs.append({"el": sp, "label": label[:90], "value": v, "text": tok, "score": sc})
    return figs
