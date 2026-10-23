# Spider Analyst

Un ragno legge un documento finanziario sul Mac: cammina sulle parole, le cifre che legge si illuminano e
finiscono in un report che si compone in diretta. Alla fine mostra le osservazioni chiave e una scheda
riassuntiva in cui ogni numero indica la pagina da cui viene.

È una ricostruzione scritta da zero dell'idea vista nei video di @buildwithbrock. Non contiene il suo codice.

## Avvio

1. Serve Python 3.10 o più recente: `python3 --version`. Se manca, installalo da
   [python.org](https://www.python.org/downloads/macos/) oppure con `brew install python`.
2. Doppio clic su **`Avvia Spider Analyst.command`**. Se macOS lo blocca: tasto destro → Apri → Apri.
   Al primo avvio prepara l'ambiente (`.venv`), installa le dipendenze e chiede un nome e un'email per la SEC
   (puoi lasciare vuoto).
3. Si apre il browser su `http://127.0.0.1:8765`. Per registrare il video usa **Chrome**.

Da terminale: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python server.py`.

## Cosa legge

| Cosa cerchi | Documento che legge il ragno | Fonte |
|---|---|---|
| Azioni USA ed emittenti esteri quotati in USA (MSFT, AAPL, …) | Ultimo 10-K, 20-F o 40-F in iXBRL | SEC EDGAR |
| Società europee (Ferrari, ENI, …) | Relazione annuale ESEF in iXBRL | filings.xbrl.org |
| Crypto, indici, valute, materie prime, ETF, fondi (BTC-USD, ^GSPC, EURUSD=X, GC=F, …) | Scheda di mercato generata: grafico, rendimenti annuali e mensili, volatilità, drawdown | Yahoo Finance |
| Qualsiasi altro documento: KID, prospetto, factsheet, whitepaper, bilancio in PDF | Il file che carichi o l'URL che incolli | Tuo file / URL |

Nei bilanci iXBRL ogni cifra è un tag XBRL: valore e posizione esatta sono certi, nessuna lettura “a occhio”.
Su PDF e HTML senza tag le cifre sono trovate con regole euristiche (o scelte da Claude, vedi sotto) e
restano sempre cifre presenti nel testo della pagina.

## Report

- **Scheda (bilanci)**: ricavi, utile netto, EPS diluito, free cash flow (flusso operativo − capex), ognuno con
  variazione annua e pagina.
- **Controlli aritmetici**: margine lordo = ricavi − costo del venduto; attivo = passivo + patrimonio netto;
  ante imposte − imposte ≈ utile netto; EPS × azioni diluite ≈ utile netto.
- **Osservazioni**: crescita, margini, conversione in cassa, ritorno agli azionisti, copertura interessi,
  debito in scadenza contro cassa, liquidità, leva. Calcoli deterministici sulle cifre del documento.

## Claude (facoltativo)

Con una chiave API Anthropic (Impostazioni, oppure `ANTHROPIC_API_KEY`) puoi spuntare
“Osservazioni scritte da Claude” (modello `claude-opus-5-5`). Claude riceve solo le cifre già lette, ognuna con
un identificativo; ogni osservazione che contiene un numero non presente tra le cifre citate viene scartata.
Sui PDF sceglie le cifre importanti tra quelle trovate sulle pagine. Senza chiave tutto il resto funziona.
La chiave resta in `~/.spider-analyst/anthropic_key` (permessi 600).

## Video

- **Formato video 9:16** impagina documento e report in verticale.
- **Registra video** (Chrome): scegli “questa scheda”; la registrazione riparte dall'inizio, si ferma da sola
  dopo la scheda finale e scarica un MP4 (con `ffmpeg`, `brew install ffmpeg`) o un WebM.

## Dati e privacy

Il server ascolta solo su `127.0.0.1`. Documenti e risposte vengono messi in cache in `.data/`.
L'identificazione per la SEC è in `~/.spider-analyst/config.json`; il default è generico, nessuna email viene
inviata se non la inserisci tu.

## Limiti noti

- Le cifre di bilancio dipendono dai tag dell'emittente: concetti rari o personalizzati possono mancare
  (la scheda mostra “—”).
- Il free cash flow usa il capex in immobilizzazioni materiali; alcune società includono anche le immateriali.
- Yahoo Finance non ha un'API ufficiale: se cambia formato la scheda di mercato smette di funzionare.
- La registrazione con ritaglio dell'area è solo su Chrome; su Safari registra l'intera scheda.

## Test

```
.venv/bin/pip install pytest reportlab
.venv/bin/python -m pytest -q
```
I test usano documenti sintetici (società e numeri inventati) e non richiedono rete.
