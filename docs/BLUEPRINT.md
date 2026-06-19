# Master document del progetto

*Versione unificata: prodotto, pagine, OCR, dati, design system, architettura e roadmap*

### Come usare questo documento

Questo file non separa più in modo rigido "quello che esiste" e "quello che dovrà esistere". Li fonde in un unico blueprint operativo, scritto da zero, da usare come riferimento per design, sviluppo, validazione dei referti e crescita del prodotto.

> Idea guida: ogni pagina pubblica deve essere una conseguenza del motore dati centrale. Niente numeri manuali sparsi, niente logiche duplicate, niente OCR che inventa.

### Indice operativo

## 1. Visione del prodotto e principi non negoziabili

2salti deve diventare l'hub multi-sport che trasforma un referto ufficiale o un referto compilato nativamente in-app in un archivio sportivo vivo. Il cuore non è la pagina bella da vedere: è la fiducia nel dato. Quando il dato è affidabile, allora classifiche, schede squadra, profili atleta, storico arbitrale e leaderboard acquistano valore reale.

La pallanuoto e il primo sport di rollout, non il limite del prodotto. La direzione corretta e quindi questa: pochi moduli, molto chiari, tutti agganciati allo stesso motore e progettati per essere replicabili anche su altri sport. Il percorso ideale parte dall'ingresso del referto, passa da compilazione digitale nativa oppure da OCR + AI + controlli, finisce nel database e aggiorna in automatico sito pubblico, dashboard e statistiche aggregate.

### Chiarimenti di baseline da tenere fissi

- Pallanuoto = primo sport lanciato e banco di prova principale; architettura, naming e navigazione vanno però pensati come framework multi-sport.
- L'ingestione dei dati è automatizzata: i referti arrivano via email o WhatsApp e vengono processati autonomamente.
- **Relazione strategica OCR ↔ Referto Digitale**: Il Referto Digitale in-app è la via principale per l'ingestione affidabile del dato; l'OCR resta in sviluppo come fallback per campionati/giurie che non adottano il digitale o per archivio storico. Entrambe le fonti convergono nello stesso contratto dati e workflow di validazione.
- Include un motore di interrogazione AI (AI Stats Engine) che funge da router intelligente e motore di risposte in linguaggio naturale.
- Sito pubblico e area autenticata non sono la stessa esperienza: la parte pubblica massimizza scoperta e trasparenza del dato, la parte loggata mostra dati personali, funzioni private e strumenti di ruolo.

### Principi fissi di progetto

- Null invece di invenzione: se un campo non e leggibile, il sistema lo segnala e non lo indovina.
- Ogni numero mostrato sul sito deve essere tracciabile fino alla partita e, se serve, fino al referto sorgente.
- Le pagine pubbliche devono essere alimentate dallo stesso backend usato dall'admin, non da contenuti duplicati.
- L'esperienza guest e quella autenticata devono essere chiaramente diverse: da pubblico si navigano dati generali, da autenticato si entra in dashboard personali e strumenti operativi.
- Prima affidabilità e usabilità interna, poi profondità pubblica, poi mobile e integrazioni.
- Le correzioni umane devono lasciare audit log, versione precedente e motivazione della modifica.

## 2. Ecosistema utenti e valore generato

Il progetto genera valore differenziato in base al ruolo e al piano di abbonamento attivo.

| Utente | Valore generato (Freemium) | Valore aggiunto (Premium Utente / Club Pro) |
| --- | --- | --- |
| Atleta | Profilo, gol, presenze, crescita | Media Gallery, Season Recap, Dashboard personalizzata |
| Genitore / Tifoso | Consultazione bacheca e statistiche | Live Alerts push, Chatbot AI, widget personalizzati |
| Allenatore | Rendimento squadra, record | Statistiche avanzate, gestione bacheca (via Club Pro) |
| Arbitro / Giuria | Consultazione cronologia | Referto digitale mobile, firma ufficiale, certificazione |
| Societa / Lega | Pagina base, roster, calendario | Bacheca push, Shop vetrina, Sponsor, Widget Club |
| Admin | Cockpit unico di governo | Monitoraggio pipeline, audit log, gestione permessi |

### Matrice servizi per piano

| Servizio                | Pagante         | Fruizione       | Connessione   | RBAC        |
| ----------------------- | --------------- | --------------- | ------------- | ----------- |
| Consultazione Bacheca   | Club Pro        | Tutti (Gratis)  | Web/App       | No          |
| Notifiche Push Bacheca  | Club Pro        | Solo Premium    | Push Act.     | Si          |
| Referto Digitale        | Giuria (Gratis) | Tutti (via API) | Offline-first | Si (Token)  |
| Chatbot AI              | Premium         | Solo Premium    | Web/App       | Si (Hard)   |
| Media Gallery / Tagging | Premium         | Tutti (Vista)   | Cloud/CDN     | Si (Opt-in) |
| Live Alerts (Referto)   | Premium         | Solo Premium    | Push Act.     | Si          |
| Season Recap            | Premium         | Solo Premium    | Batch PDF     | Si          |
| Shop vetrina (Request)  | Club Pro        | Tutti (Ordina)  | Out. Webhook  | Si (Order)  |
| Sponsor & Widget Club   | Club Pro        | Tutti (Vista)   | Web/App       | No          |
| Personalizzazione Dash  | Premium         | Solo Premium    | DB Sync       | Si          |

