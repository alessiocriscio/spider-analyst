# Spider Analyst — design notes

A from-scratch rebuild of the tool shown in @buildwithbrock's videos ("Wall Street's newest analyst is a spider"):
an animated spider reads a financial document page by page, its legs walk on the words, the figures it reads light
up and flow into a live report; at the end come the key findings and a summary card. It must work for **any
financial instrument** and run locally (macOS, Windows, Linux) in a Chromium-based browser.

## Status

- [x] `analyst/ixbrl.py` — inline XBRL parser (pages, `data-f` facts, `data-h` headings, row labels, filtered CSS)
- [x] `analyst/sources.py` — SEC EDGAR, ESEF (filings.xbrl.org), Yahoo Finance (cookie + crumb, retries), disk cache
- [x] `analyst/financials.py` — us-gaap / ifrs-full metrics, periods, ratios, checks, findings, card
- [x] `analyst/statements.py` — untagged statements (English / Italian row labels → metrics, losses and deficits too)
- [x] `analyst/tables.py` — HTML statement tables: grid with colspans, column periods from the headers (FY, 6M, 3M,
      as of), change / pro forma / percentage columns, scale; latest period vs the same period a year earlier
- [x] Paged HTML (EDGAR PDF-to-HTML page boxes, SGML envelopes), printed page numbers for citations
- [x] `analyst/themes.py` + `web/themes.js` — colour themes for the app, the spider and the PDF
- [x] `analyst/market.py` — generated market sheet for instruments without statements
- [x] `analyst/generic.py` — PDF (page image + word layer) and plain HTML
- [x] `analyst/ai.py` — AI providers (required): Anthropic SDK (streamed); OpenAI, Gemini, Mistral, xAI, DeepSeek,
      OpenRouter via OpenAI-compatible endpoints; Claude Pro/Max via the user's Claude Code CLI (`-p`, no tools,
      `--json-schema`), ChatGPT plans via the user's Codex CLI (`exec`, read-only sandbox, `--output-schema`); a test call
- [x] `analyst/reader.py` — the AI reads the document (page selection under a ~65k-token budget, summary, sections,
      figures with page, findings, statement items → metrics); every number checked against the pages
- [x] `analyst/pdfreport.py` + `analyst/charts.py` — report PDF drawn with reportlab in the app's style, with charts
      (results vs prior year, margins, balance sheet, cash bridge, ratios; price, yearly returns, drawdown, monthly
      heatmap, risk) — served at `/api/doc/{id}/report.pdf`
- [x] `analyst/i18n.py` — interface language (system) and report language (Italian / English)
- [x] `analyst/pipeline.py` — one analysis format for the web app, sanitised `view.html`
- [x] `server.py`, `web/` — spider animation, pacing, live report, finale, report download; search results offer
      *Analyse* or *Download original* (`/api/original`: SEC filing, ESEF report, price history CSV)
- [x] `launch.py` + `Start Spider Analyst.command` / `.bat` — venv, dependencies, server, Chromium browser
- [x] Offline tests (`tests/`): synthetic documents, simulated APIs, launcher browser choice
- [x] Real documents, read without the AI (the deterministic layer the AI builds on), figures compared with the
      published ones:
      - 19 PDFs from FinanceBench (github.com/patronus-ai/financebench): 10-K/10-Q of Adobe, Amazon, AmEx, Best Buy,
        Boeing, Boston Properties, Foot Locker, JPMorgan, PG&E; earnings releases of Amcor, Costco, Intel, J&J,
        McDonald's; AMD annual report; two 8-Ks (no statements: no card, no fake figures).
      - 10 ESEF reports from filings.xbrl.org: Ferrari, LVMH, Moncler, Intesa Sanpaolo, Enel (130 MB), Prysmian,
        Heineken, Stellantis, Generali, Air Liquide.
      - The Anthropic S-1 (13.5 MB paged HTML): acceptance test of the bug report, 5/5 checks.
      Remaining gaps: Boston Properties (an LP/REIT 10-K) has no EPS; Generali tags no EPS; two explained gaps
      (AMD gross profit: amortisation sits in between; Boeing operating costs); Air Liquide's exchange-rate line is
      an issuer concept with a French label, shown as an explained gap.
- [ ] SEC EDGAR live and a real AI provider from the cloud dev session: sec.gov was not reachable and no API key is
      available there; both are covered by simulated responses in the tests.
- [ ] Safari / Firefox: not supported (the app shows a notice); only Chromium-based browsers are tested.

## Data sources

| Instrument | Document the spider reads | Source |
|---|---|---|
| SEC registrants | 10-K, 20-F, 40-F (iXBRL); before an IPO the latest S-1/F-1/424B prospectus (often untagged) | `www.sec.gov/files/company_tickers.json`, `data.sec.gov/submissions/CIK##########.json`, `www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}` |
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
Checks (only those the figures allow): gross = revenue − cost; revenue − operating expenses = operating income;
pre-tax − taxes = net income; assets = liabilities + redeemable preferred + equity; EPS × shares ≈ net income;
CFO + CFI + CFF ≈ change in cash.
Every figure cites its page; the occurrence highlighted is the one on the page with most facts (the statements).

## Interface

- Document in a full-height same-origin iframe (sandboxed, no scripts), scaled; overlays in document coordinates.
- Spider (canvas), modelled on the reference clips: narrow outlined body with a head dot, three-segment legs solved
  with FABRIK, alternating gait with at most four legs in the air, feet planted on words, trailing silk line,
  pink/cyan pings, neon highlights; body follows the itinerary with a damped spring.
- Pacing: every figure on the shown pages is visited; the pace scales with their number (≈12 s to ≈75 s).
- Speed: PDF pages are chosen from plain text and only the chosen pages get word boxes and (JPEG) images.
- Report panel: "N of M figures read", pages read, table of the section being read, other figures with page.
- Finale: key findings one by one, then the card (4 tiles with YoY change and page, 3 findings, figures and checks).
- Interface in English, Italian when the OS language is Italian (server-side detection: macOS AppleLanguages,
  Windows UI language, LANG elsewhere); report in English or Italian; downloadable PDF report with charts.

## AI (required)

The first start shows a setup that cannot be skipped: a subscription (Claude Code or Codex CLI, installed and
signed in by the user) or an API key, then a test call. Anthropic through the `anthropic` SDK 2.x (`claude-opus-5-5`, `output_config` json_schema, `fallbacks="default"`,
refusals handled); OpenAI, Google Gemini, Mistral, xAI, DeepSeek and OpenRouter through their OpenAI-compatible
`/chat/completions` endpoints with JSON mode (retried without it when a model rejects it). Provider, key and model
are set in Settings (`~/.spider-analyst/ai.json`) or via environment variables. Numbers in generated observations
must match the figures they cite, otherwise the observation is dropped; provider errors become report warnings.
