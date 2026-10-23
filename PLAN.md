# Spider Analyst — piano di lavoro

Ricostruzione (scritta da zero) dello strumento visto nei video TikTok di @buildwithbrock ("Wall Street's newest analyst is a spider"):
un ragno animato "legge" un documento finanziario pagina per pagina, le zampe camminano sulle parole, le cifre lette si
illuminano e finiscono in un report live; alla fine compaiono le osservazioni chiave e una scheda riassuntiva.
Requisito dell'utente: deve funzionare su **qualsiasi strumento finanziario** e girare in locale su macOS.

## Stato

- [x] `analyst/ixbrl.py` — parser inline XBRL: pagine, fatti taggati (valore + elemento esatto `data-f`), titoli (`data-h`), CSS filtrabile. Non ancora testato.
- [ ] `analyst/sources.py` — SEC EDGAR, ESEF (filings.xbrl.org), Yahoo Finance, con cache su disco (`.data/`)
- [ ] `analyst/financials.py` — metriche, rapporti, controlli, osservazioni
- [ ] `analyst/market.py` — scheda di mercato generata (per crypto, indici, valute, materie prime, ETF)
- [ ] `analyst/generic.py` — PDF / HTML / URL caricati (KID, prospetti, whitepaper, factsheet)
- [ ] `analyst/ai.py` — Claude opzionale (osservazioni ed estrazione), sempre validato sul testo della pagina
- [ ] `server.py` — FastAPI
- [ ] `web/` — interfaccia, motore del ragno, report live, finale, modalità video 9:16, registrazione MP4
- [ ] `Avvia Spider Analyst.command` — avvio con doppio clic su Mac (venv, dipendenze, apre il browser)

## Fonti dati (verificate)

| Strumento | Documento letto dal ragno | Fonte |
|---|---|---|
| Azioni USA / emittenti esteri SEC | 10-K, 10-Q, 20-F, 40-F (iXBRL) | `data.sec.gov/submissions/CIK##########.json`, `www.sec.gov/Archives/...`, `www.sec.gov/files/company_tickers.json` |
| Azioni UE/UK | Relazione annuale ESEF (iXBRL, ifrs-full) | `filings.xbrl.org/api/entities?filter=...`, `/api/entities/{LEI}/filings` → `report_url` |
| ETF, fondi, obbligazioni, crypto, qualsiasi PDF | KID, prospetto, whitepaper, factsheet caricato o da URL | upload / URL |
| Crypto, indici, valute, materie prime, ETF | Scheda di mercato generata (grafico, rendimenti annuali/mensili, rischio) | Yahoo `query1.finance.yahoo.com/v8/finance/chart/{sym}`, ricerca `/v1/finance/search` |

- SEC richiede un User-Agent con contatto: configurabile (`SPIDER_SEC_UA` o `~/.spider-analyst/config.json`).
  Non inviare l'email dell'utente senza che lo chieda: il launcher la chiede al primo avvio, default generico.
- Struttura pagine: SEC = figli di `<body>` separati da `<hr style="page-break-after:always">`; ESEF = `div.pageView` (pagine HTML da PDF, ~35 MB, CSS con immagini base64 → filtrare il CSS sulle classi usate dalle pagine mostrate).

## Metriche (concetti us-gaap e ifrs-full con fallback)

Conto economico: ricavi, costo del venduto, margine lordo, R&S, utile operativo, utile ante imposte, imposte, utile netto, EPS diluito, interessi passivi.
Stato patrimoniale: cassa, attivo corrente, totale attivo, passivo corrente, totale passivo (o derivato), patrimonio netto, debito.
Flussi di cassa: flusso operativo, capex, buyback, dividendi pagati, compensi in azioni. Altro: debito in scadenza entro 12 mesi.
Periodo: contesto non dimensionale con fine = `DocumentPeriodEndDate`; corrente vs anno precedente.
Derivati: FCF, margini, crescita YoY, copertura interessi ((ante imposte + interessi)/interessi), debito/attivo, moltiplicatore del capitale, % FCF restituita agli azionisti, current ratio.
Controlli: lordo = ricavi − costo; attivo = passivo + PN; ante imposte − imposte ≈ utile netto; EPS × azioni diluite ≈ utile netto.
Ogni cifra cita la pagina del documento. Occorrenza da evidenziare: quella sulla pagina con più fatti (prospetti contabili).

## Interfaccia

- Documento in iframe same-origin a piena altezza (sandbox senza script per i filing; pdf.js per i PDF), scalato; overlay in coordinate documento.
- Ragno su canvas: corpo nero con bordo rosa, 8 zampe a due segmenti (IK), andatura alternata, piedi agganciati alle parole (`caretRangeFromPoint`), fili rosa verso le cifre lette, riquadri rosa sulle parole toccate, evidenziazione gialla delle etichette di riga, pillole rosa sui titoli.
- Regia: itinerario ordinato per posizione (cifre, titoli, cifre nel testo), durata totale configurabile, camera che segue il ragno.
- Pannello report: "N di M cifre mostrate", tabella della sezione in lettura (anno corrente / precedente), "altre cifre lette dal ragno" con pagina.
- Finale: osservazioni chiave una alla volta, poi scheda (4 riquadri con variazione YoY e pagina, 3 osservazioni, riga "N cifre · N controlli").
- Modalità video 9:16 + registrazione (getDisplayMedia + CropTarget, MediaRecorder; conversione MP4 con ffmpeg se serve).
- Interfaccia in italiano, etichette report IT/EN.

## Claude (opzionale)

SDK `anthropic` (installato 2.1.0), modello `claude-opus-5-5`, `output_config` con `format` json_schema ed `effort`,
`client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`, gestire `stop_reason == "refusal"`.
Chiave da `ANTHROPIC_API_KEY` o `~/.spider-analyst/anthropic_key`; senza chiave tutto funziona in modo deterministico.
I numeri nelle osservazioni generate devono corrispondere a valori calcolati, e le cifre estratte devono comparire testualmente sulla pagina citata, altrimenti si scartano.
