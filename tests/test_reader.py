"""The AI reading, with a simulated model: what is kept, what is dropped, how it reaches the report."""
import json
import os
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
FIX = HERE / "fixtures"

from analyst import ai, pdfreport, pipeline, reader  # noqa: E402

BREAK = '<hr style="page-break-after:always">'
S1 = ("<html><body>"
      "<div><h1>Lumen Labs, Inc.</h1><p>Prospectus. 10,000,000 shares of Class A common stock. "
      "Initial public offering price $21.00 per share.</p></div>" + BREAK +
      "<div><h2>Prospectus summary</h2><p>We sell access to our models to 1,200 enterprise customers.</p></div>" + BREAK +
      "<div><h2>Summary consolidated financial data</h2><p>(in millions)</p><table>"
      "<tr><td></td><td>2025</td><td>2024</td></tr>"
      "<tr><td>Model access sales</td><td>3,400</td><td>1,100</td></tr>"
      "<tr><td>Result of the business</td><td>(2,100)</td><td>(2,600)</td></tr>"
      "<tr><td>Result for the year</td><td>(1,900)</td><td>(2,500)</td></tr></table></div>"
      "</body></html>").encode()


def fig(label, value, page, metric="", role="", mult=1, period=""):
    return {"label": label, "value": value, "page": page, "period": period, "metric": metric, "role": role, "multiplier": mult}


ANSWER = {
    "doc_type": "S-1 registration statement", "company": "Lumen Labs, Inc.", "period": "2025", "currency": "USD",
    "summary": "Lumen Labs sells access to AI models. Revenue was 3,400 million in 2025. It is worth 77 billion.",
    "sections": [{"title": "The offering", "points": [{"text": "10,000,000 shares at $21.00 each.", "pages": [1]},
                                                      {"text": "A valuation of $500 billion.", "pages": [1]}]}],
    "figures": [fig("Revenue", "3,400", 3, "revenue", "current", 1_000_000, "2025"),
                fig("Revenue", "1,100", 3, "revenue", "prior", 1_000_000, "2024"),
                fig("Operating loss", "(2,100)", 3, "operating_income", "current", 1_000_000),
                fig("Operating loss", "(2,600)", 3, "operating_income", "prior", 1_000_000),
                fig("Net loss", "(1,900)", 3, "net_income", "current", 1_000_000),
                fig("Net loss", "(2,500)", 3, "net_income", "prior", 1_000_000),
                fig("IPO price per share", "$21.00", 1),
                fig("Invented figure", "$9,999", 3)],
    "findings": [{"text": "Revenue rose to 3,400 from 1,100.", "refs": ["f0", "f1"]},
                 {"text": "The net loss narrowed to (1,900).", "refs": ["f4"]},
                 {"text": "Margins will reach 45% next year.", "refs": ["f0"]},
                 {"text": "The operating loss was (2,100).", "refs": ["f2"]},
                 {"text": "Shares are offered at $21.00.", "refs": ["f6"]}],
}


@pytest.fixture
def fake_ai(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "DOCS", tmp_path / "docs")
    monkeypatch.setattr(ai, "active", lambda: ("openai", "sk-test", "gpt-test"))
    prompts = []

    def install(answer):
        def call(prompt, schema, max_tokens=16000):
            prompts.append(prompt)
            return answer(prompt) if callable(answer) else json.loads(json.dumps(answer))
        monkeypatch.setattr(ai, "_call", call)
    install.prompts = prompts
    return install


def test_validation_keeps_only_what_the_pages_show():
    pages = {1: "Initial public offering price $21.00 per share. 10,000,000 shares", 3: "Model access sales 3,400 1,100 (1,900)"}
    r = reader.validate(json.loads(json.dumps(ANSWER)), pages, {})
    assert [f["value"] for f in r["figures"]] == ["3,400", "1,100", "(1,900)", "$21.00"]
    assert "77" not in r["summary"] and r["summary"].startswith("Lumen Labs")
    assert [p["text"] for p in r["sections"][0]["points"]] == ["10,000,000 shares at $21.00 each."]
    assert [f["text"] for f in r["findings"]] == ["Revenue rose to 3,400 from 1,100.", "The net loss narrowed to (1,900).",
                                                  "Shares are offered at $21.00."]


def test_prospectus_read_by_ai(fake_ai, monkeypatch):
    fake_ai(ANSWER)
    monkeypatch.setattr(pipeline, "_statement_metrics", lambda g: None)    # rows unknown to the label rules
    a = pipeline.run({"kind": "upload", "data": S1, "name": "s1.htm", "ai": True, "lang": "en"}, lambda *_: None)
    assert a["ai"] and a["title"] == "Lumen Labs, Inc." and a["subtitle"].startswith("S-1 registration statement")
    assert a["reading"]["summary"] and "77" not in a["reading"]["summary"]
    key = {f["label"]: f["display"] for f in a["facts"].values() if f["key"]}
    assert key["IPO price per share"] == "$21.00" and "Invented figure" not in key
    card = {t["key"]: t for t in a["card"]}
    assert card["revenue"]["display"] == "$3.4B" and card["revenue"]["yoy_display"].startswith("+209")
    assert a["fin"]["metrics"]["net_income"]["cur"] == -1.9e9
    assert len(a["findings"]) == 4 and all("45%" not in f["text"] for f in a["findings"])
    assert "<page n=\"3\">" in fake_ai.prompts[0]
    pdf = pdfreport.build(a)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 3000


