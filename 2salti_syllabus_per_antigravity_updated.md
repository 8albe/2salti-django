*Versione strutturata per Antigravity: stato progetto, aree funzionali, capitoli operativi, task, gap e ordine di esecuzione*

> [!IMPORTANT]
> **CANONICAL DATA:** Questo file è la Single Source of Truth ufficiale per lo stato dello sviluppo al 13 Aprile 2026.

### Come usare questo documento

Questo file non e un semplice elenco di idee. E una cartella operativa del progetto 2salti, scritta per aiutare Antigravity a leggere il repository, confrontarlo con la visione del prodotto e restituire una mappa reale di cio che e stato fatto, di cio che manca e di cio che e fragile.

Il documento va usato in questo modo:

- come struttura di audit del repository
- come checklist di verifica tecnica e funzionale
- come base per decidere il prossimo blocco di implementazione
- come riferimento unico per evitare autoinganni sul reale stato del progetto

> Regola guida: il documento orienta il lavoro, ma la fonte finale di verita resta il codice reale, il database, le migrazioni, i test e il comportamento verificato dell'app.

### Indice operativo

## 0. Stato sintetico del progetto

## 1. Fondazioni di piattaforma

## 2. Ingestion dei referti

## 3. OCR ed estrazione AI

## 4. Validazione e normalizzazione dati

## 5. Review admin e validazione umana

## 6. Manual statistics entry

## 7. Publishing e aggiornamento dati derivati

## 8. Database e modello dominio

## 9. API applicative

## 10. Frontend admin

## 11. Frontend pubblico e superfici autenticate

## 12. Account, onboarding e claim profilo

## 13. Sicurezza, permessi e audit

## 14. Qualita, test e osservabilita

## 15. Documentazione operativa

## 16. Priorita consigliata di esecuzione

---

## 0. Stato sintetico del progetto

### Visione prodotto

2salti è una piattaforma affidabile multi-sport che:
- Non è vincolata alla sola pallanuoto: architettura, naming, navigazione e logica di calcolo (punti, periodi, eventi) sono ora multi-sport per design. [Baseline Phase 2 - March 2026]
- Riceve referti ufficiali automaticamente (via email o WhatsApp). L'upload manuale rimane come fallback solo per gli amministratori. [Baseline Phase 3 - April 2026]
- Include un'interfaccia di interrogazione AI (AI Query Interface) per l'accesso ai dati in linguaggio naturale.
- Valida e normalizza i dati.
- Permette review amministrativa.
- pubblica risultati e statistiche
- aggiorna profili di atleti, tecnici, arbitri, squadre e altri ruoli sportivi compatibili con i diversi sport

### Stato attuale consolidato emerso finora

#### Base presente o gia avviata

- architettura Django con app principali attive
- modelli base per sport, squadre, partite, eventi partita e profili ruolo
- workflow manuale MatchReport gia operativo in forma base
- upload referto e coda di validazione per staff/admin
- pagina di review manuale dedicata
- reviewer identity e note interne
- RBAC base per queue e review
- schema OCR nativo con validazione strutturale del JSON
- gating standings legato allo stato corretto di pubblicazione
- base di manual stats entry gia avviata
- base di goal attribution manuale gia avviata
- test di integrita statistica gia introdotti
- homepage e pagine pubbliche base gia presenti
- bootstrap sport e una parte della pulizia migrazioni gia fatti


### Chiarimenti di prodotto da considerare vincolanti

- La pallanuoto e il primo sport di lancio operativo, non il perimetro finale del prodotto. Ogni scelta di naming, dati, UI e navigazione va valutata anche in chiave multi-sport.
- L'acquisizione del dato sportivo è automatizzata e supporta ora tre ingressi principali: email/WhatsApp (OCR), referto digitale compilato nell'app, e upload manuale (solo per admin). [Baseline Phase 3 - April 2026]
- Il sito distingue con chiarezza esperienza pubblica e esperienza autenticata: senza login l'utente vede classifiche, risultati, pagine pubbliche e statistiche generali; dopo login vede anche dashboard personale e workflow autorizzati (Digital Report).

#### In parte fatto ma da consolidare [PARZIALE]

- manual stats entry oltre al risultato finale
- quarter scores e box score
- ✅ goal attribution ai giocatori con refresh statistiche coerente [FATTO]
- ✅ publishing service strutturato e transazionale [FATTO]
- ✅ public profiles e pagine statistiche base (atleta/team) [FATTO]
- OCR reale configurato ma attualmente in pausa [PAUSED]
- dataset referti reali ancora ridotto
- ✅ claim profilo, onboarding e pagamento [FATTO]


#### Non ancora chiuso [ASSENTE]

