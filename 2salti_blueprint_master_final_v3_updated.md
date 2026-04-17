# Master document del progetto

*Versione unificata: prodotto, pagine, OCR, dati, design system, architettura e roadmap*

### Come usare questo documento

Questo file non separa piu in modo rigido "quello che esiste" e "quello che dovra esistere". Li fonde in un unico blueprint operativo, scritto da zero, da usare come riferimento per design, sviluppo, validazione dei referti e crescita del prodotto.

> Idea guida: ogni pagina pubblica deve essere una conseguenza del motore dati centrale. Niente numeri manuali sparsi, niente logiche duplicate, niente OCR che inventa.

### Indice operativo

## 1. Visione del prodotto e principi non negoziabili

## 1. Visione del prodotto e principi non negoziabili

2salti deve diventare l'hub multi-sport che trasforma un referto ufficiale o un referto compilato nativamente in-app in un archivio sportivo vivo. Il cuore non e la pagina bella da vedere: e la fiducia nel dato. Quando il dato e affidabile, allora classifiche, schede squadra, profili atleta, storico arbitrale e leaderboard acquistano valore reale.

La pallanuoto e il primo sport di rollout, non il limite del prodotto. La direzione corretta e quindi questa: pochi moduli, molto chiari, tutti agganciati allo stesso motore e progettati per essere replicabili anche su altri sport. Il percorso ideale parte dall'ingresso del referto, passa da compilazione digitale nativa oppure da OCR + AI + controlli, finisce nel database e aggiorna in automatico sito pubblico, dashboard e statistiche aggregate.

### Chiarimenti di baseline da tenere fissi

- Pallanuoto = primo sport lanciato e banco di prova principale; architettura, naming e navigazione vanno pero pensati come framework multi-sport.
- L'ingestione dei dati è automatizzata: i referti arrivano via email o WhatsApp e vengono processati autonomamente. L'upload manuale è un fallback per admin.
- Include un motore di interrogazione AI (AI Stats Engine) che funge da router intelligente e motore di risposte in linguaggio naturale.
- Sito pubblico e area autenticata non sono la stessa esperienza: la parte pubblica massimizza scoperta e trasparenza del dato, la parte loggata mostra dati personali, funzioni private, richieste, strumenti di ruolo e workflow autorizzati.

### Principi fissi di progetto

- Null invece di invenzione: se un campo non e leggibile, il sistema lo segnala e non lo indovina.

- Ogni numero mostrato sul sito deve essere tracciabile fino alla partita e, se serve, fino al referto sorgente.

- Le pagine pubbliche devono essere alimentate dallo stesso backend usato dall'admin, non da contenuti duplicati.

- L'esperienza guest e quella autenticata devono essere chiaramente diverse: da pubblico si navigano dati generali, da autenticato si entra in dashboard personali, permessi di ruolo e strumenti operativi.

- Prima affidabilita e usabilita interna, poi profondita pubblica, poi mobile e integrazioni.

- Le correzioni umane devono lasciare audit log, versione precedente e motivazione della modifica.


### Chiarimenti di baseline da tenere fissi

- Pallanuoto = primo sport lanciato e banco di prova principale; architettura, naming e navigazione vanno pero pensati come framework multi-sport.
- L'ingestione dei dati è automatizzata: i referti arrivano via email o WhatsApp e vengono processati autonomamente. L'upload manuale è un fallback per admin.
- Include un motore di interrogazione AI (AI Stats Engine) che funge da router intelligente e motore di risposte in linguaggio naturale.
- Sito pubblico e area autenticata non sono la stessa esperienza: la parte pubblica massimizza scoperta e trasparenza del dato, la parte loggata mostra dati personali, funzioni private, richieste, strumenti di ruolo e workflow autorizzati.

## 2. Ecosistema utenti e valore generato

Il progetto non serve a un solo tipo di utente. La stessa base dati deve generare valore diverso a seconda di chi entra nella piattaforma.

