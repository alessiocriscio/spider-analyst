# Spider Analyst

Un ragno legge un documento finanziario sul Mac: cammina sulle parole, le cifre che legge si illuminano e
finiscono in un report che si compone in diretta. Alla fine mostra le osservazioni chiave e una scheda
riassuntiva in cui ogni numero indica la pagina da cui viene.

È una ricostruzione scritta da zero dell'idea vista nei video di @buildwithbrock. Non contiene il suo codice.

## Avvio

1. Serve Python 3.10 o più recente: `python3 --version`. Se manca, installalo da
   [python.org](https://www.python.org/downloads/macos/) oppure con `brew install python`.
2. Avvia dal Terminale (funziona sempre, anche se macOS blocca il doppio clic):
   apri **Terminale**, scrivi `bash ` (con lo spazio), trascina nella finestra il file
   **`Avvia Spider Analyst.command`** e premi Invio.
   In alternativa: doppio clic sul file; se macOS dice che non può verificarlo, vai in
   **Impostazioni di Sistema → Privacy e sicurezza**, in fondo clicca **Apri comunque**, poi riprova.
   Al primo avvio prepara l'ambiente (`.venv`), installa le dipendenze e chiede un nome e un'email per la SEC
   (puoi lasciare vuoto).
3. Si apre il browser su `http://127.0.0.1:8765`.

Da terminale: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python server.py`.

## Cosa legge

| Cosa cerchi | Documento che legge il ragno | Fonte |
|---|---|---|
| Azioni USA ed emittenti esteri quotati in USA (MSFT, AAPL, …) | Ultimo 10-K, 20-F o 40-F in iXBRL | SEC EDGAR |
| Società europee (Ferrari, ENI, …) | Relazione annuale ESEF in iXBRL | filings.xbrl.org |
| Crypto, indici, valute, materie prime, ETF, fondi (BTC-USD, ^GSPC, EURUSD=X, GC=F, …) | Scheda di mercato generata: grafico, rendimenti annuali e mensili, volatilità, drawdown | Yahoo Finance |
| Qualsiasi altro documento, in italiano o in inglese: bilancio o annual report in PDF/HTML, KID, prospetto, factsheet, whitepaper | Il file che carichi (riquadro “Carica un documento”) o l'URL che incolli | Tuo file / URL |

Nei bilanci iXBRL ogni cifra è un tag XBRL: valore e posizione esatta sono certi, nessuna lettura “a occhio”.
Su PDF e HTML senza tag le cifre sono quelle scritte sulla pagina. Nei bilanci (in inglese o in italiano) il ragno
riconosce le voci dalle etichette di riga — Revenue / Ricavi, Net income / Utile netto, Diluted EPS, Net cash
provided by operating activities, Purchases of property, plant and equipment… — legge le colonne anno corrente
e precedente e la scala (“in millions”, “in migliaia di euro”), e calcola scheda, controlli e osservazioni come
per i bilanci XBRL. Per altri documenti (KID, prospetti) elenca le cifre principali, o le sceglie Claude.

## Lingua e report scaricabile

- **Lingua del report**: Italiano o English, nella pagina iniziale o in alto durante la lettura (cambiandola il report
  viene rigenerato: osservazioni, controlli, etichette, formati dei numeri — $120B invece di $120 mld). Le etichette
  copiate da un documento non strutturato (es. un KID in italiano) restano quelle del documento.
- **Scarica report**: salva un file HTML autonomo con scheda, osservazioni, controlli e tutte le cifre lette con la
  pagina; per un PDF aprilo e usa File → Stampa → Salva come PDF.

## Il ragno

Corpo nero con bordo blu e testa ciano, otto zampe ciano a tre segmenti con giunture e piedi rosa che si posano sulle
parole (due gruppi alterni, mai più di quattro zampe sollevate), filo di seta alle spalle, raggi rosa e ciano che
“pingano” parole e numeri davanti a lui, evidenziazioni al neon (contorni, riempimenti, parole ingrandite, strisce).

## Velocità

Automatica: il ragno legge sempre **tutte** le cifre delle pagine che apre e regola il ritmo sul loro numero
(circa 20 secondi per un documento corto, fino a circa 2 minuti per uno lungo). Il contatore “N di M cifre lette”
conta le cifre di quelle pagine; sotto è indicato quali pagine del documento sono state lette.

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

## Dati e privacy

Il server ascolta solo su `127.0.0.1`. Documenti e risposte vengono messi in cache in `.data/`.
L'identificazione per la SEC è in `~/.spider-analyst/config.json`; il default è generico, nessuna email viene
inviata se non la inserisci tu.

## Limiti noti

- Le cifre di bilancio dipendono dai tag dell'emittente: concetti rari o personalizzati possono mancare
  (la scheda mostra “—”).
- Il free cash flow usa il capex in immobilizzazioni materiali; alcune società includono anche le immateriali.
- Yahoo Finance non ha un'API ufficiale e a volte limita le richieste (errore 429): l'app riprova con un cookie di
  sessione e sull'altro server; se ancora non risponde, scrivi direttamente il simbolo (es. BTC-USD) e riprova più tardi.

## Test

```
.venv/bin/pip install pytest reportlab
.venv/bin/python -m pytest -q
```
I test usano documenti sintetici (società e numeri inventati) e non richiedono rete.
