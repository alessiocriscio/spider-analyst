"""Network layer against simulated SEC, filings.xbrl.org and Yahoo responses (shapes of the real APIs)."""
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from analyst import pipeline, sources  # noqa: E402

TICKERS = {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
           "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"}}
SUBMISSIONS = {"cik": "0001045810", "name": "NVIDIA CORP", "tickers": ["NVDA"], "filings": {"recent": {
    "accessionNumber": ["0001045810-26-000101", "0001045810-26-000052"], "filingDate": ["2026-08-27", "2026-02-25"],
    "reportDate": ["2026-07-26", "2026-01-25"], "form": ["10-Q", "10-K"],
    "primaryDocument": ["nvda-20260726.htm", "nvda-20260125.htm"], "isInlineXBRL": [1, 1]}}}
ESEF_ENTITIES = {"data": [{"type": "entity", "id": "1234", "attributes": {"identifier": "549300ZTFBTXS1XOSZ93", "name": "Ferrari N.V."}}]}
ESEF_FILINGS = {"data": [
    {"type": "filing", "id": "1", "attributes": {"period_end": "2024-12-31", "date_added": "2025-03-01 10:00:00",
                                                  "report_url": "/549300ZTFBTXS1XOSZ93/2024-12-31/ESEF/NL/0/ferrari-2024.xhtml", "error_count": 0}},
    {"type": "filing", "id": "2", "attributes": {"period_end": "2025-12-31", "date_added": "2026-03-01 10:00:00",
                                                  "report_url": "/549300ZTFBTXS1XOSZ93/2025-12-31/ESEF/NL/0/ferrari-2025.xhtml", "error_count": 0}}]}


def chart(n=400):
    ts = [1_700_000_000 + i * 86400 for i in range(n)]
    close = [100 + i * 0.1 for i in range(n)]
    return {"chart": {"result": [{"meta": {"symbol": "BTC-USD", "currency": "USD", "longName": "Bitcoin USD", "instrumentType": "CRYPTOCURRENCY"},
                                  "timestamp": ts, "indicators": {"quote": [{"close": close}], "adjclose": [{"adjclose": close}]}}], "error": None}}


@pytest.fixture
def net(tmp_path, monkeypatch):
    calls = []
    state = {"yahoo_limited": True}

    def handler(req: httpx.Request):
        u = str(req.url)
        calls.append((u, req.headers.get("user-agent", "")))
        if u == "https://www.sec.gov/files/company_tickers.json":
            return httpx.Response(200, json=TICKERS)
        if u.startswith("https://data.sec.gov/submissions/CIK0001045810.json"):
            return httpx.Response(200, json=SUBMISSIONS)
        if u.startswith("https://filings.xbrl.org/api/entities?"):
            return httpx.Response(200, json=ESEF_ENTITIES)
        if u.startswith("https://filings.xbrl.org/api/entities/549300ZTFBTXS1XOSZ93/filings"):
            return httpx.Response(200, json=ESEF_FILINGS)
        if u.startswith("https://fc.yahoo.com"):
            return httpx.Response(404, headers={"set-cookie": "A3=abc; Domain=.yahoo.com; Path=/"})
        if "api.exchange.coinbase.com/products/BTC-USD/candles" in u:
            if state.get("coinbase_done"):
                return httpx.Response(200, json=[])
            state["coinbase_done"] = True
            return httpx.Response(200, json=[[1_700_000_000 + i * 86400, 1, 2, 1, 100 + i, 5] for i in range(300)][::-1])
        if "/v1/test/getcrumb" in u:
            if state.get("yahoo_down"):
                return httpx.Response(429)
            state["yahoo_limited"] = False
            return httpx.Response(200, text="Xy7crumb")
        if "finance.yahoo.com" in u:
            if state["yahoo_limited"]:
                return httpx.Response(429, text="Too Many Requests")
            assert "crumb=Xy7crumb" in u
            if "/v1/finance/search" in u:
                return httpx.Response(200, json={"quotes": [{"symbol": "BTC-USD", "shortname": "Bitcoin USD", "quoteType": "CRYPTOCURRENCY", "exchDisp": "CCC"}]})
            return httpx.Response(200, json=chart())
        return httpx.Response(404)

    monkeypatch.setattr(sources, "CACHE", tmp_path)
    mock = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(sources, "_client", mock)
    monkeypatch.setattr(sources, "_yahoo", mock)
    monkeypatch.setattr(sources, "_crumb", None)
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    monkeypatch.setattr(pipeline, "DOCS", tmp_path / "docs")
    net_state.update(state=state)
    return calls


net_state = {}


def test_sec(net):
    assert sources.sec_search("nvidia")[0]["ticker"] == "NVDA"
    f = sources.sec_latest("NVDA")
    assert f["form"] == "10-K" and f["url"] == "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000052/nvda-20260125.htm"
    sec_calls = [c for c in net if "sec.gov" in c[0]]
    assert all("@" in ua for _, ua in sec_calls)        # SEC requires a contact in the User-Agent