| Utente | Cosa vuole trovare | Valore generato da 2salti |
| --- | --- | --- |
| Atleta | Profilo personale, gol, presenze, crescita, storico partite | Identita sportiva persistente e numeri sempre aggiornati |
| Allenatore | Rendimento squadra, record, storico squadre, indicatori | Lettura rapida della stagione e del percorso tecnico |
| Arbitro | Partite arbitrate, designazioni, cronologia | Archivio professionale ordinato e consultabile |
| Societa / Lega | Meno inserimento manuale, meno errori, archivio centrale | Riduzione lavoro operativo e dati coerenti |
| Pubblico / fan | Scoprire squadre, partite, classifiche e profili | Esperienza semplice, sport piu leggibile, maggiore coinvolgimento |
| Admin | Caricare, correggere, approvare e pubblicare | Cockpit unico per governare l'intera piattaforma |

## 3. Struttura completa del sito e della navigazione

La piattaforma va pensata in quattro blocchi integrati: sito pubblico, area autenticata personale, area dati/profili e admin/motore. La navigazione visibile all'utente e solo la parte frontale di una macchina piu ampia che deve restare coerente da cima a fondo.

Mappa unica del prodotto: pagine pubbliche, superfici post-login, profili, area admin e motore dati.

### Inventario pagine da considerare core

| Area | Pagina | Scopo | Dato principale |
| --- | --- | --- | --- |
| Pubblico | Home | Far capire subito cos'e 2salti e dove entrare | sport, match in evidenza, CTA |
| Pubblico | Landing sport (es. Pallanuoto) | Porta di ingresso allo sport e alla stagione corrente | stagione corrente, partite, classifica |
| Pubblico | Partite | Calendario, risultati e filtri | match list + stato partita |
| Pubblico | Match detail | Rendere leggibile il tabellino completo | metadata, score, eventi, officials |
| Pubblico | Classifiche | Standing del campionato | punti, GF/GS, trend |
| Pubblico | Statistiche | Leaderboard e ranking | marcatori, espulsioni, filtri |
| Pubblico | Scheda squadra | Rendere viva una societa o team | rosa, staff, ultime gare, numeri |
| Autenticato | Dashboard personale | Mostrare dati, azioni e notifiche collegate al proprio ruolo | claim, richieste, alert, preferenze |
| Autenticato | Area squadra / ruolo | Sbloccare dati privati e funzioni autorizzate | membership, strumenti, dati riservati |
| Profili | Atleta / coach / arbitro | Creare identita persistente | storico, stagione, record |
| Servizio | Ricerca | Trovare subito persone, partite e squadre | search globale |
| Accesso | Login / register | Ingresso ruoli e impostazioni | account, tema, permessi |
| AI | AI Query | Interrogazione intelligente stats | query, answer/redirect |
| Admin | Upload / review / publish | Governare l'intero flusso referti | referto, JSON, validazione |

## 4. Home page: architettura dettagliata

La home non deve essere solo una vetrina. Deve spiegare il prodotto in pochi secondi, far entrare l'utente nello sport e anticipare il valore della parte dati.

### Struttura consigliata della home

- Header superiore con logo 2salti, link principali, ricerca rapida, login e toggle dark/light; dopo accesso l'header deve evolvere con avatar, dashboard personale e scorciatoie coerenti col ruolo.

- Hero principale con claim molto chiaro, sotto-claim orientato al valore e due CTA: entra nello sport e accedi all'area admin.

- Modulo Sport navigator con card dei vari sport; nella fase iniziale la card Pallanuoto e il percorso principale, ma la struttura deve gia poter ospitare altri sport senza riscritture.

- Blocco Campionato in evidenza con stagione corrente, classifica top 4, ultimo turno e link a partite e statistiche.

- Featured match o featured giornata con risultato, stato e link al dettaglio.

- Quick data cards con numeri semplici: squadre attive, partite pubblicate, top scorer, ultime partite aggiornate.

- Sezione Profili da scoprire con teaser di atleta, coach e arbitro, non ancora come profondita massima ma gia come promessa di piattaforma.

- Footer con link essenziali, note legali, contatti, stato progetto e collegamenti ai social o future integrazioni.

### Comportamento grafico e UX della home

- Nel primo viewport l'utente deve capire subito tre cose: sport, dati, utilita.

- La home deve funzionare anche con pochi dati: se il database e ancora incompleto, meglio pochi moduli forti che una pagina piena di sezioni vuote.

- Ogni blocco deve poter degradare elegantemente: niente card rotte, niente placeholder grezzi visibili al pubblico.

