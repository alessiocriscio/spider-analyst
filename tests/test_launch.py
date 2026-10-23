"""Launcher: Chromium browser choice on macOS (the default one if Chromium-based, else the first installed)."""
import plistlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import launch  # noqa: E402


def _home_with_default(tmp_path, bundle):
    prefs = tmp_path / "Library/Preferences/com.apple.LaunchServices"
    prefs.mkdir(parents=True)
    (prefs / "com.apple.launchservices.secure.plist").write_bytes(plistlib.dumps(
        {"LSHandlers": [{"LSHandlerURLScheme": "mailto", "LSHandlerRoleAll": "com.apple.mail"},
                        {"LSHandlerURLScheme": "https", "LSHandlerRoleAll": bundle}]}, fmt=plistlib.FMT_BINARY))
    return tmp_path


def _record(monkeypatch, installed):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        ok = cmd[1] == "-b" and cmd[2] in installed
        return subprocess.CompletedProcess(cmd, 0 if ok else 1)
    monkeypatch.setattr(launch.subprocess, "run", fake_run)
    monkeypatch.delenv("SPIDER_BROWSER", raising=False)
    return calls


def test_default_chromium_browser_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(launch.Path, "home", lambda: _home_with_default(tmp_path, "com.brave.browser"))
    calls = _record(monkeypatch, {"com.brave.browser", "com.google.chrome"})
    assert launch._open_mac()
    assert calls[0][:3] == ["open", "-b", "com.brave.browser"] and len(calls) == 1


def test_safari_default_falls_back_to_installed_chromium(tmp_path, monkeypatch):
    monkeypatch.setattr(launch.Path, "home", lambda: _home_with_default(tmp_path, "com.apple.safari"))
    calls = _record(monkeypatch, {"com.microsoft.edgemac"})
    assert launch._open_mac()
    assert calls[-1][2] == "com.microsoft.edgemac" and all(c[2] != "com.apple.safari" for c in calls)


def test_no_chromium_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(launch.Path, "home", lambda: tmp_path)
    _record(monkeypatch, set())
    assert not launch._open_mac()
