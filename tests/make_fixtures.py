"""Synthetic inline XBRL filings for tests (fictional companies, made-up numbers).

    sec_10k.htm   SEC style: us-gaap, pages split by <hr style="page-break-after:always">
    esef.xhtml    ESEF style: ifrs-full, pages are <div class="pageView">, comma decimals
"""
from pathlib import Path

HERE = Path(__file__).parent / "fixtures"

NS = ('xmlns="http://www.w3.org/1999/xhtml" xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" '
      'xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
      'xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:dei="http://xbrl.sec.gov/dei/2024" '
      'xmlns:us-gaap="http://fasb.org/us-gaap/2024" xmlns:ifrs-full="https://xbrl.ifrs.org/taxonomy/2023-03-23/ifrs-full" '
      'xmlns:ixt="http://www.xbrl.org/inlineXBRL/transformation/2020-02-12" xmlns:link="http://www.xbrl.org/2003/linkbase" '
      'xmlns:xlink="http://www.w3.org/1999/xlink"')


def ctx(cid, start=None, end=None, instant=None, dim=False):
    period = f"<xbrli:instant>{instant}</xbrli:instant>" if instant else f"<xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>"
    seg = '<xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">x:CloudMember</xbrldi:explicitMember></xbrli:segment>' if dim else ""
    return f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier>{seg}</xbrli:entity><xbrli:period>{period}</xbrli:period></xbrli:context>'


def nf(name, c, v, unit="usd", dec="-6", scale="6", fmt="ixt:num-dot-decimal", sign=""):
    s = f' sign="-"' if sign else ""
    return f'<ix:nonFraction name="{name}" contextRef="{c}" unitRef="{unit}" decimals="{dec}" scale="{scale}" format="{fmt}"{s}>{v}</ix:nonFraction>'


def row(label, cur, prev):
    return f'<tr><td><span>{label}</span></td><td>$</td><td style="text-align:right">{cur}</td><td>$</td><td style="text-align:right">{prev}</td></tr>'


