// Colour themes: the interface (CSS variables), the spider, the marks on the page and the PDF report
// (analyst/themes.py holds the same accents). The choice is remembered in this browser.

import { COLORS } from "./spider.js";

const LIGHT = {
  "--stage": "#e4e3ec", "--ink": "#1d1c26", "--muted": "#6c6a7c", "--line": "#d6d4e0", "--panel": "#ffffff", "--card": "#ffffff",
  "--soft": "#f4f3f8", "--soft2": "#e6e5ee", "--text2": "#3c3a4a", "--faint": "#efeef4", "--wait": "#c9c7d6", "--dashed": "#b9b6c8",
  "--veil": "rgba(228, 227, 236, .82)", "--btn": "#1d1c26", "--btn-ink": "#ffffff", "--btn-hover": "#000000", "--ok": "#0a7a45",
  "--up": "#0f8a5f", "--down": "#c8323c", "--warn-bg": "#fff4f4", "--warn-ink": "#6b1a20", "--marker": "#ffe45c",
};

// neon highlight palettes (fills with their text colour, and outline inks)
const NEON_FX = [
  { bg: "#FF00D4", fg: "#1b0024" }, { bg: "#39DFFF", fg: "#06222b" }, { bg: "#43FFA0", fg: "#062b17" },
  { bg: "#FF8650", fg: "#2b0e00" }, { bg: "#FFD34D", fg: "#2b2100" }, { bg: "#783BFF", fg: "#ffffff" }];

