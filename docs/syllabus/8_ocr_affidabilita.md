## 8. OCR — Perfezionamento e affidabilità

Stato: 🔄 In corso

Miglioramento accuracy, preprocessing, gestione errori, dataset test, qualità dati estratti.

### 8.1 Pipeline esistente

- [x] **Provider OCR ratificato (2026-07-09): Gemini unico e definitivo, modello `gemini-2.5-pro`.** Scelto dopo bench su referti reali a grafia difficile (il più accurato; latenza ~90s accettabile perché l'OCR gira in background). OpenAI **rimosso** dal codice/test/deps OCR; il seam provider (`BaseVisionProvider` + factory `OCRService` + `OCR_PROVIDER`) resta per future estensioni. Filone "scelta provider OCR" **chiuso**.
- [x] Provider astratto (`vision_providers.py`), `GeminiVisionProvider` in prod, mock in test
- [x] Quality gate (`ocr_quality_gate.py`) pre-EXTRACTED
- [x] Dedup via SHA-256 (`hash_service.py`)
- [x] Raw response salvata (campo `MatchReport.raw_api_response`) per audit
- [x] Workflow stati referto completo (UPLOADED → PROCESSING → EXTRACTED → VALIDATED → PUBLISHED + branch NEEDS_REVIEW/REJECTED)

### 8.2 Affidabilità da migliorare

- [x] **Dataset gold standard — struttura creata il 2026-07-19** in [docs/ocr_gold_standard/](../ocr_gold_standard/) (un file JSON per referto verificato in `cases/`, schema e procedura nel `README.md`). Prima riga: il match 3 dell'11/04/2026. Aggancio `ocr_bench --gold-case` fatto (vedi aggiornamento 2026-07-20 sotto).
  - **Aggiornamento 2026-07-20: harness di misura sul gold standard costruito** (`ocr_bench --gold-case <case_id>` / `--gold-all`, dettaglio d'uso nel [README del dataset](../ocr_gold_standard/README.md) §"Uso da ocr_bench"). Confronto per campo e mai aggregato con esito ternario correct/wrong/null (null conteggiato a parte), check esplicito di inversione casa/trasferta, nomi contro `name_on_paper`, confidence auto-dichiarata accostata a ogni verdetto, metadati di run (modello, hash del prompt, preprocessing, timestamp). **Decisione D1**: il bench produce file di *proposta* in `ocr_bench_out/gold/` (gitignorata), mai scritti in `extractions[]` — il riversamento nel dataset resta un atto umano dopo review. Read-only su DB e pipeline; provider mockato nei test (`tests_ocr_bench.py`). **Run di baseline contro Gemini non ancora eseguito** (costo API, lo lancia Alberto). Vincolo operativo: su **dev** è presente la sola immagine del caso Bellator (`referto_1.jpeg`, report 16, byte-identica a `reale_03` del report 10); le cinque `reale_0X` dei report 7, 8, 10, 11, 15 esistono solo su prod (`/opt/2salti-new/media/match_reports/`) — serve un sync media prod→dev (azione di Alberto) prima di un `--gold-all` completo su dev; i due casi senza report a DB (S.C. Salerno 18/04, Trisceloni 25/04) richiedono comunque `--image` esplicito.
  - **Aggiornamento 2026-07-19: dataset a 5 casi.** Aggiunti 4 referti collazionati a mano (punteggio e parziali soltanto; roster/eventi/ufficiali in `not_verified`), tutti stagione 2025/2026: Olympic Roma P.N. vs Libertas Roma Eur (12/04, 20-1), Unime vs Nautilus Roma (28/03, 12-10), Nautilus Nuoto Roma vs Trisceloni Etna Sport (25/04, 20-12), S.C. Salerno vs Nautilus Nuoto Roma (18/04, 12-17). Nessuna estrazione OCR associata (`extractions: []`): pronti per il bench, non ancora fatti girare. Verifica DB soggetti nuovi: 'Trisceloni Etna Sport' e 'S.C. Salerno' **assenti** sia da Team sia da Society (confermato sul sistema vivo) — un loro referto andrebbe orfano per assenza reale, non per fallimento fuzzy matching (§8.6). 'Olympic Roma P.N.' presente ma con divergenza di grafia a DB ('Olimpic Roma P.N.', stesso pattern del caso Bellator/Frosinone in §8.6).
  - **Aggiornamento 2026-07-19 (secondo giro, stesso giorno): censimento + correzione su dev.** Censimento read-only su dev e prod (identici): 4 Match totali, 4 `is_finished`, 4 con punteggio valorizzato, **0 con un report mai `PUBLISHED`** — l'intera popolazione match è a rischio, non solo i 3 casi noti (dettaglio §8.5(d)). 0 `LeagueStanding` non a zero: nessun dato errato ha ancora raggiunto la classifica, perché `StandingsService` filtra su `reports__status='PUBLISHED'`. Confermate sul sistema vivo le due discrepanze: match Olympic/Libertas (id 4) con parziali sbagliati a DB nonostante il finale giusto; match Unime/Nautilus (id 2) con casa/trasferta invertiti a DB (nuova classe di errore, §8.5(e)). **Corrette su dev** (transazione + audit `MATCH_SCORE_CORRECTED`, `is_data_verified=True`, `rebuild_standings --verify` + `check_data_integrity` puliti su entrambe le leghe). **Prod non toccato**, correzione preparata non eseguita. `normalized_data` dei report 8, 10, 11, 16 non toccato: non pubblicarli finché non corretto separatamente (nota operativa in §8.5).
  - **Aggiornamento 2026-07-19 (terzo giro, stesso giorno): dataset a 6 casi, popolazione match chiusa al 100% di errore.** Verificato a mano il quarto e ultimo referto cartaceo disponibile (match 1, Pol. Delta vs Villa York, 06/12/2025, lega 2, report 7): finale 15-9 corretto a DB, **tutti e quattro i parziali sbagliati** (veri 6-2 / 1-2 / 3-4 / 5-1), verità corroborata dalla storia cronometrica del referto (§8.5(f)). Con questo **tutti e 4 i match a DB risultano sbagliati: 4/4** e il controllo "somma parziali == finale" li attraversa tutti — **0% di rilevazione su 100% di errore** (§8.5(d)). Corretto su dev con lo stesso rigore (transazione + audit, `is_data_verified=True`, rebuild lega 2 + `check_data_integrity` puliti); backfill anche di `has_report`, incoerente per una causa applicativa registrata e **non** corretta (§8.5(g)). **Prod non toccato**: sequenza consolidata delle 4 correzioni preparata a parte.
  - Caso motivante: lo stesso match (Bellator Frusino vs SS. Lazio Nuoto, 11/04/2026) ha **due estrazioni divergenti sul punteggio finale** — report 10 (`gpt-4o`): 11-19; report 16 (`gemini-2.5-pro`): 5-19. La verità umana, collazionata sul cartaceo il 2026-07-19, è **4-19**: sbagliano **entrambe**. Il gold standard serve a **due scopi distinti**: (1) misurare l'accuratezza per campo; (2) verificare la calibrazione della confidence per tarare la soglia del quality gate.
  - Nota (2026-07-19): Mistral OCR 4 registrato come provider candidato da benchmarcare contro `gemini-2.5-pro` con `ocr_bench` sul dataset gold quando sarà costruito — nessuna implementazione ora.
- [x] **Gate del risultato pubblico (2026-07-19)** — la pagina pubblica non mostra il risultato di una partita non verificata: `is_data_verified=True` OPPURE almeno un referto `PUBLISHED`, altrimenti placeholder al posto di finale e parziali (la partita resta pubblica). Gate unico in `matches/services/result_visibility.py`, consumato da template, API pubbliche e AI Stats Engine; staff e admin continuano a vedere il punteggio. Decisione di prodotto in [BLUEPRINT.md](../BLUEPRINT.md) §14, dettaglio in §8.5(h).
- [ ] Gestione multi-page PDF: concatenazione pagine prima dell'estrazione
- [ ] Metriche qualità: success rate per campo, tempo medio upload→publish
- [x] Cluster E KO residui — guardia early-return in `ocr_service.py:254` che cortocircuita exception path per NEEDS_REVIEW
- [x] Cluster D KO residui — verifica `MatchReportUploadForm.clean()` interroga davvero `MatchReport.objects.filter(file_hash=…)`

### 8.3 Match Report Workflow

- [x] Modello `MatchReport` + `MatchReportAuditLog` con 8 stati (UPLOADED → PROCESSING → EXTRACTED → VALIDATED → PUBLISHED + branch NEEDS_REVIEW/REJECTED/DRAFT)
- [x] Service `publishing_service.py`: `publish_report()` con depublish/republish come rami interni (non funzioni standalone)
- [x] Guardrails pre-publish (blockers + warnings) in `schema.py` (`OCRSchemaValidator.assess_publish_readiness`) + guardrail "0 eventi con score positivo → abort" inline in `publishing_service.py`
- [x] Audit log per ogni transizione (utente, timestamp, diff, motivo) — vedi STATE_MACHINES.md §1
- [x] Convergenza referto cartaceo (FILE) e digitale (DIGITAL) sul ramo VALIDATED → PUBLISHED

### 8.4 Email Ingestion

- [x] Modello `InboundEmail` con deduplication idempotente via RFC822 message-id
- [x] Parser email e creazione `MatchReport` con `source_type=EMAIL`
- [x] Command `ingest_emails` per pull manuale/schedulato

### 8.5 Finding del primo caso gold standard (2026-07-19)

Primo referto collazionato a mano contro il cartaceo originale: match 3, Bellator Frusino vs SS. Lazio Nuoto, 11/04/2026. Dati completi in [docs/ocr_gold_standard/cases/](../ocr_gold_standard/cases/2026-04-11_bellator-frusino_vs_ss-lazio-nuoto.json).

**(a) Verità umana 4-19 (parziali 1-3, 0-5, 3-6, 0-5): hanno sbagliato entrambi i provider.**

| | punteggio | parziali corretti | note |
|---|---|---|---|
| **Verità (cartaceo)** | **4-19** | — | 1-3 / 0-5 / 3-6 / 0-5 |
| `gemini-2.5-pro` (report 16) | 5-19 | 2 su 4 | punteggio casa +1 |
| `gpt-4o` (report 10) | 11-19 | 0 su 4 | punteggio casa +7; è il dato che stava a DB |

Il punteggio trasferta (19) è corretto in entrambe, quello di casa in nessuna delle due: l'errore non si distribuisce a caso. Il dato errato a DB (11-19, dalla vecchia estrazione `gpt-4o`) è stato corretto su dev il 2026-07-19 con audit `MATCH_SCORE_CORRECTED`.

**(b) LIMITE del controllo somma-parziali: gli errori compensativi lo attraversano.**

In **entrambe** le estrazioni sbagliate la somma dei parziali torna esattamente al totale dichiarato:

- `gemini`: 1+0+3+1 = 5 ✓ e 3+5+5+6 = 19 ✓ → totale 5-19, coerente e falso
- `gpt-4o`: 2+4+2+3 = 11 ✓ e 2+5+4+8 = 19 ✓ → totale 11-19, coerente e falso

Non è un bug del controllo: è un **limite concettuale**. "Somma parziali == punteggio finale" (BLUEPRINT §9) verifica la *coerenza interna* dell'estrazione, non la sua *verità*, e un modello che sbaglia a leggere una griglia tende a sbagliarla in modo internamente consistente — proprio perché deriva il totale dalla stessa lettura. Il controllo passa su dati falsi per costruzione, non per caso.

Cosa serve, in alternativa o in aggiunta:

1. un **controllo indipendente**, che usi una seconda fonte dentro il referto: il conteggio degli eventi-gol per periodo deve tornare col parziale di quel periodo. È indipendente perché legge un'altra zona del foglio (la lista marcatori, non la griglia dei parziali);
2. in mancanza, accettare esplicitamente che **solo la review umana discrimina** e non lasciare che il gate strutturale verde venga letto come "dato attendibile".

**(c) Confidence 1.0 su valore errato: fuorviante, non solo scalibrata.**

Entrambi i provider hanno dichiarato `confidence_fields.final_score = 1.0` sul punteggio **sbagliato**. `gpt-4o` ha inoltre dichiarato `quarters = 0.9` con quattro parziali su quattro errati. Non è rumore di calibrazione: è un segnale che punta nella direzione opposta alla realtà. Qualunque soglia sul quality gate che si fidi di `confidence_fields` promuoverebbe questi due referti a `EXTRACTED` con la massima fiducia. **La confidence auto-dichiarata non è utilizzabile come criterio di gating** finché il gold standard non dimostra il contrario su un campione ampio.

**(d) Errori compensativi: 4 su 4, l'intera popolazione dei match a DB (2026-07-19, terzo giro).**

Con la verifica del quarto e ultimo referto cartaceo disponibile (match 1, Pol. Delta vs Villa York, 06/12/2025), **tutti e quattro i match esistenti a DB hanno dati sbagliati: 4/4, il 100% della popolazione.** In tutti e quattro la somma dei parziali a DB torna esattamente al finale dichiarato mentre i parziali stessi sono sbagliati:

| Match | Finale a DB | Parziali a DB | Somma torna? | Corretto? |
|---|---|---|---|---|
| 1 — Pol. Delta/Villa York | giusto (15-9) | tutti e 4 sbagliati (vero 6-2/1-2/3-4/5-1) | 5+4+3+3=15, 2+2+1+4=9 ✓ | dev 19-07, **prod 20-07** |
| 2 — Unime/Nautilus | giusto nei due totali, **squadre invertite** | tutti e 4 sbagliati | 3+2+4+3=12, 2+3+3+2=10 ✓ | dev 19-07, **prod 20-07** |
| 3 — Bellator/Lazio | sbagliato (11-19, vero 4-19) | tutti e 4 sbagliati | 2+4+2+3=11, 2+5+4+8=19 ✓ | dev 19-07, **prod 20-07** |
| 4 — Olympic/Libertas | giusto (20-1) | tutti e 4 sbagliati | 5+5+5+5=20, 0+0+0+1=1 ✓ | dev 19-07, **prod 20-07** |

Tutti e quattro sono stati corretti **anche su prod il 2026-07-20** (OPS_RUNBOOK §2.7), con audit `MATCH_SCORE_CORRECTED` per match e `is_data_verified=True`, quindi il risultato è di nuovo pubblico attraverso il gate (h).

**La statistica che conta: il controllo strutturale "somma parziali == finale" ha un tasso di rilevazione dello 0% su una popolazione con tasso di errore del 100%.** Quattro match sbagliati, zero segnalati. Non è un controllo debole da tarare meglio: su questa classe di errore è **inutile per costruzione**, perché il modello deriva parziali e totale dalla stessa lettura (o ricostruisce i parziali a partire dal totale). Un controllo che non può fallire non può nemmeno rilevare — vedi (b) per le alternative indipendenti.

Il campione resta piccolo (4 casi), ma non è più un campione: è la popolazione intera.

**Conferma dal vivo del limite, su un caso non costruito (2026-07-20).** Durante la correzione dei quattro match su prod (OPS_RUNBOOK §2.7) il blocco del **match 4 è stato saltato** per un errore di copia-incolla. `rebuild_standings --verify` e `check_data_integrity` sono passati **puliti sul dato ancora sbagliato**, perché i parziali vecchi (`5-0 / 5-0 / 5-0 / 5-1`) sommavano comunque a 20-1. L'omissione è stata intercettata **solo** dall'asserzione finale contro i valori collazionati a mano sul cartaceo.

Il valore di questo episodio è che non è una dimostrazione costruita: è il finding (b)/(d) che si manifesta spontaneamente, in condizioni operative reali, su un errore di *procedura* invece che di *estrazione*. La stessa proprietà — coerenza interna che regge mentre la verità è sbagliata — protegge un OCR che allucina e un blocco di checklist mai eseguito. Se ne ricava anche una regola operativa generale, registrata in OPS_RUNBOOK §6.5: in una procedura manuale a blocchi la rete non sono i controlli di coerenza, ma l'asserzione finale contro valori esterni noti in anticipo.

**Corollario (ipotesi con n=4, non legge): il totale è il campo più affidabile, i parziali il meno affidabile.** Il punteggio finale è corretto in 3 casi su 4 (match 1, 2, 4 — nel match 2 i due totali sono giusti, solo attribuiti alla squadra sbagliata), mentre i parziali sono sbagliati in 4 su 4. Se regge su più casi, ha una conseguenza operativa concreta: la review umana va concentrata sui parziali, e i parziali non andrebbero trattati come dato pubblicabile senza collazione. Da riverificare a ogni nuovo caso gold prima di trasformarla in una regola.

**(e) Nuova classe di errore: INVERSIONE CASA/TRASFERTA (match 2, 2026-07-19).**

Il match Unime vs Nautilus Roma (28/03/2026) aveva a DB **le squadre scambiate**: `home_team=Nautilus (12)`, `away_team=Unime (10)`, mentre il cartaceo dice il contrario — ospitante Unime, vincitore 12-10. I due punteggi totali (12 e 10) erano entrambi presenti e corretti, solo attribuiti alla squadra sbagliata. **Nessun controllo aritmetico può rilevare questa classe di errore**: la somma dei parziali torna, il totale torna, tutti i numeri sono quelli giusti — cambia solo *a chi* sono assegnati. La conseguenza pratica è che falsa il vincitore e quindi, se il referto venisse pubblicato, i punti in classifica (3 punti alla squadra sbagliata). Corretto su dev il 2026-07-19 scambiando le FK `home_team`/`away_team` insieme a punteggio e parziali nella stessa transazione (recon preventivo: zero `MatchEvent` e zero `Convocation` collegati a quel match, quindi nessun effetto collaterale su altre tabelle); **stessa correzione applicata su prod il 2026-07-20**, con verifica browser che la pagina pubblica mostri Unime come squadra di casa.

**Ipotesi da verificare, non conclusione:** il pattern dei parziali sbagliati sul match 4 (`5-0 / 5-0 / 5-0 / 5-1` a DB) ha una regolarità sospetta — tre quarti identici e il quarto che assorbe il resto — che potrebbe essere una firma di allucinazione (il modello "inventa" una distribuzione plausibile invece di leggere davvero la griglia) piuttosto che un errore di lettura genuino. Da tenere d'occhio sui prossimi casi gold, non abbastanza dati per concludere su un solo campione.

**(f) Corroborazione incrociata sul foglio: la storia cronometrica come seconda fonte (match 1, 2026-07-19).**

Sul match 1 la verità dei parziali (6-2 / 1-2 / 3-4 / 5-1) non viene da una sola lettura: è confermata dalla **storia cronometrica** del referto, la sequenza dei gol col minuto, che dà la progressione 6-2 → 7-4 → 10-8 → 15-9 e coincide con i cumulati dei parziali collazionati. È una zona del foglio **indipendente** dal riquadro dei parziali, compilata separatamente durante la gara: la concordanza non è una ricopiatura, è una conferma. Regola metodologica per i casi futuri: quando le due zone concordano la fiducia nella `truth` è più alta di una singola lettura; quando divergono il caso va marcato e non chiuso. È anche la conferma pratica che la strada indicata in (b)-1 esiste davvero sul foglio.

**(g) Flag `has_report` incoerente sul match 1 (dato corretto, causa applicativa aperta).**

Il match 1 aveva `has_report=False` pur avendo il report 7 collegato. Causa: `Match.has_report` viene scritto **solo** nei percorsi di upload/creazione (`matches/views.py:163` upload con match noto, `:591` referto digitale, `:647` creazione match da OCR) e **non** nei due percorsi che collegano un referto a una partita *a posteriori* — `link_match` (`matches/views.py:361`) e l'auto-aggancio di `MatchDiscoveryService` (`matches/services/ocr_service.py:380`). Entrambi fanno `report.match = ...; report.save()` senza toccare il flag sul `Match`. Con l'asincrono (Macro 22) la discovery è il percorso *normale*, quindi l'incoerenza è sistematica, non un caso isolato: ogni referto agganciato dalla discovery lascia il match con `has_report=False`. Impatto: `matches/views.py:647` e `core/services/dashboard_service.py:203` filtrano su questo flag, quindi il match risulta invisibile in quelle viste. Su dev è stato fatto il **backfill del solo dato** (audit `MATCH_HAS_REPORT_BACKFILLED`); gli altri 3 match non ne sono affetti. **La logica applicativa non è stata toccata**: la correzione naturale è derivare il flag dal collegamento invece di replicarlo (proprietà `has_report` calcolata su `self.reports.exists()`, come già fa `is_public`) oppure scriverlo nei due percorsi mancanti — decisione da prendere a parte.

**(h) PRIMA DIFESA CONCRETA: gate del risultato pubblico (ratificato 2026-07-19).**

I finding (a)-(g) dicono cosa non funziona; questa è la prima contromisura che *cambia il comportamento del prodotto*, non solo la documentazione. Decisione di prodotto ratificata da Alberto e registrata in [BLUEPRINT.md](../BLUEPRINT.md) §14: **la pagina pubblica non mostra il risultato di una partita i cui dati non sono verificati.**

- **Criterio (uno solo, niente terza definizione di "verificato"):** il risultato è mostrabile se `is_data_verified=True` **oppure** se esiste almeno un referto `PUBLISHED`. Le due strade sono la validazione umana diretta — il campo `is_data_verified`, che fino al 2026-07-19 era **morto** (dichiarato nel modello, zero usi in view/template/queryset) e che le correzioni di oggi hanno iniziato a valorizzare — e il workflow di pubblicazione del referto, cioè lo stesso criterio già usato da `StandingsService` per le classifiche.
- **Cosa si nasconde:** punteggio finale e parziali. **Cosa resta pubblico:** la partita, con squadre, data, luogo e competizione. Il match esiste, è il risultato a non essere certo.
- **Chi continua a vedere:** staff e admin, su tutte le pagine, con un badge esplicito "dato non verificato". Nascondere il punteggio a chi deve verificarlo sarebbe autolesionista.
- **Dove vive:** `matches/services/result_visibility.py`, unico punto di verità, consumato da template (`{% load match_visibility %}`), API pubbliche e AI Stats Engine. Il gate copre anche l'AI: un motore che risponde in linguaggio naturale è una porta di servizio come le altre, e oggi conta i gol solo su match il cui risultato è pubblico.
- **Perché ora:** con il 100% della popolazione a DB sbagliata (finding (d)), pubblicare un punteggio non verificato significa pubblicare, statisticamente, un punteggio sbagliato. È l'applicazione diretta di "Null invece di invenzione" (BLUEPRINT §1) e del Principio del Dato Certo (§7.4.3): il principio non copre solo il dato *mancante* ma anche quello *non ancora verificato*.
- **Cosa il gate NON risolve:** le classifiche leggono `LeagueStanding` persistito, che non ricontrolla la pubblicazione a lettura (dipende dal rebuild); e i tre punti di questo elenco restano indipendenti dal gate — `normalized_data` sbagliato, `has_report` (g), duplicati anagrafici (§8.7).

Il censimento dei punti di esposizione è stato fatto in modo esaustivo prima dell'implementazione (lezione dallo stato `QUEUED`: 7 punti rotti su 14 perché nessuno li aveva enumerati) e il test `TemplateScoreExposureAuditTest` in `matches/tests_result_visibility.py` **deriva** la lista dai template invece di elencarla a mano: un nuovo template che stampa un punteggio senza gate fa fallire la suite da solo.

**Nota operativa: non pubblicare i report 7, 8, 10, 11, 16.** Questi cinque report hanno `normalized_data` con punteggio e/o attribuzione casa/trasferta sbagliati, non ancora corretti (giro separato, fuori scope Macro 8 attuale). La correzione applicata finora — su dev il 2026-07-19 e su prod il 2026-07-20 — ha toccato solo il `Match`, non il report.

> **Aggiornamento 2026-07-20.** Su prod tutti e cinque sono ora in `NEEDS_REVIEW`: il report 16, che era in `EXTRACTED` (cioè a un click dalla pubblicazione), è stato **demosso a `NEEDS_REVIEW` con audit** all'inizio della finestra di deploy, prima di ogni altra operazione, proprio per togliere di mezzo il rischio durante il lavoro. Il `normalized_data` non è stato toccato: la demozione allontana il pericolo, non lo rimuove. Non esiste tuttora **alcun guardrail a codice** che impedisca la pubblicazione — la protezione è documentale, registrata come debito in OPS_RUNBOOK §10.22. Se uno di questi report venisse pubblicato o ripubblicato, `publish_report()` (`matches/services/publishing_service.py`) sovrascriverebbe `Match.home_score`/`away_score`/`quarter_scores` (e, per match 2, ricreerebbe gli eventi con l'attribuzione squadra ancora sbagliata) leggendo dal `normalized_data` non corretto — vanificando silenziosamente la correzione appena fatta.

### 8.6 Finding di discovery: nome sul cartaceo ≠ nome a DB

L'OCR legge `BELLATOR FROSINONE` (com'è scritto sul referto cartaceo), mentre a DB la squadra è registrata come **`Bellator Frusino`** (Team pk=5). Il fuzzy matching di `match_discovery` non le riconcilia: il referto 16 è finito orfano (`match=None`) e in `NEEDS_REVIEW` con "Impossibile risolvere una o entrambe le squadre", **pur esistendo la squadra a DB**.