def sec():
    g = "us-gaap:"
    rows_is = [
        row("Revenue", nf(g + "Revenues", "FY25", "120,000"), nf(g + "Revenues", "FY24", "100,000")),
        row("Cost of revenue", nf(g + "CostOfRevenue", "FY25", "40,000"), nf(g + "CostOfRevenue", "FY24", "35,000")),
        row("Gross margin", nf(g + "GrossProfit", "FY25", "80,000"), nf(g + "GrossProfit", "FY24", "65,000")),
        row("Research and development", nf(g + "ResearchAndDevelopmentExpense", "FY25", "20,000"), nf(g + "ResearchAndDevelopmentExpense", "FY24", "18,000")),
        row("Operating income", nf(g + "OperatingIncomeLoss", "FY25", "50,000"), nf(g + "OperatingIncomeLoss", "FY24", "38,000")),
        row("Interest expense", nf(g + "InterestExpense", "FY25", "2,000"), nf(g + "InterestExpense", "FY24", "2,100")),
        row("Income before income taxes", nf(g + "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "FY25", "48,000"), nf(g + "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "FY24", "36,000")),
        row("Provision for income taxes", nf(g + "IncomeTaxExpenseBenefit", "FY25", "8,000"), nf(g + "IncomeTaxExpenseBenefit", "FY24", "6,000")),
        row("Net income", nf(g + "NetIncomeLoss", "FY25", "40,000"), nf(g + "NetIncomeLoss", "FY24", "30,000")),
        row("Diluted", nf(g + "EarningsPerShareDiluted", "FY25", "5.00", unit="usdps", dec="2", scale="0"), nf(g + "EarningsPerShareDiluted", "FY24", "3.75", unit="usdps", dec="2", scale="0")),
        row("Diluted shares", nf(g + "WeightedAverageNumberOfDilutedSharesOutstanding", "FY25", "8,000", unit="shares"), nf(g + "WeightedAverageNumberOfDilutedSharesOutstanding", "FY24", "8,000", unit="shares")),
    ]
    rows_bs = [
        row("Cash and cash equivalents", nf(g + "CashAndCashEquivalentsAtCarryingValue", "I25", "30,000"), nf(g + "CashAndCashEquivalentsAtCarryingValue", "I24", "25,000")),
        row("Total current assets", nf(g + "AssetsCurrent", "I25", "90,000"), nf(g + "AssetsCurrent", "I24", "80,000")),
        row("Total assets", nf(g + "Assets", "I25", "300,000"), nf(g + "Assets", "I24", "260,000")),
        row("Current portion of long-term debt", nf(g + "LongTermDebtCurrent", "I25", "5,000"), nf(g + "LongTermDebtCurrent", "I24", "3,000")),
        row("Total current liabilities", nf(g + "LiabilitiesCurrent", "I25", "60,000"), nf(g + "LiabilitiesCurrent", "I24", "55,000")),
        row("Long-term debt", nf(g + "LongTermDebtNoncurrent", "I25", "40,000"), nf(g + "LongTermDebtNoncurrent", "I24", "45,000")),
        row("Total liabilities", nf(g + "Liabilities", "I25", "140,000"), nf(g + "Liabilities", "I24", "130,000")),
        row("Total stockholders’ equity", nf(g + "StockholdersEquity", "I25", "160,000"), nf(g + "StockholdersEquity", "I24", "130,000")),
        row("Total liabilities and stockholders’ equity", nf(g + "LiabilitiesAndStockholdersEquity", "I25", "300,000"), nf(g + "LiabilitiesAndStockholdersEquity", "I24", "260,000")),
    ]
    rows_cf = [
        row("Net cash from operations", nf(g + "NetCashProvidedByUsedInOperatingActivities", "FY25", "60,000"), nf(g + "NetCashProvidedByUsedInOperatingActivities", "FY24", "50,000")),
        row("Stock-based compensation expense", nf(g + "ShareBasedCompensation", "FY25", "6,000"), nf(g + "ShareBasedCompensation", "FY24", "5,000")),
        row("Additions to property and equipment", "(" + nf(g + "PaymentsToAcquirePropertyPlantAndEquipment", "FY25", "15,000") + ")", "(" + nf(g + "PaymentsToAcquirePropertyPlantAndEquipment", "FY24", "12,000") + ")"),
        row("Common stock repurchased", "(" + nf(g + "PaymentsForRepurchaseOfCommonStock", "FY25", "10,000") + ")", "(" + nf(g + "PaymentsForRepurchaseOfCommonStock", "FY24", "8,000") + ")"),
        row("Common stock cash dividends paid", "(" + nf(g + "PaymentsOfDividends", "FY25", "12,000") + ")", "(" + nf(g + "PaymentsOfDividends", "FY24", "11,000") + ")"),
    ]
    seg = f'<p>Cloud revenue was {nf(g + "Revenues", "FY25cloud", "70,000")} million.</p>'
    hr = '<hr style="page-break-after:always"/>'
    header = (
        '<div style="display:none"><ix:header><ix:hidden>'
        '<ix:nonNumeric name="dei:DocumentType" contextRef="FY25">10-K</ix:nonNumeric>'
        '</ix:hidden><ix:resources>'
        + ctx("FY25", "2024-07-01", "2025-06-30") + ctx("FY24", "2023-07-01", "2024-06-30")
        + ctx("I25", instant="2025-06-30") + ctx("I24", instant="2024-06-30")
        + ctx("FY25cloud", "2024-07-01", "2025-06-30", dim=True)
        + '<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
        + '<xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>'
        + '<xbrli:unit id="usdps"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>'
        + '</ix:resources></ix:header></div>'
    )
    table = lambda rows: '<table><tr><td></td><td colspan="2">2025</td><td colspan="2">2024</td></tr>' + "".join(rows) + "</table>"
    body = (
        header
        + '<div><p style="font-weight:bold">UNITED STATES SECURITIES AND EXCHANGE COMMISSION</p>'
        + '<p>FORM 10-K for the fiscal year ended <ix:nonNumeric name="dei:DocumentPeriodEndDate" contextRef="FY25">June 30, 2025</ix:nonNumeric></p>'
        + '<p><ix:nonNumeric name="dei:EntityRegistrantName" contextRef="FY25">EXAMPLE CORP</ix:nonNumeric> '
        + '(<ix:nonNumeric name="dei:TradingSymbol" contextRef="FY25">EXMP</ix:nonNumeric>)</p></div>' + hr
        + '<div><p style="font-weight:bold">Management’s Discussion and Analysis</p>' + seg
        + '<script>alert(1)</script><img src="logo.jpg" onerror="alert(2)"/><a href="javascript:x()">link</a></div>' + hr
        + '<div><p style="font-weight:bold">INCOME STATEMENTS</p>' + table(rows_is) + "</div>" + hr
        + '<div><p style="font-weight:bold">BALANCE SHEETS</p>' + table(rows_bs) + "</div>" + hr
        + '<div><p style="font-weight:bold">CASH FLOWS STATEMENTS</p>' + table(rows_cf) + "</div>"
    )
    return f'<?xml version="1.0" encoding="utf-8"?><html {NS}><head><title>10-K</title><style>.x{{color:red}} .unused{{color:blue}}</style></head><body>{body}</body></html>'


