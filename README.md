# Spider Analyst

A spider reads a financial document on your computer: it walks over the words, the figures it reads light up
and flow into a report that builds up live, and at the end it shows the key findings and a summary card where
every number cites the page it comes from.

A from-scratch rebuild of the idea shown in @buildwithbrock's videos. It contains none of his code.

The app interface is in Italian; the report can be produced in Italian or English.

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
- Options: `SPIDER_PORT=9000` changes the port, `SPIDER_BROWSER="Brave Browser"` (macOS app name, or an
  executable path elsewhere) forces a browser, `--no-browser` starts only the server.

## What it reads

| You look for | The document the spider reads | Source |
|---|---|---|
| US-listed companies (MSFT, NVDA, …) | Latest 10-K, 20-F or 40-F in inline XBRL | SEC EDGAR |
| European companies (Ferrari, ENI, …) | ESEF annual report in inline XBRL | filings.xbrl.org |
| Crypto, indices, currencies, commodities, ETFs, funds (BTC-USD, ^GSPC, EURUSD=X, GC=F, …) | A generated market sheet: chart, calendar-year and monthly returns, volatility, drawdowns | Yahoo Finance |
| Any other document, in English or Italian: annual report or statements as PDF/HTML, KID, prospectus, factsheet, whitepaper | The file you upload (*Carica un documento*) or the URL you paste | Your file / URL |

In inline XBRL filings every figure is an XBRL tag, so its value and exact position are known — no guessing.
In untagged PDF/HTML the figures are the ones printed on the page. In financial statements (English or Italian)
the spider recognises the rows from their labels — Revenue / Ricavi, Net income / Utile netto, Diluted EPS, Net
cash provided by operating activities, Purchases of property, plant and equipment… — reads the current and prior
year columns and the scale ("in millions", "in migliaia di euro"), and computes the card, checks and findings as
for XBRL filings. For other documents (KID, prospectus) it lists the main figures, or Claude picks them.

## Report

- **Card (financial statements)**: revenue, net income, diluted EPS, free cash flow (operating cash flow − capex),
  each with its year-on-year change and page.
- **Arithmetic checks**: gross profit = revenue − cost of revenue; assets = liabilities + equity;
  pre-tax income − taxes ≈ net income; diluted EPS × diluted shares ≈ net income.
- **Findings**: growth, margins, cash conversion, shareholder returns, interest coverage, debt due vs cash,
  liquidity, leverage — deterministic calculations on the document's figures.
- **Language**: Italian or English, chosen on the home page or while reading (the report is regenerated:
  findings, checks, labels, number formats — `$120B` / `$120 mld`).
- **Download**: *Scarica report* saves a self-contained HTML file with the card, findings, checks and every figure
  read with its page. To get a PDF, open it and use File → Print → Save as PDF.

## The spider

Narrow black body with a blue outline and a cyan head, eight cyan legs of three segments with pink joints and feet
that land on words (two alternating sets, never more than four legs in the air), a silk line trailing behind,
pink and cyan pings to the words and numbers ahead of it, and neon highlights (outlines, fills, enlarged words,
rotated strips).

It always reads **every** figure on the pages it opens and adapts its pace to how many there are (about
20 seconds for a short document, up to about 2 minutes for a long one). The "N of M figures read" counter counts
the figures on those pages, and the panel lists which pages of the document were read (the cover and the pages
with the financial statements and the key figures).

## Claude (optional)

With an Anthropic API key (*Impostazioni*, or `ANTHROPIC_API_KEY`) you can tick *Osservazioni scritte da Claude*
(model `claude-opus-5-5`). Claude only receives the figures already read, each with an id; any observation with a
number that is not among the figures it cites is dropped. On PDFs it picks the important figures among those
found on the pages. Everything else works without a key, which is stored in `~/.spider-analyst/anthropic_key`.

## Data and privacy

The server listens on `127.0.0.1` only. Documents and responses are cached in `.data/`. The SEC identity is in
`~/.spider-analyst/config.json`; the default is generic and no email is sent unless you enter one.

## Known limits

- Financial figures depend on the issuer's tags: rare or custom concepts may be missing (the card shows "—").
- Free cash flow uses capex on property, plant and equipment; some companies also include intangibles.
- Yahoo Finance has no official API and sometimes rate-limits (HTTP 429): the app retries with a session
  cookie and on the second host; if it still fails, type the symbol directly (e.g. BTC-USD) and try again later.

## Project layout

```
launch.py                     cross-platform launcher (venv, dependencies, server, Chromium browser)
Start Spider Analyst.command  macOS/Linux double-click wrapper
Start Spider Analyst.bat      Windows double-click wrapper
server.py                     FastAPI server (localhost only)
analyst/                      sources, iXBRL parser, financials, statements, market sheet, PDF/HTML, Claude, i18n
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