- Su mobile la gerarchia deve restare identica, solo impilata: hero, sport navigator, match in evidenza, classifica teaser, CTA profili.

### Copy direction suggerita per la hero

- Titolo: Il tuo sport, un altro livello.

- Sottotitolo: Partite, classifiche, profili e statistiche alimentati da referti ufficiali o compilati digitalmente.

- CTA 1: Esplora lo sport. CTA 2: Accedi.
- Nella fase iniziale il percorso principale puo portare alla Pallanuoto, ma il copy non deve bloccare l'identita multi-sport.

## 5. Pagine pubbliche principali

### 5.1 Landing sport - primo rollout: Pallanuoto

Scopo: Deve essere la vera porta d'ingresso al campionato corrente dello sport selezionato. Nel primo rollout questo pattern viene applicato alla Pallanuoto, ma deve restare replicabile su altri sport.

### Blocchi da prevedere:

- Hero piccolo con nome campionato/stagione e accessi rapidi a partite, classifica e statistiche.

- Blocco ultimi risultati e prossime gare.

- Blocco classifica ridotta con link alla vista completa.

- Blocco leaderboard ridotta con top marcatori o numeri chiave.

- Teaser squadre del campionato.

Nota mobile: Su mobile il campionato deve essere leggibile come feed: prima risultati, poi classifica, poi statistiche.

### 5.2 Partite

Scopo: Una pagina elenco, filtrabile e veloce da leggere.

### Blocchi da prevedere:

- Filtri per stagione, competizione, squadra, round, stato partita.

- Lista match con data, squadre, risultato, luogo e link al dettaglio.

- Gestione stato: programmata, in corso, disputata, pubblicata.

- Area archivio storico quando le stagioni cresceranno.

Nota mobile: Filtri compatti, con drawer o accordion, mai una tabella ingestibile.

### 5.3 Match detail

Scopo: E la pagina che deve dare credibilita all'intero sistema.

### Blocchi da prevedere:

- Header con metadata: data, luogo, competizione, round, squadre e risultato finale.

- Tabellino principale con score per squadra e, se disponibile, breakdown per tempi.

- Eventi partita: gol, espulsioni, carte, presenza, note arbitri.

- Blocchi officials: arbitri, allenatori, eventuali osservazioni.

- Link a squadra, giocatori e partita precedente/successiva.

Nota mobile: Il tabellino deve restare leggibile a colpo d'occhio, anche su schermo stretto.

### 5.4 Classifiche

Scopo: Una standing page stabile, molto pulita, adatta a fan e addetti ai lavori.

### Blocchi da prevedere:

- Tabella con posizione, squadra, punti, partite, vittorie, pareggi, sconfitte, gol fatti, gol subiti, differenza.

- Facoltativo: forma ultime cinque, casa/trasferta, trend frecce.

- Link sempre presenti alla scheda squadra.

Nota mobile: Le colonne si riducono su mobile ma il senso della tabella non deve rompersi.

### 5.5 Statistiche

Scopo: Una leaderboard page semplice ma profonda.

### Blocchi da prevedere:

- Vista top scorer, espulsioni, presenze o altre classifiche selezionabili.

- Filtri per stagione, squadra, competizione, ruolo.

- Card sintetiche sopra e tabella sotto.

- Ogni nome porta al profilo o, se il profilo non e pronto, a una pagina minima coerente.

Nota mobile: Su mobile la tabella diventa card list con lo stesso ordine logico.

### 5.6 Scheda squadra

Scopo: Pagina cardine per dare vita ai club.

### Blocchi da prevedere:

- Header squadra con nome, logo, stagione e posizione in classifica.

- Numeri chiave: punti, gol fatti, gol subiti, forma recente.

- Rosa e staff tecnico.

- Ultime partite e prossime gare.

- Link ai profili dei giocatori quando disponibili.

Nota mobile: La scheda deve funzionare anche se alcuni profili individuali non sono ancora completi.

## 6. Profili atleta, coach e arbitro

I profili sono la parte che trasforma 2salti da semplice sito risultati a piattaforma identitaria. Devono essere pagine vere, non solo schede con due numeri.

### Profilo atleta

- Header con nome completo, team attuale, ruolo, categoria, eventuale numero di calottina.

