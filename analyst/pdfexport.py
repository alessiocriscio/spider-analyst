"""Report HTML -> PDF with the Chromium browser already installed (headless print).

The app needs a Chromium-based browser anyway, so printing with it keeps the
report's exact look (colours, tiles, fonts) without extra dependencies.
SPIDER_CHROME can point to a specific Chrome/Brave/Edge/Chromium executable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

MAC_APPS = ["Google Chrome", "Brave Browser", "Microsoft Edge", "Chromium", "Vivaldi", "Opera", "Google Chrome Canary"]
WIN_RELS = [r"Google\Chrome\Application\chrome.exe", r"BraveSoftware\Brave-Browser\Application\brave.exe",
            r"Microsoft\Edge\Application\msedge.exe", r"Chromium\Application\chrome.exe"]
LINUX_BINS = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "brave-browser", "microsoft-edge", "vivaldi"]


class PdfError(Exception):
    pass


def chromium_executable() -> Optional[str]:
    forced = os.environ.get("SPIDER_CHROME")
    if forced and Path(forced).exists():
        return forced
    if sys.platform == "darwin":
        for app in MAC_APPS:
            for root in (Path("/Applications"), Path.home() / "Applications"):
                exe = root / f"{app}.app" / "Contents" / "MacOS" / app
                if exe.exists():
                    return str(exe)
        return None
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
            for rel in WIN_RELS:
                if base and (Path(base) / rel).exists():
                    return str(Path(base) / rel)
        return None
    for name in LINUX_BINS:
        exe = shutil.which(name)
        if exe:
            return exe
    return None


def html_to_pdf(html: str) -> bytes:
    exe = chromium_executable()
    if not exe:
        raise PdfError("no Chromium browser found")
    tmp = Path(tempfile.mkdtemp(prefix="spider-pdf-"))
    try:
        src, out = tmp / "report.html", tmp / "report.pdf"
        src.write_text(html, encoding="utf-8")
        cmd = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               f"--user-data-dir={tmp / 'profile'}",            # never touch the user's open browser profile
               "--no-pdf-header-footer", "--print-to-pdf-no-header", f"--print-to-pdf={out}", src.as_uri()]
        if sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")
        proc = subprocess.run(cmd, capture_output=True, timeout=90)
        if not out.exists() or out.stat().st_size < 500:
            raise PdfError(f"printing failed ({proc.returncode}): {proc.stderr.decode(errors='ignore')[-300:]}")
        return out.read_bytes()
    except subprocess.TimeoutExpired as e:
        raise PdfError("printing timed out") from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