def test_ixbrl_findings_cite_tagged_figures(fake_ai):
    def answer(prompt):
        known = dict(re.findall(r"- id=(\w+) \| [^:\n]+: ([^\s(]+)", prompt))
        ids = [k for k in ("revenue_cur", "net_income_cur", "cfo_cur") if k in known]
        return {"doc_type": "10-K annual report", "company": "", "period": "", "currency": "USD",
                "summary": "A software company.", "sections": [{"title": "Business", "points": [{"text": "Sells software.", "pages": [1]}]}],
                "figures": [], "findings": [{"text": f"Item {chr(65 + i)} was {known[k]}.", "refs": [k]} for i, k in enumerate(ids)]}
    fake_ai(answer)
    a = pipeline.run({"kind": "upload", "data": (FIX / "sec_10k.htm").read_bytes(), "name": "x.htm", "ai": True, "lang": "en"}, lambda *_: None)
    assert a["ai"] and a["reading"]["doc_type"] == "10-K annual report"
    assert len(a["findings"]) == 3 and a["findings"][0]["text"].startswith("Item A was $")


def test_page_choice_fits_the_budget():
    texts = ["Cover"] + ["filler text " * 900] * 60 + ["PROSPECTUS SUMMARY revenue 1,000 net income 200 " * 20]
    picked = reader.choose_pages(texts)
    assert picked[0] == 0 and len(texts) - 1 in picked
    assert sum(min(len(texts[i]), reader.PAGE_CAP) for i in picked) <= reader.CHAR_BUDGET


# ---------------------------------------------------------------- subscriptions through the official CLIs

@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(ai, "AI_FILE", tmp_path / "ai.json")
    monkeypatch.setattr(ai, "LEGACY_KEY_FILE", tmp_path / "anthropic_key")
    for p in ai.PROVIDERS.values():
        for v in p["env"]:
            monkeypatch.delenv(v, raising=False)
    return tmp_path


def fake_tool(d: Path, name: str, body: str):
    p = d / name
    p.write_text(f"#!{sys.executable}\nimport json, sys\n{body}\n")
    p.chmod(0o755)


@pytest.mark.skipif(os.name == "nt", reason="fake tools are POSIX scripts")
def test_claude_subscription_via_claude_code(cfg, tmp_path, monkeypatch):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    fake_tool(bin_, "claude", """
a = sys.argv[1:]
assert a[0] == "-p" and a[a.index("--tools") + 1] == "" and "--json-schema" in a and "--no-session-persistence" in a
assert "ok" in sys.stdin.read()
print(json.dumps({"type": "result", "is_error": False, "result": "", "structured_output": {"ok": True}}))""")
    monkeypatch.setenv("PATH", str(bin_))
    monkeypatch.setattr(ai.Path, "home", lambda: tmp_path)
    assert ai.active() is None
    ai.save_settings("claude_code")
    assert ai.active() == ("claude_code", "", "") and ai.test() == "Claude subscription (via Claude Code)"


@pytest.mark.skipif(os.name == "nt", reason="fake tools are POSIX scripts")
def test_chatgpt_subscription_via_codex(cfg, tmp_path, monkeypatch):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    fake_tool(bin_, "codex", """
a = sys.argv[1:]
assert a[0] == "exec" and a[a.index("--sandbox") + 1] == "read-only" and a[-1] == "-"
json.load(open(a[a.index("--output-schema") + 1]))
sys.stdin.read()
open(a[a.index("-o") + 1], "w").write(json.dumps({"ok": True}))""")
    monkeypatch.setenv("PATH", str(bin_))
    monkeypatch.setattr(ai.Path, "home", lambda: tmp_path)
    ai.save_settings("codex")
    assert ai.test() == "ChatGPT subscription (via Codex)"


def test_subscription_not_installed_is_not_used(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(ai.Path, "home", lambda: tmp_path)
    ai.save_settings("claude_code")
    assert ai.active() is None
    ai.save_settings("openai", "sk-test-abcdefghij")
    assert ai.active()[0] == "openai"


def test_server_requires_the_ai(monkeypatch):
    import server
    client = TestClient(server.app, base_url="http://127.0.0.1:8765")
    monkeypatch.setattr(ai, "active", lambda: None)
    r = client.post("/api/analyze", json={"kind": "sec", "query": "MSFT"})
    assert r.status_code == 409 and "AI" in r.json()["detail"]
    assert client.post("/api/upload", files={"file": ("a.pdf", b"%PDF-1.4")}).status_code == 409
    assert client.get("/api/status").json()["ai"] is False
