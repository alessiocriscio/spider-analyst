"""Untagged filings read from their tables: pages, periods, comparisons, checks, noise (synthetic S-1, no AI)."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import make_s1  # noqa: E402
from analyst import ai, ixbrl, pdfreport, pipeline, tables  # noqa: E402

S1 = make_s1.s1().encode()


@pytest.fixture
def no_ai(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "DOCS", tmp_path / "docs")
    monkeypatch.setattr(ai, "active", lambda: None)


def test_pages_and_printed_numbers():
    d = ixbrl.parse(S1)
    assert len(d.pages) == 6
    assert d.page_labels == ["", "1", "2", "3", "F-2", "F-3"]
    assert "Table of Contents" not in [h["text"] for h in d.headings]          # running header, not a heading
    assert d.info["DocumentTitle"] == "Example AI, PBC - S-1"
    assert "tracker" not in "".join(d.pages)


def test_column_periods():
    assert tables._period("Six Months Ended June 30, 2026 (unaudited)")[:3] == (6, tables.date(2026, 6, 30), False)
    assert tables._period("As of December 31, 2025")[2] is True
    assert tables._period("$ Change")[3] and tables._period("Pro Forma As Adjusted")[3]
    assert tables.period_label(6, tables.date(2026, 6, 30), "en") == "H1 2026"


def test_latest_period_against_the_same_period_a_year_earlier(no_ai):
    a = pipeline.run({"kind": "upload", "data": S1, "name": "s1.htm", "lang": "en"}, lambda *_: None)
    assert a["title"] == "Example AI, PBC" and a["subtitle"].startswith("Form S-1")
    card = {t["key"]: t for t in a["card"]}
    assert card["revenue"]["display"] == "$16.3B" and card["revenue"]["exact"] == "$16,286 million"
    assert card["revenue"]["yoy_display"] == "+1,300%" and card["revenue"]["vs"] == "H1 2025"
    assert card["net_income"]["en"] == "Net loss" and card["net_income"]["exact"] == "−$80,748 million"
    assert card["net_income"]["yoy_display"] == "" and card["net_income"]["prev_display"] == "−$13.0B"
    assert card["eps_diluted"]["display"] == "−$39.88"
    assert card["fcf"]["exact"] == "$3,447 million" and card["fcf"]["note"].startswith("computed")
    assert card["revenue"]["pages"] == [3] and a["page_labels"]["3"] == "2"
    assert a["fin"]["periods"] == {"flow": ["H1 2026", "H1 2025"], "stock": ["Jun 30, 2026", "Dec 31, 2025"]}
    names = {c["name"]: c["ok"] for c in a["checks"]}
    assert len(names) == 5 and all(names.values())
    assert "Assets = liabilities + redeemable preferred + equity" in names


def test_noise_is_not_read_as_figures(no_ai):
    a = pipeline.run({"kind": "upload", "data": S1, "name": "s1.htm", "lang": "en"}, lambda *_: None)
    shown = [f["display"] for f in a["facts"].values()]
    for noise in ("(2)", "30", "94104", "90375", "(650)", "13)", "$0.000", "$0.00001"):
        assert noise not in shown, noise
    pct = [f for f in a["facts"].values() if f["label"].startswith("Revenue (% of revenue)")]
    assert not pct or all(f["value_fmt"].endswith("%") and not f["key"] for f in pct)


def test_report_has_no_lists_of_raw_figures(no_ai):
    a = pipeline.run({"kind": "upload", "data": S1, "name": "s1.htm", "lang": "it"}, lambda *_: None)
    pdf = pdfreport.build(json.loads(json.dumps(a)), "ocean")
    assert pdf[:5] == b"%PDF-"
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf)
    text = " ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "Cifre lette" not in text and "Altre cifre lette" not in text
    assert "I numeri in sintesi" in text and "Controlli aritmetici" in text and "p. F-3" in text
    assert "1° sem. 2026" in text


def test_report_theme_is_applied(no_ai, monkeypatch):
    import server
    a = pipeline.run({"kind": "upload", "data": S1, "name": "s1.htm", "lang": "en"}, lambda *_: None)
    client = TestClient(server.app, base_url="http://127.0.0.1:8765")
    r = client.get(f"/api/doc/{a['id']}/report.pdf", params={"theme": "midnight"})
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    assert client.get(f"/api/doc/{a['id']}/report.pdf", params={"theme": "nope"}).status_code == 200
