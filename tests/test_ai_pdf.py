"""AI providers (simulated HTTP) and PDF export (real headless Chromium when available)."""
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from analyst import ai, pdfexport, pipeline  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(ai, "AI_FILE", tmp_path / "ai.json")
    monkeypatch.setattr(ai, "LEGACY_KEY_FILE", tmp_path / "anthropic_key")
    for p in ai.PROVIDERS.values():
        for v in p["env"]:
            monkeypatch.delenv(v, raising=False)
    return tmp_path


def test_settings_and_active_provider(cfg, monkeypatch):
    assert ai.active() is None and not ai.available()
    ai.save_settings("openrouter", "sk-or-test-1234567890", "")
    assert ai.active() == ("openrouter", "sk-or-test-1234567890", "openrouter/auto")
    ai.save_settings("openai", "sk-test-abcdefghij", "gpt-test")
    assert ai.active() == ("openai", "sk-test-abcdefghij", "gpt-test")
    assert oct(os.stat(cfg / "ai.json").st_mode)[-3:] == "600" or os.name == "nt"
    ai.save_settings("openai", remove=True)
    assert ai.active()[0] == "openrouter"                      # falls back to another saved key
    monkeypatch.setenv("MISTRAL_API_KEY", "env-key-123456")
    assert {p["id"]: p["has_key"] for p in ai.status()["providers"]}["mistral"]


def test_openai_compatible_call_is_validated(cfg, monkeypatch):
    ai.save_settings("openrouter", "sk-or-test-1234567890", "")
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, headers=headers, body=json)
        content = '```json\n{"observations": [{"text": "Revenue reached $120B, up 20.0%.", "ids": ["revenue_cur", "growth_revenue"]},' \
                  '{"text": "Margins will double to 99%.", "ids": ["revenue_cur"]}]}\n```'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    monkeypatch.setattr(ai.httpx, "post", fake_post)
    data = {"revenue_cur": {"label": "Revenue", "display": "$120B", "pages": [3]},
            "growth_revenue": {"label": "Revenue growth", "display": "+20.0%", "pages": [3]}}
    obs = ai.observations("Example", data)
    assert sent["url"] == "https://openrouter.ai/api/v1/chat/completions" and sent["body"]["model"] == "openrouter/auto"
    assert sent["headers"]["Authorization"] == "Bearer sk-or-test-1234567890"
    assert [o["text"] for o in obs] == ["Revenue reached $120B, up 20.0%."]   # the invented 99% is dropped


def test_provider_error_becomes_a_warning(cfg, monkeypatch, tmp_path):
    ai.save_settings("openai", "sk-bad-key-1234567", "")
    monkeypatch.setattr(ai.httpx, "post", lambda *a, **k: httpx.Response(401, json={"error": {"message": "Incorrect API key"}}))
    monkeypatch.setattr(pipeline, "DOCS", tmp_path / "docs")
    import make_fixtures
    FIX.mkdir(exist_ok=True)
    (FIX / "sec_10k.htm").write_text(make_fixtures.sec(), encoding="utf-8")
    a = pipeline.run({"kind": "upload", "data": (FIX / "sec_10k.htm").read_bytes(), "name": "x.htm", "ai": True, "lang": "en"}, lambda *_: None)
    assert not a["ai"] and a["findings"] and any("Incorrect API key" in w for w in a["warnings"])


def test_pdf_export(monkeypatch):
    chrome = next(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"), None) if Path("/opt/pw-browsers").exists() else None
    if chrome:
        monkeypatch.setenv("SPIDER_CHROME", str(chrome))
    if not pdfexport.chromium_executable():
        pytest.skip("no Chromium browser here")
    pdf = pdfexport.html_to_pdf('<!doctype html><html><body style="background:#ff2d8f"><h1>Spider</h1></body></html>')
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
