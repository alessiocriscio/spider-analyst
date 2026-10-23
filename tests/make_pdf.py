"""A small KID-like PDF (fictional fund, made-up numbers) for tests. Needs reportlab (test-only)."""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

out = Path(__file__).parent / "fixtures" / "kid.pdf"
c = canvas.Canvas(str(out), pagesize=A4)
c.setFont("Helvetica-Bold", 20); c.drawString(60, 780, "Documento contenente le informazioni chiave")
c.setFont("Helvetica", 11)
lines = ["Prodotto: Fondo Esempio Azionario Globale, classe A", "Indicatore sintetico di rischio 4 su 7",
         "Spese correnti 1,45%", "Commissioni di ingresso 3,00%", "Periodo di detenzione raccomandato 5 anni",
         "Scenario sfavorevole: rendimento medio annuo -8,20%", "Scenario favorevole: rendimento medio annuo 12,35%",
         "Patrimonio del fondo EUR 1.234.567.890"]
y = 740
for t in lines:
    c.drawString(60, y, t); y -= 22
c.showPage()
c.setFont("Helvetica-Bold", 18); c.drawString(60, 780, "Quali sono i costi?")
c.setFont("Helvetica", 11)
c.drawString(60, 740, "Costi totali 545 EUR"); c.drawString(60, 718, "Incidenza annuale dei costi 2,10%")
c.save()
print(out)