- Metriche stagione: gol, espulsioni, carte, partite, media per partita.

- Timeline partite o tabellino personale.

- Storico squadre e stagioni, anche se inizialmente in forma compatta.

- Grafico semplice di andamento o distribuzione gol per giornata.

Il profilo atleta deve essere percepito come una pagina da condividere.

### Profilo coach

- Header con nome, team attuale e record stagione.

- Rendimento squadra: partite, vittorie, pareggi, sconfitte, gol fatti/subiti.

- Storico squadre allenate.

- Ultime partite del team corrente.

- Indicatori semplici: forma, media punti, differenza reti.

Il coach non va trattato come anagrafica passiva ma come profilo tecnico.

### Profilo arbitro

- Header con nome e stagione corrente.

- Partite arbitrate, frequenza, campionati coperti, squadre arbitrate piu spesso.

- Storico designazioni per data e competizione.

- Archivio partite e link al dettaglio match.

Questa pagina puo diventare molto distintiva per il progetto.

## 7. Account, ruoli e impostazioni

In 2salti il profilo sportivo e l'account devono restare separati. Il profilo atleta, coach, arbitro o dirigente nasce dal motore dati; l'account nasce dalla registrazione e governa accesso, pagamento, permessi, notifiche e impostazioni.


Differenza esplicita tra esperienza pubblica e esperienza autenticata

- Guest pubblico: home, landing sport, partite, classifiche, statistiche generali, schede squadra e teaser profili.
- Utente autenticato: dashboard personale, notifiche, claim profilo, richieste membership, preferenze, stato pagamenti e funzioni legate al ruolo.
- Utente autenticato e autorizzato: accesso ad aree private di squadra, dati non pubblici, workflow operativi e strumenti amministrativi secondo permessi.
- La grafica deve far percepire questo cambio: header diverso, CTA diverse, moduli personali, alert e scorciatoie contestuali.

Architettura corretta di account e profili

- Profili sportivi pre-caricati nel sistema: players, coaches, referees, presidenti/dirigenti, club e squadre di stagione.

- Account utente separato: email, credenziali, stato abbonamento, impostazioni, preferenze, log accessi e collegamento al profilo sportivo.

- Claim del profilo: l'utente non crea il proprio profilo; cerca quello giusto e ne richiede il possesso operativo.

- Doppio stato di verifica: identita personale verificata e appartenenza sportiva verificata.

Sequenza di onboarding da bloccare

- 1) Registrazione account base con email e password o login compatibile.

- 2) Verifica identita personale: metodo principale SPID/CIE; fallback documento + selfie oppure video-selfie per stranieri, utenti senza SPID/CIE, minorenni o casi particolari.

- 3) Attivazione del pagamento mensile: solo dopo identita verificata l'utente sblocca il piano account e puo procedere con il claim completo.

- 4) Ricerca del proprio profilo sportivo gia presente nel sistema e invio della richiesta di claim.

- 5) Autenticazione con la squadra: metodo base tramite codice di attivazione fornito dal presidente o dal club admin per squadra, stagione e ruolo.

- 6) Se l'utente non possiede il codice, puo comunque inviare richiesta di accesso: il sistema notifica il club admin competente e apre una revisione manuale.

- 7) Solo dopo verifica identita, pagamento attivo e appartenenza sportiva approvata si sbloccano le aree private della squadra.

Ruoli e permessi da prevedere

- Guest pubblico: navigazione libera della parte aperta del sito.

- Subscriber verificato: account attivo e identita verificata, ma senza area privata squadra finche non completa il claim sportivo.

- Verified player / coach / referee: profilo sportivo rivendicato e verificato per il proprio ruolo.

- Verified club admin: dirigente o presidente con potere di validare i membri del club, generare codici, revocare accessi e gestire richieste.

- Internal editor / publisher / super admin: ruoli interni di piattaforma per ingestione, correzione, pubblicazione e audit.

Regole di verifica e privacy da tenere fisse

Il club admin deve poter controllare il pacchetto di verifica del richiedente, ma in una schermata dedicata e tracciata: dati essenziali sempre visibili, documento completo apribile solo quando serve davvero e con audit log.

