"""Languages.

Interface language: English, or Italian when the operating system's language is
Italian (detected once on this machine; SPIDER_LANG=it|en overrides it).
Report language: Italian or English, chosen per analysis with `using(lang)`;
formatting helpers and report texts read it from a context variable, so worker
threads never mix languages.

Standard library only: the launcher imports this module before the virtual
environment exists.
"""
from __future__ import annotations

import contextvars
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from typing import Optional

LANGS = ("it", "en")
_LANG = contextvars.ContextVar("report_lang", default="it")


def lang() -> str:
    return _LANG.get()


def t(it: str, en: str) -> str:
    """Text in the report language."""
    return en if _LANG.get() == "en" else it


@contextmanager
def using(code: str):
    token = _LANG.set(code if code in LANGS else "en")
    try:
        yield
    finally:
        _LANG.reset(token)


# ---------------------------------------------------------------- interface language

def _mac_lang() -> Optional[str]:
    try:
        out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r'"?([A-Za-z]{2})[-_A-Za-z]*"?', out.replace("(", " "))
    return m.group(1).lower() if m else None


def _windows_lang() -> Optional[str]:
    try:
        import ctypes
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError):
        return None
    return "it" if (langid & 0x3FF) == 0x10 else "en"       # LANG_ITALIAN = 0x10


def _env_lang() -> Optional[str]:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        v = os.environ.get(var, "")
        if v and v not in ("C", "POSIX") and not v.startswith("C."):
            return v[:2].lower()
    return None


_SYSTEM: Optional[str] = None


def system_lang() -> str:
    """'it' when the operating system is set to Italian, otherwise 'en'."""
    global _SYSTEM
    forced = os.environ.get("SPIDER_LANG", "").lower()
    if forced in LANGS:
        return forced
    if _SYSTEM is None:
        if sys.platform == "darwin":
            code = _mac_lang() or _env_lang()
        elif os.name == "nt":
            code = _windows_lang()
        else:
            code = _env_lang()
        _SYSTEM = "it" if code == "it" else "en"
    return _SYSTEM


def ui(it: str, en: str) -> str:
    """Text in the interface language (messages shown by the app and the launcher)."""
    return it if system_lang() == "it" else en
