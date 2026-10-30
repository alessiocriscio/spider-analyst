"""A synthetic IPO prospectus laid out like EDGAR's PDF-to-HTML renderings (made-up company and numbers).

One fixed-size <div> per printed page, the printed page number first, statement tables whose header groups
the columns ("Year Ended December 31," over 2024 and 2025, "Six Months Ended June 30," over 2025 and 2026),
a percentage-of-revenue table, footnote marks, dates, a phone number and a ZIP code in the text, all wrapped
in the <DOCUMENT><TYPE>S-1… envelope of an EDGAR submission.
"""

PAGE = '<div style="--x:1;background-color:#FFFFFF;height:792pt;margin:10px auto;overflow:hidden;position:relative;width:612pt">{}</div>'


def _page(label: str, body: str) -> str:
    head = f'<div style="position:absolute;top:9pt"><font style="font-size:8pt">{label}</font></div>' if label else ""
    toc = '<div style="position:absolute;top:20pt"><a href="#toc"><font>Table of Contents</font></a></div>'
    return PAGE.format(head + toc + body)


def _cell(text: str, bold: bool = False) -> str:
    if not text:
        return '<td style="font-size:0"></td>'
    style = "font-weight:bold" if bold else "font-weight:normal"
    if text.startswith("$"):
        inner = f'<font style="left:2pt;position:absolute">$</font><font style="left:40pt;position:absolute">{text[1:]}</font>'
    else:
        inner = text
    return f'<td><div style="position:absolute"><div><font style="{style};white-space:pre">{inner}</font></div></div></td>'


def _row(cells: list[str], spans: dict[int, int] | None = None) -> str:
    out = []
    for i, c in enumerate(cells):
        if spans and i in spans:
            out.append(f'<td colspan="{spans[i]}"><div><font style="font-weight:bold">{c}</font></div></td>')
        else:
            out.append(_cell(c))
    return "<tr>" + "".join(out) + "</tr>"


def _table(group: list[tuple[str, int]], years: list[str], unit: str, rows: list[list[str]]) -> str:
    # columns: label, then value + spacer per period, as Workiva lays them out
    head1 = '<tr><td style="font-size:0"></td>' + "".join(f'<td colspan="{span}"><div><font style="font-weight:bold">{g}</font></div></td>'
                                                          for g, span in group) + "</tr>"
    head2 = "<tr>" + _cell(unit) + "".join(_cell(y, True) + '<td style="font-size:0"></td>' for y in years) + "</tr>"
    body = "".join("<tr>" + _cell(r[0]) + "".join(_cell(v) + '<td style="font-size:0"></td>' for v in r[1:]) + "</tr>" for r in rows)
    return f'<div style="position:absolute;top:120pt"><table style="border-collapse:collapse">{head1}{head2}{body}</table></div>'


def _text(top: int, s: str, bold: bool = False) -> str:
    w = "bold" if bold else "normal"
    return f'<div style="position:absolute;top:{top}pt;width:612pt"><font style="font-weight:{w};white-space:pre">{s}</font></div>'


PERIODS = [("Year Ended December 31,", 4), ("Six Months Ended June 30,", 4)]
YEARS = ["2024", "2025", "2025", "2026"]


def s1() -> str:
    pages = [
        _page("", _text(40, "UNITED STATES SECURITIES AND EXCHANGE COMMISSION", True) + _text(60, "FORM S-1", True) +
              _text(80, "REGISTRATION STATEMENT UNDER THE SECURITIES ACT OF 1933", True) +
              _text(110, "Example AI, PBC") + _text(125, "548 Market Street PMB 90375, San Francisco, California 94104, (650) 555-0100") +
              _text(140, "As filed on October 26, 2026. Approximate date of sale: after June 30, 2026.")),
        _page("1", _text(40, "Prospectus Summary", True) +
              _text(60, "We had more than 1,200 enterprise customers as of June 30, 2026, and revenue grew in every quarter.") +
              _text(75, "Commitments are described in Note 13 and in (Note 14).")),
        _page("2", _text(40, "Summary Consolidated Financial Data", True) + _table(PERIODS, YEARS, "(in millions, except share and per share amounts)", [
            ["Revenue", "$386", "$4,585", "$1,163", "$16,286"],
            ["Total operating expenses", "3,366", "12,645", "3,298", "16,979"],
            ["Operating loss", "(2,980)", "(8,060)", "(2,135)", "(693)"],
            ["Loss before provision for income taxes", "(8,308)", "(41,945)", "(12,962)", "(80,727)"],
            ["Provision for income taxes", "1", "20", "7", "21"],
            ["Net loss(2)", "$(8,309)", "$(41,965)", "$(12,969)", "$(80,748)"],
            ["Net loss per share attributable to common stockholders, basic and diluted", "$(5.43)", "$(23.04)", "$(7.25)", "$(39.88)"],
            ["Weighted-average shares outstanding, basic and diluted", "1,528,994,540", "1,821,084,860", "1,788,730,900", "2,024,972,990"],
        ])),
        _page("3", _text(40, "Results of Operations", True) + _table(PERIODS, YEARS, "(as a percentage of revenue)", [
            ["Revenue", "100", "100", "100", "100"],
            ["Total operating expenses", "872", "276", "284", "104"],
            ["Operating loss", "(772)", "(176)", "(184)", "(4)"],
        ])),
        _page("F-2", _text(40, "Consolidated Balance Sheets", True) + _table(
            [("As of December 31,", 2), ("As of June 30,", 2)], ["2025", "2026"], "(in millions)", [
                ["Cash and cash equivalents", "$17,388", "$112,389"],
                ["Total current assets", "23,746", "137,980"],
                ["Total assets", "$24,661", "$147,358"],
                ["Total current liabilities", "2,817", "7,220"],
                ["Total liabilities", "45,397", "117,467"],
                ["Redeemable convertible preferred stock, $0.00001 par value; 728,289 and 1,040,441 shares authorized", "29,769", "157,510"],
                ["Total stockholders’ deficit", "(50,505)", "(127,619)"],
            ])),
        _page("F-3", _text(40, "Consolidated Statements of Cash Flows", True) + _table(PERIODS, YEARS, "(in millions)", [
            ["Net loss", "$(8,309)", "$(41,965)", "$(12,969)", "$(80,748)"],
            ["Net cash provided by (used in) operating activities", "(5,692)", "(2,637)", "(1,513)", "3,929"],
            ["Purchases of property and equipment", "(15)", "(131)", "(18)", "(482)"],
            ["Net cash used in investing activities", "(22)", "(3,077)", "(49)", "(17,181)"],
            ["Net cash provided by financing activities", "7,248", "19,960", "4,749", "110,774"],
            ["Net increase in cash, cash equivalents, and restricted cash", "1,534", "14,247", "3,188", "97,517"],
        ])),
    ]
    html = ('<html><head><title>Example AI, PBC - S-1</title><script>tracker()</script></head><body>'
            '<div style="background-color:#E4E4E4">' + "".join(pages) + "</div></body></html>")
    return "<DOCUMENT>\n<TYPE>S-1\n<SEQUENCE>1\n<FILENAME>exampleai-s1.htm\n<TEXT>\n" + html + "\n</TEXT>\n</DOCUMENT>\n"