L'identita personale non basta mai per l'accesso ai dati privati: deve esistere anche un collegamento sportivo valido tra utente, squadra, stagione e ruolo.

Tema dark/light, recupero password, sessioni e messaggi di errore restano parte del modulo account, ma non devono alterare questa gerarchia di sicurezza.

## 8. Dashboard admin e workflow editoriale

L'admin dashboard e il vero cockpit del progetto. Se qui il flusso e confuso, tutta l'automazione perde valore. Va progettata come uno strumento operativo per chi lavora su referti e pubblicazioni, non come una pagina accessoria.

| Schermata | Funzione | Elementi chiave |
| --- | --- | --- |
| Dashboard | Vista stato sistema | coda referti, alert, ultimi upload, match pubblicati |
| Upload referto | Ingresso file | drag&drop, tipo file, metadata iniziali, source email |
| Referto digitale | Compilazione nativa in-app | metadata match, roster, score, officials, salvataggio draft |
| Extraction review | Controllo JSON | preview immagine, campi estratti, confidence, warning |
| Correction panel | Fix manuali | edit campi, merge persone/squadre, note revisione |
| Duplicate check | Evitare doppioni | match simili, confronto rapido, blocco publish |
| Publish step | Chiusura workflow | approva, rimanda in revisione, rifiuta, audit log |
| Logs / storico | Traccia operativa | chi ha fatto cosa, quando e su quale referto |

Stati di lavorazione consigliati

- UPLOADED - file ricevuto e salvato.

- EXTRACTED - OCR/AI completato con JSON grezzo disponibile.

- NEEDS_REVIEW - presenti warning, campi null critici o incoerenze.

- VERIFIED - controlli completati e dato pronto.

- PUBLISHED - dati scritti sul database pubblico e cache aggiornate.

- REJECTED - file scartato, con motivazione tracciata.

Moduli operativi da aggiungere alla dashboard

- Inbox richieste profilo e membership: elenco di utenti che hanno completato identita e pagamento e chiedono accesso alla squadra.

- Pannello codici di attivazione: creazione, scadenza, revoca, riemissione e tracciamento per club, squadra, stagione e ruolo.

- Centro notifiche club admin: avvisi automatici quando un utente tenta il claim senza codice, quando un documento richiede revisione o quando un accesso va revocato.

- Audit log leggibile: chi ha approvato chi, quale documento e stato aperto, quando e con quale esito.

## 9. OCR, ingestione, validazione e pubblicazione

L'OCR non va pensato come una scatola magica. Deve essere un processo completo: ingresso file, normalizzazione, lettura, parsing in JSON strutturato, controlli e solo dopo eventuale pubblicazione.

Workflow dall'ingresso del referto alla statistica pubblicata.

Canali di ingresso

- Foto da smartphone.

- Scansione singola o multipagina.

- PDF generato da scanner o da sistemi esterni.

- Email ingest con allegato referto (Automatico).
- WhatsApp ingest (Automatico).
- Referto digitale compilato direttamente in-app da arbitri o personale di giuria.
- Upload manuale (Solo per Admin come fallback).

Comportamento del modulo OCR/AI

- Pre-processing: rotazione, ordine pagine, controllo qualita minima, eventuale cropping.

- Prompt strutturato orientato al dominio sportivo e al referto ufficiale.

- Output obbligatorio in JSON rigido; nessun testo libero come risposta finale.

- Confidence per campo o gruppo di campi.

- Null esplicito se il dato non e leggibile.

- Conservazione di file originale, risposta grezza del modello, JSON normalizzato e versione post-revisione.

Il referto digitale nativo deve produrre lo stesso contratto dati finale, saltando OCR ma non review, validazione, audit e publish.

Campi da estrarre come base minima

| Blocco | Campi | Note |
| --- | --- | --- |
| Match metadata | data, ora, competizione, round/fase, girone, venue, home team, away team, score finale | senza questi campi il match non si pubblica |
| Giocatori per team | nome, numero, gol, espulsioni, carte, presenza/convocazione | gestire null e grafie sporche |
| Officials | arbitro/i, allenatore casa, allenatore trasferta | fondamentale per profili coach e arbitro |
| Referto file | path file, tipo file, pagina/e, hash, source | serve per audit e duplicate check |
| Confidence e warning | campo, score fiducia, warning logico | visibili nell'admin |

