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