def test_esef(net):
    f = sources.esef_latest("ferrari")
    assert f["period"] == "2025-12-31"
    assert f["url"] == "https://filings.xbrl.org/549300ZTFBTXS1XOSZ93/2025-12-31/ESEF/NL/0/ferrari-2025.xhtml"


def test_yahoo_recovers_from_429_with_crumb(net):
    assert sources.yahoo_search("bitcoin")[0]["symbol"] == "BTC-USD"
    h = sources.yahoo_history("BTC-USD")
    assert h["currency"] == "USD" and len(h["points"]) == 400


def test_market_end_to_end(net):
    a = pipeline.run({"kind": "market", "symbol": "BTC-USD", "lang": "en"}, lambda *_: None)
    assert a["kind"] == "market" and a["lang"] == "en" and len(a["facts"]) >= 25


def test_crypto_falls_back_to_coinbase_when_yahoo_blocks(net):
    net_state["state"]["yahoo_down"] = True
    h = sources.price_history("BTC-USD")
    assert h["source"] == "Coinbase" and h["currency"] == "USD" and len(h["points"]) == 300
    assert h["points"][0][0] < h["points"][-1][0]


def test_non_crypto_reports_yahoo_error(net):
    net_state["state"]["yahoo_down"] = True
    import pytest as _p
    with _p.raises(sources.SourceError, match="429"):
        sources.price_history("^GSPC")


