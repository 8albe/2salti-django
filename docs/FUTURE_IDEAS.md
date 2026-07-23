# FUTURE_IDEAS — Idee parcheggiate fuori dallo scope corrente

Creato il 2026-07-01, nel giro preparatorio della potatura documentale (restrizione dello scope a pallanuoto-only). Questo file è il parcheggio delle idee che escono dalla documentazione operativa: ogni voce spiega cos'era l'idea, perché è stata parcheggiata e cosa la riaprirebbe, così tra un anno il contesto si ricostruisce senza archeologia su git. Non è un backlog: niente priorità, niente task. I riferimenti a sezioni di BLUEPRINT/SYLLABUS sono citazioni storiche — le sezioni citate verranno rimosse o riscritte dalla potatura; il testo integrale resta recuperabile dalla history git.

---

## 1. Eliminato dallo scope (mai costruito — esisteva solo in documentazione)

Le prime quattro voci sotto non hanno una riga di codice, un modello o una migration: erano solo pianificazione. Verificato nell'inventario read-only del 2026-07-01 (grep su modelli, viste, migration, requirements). La quinta (minuti giocati) è stata aggiunta il 2026-07-02 in chiusura della Macro 4: anche lei mai costruita. La sesta (statistiche avanzate del referto digitale) e la settima (Jury Token federale) sono state aggiunte il 2026-07-19 su feedback/risposta federale: anche loro mai costruite.

### Shop vetrina / Shop_Orders / webhook HMAC
Era la vetrina prodotti delle società con pulsante "Richiesta Materiale": nessun checkout in-app, 2salti faceva da intermediario inoltrando l'ordine allo shop della società via webhook outbound firmato HMAC (o email strutturata), con log degli ordini in una entità `Shop_Orders`. Parcheggiata perché mai costruita e perché il suo valore dipende da un sistema-società maturo e da accordi commerciali coi club che oggi non esistono; restavano aperti anche i punti SLA/retry del webhook. La riaprirebbe una domanda reale delle società paganti per l'intermediazione del materiale. (Storico: BLUEPRINT v3.x §2, §3, §10, §13, §14.)

### Media Gallery + AI tagging
Era lo spazio multimediale della partita: upload foto/video riservato ai premium, pipeline di face detection con match automatico sul roster ufficiale del match, coda di review per evitare mis-tagging, gallery pubblica sul profilo atleta con opt-in esplicito del genitore per i minorenni e opt-out sempre disponibile per l'atleta. Parcheggiata perché mai costruita e sproporzionata rispetto al nucleo dati: richiede storage bucket+CDN con lifecycle policy, una pipeline AI dedicata e decisioni pesanti su privacy e moderazione (segnalazione automatica vs dashboard manuale, mai decisa). La riaprirebbero una base utenti attiva che genera contenuti e il budget per lo storage. (Storico: BLUEPRINT v3.x §7.6; SYLLABUS Macro 11.)

### Modello Venue / Impianto
Era l'entità autonoma per gli impianti sportivi: oggi il luogo della partita è solo `Match.location`, un CharField libero, e l'idea era promuoverlo a modello per aggregare partite per impianto e profilarli. Parcheggiata perché mai costruita: era l'unico task rimasto aperto della macro classifica, già rimandato per scelta "a quando serviranno dati reali", e ora esce dallo scope. Nota tecnica per il futuro: è l'unica voce di questa sezione che comporterebbe schema-change e migration. La riaprirebbe un bisogno reale di navigazione per impianto emerso coi dati veri. (Storico: BLUEPRINT v3.x §10; SYLLABUS Macro 3, task residuo. Scheda di dettaglio tecnico: [SYLLABUS Macro 20](syllabus/20_venue_impianto.md).)

### Genesi società via calendario di lega (dipendenza FIN)
Era il modello a regime per la nascita delle società sulla piattaforma: le partite di una stagione esistono già programmate (import del calendario federale) e da lì si estraggono le società personificabili — le società "nascono" dal calendario, non dai referti. Parcheggiata perché l'import calendario non esiste a codice e presuppone un accordo con la federazione (FIN) che non c'è; nel frattempo le società nascono come oggi, da referti OCR o seed mirato (es. Zero9 seminata a mano). La riaprirebbe l'accordo federale sull'accesso ai calendari — a quel punto andrebbe riletta insieme alla voce "Jury Token federale" (in questa stessa sezione), che dipendeva dallo stesso interlocutore ed è stata eliminata il 2026-07-19 su risposta federale negativa. (Storico: BLUEPRINT v3.x §1, "Strategia di rollout a imbuto".)

