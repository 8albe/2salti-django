# Roadmap e Gap Progetto 2salti

Questo documento elenca onestamente ciò che è ancora in stato di bozza, parziale o mancante nel progetto 2salti dopo la Fase 5.

## 🤖 AI Stats Engine (Linguaggio Naturale)
- **Interfaccia Query**: Manca l'implementazione del motore che trasforma domande in linguaggio naturale ("Quanti gol ha fatto Rossi nelle ultime 3 partite?") in query SQL o redirect a pagine specifiche.
- **Logica Hybrid**: Integrazione del fallback tra risposte dirette AI e redirect a pagine di statistiche esistenti.

## 🎨 UX/UI Avanzata
- **Dashboard Post-Login**: La separazione tra area pubblica e "Mio Spazio" (area autenticata) è definita a livello di route ma necessita di un design UI più ricco e differenziato per ruolo.
- **Review Side-by-Side**: La pagina di validazione admin deve essere migliorata visivamente per mostrare l'immagine originale del referto accanto ai dati estratti per un confronto immediato.

## 🔍 Data Integrity & Matching
- **Fuzzy Matching**: Sistema di riconciliazione anagrafica per gestire errori di battitura o varianti dei nomi (es. "Team A" vs "ASD Team A") eliminando la creazione di duplicati sporchi.
- **Deduplica Atleti**: Logica automatizzata per unire profili quando l'OCR estrae lo stesso giocatore con leggere varianti nel nome.

## 🔌 Integrazioni Reali
- **SPID/CIE/SARC**: Sostituzione della logica di login mock con provider di identità digitale reali.
- **Stripe Production**: Transizione dal sistema di pagamento simulato all'integrazione con gateway reali e gestione fatturazione.
- **WhatsApp/Email Ingestion**: Collegamento asincrono con i webhook reali di Twilio/SendGrid per l'acquisizione automatica.

## 📈 Operations & Monitoraggio
- **Benchmark su Larga Scala**: Test prestazionali e di accuratezza su volumi reali (centinaia di referti caricati simultaneamente).
- **Error Monitoring**: Integrazione di strumenti di monitoraggio errori in produzione (es. Sentry) specifici per la pipeline OCR.
- **Dashboard KPI Business**: Visualizzazione di statistiche sulla crescita (numero iscritti, match processati, tempo medio di review).