Validazioni automatiche indispensabili

- Campi obbligatori presenti prima della pubblicazione.

- Coerenza tra punteggio finale e somma eventi, quando gli eventi sono completi.

- Riconciliazione nomi squadra e persone con database esistente.

- Controllo duplicato per data + squadre + competizione + punteggio.

- Valori impossibili o sospetti segnalati, non pubblicati in silenzio.

- Eventuali conflitti di identita messi in review umana.

Regola di sicurezza da tenere fissa

L'OCR crea e aggiorna solo dati sportivi: partite, eventi, persone, squadre, statistiche e warning. Non deve mai creare account utente, concedere permessi o approvare accessi alle aree private.

> Se i controlli non passano, il match non va live. Il sistema deve privilegiare l'affidabilita rispetto alla velocita.

---

## 9.1 AI STATS ENGINE

Scopo: Fornire un'interfaccia di ricerca e analisi basata su AI che integri la navigazione esistente con risposte dinamiche.

### Architettura
User Input -> AI Parser -> Intent -> Query Builder -> DB -> Response Generator

### Componenti Core

1. **QUERY PARSER**
   - Input: linguaggio naturale.
   - Output: `{ entity, metric, filters, time_range }`.

2. **PAGE RESOLVER**
   - Rileva se la query mappa su una pagina esistente.
   - Output: `{ type: "page", target_url, summary }`.

3. **QUERY BUILDER**
   - Converte l'intent in query ORM (Django).
   - Utilizza i modelli: Match, MatchEvent, Athlete, Team.

4. **STATS ENGINE**
   - Esegue aggregazioni (count, sum) filtrate per match, date o team.

5. **RESPONSE GENERATOR**
   - Produce l'output finale in formato JSON per il frontend.

### Safety & Guardrails
- **Zero Hallucination**: Risposte basate solo sui dati certi del database.
- **Validazione Entità**: Verifica che atleti e squadre esistano prima di rispondere.
- **Ambiguity Handling**: Se la query è ambigua, il sistema chiede chiarimenti invece di indovinare.

---

## 10. Modello dati e motore statistiche

Per evitare caos, il database deve riflettere entita reali e relazioni chiare. Statistiche e profili non vanno salvati come testo libero: devono nascere da match, persone, team, stagioni ed eventi partita.

Entita minime e relazioni da cui devono derivare profili e statistiche.

Entita chiave

- matches - una riga per partita, con metadata, stato workflow e collegamento al referto o al referto digitale nativo.

- teams - club o squadra in una specifica stagione/categoria.

- players - identita atleta, ruolo, legami con team e storico.

- coaches - identita allenatore e storico squadre.

- referees - identita arbitro e storico designazioni.

- match_events - layer piu prezioso per gol, espulsioni, carte, presenze.

- seasons / competitions - contesto di campionato, girone, round.

- cached_stats - aggregati veloci per homepage, classifiche e profili.

- report_sources / match_reports - origine del dato sportivo: upload esterno, email ingest oppure compilazione digitale in-app.

Entita applicative per account, pagamenti e accessi privati

- user_accounts - identita applicativa con email, credenziali, stato verifica e preferenze.

- subscriptions - piano attivo, storico rinnovi, stato pagamento e grace period.

- account_profile_links - collegamento tra account e profilo sportivo rivendicato.

- claim_requests - richieste di possesso profilo con stato, note e revisore.

- team_activation_codes - codici temporanei o permanenti emessi dal club admin, legati a squadra, stagione e ruolo.

- membership_requests - richieste di accesso squadra, con o senza codice, e relativo esito.

- verification_events - traccia delle verifiche SPID/CIE o fallback documento + selfie/video-selfie.

- permission_scopes - matrice finale di cio che un utente puo vedere: pubblico, profilo verificato, area privata squadra, gestione club.

Motore statistiche: regole operative

- Le classifiche di campionato derivano da matches verificati, non da inserimenti manuali separati.

- Le leaderboard giocatori derivano da match_events o, in fallback controllato, dai tabellini verificati.

- Il profilo rapido puo usare cache, ma la fonte di verita resta il dato normalizzato.

- Ogni ricalcolo deve essere idempotente: rigenerare lo stesso match non deve creare doppioni.