### Minuti giocati per atleta
Era la metrica "minuti giocati" nel profilo pubblico dell'atleta, accanto a gol, presenze ed espulsioni. Parcheggiata perché mai costruita e bloccata a monte: richiede eventi di sostituzione SUB_IN/SUB_OUT che il modello Match_Events non traccia (oggi elenca solo gol, espulsione, cartellino, timeout, rigore) — modellare le sostituzioni è il prerequisito. La riaprirebbe l'aggiunta degli eventi sostituzione a Match_Events con il relativo calcolo dei minuti. (Storico: SYLLABUS Macro 4, task residuo.)

### Statistiche avanzate pallanuoto (livello Avanzato del referto digitale)
Era il secondo livello di compilazione del referto digitale, a scelta della giuria accanto al livello Base (gol, cartellini, espulsioni, timeout, parziali): palombelle, contropiedi, rigori causati, parate e simili. Accantonata su feedback federale raccolto alle finali nazionali U18 (2026-07): la federazione conferma che queste statistiche non vengono rilevate nemmeno in Serie A — non esiste quindi una fonte reale del dato, e il principio del Dato Certo vieta di inventarla. La riaprirebbe una rilevazione reale da parte di giurie/federazione (o di rilevatori dedicati a bordo vasca). (Storico: BLUEPRINT §7.4.3; SYLLABUS Macro 14.)

