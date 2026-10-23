# Spider Analyst

*by Alessio Criscio*

Spider Analyst: an animated spider reads financial documents (10-K, ESEF, PDFs, market data) and builds a live report. Runs locally on macOS, Windows and Linux in a Chromium browser. Completely Open Source and free.

A from-scratch rebuild of the idea shown in @buildwithbrock's videos. It contains none of his code.

The interface is in English, or in Italian when the operating system's language is Italian (`SPIDER_LANG=en` or
`SPIDER_LANG=it` forces one). The report can be produced in English or Italian; it starts in the interface language.

## Requirements

- **Python 3.10 or newer** — [python.org/downloads](https://www.python.org/downloads/) (on Windows tick
  *Add python.exe to PATH*; on a Mac `brew install python` also works).
- **A Chromium-based browser**: Chrome, Brave, Edge, Arc, Vivaldi or Opera.
  **Safari and Firefox are not supported** — the page loads but the spider does not read the document.
  The launcher opens the app in a Chromium browser on its own (your default one if it is Chromium-based).
- macOS, Windows or Linux.

## Start

| System | Double-click | Or from a terminal, in the project folder |
|---|---|---|
| macOS / Linux | `Start Spider Analyst.command` | `python3 launch.py` |
| Windows | `Start Spider Analyst.bat` | `py launch.py` |

The first start creates a virtual environment (`.venv`), installs the dependencies (1–2 minutes) and asks for a
name and email to identify yourself to the SEC (optional). Then the app opens at `http://127.0.0.1:8765`.
Close the terminal window (or press Ctrl+C) to stop it.

- **macOS blocks the double-click** ("cannot be verified"): use `python3 launch.py` from Terminal, or go to
  *System Settings → Privacy & Security*, click *Open Anyway* at the bottom and try again.
- **Windows shows "Windows protected your PC"**: click *More info → Run anyway*, or use `py launch.py`.
- Options: `SPIDER_PORT=9000` changes the port, `SPIDER_LANG=en|it` forces the interface language, `SPIDER_BROWSER="Brave Browser"` (macOS app name, or an
  executable path elsewhere) forces a browser, `--no-browser` starts only the server.

## What it reads

| You look for | The document the spider reads | Source |
|---|---|---|
| US-listed companies (MSFT, NVDA, …) | Latest 10-K, 20-F or 40-F in inline XBRL | SEC EDGAR |
| European companies (Ferrari, ENI, …) | ESEF annual report in inline XBRL | filings.xbrl.org |
| Crypto, indices, currencies, commodities, ETFs, funds (BTC-USD, ^GSPC, EURUSD=X, GC=F, …) | A generated market sheet: chart, calendar-year and monthly returns, volatility, drawdowns | Yahoo Finance (Coinbase as fallback for crypto) |
| Any other document, in English or Italian: annual report or statements as PDF/HTML, KID, prospectus, factsheet, whitepaper | The file you upload (*Upload a document*) or the URL you paste | Your file / URL |

Each search result offers two actions: **Analyse** (the spider reads it) or **Download original** — the filing as
published on SEC EDGAR (`.htm`), the ESEF report from filings.xbrl.org (`.xhtml`), or for market instruments the
daily price history as CSV.

In inline XBRL filings every figure is an XBRL tag, so its value and exact position are known — no guessing.
In untagged PDF/HTML the figures are the ones printed on the page. In financial statements (English or Italian)
the spider recognises the rows from their labels — Revenue / Ricavi, Net income / Utile netto, Diluted EPS, Net
cash provided by operating activities, Purchases of property, plant and equipment… — reads the current and prior
year columns and the scale ("in millions", "in migliaia di euro"), and computes the card, checks and findings as
for XBRL filings. For other documents (KID, prospectus) it lists the main figures, or the AI model picks them.

## Report

- **Card (financial statements)**: revenue, net income, diluted EPS, free cash flow (operating cash flow − capex),
  each with its year-on-year change and page.
- **Arithmetic checks**: gross profit = revenue − cost of revenue; assets = liabilities + equity;
  pre-tax income − taxes ≈ net income; diluted EPS × diluted shares ≈ net income.
- **Findings**: growth, margins, cash conversion, shareholder returns, interest coverage, debt due vs cash,
  liquidity, leverage — deterministic calculations on the document's figures.
- **Language**: Italian or English, chosen on the home page or while reading (the report is regenerated:
  findings, checks, labels, number formats — `$120B` / `$120 mld`).
