"""Inline XBRL (iXBRL) document -> pages, tagged facts and headings.

Works for SEC filings (10-K, 10-Q, 20-F, 40-F; us-gaap / ifrs-full taxonomies) and
European ESEF annual reports (ifrs-full). Every number the report uses is an
ix:nonFraction tag in the filing, so its value AND its exact place on the page are
known without guessing: the spider walks to the very element that holds it.

Output HTML is sanitised: no scripts, no event handlers, no external frames.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote, urljoin

from lxml import etree, html as lxml_html

REMOVE_TAGS = {"script", "noscript", "iframe", "object", "embed", "frame", "frameset", "applet", "base", "link", "meta", "form", "input", "button", "select", "textarea"}
BLOCK_TAGS = {"div", "p", "table", "tr", "td", "th", "ul", "ol", "li", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}
DEI_KEYS = {
    "DocumentType", "DocumentPeriodEndDate", "DocumentFiscalYearFocus", "DocumentFiscalPeriodFocus",
    "EntityRegistrantName", "TradingSymbol", "EntityCentralIndexKey", "CurrentFiscalYearEndDate",
    "NameOfReportingEntityOrOtherMeansOfIdentification", "DescriptionOfPresentationCurrency",
    "DomicileOfEntity", "LegalFormOfEntity", "CountryOfIncorporation",
}
ASSET_HOSTS = ("www.sec.gov", "sec.gov", "filings.xbrl.org")


@dataclass
class Fact:
    id: int
    concept: str          # e.g. "us-gaap:Revenues"
    local: str            # e.g. "Revenues"
    context: str
    unit: Optional[str]
    value: Optional[float]
    display: str          # text exactly as printed
    decimals: Optional[str]
    page: int = 0
    row_label: str = ""   # first text cell of the table row holding the figure


@dataclass
class Context:
    id: str
    start: Optional[str]
    end: Optional[str]
    instant: Optional[str]
    dimensional: bool

    @property
    def period_end(self) -> Optional[str]:
        return self.instant or self.end

    @property
    def days(self) -> Optional[int]:
        if not (self.start and self.end):
            return None
        from datetime import date
        a, b = date.fromisoformat(self.start[:10]), date.fromisoformat(self.end[:10])
        return (b - a).days


@dataclass
class IxDoc:
    pages: list[str]
    css: str
    facts: list[Fact]
    contexts: dict[str, Context]
    units: dict[str, str]
    info: dict[str, str]
    info_ctx: dict[str, str]
    headings: list[dict]
    page_text: list[str]
    page_fact_count: list[int]
    warnings: list[str] = field(default_factory=list)

    def fact(self, fid: int) -> Fact:
        return self.facts[fid]


def _local(tag) -> str:
    if not isinstance(tag, str):
        return ""
    tag = tag.rsplit("}", 1)[-1]
    return tag.split(":", 1)[-1] if ":" in tag else tag


def _prefix(tag) -> str:
    """'ix' for {inlineXBRL ns}x or 'ix:x' (html-parser fallback), else ''."""
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        nsuri = tag[1:].split("}", 1)[0]
        if "inlineXBRL" in nsuri:
            return "ix"
        if nsuri.endswith("/instance") or "xbrl.org/2003/instance" in nsuri:
            return "xbrli"
        if "xhtml" in nsuri:
            return ""
        return "other"
    if ":" in tag:
        return tag.split(":", 1)[0].lower()
    return ""


def _text(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


BLOCK_TAGS = {"td", "th", "tr", "p", "div", "li", "br", "table", "section", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd"}


def _block_text(el) -> str:
    """Text with a space between cells and blocks, so "Revenue | 3,400 | 1,100" never reads as "Revenue3,4001,100"."""
    parts = []
    for ev, e in etree.iterwalk(el, events=("start", "end")):
        block = isinstance(e.tag, str) and _local(e.tag).lower() in BLOCK_TAGS
        if ev == "start":
            if block:
                parts.append(" ")
            if isinstance(e.tag, str) and e.text:
                parts.append(e.text)
        else:
            if block:
                parts.append(" ")
            if e is not el and e.tail:
                parts.append(e.tail)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def parse_number(text: str, fmt: str) -> Optional[float]:
    f = (fmt or "").split(":")[-1].lower()
    t = (text or "").strip().replace(" ", "").replace(" ", "")
    if "zero" in f or t in ("—", "–", "-", "‒"):
        return 0.0
    if not t:
        return None
    if "comma" in f and "decimal" in f:          # 1.234,56
        t = t.replace(".", "").replace(",", ".")
    elif "space" in f or "apos" in f:
        t = t.replace("'", "").replace(",", ".") if "comma" in f else t.replace("'", "")
    else:                                         # 1,234.56
        t = t.replace(",", "")
    m = re.search(r"\d+(?:\.\d+)?", t)
    return float(m.group()) if m else None


def _load_tree(data: bytes):
    opts = dict(huge_tree=True, resolve_entities=False, no_network=True, remove_comments=True)
    try:
        root = etree.fromstring(data, etree.XMLParser(**opts))
    except etree.XMLSyntaxError:
        root = None
        # tagged documents need the XML namespaces even when slightly malformed; plain HTML (old EDGAR filings,
        # S-1s with unclosed <hr>, <br>, <p>) goes to the HTML parser, or the XML recovery nests whole pages in a tag
        if b"ix:" in data[:3_000_000]:
            try:
                root = etree.fromstring(data, etree.XMLParser(recover=True, **opts))
            except etree.XMLSyntaxError:
                root = None
    if root is None or _local(root.tag).lower() != "html" or root.find(".//{*}body") is None:
        root = lxml_html.document_fromstring(data)
    return root


def _contexts_units(root) -> tuple[dict[str, Context], dict[str, str]]:
    contexts, units = {}, {}
    for el in root.iter():
        name = _local(el.tag)
        if name == "context":
            start = end = instant = None
            dims = False
            for d in el.iter():
                ln = _local(d.tag)
                if ln == "startDate":
                    start = (d.text or "").strip()
                elif ln == "endDate":
                    end = (d.text or "").strip()
                elif ln == "instant":
                    instant = (d.text or "").strip()
                elif ln in ("explicitMember", "typedMember"):
                    dims = True
            cid = el.get("id")
            if cid:
                contexts[cid] = Context(cid, start, end, instant, dims)
        elif name == "unit":
            meas = [(_local(m.tag), (m.text or "").strip()) for m in el.iter() if _local(m.tag) == "measure"]
            vals = [v.split(":")[-1] for _, v in meas]
            uid = el.get("id")
            if uid:
                units[uid] = "/".join(vals) if vals else uid
    return contexts, units


def _style_has_break(el, which: str) -> bool:
    s = (el.get("style") or "").lower().replace(" ", "")
    return f"page-break-{which}:always" in s or f"break-{which}:page" in s


PAGE_CLASS = re.compile(r"(^|\s)(pageview|page|pf|pagecontainer|page-container)(\s|$)", re.I)


def _page_like(el) -> bool:
    return bool(PAGE_CLASS.search(el.get("class") or ""))


def _group(kids: list) -> list[list]:
    marked = sum(_page_like(k) for k in kids)
    if marked >= 2 and marked >= 0.5 * len(kids):
        pages, pending = [], []
        for k in kids:
            if _page_like(k):
                pages.append(pending + [k])
                pending = []
            else:
                pending.append(k)
        if pending:
            (pages[-1].extend(pending) if pages else pages.append(pending))
        return pages
    pages: list[list] = [[]]
    for k in kids:
        before, after = _style_has_break(k, "before"), _style_has_break(k, "after")
        tag = _local(k.tag).lower()
        empty = not _text(k) and k.find(".//{*}img") is None and k.find(".//img") is None
        if (before or after) and (tag == "hr" or empty):
            if pages[-1]:
                pages.append([])
            continue
        if before and pages[-1]:
            pages.append([])
        pages[-1].append(k)
        if after:
            pages.append([])
    return [p for p in pages if p]


def _split_pages(body) -> list[list]:
    container = body
    for _ in range(5):
        kids = [k for k in container if isinstance(k.tag, str)]
        pages = _group(kids)
        if len(pages) >= 2:
            return pages
        if len(kids) != 1:
            break
        container = kids[0]
    # breaks nested deeper: use the parent that holds most of them
    breaks = [e for e in body.iter() if isinstance(e.tag, str) and (_style_has_break(e, "after") or _style_has_break(e, "before"))]
    if breaks:
        from collections import Counter
        parent, n = Counter(b.getparent() for b in breaks).most_common(1)[0]
        if parent is not None and n >= max(2, len(breaks) // 2):
            pages = _group([k for k in parent if isinstance(k.tag, str)])
            if len(pages) >= 2:
                return pages
    return [[k for k in body if isinstance(k.tag, str)]]


def _sanitize(root, base_url: Optional[str]):
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            continue
        name = _local(el.tag).lower()
        if name in REMOVE_TAGS and _prefix(el.tag) in ("", "other"):
            parent = el.getparent()
            if parent is not None:
                if el.tail:
                    prev = el.getprevious()
                    if prev is not None:
                        prev.tail = (prev.tail or "") + el.tail
                    else:
                        parent.text = (parent.text or "") + el.tail
                parent.remove(el)
            continue
        for a in list(el.attrib):
            al = a.lower()
            if "}" in a or ":" in a or al.startswith("on"):
                del el.attrib[a]
            elif al in ("href", "src") and el.attrib[a].strip().lower().startswith(("javascript:", "vbscript:")):
                del el.attrib[a]
        if name == "img" and el.get("src"):
            src = el.get("src")
            if not src.startswith("data:"):
                absu = urljoin(base_url or "", src)
                host = re.sub(r"^https?://([^/]+).*$", r"\1", absu)
                if host in ASSET_HOSTS:
                    el.set("src", "/api/asset?u=" + quote(absu, safe=""))
                else:
                    el.attrib.pop("src", None)
        if name == "a":
            el.attrib.pop("href", None)


def filter_css(css: str, used: set[str]) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        prelude = css[i:j].strip()
        if prelude.startswith("@import") or prelude.startswith("@charset"):
            k = css.find(";", i)
            i = k + 1 if 0 <= k < j else j
            if 0 <= k < j:
                continue
            prelude = css[i:j].strip()
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        body = css[j + 1:k - 1]
        if prelude.startswith(("@media", "@supports")):
            inner = filter_css(body, used)
            if inner.strip():
                out.append(f"{prelude}{{{inner}}}")
        elif prelude.startswith("@"):
            out.append(f"{prelude}{{{body}}}")
        else:
            classes = re.findall(r"\.(-?[_a-zA-Z][\w-]*)", prelude)
            if not classes or any(c in used for c in classes):
                out.append(f"{prelude}{{{body}}}")
        i = k
    return "\n".join(out)


def _row_label(el) -> str:
    tr = next((a for a in el.iterancestors() if isinstance(a.tag, str) and a.tag.lower() == "tr"), None)
    if tr is None:
        return ""
    for cell in tr:
        if not isinstance(cell.tag, str):
            continue
        t = _text(cell)
        if sum(c.isalpha() for c in t) >= 3:
            return t[:120]
    return ""


def parse(data: bytes, base_url: Optional[str] = None) -> IxDoc:
    root = _load_tree(data)
    contexts, units = _contexts_units(root)
    warnings: list[str] = []

    # header holds contexts/units and hidden facts: read, then drop
    for el in list(root.iter()):
        if isinstance(el.tag, str) and _prefix(el.tag) == "ix" and _local(el.tag).lower() == "header":
            el.getparent().remove(el)

    css_parts = []
    for el in list(root.iter()):
        if isinstance(el.tag, str) and _local(el.tag).lower() == "style":
            css_parts.append(el.text or "")
            el.getparent().remove(el)

    facts: list[Fact] = []
    info: dict[str, str] = {}
    info_ctx: dict[str, str] = {}
    for el in root.iter():
        if not isinstance(el.tag, str) or _prefix(el.tag) != "ix":
            continue
        ln = _local(el.tag).lower()
        if ln == "nonfraction":
            if el.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                continue
            concept = el.get("name") or ""
            disp = _text(el)
            val = parse_number(disp, el.get("format") or "")
            if val is not None:
                try:
                    val *= 10 ** int(el.get("scale") or 0)
                except ValueError:
                    pass
                if el.get("sign") == "-":
                    val = -val
            fid = len(facts)
            facts.append(Fact(fid, concept, concept.split(":")[-1], el.get("contextRef") or el.get("contextref") or "",
                              el.get("unitRef") or el.get("unitref"), val, disp, el.get("decimals")))
            el.set("data-f", str(fid))
        elif ln == "nonnumeric":
            key = (el.get("name") or "").split(":")[-1]
            if key in DEI_KEYS and key not in info:
                t = _text(el)
                if t and len(t) <= 200:
                    info[key] = t
                    info_ctx[key] = el.get("contextRef") or el.get("contextref") or ""

    # rename every element to a plain HTML tag
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        pre, ln = _prefix(el.tag), _local(el.tag)
        if pre == "ix":
            is_fact = el.get("data-f") is not None
            fid = el.get("data-f")
            el.attrib.clear()
            el.tag = "span"
            if is_fact:
                el.set("data-f", fid)
                el.set("class", "xf")
        elif pre in ("xbrli", "other"):
            el.tag = "span"
        else:
            el.tag = ln
    _sanitize(root, base_url)
    etree.cleanup_namespaces(root)

    for el in root.iter():
        if isinstance(el.tag, str) and el.get("data-f") is not None:
            facts[int(el.get("data-f"))].row_label = _row_label(el)

    body = root.find(".//body")
    if body is None:
        body = root
    groups = _split_pages(body)

    # headings: short bold lines outside tables
    headings: list[dict] = []
    hid = 0
    for pi, els in enumerate(groups, start=1):
        per_page = 0
        for top in els:
            for el in top.iter():
                if not isinstance(el.tag, str) or el.get("data-h") is not None:
                    continue
                tag = el.tag.lower()
                style = (el.get("style") or "").lower()
                bold = tag in ("b", "strong", "h1", "h2", "h3", "h4", "h5", "h6") or re.search(r"font-weight:\s*(bold|[6-9]00)", style)
                if not bold:
                    continue
                if any(isinstance(a.tag, str) and a.tag.lower() in ("td", "th", "table") for a in el.iterancestors()):
                    continue
                if any(isinstance(a.tag, str) and a.get("data-h") is not None for a in el.iterancestors()):
                    continue
                if any(isinstance(d.tag, str) and d.tag.lower() in BLOCK_TAGS for d in el.iterdescendants()):
                    continue
                t = _text(el)
                letters = sum(c.isalpha() for c in t)
                if not (4 <= len(t) <= 90) or letters < 0.6 * len(t) or not t[0].isalpha() or not t[0].isupper():
                    continue
                if headings and headings[-1]["text"] == t:
                    continue
                el.set("data-h", str(hid))
                headings.append({"id": hid, "text": t, "page": pi})
                hid += 1
                per_page += 1
                if per_page >= 8:
                    break
            if per_page >= 8:
                break

    pages, page_text, page_fact_count = [], [], []
    for pi, els in enumerate(groups, start=1):
        n = 0
        for top in els:
            for el in top.iter():
                if isinstance(el.tag, str):
                    f = el.get("data-f")
                    if f is not None:
                        facts[int(f)].page = pi
                        n += 1
        page_fact_count.append(n)
        page_text.append(re.sub(r"\s+", " ", " ".join(_block_text(t) for t in els)).strip())
        pages.append("".join(etree.tostring(t, method="html", encoding="unicode", with_tail=True) for t in els))

    if len(pages) < 2:
        warnings.append("Il documento non ha interruzioni di pagina riconoscibili: mostrato come pagina unica.")
    return IxDoc(pages, "\n".join(css_parts), facts, contexts, units, info, info_ctx, headings,
                 page_text, page_fact_count, warnings)
