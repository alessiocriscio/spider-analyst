# Implementation plan

Working notes to resume after a context reset. Read this first, then `PLAN.md` (design notes) and `README.md`.

## Ground rules

- Repo `alessiocriscio/spider-analyst`, branch `main`, push directly (no PRs unless asked). The user installs from the
  zip into a folder named `spider-analyst-main`.
- Commit author: `alessiocriscio <262817053+alessiocriscio@users.noreply.github.com>`; trailers
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01SJf4EE1JxcFnmUfYg7YFZu`.
  No model ids in commits or code.
- Answer the user in Italian, concise, honest; cite sources.
- Never commit the user's documents (the Anthropic S-1 lives only in the scratchpad).
- Do not break what is verified: the S-1 acceptance test (`tests/test_tables.py`), real-document verification
  (`verify.py`, below), 53+ offline tests.

## Done (commits on main)

| Commit | What |
|---|---|
| 31a566e | Livelier spider (gait, sway, grab pulse) |
| 9ad73dd | AI required (Claude/ChatGPT subscriptions via CLI, API keys), `reader.py`, pre-IPO prospectuses |
| 60f9f11 | Paged HTML (S-1), statement tables with periods, real checks, new PDF report, colour themes |
| 769a3cc | Real filings: PDF statements (year order, quarter codes, note/% columns), ESEF layouts, banks/insurers, cash check, 400 MB, retries |

## Now: from "reads a document" to "a deliverable for work"

Status: `[ ]` todo, `[~]` in progress, `[x]` done.

### 1. Export for presentations and models

- [x] `analyst/pptx_report.py` — PowerPoint deck (16:9) built with python-pptx from the analysis dict:
      title, headline figures (card), key findings, results vs comparative (native, editable bar chart), trend
      over time, margins, balance sheet, cash flow, statement highlights table, what the AI understood, checks,
      sources. Every slide carries its page references ("p. F-7") and the source. Theme colours from
      `analyst/themes.py`. Market sheets: price line, calendar-year returns, return/risk table.
- [x] `analyst/xlsx_export.py` — Excel workbook (XlsxWriter, already a python-pptx dependency): Summary, Statements
      (current, comparative, change as a formula, page), Ratios, Checks, Figures (every figure read with period
      and page), Prices for market sheets. Numbers are numbers (not text), with number formats; free cash flow as
      a formula of the cells it comes from.
- [x] `server.py`: `GET /api/doc/{id}/report.pptx?theme=` and `GET /api/doc/{id}/data.xlsx`.
- [x] `web/`: download menu (PDF / PowerPoint / Excel) where the PDF button is now (browser check: with the e2e run in step 4).
- [x] `requirements.txt`: python-pptx, XlsxWriter; reportlab range widened to the tested 5.x.
- [x] Tests: deck and workbook for the S-1, an ESEF-like iXBRL fixture, a market sheet; open them back with
      python-pptx / zip and check slides, charts, formulas, page tags; server routes.
- [x] Render a deck with LibreOffice (`soffice --headless --convert-to pdf`) and look at the slides.

Notes: deck 10–13 slides, native charts (values scaled to millions/billions, unit printed), source line with
printed pages on every chart slide; workbook formulas carry cached results (LibreOffice recalculation with
`$SC/lo_profile` gives the same numbers). Tests: `tests/test_exports.py`.

### 2. Search coverage: pick the document, say what is covered

- [x] `sources.sec_documents(query)`: the company's recent filings to choose from — 10-K, 10-Q, 20-F, 40-F, 6-K,
      S-1/F-1/424B, and 8-K with Item 2.02 (results), whose earnings release is exhibit 99.1 (resolved from the
      filing index).
- [x] `sources.esef_documents(query)`: every year filings.xbrl.org has for the issuer, not only the latest.
- [x] `GET /api/documents?kind=sec|esef&query=` and analyse / download a chosen document (`url` restricted to
      sec.gov and filings.xbrl.org).
- [x] UI: each search result gets a document picker (latest annual report preselected).
- [x] Coverage stated in the UI and README: covered (SEC filings, EU ESEF annual reports), not covered (Italian
      half-year reports and non-ESEF documents, unlisted companies' filings at the business register, fund KIDs):
      upload the PDF or paste its URL.
- [x] Tests with simulated EDGAR / filings.xbrl.org responses (`tests/test_sources.py::test_document_picker_sec_and_esef`).
      Live: data.sec.gov (submissions) is reachable from the dev session, www.sec.gov (documents) is not.

Also fixed: dei facts in `ix:hidden` (DocumentType, fiscal period) were dropped with the header; 3-month periods are
no longer called "Q2" from the calendar (Apple's fiscal Q3 ends in June): "3M to Jun 2026", or the issuer's
"Q3 FY2026" from the dei tags.

### 3. More real documents

- [x] 25 more FinanceBench PDFs (`$SC/real2`: 10-K of Coca-Cola, PepsiCo, Nike, Netflix, Walmart, Verizon, Pfizer, CVS,
      Microsoft, Oracle, PayPal, General Mills, Kraft Heinz, MGM, Ulta, Salesforce, FedEx, AES; 10-Q of 3M, Apple,
      American Water, Corning, Lockheed (a release printed from HTML); releases of eBay, Best Buy).
- [x] 12 more ESEF by name (Eni, Leonardo, Campari, Pirelli, Poste, Mediobanca Intl., Unipol, Terna, Nokia, Philips,
      TotalEnergies; SAP has none on filings.xbrl.org).
- [x] Live SEC: the document list (data.sec.gov) for Apple, Amazon, Broadcom. Documents (www.sec.gov) are not
      reachable from the dev session: covered by simulated responses.
- [x] Every document also through the PPTX and XLSX exports (`verify.py`, `esefnames.py` build both).
- Bugs found and fixed (regression tests in `tests/test_layouts.py`):
  - wrong figures: Pfizer net income from an investee's note (the income statement page was not among the pages
    read → statement pages always included), AES/Oracle/PepsiCo years (a dateline naming the years ran into the
    column header), 3M prior-quarter $78M dropped as a note reference, PepsiCo EPS mixed with the share count
    under one "Diluted" label, Lockheed net income from the 6-month cash flow (statement printed mid-page),
    MGM revenue from a segment table (lone off-statement figures dropped), Nike revenue from a segment table
  - missing: Coca-Cola "Net operating revenues", Walmart "Consolidated net income attributable to", Kraft Heinz
    "Net income/(loss)", JPMorgan "Total assets(a)", Pfizer 10-word pretax label, MGM "Benefit (provision)"
  - periods: Microsoft/Nike balance sheet dated without "as of"; quarters named neutrally
  - ESEF: name search ranked "Renishaw" for "eni" and "Credit Suisse International" for "terna" (word match first,
    100 candidates); Eni's unlabelled FX extension concept; an iXBRL report tagging only its name is read as HTML
- Still open (honest): EPS missing when the diluted EPS row is labelled by a section header only (Pfizer, Verizon,
  CVS, Corning, American Water, AES); Pirelli tags EPS 0.496 as 496 (issuer's format); MGM's total revenue line is
  unlabelled; Mediobanca International (no tagged figures, tables not recognised) gives no card without the AI.

### 4. Faster spider (last, only if it does not touch the reading)

- [ ] Shorter pauses and faster walking between figures in `web/app.js` pacing; same figures read and lit, same
      order, same report. Verify with the browser test (`e2e/`) that every figure is still visited.

### 5. Wrap-up

- [ ] README / PLAN updated, tests green, commit and push, answer in Italian.

## How to verify

Scratchpad: `/tmp/claude-0/-home-user-spider-analyst/813b7837-9089-595e-b3bf-d58e614c7198/scratchpad` (`$SC`).

- Tests: `.venv/bin/python -m pytest -q`
- Real documents without AI: `cd $SC && SPIDER_DATA_DIR=$SC/esefcache .venv/bin/python -I verify.py en real esef s1`
  (`real/` FinanceBench PDFs, `esef/` ESEF reports, `s1/` the user's S-1 — expected: S-1 revenue $16.3B +1,300%
  vs H1 2025, 5/5 checks).
- ESEF by name: `cd $SC && SPIDER_DATA_DIR=$SC/esefcache .venv/bin/python -I esefnames.py "air liquide" generali …`
- FinanceBench list: `$SC/fb_list.txt`; blobless clone at `/home/user/patronus-ai/financebench` (outside the repo).
- Network from the dev session: SEC and filings.xbrl.org reachable; company websites and borsaitaliana.it are not.
