# Spider Analyst — design notes

A from-scratch rebuild of the tool shown in @buildwithbrock's videos ("Wall Street's newest analyst is a spider"):
an animated spider reads a financial document page by page, its legs walk on the words, the figures it reads light
up and flow into a live report; at the end come the key findings and a summary card. It must work for **any
financial instrument** and run locally (macOS, Windows, Linux) in a Chromium-based browser.

## Status

- [x] `analyst/ixbrl.py` — inline XBRL parser (pages, `data-f` facts, `data-h` headings, row labels, filtered CSS)
- [x] `analyst/sources.py` — SEC EDGAR, ESEF (filings.xbrl.org), Yahoo Finance (cookie + crumb, retries), disk cache
- [x] `analyst/financials.py` — us-gaap / ifrs-full metrics, periods, ratios, checks, findings, card
- [x] `analyst/statements.py` — untagged statements (English / Italian row labels → metrics)
- [x] `analyst/market.py` — generated market sheet for instruments without statements
- [x] `analyst/generic.py` — PDF (page image + word layer) and plain HTML
- [x] `analyst/ai.py` — optional AI pass (Anthropic SDK; OpenAI, Gemini, Mistral, xAI, DeepSeek, OpenRouter via
      OpenAI-compatible endpoints), limited to figures already read, numbers validated
- [x] `analyst/pdfexport.py` — report PDF printed by the installed Chromium (headless), print-dialog fallback
- [x] `analyst/i18n.py` — interface language (system) and report language (Italian / English)
- [x] `analyst/pipeline.py` — one analysis format for the web app, sanitised `view.html`
- [x] `server.py`, `web/` — spider animation, pacing, live report, finale, report download
- [x] `launch.py` + `Start Spider Analyst.command` / `.bat` — venv, dependencies, server, Chromium browser
- [x] Offline tests (`tests/`): synthetic documents, simulated APIs, launcher browser choice
- [ ] Real-data run (MSFT 10-K, Ferrari ESEF, BTC-USD) on the user's machine: the cloud dev session could not
      reach sec.gov / filings.xbrl.org / Yahoo.
- [ ] Safari / Firefox: not supported (the app shows a notice); only Chromium-based browsers are tested.

## Data sources

| Instrument | Document the spider reads | Source |
|---|---|---|
| SEC registrants | 10-K, 20-F, 40-F (iXBRL) | `www.sec.gov/files/company_tickers.json`, `data.sec.gov/submissions/CIK##########.json`, `www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}` |
| EU/UK companies | ESEF annual report (iXBRL, ifrs-full) | `filings.xbrl.org/api/entities?filter=[ilike]`, `/api/entities/{LEI}/filings` → `report_url` |
| Crypto, indices, FX, commodities, ETFs, funds | Generated market sheet | Yahoo `/v8/finance/chart/{symbol}`, search `/v1/finance/search` |
| Anything else | Uploaded or linked PDF / HTML | upload / URL |

- SEC requires a User-Agent with a contact: `SPIDER_SEC_UA` or `~/.spider-analyst/config.json`; the launcher asks
  once, the default is generic.
- Page structure: SEC = `<body>` children split by `<hr style="page-break-after:always">`; ESEF = `div.pageView`
  (HTML pages rendered from PDF, tens of MB, CSS with base64 images → CSS filtered to the classes on shown pages).

## Metrics (us-gaap and ifrs-full concepts with fallbacks)

Income statement: revenue, cost of revenue, gross profit, R&D, operating income, pre-tax income, taxes, net income,
diluted EPS, interest expense. Balance sheet: cash, current assets, total assets, current liabilities, total
liabilities (or derived), equity, debt. Cash flow: operating cash flow, capex, buybacks, dividends, stock-based
compensation. Debt due within 12 months.

Period: the non-dimensional context ending on `DocumentPeriodEndDate`; current vs prior year.
Derived: FCF, margins, YoY growth, interest coverage, debt/assets, equity multiplier, % of FCF returned, current ratio.
Checks: gross = revenue − cost; assets = liabilities + equity; pre-tax − taxes ≈ net income; EPS × shares ≈ net income.
Every figure cites its page; the occurrence highlighted is the one on the page with most facts (the statements).

## Interface

- Document in a full-height same-origin iframe (sandboxed, no scripts), scaled; overlays in document coordinates.
- Spider (canvas), modelled on the reference clips: narrow outlined body with a head dot, three-segment legs solved
  with FABRIK, alternating gait with at most four legs in the air, feet planted on words, trailing silk line,
  pink/cyan pings, neon highlights; body follows the itinerary with a damped spring.
- Pacing: every figure on the shown pages is visited; the pace scales with their number (≈20 s to ≈2 min).
- Report panel: "N of M figures read", pages read, table of the section being read, other figures with page.
- Finale: key findings one by one, then the card (4 tiles with YoY change and page, 3 findings, figures and checks).
- Interface in English, Italian when the OS language is Italian (server-side detection: macOS AppleLanguages,
  Windows UI language, LANG elsewhere); report in English or Italian; downloadable self-contained HTML report.

## AI (optional)

Anthropic through the `anthropic` SDK 2.x (`claude-opus-5-5`, `output_config` json_schema, `fallbacks="default"`,
refusals handled); OpenAI, Google Gemini, Mistral, xAI, DeepSeek and OpenRouter through their OpenAI-compatible
`/chat/completions` endpoints with JSON mode (retried without it when a model rejects it). Provider, key and model
are set in Settings (`~/.spider-analyst/ai.json`) or via environment variables. Numbers in generated observations
must match the figures they cite, otherwise the observation is dropped; provider errors become report warnings.