## 3. Struttura completa del sito e della navigazione

Mappa del prodotto: pagine pubbliche, superfici post-login, profili e strumenti operativi.

### Inventario pagine core

| Area           | Pagina                      | Scopo                                                          |
| -------------- | --------------------------- | -------------------------------------------------------------- |
| Pubblico       | Home / Landing Sport        | Hub di ingresso, campionati, classifiche teaser                |
| Pubblico       | Partite / Match Detail      | Calendario, risultati, tabellini e cronologia eventi           |
| Pubblico       | Classifiche / Statistiche   | Standing squadre e leaderboard marcatori                       |
| Pubblico       | Scheda squadra / Società    | Rosa, staff, sponsor, bacheca pubblica, link esterno           |
| Autenticato    | Dashboard personalizzata    | Widget riordinabili (Premium), alert, preferenze               |
| Autenticato    | Bacheca (Atleti / Genitori) | Comunicazioni società gated: scrittura Club Pro, lettura tutti |
| Autenticato    | Media Gallery Partita       | Upload (Premium) e visualizzazione foto/video taggati          |
| Autenticato    | Vetrina Shop Società        | Catalogo prodotti con pulsante "Richiesta Materiale"           |
| Autenticato    | Chatbot Panel               | Interfaccia AI per query e comandi operativi                   |
| Profili        | Atleta / Coach / Arbitro    | Identità sportiva, storico e Season Recap (Premium)            |
| Admin / Giuria | Form Referto Digitale       | Compilazione mobile, firma PIN, sync offline                   |
| Admin          | Cockpit Workflow            | Review OCR, validazione, audit log e publishing                |

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

### 5.6 Scheda squadra / Pagina Società

Scopo: Pagina cardine per dare vita ai club, con flessibilità tra contenuto nativo ed esterno.

### Blocchi da prevedere:
- Header squadra con nome, logo, stagione e posizione in classifica.
- **Modello Widget**: Layout a slot fissi riordinabili (non drag&drop) per sponsor, roster, calendario, bacheca pubblica, gallery, staff e storia.
- **Opzione Sito Esterno**: Se la società ha un proprio sito, può disattivare la pagina 2salti personalizzata. In questo caso, il CTA "Pagina Società" effettua un **redirect diretto** al sito esterno; un badge o una nota "Sito esterno gestito dal Club" viene mostrato nell'elenco società per gestire le aspettative dell'utente. I dati sportivi (partite, classifiche) restano comunque accessibili nelle pagine pubbliche del motore 2salti.
- Numeri chiave: punti, gol fatti, gol subiti, forma recente.
- Ultime partite e prossime gare.
- Sponsor: Visibili sulla pagina società e in forma ridotta sui profili degli atleti del club.

Nota mobile: La scheda deve funzionare anche se alcuni moduli (es. Sponsor) non sono attivi per quella specifica società.

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

In 2salti il profilo sportivo e l'account sono separati. Il profilo nasce dai dati; l'account governa l'accesso e i permessi.

### 7.1 Profili default per ruolo
Prima della personalizzazione Premium, ogni utente riceve un setup di default basato sul ruolo verificato:

| Ruolo | Dashboard Default (Widget) | Header / Navigazione | Permessi RBAC | Notifiche Default |
| --- | --- | --- | --- | --- |
| **Atleta** | Ultime gare, Stats personali, Prossimo match | Mio Profilo, Team | Lettura area team | Risultati, Variazioni orario |
| **Genitore** | Squadra figlio, Calendario, Bacheca | Figli, Team, Shop | Lettura area team | Alert live match, Bacheca |
| **Allenatore** | Roster, Registro presenze, Stats team | Gestione Team, Dati | Scrittura area team | Report partita post-match |
| **Dirigente** | KPI Club, Richieste membership, Sponsor | Club Admin, Shop Admin | Gestione Club | Nuove richieste, Alert Shop |
| **Arbitro** | Mie designazioni, Storico, Rimborsi | Archivio Arbitrale | Update match assigned | Nuove designazioni |
| **Giuria (Cert)**| Match corrente (Form Referto) | Live Match Tool | Edit match token-spec | Nessuna |
| **Admin** | Cockpit completo, System health | Super Admin Panel | Full access | Errori critici pipeline |

La personalizzazione Premium permette di sovrascrivere questi default riordinando o nascondendo widget e cambiando il tema colore.

### 7.2 Onboarding e Claim Profilo
Esperienza differenziata tra Guest e Autenticato:
- **Guest**: Navigazione libera dati pubblici (Classifiche, Risultati, Schede Squadra).
- **Utente Premium**: Sblocca dashboard personalizzata, Live Alerts, Chatbot, Gallery e Season Recap.
- **Utente Club Pro**: Sblocca per la società la gestione bacheca, shop, sponsor e pagina dedicata.