È un problema di **Macro 8 (discovery/riconciliazione), non di Macro 22**: l'asincrono si è limitato a renderlo visibile al primo upload reale. Genera orfani sistematici, non occasionali, perché la divergenza è stabile nel tempo — ogni referto di quella squadra fallirà allo stesso modo finché il matching non gestisce gli alias.

Direzione da valutare (nessuna implementazione in questo giro): tabella di alias per squadra/società, alimentata proprio dai casi di discovery fallita, invece di alzare la tolleranza del fuzzy matching — che sui nomi di società brevi produrrebbe falsi positivi.

### 8.7 Duplicato anagrafico Lazio (registrato, non riconciliato)

Presente **sia su dev sia su prod**, identico:

| Team pk | Nome | Society pk | Lega |
|---|---|---|---|
| 6 | `SS. Lazio Nuoto` | 6 | 4 — Allievi nazionali U16A |
| 12 | `S.S. Lazio Nuoto` | 12 | 6 — serie B/C |

Due `Society` distinte per quella che è verosimilmente la stessa società reale, con due grafie diverse (`SS.` vs `S.S.`). Le due squadre sono in **leghe diverse**, quindi la coesistenza non è di per sé un errore di dati — una società può avere più squadre in campionati diversi. L'anomalia è a livello di **Society**: sono due anagrafiche per lo stesso ente.