- **Download**: *Download report (PDF)* downloads a PDF in the app's style, drawn by the local server in a fraction
  of a second (no browser involved). It contains the summary card and findings, then charts built only from the
  figures read:
  - financial statements: current vs prior year for the main lines, margins, balance sheet structure (assets vs
    liabilities and equity), cash bridge from operating cash flow to free cash flow and shareholder returns, and a
    key-ratios table with both years;
  - market sheets: price chart, calendar-year returns, drawdown, monthly-returns heatmap and a return/risk table;
  - then the arithmetic checks and every figure read with its page.

## The spider

Like a spider on a wall, it climbs straight down the middle of each page, head first, never sideways, hanging
from a silk line, and reaches each figure with its pink line. Narrow black body with a blue outline and a cyan head, eight cyan legs of three segments with pink joints and feet
that land on words (two alternating sets, never more than four legs in the air),
pink and cyan pings to the words and numbers ahead of it, and neon highlights (outlines, fills, enlarged words,
rotated strips). It moves like a real spider: quick dashes that brake hard, with short freezes on longer stretches,
a body that sways and stretches with its stride, a pulse and a strike of the front legs when it grabs a figure,
front legs that keep tapping the words while it reads, and a silk line that swings as it pulls on it.

It always reads **every** figure on the pages it opens and adapts its pace to how many there are (about
12 seconds for a short document, up to about 75 seconds for a long one). The "N of M figures read" counter counts
the figures on those pages, and the panel lists which pages of the document were read (the cover and the pages
with the financial statements and the key figures).

## AI findings (optional)

Add an API key in *Settings* to tick *Findings written by AI*. Supported providers:

| Provider | Default model (editable) | Key from |
|---|---|---|
| Anthropic (Claude) | `claude-opus-5-5` | console.anthropic.com · `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-5` | platform.openai.com · `OPENAI_API_KEY` |
| Google Gemini | `gemini-2.5-pro` | aistudio.google.com · `GEMINI_API_KEY` |
| Mistral | `mistral-large-latest` | console.mistral.ai · `MISTRAL_API_KEY` |
| xAI (Grok) | `grok-4` | console.x.ai · `XAI_API_KEY` |
| DeepSeek | `deepseek-chat` | platform.deepseek.com · `DEEPSEEK_API_KEY` |
| OpenRouter (any model it offers) | `openrouter/auto` | openrouter.ai · `OPENROUTER_API_KEY` |

The model only receives the figures already read, each with an id; any observation with a number that is not among
the figures it cites is dropped, so the report never shows numbers the document does not contain. On PDFs it picks
the important figures among those found on the pages. Keys are stored in `~/.spider-analyst/ai.json` (readable only
by you) or read from the environment variables above. Everything else works without a key.

## Data and privacy

The server listens on `127.0.0.1` only. Documents and responses are cached in `.data/`. The SEC identity is in
`~/.spider-analyst/config.json`; the default is generic and no email is sent unless you enter one.

## Known limits

- Financial figures depend on the issuer's tags: rare or custom concepts may be missing (the card shows "—").
- Free cash flow uses capex on property, plant and equipment; some companies also include intangibles.
- Yahoo Finance has no official API. It rejects clients that do not look like a browser (HTTP 429), so the app
  talks to it through `curl_cffi`, which presents itself as Chrome, with a session cookie and both hosts. For crypto
  pairs (BTC-USD, ETH-EUR, …) the price history falls back to Coinbase's public API if Yahoo is still unavailable;
  for indices, currencies and commodities Yahoo is the only source, so try again a few minutes later.

## Project layout

```
launch.py                     cross-platform launcher (venv, dependencies, server, Chromium browser)
Start Spider Analyst.command  macOS/Linux double-click wrapper
Start Spider Analyst.bat      Windows double-click wrapper
server.py                     FastAPI server (localhost only)
analyst/                      sources, iXBRL parser, financials, statements, market sheet, PDF/HTML, AI providers, PDF report and charts, i18n
web/                          interface, spider animation, live report
tests/                        offline tests on synthetic documents and simulated APIs
```

## Tests

```
.venv/bin/pip install pytest reportlab        # Windows: .venv\Scripts\pip install pytest reportlab
.venv/bin/python -m pytest -q
```

The tests use synthetic documents (made-up companies and numbers) and simulated SEC, filings.xbrl.org and Yahoo
responses; they need no network.
