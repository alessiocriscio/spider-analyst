"""Layouts met in real filings (10-K, bank 10-Q, ESEF), rebuilt with made-up companies and numbers."""
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from analyst import ai, financials, ixbrl, pipeline, sources  # noqa: E402


@pytest.fixture
def no_ai(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "DOCS", tmp_path / "docs")
    monkeypatch.setattr(ai, "active", lambda: None)


def _pdf(path: Path, pages: list[list[tuple]]) -> bytes:
    """pages of (x, y, text, bold, right-aligned) lines."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=letter)
    for lines in pages:
        for x, y, s, bold, right in lines:
            c.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
            (c.drawRightString if right else c.drawString)(x, y, s)
        c.showPage()
    c.save()
    return path.read_bytes()


def _statement(title: str, unit: str, head: list[str], rows: list[tuple], above: str = "") -> list[tuple]:
    xs = [400, 470, 540][-len(head):]
    out = [(50, 740, title, True, False), (50, 725, unit, False, False)]
    if above:
        out.append((540, 712, above, True, True))
    out += [(x, 700, h, True, True) for x, h in zip(xs, head)]
    y = 680
    for label, *vals in rows:
        if "\n" in label:                                 # a label wrapped onto two lines
            first, label = label.split("\n")
            out.append((50, y, first, False, False))
            y -= 12
        out.append((50, y, label, False, False))
        out += [(x, y, v, False, True) for x, v in zip(xs, vals)]
        y -= 16
    return out


def test_10k_ascending_years_wrapped_label_and_cover(no_ai, tmp_path):
    pytest.importorskip("reportlab")
    cover = [(50, 740, "UNITED STATES", True, False), (50, 725, "SECURITIES AND EXCHANGE COMMISSION", True, False),
             (50, 700, "FORM 10-K", True, False), (50, 680, "Commission file number 1-12345", False, False),
             (50, 650, "Example Outdoor Corp.", True, False), (50, 638, "(Exact name of registrant as specified in its charter)", False, False),
             (50, 610, "Common Stock, par value $.01 per share EXO New York Stock Exchange", False, False),
             (50, 598, "(17 CFR 240.13e-4(c)) Pre-commencement communications pursuant to Rule 13e-4(c)", False, False)]
    years = ["2022", "2023", "2024"]                     # oldest first, as some filers print them
    ops = _statement("CONSOLIDATED STATEMENTS OF OPERATIONS", "(Millions, except per share data)", years, [
        ("Net sales", "$1,000", "$1,100", "$1,260"), ("Total operating expenses", "900", "980", "1,110"),
        ("Operating income", "100", "120", "150"), ("Income before income taxes", "95", "115", "140"),
        ("Provision for income taxes", "20", "25", "30"), ("Net income", "75", "90", "110"),
        ("Diluted earnings per share attributable to Example", "0.75", "0.90", "1.10"),
        ("Weighted-average diluted shares", "100", "100", "100")], above="Year Ended December 31,")
    bs = _statement("CONSOLIDATED BALANCE SHEETS", "(Millions)", ["2023", "2024"], [
        ("Total assets", "2,000", "2,300"), ("Total liabilities", "1,200", "1,350"), ("Total stockholders’ equity", "800", "950")],
        above="December 31,")
    cf = _statement("CONSOLIDATED STATEMENTS OF CASH FLOWS", "(Millions)", years, [
        ("Net cash provided by operating activities", "150", "170", "200"),
        ("Purchases of property and equipment", "(50)", "(60)", "(70)"),
        ("Net cash used in investing activities", "(60)", "(70)", "(80)"),
        ("Net cash used in financing activities", "(40)", "(50)", "(60)"),
        ("Effect of exchange\nrate changes on cash", "(2)", "(3)", "(6)"),
        ("Net increase in cash and cash equivalents", "48", "47", "54")], above="Year Ended December 31,")
    data = _pdf(tmp_path / "exo.pdf", [cover, ops, bs, cf])
    a = pipeline.run({"kind": "upload", "data": data, "name": "exo-10k.pdf", "lang": "en"}, lambda *_: None)
    assert a["title"] == "Example Outdoor Corp."
    card = {t["key"]: t for t in a["card"]}
    assert card["revenue"]["display"] == "$1.3B" and card["revenue"]["yoy_display"] == "+14.5%" and card["revenue"]["vs"] == "FY2023"
    assert card["net_income"]["display"] == "$110M" and card["eps_diluted"]["display"] == "$1.10"
    assert card["fcf"]["display"] == "$130M"
    names = {c["name"]: c["ok"] for c in a["checks"]}
    assert all(names.values()) and any(n.startswith("Operating + investing") for n in names)
    assert not [f for f in a["facts"].values() if f["display"].startswith("(17")]


def test_bank_quarter_codes_compare_with_the_same_quarter(no_ai, tmp_path):
    pytest.importorskip("reportlab")
    page = _statement("CONSOLIDATED STATEMENTS OF INCOME", "(in millions, except per share data)", ["1Q24", "4Q23", "1Q23"], [
        ("Total net revenue", "40,000", "38,000", "36,000"), ("Net income", "12,000", "10,000", "11,000"),
        ("Diluted earnings per share", "4.00", "3.30", "3.60")])
    data = _pdf(tmp_path / "bank.pdf", [[(50, 740, "Example Bancorp", True, False)], page])
    a = pipeline.run({"kind": "upload", "data": data, "name": "bank-10q.pdf", "lang": "en"}, lambda *_: None)
    card = {t["key"]: t for t in a["card"]}
    assert card["revenue"]["yoy_display"] == "+11.1%" and card["revenue"]["vs"] == "1Q23"
    assert a["fin"]["periods"]["flow"] == ["1Q24", "1Q23"]


def _m(**vals):
    return {k: {"cur": {"value": v, "page": 1}} for k, v in vals.items()}


def test_cash_check_with_held_for_sale_line_and_unread_fx():
    ok = financials.checks(_m(cfo=-4650, cfi=-5897, cff=7574, fx_effect=-1278, cash_hfs=297, cash_change=-3954))
    assert [c["ok"] for c in ok] == [True]
    gap = financials.checks(_m(cfo=6322.2, cfi=-3583.4, cff=-2807.6, cash_change=-101.2))
    assert not gap[0]["ok"] and "effetto cambi o perimetro" in gap[0]["detail"]


def test_esef_page_containers_and_reflowed_text():
    pf = "".join(f'<div class="pf" id="p{i}"><p>Page {i} text</p></div>' for i in range(1, 6))
    d = ixbrl.parse(f'<html><body><div class="wrapper">{pf}</div></body></html>'.encode())
    assert len(d.pages) == 5
    flow = "".join(f"<h2>Section {i}</h2>" + "<p>" + "Narrative text. " * 120 + "</p>" for i in range(30))
    d = ixbrl.parse(f"<html><body><div>{flow}</div></body></html>".encode())
    assert len(d.pages) > 5 and all(len(p) < 20000 for p in d.pages)


def test_busy_server_is_retried_and_huge_documents_refused(tmp_path, monkeypatch):
    hits = []

    def handler(req):
        hits.append(1)
        if len(hits) < 3:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, content=b"x" * 2000)

    monkeypatch.setattr(sources, "CACHE", tmp_path)
    monkeypatch.setattr(sources, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    assert sources.fetch("https://filings.xbrl.org/x.xhtml", ttl=None) == b"x" * 2000 and len(hits) == 3
    with pytest.raises(sources.SourceError):
        sources.fetch("https://filings.xbrl.org/y.xhtml", ttl=None, max_bytes=1000)
    assert sources.MAX_DOC >= 400_000_000
