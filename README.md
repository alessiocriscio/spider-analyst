# Spider Analyst

*by Alessio Criscio*

Spider Analyst: an animated spider reads financial documents (10-K, ESEF, PDFs, market data) and builds a live report. Runs locally on macOS, Windows and Linux in a Chromium browser. Completely Open Source and free.

An AI reads every document first — what it is, how the business works, the results, the risks, the offering — and
the spider then walks over the pages that hold what it found. Every number the AI writes is checked against the
page it comes from.

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
- **An AI** (asked on the first start, required): your Claude Pro/Max or ChatGPT subscription, or an API key — see
  [The AI](#the-ai-required).

## Start

| System | Double-click | Or from a terminal, in the project folder |
|---|---|---|
| macOS / Linux | `Start Spider Analyst.command` | `python3 launch.py` |
| Windows | `Start Spider Analyst.bat` | `py launch.py` |

The first start creates a virtual environment (`.venv`), installs the dependencies (1–2 minutes) and asks for a
name and email to identify yourself to the SEC (optional). Then the app opens at `http://127.0.0.1:8765` and, the first time, asks you to connect an AI.
Close the terminal window (or press Ctrl+C) to stop it.

- **macOS blocks the double-click** ("cannot be verified"): use `python3 launch.py` from Terminal, or go to
  *System Settings → Privacy & Security*, click *Open Anyway* at the bottom and try again.
- **Windows shows "Windows protected your PC"**: click *More info → Run anyway*, or use `py launch.py`.
- Options: `SPIDER_PORT=9000` changes the port, `SPIDER_LANG=en|it` forces the interface language, `SPIDER_BROWSER="Brave Browser"` (macOS app name, or an
  executable path elsewhere) forces a browser, `--no-browser` starts only the server.

## What it reads

| You look for | The document the spider reads | Source |
|---|---|---|
| US-listed companies (MSFT, NVDA, …) | Latest 10-K, 20-F or 40-F in inline XBRL; under *Other documents* the quarterly reports (10-Q), results releases (8-K item 2.02, read from exhibit 99.1), prospectuses and earlier years | SEC EDGAR |
| Companies before an IPO (no ticker yet) | Latest S-1, F-1 or 424B prospectus (tagged or not) | SEC EDGAR full-text search |
| European companies (Ferrari, ENI, …) | ESEF annual report in inline XBRL; earlier years under *Other documents* | filings.xbrl.org |
| Crypto, indices, currencies, commodities, ETFs, funds (BTC-USD, ^GSPC, EURUSD=X, GC=F, …) | A generated market sheet: chart, calendar-year and monthly returns, volatility, drawdowns | Yahoo Finance (Coinbase as fallback for crypto) |
| Any other document, in English or Italian: annual report or statements as PDF/HTML, KID, prospectus, factsheet, whitepaper | The file you upload (*Upload a document*) or the URL you paste | Your file / URL |

**Not in the search** (the home page says so too): Italian half-year reports and other documents not filed in ESEF, accounts of
unlisted companies (business register), fund KIDs and factsheets — upload the PDF or paste its address.

Companies without a ticker are found through EDGAR full-text search among the filers of prospectuses and annual
reports. Each search result offers two actions: **Analyse** (the spider reads it) or **Download original** — the filing as
published on SEC EDGAR (`.htm`), the ESEF report from filings.xbrl.org (`.xhtml`), or for market instruments the
daily price history as CSV.

In inline XBRL filings every figure is an XBRL tag, so its value and exact position are known — no guessing.
In untagged PDF/HTML the figures are the ones printed on the page:

- **Pages**: HTML filings are split into their printed pages — page breaks, or the fixed-size page boxes of EDGAR's
  PDF-to-HTML renderings (an S-1 of 400+ pages included); EDGAR submission envelopes (`<DOCUMENT><TYPE>S-1…`) are
  removed. Citations use the page numbers printed on the page ("p. 22", "p. F-7").
- **Tables**: statement tables are read as tables: every cell gets its row and its column, and the column header
  gives the period — "Year Ended December 31, 2025", "Six Months Ended June 30, 2026", "As of June 30, 2026";
  "$ Change", "% Change", "Pro Forma" and "As Adjusted" columns are left out, percentage-of-revenue tables are
  marked as percentages, the scale comes from "(in millions…)" (share counts "in thousands" too).
- **Periods**: the current period is the latest one (an interim period when there is one) and it is compared with
  the same period a year earlier; balance sheet items with the latest date and the previous year end. The same line
  printed in the summary, the MD&A and the statements is counted once.
- **Rows**: Revenue / Ricavi, Net income or Net loss / Utile netto, "Net loss per share…, basic and diluted",
  Operating loss, Loss before provision for income taxes, Total operating expenses, Redeemable convertible preferred
  stock, Total stockholders' deficit, Net cash provided by (used in) operating / investing / financing activities,
  Purchases of property and equipment, Net increase in cash…
- **Not figures**: days in dates ("June 30"), footnote marks ("Net loss(2)", "(Note 13)"), par values, phone
  numbers and ZIP codes are skipped.
- In PDFs the rows are recognised from their labels on the page with the column periods and scale: years in either
  order (2022 2023 2024 or the reverse), quarter codes (1Q23 vs 1Q22), "Three Months Ended", "Thirteen Weeks Ended",
  "Second Quarter", dates printed on a line of their own; note-reference and "% to sales" columns are left out, labels
  wrapped onto two lines are joined, the consolidated statements win over the parent-company ones and over segment
  tables. Statement lines no rule knows are recognised by the AI, whose values are checked against the page before
  they feed the card, checks and charts.
- **Banks and insurers**: net interest and other banking income, total net revenue, insurance revenue (IFRS 17) count
  as revenue; free cash flow is not computed for them (capex means little for a bank's cash flow statement).
- **ESEF reports** laid out with page containers (`pf`, `page…` classes, nested) or with no pages at all (the text
  is cut into pages at headings) are split too; issuer-specific concepts are recognised by the label of their row.

## Report

- **What the AI understood**: the kind of document, a short summary and the key points by theme (business, results,
  cash, risks, offering, ownership…), each with its pages — in the side panel at the end of the reading and in the PDF.
- **Card (financial statements)**: revenue, net income (or net loss), diluted EPS, free cash flow (operating cash flow −
  capex, marked as computed), each with the exact amount, the change against the comparative period ("+1,300% vs
  H1 2025") — or the comparative value when a loss makes a percentage meaningless — and the page.
- **Arithmetic checks**, only those the figures allow: revenue − operating expenses = operating income;
  pre-tax income − taxes = net income; assets = liabilities (+ redeemable preferred stock) + equity; diluted EPS ×
  diluted shares ≈ net income; operating + investing + financing cash flows (+ exchange rates, + cash moved to assets
  held for sale) ≈ change in cash; gross profit = revenue − cost of revenue. A gap that other lines explain (amortisation
  between gross profit and costs, an exchange-rate line not read) is shown with its amount and the reason, not as a
  pass. When no check is possible the report says so; it never calls figures "verified" without a check.
- **Findings**: growth, margins, cash conversion, shareholder returns, interest coverage, debt due vs cash,
  liquidity, leverage — deterministic calculations on the document's figures.
- **Language**: Italian or English, chosen on the home page or while reading (the report is regenerated:
  findings, checks, labels, number formats — `$120B` / `$120 mld`).
- **Download** (menu in the reading view): *Report (PDF)*; *Slides (PowerPoint)* — a 16:9 deck with native, editable charts,
  every slide citing the printed pages and the source; *Figures (Excel)* — statements as numbers with unit and page, changes
  and free cash flow as formulas, ratios, checks, every figure read (prices and returns for market sheets).
  The PDF is drawn in the app's style and colour theme by the local server
  in a fraction of a second (no browser involved). No pages of raw figures: it holds
  - the summary card, the AI's summary and the key findings;
  - **financial highlights**: income statement, balance sheet and cash flows with the two periods compared, the change
    and the page of each line;
  - charts: revenue and net income over every period the document prints (years, then the latest interim pair),
    results against the comparative period, margins, balance sheet (side by side when there is a deficit or
    redeemable preferred stock), where the operating cash goes; for market sheets the price chart, calendar-year
    returns, drawdown and the monthly-returns heatmap;
  - what the AI understood section by section, key ratios, the arithmetic checks with their pages, and how the
    document was read (pages shown, pages the AI read, periods compared).
- **Themes**: Neon, Ocean, Sunset, Forest, Mono and Midnight (dark) — the swatches on the home page and in the reading
  bar change the interface, the spider, the highlights and the PDF; the choice is remembered in the browser.

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

## The AI (required)

The first time the page opens it asks how to connect an AI, and checks that it answers. Two ways:

**A subscription you already have.** Spider Analyst runs the vendor's official command-line tool, which you install
and sign in to yourself; the app never sees or stores your credentials, and the usage counts toward your plan's limits.

| Subscription | Tool | Set up once |
|---|---|---|
| Claude Pro / Max | [Claude Code](https://claude.com/product/claude-code) | install it, run `claude`, sign in with your Claude account |
| ChatGPT Plus / Pro | [Codex CLI](https://github.com/openai/codex) | `npm install -g @openai/codex`, run `codex`, choose *Sign in with ChatGPT* |

The tool runs with no tools enabled (Claude Code: `--tools ""`) or in a read-only sandbox (Codex), in an empty
folder, and must return JSON that matches the expected schema.

> Terms: Anthropic's [Claude Code legal page](https://code.claude.com/docs/en/legal-and-compliance) says that
> third-party developers may not "route requests through Free, Pro, or Max plan credentials on behalf of their users",
> while it does not prevent an end user from signing in to the unmodified Claude Code binary with their own
> subscription. Spider Analyst does the latter (your own Claude Code, your own account, on your computer), but whether
> this kind of use fits your plan is for you to judge; Anthropic advises an API key for products built on Claude. If
> in doubt, use an API key.

**An API key** (billed by the provider to your account):

| Provider | Default model (editable) | Key from |
|---|---|---|
| Anthropic (Claude) | `claude-opus-5-5` | console.anthropic.com · `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-5` | platform.openai.com · `OPENAI_API_KEY` |
| Google Gemini | `gemini-2.5-pro` | aistudio.google.com · `GEMINI_API_KEY` |
| Mistral | `mistral-large-latest` | console.mistral.ai · `MISTRAL_API_KEY` |
| xAI (Grok) | `grok-4` | console.x.ai · `XAI_API_KEY` |
| DeepSeek | `deepseek-chat` | platform.deepseek.com · `DEEPSEEK_API_KEY` |
| OpenRouter (any model it offers) | `openrouter/auto` | openrouter.ai · `OPENROUTER_API_KEY` |

**What the AI gets and what is checked.** The text of the pages — all of them when they fit in about 65k tokens,
otherwise the cover, the summary sections (prospectus summary, risk factors, MD&A, use of proceeds…) and the pages
densest with financial figures — plus, for XBRL filings, the tagged figures already read. It returns the kind of
document, a summary, key points by theme, up to 30 important figures with their page, and findings. A figure is kept
only if its value is printed on the page it cites; a sentence is kept only if each of its numbers is printed in the
pages read (a finding: in the figures it cites). So the report never shows numbers the document does not contain.
If the AI fails (network, limits), the reading goes on with the rule-based extraction and the report says so.

Keys and the choice of provider are stored in `~/.spider-analyst/ai.json` (readable only by you) or read from the
environment variables above.

## Data and privacy

The server listens on `127.0.0.1` only. Documents and responses are cached in `.data/`. The SEC identity is in
`~/.spider-analyst/config.json`; the default is generic and no email is sent unless you enter one.

## Known limits

- A document already read is kept in `.data/`; after an update of Spider Analyst it is read again (the cache key
  includes the version of the reading).
- The AI reading takes from a few seconds to a couple of minutes for a long prospectus, and costs what the provider
  charges for about 65k input tokens (or counts toward your subscription's limits). Each report language is a new reading.
- Financial figures depend on the issuer's tags: rare or custom concepts may be missing (the card shows "—").
- Documents up to 400 MB (a large ESEF report such as Enel's is 130 MB and takes about 10 s and 700 MB of memory).
  filings.xbrl.org and SEC EDGAR answer "busy" (HTTP 429/503) at times: the app waits and retries three times.
- Untagged PDFs are read from their layout: a statement printed as an image (a scan) has no text to read, and an
  unusual layout can leave a line unread or take it from another table; the page of every figure is shown so it can
  be checked. Checked on 19 real SEC filings and earnings releases (FinanceBench) and 10 ESEF reports — see PLAN.md.
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
analyst/                      sources, iXBRL parser, tables, financials, statements, market sheet, PDF/HTML, AI providers and reader, PDF report, charts and themes, i18n
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