def esef():
    g = "ifrs-full:"
    fmt = "ixt:num-comma-decimal"
    e = lambda n, c, v, **k: nf(n, c, v, unit="eur", fmt=fmt, dec="-3", scale="3", **k)
    page = lambda inner: f'<div class="pageView" style="width:800px;height:1100px;position:relative">{inner}</div>'
    tab = lambda rows: "<table>" + "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in rows) + "</table>"
    p1 = '<p style="font-weight:bold">Annual Report 2025</p><p><ix:nonNumeric name="ifrs-full:NameOfReportingEntityOrOtherMeansOfIdentification" contextRef="Y25">Esempio Motori N.V.</ix:nonNumeric></p>'
    p2 = '<p style="font-weight:bold">Consolidated income statement</p>' + tab([
        ("Net revenues", e(g + "Revenue", "Y25", "6.677.000"), e(g + "Revenue", "Y24", "5.970.000")),
        ("Cost of revenues", e(g + "CostOfSales", "Y25", "3.250.000"), e(g + "CostOfSales", "Y24", "3.000.000")),
        ("EBIT", e(g + "ProfitLossFromOperatingActivities", "Y25", "1.900.000"), e(g + "ProfitLossFromOperatingActivities", "Y24", "1.600.000")),
        ("Net financial expenses", e(g + "FinanceCosts", "Y25", "50.000"), e(g + "FinanceCosts", "Y24", "40.000")),
        ("Profit before taxes", e(g + "ProfitLossBeforeTax", "Y25", "1.850.000"), e(g + "ProfitLossBeforeTax", "Y24", "1.560.000")),
        ("Income tax expense", e(g + "IncomeTaxExpenseContinuingOperations", "Y25", "350.000"), e(g + "IncomeTaxExpenseContinuingOperations", "Y24", "300.000")),
        ("Net profit", e(g + "ProfitLoss", "Y25", "1.500.000"), e(g + "ProfitLoss", "Y24", "1.260.000")),
        ("Net profit attributable to owners of the parent", e(g + "ProfitLossAttributableToOwnersOfParent", "Y25", "1.490.000"), e(g + "ProfitLossAttributableToOwnersOfParent", "Y24", "1.250.000")),
        ("Diluted earnings per share (in €)", nf(g + "DilutedEarningsLossPerShare", "Y25", "8,30", unit="eurps", dec="2", scale="0", fmt=fmt), nf(g + "DilutedEarningsLossPerShare", "Y24", "6,90", unit="eurps", dec="2", scale="0", fmt=fmt)),
    ])
    p3 = '<p style="font-weight:bold">Consolidated statement of financial position</p>' + tab([
        ("Cash and cash equivalents", e(g + "CashAndCashEquivalents", "I25", "1.500.000"), e(g + "CashAndCashEquivalents", "I24", "1.400.000")),
        ("Total assets", e(g + "Assets", "I25", "10.000.000"), e(g + "Assets", "I24", "9.000.000")),
        ("Total equity", e(g + "Equity", "I25", "3.800.000"), e(g + "Equity", "I24", "3.400.000")),
        ("Total liabilities", e(g + "Liabilities", "I25", "6.200.000"), e(g + "Liabilities", "I24", "5.600.000")),
    ])
    p4 = '<p style="font-weight:bold">Consolidated statement of cash flows</p>' + tab([
        ("Cash flows from operating activities", e(g + "CashFlowsFromUsedInOperatingActivities", "Y25", "2.300.000"), e(g + "CashFlowsFromUsedInOperatingActivities", "Y24", "2.000.000")),
        ("Investments in property, plant and equipment", "(" + e(g + "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "Y25", "900.000") + ")", "(" + e(g + "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "Y24", "800.000") + ")"),
        ("Dividends paid", "(" + e(g + "DividendsPaidClassifiedAsFinancingActivities", "Y25", "550.000") + ")", "(" + e(g + "DividendsPaidClassifiedAsFinancingActivities", "Y24", "450.000") + ")"),
    ])
    header = (
        '<div style="display:none"><ix:header><ix:resources>'
        + ctx("Y25", "2025-01-01", "2025-12-31") + ctx("Y24", "2024-01-01", "2024-12-31")
        + ctx("I25", instant="2025-12-31") + ctx("I24", instant="2024-12-31")
        + '<xbrli:unit id="eur"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>'
        + '<xbrli:unit id="eurps"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>'
        + '</ix:resources></ix:header></div>'
    )
    body = header + page(p1) + page(p2) + page(p3) + page(p4)
    return f'<?xml version="1.0" encoding="utf-8"?><html {NS}><head><title>ESEF</title></head><body>{body}</body></html>'


if __name__ == "__main__":
    HERE.mkdir(exist_ok=True)
    (HERE / "sec_10k.htm").write_text(sec(), encoding="utf-8")
    (HERE / "esef.xhtml").write_text(esef(), encoding="utf-8")
    print("ok")