**Sequenza di onboarding**:
1. Registrazione account base (Email/Password).
2. Verifica identità (SPID/CIE come primario; fallback doc+selfie).
3. Selezione Piano: Freemium (gratis), Premium o Club Pro.
4. Claim del profilo sportivo (Ricerca e richiesta possesso).
5. Autenticazione con la squadra: Tramite codice fornito dal club o richiesta manuale al Club Admin.
6. Accesso completo post-approvazione.

### 7.3 Regole di verifica e privacy

- Il club admin deve poter controllare il pacchetto di verifica del richiedente, ma in una schermata dedicata e tracciata: dati essenziali sempre visibili, documento completo apribile solo quando serve davvero e con audit log.
- L'identità personale non basta mai per l'accesso ai dati privati: deve esistere anche un collegamento sportivo valido tra utente, squadra, stagione e ruolo.
- Per i minorenni: richiesto opt-in esplicito del genitore per Media Gallery e tagging.
- Tema dark/light, recupero password, sessioni e messaggi di errore restano parte del modulo account, ma non devono alterare la gerarchia di sicurezza.

### 7.4 Referto Digitale In-App

Strumento dedicato alla giuria e agli arbitri per l'ingestione nativa del dato di partita. Sostituisce il cartaceo come fonte primaria.

#### 7.4.1 Accesso e Certificazione (Giuria)
- **Utilizzo**: Esclusivamente da smartphone. Gratis per la giuria.
- **Token Match-Specific**: L'account giuria riceve un token legato a un singolo `match_id` + `user_id`, emesso dalla federazione/lega.
- **Finestra di validità**: Attivo da 30 minuti prima del match; revoca automatica al fischio finale. Un account senza token attivo non può modificare alcun referto.
- **Certificazione**: Richiede workflow di sicurezza (emissione token → validazione → scadenza → revoca manuale admin).

#### 7.4.2 Architettura Offline-First
- Compilazione locale tramite Service Worker + IndexedDB.
- Salvataggio continuo in locale; sincronizzazione automatica al ritorno della rete.
- Le Live Alerts push partono solo quando la connessione è attiva; offline il referto resta valido ma muto verso gli abbonati.

#### 7.4.3 Firma e Statistiche
- **Firma Arbitro**: Inserimento PIN personale a fine gara. Il referto diventa immutabile; correzioni solo via admin audit log.
- **Livelli di Statistiche** (scelta giuria, entrambi gratis):
    - **Base**: Gol, cartellini, espulsioni, timeout, parziali, nomi squadre, luogo, orario.
    - **Avanzato**: Palombelle, contropiedi, rigori causati, parate, ecc.
- **Principio del Dato Certo**: Se il dato avanzato non è rilevato, il sistema mostra "non rilevato", mai valori inventati (coerente con il principio "Null invece di invenzione" del Cap. 1).
- **Form UX**: Mobile-first, validazioni inline (es. somma parziali == totale gol), più veloce del cartaceo. È lo strumento con cui proporre alla federazione il passaggio dal cartaceo al digitale: deve essere più rapido e meno error-prone della compilazione manuale.

### 7.5 Chatbot AI (L'impiegato virtuale)

Disponibile esclusivamente per **utenti Premium**.