## 11. API, backend, infrastruttura e operations

L'architettura deve rimanere semplice da capire. Sopra c'e l'interfaccia, in mezzo il layer applicativo, sotto il motore OCR/AI, il database e l'infrastruttura.

Vista a layer: esperienza utente, application layer, AI processing, data e operations.

Struttura logica consigliata del backend

- Frontend pubblico per home, partite, classifiche, squadre, profili e accesso.

- Dashboard admin separata ma coerente visivamente.

- API applicative per upload, process, status, profili, partite e classifiche.

- OCR service che riceve file, costruisce prompt e restituisce JSON.

- Rules engine per coerenza, duplicate detection e normalizzazione.

- DB relazionale con storage file e log di elaborazione.

- Cache o materialized layer per rendere veloci le pagine pubbliche.

Endpoint MVP da prevedere

- POST /auth/register, POST /auth/verify-identity, POST /auth/payment/activate - apertura account, verifica identita e attivazione del piano.

- GET /profiles/search e POST /profiles/{id}/claim - ricerca del profilo sportivo e richiesta di claim.

- POST /teams/access-by-code e POST /teams/request-access - accesso tramite codice oppure richiesta manuale con notifica al club admin.

- GET /club-admin/requests, POST /club-admin/requests/{id}/approve, POST /club-admin/requests/{id}/reject - workflow di approvazione membership.

- POST /club-admin/codes e POST /club-admin/codes/{id}/revoke - gestione dei codici di attivazione.

| Metodo + path | Funzione | Output |
| --- | --- | --- |
| POST /ai/query | AI Query Interface endpoint | answer/redirect + data |
| POST /api/referti/upload | Carica il file e crea il job | job id + stato iniziale |
| POST /api/referti/process | Lancia OCR/AI sul job | stato elaborazione |
| POST /api/referti/digital/start | Crea un referto digitale nativo | id referto + draft iniziale |
| PUT /api/referti/digital/{id} | Aggiorna il draft digitale | bozza salvata |
| POST /api/referti/digital/{id}/close | Chiude il referto digitale e lo manda a review/validate | stato workflow |
| GET /api/referti/{id}/status | Restituisce stato workflow | UPLOADED/EXTRACTED/... |
| GET /api/referti/{id}/results | Mostra JSON estratto e warning | payload per admin |
| PUT /api/referti/{id}/validate | Correzione + approvazione | stato aggiornato |
| GET /api/matches | Lista partite e filtri | match list |
| GET /api/players/{id} | Profilo atleta | bio + season stats |
| GET /api/coaches/{id} | Profilo coach | record + storico |
| GET /api/referees/{id} | Profilo arbitro | designazioni + partite |
| GET /api/teams/{id} | Scheda squadra | rosa, stats, ultime gare |

Infrastruttura e operations

La base tecnica gia impostata su server Hetzner puo restare il punto di partenza, ma va ordinata in moduli stabili: app backend, ocr module, email ingest, scripts, storage referti, database, log e deploy GitHub.

- Project root unico e leggibile, con separazione chiara fra backend, OCR, ingest e utility.

- Log per ogni job di referto, con errori, warning e tempi di esecuzione.

- Storage originale dei file e hash per duplicate detection.

- Deploy disciplinato via GitHub, con ambiente di test prima del live.

## 12. Grafica del sito e regole UX

La grafica di 2salti deve sembrare sportiva ma non caotica, moderna ma non giocattolo. La sensazione giusta e quella di una piattaforma dati affidabile, con energia sportiva e leggibilita prima di tutto.

Palette, tipografia, componenti base, tema dark/light e regole UX.

Direzione visiva

- Palette primaria basata su blue + navy, con teal, orange e green come colori funzionali.

- Card arrotondate, sfondi molto puliti, ampio respiro tra moduli.

- Titoli grandi e netti; testo secondario piu morbido, mai grigio troppo scarico.

- Grafici pochi ma chiari; tabelle pulite, con varianti card su mobile.

- Dark mode coerente, non improvvisata: contrasto alto, stessi componenti, stessi spazi.

Regole UX da tenere fisse

