"""An English annual-report-like PDF (fictional company, made-up numbers) for tests. Needs reportlab."""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

out = Path(__file__).parent / "fixtures" / "annual_en.pdf"
c = canvas.Canvas(str(out), pagesize=A4)


def table(title, rows, y=700):
    c.setFont("Helvetica-Bold", 16); c.drawString(60, 780, title)
    c.setFont("Helvetica", 9); c.drawString(60, 760, "(in millions of U.S. dollars, except per share amounts)")
    c.setFont("Helvetica-Bold", 10); c.drawString(330, 735, "Note"); c.drawRightString(450, 735, "2025"); c.drawRightString(530, 735, "2024")
    c.setFont("Helvetica", 10)
    for label, note, a, b in rows:
        c.drawString(60, y, label)
        if note:
            c.drawString(335, y, note)
        c.drawRightString(450, y, a); c.drawRightString(530, y, b)
        y -= 20
    c.showPage()


c.setFont("Helvetica-Bold", 24); c.drawString(60, 760, "Northwind Instruments Inc."); c.setFont("Helvetica", 14)
c.drawString(60, 730, "Annual Report 2025"); c.drawString(60, 700, "Letter to shareholders: a year of steady growth.")
c.showPage()
table("Consolidated Statements of Operations", [
    ("Net sales", "4", "12,450", "11,200"), ("Cost of sales", "", "(7,100)", "(6,500)"), ("Gross profit", "", "5,350", "4,700"),
    ("Research and development", "", "(1,200)", "(1,050)"), ("Operating income", "", "2,600", "2,150"), ("Interest expense", "", "(150)", "(160)"),
    ("Income before income taxes", "", "2,450", "1,990"), ("Income tax expense", "9", "(500)", "(410)"), ("Net income", "", "1,950", "1,580"),
    ("Diluted earnings per share", "", "4.12", "3.30")])
table("Consolidated Balance Sheets", [
    ("Cash and cash equivalents", "", "3,100", "2,800"), ("Total current assets", "", "7,900", "7,100"), ("Total assets", "", "21,000", "19,500"),
    ("Total current liabilities", "", "4,800", "4,600"), ("Total liabilities", "", "11,500", "11,000"), ("Total shareholders' equity", "", "9,500", "8,500")])
table("Consolidated Statements of Cash Flows", [
    ("Net cash provided by operating activities", "", "2,900", "2,450"), ("Purchases of property, plant and equipment", "", "(700)", "(650)"),
    ("Repurchases of common stock", "", "(800)", "(600)"), ("Dividends paid", "", "(400)", "(380)")])
c.save()
print(out)