export const THEMES = {
  neon: {
    name: { en: "Neon", it: "Neon" }, swatch: "#ff2d8f",
    css: { ...LIGHT, "--silk": "#ff2e88", "--silk-soft": "#ffe3ef", "--accent2": "#3fd4f5" },
    spider: { body: "#0b0d12", outline: "#3b6cff", head: "#4fe3ff", leg: "#3fd4f5", joint: "#ff2d8f", silk: "#5cc2ff" },
    ping: "#ff2d8f", sight: "#27c8ff", fx: NEON_FX, ink: ["#FF00D4", "#00B3E0", "#00C46A", "#FF6A2B", "#E0A800", "#783BFF"],
  },
  ocean: {
    name: { en: "Ocean", it: "Oceano" }, swatch: "#0a7bc2",
    css: { ...LIGHT, "--stage": "#dfe9ef", "--silk": "#0a7bc2", "--silk-soft": "#dcefff", "--accent2": "#14b8a6",
           "--veil": "rgba(223, 233, 239, .84)", "--soft": "#eef4f8", "--soft2": "#dde8ef" },
    spider: { body: "#0b1a26", outline: "#1e3a8a", head: "#5eead4", leg: "#14b8a6", joint: "#0a7bc2", silk: "#7dd3fc" },
    ping: "#0a7bc2", sight: "#14b8a6",
    fx: [{ bg: "#0a7bc2", fg: "#ffffff" }, { bg: "#5eead4", fg: "#06302b" }, { bg: "#7dd3fc", fg: "#062033" },
         { bg: "#1e3a8a", fg: "#ffffff" }, { bg: "#fcd34d", fg: "#2b2100" }, { bg: "#38bdf8", fg: "#062033" }],
    ink: ["#0a7bc2", "#0f9488", "#1e3a8a", "#0369a1", "#b45309", "#0e7490"],
  },
  sunset: {
    name: { en: "Sunset", it: "Tramonto" }, swatch: "#e8590c",
    css: { ...LIGHT, "--stage": "#f1e6df", "--silk": "#e8590c", "--silk-soft": "#ffe8d9", "--accent2": "#f5a623",
           "--veil": "rgba(241, 230, 223, .84)", "--soft": "#f8f1ec", "--soft2": "#efe2d9" },
    spider: { body: "#1c0f0a", outline: "#7b2d8e", head: "#ffd166", leg: "#f5a623", joint: "#e8590c", silk: "#f4a261" },
    ping: "#e8590c", sight: "#f5a623",
    fx: [{ bg: "#e8590c", fg: "#ffffff" }, { bg: "#ffd166", fg: "#2b2100" }, { bg: "#c2255c", fg: "#ffffff" },
         { bg: "#f4a261", fg: "#2b1200" }, { bg: "#7b2d8e", fg: "#ffffff" }, { bg: "#ff8fa3", fg: "#2b0010" }],
    ink: ["#e8590c", "#c2255c", "#7b2d8e", "#d97706", "#b45309", "#be123c"],
  },
  forest: {
    name: { en: "Forest", it: "Bosco" }, swatch: "#1f9d55",
    css: { ...LIGHT, "--stage": "#e1ebe2", "--silk": "#1f9d55", "--silk-soft": "#dcf3e4", "--accent2": "#84cc16",
           "--veil": "rgba(225, 235, 226, .84)", "--soft": "#eff5f0", "--soft2": "#dde9df" },
    spider: { body: "#0c1a10", outline: "#0f5132", head: "#bef264", leg: "#84cc16", joint: "#1f9d55", silk: "#86efac" },
    ping: "#1f9d55", sight: "#84cc16",
    fx: [{ bg: "#1f9d55", fg: "#ffffff" }, { bg: "#bef264", fg: "#1a2e05" }, { bg: "#86efac", fg: "#052e16" },
         { bg: "#d4a017", fg: "#2b2100" }, { bg: "#0f5132", fg: "#ffffff" }, { bg: "#4ade80", fg: "#052e16" }],
    ink: ["#1f9d55", "#4d7c0f", "#0f5132", "#15803d", "#a16207", "#166534"],
  },
  mono: {
    name: { en: "Mono", it: "Mono" }, swatch: "#222222",
    css: { ...LIGHT, "--stage": "#e7e7e7", "--silk": "#222222", "--silk-soft": "#e9e9e9", "--accent2": "#8a8a8a",
           "--veil": "rgba(231, 231, 231, .86)", "--soft": "#f2f2f2", "--soft2": "#e2e2e2" },
    spider: { body: "#111111", outline: "#555555", head: "#dddddd", leg: "#777777", joint: "#222222", silk: "#999999" },
    ping: "#222222", sight: "#888888",
    fx: [{ bg: "#222222", fg: "#ffffff" }, { bg: "#d4d4d4", fg: "#111111" }, { bg: "#555555", fg: "#ffffff" },
         { bg: "#ffe45c", fg: "#222222" }, { bg: "#aaaaaa", fg: "#111111" }, { bg: "#000000", fg: "#ffffff" }],
    ink: ["#222222", "#555555", "#000000", "#777777", "#444444", "#333333"],
  },
  midnight: {
    name: { en: "Midnight", it: "Notte" }, swatch: "#4fe3ff", dark: true,
    css: {
      "--stage": "#14141c", "--ink": "#ecebf5", "--muted": "#9a98ad", "--line": "#33323f", "--panel": "#1b1b25", "--card": "#22222e",
      "--soft": "#1b1b25", "--soft2": "#2b2a38", "--text2": "#c9c7d8", "--faint": "#2a2936", "--wait": "#55536a", "--dashed": "#4a4960",
      "--veil": "rgba(20, 20, 28, .86)", "--btn": "#ecebf5", "--btn-ink": "#14141c", "--btn-hover": "#ffffff", "--ok": "#4ade80",
      "--up": "#34d399", "--down": "#f87171", "--warn-bg": "#3a1c22", "--warn-ink": "#fecaca", "--marker": "#ffe45c",
      "--silk": "#ff4fa3", "--silk-soft": "#3a1f33", "--accent2": "#4fe3ff",
    },
    spider: { body: "#05060a", outline: "#7c8cff", head: "#4fe3ff", leg: "#4fe3ff", joint: "#ff4fa3", silk: "#7dd3fc" },
    ping: "#ff4fa3", sight: "#4fe3ff", fx: NEON_FX, ink: ["#FF00D4", "#00B3E0", "#00C46A", "#FF6A2B", "#E0A800", "#783BFF"],
  },
};

let current = "neon";

export function themeId() { return current; }
export function theme() { return THEMES[current]; }

export function applyTheme(id) {
  current = THEMES[id] ? id : "neon";
  const th = THEMES[current], root = document.documentElement;
  for (const [k, v] of Object.entries(th.css)) root.style.setProperty(k, v);
  root.dataset.theme = current;
  root.style.colorScheme = th.dark ? "dark" : "light";
  Object.assign(COLORS, th.spider, { ping: th.ping, sight: th.sight });
  try { localStorage.setItem("spider-theme", current); } catch { /* private window: not remembered */ }
  return th;
}

export function savedTheme() {
  try { return localStorage.getItem("spider-theme") || "neon"; } catch { return "neon"; }
}

// "rgba(r,g,b,a)" from "#rrggbb"
export function rgba(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