def test_pre_ipo_company_and_prospectus(tmp_path, monkeypatch):
    """A company without a ticker is found through EDGAR full-text search; its latest S-1/A is the document read."""
    efts = {"hits": {"hits": [
        {"_source": {"ciks": ["0002000001"], "display_names": ["Lumen Labs, Inc.  (CIK 0002000001)"], "form": "S-1/A", "file_date": "2026-09-30"}},
        {"_source": {"ciks": ["0000789019"], "display_names": ["MICROSOFT CORP  (MSFT)  (CIK 0000789019)"], "form": "10-K", "file_date": "2026-07-30"}}]}}
    subs = {"cik": "0002000001", "name": "Lumen Labs, Inc.", "tickers": [], "filings": {"recent": {
        "accessionNumber": ["0002000001-26-000009", "0002000001-26-000003"], "filingDate": ["2026-09-30", "2026-08-01"],
        "reportDate": ["", ""], "form": ["S-1/A", "S-1"], "primaryDocument": ["lumen-s1a.htm", "lumen-s1.htm"], "isInlineXBRL": [0, 0]}}}

    def handler(req: httpx.Request):
        u = str(req.url)
        if u == "https://www.sec.gov/files/company_tickers.json":
            return httpx.Response(200, json=TICKERS)
        if u.startswith("https://efts.sec.gov/LATEST/search-index?"):
            assert "S-1" in req.url.params["forms"] and req.url.params["q"] == '"lumen"'
            return httpx.Response(200, json=efts)
        if u.startswith("https://data.sec.gov/submissions/CIK0002000001.json"):
            return httpx.Response(200, json=subs)
        return httpx.Response(404)

    monkeypatch.setattr(sources, "CACHE", tmp_path)
    monkeypatch.setattr(sources, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    hits = sources.sec_search("lumen")
    assert hits == [{"cik": 2000001, "ticker": "", "name": "Lumen Labs, Inc.", "form": "S-1/A", "filed": "2026-09-30"}]
    f = sources.sec_latest("2000001")
    assert f["form"] == "S-1/A" and f["url"].endswith("/000200000126000009/lumen-s1a.htm")


def test_document_picker_sec_and_esef(tmp_path, monkeypatch):
    """Quarterly reports, results releases (8-K item 2.02 → exhibit 99.1) and earlier ESEF years, chosen from a list."""
    subs = {"cik": "0000320193", "name": "Apple Inc.", "tickers": ["AAPL"], "filings": {"recent": {
        "accessionNumber": ["0000320193-26-000020", "0000320193-26-000018", "0001140361-26-015711", "0000320193-25-000079"],
        "filingDate": ["2026-07-31", "2026-07-30", "2026-04-20", "2025-10-31"], "reportDate": ["2026-06-27", "2026-07-30", "2026-04-17", "2025-09-27"],
        "form": ["10-Q", "8-K", "8-K", "10-K"], "items": ["", "2.02,9.01", "5.02", ""],
        "primaryDocument": ["aapl-20260627.htm", "aapl-20260730.htm", "ef2007_8k.htm", "aapl-20250927.htm"], "isInlineXBRL": [1, 1, 0, 1]}}}
    index = """<html><body><table class="tableFile" summary="Document Format Files">
      <tr><th scope="col">Seq</th><th scope="col">Description</th><th scope="col">Document</th><th scope="col">Type</th><th scope="col">Size</th></tr>
      <tr><td scope="row">1</td><td scope="row">8-K</td><td scope="row"><a href="/ix?doc=/Archives/edgar/data/320193/000032019326000018/aapl-20260730.htm">aapl-20260730.htm</a></td><td scope="row">8-K</td><td>37066</td></tr>
      <tr class="blueRow"><td scope="row">2</td><td scope="row">EX-99.1</td><td scope="row"><a href="/Archives/edgar/data/320193/000032019326000018/a8-kex991q3.htm">a8-kex991q3.htm</a></td><td scope="row">EX-99.1</td><td>9123</td></tr>
    </table></body></html>"""
    release = """<html><body><h1>Apple reports third quarter results</h1><p>CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS</p>
      <p>(in millions, except per-share amounts)</p><table>
      <tr><td></td><td>Three Months Ended June 27, 2026</td><td>Three Months Ended June 28, 2025</td></tr>
      <tr><td>Total net sales</td><td>$ 98,000</td><td>$ 94,036</td></tr><tr><td>Total cost of sales</td><td>52,000</td><td>50,318</td></tr>
      <tr><td>Gross margin</td><td>46,000</td><td>43,718</td></tr><tr><td>Operating income</td><td>31,000</td><td>28,202</td></tr>
      <tr><td>Income before provision for income taxes</td><td>31,200</td><td>28,031</td></tr>
      <tr><td>Provision for income taxes</td><td>6,200</td><td>4,597</td></tr><tr><td>Net income</td><td>$ 25,000</td><td>$ 23,434</td></tr>
      <tr><td>Diluted</td><td>$ 1.68</td><td>$ 1.57</td></tr></table></body></html>"""
    filings = {"data": [
        {"type": "filing", "id": str(i), "attributes": {"period_end": p, "date_added": d, "report_url": f"/549300ZTFBTXS1XOSZ93/{p}/ESEF/NL/0/f-{p[:4]}{s}.xhtml",
                                                         "error_count": 0, "language": "en"}}
        for i, (p, d, s) in enumerate([("2025-12-31", "2026-03-01 10:00:00", ""), ("2025-12-31", "2026-02-20 10:00:00", "-old"),
                                       ("2024-12-31", "2025-03-01 10:00:00", "")])]}
    calls = []

    def handler(req: httpx.Request):
        u = str(req.url)
        calls.append(u)
        if u == "https://www.sec.gov/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}})
        if u.startswith("https://data.sec.gov/submissions/CIK0000320193.json"):
            return httpx.Response(200, json=subs)
        if u == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000018/0000320193-26-000018-index.htm":
            return httpx.Response(200, text=index)
        if u == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000018/a8-kex991q3.htm":
            return httpx.Response(200, text=release)
        if u.startswith("https://filings.xbrl.org/api/entities?"):
            return httpx.Response(200, json=ESEF_ENTITIES)
        if u.startswith("https://filings.xbrl.org/api/entities/549300ZTFBTXS1XOSZ93/filings"):
            return httpx.Response(200, json=filings)
        return httpx.Response(404)

    monkeypatch.setattr(sources, "CACHE", tmp_path)
    monkeypatch.setattr(sources, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    monkeypatch.setattr(pipeline, "DOCS", tmp_path / "docs")
    from analyst import ai
    monkeypatch.setattr(ai, "active", lambda: None)

    res = sources.sec_documents("AAPL")
    assert res["company"] == "Apple Inc."
    assert [(d["form"], d["what"]) for d in res["documents"]] == [
        ("10-Q", "Quarterly report"), ("8-K", "Results release"), ("10-K", "Annual report")]   # the 8-K about a director is left out
    eight_k = res["documents"][1]["url"]
    assert sources.sec_release(eight_k) == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000018/a8-kex991q3.htm"

    a = pipeline.run({"kind": "sec", "query": "AAPL", "url": eight_k, "form": "8-K", "lang": "en"}, lambda *_: None)
    card = {c["key"]: c for c in a["card"]}
    assert card["revenue"]["display"] == "$98.0B" and card["revenue"]["yoy_display"] == "+4.2%"
    assert card["revenue"]["vs"] == "3M to Jun 2025"            # Apple's third fiscal quarter: not called "Q2"

    esef = sources.esef_documents("549300ZTFBTXS1XOSZ93")
    assert [d["period"] for d in esef["documents"]] == ["2025-12-31", "2024-12-31"]          # one per year and language
    assert esef["documents"][0]["url"].endswith("f-2025.xhtml") and esef["documents"][1]["what"] == "Annual financial report 2024"

    import server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "_need_ai", lambda: None)
    client = TestClient(server.app, base_url="http://127.0.0.1:8765")
    r = client.get("/api/documents", params={"kind": "sec", "query": "AAPL"})
    assert r.status_code == 200 and len(r.json()["documents"]) == 3
    assert client.get("/api/documents", params={"kind": "market", "query": "x"}).status_code == 400
    # a chosen document must come from the archive it was listed from
    assert client.post("/api/analyze", json={"kind": "sec", "query": "AAPL", "url": "https://evil.example/x.htm"}).status_code == 400
    assert client.post("/api/analyze", json={"kind": "esef", "query": "x", "url": "https://www.sec.gov/Archives/edgar/data/1/000000000000000001/a.htm"}).status_code == 400
    r = client.get("/api/original", params={"kind": "sec", "query": "AAPL", "url": eight_k, "form": "8-K"})
    assert r.status_code == 200 and b"third quarter" in r.content and "a8-kex991q3.htm" in r.headers["content-disposition"]