Conseguenze pratiche: la discovery può agganciare la squadra sbagliata su un referto ambiguo, e qualunque aggregato per società (statistiche, profili, sponsor, entitlement) conta due entità dove ce n'è una. **Nessuna riconciliazione effettuata** — richiede una decisione di prodotto su quale anagrafica sopravvive e una data migration con merge delle FK.

### 8.8 Report 15: orfano in `UPLOADED`, mai elaborato (censito 2026-07-20)

Emerso guardando la lista referti in admin durante il deploy §2.7 e verificato a DB in sola lettura. **Non era nel censimento del 2026-07-19**, che copriva i cinque report collegati ai quattro match (7, 8, 10, 11, 16).

Stato reale su prod: `status=UPLOADED`, `match=None` — è l'**unico referto orfano** a DB — con file allegato presente (`source_channel=FILE`), `normalized_data` **vuoto**, `ocr_attempts=0` e `ocr_queued_at`/`ocr_started_at` a `None`. Creato il 2026-04-19. In breve: **caricato e mai elaborato**, non un'estrazione andata male.

Due cose lo rendono interessante oltre al censimento in sé:

1. **Non partirà da solo.** `UPLOADED` non è `QUEUED`, e l'accodamento è esplicito per disegno (Macro 22). Nessun processo lo raccoglierà: né il worker, che consuma `QUEUED`, né il backstop `recover_stale_reports`, che guarda `PROCESSING`. Non compare nemmeno in nessuno dei tre segnali di coda di `ops_check`. È un **punto cieco della strumentazione**, non un malfunzionamento — ma è il tipo di dato che resta fermo per mesi senza che nulla lo dica, come infatti è successo per tre mesi.
2. **È il candidato naturale per il collaudo end-to-end mancante** dell'asincrono su prod (Macro 22 §As-built giro 3): un file reale, già a sistema, non collegato a nessun match, quindi accodarlo non rischia di sovrascrivere dati corretti. Se poi il referto risultasse collazionabile sul cartaceo, diventerebbe anche il settimo caso gold.

Anomalia minore rilevata nello stesso censimento: `in_review_at` è valorizzato (2026-04-19) pur essendo lo stato `UPLOADED` — residuo di una transizione passata, incoerente con lo stato attuale.

**Non toccato**: non accodato, non collegato, non eliminato. La decisione è di prodotto; registrato anche in OPS_RUNBOOK §10.23 perché non se ne perda traccia.

---

← [Macro precedente](7_profilo_fan.md) | → [Macro successiva](9_sistema_sponsor.md)
