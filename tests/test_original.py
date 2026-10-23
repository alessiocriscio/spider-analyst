"""Download of the original document behind a search result (no network: sources are simulated)."""
from fastapi.testclient import TestClient

import server
from analyst import sources

client = TestClient(server.app, base_url="http://127.0.0.1:8765")


def test_original_sec(monkeypatch):
    monkeypatch.setattr(sources, "sec_latest", lambda q: {"url": "https://www.sec.gov/Archives/edgar/data/1/2/acme-20251231.htm",
                                                           "ticker": "ACME", "form": "10-K", "period": "2025-12-31"})
    monkeypatch.setattr(sources, "fetch", lambda url, **k: b"<html>10-K</html>")
    r = client.get("/api/original", params={"kind": "sec", "query": "ACME"})
    assert r.status_code == 200 and r.content == b"<html>10-K</html>"
    assert 'filename="ACME-10-K-2025-12-31.htm"' in r.headers["content-disposition"]


def test_original_market_csv(monkeypatch):
    monkeypatch.setattr(sources, "price_history", lambda s: {"symbol": "BTC-USD", "currency": "USD", "source": "Coinbase",
                                                             "points": [("2025-01-01", 93000.5), ("2025-01-02", 94100.0)]})
    r = client.get("/api/original", params={"kind": "market", "symbol": "BTC-USD"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines() == ["date,close,currency,source", "2025-01-01,93000.5,USD,Coinbase", "2025-01-02,94100,USD,Coinbase"]


def test_original_error(monkeypatch):
    def boom(q):
        raise sources.SourceError("No SEC company found")
    monkeypatch.setattr(sources, "sec_latest", boom)
    r = client.get("/api/original", params={"kind": "sec", "query": "ZZZ"})
    assert r.status_code == 502 and "No SEC company" in r.json()["detail"]