- Ricerca e cambio tema sempre accessibili.
- Da guest e da utente loggato il sito deve essere riconoscibile come la stessa piattaforma, ma con gerarchie e moduli diversi: da pubblico scoperta e consultazione; da autenticato azione, personalizzazione e strumenti.

- Ogni pagina dati deve mostrare contesto: stagione, competizione, data ultimo aggiornamento.

- Nessuna pagina pubblica deve sembrare rotta quando il dato manca: usare stati vuoti curati e copy chiaro.

- Filtri semplici, visibili e coerenti tra partite, classifiche e statistiche.

- AI search bar sempre visibile nell'header o sidebar.
- Risposte AI con breakdown opzionale dei dati.

---

## 13. Modello di business e priorita di esecuzione

Il modello economico da bloccare e un micro-abbonamento mensile per account. L'obiettivo non e far pagare la creazione del profilo sportivo, ma l'accesso verificato alla piattaforma, alle funzioni personali e alle aree private autorizzate.

Struttura economica consigliata

- Prezzo guida iniziale: circa 0,50 EUR al mese per account.

- Pagano atleti, allenatori, arbitri, presidenti/dirigenti e utenti premium che vogliono usare davvero la piattaforma.

- Il profilo sportivo puo esistere anche senza account; il pagamento serve a trasformare quel profilo in esperienza personale, verificata e operativa.

- Il valore pagato dall'utente comprende: verifica identita, claim del profilo, dashboard personale, notifiche, accesso riservato e strumenti coerenti con il ruolo.

Ordine logico del funnel

- 1) Registrazione account.

- 2) Verifica identita personale.

- 3) Attivazione del pagamento.

- 4) Claim del profilo sportivo.

- 5) Accesso squadra tramite codice o richiesta manuale notificata al club admin.

- 6) Approvazione finale e sblocco delle aree private.

Equilibrio tra pubblico e riservato

La piattaforma puo mantenere una superficie pubblica utile per scoperta, SEO e reputazione del dato - home, partite, classifiche, teaser profili - ma il vero valore operativo vive dietro account verificato e pagamento attivo.

Priorita di esecuzione aggiornata

- 1) Nucleo affidabile del dato: upload, referto digitale nativo, OCR strutturato, validazione, database e profili sportivi pre-caricati.

- 2) Modulo account: registrazione, SPID/CIE, fallback documento + selfie/video-selfie e pagamento.

- 3) Claim e membership: ricerca profilo, codici di attivazione, notifiche al club admin, approvazioni e revoche.

- 4) Area pubblica robusta e dashboard private per ruoli verificati, con distinzione netta tra guest e autenticato.

- 5) Crescita: nuovi sport oltre la pallanuoto, email ingest, mobile/PWA, analytics piu profonde e integrazioni future.

## 14. Decisioni immediate da bloccare

Per evitare dispersione, le scelte da usare come baseline del progetto sono queste.

- Profili sportivi creati dal sistema; gli utenti non creano da zero il proprio profilo sportivo.

- Verifica identita personale con SPID/CIE come metodo principale.

- Fallback documento + selfie oppure video-selfie per stranieri, utenti senza SPID/CIE, minorenni o casi eccezionali.

- Sequenza funnel: registrazione -> verifica identita -> pagamento -> claim profilo -> accesso squadra.

- Metodo base di appartenenza sportiva: codice di attivazione fornito dal club.

- Se il codice manca, il sistema deve permettere richiesta manuale e notificare automaticamente il club admin competente.

- Il club admin puo validare i membri e aprire il documento completo solo in una vista protetta e tracciata.

- L'accesso ai dati privati di squadra richiede sempre entrambe le condizioni: identita verificata e membership sportiva approvata.

- Il dato sportivo puo entrare sia da OCR sia da referto digitale compilato nativamente in-app; entrambi devono convergere nello stesso contratto dati e nello stesso workflow di controllo.

- L'OCR aggiorna il mondo sportivo ma non crea account e non assegna permessi.

- La pallanuoto e il primo sport di rollout, ma repository, navigazione, design system e dominio devono restare estendibili ad altri sport.

- Il sito deve avere una superficie pubblica chiara e una superficie autenticata/personale distinta, con permessi e contenuti coerenti con il ruolo.

- Modello economico base: micro-abbonamento mensile per account, con prezzo guida intorno a 0,50 EUR.