### Jury Token federale (identità giuria emessa dalla FIN)
Era il modello di accesso al referto digitale della Macro 14: token match-specific legato a `match_id`+`user_id` emesso dalla federazione/lega, finestra di validità 30 minuti pre-match, revoca automatica al fischio finale, ruolo utente `jury` dedicato in `User.role`. Eliminato il 2026-07-19 su risposta federale diretta: le designazioni delle giurie sono gestite dal **GUG, organo nazionale**, e comunicate via mail attraverso il portale federale, che **non sarà reso accessibile a terzi** perché gestisce i dati personali dei tesserati FIN — l'anagrafica su cui l'intero modello si fondava non è ottenibile. Mai implementato (nessuna riga di codice). Sostituito dal **link monouso per-partita** (SYLLABUS Macro 14 §14.2; BLUEPRINT §7.4.1), che identifica la partita e non la persona. La riaprirebbe un accordo con la FIN che fornisse **identità federate senza esporre dati personali** (es. verifica di un ID tessera via API, senza accesso all'anagrafica). (Storico: BLUEPRINT v3.x §7.4.1, §10, §11, §13, §14; SYLLABUS Macro 14 §14.1–14.2 pre-riscrittura.)

---

## 2. Visione multi-sport (parcheggiata — non prima di 2-3 anni)

2salti è nato come "hub multi-sport": il blueprint dichiarava la pallanuoto "primo sport di rollout, non il limite del prodotto" e imponeva architettura, naming, navigazione e design system pensati come framework replicabile su altri sport. Con la restrizione di scope del 2026-07 il prodotto diventa **pallanuoto-only**: tutta la pianificazione multi-sport esce dalla documentazione operativa (visione, roadmap, copy, naming "estendibile").

**Nota tecnica vincolante, da non dimenticare:** il database resta tecnicamente predisposto. Il modello `Sport` (con `point_system`, `period_label`, `hex_color`) e le sue FK vive sotto `League`, `Team`, `Season` e `SportEventConfig` restano **intatti nello schema** — nessuna rimozione dal codice, nessuna migration di smantellamento. Su `Sport` ci sono migration recenti applicate in produzione (`core/0020`/`0021`, deploy `24bfc62` del 2026-06-30). La potatura multi-sport è **solo documentale**: lo sport navigator in `base.html` resta a codice e si auto-nasconde quando un solo sport ha leghe, comportamento già by-design.

Cosa riaprirebbe la visione: un prodotto pallanuoto consolidato (dati reali, società paganti a regime) più una domanda concreta da un secondo sport. Lo schema dormiente rende la ripartenza tecnica poco costosa; UX, naming e posizionamento di prodotto andrebbero invece riprogettati da capo, perché la potatura documentale ne rimuove ogni traccia.

---

## 3. Differito per dipendenza esterna (roadmap viva, non abbandono)

### Referto digitale giuria completo (Jury App) — SBLOCCATA E RIENTRATA IN ROADMAP (2026-07-19)
Questa voce è **uscita dal parcheggio**: la risposta federale del 2026-07-19 ha chiuso la dipendenza esterna, in negativo (le designazioni sono del GUG nazionale e il portale federale non sarà accessibile a terzi — nessuna anagrafica FIN), e la Macro 14 è stata riscritta sul modello a **link monouso per-partita**, progettabile e costruibile senza accordo federale. Vedi SYLLABUS Macro 14 (stato 🔄) e BLUEPRINT §7.4.1. L'unico pezzo morto — il modello a **Jury Token federale** — è archiviato in §1. Con la FIN resta un'unica question aperta (la consegna del link, §14.2), che non blocca la costruzione. Questa voce resta qui solo come traccia storica del periodo di differimento (2026-06-02 → 2026-07-19).

---

## 4. Statistiche abilitate dalla semantica rigori/espulsioni (dato GIÀ sul cartaceo)

Repository di idee di prodotto, senza etichette di stato. A differenza delle
"Statistiche avanzate pallanuoto" del §1 (palombelle, contropiedi, parate: **nessuna
fonte reale**, la federazione non le rileva nemmeno in Serie A → il Dato Certo vieta di
inventarle), queste **hanno già la fonte**: sono scritte sul referto cartaceo standard e
oggi vengono semplicemente **scartate** in estrazione. Con la semantica `is_penalty`
introdotta il 2026-07-22 (prompt OCR V3.1 + `MatchEvent.is_penalty`) il dato entra nel
sistema e queste metriche diventano derivabili a valle, senza rilevazione aggiuntiva a
bordo vasca.

### Statistiche rigori
Dalla lettura della storia cronometrica (espulsione con `is_penalty` = fallo che comporta
un rigore; gol `type=GOAL` con `is_penalty` = rigore realizzato; espulsione `is_penalty`
senza gol allo stesso clock+periodo = rigore sbagliato/parato):

- **Rigori causati** per giocatore/squadra (chi commette il fallo da rigore).
- **Rigori ottenuti** per squadra (rigori concessi a favore).
- **Rigori segnati** e **rigori sbagliati/parati** per giocatore/squadra.
- **Percentuale di realizzazione** (segnati / ottenuti) per giocatore, squadra, stagione.

L'accoppiamento rigore↔gol è una **regola derivata** (stesso clock+periodo), non un campo
estratto: si calcola a valle, non si chiede al modello OCR. Prerequisito già soddisfatto:
`is_penalty` su gol ed espulsioni nella pipeline. Manca solo l'aggregazione statistica e
la sua esposizione nel percorso stats (`matches/stats_services.py`).

### Conteggio "fouled out" (3 espulsioni)
A regolamento, alla **terza espulsione** un giocatore è fuori per tutta la partita. È uno
stato di gioco reale, non solo un check di plausibilità, e segnala indisciplina o durezza
difensiva. Metriche:

- **Fouled out per giocatore/partita**: se e quante volte un giocatore raggiunge le 3.
- **Fouled out per giocatore/stagione**: in quante partite è uscito per falli.
- **Fouled out per squadra**: frequenza aggregata.

Derivato dalla lista espulsioni (regola, non estrazione): base già implementata in
`matches/event_types.py` (`fouled_out_players`, soglia `FOUL_OUT_EXCLUSIONS=3`) ed esposta
in `get_fouled_out_stats` (percorso stats lega). Estensioni naturali: viste per-atleta e
per-stagione, e il flag "uscito per falli" nel timeline della singola partita.

Cosa riaprirebbe/allargherebbe: dati reali a regime (più referti con eventi riconciliati) e
una decisione UX su dove mostrarli (profilo atleta, pagina lega, timeline partita).

### Qwen3-VL come secondo lettore decorrelato nel cross-check

Il cross-check misurato in §8.20 accoppia gemini-2.5-pro e gemini-3.6-flash: 0 concordi-e-sbagliati su 8 errori, su 6 referti. Il metodo funziona perché i due modelli sbagliano in punti diversi, e il suo unico punto cieco sono gli errori commessi da entrambi.

Pro e Flash appartengono però alla stessa famiglia e allo stesso addestramento: i loro errori sono verosimilmente più correlati di quelli di due modelli di fornitori diversi. Sui 6 referti del gold la correlazione non è emersa, ma il campione è troppo piccolo per escluderla. Un secondo lettore di famiglia diversa dovrebbe restringere il punto cieco.

Qwen3-VL (Alibaba, Model Studio) è l'unico candidato non-Google architetturalmente compatibile: è un VLM generalista che sa produrre output strutturato, quindi si innesta nell'architettura a provider già esistente (che ospitava OpenAI prima della migrazione a Gemini). Gli OCR specializzati (Mistral OCR, DeepSeek-OCR, GLM-OCR) sono invece esclusi: restituiscono testo o markdown, non il JSON con semantica di dominio (is_penalty, articolo EDCS, clock per periodo, roster per calottina), e senza gli stessi campi il confronto campo-per-campo del cross-check non è possibile.

Costo della valutazione: quasi nullo. Alibaba Cloud Model Studio dà ~70M token gratuiti per 90 giorni sull'endpoint Singapore, sufficienti a misurare Qwen sul gold senza spesa. Il lavoro è la scrittura del provider nel bench.

PREREQUISITO NON NEGOZIABILE: valutazione privacy prima di qualunque chiamata con referti reali. I referti contengono nomi e cognomi di atleti potenzialmente minorenni, e l'endpoint è extra-UE. La valutazione va fatta prima della misura, non dopo.

Sequenziamento: viene dopo il test dello zero-autori su Flash, perché quel test decide se il lettore primario resta Pro o diventa Flash, e quindi quale posto Qwen andrebbe a occupare.