- ✅ OCR production-grade con confidence ed evidence [FATTO]
- ✅ validazione forte contro anagrafiche esistenti (Fuzzy Matching) [FATTO]
- ✅ review admin completa stile originale vs estratto vs corretto [FATTO]
- ✅ persistenza completa dei dati evento partita [FATTO]
- ✅ profili pubblici davvero alimentati dai dati [FATTO]
- ✅ dashboard operativa completa (Admin Cockpit) [FATTO]
- ✅ API v1 complete per mobile e web pubblico [FATTO]
- ✅ workflow robusto di publish e idempotenza [FATTO]
- ✅ AI Stats Engine (Linguaggio Naturale) [FATTO]
- ✅ Monitoring e Error Tracking (Sentry) [FATTO]

- disciplina completa dev/staging/prod

---

## 1. Fondazioni di piattaforma

### 1.1 Architettura progetto

Scopo: mantenere una base tecnica pulita, estendibile e coerente con un MVP reale.

#### Task completati o probabili
- struttura app Django principale impostata
- modelli base esistenti
- prime migrazioni riallineate
- bootstrap sport consolidato

#### Task mancanti
- mappare file-by-file lo stato del repository
- identificare componenti legacy, duplicati o fragili
- definire una single source of truth per OCR, review e publishing
- documentare dipendenze reali e servizi non usati
- uniformare naming e convenzioni 2salti in chiave multi-sport, evitando assunzioni hardcoded sulla sola pallanuoto

#### Task operativi [FATTO]
- elencare tutte le app attive e il loro ruolo reale
- elencare views, forms, models, services e template collegati al workflow referti
- segnare file duplicati, morti o sospetti
- identificare gli entry point reali del flusso upload -> review -> publish
- produrre mappa modulo -> responsabilita
- separare chiaramente UI logic, domain logic e persistence logic
- definire convenzioni per status, services, test e costanti condivise

### 1.2 Ambienti e workflow di sviluppo

Scopo: lavorare in modo disciplinato tra sviluppo, staging e produzione.

#### Task completati o probabili
- distinzione concettuale dev/staging/prod gia definita
- uso di Hetzner e GitHub gia impostato come flusso raccomandato

#### Task mancanti
- verificare che le modifiche non banali avvengano solo su dev/staging
- definire checklist deploy standard
- definire backup e restore rapidi di DB e media
- scrivere runbook di emergenza
- verificare static, media, env vars e segreti per ambiente

#### Task operativi
- verificare branch strategy reale
- definire naming branch per feature, fix e hotfix
- definire checklist pre-merge e pre-deploy
- verificare settings dev/staging/prod
- verificare variabili ambiente presenti e mancanti
- verificare media, static e connessioni DB per ambiente
- preparare backup DB automatico
- preparare backup file upload/media
- testare una procedura di restore

---

## 2. Ingestion dei referti

### 2.1 Automated Data Ingestion

Scopo: Ricevere referti in modo automatico, senza attrito per l'utente finale.

#### DATA INGESTION FLOW
Referti ingestion is fully automated:
1. **Referto received** via email or WhatsApp.
2. **File stored** automatically in the ingestion area.
3. **OCR pipeline triggered** on the new file.
4. **Extraction -> Validation -> Review -> Publish**.

GOAL: Zero friction for end users.

#### Task completati [FATTO]
- ✅ Modello MatchReport con hash/checksum file
- ✅ Naming strutturato e storage sicuro
- ✅ Deduplica e blocco upload duplicati
- ✅ Coda operativa di validazione disponibile
- ✅ Automazione ricezione Email/WhatsApp
- ✅ Upload manuale limitato ad Admin (fallback)


#### Task operativi
- verificare formati file accettati
- verificare limiti dimensione file
- verificare messaggi errore lato UI
- verificare salvataggio file su storage corretto
- verificare associazione uploader, timestamp e stato iniziale
- salvare nome file originale e nome file interno
- salvare tipo MIME, peso e numero pagine quando disponibile
- definire casella email dedicata per ingest
- estrarre allegati validi
- scartare allegati non compatibili
- creare MatchReport automatico dagli allegati validi
- loggare email processata, mittente ed errori


### 2.2 Referto digitale compilato in-app [✅ Phase 1 Completa]

Scopo: permettere ad arbitri e personale di giuria di creare direttamente un referto digitale strutturato, riducendo passaggi manuali e dipendenza dall'OCR.

