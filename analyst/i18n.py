"""Report language (Italian or English) for everything the analysis writes.

The language is set once per analysis with `using(lang)`; formatting helpers and
texts read it from a context variable, so worker threads never mix languages.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager

LANGS = ("it", "en")
_LANG = contextvars.ContextVar("report_lang", default="it")


def lang() -> str:
    return _LANG.get()


def t(it: str, en: str) -> str:
    return en if _LANG.get() == "en" else it


@contextmanager
def using(code: str):
    token = _LANG.set(code if code in LANGS else "it")
    try:
        yield
    finally:
        _LANG.reset(token)
