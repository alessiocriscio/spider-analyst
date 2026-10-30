"""Colour themes shared by the app (web/themes.js holds the same accents) and the PDF report."""
from __future__ import annotations

from reportlab.lib import colors

THEMES = {
    "neon": {"accent": "#ff2d8f", "accent2": "#39c5e8", "accent3": "#3b6cff", "amber": "#f2b134", "violet": "#783bff", "prior": "#c9c6d8"},
    "ocean": {"accent": "#0a7bc2", "accent2": "#14b8a6", "accent3": "#1e3a8a", "amber": "#f59e0b", "violet": "#6366f1", "prior": "#c3d3e0"},
    "sunset": {"accent": "#e8590c", "accent2": "#f5a623", "accent3": "#7b2d8e", "amber": "#ffd166", "violet": "#c2255c", "prior": "#e3cfc4"},
    "forest": {"accent": "#1f9d55", "accent2": "#84cc16", "accent3": "#0f5132", "amber": "#d4a017", "violet": "#2f855a", "prior": "#c8d8cc"},
    "mono": {"accent": "#222222", "accent2": "#8a8a8a", "accent3": "#555555", "amber": "#b0b0b0", "violet": "#3d3d3d", "prior": "#d4d4d4"},
    "midnight": {"accent": "#ff4fa3", "accent2": "#4fe3ff", "accent3": "#7c8cff", "amber": "#ffd34d", "violet": "#a78bfa", "prior": "#c9c6d8"},
}
DEFAULT = "neon"


def palette(theme: str) -> dict:
    return THEMES.get(theme) or THEMES[DEFAULT]


def apply(theme: str) -> dict:
    """Point the report and chart colours at the theme; returns the palette (hex strings)."""
    from . import charts, pdfreport
    p = palette(theme)
    c = {k: colors.HexColor(v) for k, v in p.items()}
    charts.PINK, charts.CYAN, charts.BLUE, charts.AMBER, charts.VIOLET, charts.PRIOR = (
        c["accent"], c["accent2"], c["accent3"], c["amber"], c["violet"], c["prior"])
    pdfreport.PINK, pdfreport.CYAN, pdfreport.BLUE = c["accent"], c["accent2"], c["accent3"]
    pdfreport.ACCENT_HEX = p["accent"]
    return p