#### Task completati [Phase 1]
- ✅ Definita architettura source-agnostic per MatchReport
- ✅ Implementato entry point 'Referto Digitale' (ingresso alternativo equivalente all'OCR)
- ✅ Allineato contratto dati JSON tra OCR e Digital Entry
- ✅ Supportata review manuale identica per entrambi i canali
- ✅ Verifica automatica publish-readiness via schema

### 2.2 Stati del workflow

Scopo: avere una macchina a stati unica, coerente e verificabile.

#### Task completati o probabili
- macchina a stati di base definita
- gating pubblicazione/standings gia avviato

#### Task mancanti
- verificare stato unico e coerente tra modello, admin, views e template
- allineare eventuale needs_review con gli altri stati reali nel codice

#### Task completati [FATTO]
- ✅ aggiungere audit trail completo dei cambi stato
- ✅ tracciare chi ha fatto cosa e quando
- ✅ registrare old_status -> new_status con motivazione
- ✅ registrare utente, timestamp e motivo del cambio
- ✅ mostrare storico nella UI admin (Audit Trail Completo nella Review)

---

## 3. OCR ed estrazione AI

### 3.1 Contratto dati OCR

Scopo: avere un JSON rigido, spiegabile e versionabile.

#### Task completati o probabili
- OCRSchemaValidator creato
- root structure obbligatoria definita
- validazione su review/admin inserita
- mock payload e test allineati al contratto base

#### Task completati [FATTO - Aprile 2026]
- ✅ Schema version (`schema_version: "2.0"`) in metadata
- ✅ Esteso `match_info` con `venue`, `round`, `group` (nullable, opzionali)
- ✅ Nuova sezione root `officials` con arbitri (`name`, `role`), segnapunti e `confidence`
- ✅ `teams.home/away.coach` (nullable, opzionale)
- ✅ `teams.home/away.confidence` per monitoraggio qualità roster
- ✅ Tipi evento estesi: `TIMEOUT`, `RED_CARD`, `YELLOW_CARD`, `PENALTY_MISSED`, `EXCLUSION_BRUTAL`
- ✅ Campo `sanction_duration` negli eventi (nullable, opzionale)
- ✅ Retrocompatibilità completa con i 4 referti già pubblicati (schema v1)
- ✅ Confidence per sezione `officials` e per team-level roster
- ✅ Test suite v2: 28 test aggiuntivi tutti verdi
- ✅ MockVisionProvider aggiornato con payload v2 realistico
- ✅ GPT4oVisionProvider: prompt aggiornato per richiedere i nuovi campi
- ✅ `_normalize_response` aggiornato con safe defaults per tutti i nuovi campi opzionali

#### Task mancanti
- aggiungere raw evidence o snippet sorgente per campi incerti
- separare chiaramente raw extraction e normalized data

#### Task operativi
- definire campi nullable nei casi ambigui (già fatto per tutti i campi v2)
- definire warning standardizzati (già implementati in validate_coherence)
- gestire compatibilita con versioni precedenti (retrocompatibilità garantita)


### 3.2 Pipeline OCR reale

Scopo: collegare un OCR reale al workflow senza inventare dati, trattandolo come canale di acquisizione parallelo al referto digitale nativo.

#### Task completati o probabili
- direzione architetturale definita
- mock/test path gia pensato per simulare il processo

#### Task mancanti
- ✅ collegare provider OCR reale al processamento [FATTO]
- ✅ gestire PDF, immagini ruotate e scan di bassa qualita [FATTO]
- ✅ gestire preprocessing base [FATTO]
- ✅ salvare raw OCR output per debug [FATTO]
- ✅ introdurre fallback quando l'estrazione fallisce [FATTO]
- ✅ distinguere estratto ma incerto da non leggibile [FATTO]

#### Task operativi
- convertire PDF in immagini quando serve
- rilevare orientamento pagina
- correggere rotazione automatica
- migliorare contrasto e luminosita
- gestire multi-pagina e merge risultati
- creare interfaccia provider astratta
- implementare primo provider OCR reale
- gestire timeout e rate limits
- gestire fallimenti provider
- salvare response raw in area tecnica
- estrarre metadata match
- estrarre squadre e roster
- estrarre punteggio finale e periodi
- estrarre arbitri e allenatori
- estrarre eventi principali quando leggibili
- se OCR fallisce, marcare come needs_review
- se OCR e parziale, salvare warning di incompletezza
- se file e illeggibile, salvare motivazione tecnica

### 3.3 Dataset e valutazione qualita

Scopo: misurare il comportamento reale su referti veri.

#### Task completati o probabili
- idea dataset referti reali gia definita
- strategia easy/medium/dirty gia emersa

#### Task mancanti
- raccogliere almeno 5-20 referti reali
- classificarli per formato e qualita
- annotare i campi target da estrarre
- creare benchmark minimo accuracy/completeness
- definire casi limite ricorrenti

#### Task operativi
- creare cartella dataset di test
- dare ID univoco a ogni referto
- etichettare qualita: pulito, medio, sporco
- annotare manualmente ground truth dei campi principali
- confrontare output OCR con ground truth
- calcolare completezza e correttezza per campo
- creare lista errori ricorrenti

---

## 4. Validazione e normalizzazione dati

### 4.1 Validazione di coerenza match

Scopo: bloccare dati impossibili o incoerenti prima della pubblicazione.

#### Task completati o probabili
- prime regole strutturali presenti
- alcuni controlli di integrita statistica gia inseriti

#### Task mancanti
- validare date, orari, competizione, fase, girone e impianto
- verificare coerenza home/away con anagrafiche esistenti
- verificare punteggio finale vs somma periodi
- verificare goal events vs final score
- bloccare duplicati giocatore nella stessa squadra
- validare formati sanzioni e exclusions

#### Task operativi
- validare formati data e ora
- validare presenza campi minimi per pubblicazione
- verificare che home_team e away_team siano diversi
- verificare che score_home e score_away siano numeri validi
- verificare che somma periodi coincida con score finale
- verificare che numero goal assegnati coincida col punteggio
- verificare che ogni atleta compaia una sola volta per roster
- generare warning o blocco in base alla gravita

### 4.2 Normalizzazione anagrafiche

Scopo: riconciliare i nomi sporchi con il database reale senza inventare.

#### Task mancanti
- ✅ team name matching con alias e fuzzy matching controllato [FATTO]
- ✅ matching giocatori con roster storico [FATTO]
- ✅ matching arbitri e tecnici [FATTO]
- ✅ gestione omonimie e casi non risolti [FATTO]
- ✅ regola null > guess nei casi ambigui [FATTO]

#### Task operativi
- creare tabella alias squadre
- creare strategia exact + fuzzy con soglia
- segnalare match dubbio sotto soglia
- tentare match atleta nel roster della stagione corretta
- distinguere nessun match da match ambiguo
- permettere correzione admin e memorizzazione alias approvati

### 4.3 Log e spiegabilita

Scopo: mantenere traccia di come un dato e stato trasformato.

#### Task mancanti
- loggare ogni correzione automatica
- distinguere valore originale, estratto, normalizzato e corretto manualmente
- salvare motivazione del warning o del blocco

#### Task operativi
- salvare raw value OCR
- salvare normalized value
- salvare corrected value post-review
- salvare motivo della trasformazione
- esporre differenze nella UI di review

---

## 5. Review admin e validazione umana

### 5.1 Coda operativa

Scopo: dare allo staff una queue davvero utile e leggibile.

#### Task completati o probabili
- validation queue per staff/admin presente
- accesso protetto da permessi base

#### Task completati [FATTO]
- ✅ aggiungere filtri per uploader, reviewer, competizione, data e stato
- ✅ aggiungere ordinamento interattivo per priorità e anzianità
- ✅ mostrare dashboard KPI in cima alla queue (totali, needs review, blocchi, pronti)
- ✅ evidenziare su riga i referti bloccati e con warning critici

### 5.2 Schermata review referto

Scopo: permettere confronto e correzione rapida del referto.

#### Task completati o probabili
- review manuale dedicata presente
- reviewer identity e internal notes introdotti
- form review gia robustito in alcune parti

#### Task mancanti
- ✅ visualizzazione side-by-side originale / estratto / corretto [FATTO]
- ✅ highlight dei campi incerti [FATTO]
- ✅ editing rapido roster e score [FATTO]
- ✅ editing arbitri, allenatori, venue, round e group [FATTO]
- ✅ sezione warning con regole violate [FATTO]
- ✅ salvataggio draft intermedio [FATTO]
- ✅ storico modifiche e differenze [FATTO]

#### Task operativi
- colonna 1 referto originale
- colonna 2 dati estratti
- colonna 3 dati corretti/admin
- rendere navigabili le sezioni lunghe
- evidenziare i campi obbligatori mancanti
- permettere modifica metadata match
- permettere modifica squadre e roster
- permettere modifica score finale e periodi
- permettere modifica arbitri e allenatori
- permettere modifica venue, fase e girone
- mostrare warning leggibili
- mostrare confidence OCR per campo critico
- suggerire possibili match anagrafici
- permettere note interne aggiuntive
- permettere salvataggio draft senza publish

### 5.3 Decisione finale

Scopo: chiudere il workflow con validate, reject e publish in modo controllato.

#### Task mancanti
- flusso completo validate / reject / publish con motivazione
- permessi piu granulari per review e publish
- conferma finale con riepilogo impatti su stats

#### Task operativi
- aggiungere pulsante validate
- aggiungere pulsante reject con motivo obbligatorio
- aggiungere pulsante publish con conferma
- mostrare riepilogo impatti prima del publish
- bloccare publish se warning bloccanti non risolti

---

## 6. Manual statistics entry

### 6.1 Risultato e box score

Scopo: completare la parte manuale necessaria prima dell'OCR pieno.

#### Task completati [FATTO]
- ✅ Inserimento quarter scores (1, 2, 3, 4 tempo)
- ✅ Validazione automatica somma quarti == finale
- ✅ Salvataggio box score in normalized_data
- ✅ Calcolo e verifica totale automatico


### 6.2 Attribuzione goal ai giocatori

Scopo: fare in modo che i profili atleta inizino a vivere davvero.

#### Task completati o probabili
#### Task completati [FATTO]
- ✅ UI per assegnazione goal a roster home e away
- ✅ Validazione somma goal assegnati == score match
- ✅ Idempotenza ricreazione eventi e ricalcolo stats
- ✅ Refresh statistiche atleta automatico al publish


### 6.3 Estensione eventi partita

Scopo: preparare il motore eventi oltre ai goal.

#### Task mancanti
- exclusions per atleta
- cartellini e sanzioni
- timeouts
- eventi per periodo o minuto
- coaching decisions dove utile

#### Task operativi
- definire struttura dati eventi oltre ai goal
- aggiungere UI minima per exclusions e cards
- validare formati ammessi
- collegare eventi a atleta, team e periodo
- aggiornare stats derivate quando gli eventi saranno attivi

---

## 7. Publishing e aggiornamento dati derivati

### 7.1 Publishing service

Scopo: pubblicare un match in modo transazionale, idempotente e tracciabile.

#### Task completati [FATTO]
- ✅ PublishingService strutturato e transazionale
- ✅ Gate standings legato a status PUBLISHED
- ✅ Idempotenza completa (MatchEvent reset & refresh)


#### Task completati [FATTO]
- ✅ loggare impatti del publish in audit trail dedicato (MatchReportAuditLog con old_status, new_status, reason, diff dati)


### 7.2 Dati derivati e classifiche

Scopo: far derivare classifiche e profili da dati pubblicati veri.



#### Task completati [FATTO]
- ✅ Standings update automatico post-publish
- ✅ Athlete stats sync (total_goals) al publish
- ✅ Idempotenza completa su re-publish / re-edit
- ✅ E2E Verification Pilot pass (Upload -> Public)

#### Task mancanti
- aggiornare match officiated per arbitri
- aggiornare match coached per allenatori


#### Task operativi
- ricalcolare standings dopo publish e republish
- aggiornare partite giocate, vinte, perse e pareggiate
- aggiornare goal fatti e subiti per squadra
- aggiornare total_goals per atleta
- aggiornare match officiated per arbitri
- aggiornare match coached per allenatori
- verificare assenza di doppio conteggio su edit successivi

---

## 8. Database e modello dominio

### 8.1 Entita core

Scopo: avere un modello dati coerente con il dominio reale del prodotto.

#### Task completati o probabili
- base modelli utenti, team, player, match e match events presente
- parte delle entita onboarding ripristinata

#### Task mancanti
- verificare copertura completa per competitions, seasons, venues, uploads e validation_logs
- formalizzare team history per atleti e tecnici
- collegare arbitri e allenatori alle partite in modo storico corretto
- verificare indici e vincoli univoci

#### Task operativi
- mappare tutte le entita realmente esistenti nel DB
- verificare relazioni FK tra match, team, competition e season
- aggiungere entita mancanti se davvero necessarie
- modellare storico appartenenza team per atleta e coach
- modellare assegnazione arbitri a match
- rivedere unique constraints e index utili

### 8.2 Integrita dati

Scopo: evitare duplicati logici e dati incoerenti nel tempo.

#### Task mancanti
- vincoli per evitare duplicati logici
- soft delete o audit dove serve
- strategie di merge entita duplicate
- data migrations per pulizia iniziale

#### Task operativi
- impedire doppie entita team quasi uguali
- impedire doppio atleta nello stesso contesto senza motivo
- definire procedura merge manuale di record duplicati
- aggiungere migration di pulizia per dati legacy

---

## 8.3 AI QUERY INTERFACE [✅ FATTO]

Scopo: Permettere agli utenti di interrogare le statistiche usando il linguaggio naturale.

### Funzionamento HYBRID MODE

1. **EXISTING PAGE MATCH (Redirect)**
   - Se la query mappa su una pagina esistente (classifiche, profilo atleta, marcatori, pagina squadra), il sistema restituisce un breve riepilogo e un link diretto alla pagina (deep link).
   - *Esempio*: "top scorer this season" -> "Marco Rossi is the top scorer with 42 goals." + CTA "View full scorers ranking".

2. **AI RESPONSE MODE (Direct Answer)**
   - Se nessuna pagina soddisfa la query, il sistema interroga direttamente il DB e genera una risposta testuale.
   - *Esempio*: "goals by Rossi in last 5 matches" -> "Rossi scored 7 goals in the last 5 matches."

### Regole di Sicurezza
- **No hallucinations**: Solo dati reali dal database.
- **Explicit fallback**: Se il dato non esiste, messaggio esplicito.
- **Clarification**: Se la query è ambigua, chiedere chiarimenti.

---

## 9. API applicative

### 9.1 API ingestion e workflow referti [✅ FATTO]

Scopo: esporre il workflow referti in modo pulito e riusabile.

#### Task mancanti
- POST /api/referti/upload
- POST /api/referti/process
- POST /api/referti/digital/start
- PUT /api/referti/digital/{id}
- POST /api/referti/digital/{id}/close
- GET /api/referti/{id}/status
- GET /api/referti/{id}/results
- PUT /api/referti/{id}/validate
- POST /ai/query (AI Query Interface)

#### Task operativi
- definire serializer input/output upload
- definire endpoint process con gestione asincrona o pseudo-asincrona
- esporre stato referto e warning
- esporre risultati estrazione e dati normalizzati
- esporre endpoint di validazione admin con audit

### 9.2 API dashboard/admin

Scopo: alimentare dashboard e queue in modo robusto.

#### Task mancanti
- GET /api/dashboard/stats
- endpoint queue/filtering
- endpoint warnings/review metadata

#### Task operativi
- restituire KPI operativi principali
- restituire queue filtrabile per stato, data e competizione
- restituire warning e campi incerti per referto
- proteggere endpoint con permessi staff/admin

### 9.3 API profili/statistiche

Scopo: alimentare il lato pubblico e mobile.

#### Task completati [FATTO]
- ✅ GET /api/v1/leagues/
- ✅ GET /api/v1/league/{id}/standings/
- ✅ GET /api/v1/league/{id}/matches/
- ✅ GET /api/v1/match/{id}/ (Published matches only)
- ✅ GET /api/v1/team/{id}/
- ✅ GET /api/v1/athlete/{id}/

- GET /api/v1/matches/?filters=... (League matches already supports this)


#### Task operativi
- definire contract JSON per profilo atleta
- definire contract JSON per coach e referee
- definire stats squadra e storico match
- definire filtri partite per stagione, competizione e team
- aggiungere paginazione e gestione errori

---

## 10. Frontend admin

### 10.1 Dashboard operativa [✅ FATTO]

Scopo: creare il cockpit del workflow referti.

#### Task completati [FATTO]
- ✅ Landing Admin Cockpit / Queue Operativa
- ✅ Filtraggio per stato, competizione e uploader
- ✅ Badge warning e fiducia OCR
- ✅ Collegamento rapido ai referti bloccati


#### Task operativi
- creare landing admin workflow referti
- mostrare card KPI principali
- mostrare queue recente
- mostrare referti con warning critici
- mostrare scorciatoie verso review e publish

### 10.2 Review UX

Scopo: rendere la review davvero usabile e veloce.

#### Task mancanti
- layout piu robusto e usabile
- errori inline
- componenti per roster ed eventi
- indicatori di confidence e warning
- UX mobile/tablet almeno per emergenza

#### Task operativi
- ridisegnare layout della review
- mostrare errori vicino al campo
- rendere usabile inserimento score, roster e goal
- aggiungere badge confidence e warning
- verificare leggibilita da tablet

---

## 11. Frontend pubblico e superfici autenticate

### 11.1 Match e team browsing

Scopo: dare valore pubblico ai dati pubblicati.

#### Task completati o probabili
- scheletro homepage e pagine base gia presente

#### Task completati [FATTO]
- ✅ Listing partite con filtri e paging
- ✅ Dettaglio match arricchito (Gated/Hardened)
- ✅ Pagina squadra con statistiche e roster
- ✅ Tabellini e cronologia risultati base


#### Task operativi
- creare lista partite filtrabile
- creare dettaglio match con score, periodi e tabellino
- creare pagina squadra con roster e risultati
- creare storico partite squadra
- mostrare classifica e indicatori base dove utili


### 11.2 Distinzione tra area pubblica e area autenticata [✅ FATTO]

Scopo: chiarire cosa cambia nel sito quando un utente naviga da guest rispetto a quando accede con un account verificato.

#### Stato attuale:
- ✅ Navigazione role-aware attiva su Sidebar e Mobile.
- ✅ Security Hardening: Visibilità legata a status PUBLISHED [FATTO].
- ✅ Onboarding Flow: Journey utente (SPID -> Pagamento -> Setup) implementato e operativo. [FATTO]


#### Task mancanti
- definire una mappa completa delle pagine pubbliche visibili senza login
- definire una mappa delle aree private/personali visibili solo dopo accesso e verifica del ruolo
- differenziare navigazione, CTA, dashboard e contenuti personalizzati
- Consolidare la distinzione tra:
    - Esperienza Pubblica (Guest): Home con CTA di registrazione, Results, Standings, Stats e Profili pubblici (read-only).
    - Esperienza Autenticata (User/Staff): Dashboard personale dedicata, gestione profili, strumenti operativi per staff, navigazione "Mio Spazio".
- **Security Hardening**: Audit completo dei permessi e protezione PII (Email, Cellulare).
- ✅ **Onboarding Flow**: Implementazione tecnica Journey utente (SPID -> Pagamento -> Setup -> Member) [FATTO].

#### Task operativi
- mantenere pubblici risultati, classifiche, pagine sport, match detail, team page e statistiche generali
- mostrare da utente autenticato una home o dashboard personalizzata con i propri dati, alert, richieste e scorciatoie operative
- sbloccare solo dopo login e autorizzazione le aree private di squadra, claim profilo, notifiche, strumenti admin e workflow referti
- differenziare header, menu, CTA e componenti in base a guest, utente autenticato e ruoli interni
- verificare privacy e permessi sui dati personali e di team
- progettare un'esperienza coerente multi-sport anche nella personalizzazione post-login

### 11.3 Profili pubblici [PARZIALE]

Scopo: trasformare il progetto in piattaforma identitaria, non solo risultati.

#### Task completati [FATTO]
- ✅ Pagina Atleta con statistiche basi (Goal, Match)
- ✅ Roaster Team con link ai profili
- ✅ Match Detail con scorer attribution

#### Task mancanti

- profilo atleta
- profilo allenatore
- profilo arbitro
- stagioni, cronologia e aggregate
- top scorers e classifiche giocatori

#### Task operativi
- definire layout profilo atleta
- definire layout profilo coach
- definire layout profilo referee
- mostrare statistiche aggregate per stagione
- mostrare cronologia squadre/match
- costruire pagina top scorers

---

## 12. Account, onboarding e claim profilo

### 12.1 Modello utente e stato account

Scopo: allineare account applicativo, stato verifica e accessi.

#### Task completati o probabili
- sistema account base gia presente
- profili ruolo automatici almeno in parte presenti

#### Task mancanti
- riallineare completamente il modello User ai campi DB reali dove necessario
- completare stati identity/subscription se previsti nel blueprint
- verificare middleware di accesso

#### Task operativi
- audit campi User presenti nel DB
- audit campi User presenti nel codice
- allineare migration, model e form dove divergono
- definire stati account e relative regole di accesso
- verificare middleware e blocchi onboarding

### 12.2 Claim profilo sportivo

Scopo: legare account e profilo sportivo in modo verificato.

#### Task mancanti
- flow rivendica profilo completo
- link account <-> profilo esistente
- gestione approvazione societa/admin
- gestione conflitti e duplicati

#### Task operativi
- creare entrypoint rivendica profilo
- cercare profili candidati per nome, squadra e stagione
- permettere invio richiesta claim
- permettere approvazione/rifiuto admin o societa
- gestire casi di claim multiplo o dubbio

### 12.3 Onboarding business

Scopo: chiudere il funnel registrazione -> verifica -> pagamento -> membership.

#### Task mancanti
- ✅ step identita [FATTO]
- ✅ step pagamento [FATTO]
- ✅ step membership/team association [FATTO]
- ✅ attivazione completa post-onboarding [FATTO]

#### Task operativi
- definire funnel onboarding reale
- implementare step identita
- implementare step pagamento
- implementare step associazione team/societa
- bloccare accessi avanzati finche onboarding non e completo

---

## 13. Sicurezza, permessi e audit

### 13.1 RBAC [PARZIALE]

Scopo: distinguere bene ruoli e poteri operativi.

#### Task completati o probabili
- accesso staff/admin a queue e review gia protetto a livello base

#### Task mancanti
- ✅ distinguere uploader, reviewer, publisher e superadmin [FATTO]
- ✅ permessi a livello societa/team [FATTO]
- ✅ proteggere API con gli stessi criteri [FATTO]
- ✅ **Security Hardening**: Audit completo dei permessi e protezione PII (Email, Cellulare) [FATTO].

### 13.2 Audit e conformita operativa [FATTO]

Scopo: sapere sempre chi ha fatto cosa e quando.

#### Task completati [FATTO]
- ✅ log azioni utente su referti (MatchReportAuditLog)
- ✅ log modifiche ai dati sensibili di match (before/after diff in audit log)
- ✅ storico publish, republish, depublish e reject
- ✅ registrare upload, review, validate, publish e reject
- ✅ registrare cambi ai campi sensibili (old_status -> new_status)
- ✅ registrare motivo del reject o override (campo reason)
- ✅ preparare vista cronologia operativa del referto (Audit Trail Completo nella Review UI)

#### Task mancanti
- report errori operativi
- preparare report errori ricorrenti

---

## 14. Qualita, test e osservabilita

### 14.1 Test automatici

Scopo: non considerare fatto cio che non e testato almeno nel nucleo critico.

#### Task completati [FATTO]
- ✅ Test integrità statistica (Match vs Events)
- ✅ Test publishing transazionale e idempotente
- ✅ Test End-to-End Pilot Verification (Upload -> Review -> Publish -> API)
- ✅ Test OCR Quality Gate


### 14.2 Test con dati reali

Scopo: misurare comportamento vero su referti reali.

#### Task mancanti
- test su referti reali multipli
- benchmark qualita OCR
- test scansioni storte o pessime
- test coerenza statistiche post-publish

#### Task operativi
- preparare piccolo set di referti veri
- eseguire pipeline su tutti
- confrontare output con correzione umana
- misurare errori principali
- verificare risultato finale dopo publish

### 14.3 Monitoring

Scopo: vedere backlog, errori e tempi del workflow.

#### Task mancanti
- ✅ logging strutturato [FATTO]
- ✅ error reporting (Sentry) [FATTO]
- ✅ metriche pipeline: upload, OCR success, review backlog, publish success [FATTO]

#### Task operativi
- aggiungere logging strutturato per workflow referti
- aggiungere cattura errori tecnici
- contare tempi medi per stato
- contare referti bloccati o falliti
- mostrare metriche minime in dashboard/admin

---

## 15. Documentazione operativa

Scopo: mantenere il progetto comprensibile e gestibile anche fuori dalla singola sessione.

#### Task mancanti
- README tecnico aggiornato
- mappa flussi referto
- guida admin reviewer
- runbook deploy
- runbook correzione dati errati
- catalogo prompt/istruzioni Antigravity

#### Task operativi
- scrivere README di architettura reale
- disegnare flusso upload -> OCR -> review -> publish
- scrivere guida staff per review referti
- scrivere guida deploy sicuro
- scrivere guida correzione match/statistiche errate
- raccogliere prompt standard per audit, implementazione e verifica browser

---

## 16. Priorita consigliata di esecuzione

### Fase 1 — Affidabilità dati e ricalcolo [COMPLETATA]
- ✅ Quarter scores, Goal attribution, Publishing transazionale, Ricalcolo stats automatico.

### Fase 2 — Workflow Admin ed Efficienza [COMPLETATA]

1. ✅ MIGLIORARE SCHERMATA REVIEW (Side-by-side, highlight campi incerti, compare originale/estratto/corretto) -> [FATTO]
2. ✅ COMPLETARE QUEUE ADMIN (Filtri reali interattivi, dashboard KPI e alert blocchi/warning su coda referti) (Section 5.1) -> [FATTO]
3. ✅ IMPLEMENTARE AUDIT TRAIL E LOG CAMBI STATO (Section 2.3 / 13.2) -> [FATTO]
4. ✅ NOTIFICHE OPERATORI (Email/Telegram quando un report entra in NEEDS_REVIEW) -> [FATTO]
    - Implementato `NotificationService` estendibile.
    - Supporto Email (via `django.core.mail`) e Telegram (via `httpx`).
    - Alert automatico integrato in `OCRService` per fallimenti Quality Gate o Errori Tecnici.

### Fase 3 — Ingestion ed Estrazione (Ingestion/OCR) [COMPLETATA]

1. raccogliere dataset referti esterni -> [SKIPPATO - MANUALE]
2. ✅ estendere schema OCR (v2.0) -> [FATTO]
3. ✅ implementare utilità PDFProcessor -> [FATTO]
4. ✅ implementare BaseOCRProvider e OCRRawResponse -> [FATTO]
5. ✅ implementare Image Preprocessor (rotazione automatica, contrasto, OpenCV/PIL) -> [FATTO]
6. ✅ implementare OpenAIProvider concreto (payload API, salvataggio RawResponse) -> [FATTO]
7. ✅ creare script Django (`manage.py evaluate_ocr`) per test accuracy su referti locali (Section 14.2) -> [FATTO]

### Fase 4 — Valore Pubblico e API (Public Layer) [COMPLETATA]

1. ✅ implementare profili atleta alimentati da dati reali (storico match, gol totali) (Section 11.3) -> [FATTO]
2. ✅ implementare profili coach e referee alimentati da dati reali (storico designazioni/partite) (Section 11.3) -> [FATTO]
3. ✅ arricchire dettaglio match (tabellino esteso) e statistiche squadra (Section 11.1) -> [FATTO]
4. ✅ implementare leaderboard, top scorers e classifiche pubbliche aggregate -> [FATTO]
5. ✅ stabilizzare API pubbliche (JSON response per frontend e mobile) (Section 9.3) -> [FATTO]

### Fase 5 — Account e Business (Onboarding/RBAC) [COMPLETATA]
1. ✅ implementare flow claim profilo sportivo (ricerca profilo e richiesta claim) (Section 12.2) -> [FATTO]
2. ✅ implementare approvazione/rifiuto claim sportivo da parte del club admin (Section 12.2) -> [FATTO]
3. ✅ consolidare step onboarding: identita, pagamento, membership e unit tests (Section 12.3) -> [FATTO]
4. ✅ consolidare RBAC granulare e protezione PII (Section 13.1) -> [FATTO]

## Nota finale

Questo syllabus non va letto come fotografia perfetta del codice. Va letto come struttura di controllo del progetto.

Antigravity deve usarlo per fare un audit reale del repository e del sito, classificando ogni capitolo e ogni blocco come:

- FATTO
- PARZIALE
- ASSENTE
- FRAGILE

e deve motivare sempre la classificazione con evidenze concrete.