- **Capacità**: Risponde a query su statistiche (pubbliche e private, queste ultime solo se l'utente ha i permessi RBAC per accedervi), informazioni sulla piattaforma, info squadra (allenamenti, bacheca) se l'utente è iscritto.
- **Function Calling**: Esegue comandi operativi via chat (spostare widget, cambiare tema, applicare colori squadra, gestire notifiche, nascondere sezioni).
- **Sicurezza RBAC**: Permission check server-side obbligatorio per ogni chiamata. Il chatbot non deve mai restituire dati che l'utente non avrebbe diritto di vedere navigando manualmente. Nessun bypass via prompt.
- **Audit Log**: Ogni comando eseguito dal bot è tracciato in un log visibile all'utente per reversibilità e trasparenza.

### 7.6 Media Gallery & AI Tagging

Spazio dedicato ai contenuti multimediali della partita.

- **Fruizione**: Caricamento foto/video riservato a **utenti Premium**. Visualizzazione pubblica sul profilo atleta, salvo opt-out.
- **AI Pipeline**: Face detection + match automatico con il roster ufficiale della partita.
- **Tagging**: I tag validati alimentano le gallery personali nei profili atleta. Prevedere una coda di review (almeno inizialmente manuale o semi-automatica) per evitare mis-tagging.
- **Privacy Minorenni**: Richiesto opt-in esplicito del genitore per upload e tagging. L'atleta può sempre esercitare l'opt-out globale o per singolo contenuto.

## 8. Dashboard admin e workflow editoriale

L'admin dashboard è il vero cockpit del progetto. Se qui il flusso è confuso, tutta l'automazione perde valore. Va progettata come uno strumento operativo per chi lavora su referti e pubblicazioni, non come una pagina accessoria.

### Schermate core dell'admin

| Schermata | Funzione | Elementi chiave |
| --- | --- | --- |
| Dashboard | Vista stato sistema | coda referti, alert, ultimi upload, match pubblicati |
| Upload referto | Ingresso file manuale | drag&drop, tipo file, metadata iniziali, source email/WA |
| Referto digitale | Compilazione nativa in-app | metadata match, roster, score, officials, salvataggio draft |
| Extraction review | Controllo JSON | preview immagine, campi estratti, confidence, warning |
| Correction panel | Fix manuali | edit campi, merge persone/squadre, note revisione |
| Duplicate check | Evitare doppioni | match simili, confronto rapido, blocco publish |
| Publish step | Chiusura workflow | approva, rimanda in revisione, rifiuta, audit log |
| Logs / storico | Traccia operativa | chi ha fatto cosa, quando e su quale referto |

### Stati di lavorazione del workflow

Lo stato di partenza dipende dal `source_channel` del referto. I referti cartacei (FILE) entrano come UPLOADED e attraversano OCR; i referti digitali nativi (DIGITAL) partono da DRAFT senza OCR. I due flussi confluiscono su VALIDATED → PUBLISHED.

- **Flusso cartaceo (FILE):** UPLOADED → PROCESSING → EXTRACTED → VALIDATED → PUBLISHED
- **Flusso digitale (DIGITAL):** DRAFT → VALIDATED → PUBLISHED
- **Branch di revisione:** PROCESSING → NEEDS_REVIEW (quality gate bloccante o errore OCR); il reviewer può promuovere NEEDS_REVIEW → VALIDATED o ri-qualificarlo a EXTRACTED, oppure ri-processarlo riportandolo a PROCESSING
- **Stato parallelo di rifiuto:** REJECTED (con motivazione obbligatoria); ri-processabile con ritorno a PROCESSING
- Ogni transizione lascia audit log con utente, timestamp, diff dati e motivo
- Il gate di pubblicazione (standings, profili) è legato allo stato PUBLISHED

> Per la fonte di verità completa con transizioni e side effects vedi [docs/STATE_MACHINES.md](../docs/STATE_MACHINES.md) §1.

### Principi UX dell'admin cockpit

- Tutto deve essere leggibile in una schermata principale: quanti referti pendenti, quanti in errore, quanti pronti al publish.
- La review side-by-side (originale / estratto / corretto) è il cuore operativo e deve restare sempre a massimo due click di distanza.
- Ogni azione irreversibile (publish, reject, depublish) richiede conferma con riepilogo impatti.
- I filtri della coda devono essere veri, persistenti e condivisibili via URL.

## 9. OCR, ingestione e validazione

L'OCR funge da fallback strategico per i referti cartacei. Il Referto Digitale in-app resta la via principale; l'OCR continua a essere sviluppato per campionati che non adottano il digitale e per l'archivio storico.

### Canali di ingresso

- Email dedicata con estrazione allegati automatica.
- WhatsApp con bot di ingestione e deduplica.
- Upload manuale da admin come fallback.
- Foto da smartphone, scansioni, PDF multipagina.

### Comportamento del modulo OCR

- **Pre-processing** (OpenCV/PIL): rotazione automatica, correzione contrasto, split multipagina, normalizzazione dimensioni.
- **Estrazione** via provider LLM Vision con prompt strutturato che forza output JSON rigido.
- **Confidence score** per campo e per sezione; soglia configurabile sotto la quale il referto va in NEEDS_REVIEW.
- **Raw evidence** salvata per ogni campo dubbio (snippet immagine o testo grezzo).
- **Fallback obbligatorio** a review umana se confidence < soglia o se validazione strutturale fallisce.
- **File originali conservati** insieme all'hash per duplicate detection e audit.

### Validazioni automatiche post-estrazione

- Somma parziali periodi == score finale.
- Goal events totali == score finale per squadra.
- Roster senza duplicati nello stesso team.
- Home team ≠ Away team.
- Match lookup fuzzy contro anagrafiche esistenti (squadre, atleti, arbitri).
- Deduplica: stesso match non può essere pubblicato due volte; proposta merge manuale.

### Convergenza con il Referto Digitale

OCR e Referto Digitale producono lo stesso contratto dati JSON e passano per lo stesso workflow di validazione. Un match con referto digitale nativo NON rifà OCR; un match con solo cartaceo passa per OCR e poi per review umana come sempre.

### Ordine di modifica della pipeline OCR

Chi tocca la pipeline OCR deve rispettare l'ordine: **schema.py → ocr_service.py → converters.py → test e fixtures**. Modificare il converter senza prima aggiornare lo schema (o viceversa) crea disallineamenti tra contratto JSON e normalizzazione, con KO silenziosi sui referti reali. Le fixture di test vanno aggiornate solo dopo che il contratto è stabile, mai prima.

### Monitor integrità — falsi positivi strutturali

`DataIntegrityService.check_league_standings(league)` confronta la classifica persistita con quella **attesa**, dove "attesa" è un placeholder a zero per ogni squadra iscritta alla lega, **indipendentemente dai match giocati**. Conseguenza: una lega con N squadre iscritte e zero `MatchReport` in stato `PUBLISHED` produce sempre N segnalazioni `MISSING_RECORD` finché un rebuild non popola i placeholder. Non è un bug — è il comportamento atteso del check — ma genera mail dal monitor (`2salti-monitor.timer`) che sembrano allarmi e non lo sono. Prima di trattare un alert come problema, verificare quanti match `PUBLISHED` ha la lega segnalata: se sono zero, l'alert è strutturale.

## 9.1 AI Stats Engine

Scopo: fornire un'interfaccia di ricerca e analisi basata su AI che integri la navigazione esistente con risposte dinamiche in linguaggio naturale.

### Stato implementazione: v0 vs v1

- **v0 (presente in produzione)**: endpoint query→risposta statico, log query in `AIQueryLog`, matching atleta basico, calcolo statistiche aggregate via `stats_services.py`. Nessun contesto multi-turn, nessun function calling.
- **v1 (roadmap)**: chatbot interattivo con history conversazione, hybrid mode redirect/direct answer, function calling con whitelist comandi, RBAC enforcement server-side per query private. Quanto descritto nei paragrafi seguenti è il target v1, non l'implementazione attuale.

### Funzionamento HYBRID MODE

1. **Existing Page Match (Redirect)**: se la query mappa su una pagina esistente (classifiche, profilo atleta, top scorer, scheda squadra), il sistema restituisce un breve riepilogo e un link diretto alla pagina.
   - Esempio: "top scorer this season" → "Marco Rossi è il miglior marcatore con 42 gol" + CTA "Vedi classifica completa marcatori".

2. **AI Response Mode (Direct Answer)**: se nessuna pagina soddisfa la query, il sistema interroga direttamente il DB e genera una risposta testuale.
   - Esempio: "gol di Rossi nelle ultime 5 partite" → "Rossi ha segnato 7 gol nelle ultime 5 partite."

### Regole di sicurezza

- **Zero Hallucination**: solo dati reali dal database, mai inventati.
- **Explicit fallback**: se il dato non esiste, messaggio esplicito all'utente.
- **Ambiguity handling**: se la query è ambigua, il sistema chiede chiarimenti invece di indovinare.
- **RBAC enforcement**: stesso principio del Chatbot AI — mai restituire dati che l'utente non avrebbe diritto di vedere.

## 10. Modello dati e motore statistiche

Per evitare caos, il database deve riflettere entità reali e relazioni chiare.

### Entità core

- **Matches**: metadata (data, luogo, competizione, round, girone), stato workflow, link referto sorgente, score finale, score per periodo.
- **Teams**: anagrafica squadre, alias, storico per stagione.
- **Players**: anagrafiche atleti, storico appartenenza team per stagione.
- **Coaches**: anagrafica tecnici, storico squadre allenate.
- **Referees**: anagrafica arbitri, designazioni storiche.
- **Match_Events**: riga per ogni evento (gol, espulsione, cartellino, timeout, rigore), con timestamp/periodo, atleta, team.
- **Competitions / Venues**: entità di contesto per aggregare correttamente i dati.
- **Season** (entità di prima classe): identificativo stagione nel formato canonico `2025/2026` (validato sul pattern `AAAA/AAAA`, con secondo anno = primo + 1), `sport`, flag `is_current`. Sostituisce il CharField libero `League.season` come asse temporale del dominio. Distinta da `SeasonArchive` (cap. 13 / Macro 13), che resta l'archivio storico delle statistiche.
- **Validation_Logs**: storico di tutte le correzioni e revisioni manuali.

### 10.1 Modello stagione e tesseramento

> Decisione di prodotto **chiusa** (Sprint D, 2026-06-06). **Implementata** (dev 2026-06-11, live su prod 2026-06-12) — vedi [SYLLABUS](SYLLABUS.md) Macro 16.

Il dominio adotta la **stagione come asse** del tesseramento, non più le date libere:

- **Season come entità.** La stagione corrente è un flag `is_current` acceso a mano dall'admin, **per sport** (di norma le stagioni sono allineate tra sport), con al massimo una stagione corrente per sport. Sostituisce il calcolo lessicografico `order_by('-season')` oggi in `core/views.py`.
- **Membership per stagione.** `Membership` acquisisce un campo `season` esplicito (FK a `Season`) e una nuova chiave di unicità `(user, society, team, role, season)`. Spariscono `start_date`/`end_date`: l'appartenenza è ancorata alla stagione, non a un intervallo di date.
- **La lega è la fonte di verità grandi/giovanili.** Si elimina la `category` duplicata e contraddittoria su `Team`. Il tipo lega è una lista chiusa: `A1, A2, B, C, D` = "dei grandi"; `U10, U12, U14, U16, U18, U20` = giovanili. Le giovanili portano etichette tradizionali italiane come **display**, mappate 1:1 sul valore Under canonico (U12 = Esordienti, U14 = Ragazzi, U16 = Allievi, U18 = Juniores; U10 e U20 senza etichetta tradizionale assegnata).
- **Prestito strutturato.** Unica eccezione alla regola "una società per stagione", valida **solo** per squadre dei grandi (A1–D), mai giovanili. Il giocatore in prestito mantiene tesseramento e giovanili nella società d'origine. Constraint DB **rigido**: vietata una seconda società nella stessa stagione se la membership non è marcata come prestito. La membership di prestito porta il riferimento alla società di tesseramento e uno **stato (attivo/concluso) come semplice etichetta** — non una macchina a stati.

### Entità business

- **User_Accounts**: account applicativi con stato identità/subscription.
- **Subscriptions**: piani attivi (Freemium / Premium / Club Pro) con date e metodo pagamento.
- **Claim_Requests**: richieste di rivendica profilo sportivo.
- **Activation_Codes**: codici società per membership sportiva.
- **Shop_Orders**: log ordini intermediati dai webhook verso gli shop delle società.
- **Sponsor_Assets**: sponsor caricati dalle società, con placement (pagina società, profili atleti).
- **User_Preferences**: layout widget, tema colore, notifiche opt-in per ciascun utente Premium.
- **Jury_Tokens**: token match-specific emessi per i giurati certificati, con scadenza e stato revoca.
- **ChatMessage**: canale di chat informale per squadra (messaggistica diretta tra membri), complementare alla Bacheca (Post/Comment) che resta il canale strutturato.

### Principi di integrità

- Ogni statistica aggregata (top scorer, classifica, profilo atleta) deve poter essere ricalcolata da zero partendo dai Match_Events pubblicati.
- Nessun campo aggregato va scritto a mano senza che esista un job che lo può rigenerare.
- Unique constraints forti per evitare duplicati logici: un atleta non può comparire due volte nello stesso roster match; due squadre quasi uguali vanno riconciliate.

## 11. API, backend, infrastruttura e operations

Sopra l'interfaccia, in mezzo il layer applicativo, sotto il motore OCR/AI e il DB. Le API sono l'ossatura che alimenta sia il sito pubblico sia la futura app mobile.

### Endpoint principali

| Metodo + path | Funzione | Output |
| --- | --- | --- |
| POST /ai/query | AI Stats Engine (query linguaggio naturale) | answer/redirect + data |
| POST /api/referti/upload | Carica file cartaceo e crea job OCR | job_id + stato iniziale |
| POST /api/referti/process | Lancia OCR/AI sul job | stato elaborazione |
| POST /api/referti/digital/start | Crea un referto digitale nativo (giuria) | id referto + draft iniziale |
| PUT /api/referti/digital/{id} | Aggiorna il draft digitale (sync offline) | bozza salvata |
| POST /api/referti/digital/{id}/close | Firma PIN arbitro e chiude il referto | stato workflow + immutabilità |
| GET /api/referti/{id}/status | Stato workflow del referto | UPLOADED / EXTRACTED / ... |
| GET /api/referti/{id}/results | JSON estratto e warning (supporto Base/Avanzato) | payload per admin |
| PUT /api/referti/{id}/validate | Correzione e approvazione admin | stato aggiornato |
| GET /api/matches | Lista partite con filtri | match list |
| GET /api/players/{id} | Profilo atleta | bio + season stats |
| GET /api/coaches/{id} | Profilo coach | record + storico |
| GET /api/referees/{id} | Profilo arbitro | designazioni + partite |
| GET /api/teams/{id} | Scheda squadra | rosa, stats, ultime gare |
| POST /api/media/upload | Caricamento foto/video Media Gallery (Premium) | media_id + tagging job |
| GET /api/ai/chatbot | Interfaccia Chatbot con function calling | bot_response + eventuali azioni |
| POST /api/jury/token/issue | Emissione token giuria match-specific | token + finestra validità |
| POST /api/shop/webhook | Outbound firmato HMAC verso shop società | delivery status |
| GET/PUT /api/user/preferences | Layout widget e tema utente Premium | preferenze persistenti |

### Infrastruttura e operations

La base tecnica già impostata su server Hetzner può restare il punto di partenza, ma va ordinata in moduli stabili:

- **Project root unico** e leggibile, con separazione chiara tra backend, modulo OCR, ingest email/WhatsApp e utility.
- **Log per ogni job di referto**, con errori, warning e tempi di esecuzione.
- **Storage originale dei file** con hash per duplicate detection.
- **Deploy disciplinato via GitHub**, con ambiente di test/staging prima del live.
- **Monitoring** code di sync offline, webhook shop, push notifications e pipeline OCR.
- **Storage media** (foto/video gallery) su bucket con CDN e lifecycle policy per archiviazione.
- **Backup** DB e media automatici, con procedura di restore testata.

## 12. Grafica del sito e regole UX

La grafica di 2salti deve sembrare sportiva ma non caotica, moderna ma non giocattolo. La sensazione giusta è quella di una piattaforma dati affidabile, con energia sportiva e leggibilità prima di tutto.

### Direzione visiva

- **Palette**: primaria basata su blue + navy, con teal, orange e green come colori funzionali.
- **Card**: arrotondate, sfondi molto puliti, ampio respiro tra moduli.
- **Tipografia**: titoli grandi e netti; testo secondario più morbido, mai grigio troppo scarico.
- **Grafici**: pochi ma chiari; tabelle pulite, con varianti card su mobile.
- **Dark mode**: coerente, non improvvisata — contrasto alto, stessi componenti, stessi spazi.

### Widget Layout System

Dashboard utente e Pagina Società sono costruite su un sistema a **slot fissi riordinabili**, NON drag&drop libero stile Canva. Ogni utente Premium e ogni società Club Pro può:

- Riordinare l'ordine dei widget disponibili.
- Nascondere i widget non interessanti.
- Applicare un tema colore (default 2salti + varianti con i colori della squadra seguita).

Le preferenze sono persistite per utente in `user_preferences`. La personalizzazione Premium è un override dei profili default per ruolo definiti al Cap. 7.1 — non un disegno da foglio bianco.

### Regole UX da tenere fisse

- Ricerca e cambio tema sempre accessibili nell'header.
- Da guest e da utente loggato il sito deve essere riconoscibile come la stessa piattaforma, ma con gerarchie e moduli diversi: da pubblico scoperta e consultazione; da autenticato azione, personalizzazione e strumenti.
- Ogni pagina dati deve mostrare contesto: stagione, competizione, data ultimo aggiornamento.
- Nessuna pagina pubblica deve sembrare rotta quando il dato manca: usare stati vuoti curati e copy chiaro.
- Filtri semplici, visibili e coerenti tra partite, classifiche e statistiche.
- AI search bar sempre visibile nell'header o nella sidebar.
- Risposte AI con breakdown opzionale dei dati sorgente.

## 13. Modello di business (Three-Tier)

Il modello economico si basa su tre piani paralleli che sbloccano diverse profondità di utilizzo. Sostituisce il precedente piano unico a ~0,50 EUR/mese.

| Piano | Prezzo Guida | Target | Feature Chiave |
| --- | --- | --- | --- |
| **Freemium** | Gratis | Utente base | Pagine pubbliche, claim profilo, lettura bacheca società |
| **Premium Utente** | Mensile (TBD) | Famiglie, Atleti, Tifosi | Chatbot AI, Live Alerts push, Media Gallery upload, Season Recap, Dashboard widget personalizzata |
| **Club Pro** | Mensile (TBD) | Società / Club | Scrittura Bacheca + push a iscritti, Shop vetrina, gestione Sponsor, Pagina Club personalizzata |

### Chi paga cosa / chi riceve cosa

- **Utente Premium**: paga per servizi avanzati personali (Alerts, Chatbot, Gallery, Season Recap, personalizzazione).
- **Società (Club Pro)**: paga per visibilità (Sponsor, pagina società), gestione operativa (Shop vetrina) e comunicazione diretta (Bacheca push).
- **Giuria certificata**: utilizzo del Referto Digitale sempre gratuito, via token match-specific emesso dalla federazione/lega.
- **Fruizione contenuti**: la lettura della bacheca e la consultazione dati base restano gratis per tutti gli utenti iscritti alla società (anche Freemium). Le notifiche push sulla bacheca arrivano solo ai Premium.

### Funnel di attivazione

1. Registrazione account base (email + password o OAuth).
2. Verifica identità personale (SPID/CIE primario; fallback documento + selfie per stranieri, minorenni, casi speciali).
3. Selezione piano: Freemium (gratis) attivato subito; Premium o Club Pro richiedono pagamento.
4. Claim del profilo sportivo (ricerca profilo e richiesta di possesso).
5. Accesso squadra tramite codice fornito dal club o richiesta manuale notificata al club admin.
6. Approvazione finale e sblocco delle aree private.

### Priorità di esecuzione

1. **Nucleo affidabile del dato**: Referto Digitale (form mobile, offline, PIN), OCR fallback, validazione, database e profili sportivi pre-caricati.
2. **Modulo account**: registrazione, SPID/CIE, fallback documento, pagamento tre piani.
3. **Claim e membership**: ricerca profilo, codici di attivazione, notifiche al club admin, approvazioni e revoche.
4. **Area pubblica robusta e dashboard private** per ruoli verificati, con distinzione netta tra guest, Freemium, Premium e Club Pro.
5. **Crescita**: nuovi sport oltre la pallanuoto, mobile/PWA, analytics più profonde, integrazioni future.

## 14. Decisioni immediate da bloccare (Baseline v3)

- **Referto Digitale**: via principale di ingestione. OCR come fallback per cartaceo e archivio storico.
- **Three-Tier Pricing**: Freemium / Premium Utente / Club Pro. Prezzi puntuali TBD, da validare con campione di famiglie e società.
- **Widget Layout**: sistema a slot fissi riordinabili per dashboard utente e pagine club. Niente drag&drop libero in v1.
- **Chatbot AI**: esclusiva Premium, con function calling e RBAC server-side obbligatorio.
- **Bacheca mista**: scrittura gated Club Pro, lettura gratis per tutti gli iscritti, notifiche push solo Premium.
- **Shop vetrina**: webhook outbound firmato HMAC o email strutturata verso lo shop società. Nessun checkout diretto in-app. 2salti è intermediario, non venditore.
- **Certificazione giuria**: token match-specific con finestra 30 minuti pre-match, revoca automatica al fischio finale, revoca manuale admin disponibile.
- **Firma referto**: PIN arbitro rende il referto immutabile post-firma; correzioni successive solo via admin con audit log completo.
- **AI Tagging Media Gallery**: detection automatica + coda di review manuale; opt-in esplicito per minorenni, opt-out disponibile per ogni atleta.
- **Profili sportivi creati dal sistema**: gli utenti non creano da zero il proprio profilo sportivo, lo rivendicano.
- **Verifica identità**: SPID/CIE primario; fallback documento + selfie / video-selfie per casi eccezionali.
- **Accesso dati privati**: richiede SEMPRE entrambe le condizioni — identità verificata + membership sportiva approvata.
- **Multi-sport by design**: pallanuoto è il primo rollout, non il limite. Naming, navigazione, design system, dominio devono restare estendibili ad altri sport.

---

## Punti da validare con il product owner

- **[Federazione]** ✅ **RISOLTO (2026-06-02):** l'autorità emittente dei token giuria è la **federazione/lega** (NON il club). Conferma §7.4.1 e §14 (Baseline); vedi SYLLABUS Macro 14 §14.2.
- **[Conflitti]** ✅ **RISOLTO (2026-06-02):** conflict resolution = single-writer lock per match (un solo device writer-attivo alla volta; NON last-write-wins, NON merge). Vedi SYLLABUS Macro 14 §14.3.
- **[Shop]** SLA del webhook verso società: quante ore di retry? Notifica admin club in caso di failure?
- **[UX]** Opzione "sito esterno": Redirect diretto (Opzione A) vs Pagina teaser con badge (Opzione B).
- **[Gallery]** Moderazione contenuti: Segnalazione automatica o dashboard manuale Club Admin?
- **[Chatbot]** Function calling aperto (Opzione A) vs Lista chiusa whitelist comandi (Opzione B).
- **[Privacy]** Season Recap minorenni: Opt-in richiesto per generazione PDF o solo per condivisione?
- **[Identity]** Chi valida manualmente i documenti nel fallback SPID (Documento+Selfie)? (2salti Staff / Club Admin?)

---

### Modifiche applicate in questa revisione (v3.3)

- **FIX 7.3**: Rimossa duplicazione interna delle regole di verifica e privacy; contenuto consolidato in un unico elenco puntato.
- **FIX 7.4 / 7.5 / 7.6**: Ripristinato il dettaglio operativo completo delle sotto-sezioni Referto Digitale (certificazione token, offline-first, PIN, livelli Base/Avanzato, form UX), Chatbot AI (function calling, RBAC server-side, audit log) e Media Gallery (pipeline AI, coda review, opt-in minorenni, opt-out atleti).
- **FIX Cap. 8**: Ripristinato dettaglio workflow editoriale (schermate, stati completi con transizioni, principi UX cockpit).
- **FIX Cap. 9**: Ripristinato dettaglio OCR (canali ingresso, pre-processing, confidence, raw evidence, validazioni automatiche) e convergenza con il Referto Digitale.
- **FIX Cap. 9.1**: Ripristinato dettaglio AI Stats Engine (hybrid mode, redirect/direct answer, regole sicurezza).
- **FIX Cap. 10**: Ripristinato inventario completo entità core e aggiunte entità business nuove (Subscriptions, Shop_Orders, Sponsor_Assets, User_Preferences, Jury_Tokens).
- **FIX Cap. 11**: Ripristinata tabella completa endpoint (15+ API) integrando i nuovi: media upload, chatbot, jury token issue, shop webhook, user preferences. Ripristinato paragrafo infrastruttura/operations con monitoring e backup.
- **FIX Cap. 12**: Ripristinato dettaglio direzione visiva (palette, card, tipografia, grafici, dark mode) + Widget Layout System + regole UX.
- **FIX Cap. 13**: Modello economico esteso con "Chi paga cosa", funnel attivazione e priorità di esecuzione.
- **FIX Cap. 14**: Decisioni bloccate ampliate con certificazione giuria, firma PIN, AI tagging, profili sportivi, verifica identità, multi-sport by design.

### Cronologia revisioni

- **v3**: Versione iniziale unificata (prodotto, pagine, OCR, dati, design system, architettura, roadmap).
- **v3.1**: Introdotti modello three-tier, Referto Digitale, Chatbot, Media Gallery, profili default per ruolo. Capitoli 8-14 inavvertitamente compressi a stub.
- **v3.2**: Ripristinata numerazione capitoli originale; aggiunto blocco "Punti da validare"; capitoli 8-14 parzialmente ricostruiti ma ancora incompleti.
- **v3.3**: Ripristino chirurgico completo dei capitoli 7.4-7.6 e 8-14 con contenuto operativo pieno. Consolidata sezione 7.3.
- **v3.4**: Risolti 2 punti da validare — [Federazione] issuer token giuria = federazione/lega; [Conflitti] sync multi-device = single-writer lock. Macro 14 (Referto Digitale) marcata 🧊 Differita nel syllabus per dipendenza esterna (accordo federale).
- **v3.5**: Modello stagione e tesseramento (Sprint D, deciso, non implementato) — `Season` promossa a entità di prima classe (formato `2025/2026`, `is_current` per sport), `Membership.season` + nuova unique key `(user, society, team, role, season)` in luogo di `start_date`/`end_date`, lega come fonte di verità grandi/giovanili (lista chiusa A1–D / U10–U20 con etichette tradizionali), prestito strutturato con constraint DB rigido (solo squadre dei grandi, riferimento società di tesseramento + stato attivo/concluso come etichetta). Vedi cap. 10.1 e syllabus Macro 16.