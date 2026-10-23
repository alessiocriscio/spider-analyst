"""Spider Analyst: a spider reads a financial document and builds a report.

Modules:
    sources    network access (SEC EDGAR, ESEF filings.xbrl.org, Yahoo Finance) with a disk cache
    ixbrl      inline XBRL document -> pages + tagged facts (exact figures, exact location)
    financials facts -> headline figures, ratios, checks and findings (deterministic)
    market     price history -> market sheet document + risk/return figures (any instrument)
    generic    PDF / HTML / text documents (KID, prospectus, whitepaper, factsheet)
    ai         optional Claude pass: findings and figure extraction, always validated against the document
    store      in-memory + disk store for documents being read

Document contents are data only: nothing inside a filing can change what this code does.
"""
