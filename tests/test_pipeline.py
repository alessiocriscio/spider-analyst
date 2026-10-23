"""Offline tests on synthetic documents (fictional companies, made-up numbers).

Run:  .venv/bin/python -m pytest -q
The PDF fixture needs reportlab (test-only): pip install reportlab
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
FIX = HERE / "fixtures"

import make_fixtures  # noqa: E402
from analyst import ai, financials as F, generic, ixbrl, market, pipeline, sources  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def fixtures(tmp_path_factory):
    FIX.mkdir(exist_ok=True)
    (FIX / "sec_10k.htm").write_text(make_fixtures.sec(), encoding="utf-8")
    (FIX / "esef.xhtml").write_text(make_fixtures.esef(), encoding="utf-8")
    pipeline.DOCS = tmp_path_factory.mktemp("docs")


def parse(name):
    return ixbrl.parse((FIX / name).read_bytes(), "https://www.sec.gov/Archives/edgar/data/1/x/")


def test_sec_pages_and_sanitising():
    d = parse("sec_10k.htm")
    assert len(d.pages) == 5
    html = "".join(d.pages)
    assert "<script" not in html and "onerror" not in html and "javascript:" not in html
    assert "/api/asset?u=https%3A%2F%2Fwww.sec.gov" in html
    assert d.info["DocumentPeriodEndDate"] == "June 30, 2025"


def test_sec_metrics_checks_card():
    d = parse("sec_10k.htm")
    x = F.extract(d)
    m = x["metrics"]
    assert x["currency"] == "USD"
    assert m["revenue"]["cur"]["value"] == 120e9 and m["revenue"]["prev"]["value"] == 100e9
    assert m["revenue"]["cur"]["page"] == 3          # statement, not the segment mention on p. 2
    assert m["eps_diluted"]["cur"]["value"] == 5.0
    dv = F.derive(m)
    assert dv["cur"]["fcf"] == 45e9
    assert all(c["ok"] for c in F.checks(m))
    card = {t["key"]: t for t in F.card(m, dv, "USD")}
    assert card["revenue"]["display"] == "$120 mld" and card["revenue"]["yoy_display"] == "+20,0%"
    assert card["fcf"]["pages"] == [5]


def test_esef_comma_decimals_and_ifrs():
    d = parse("esef.xhtml")
    assert len(d.pages) == 4
    m = F.extract(d)["metrics"]
    assert m["revenue"]["cur"]["value"] == 6_677_000_000
    assert m["eps_diluted"]["cur"]["value"] == pytest.approx(8.30)
    assert m["net_income"]["cur"]["value"] == 1_490_000_000      # attributable to owners first


def test_italian_formatting():
    assert F.fmt_money(1.234e9, "EUR") == "€1,2 mld"
    assert F.fmt_pct(-0.0712, signed=True) == "−7,1%"
    assert F.art("11,8%") == "dell'11,8%" and F.art("20,0%") == "del 20,0%" and F.art("8%", False) == "l'8%"


def test_generic_number_parsing():
    assert generic.parse_loose("1.234.567,89") == pytest.approx(1234567.89)
    assert generic.parse_loose("1,234,567.89") == pytest.approx(1234567.89)
    assert generic.parse_loose("(2,5%)") == -2.5
    assert not generic.is_figure("2025")


def test_ai_validation_drops_invented_numbers():
    data = {"a": {"label": "Ricavi", "display": "$120 mld", "pages": [3]}, "b": {"label": "Crescita", "display": "+20,0%", "pages": [3]}}
    ok = ai.validate([{"text": "Ricavi a $120 mld (+20,0%).", "ids": ["a", "b"]}], data)
    bad = ai.validate([{"text": "Ricavi a $121 mld.", "ids": ["a"]}, {"text": "Ricavi su.", "ids": ["zzz"]}], data)
    assert len(ok) == 1 and ok[0]["pages"] == [3] and bad == []


def test_market_sheet():
    from synth import series
    r = market.build(series())
    assert len(r["pages"]) == 4
    assert all(c["ok"] for c in r["checks"])
    assert {t["key"] for t in r["card"]} == {"price", "r1y", "vol", "mdd"}


def test_pipeline_upload_ixbrl():
    a = pipeline.run({"kind": "upload", "data": (FIX / "sec_10k.htm").read_bytes(), "name": "x.htm"}, lambda *_: None)
    assert a["kind"] == "ixbrl" and a["total_facts"] == 51
    assert 3 in [p["n"] for p in a["pages"]]
    view = (pipeline.DOCS / a["id"] / "view.html").read_text()
    assert 'data-f="1"' in view and "<script" not in view


def test_pdf(tmp_path):
    pytest.importorskip("reportlab")
    import make_pdf  # noqa: F401  (writes fixtures/kid.pdf)
    g = generic.pdf_document((FIX / "kid.pdf").read_bytes(), tmp_path, "/img")
    labels = {f["display"]: f["label"] for f in g["facts"]}
    assert labels["1,45%"] == "Spese correnti"
    assert labels["4"] == "Indicatore sintetico di rischio"
    assert (tmp_path / "p1.png").exists()


def test_sec_user_agent_is_generic_by_default(monkeypatch):
    monkeypatch.delenv("SPIDER_SEC_UA", raising=False)
    monkeypatch.setattr(sources, "config", lambda: {})
    assert "@" in sources.sec_user_agent() and "example.com" in sources.sec_user_agent()


def test_statement_labels_en_it():
    from analyst import statements as S
    assert S.match("Net sales") == "revenue" and S.match("Ricavi netti") == "revenue"
    assert S.match("Net income attributable to shareholders") == "net_income"
    assert S.match("Utile netto dell'esercizio") == "net_income"
    assert S.match("Net cash provided by operating activities") == "cfo"
    assert S.match("Flusso di cassa netto generato dalle attività operative") == "cfo"
    assert S.match("Purchases of property, plant and equipment") == "capex"
    assert S.match("Total shareholders’ equity") == "equity"
    assert S.match("Letter to shareholders") is None
    assert S.page_scale("(in millions of U.S. dollars)") == 1e6 and S.page_scale("(in migliaia di euro)") == 1e3


def test_english_pdf_annual_report():
    pytest.importorskip("reportlab")
    import make_pdf_en  # noqa: F401  (writes fixtures/annual_en.pdf)
    a = pipeline.run({"kind": "upload", "data": (FIX / "annual_en.pdf").read_bytes(), "name": "annual_en.pdf"}, lambda *_: None)
    card = {t["key"]: t for t in a["card"]}
    assert a["title"] == "Northwind Instruments Inc."
    assert card["revenue"]["yoy_display"] == "+11,2%" and card["eps_diluted"]["display"] == "$4,12"
    assert card["fcf"]["display"] == "$2,2 mld"           # 2,900 − 700 million
    assert all(c["ok"] for c in a["checks"]) and len(a["checks"]) >= 3


def test_english_html_table_report():
    html = b"""<html><body><h2>Consolidated Statement of Income</h2><p>(in thousands of euros)</p><table>
    <tr><td></td><td>2025</td><td>2024</td></tr>
    <tr><td>Revenue</td><td>500,000</td><td>400,000</td></tr>
    <tr><td>Operating profit</td><td>90,000</td><td>70,000</td></tr>
    <tr><td>Profit for the year</td><td>60,000</td><td>45,000</td></tr>
    <tr><td>Total assets</td><td>900,000</td><td>850,000</td></tr></table></body></html>"""
    a = pipeline.run({"kind": "upload", "data": html, "name": "report.html"}, lambda *_: None)
    assert a["cols"][1] == ["2025", "2024"]
    card = {t["key"]: t for t in a["card"]}
    assert a["currency"] == "EUR" and card["revenue"]["display"] == "€500 mln" and card["revenue"]["yoy_display"] == "+25,0%"


def test_pdf_note_references_are_not_figures(tmp_path):
    pytest.importorskip("reportlab")
    import make_pdf_en  # noqa: F401
    g = generic.pdf_document((FIX / "annual_en.pdf").read_bytes(), tmp_path, "/img")
    assert not [f for f in g["facts"] if f["display"] in ("4", "9")]
