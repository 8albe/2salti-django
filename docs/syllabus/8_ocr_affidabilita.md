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
  - **Aggiornamento 2026-07-20: harness di misura sul gold standard costruito** (`ocr_bench --gold-case <case_id>` / `--gold-all`, dettaglio d'uso nel [README del dataset](../ocr_gold_standard/README.md) §"Uso da ocr_bench"). Confronto per campo e mai aggregato con esito ternario correct/wrong/null (null conteggiato a parte), check esplicito di inversione casa/trasferta, nomi contro `name_on_paper`, confidence auto-dichiarata accostata a ogni verdetto, metadati di run (modello, hash del prompt, preprocessing, timestamp). **Decisione D1**: il bench produce file di *proposta* in `ocr_bench_out/gold/` (gitignorata), mai scritti in `extractions[]` — il riversamento nel dataset resta un atto umano dopo review. Read-only su DB e pipeline; provider mockato nei test (`tests_ocr_bench.py`). **Run di baseline contro Gemini eseguito il 2026-07-20** (finestra costi aperta da Alberto): risultati in §8.9. Vincolo operativo (chiuso il 2026-07-20): il sync media prod→dev delle cinque famiglie `reale_0X` è stato eseguito da Alberto — su dev ora ci sono tutte le immagini, byte-identiche a prod; il caso Triscelon 25/04 (senza report a DB, grafia corretta dal 2026-07-20, era "Trisceloni") richiede comunque `--image` esplicito.
  - **Aggiornamento 2026-07-19: dataset a 5 casi.** Aggiunti 4 referti collazionati a mano (punteggio e parziali soltanto; roster/eventi/ufficiali in `not_verified`), tutti stagione 2025/2026: Olympic Roma P.N. vs Libertas Roma Eur (12/04, 20-1), Unime vs Nautilus Roma (28/03, 12-10), Nautilus Nuoto Roma vs Triscelon Etna Sport (25/04, 20-12 — squadra ospite "Triscelon", corretto dal 2026-07-20, era trascritta "Trisceloni"), S.C. Salerno vs Nautilus Nuoto Roma (18/04, 12-17). Nessuna estrazione OCR associata (`extractions: []`): pronti per il bench, non ancora fatti girare. Verifica DB soggetti nuovi: 'Triscelon Etna Sport' e 'S.C. Salerno' **assenti** sia da Team sia da Society (confermato sul sistema vivo) — un loro referto andrebbe orfano per assenza reale, non per fallimento fuzzy matching (§8.6). 'Olympic Roma P.N.' presente ma con divergenza di grafia a DB ('Olimpic Roma P.N.') — **riverificata e CONFERMATA reale il 2026-07-20** (§8.6): non era l'errore di collazione temuto dopo il caso Bellator.
  - **Aggiornamento 2026-07-19 (secondo giro, stesso giorno): censimento + correzione su dev.** Censimento read-only su dev e prod (identici): 4 Match totali, 4 `is_finished`, 4 con punteggio valorizzato, **0 con un report mai `PUBLISHED`** — l'intera popolazione match è a rischio, non solo i 3 casi noti (dettaglio §8.5(d)). 0 `LeagueStanding` non a zero: nessun dato errato ha ancora raggiunto la classifica, perché `StandingsService` filtra su `reports__status='PUBLISHED'`. Confermate sul sistema vivo le due discrepanze: match Olympic/Libertas (id 4) con parziali sbagliati a DB nonostante il finale giusto; match Unime/Nautilus (id 2) con casa/trasferta invertiti a DB (nuova classe di errore, §8.5(e)). **Corrette su dev** (transazione + audit `MATCH_SCORE_CORRECTED`, `is_data_verified=True`, `rebuild_standings --verify` + `check_data_integrity` puliti su entrambe le leghe). **Prod non toccato**, correzione preparata non eseguita. `normalized_data` dei report 8, 10, 11, 16 non toccato: non pubblicarli finché non corretto separatamente (nota operativa in §8.5).
  - **Aggiornamento 2026-07-19 (terzo giro, stesso giorno): dataset a 6 casi, popolazione match chiusa al 100% di errore.** Verificato a mano il quarto e ultimo referto cartaceo disponibile (match 1, Pol. Delta vs Villa York, 06/12/2025, lega 2, report 7): finale 15-9 corretto a DB, **tutti e quattro i parziali sbagliati** (veri 6-2 / 1-2 / 3-4 / 5-1), verità corroborata dalla storia cronometrica del referto (§8.5(f)). Con questo **tutti e 4 i match a DB risultano sbagliati: 4/4** e il controllo "somma parziali == finale" li attraversa tutti — **0% di rilevazione su 100% di errore** (§8.5(d)). Corretto su dev con lo stesso rigore (transazione + audit, `is_data_verified=True`, rebuild lega 2 + `check_data_integrity` puliti); backfill anche di `has_report`, incoerente per una causa applicativa registrata e **non** corretta (§8.5(g)). **Prod non toccato**: sequenza consolidata delle 4 correzioni preparata a parte.
  - **Aggiornamento 2026-07-21: riparazione dei `normalized_data` eseguita su dev (Opzione A, prerequisito 2).** I cinque report 7/8/10/11/16 hanno avuto `normalized_data.scores` (più la sola `match_info.date` del report 11, 2025-04-12 → 2026-04-12) riportati ai valori gold, in un'unica transazione con audit `normalized_data_repair_gold` (before/after dei soli campi toccati; `raw_extracted_data` e status invariati, restano `NEEDS_REVIEW`). **Solo dev; prod gated a parte.** Effetto **voluto e misurato**: dopo la riparazione gli **eventi restano incoerenti coi punteggi per costruzione** — il gold copre punteggio e parziali, non gli eventi — quindi i blocker di `assess_publish_readiness` *aumentano* (da 8/2/3/2/1 a **7/7/7/4/5**) e il report 16 passa da verde a rosso. Chi legge `normalized_data` assumendo coerenza interna deve sapere che qui l'incoerenza è attesa: il check ora misura la distanza dalla verità, non la coerenza con l'errore. La divergenza dev↔prod sui parziali del report 16, prima non spiegata, è chiusa nel caso gold (due estrazioni Gemini indipendenti dello stesso cartaceo).
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

#### §8.5(b)-1 — IMPLEMENTATO (2026-07-21)

Il controllo del punto 1 esiste: `OCRSchemaValidator.check_goal_events_per_period` in `matches/services/schema.py`, funzione pura sul solo `normalized_data`. **Non legge `MatchEvent`**: alla proiezione a DB il periodo mancante viene forzato a 1 (`quarter or 1` in `publishing_service.py`), quindi un gol senza periodo diventa indistinguibile da un gol del primo tempo e il confronto darebbe un risultato inventato.

Il punto capitale è che **le due direzioni non sono simmetriche**, e trattarle allo stesso modo avrebbe reso il check inservibile: un eccesso è impossibile per costruzione, un difetto è la normale conseguenza di una cronologia letta solo in parte. Le decisioni ratificate da Alberto:

| | Caso | Al gate post-estrazione | Al publish |
|---|---|---|---|
| **D1** | **Eccesso**: più eventi-gol del parziale di quel periodo | **blocker** → `NEEDS_REVIEW` | **blocker** |
| **D2** | **Difetto con estrazione dichiaratamente completa**: la somma degli eventi-gol della squadra torna col suo finale, ma la distribuzione fra i periodi no | warning, **non declassa da solo** | **blocker** |
| **D3** | **Difetto con estrazione incompleta**: eventi-gol totali < finale | solo **evidenza** informativa | nessun blocco |
| **D4** | Hardening del prompt v2: il `quarter` di ogni evento va derivato dalla **sezione** della storia cronometrica, mai dal minuto e mai distribuito per far tornare i parziali. `null` resta ammesso e preferibile all'invenzione; il campo **non** diventa obbligatorio | — | — |
| **D5** | Correzione di framing in §8.11 (vedi lì) | — | — |
| **D6** | Tripla semantica: al gate il per-periodo sostituisce la variante aggregata **solo dove la domina davvero** — tutti i parziali leggibili e nessun gol privo di periodo, valutato **per squadra**; altrimenti l'aggregato resta attivo. Al publish **si affianca** all'uguaglianza stretta gol-eventi/finale, che resta un requisito a sé. *Perché condizionata e non secca: con la sostituzione secca un referto con gol senza periodo avrebbe perso anche la copertura aggregata, riducendo la difesa invece di aumentarla.* | — | — |

Due precisazioni che il codice rende esplicite e che sarebbe facile perdere:

- **La sostituzione D6 vale solo dove il per-periodo domina davvero.** Con tutti i parziali leggibili e ogni gol dotato di periodo, un eccesso sul totale implica un eccesso su almeno un periodo. Se però un parziale è illeggibile o qualche gol è privo di periodo, i gol possono "nascondersi" e la copertura non è più totale: in quel caso il controllo aggregato resta al suo posto per la squadra interessata. C'è un test di contro-prova.
- **Il difetto non è valutabile per una squadra che ha gol senza periodo**, e questo viene **dichiarato**, non taciuto: il check ha un esito esplicito `not_applicable` — per riga e complessivo — con il motivo. Un check che tace si legge come "tutto a posto", che è la falsa garanzia rimossa dalla fetta A1 (§8.11).

**Misure sui cinque referti reali di dev**, che sono anche le fixture statiche dei test (`matches/tests_ocr_period_coherence.py`; copie PII-free, non lette dal DB a runtime perché la riparazione dei `normalized_data` è il giro successivo):

| Referto | Esito per-periodo | Direzione |
|---|---|---|
| 7 | 4 periodi su 4 in eccesso | **D1** — 23 eventi-gol casa contro un finale di 15 |
| 8 | 2 periodi su 4 in difetto | D3 — casa completa e ben distribuita, ospite 8 gol su 10 |
| 10 | 3 periodi su 4 in difetto | D3 — entrambe le squadre incomplete |
| 11 | 4 periodi su 4 in difetto | D3 — 12 eventi-gol estratti su 21 |
| 16 | 4 periodi su 4 coerenti | **nessuno** — su parziali falsi (vedi §8.11) |

**In review** la tabella per-periodo è **evidenza per il revisore, etichettata coerenza interna e mai verifica di verità**: nessun highlight verde, nessun segno di conferma. Una tabella tutta pari non dice che i numeri sono giusti — il referto 16 lo dimostra — e un segnale positivo sarebbe esattamente la falsa garanzia che A1 ha rimosso.

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

**Decisione di prodotto ratificata (2026-07-21): la classifica resta a una sola strada, il gate del risultato pubblico no.** Durante la propagazione su prod del merge Lazio (§8.7, OPS_RUNBOOK §2.10) la verifica browser ha rilevato la lega 4 con la classifica interamente a zero pur avendo il match 3 concluso e `is_data_verified=True`. Recon read-only ha confermato che lo zero è preesistente e strutturale (nessun referto `PUBLISHED` su prod, vedi apertura di questo §8.5). Alberto ha esaminato il caso e **ratificato** — non lasciato per inerzia — il comportamento attuale di `StandingsService` (`reports__status='PUBLISHED'`, invariato dal codice): *"la classifica si aggiorna solo quando una partita è stata ufficialmente letta e confermata da un referto, e usando i dati che stanno sul referto."* Rifiutata esplicitamente la doppia strada del gate (h): `is_data_verified` **non deve mai diventare fonte per la classifica**, perché è un atto umano (una dichiarazione), mentre la classifica deve poggiare su un artefatto verificabile — il referto pubblicato — e sui dati che quel referto contiene. Conseguenza accettata consapevolmente, non un bug da correggere in UI aggirando il criterio: **l'asimmetria fra pagina match (risultato visibile via `is_data_verified`) e classifica (a zero) è per disegno** finché nessun referto è `PUBLISHED`. L'unica strada per popolare le classifiche resta correggere i `normalized_data` dei referti (giro già dichiarato in OPS_RUNBOOK §10.22) e pubblicarli — non un secondo criterio di lettura.

Il censimento dei punti di esposizione è stato fatto in modo esaustivo prima dell'implementazione (lezione dallo stato `QUEUED`: 7 punti rotti su 14 perché nessuno li aveva enumerati) e il test `TemplateScoreExposureAuditTest` in `matches/tests_result_visibility.py` **deriva** la lista dai template invece di elencarla a mano: un nuovo template che stampa un punteggio senza gate fa fallire la suite da solo.

**Nota operativa: non pubblicare i report 7, 8, 10, 11, 16.** Questi cinque report hanno `normalized_data` con punteggio e/o attribuzione casa/trasferta sbagliati, non ancora corretti (giro separato, fuori scope Macro 8 attuale). La correzione applicata finora — su dev il 2026-07-19 e su prod il 2026-07-20 — ha toccato solo il `Match`, non il report.

> **Aggiornamento 2026-07-20.** Su prod tutti e cinque sono ora in `NEEDS_REVIEW`: il report 16, che era in `EXTRACTED` (cioè a un click dalla pubblicazione), è stato **demosso a `NEEDS_REVIEW` con audit** all'inizio della finestra di deploy, prima di ogni altra operazione, proprio per togliere di mezzo il rischio durante il lavoro. Il `normalized_data` non è stato toccato: la demozione allontana il pericolo, non lo rimuove. Non esiste tuttora **alcun guardrail a codice** che impedisca la pubblicazione — la protezione è documentale, registrata come debito in OPS_RUNBOOK §10.22. Se uno di questi report venisse pubblicato o ripubblicato, `publish_report()` (`matches/services/publishing_service.py`) sovrascriverebbe `Match.home_score`/`away_score`/`quarter_scores` (e, per match 2, ricreerebbe gli eventi con l'attribuzione squadra ancora sbagliata) leggendo dal `normalized_data` non corretto — vanificando silenziosamente la correzione appena fatta.

**(i) Debito dichiarato: il caso Bellator è sotto la soglia di chiusura del dataset gold, ma il match resta pubblico su prod (2026-07-20).**

Lo stesso 2026-07-20 Alberto ha rivalutato `match.legibility.score` del caso Bellator da 2 a 1, dopo aver visto per confronto tutti gli altri cinque cartacei del dataset (correzione tracciata in `corrections[]` del caso gold, non un nuovo elemento letto sul foglio). Con score 1 il caso ricade sotto la regola del README del dataset (`docs/ocr_gold_standard/README.md` §"Leggibilità del foglio"): uno score 1 o 2 richiede `corroboration` per potersi considerare chiuso. Su questo referto la corroborazione — la storia cronometrica, seconda zona indipendente del foglio — è dichiarata esplicitamente **non ottenibile**, per le stesse ragioni di leggibilità (spaziature indecifrabili anche dopo riverifica). Il caso è quindi, secondo la regola interna del dataset, **formalmente non chiudibile**, pur avendo due letture umane indipendenti e concordi sui parziali (19/07 e 20/07 — vedi `reverification` nel caso gold).

Questo confligge con lo stato di produzione, e la tensione va **registrata, non sciolta qui**: il match 3 è marcato `is_data_verified=True` su prod e mostra pubblicamente 4-19 (finding (d) e (h) sopra) sulla base di questa stessa collazione. **Non si propone di cambiare il dato pubblico**: la doppia lettura umana concorde resta il grado di evidenza più alto disponibile per questo foglio, superiore a qualunque estrazione OCR — sarebbe un errore scambiare "il dataset gold non può chiudere questo caso" per "il dato pubblico è in dubbio". I due criteri misurano cose diverse: il criterio del dataset gold è il rigore della misura stessa (può un umano fidarsi di questa lettura come metro per giudicare i provider OCR?), il criterio di pubblicazione è il miglior dato disponibile per il prodotto (`is_data_verified=True`, §8.5(h)). Possono legittimamente restare divergenti — ma la divergenza deve restare visibile, non implicita.

Per confronto, sullo stesso foglio la maggioranza su 5 chiamate Gemini indipendenti sui parziali casa produce `1/0/2/2` (somma 5) contro la truth `1/0/3/0` (somma 4): il modello legge quella colonna in modo sistematicamente diverso dall'umano — un'ulteriore conferma indiretta che il foglio è al limite anche per un lettore automatico ripetuto, non solo per la prima collazione umana. Rilettura (2026-07-20): quel run è stato eseguito **prima** del fix del tie-break (`2f22b9d`); su `home_team_name` non c'era maggioranza stretta (FRUSINO ×2, FROSINONE ×2, FROSINO ×1), quindi con la regola corretta l'esito è **`ambiguo`**, non il `correct` stampato allora per tie-break silenzioso di prima comparsa.

### 8.6 Finding di discovery: due problemi distinti sui nomi squadra

> **Diagnosi chiusa il 2026-07-20** dopo la riverifica sul cartaceo di tutti i casi coinvolti (Bellator, Olympic, le due occorrenze Nautilus). Fino al giro precedente questo paragrafo era stato riscritto per un errore di collazione umana sul caso Bellator (dettaglio in fondo) e la direzione "tabella di alias" era stata sospesa in attesa di riverifica. La riverifica è arrivata: **esistono due problemi diversi, e vanno tenuti separati.**

**(a) Divergenza REALE di grafia foglio↔DB.** Confermata su due casi:

- `Olympic Roma P.N.` sul foglio (con la Y) vs `Olimpic Roma P.N.` a DB (Team pk=7). Riverificato da Alberto il 2026-07-20: invariato rispetto alla prima lettura.
- La stessa società (`Nautilus N. Roma` a DB, Team pk=3) compare con grafie diverse su fogli diversi, perché i referti sono compilati da segretari diversi: `Nautilus Roma` sul referto del 28/03 (dove la parola "Nuoto" non c'è proprio), `Nautilus Nuoto Roma` sui referti del 18/04 e del 25/04 (dove "Nuoto" c'è). Entrambe le grafie riverificate e confermate il 2026-07-20 — non era un'incoerenza del dataset, i fogli differiscono davvero.

Questi sono i casi **fondativi di una tabella di alias squadra/società**: un alias che mappa `Olimpic` ↔ `Olympic` o le varianti di `Nautilus N. Roma` risolverebbe la discovery su questi referti, perché la variante sul foglio è una grafia legittima, non un valore inventato.

**(b) Allucinazione OCR sul nome.** Caso Bellator (11/04): sul referto cartaceo c'è scritto **`BELLATOR FRUSINO`**, che coincide con il nome a DB (`Bellator Frusino`, Team pk=5) — riverificato una seconda volta il 2026-07-20, nessuna divergenza foglio↔DB. Entrambi i provider hanno però estratto **`BELLATOR FROSINONE`** (verificato in sola lettura su `normalized_data` di dev e prod: report 16 `gemini-2.5-pro`, report 10 `gpt-4o`), entrambi con `confidence_fields.home_team = 1.0`. Il referto 16 è finito orfano (`match=None`, `NEEDS_REVIEW`, "Impossibile risolvere una o entrambe le squadre") **pur esistendo la squadra a DB con il nome giusto**. `FRUSINO` è la forma latina di Frosinone e la parola `FROSINONE` compare altrove sullo stesso foglio (campo città): entrambi i modelli hanno normalizzato un nome proprio raro verso la forma comune più probabile — errore di prior linguistico, che il preprocessing non attenua e che la confidence auto-dichiarata non segnala. Aggravante di contesto: quel cartaceo è compilato molto male, al limite della leggibilità anche per un umano su valori e nomi (`match.legibility.score = 1` nel caso gold, rivalutato da 2 il 2026-07-20 — vedi §8.5(i)) — è la condizione in cui era nato anche l'errore di collazione umana del 19/07, poi corretto.

**Una tabella di alias NON risolve (b).** L'alias dovrebbe mappare un valore allucinato dal modello, non una grafia legittima alternativa: su Bellator non ci sarebbe nulla da mappare in anticipo. Il caso resta quindi **fuori dai casi fondativi della fase 3** e va sotto il problema separato dell'accuratezza OCR sui nomi propri, non della discovery.

Entrambi restano problemi di **Macro 8, non di Macro 22**: l'asincrono si è limitato a renderli visibili al primo upload reale. Entrambi sono sistematici, non occasionali: (a) si ripete a ogni referto della stessa società compilato dallo stesso segretario con la stessa grafia; (b) si ripete a ogni referto della stessa squadra, perché l'errore di prior linguistico non dipende dal singolo scan.

**Corollario sulla collazione stessa.** La riverifica di questo giro ha anche trovato un **secondo** errore di collazione, indipendente dal primo: nel caso del 25/04 la squadra ospite si chiama "Triscelon", non "Trisceloni" come trascritto il 19/07 (`case_id` e file rinominati, dettaglio nel caso gold). Due errori di collazione su sei casi, in due giorni diversi di riverifica, confermano che la regola del README ("il metro misura anche chi lo ha costruito") non è cautela teorica: la collazione umana su questi referti va sempre trattata come rivedibile, non come assioma.

#### Implementazione: tabella alias (C1) e discovery a `difflib` — 2026-07-21

I due problemi separati da questa diagnosi hanno ricevuto due fette **separate**, con test propri, deliberatamente non fuse in una.

**C1 — `core.TeamAlias`.** FK a `Team`, `alias` come scritto sulla fonte, `alias_normalized` derivata in `save()` e **unique**: da lì l'unicità case-insensitive e, gratis, l'unicità cross-team (lo stesso alias non può puntare a due squadre — sarebbe ambiguo per costruzione). Più origine, nota, autore e timestamp, perché fra sei mesi la domanda sarà "chi l'ha detto, e su quale foglio". La normalizzazione **delega** a `normalize_team_name`, la stessa della discovery: se le due divergessero, un alias inserito a mano smetterebbe di essere trovato dalla ricerca che dovrebbe servirlo. `resolve_team_entity` consulta gli alias in exact match **prima** del fuzzy — l'alias è l'unica fonte certa in quella funzione, il fuzzy indovina.

**Popolamento solo umano, e un test che lo tiene fermo.** Nessun percorso automatico scrive alias: non l'OCR, non la discovery, non il bench. Una guardia anti-ruggine scandisce il codice applicativo e fallisce se un modulo non-admin inizia a creare `TeamAlias`. La ragione è (b): mappare un'allucinazione significherebbe insegnare al sistema a fidarsene.

**Fetta separata — discovery da fuzzy posizionale a `difflib`.** `simple_similarity` confrontava i caratteri **alla stessa posizione**: una singola inserzione all'inizio disallineava tutto il resto. È il motivo per cui `Nautilus Roma` contro `Nautilus N. Roma` valeva **0.562** — sotto ogni soglia utile — pur essendo la stessa squadra. `SequenceMatcher` lavora su sottosequenze comuni:

| Nome estratto | Squadra a DB | posizionale | difflib |
|---|---|---|---|
| `Nautilus Roma` | Nautilus N. Roma | 0.562 | **0.897** |
| `Nautilus Nuoto Roma` | Nautilus N. Roma | 0.579 | **0.857** |
| `LIBERTAS ROMA EUR P.N` | Libertas Roma Eur | 0.810 | 0.895 |
| `Olympic Roma P.N.` | Olimpic Roma P.N. | 0.941 | 0.941 |

**Soglia: resta 0.80** — la fetta cambia la metrica, non la soglia, così l'effetto è isolato e attribuibile. Il valore è comunque misurato: sulla popolazione reale i veri positivi stanno fra 0.857 e 0.941, il falso positivo più alto è **0.606** (`Virtus Nuoto Roma` contro Nautilus N. Roma). La soglia cade in mezzo a una banda vuota larga 0.25. **Non allineata allo 0.6 del quality gate, deliberatamente**: le due soglie proteggono da rischi opposti. Il gate confronta il nome con una partita *già scelta da un umano*, e lì un falso negativo blocca un referto sano; la discovery invece *sceglie* la partita, e un falso positivo ne sovrascrive il punteggio. A 0.6 aggancerebbe proprio `Virtus Nuoto Roma` a Nautilus — l'allucinazione del report 15 che il collaudo su prod ha visto **non** agganciare (§8.10).

**Due fatti emersi scrivendo i test, che correggono ipotesi precedenti.**

1. **Il fuzzy posizionale risolveva già `Olympic` → Olimpic (0.941) e anche l'allucinazione `BELLATOR FROSINONE` → Bellator Frusino (0.833).** L'orfanità del report 16 non veniva quindi dal nome di casa, come si poteva leggere in (b): veniva quasi certamente dal lato **Lazio**, dove il duplicato anagrafico di §8.7 produce due punteggi pari e la funzione risponde `None` per ambiguità. Il valore dell'alias non è allora "rendere possibile l'impossibile" ma **rendere deterministico ciò che dipendeva da una soglia**: con l'alias la risoluzione non è più esposta a un cambio di soglia, all'arrivo di una squadra dal nome simile o al passaggio a un altro algoritmo.
2. **`difflib` rende risolvibile il duplicato Lazio, ma per uno scarto di 0.03** (`0.846` contro `0.815`). Cioè su un referto Lazio la discovery ora *risponde*, e la risposta è decisa da rumore fra due anagrafiche che sono la stessa società reale. Non è un aggancio spurio verso una squadra estranea — è l'ambiguità di §8.7 che si manifesta — e la cura è il merge (D1), non una soglia più alta: a qualunque soglia le due sono indistinguibili. Il fatto era fissato in un test, riscritto dopo l'esecuzione di D1 su dev (§8.7).

`simple_similarity` **resta in uso sulla riconciliazione atleti**, non toccata da questa fetta: i nomi di persona hanno una fenomenologia diversa (iniziali puntate, cognomi composti) e cambiare metrica anche lì va misurato a parte. Debito dichiarato, non dimenticanza.

### 8.7 Duplicato anagrafico Lazio — merge ESEGUITO SU DEV E PROD il 2026-07-21

Presente **sia su dev sia su prod**, identico:

| Team pk | Nome | Society pk | Lega |
|---|---|---|---|
| 6 | `SS. Lazio Nuoto` | 6 | 4 — Allievi nazionali U16A |
| 12 | `S.S. Lazio Nuoto` | 12 | 6 — serie B/C |

Due `Society` distinte per quella che è verosimilmente la stessa società reale, con due grafie diverse (`SS.` vs `S.S.`). Le due squadre sono in **leghe diverse**, quindi la coesistenza non è di per sé un errore di dati — una società può avere più squadre in campionati diversi. L'anomalia è a livello di **Society**: sono due anagrafiche per lo stesso ente.

Conseguenze pratiche: la discovery può agganciare la squadra sbagliata su un referto ambiguo, e qualunque aggregato per società (statistiche, profili, sponsor, entitlement) conta due entità dove ce n'è una. **Nessuna riconciliazione effettuata** — richiede una decisione di prodotto su quale anagrafica sopravvive e una data migration con merge delle FK.

**Aggiornamento 2026-07-21 — il problema si è aggravato con `difflib`, e la migrazione è preparata ma non eseguita.**

Col fuzzy posizionale un nome Lazio non raggiungeva la soglia e il referto restava orfano: sbagliato, ma *silenzioso e innocuo*. Con `difflib` (§8.6) la discovery **risponde**, scegliendo fra le due anagrafiche per uno scarto di **0.03** (`SS Lazio Nuoto` → `ss. lazio nuoto` 0.846 contro `s.s. lazio nuoto` 0.815). Il rischio descritto qui sopra in astratto è diventato concreto: la scelta è decisa da rumore. Non si cura alzando la soglia — a qualunque soglia le due grafie sono indistinguibili — si cura togliendo il duplicato.

**Recon (dev, sola lettura, 2026-07-21), che decide anche il verso del merge:**

| | Society 6 `SS. Lazio Nuoto` | Society 12 `S.S. Lazio Nuoto` |
|---|---|---|
| Slug | `SS_Lazio_Nuoto` | `ss-lazio-nuoto` (forma canonica) |
| `core.Team` | 1 (Team 6, lega 4 U16A) | 1 (Team 12, lega 6 B/C) |
| `management.Membership` | **0** | **14** |
| Altre FK entranti | nessuna | — |

**Merge 6 → 12: sopravvive la 12.** Non è arbitrario: è l'anagrafica viva (14 tesseramenti contro 0) e ha lo slug canonico. Spostare 14 tesseramenti per salvare uno slug è il verso sbagliato. Il fatto che sulla 6 non punti nient'altro che il suo Team è ciò che rende la `DELETE` innocua — e va **riverificato sull'ambiente bersaglio**, non dato per buono da questa tabella.

**Stato: ESEGUITO SU DEV il 2026-07-21, poi SU PROD lo stesso giorno.** Checklist a blocchi in `scratch/d1_merge_societa_lazio_20260721.sh` (untracked, si esegue un blocco alla volta) più il corpo della migrazione in `scratch/d1_merge_lazio_core.py`, **lo stesso codice** usato sia dal dry-run su copia scratch sia dall'esecuzione vera: il dry-run deve provare ciò che poi gira davvero, non una sua parafrasi. Cinque blocchi: gate sui parametri, recon sul posto, dry-run su copia con verifica dello SHA256 del DB reale, esecuzione in transazione unica con audit, asserzione finale contro valori noti in anticipo (OPS_RUNBOOK §6.5).

**Gate bloccante (sciolto il 2026-07-21): la grafia ufficiale del nome.** Il nome della società superstite era un **parametro non compilato** (`__DA_CONFERMARE__`) e il BLOCCO 1 si rifiutava di proseguire finché restava tale — verificato in entrambe le direzioni prima dell'esecuzione. Alberto ha confermato sulla fonte reale la grafia **`S.S. Lazio Nuoto`**, che coincide con quella già presente sulla Society 12: il passo di rinomina del core è quindi risultato un no-op, atteso e non un errore.

La grafia perdente non viene buttata: diventa un `TeamAlias` di origine `ANAGRAFICA` sulla squadra ri-puntata, così i referti già compilati con quella grafia continuano a risolvere.

**Esito su dev.** Society 6 eliminata (cascata vuota, come previsto dal recon); Team 6 ri-puntato sulla Society 12 e rinominato `S.S. Lazio Nuoto Allievi`; `TeamAlias` `SS. Lazio Nuoto` (origine `ANAGRAFICA`) → Team 6. Asserzione finale verde contro costanti fissate **prima** dell'esecuzione (§6.5 di OPS_RUNBOOK), inclusi gli invarianti che il merge non doveva toccare: 14 `Membership` sulla società superstite, 13 `Team` totali, i 3 alias fondativi C1 intatti. Suite `core matches management`: 670 OK, 2 skipped.

**Effetto misurato sulla discovery, e cosa NON è.** Sulla grafia `SS Lazio Nuoto`:

| | Allievi | Serie C | Scarto | Vincitore |
|---|---|---|---|---|
| Prima del merge | **0.8462** | 0.8148 | 0.0314 | Team 6 (Allievi) |
| Dopo il merge | 0.6286 | **0.8148** | 0.1862 | Team 12 (Serie C) |

Da distinguere due cose che è facile confondere. La prima è l'**irrobustimento**: lo scarto passa da rumore a segnale, e la risposta smette di dipendere da un punto e mezzo di differenza. La seconda è che **il vincitore cambia**: la stessa grafia che prima andava agli Allievi ora va alla Serie C. È l'effetto voluto — la scelta di prima era un accidente, non un giudizio — ma resta un cambiamento di **semantica**, non solo di robustezza, e va ricordato come tale quando si rileggeranno referti storici.

**L'alias pinna la grafia perdente sugli Allievi.** `SS. Lazio Nuoto` risolve ora su Team 6 per alias; su un referto di **serie C** con quella grafia risolverebbe quindi sulla squadra sbagliata. **Non è una regressione**: prima del merge quella grafia andava già al Team 6, per exact match sul nome. La differenza è di natura, non di esito — prima era un accidente dell'anagrafica duplicata, ora è un'**affermazione umana** registrata e riverificabile. Entrambi i fatti sono fissati in `matches/tests_team_similarity.py`, che il merge ha reso necessario riscrivere: `REAL_TEAMS` era hardcoded, quindi il test dell'ambiguità sarebbe rimasto **verde affermando un fatto ormai falso** — la stessa classe del quasi-incidente del PASSO 3d (OPS_RUNBOOK §2.7).

**Debito aperto (cosmetico, generale — non solo Lazio):** il merge lascia il Team 6 col suffisso di categoria (`S.S. Lazio Nuoto Allievi`) e il Team 12 senza (`S.S. Lazio Nuoto`, non `… Serie C`), mentre l'`help_text` del campo dichiara la convenzione "Society + tipo lega"; l'asimmetria è **preesistente e diffusa su tutte e 13 le squadre**, quindi va sanata in un giro dedicato su tutte o su nessuna, mai su una sola.

**Non è una data migration versionata, deliberatamente**: è una correzione anagrafica una-tantum su due pk specifici, non una regola che deve valere per ogni installazione. Come migration verrebbe ri-eseguita su ogni ambiente nuovo cercando pk che lì non esistono.

**Propagato su prod il 2026-07-21** (stesso corpo, stesso verso 6→12; dettaglio rituale in OPS_RUNBOOK §2.10). Baseline discovery su prod, stessa grafia `SS Lazio Nuoto`, stesso scarto misurato su dev perché i nomi di partenza erano identici nei due ambienti: **0.0313 prima del merge → 0.1862 dopo**.

**Su prod l'alias non è una cortesia, è load-bearing.** Il referto 16 (match 3) riconcilia il lato Lazio tramite l'alias `SS. LAZIO NUOTO` → Team 6: senza, `resolve_team_entity()` la cercherebbe solo per fuzzy contro il Team già agganciato al match (`[match.away_team]`, `ocr_service.py` r. 490), e il punteggio è **0.7692 < 0.80** — sotto soglia. La riconciliazione squadra/rosa lato Lazio del referto 16 non si aggancerebbe. Su dev nessun referto reale dipende da questo percorso, quindi lì l'alias è una rete di sicurezza non ancora esercitata; su prod è già la differenza fra un referto riconciliato e uno che non lo è.

### 8.8 Report 15: orfano in `UPLOADED`, mai elaborato (censito 2026-07-20)

Emerso guardando la lista referti in admin durante il deploy §2.7 e verificato a DB in sola lettura. **Non era nel censimento del 2026-07-19**, che copriva i cinque report collegati ai quattro match (7, 8, 10, 11, 16).

Stato reale su prod: `status=UPLOADED`, `match=None` — è l'**unico referto orfano** a DB — con file allegato presente (`source_channel=FILE`), `normalized_data` **vuoto**, `ocr_attempts=0` e `ocr_queued_at`/`ocr_started_at` a `None`. Creato il 2026-04-19. In breve: **caricato e mai elaborato**, non un'estrazione andata male.

Due cose lo rendono interessante oltre al censimento in sé:

1. **Non partirà da solo.** `UPLOADED` non è `QUEUED`, e l'accodamento è esplicito per disegno (Macro 22). Nessun processo lo raccoglierà: né il worker, che consuma `QUEUED`, né il backstop `recover_stale_reports`, che guarda `PROCESSING`. Non compare nemmeno in nessuno dei tre segnali di coda di `ops_check`. È un **punto cieco della strumentazione**, non un malfunzionamento — ma è il tipo di dato che resta fermo per mesi senza che nulla lo dica, come infatti è successo per tre mesi.
2. **È il candidato naturale per il collaudo end-to-end mancante** dell'asincrono su prod (Macro 22 §As-built giro 3): un file reale, già a sistema, non collegato a nessun match, quindi accodarlo non rischia di sovrascrivere dati corretti. Se poi il referto risultasse collazionabile sul cartaceo, diventerebbe anche il settimo caso gold.

Anomalia minore rilevata nello stesso censimento: `in_review_at` è valorizzato (2026-04-19) pur essendo lo stato `UPLOADED` — residuo di una transizione passata, incoerente con lo stato attuale.

~~**Non toccato**: non accodato, non collegato, non eliminato.~~ **Superato il 2026-07-21**: il report 15 è stato accodato su prod come oggetto del collaudo end-to-end del worker (OPS_RUNBOOK §2.8) ed è ora in `NEEDS_REVIEW`, orfano. L'esito di merito dell'estrazione è in **§8.10**; la decisione di prodotto (resta orfano documentato, nessuna azione a DB) è registrata lì e in OPS_RUNBOOK §10.23, ora chiusa.

### 8.9 Baseline Gemini sul dataset gold (2026-07-20)

Primo run di baseline completo: `gemini-2.5-pro`, prompt `OCR_SYSTEM_PROMPT_V2@sha256:31f3335733e2`, preprocessing on, eseguito su dev il 2026-07-20 (chiamate reali autorizzate da Alberto). Due misure: un passaggio singolo su tutti e 6 i casi (`--gold-all` + Triscelon via `--image`) e la varianza su 5 chiamate indipendenti per caso (`--repeat 5`, tie-break corretto `2f22b9d`: esito `ambiguo` senza maggioranza stretta). Proposte JSON in `ocr_bench_out/gold/` su dev, mai riversate nei casi (D1).

**Passaggio singolo — 67 correct / 11 wrong / 0 null su 78 campi confrontati (86%), nessuna inversione casa/trasferta rilevata:**

| Caso (legibility) | correct | wrong | null | Campi sbagliati (estratto vs truth, confidence) |
|---|---|---|---|---|
| Pol. Delta (3) | 13/13 | 0 | 0 | — |
| Unime (2) | 13/13 | 0 | 0 | — |
| Bellator (1) | 8/13 | 5 | 0 | finale casa 5 vs 4 (0.99); Q2/Q3/Q4 casa (0.99); `BELLATOR FROSINONE` vs FRUSINO (0.98) |
| Olympic (3) | 11/13 | 2 | 0 | Q3 away 0 vs 1, Q4 away 1 vs 0 (0.99) — scambio fra quarti, somme invariate |
| Salerno (2, ruotato 90°) | 10/13 | 3 | 0 | `S.C. SACCENGO` vs S.C. Salerno (0.90); `VIRTUS NUOTO ROMA` vs Nautilus Nuoto Roma (0.90); data 2026-05-28 vs 2026-04-18 |
| Triscelon (2) | 12/13 | 1 | 0 | data 2026-04-28 vs 2026-04-25 |

**Varianza su 5 chiamate indipendenti (`--repeat 5`) — per campo: stabile-corretto / stabile-sbagliato / instabile / ambiguo:**

| Caso | stab-corr | stab-SBAGLIATO | instabile | ambiguo | Note |
|---|---|---|---|---|---|
| Pol. Delta | 13 | 0 | 0 | 0 | perfettamente stabile e corretto |
| Unime | 12 | 0 | 1 | 0 | instabile solo la data (2026-03-28 ×4, 2006-03-28 ×1; maggioranza corretta) |
| Bellator | 6 | **1** | 6 | 0 | `final_score_home` **5×5 vs truth 4, confidence 1.00**: errore stabile riprodotto. `home_team_name` FROSINONE×3/FROSINO×1/FRUSINO×1 (maggioranza wrong; stamattina era 2-2-1 → `ambiguo`). Parziali casa maggioritari 1/0/2/2 → somma 5 = totale sbagliato: errore compensativo riprodotto |
| Olympic | 10 | 0 | 3 | 0 | instabili Q3 away (0×3, 1×2 — maggioranza wrong), Q4 away (1×3, 0×2 — maggioranza wrong) e `away_team_name` (LIBERTAS ROMA EUR P.N×3 e varianti — maggioranza wrong per suffisso aggiunto), tutti a confidence 1.00 |
| Salerno | 2 | 0 | 6 | 5 | il caso limite del dataset: stabili-corretti solo Q1 home/away. Nomi = 5 allucinazioni diverse in 5 chiamate per lato (`CONI`×2, `S.C. TUSCOLANO`, `Asd Tus Novara Nuoto Roma`, `S.C. Spresiano`; away tutte diverse, inclusa `Invictus Nuoto Roma`) → `ambiguo`. Data mai corretta in 5 run (2024-05-18×2, 2026-05-28×2, 2022-05-28×1) → `ambiguo`. Finale casa 12×3/11×1/17×1. **1 inversione casa/trasferta su 5 run.** Confidence media ~0.94 ovunque |
| Triscelon | 11 | **1** | 0 | 1 | data **stabile-sbagliata 5×5** (2026-04-28 vs truth 2026-04-25): secondo errore stabile del dataset. `away_team_name` in pareggio vero 2-2 (`TRIS CELON ETNA SPORT` correct vs `TRISKELION ETNA SPORT` wrong, conf 0.998) → esito `ambiguo` — il tie-break corretto (`2f22b9d`) al lavoro |

Totali `--repeat` sui 78 campi: **54 stabili-corretti (69%), 2 stabili-SBAGLIATI, 16 instabili, 6 ambigui.**

**Letture della baseline** (fatti misurati, non conclusioni definitive — campione: 6 fogli, 1+5 chiamate ciascuno):

1. **La confidence auto-dichiarata resta non informativa nei casi che contano**: tutti gli errori del passaggio singolo stanno fra 0.90 e 0.99 — le due allucinazioni sui nomi di Salerno a 0.90, l'errore stabile di Bellator a 0.99-1.00. Nel `--repeat`, i campi instabili, sbagliati o ambigui hanno `confidence_mean` fra 0.94 (Salerno, incluse 5 allucinazioni diverse dello stesso nome) e 1.00 (Bellator, Olympic). Nessuna soglia su questo segnale separerebbe il giusto dallo sbagliato su questi dati.
2. **L'errore stabile esiste e ora sono due**: Bellator `final_score_home` = 5 in 5 chiamate su 5 (truth 4, confidence 1.00), coi parziali casa maggioritari (1/0/2/2) che sommano ancora al totale sbagliato — errore compensativo sistematico, non rumore di run; e Triscelon `date` = 2026-04-28 in 5 su 5 (truth 2026-04-25). Nessuna ripetizione li smaschera: è la classe di errore che solo una verità esterna rileva.
3. **La leggibilità/qualità del foglio domina l'esito**: Delta e Unime perfetti e stabili; Olympic e Triscelon quasi; Bellator (legibility 1) 8/13 con 7 campi instabili; Salerno (ruotato 90°) è il caso limite — il singolo passaggio odierno leggeva 10/13 coi punteggi perfetti, ma il `--repeat` mostra che era **fortuna del run**: 11 campi su 13 instabili o ambigui, contro i 6/13 del 19/07 sullo stesso foglio. Un passaggio singolo su un foglio degradato non è una misura: è un'estrazione dalla distribuzione.
4. **La classe di errore dei nomi è l'allucinazione plausibile, non il typo**: `S.C. SACCENGO`, `VIRTUS NUOTO ROMA` (Salerno), `BELLATOR FROSINONE` (prior linguistico, di nuovo), `LIBERTAS ROMA EUR P.N` (suffisso inventato). Nessuna è una grafia legittima alternativa: confermano la separazione della diagnosi §8.6 (alias per divergenze reali, accuratezza OCR per le allucinazioni).
5. **La data è il campo più fragile dopo i nomi**: sbagliata, instabile o ambigua su 3 casi su 6 — Triscelon stabile-sbagliata (28 vs 25, 5×5), Salerno mai corretta in 5 run (tre valori diversi, due anni diversi), Unime 2006 in 1 run su 5 — e il provider non dichiara una confidence dedicata per la data.
6. **Inversione casa/trasferta: rara ma riprodotta** — 1 estrazione su 36 (un run del `--repeat` Salerno, 17-12), sempre e solo sul foglio ruotato. Il check dedicato dell'harness l'ha rilevata; su tutti gli altri fogli non è mai scattato.
7. Nessun run fallito per errore API: 36/36 chiamate a buon fine, nessun caso non-benchato.

### 8.10 Estrazione del report 15 su prod (2026-07-21): il primo dato di accuratezza raccolto in produzione

Il 2026-07-21 il report 15 è stato accodato su prod come oggetto del **collaudo end-to-end del worker OCR** (Macro 22, OPS_RUNBOOK §2.8). Il collaudo è **verde** — è la pipeline a essere stata verificata. Quello che segue è il dato *di merito*, che appartiene a Macro 8 e che è **negativo**.

Il foglio è il cartaceo del caso gold `2026-04-18_sc-salerno_vs_nautilus-nuoto-roma` — lo stesso "caso limite ruotato 90°" della baseline §8.9. Questa però è la **prima estrazione di questo foglio fatta dalla pipeline reale in produzione**, non dall'harness di bench: stesso modello (`gemini-2.5-pro`), stesso preprocessing, percorso applicativo completo.

| Campo | Estratto (prod, report 15) | Truth (cartaceo) | Esito |
|---|---|---|---|
| `home_team` | `S.C. Tuscolano` | S.C. Salerno | **allucinazione** |
| `away_team` | `Virtus Nuoto Roma` | Nautilus Nuoto Roma | **allucinazione** |
| `date` | 2026-06-18 | 2026-04-18 | **sbagliata** (mese) |
| `final_score` | 17-12 | 12-17 | **invertito** |
| Q1 | 5-5 | 5-5 | corretto |
| Q2 | 4-6 | 4-6 | corretto |
| Q3 | 7-1 | 2-4 | **allucinato** |
| Q4 | 1-0 | 1-2 | **allucinato** |

**(a) L'errore compensativo si ripresenta, e qui è ancora più istruttivo.** I parziali estratti sommano `5+4+7+1 = 17` e `5+6+1+0 = 12`: tornano **esattamente al finale estratto**, cioè al finale *invertito*. Il controllo "somma parziali == finale" passa, come sempre. Ma c'è un dettaglio in più rispetto ai casi di §8.5(b): Q1 e Q2 sono corretti *nei valori e nell'attribuzione*, mentre Q3 e Q4 sono inventati per far quadrare i totali con l'inversione. Cioè il modello non ha invertito il foglio in modo uniforme — ha letto correttamente la parte alta della griglia e ha poi **riconciliato all'indietro** la parte bassa verso un totale sbagliato. È la firma di una ricostruzione, non di una lettura.

**(b) I due nomi confermano la classe "allucinazione plausibile" (§8.6(b), §8.9 lettura 4).** `S.C. Tuscolano` e `Virtus Nuoto Roma` sono nomi di società di pallanuoto romana perfettamente verosimili, e nessuno dei due è una grafia alternativa di quello vero: non sono mappabili da una tabella di alias, per definizione. `S.C. Tuscolano` compare peraltro già nell'elenco delle cinque allucinazioni diverse prodotte dal `--repeat 5` su questo stesso foglio (§8.9): la pipeline di produzione ha pescato dalla stessa distribuzione dell'harness di bench.

Conseguenza operativa positiva: **la discovery non ha agganciato nulla** e il referto è finito orfano in `NEEDS_REVIEW`. Su un'estrazione sbagliata così, un fuzzy matching più permissivo sarebbe stato un danno, non un miglioramento — è il vincolo di disegno che la fetta sul passaggio a `difflib` deve rispettare.

**(c) Chiarimento sulla chiave `confidence` — il `{}` del PASSO 7 era un artefatto dello script, non un dato.** La checklist di collaudo leggeva `normalized_data['confidence_fields']` alla **radice** del payload, dove quella chiave non esiste, e mostrava quindi `{}`. Nel payload reale la confidence sta sotto `metadata`, coerentemente con lo schema v2. Valori effettivi del report 15:

- `metadata.confidence` = **0.95**
- `metadata.confidence_fields` = `home_team` **1.0**, `away_team` **1.0**, `final_score` **1.0**, `quarters` **1.0**, `home_roster` 0.98, `away_roster` 0.98, `events` 0.9, `officials` 0.95
- (esistono anche `officials.confidence` = 0.95 e `teams.{home,away}.confidence` = 0.98)

**Il dato corretto è peggiore del `{}`.** Il modello ha dichiarato **1.0** su tutti e quattro i campi che ha sbagliato: entrambi i nomi allucinati, il finale invertito e la griglia dei parziali. Non è confidence bassa ignorata: è confidence **massima su valori inventati**, in produzione, sul percorso reale. È la conferma su un caso non costruito di §8.5(c) e della lettura 1 di §8.9 — e la motivazione diretta della neutralizzazione dei gate su `confidence`/`confidence_fields` (§8.11): quei gate non sono mai scattati perché **non possono** scattare, gli errori vivono tutti fra 0.90 e 1.00.

**Nessun riversamento nel caso gold.** Questa estrazione **non** è stata scritta in `extractions[]` del caso: vale la decisione D1 di §8.2 — il riversamento nel dataset è un atto umano dopo review, mai automatico. I valori qui sopra sono registrati come finding, non come misura del dataset.

**Report 15 — decisione presa (Alberto, 2026-07-21):** resta in `NEEDS_REVIEW` come orfano documentato, nessuna azione a DB. Le due società lette sul foglio non esistono a sistema (e quelle vere, `S.C. Salerno` e `Nautilus Nuoto Roma`, sono rispettivamente assente e presente — §8.2): il referto diventerà risolvibile solo se e quando le anagrafiche mancanti entreranno a DB. Registrato anche in OPS_RUNBOOK §10.23, che si chiude con questa decisione.

### 8.11 Fetta A1 — neutralizzazione dei gate sulla confidence (2026-07-21)

Prima contromisura del giro post-collaudo. **Non aggiunge un controllo: ne toglie quattro**, perché quattro controlli inerti sono peggio di zero — comunicano una garanzia che non esiste.

**Cosa è stato rimosso.**

| Dove | Decisione rimossa |
|---|---|
| `ocr_quality_gate.evaluate` | blocker se `metadata.confidence < 0.3`; warning se `< 0.6` |
| `ocr_quality_gate.evaluate` | blocker se `confidence_fields[home_team/away_team/final_score] < 0.5`; info se `< 0.8` |
| `schema.validate_coherence` | warning su confidence globale `< 0.6`, su `officials.confidence < 0.5`, su `teams.<side>.confidence < 0.5` |
| `schema.assess_publish_readiness` | blocker se `confidence < 0.3`; warning se `0.3 ≤ confidence < 0.6` |

**Motivazione, in una riga: gli errori vivono dove le soglie non arrivano.** Sui 78 campi della baseline §8.9 e sull'estrazione reale in produzione §8.10, ogni singolo errore osservato ha confidence fra **0.90 e 1.00** — le due allucinazioni di nome del report 15 a 1.00, l'errore stabile di Bellator a 0.99-1.00, le allucinazioni di Salerno a 0.90. Le soglie più alte in gioco erano 0.6 e 0.8. **Nessuno di questi gate è mai scattato in esercizio, e nessuno potrebbe scattare**: non è una taratura da correggere, è un segnale che non contiene l'informazione richiesta.

**Cosa resta, deliberatamente.**

- **Tutti i controlli strutturali**: sezioni obbligatorie, nomi squadra presenti e diversi fra loro, match col contesto della partita selezionata, formato del punteggio, somma dei quarti, eventi che non eccedono i totali, valori placeholder. Sono i controlli che *possono* fallire, e che infatti falliscono.
- **Il contratto di schema** che vuole `metadata.confidence` numerica: è forma del payload, non giudizio sul valore. Rimuoverlo avrebbe cambiato il contratto con il provider senza guadagno.
- **La confidence nei dati e sotto gli occhi del revisore**: resta in `normalized_data`, resta stampata in review — ma etichettata **"non calibrata"**, con il razionale nel tooltip. È un dato grezzo di provenienza, non un semaforo.

**Rimossi anche gli highlight in review** sui campi con confidence `< 0.7`: stessa patologia, forma più insidiosa. Su questi dati non si accendevano mai, quindi il revisore leggeva l'assenza di evidenziazione come "campo affidabile" **proprio sui campi sbagliati** — un gate inerte che si trasforma in disinformazione attiva. Nel rimuoverli è emerso che la variabile di contesto `confidence_fields` non era **mai** stata popolata dalla view: la riga `const confidenceFields = {{ confidence_fields|safe }}` renderizzava `const confidenceFields = ;`, un `SyntaxError` che uccideva l'intero blocco script della review page. Bug latente, trovato togliendo codice morto.

**Cosa questa fetta NON fa.** Non sostituisce il segnale rimosso. Il controllo indipendente indicato in §8.5(b)-1 — conteggio degli eventi-gol per periodo contro il parziale di quel periodo — è stato **implementato il 2026-07-21** (dettaglio e decisioni D1-D6 in §8.5(b)-1). Vale comunque §8.5(b)-2: **solo la review umana discrimina**, e nessun verde del gate va letto come "dato attendibile".

**Correzione di framing (D5, 2026-07-21): l'indipendenza fra griglia e cronologia esiste sul foglio, ma non nell'estrazione.** §8.5(b)-1 e §8.5(f) qualificavano il conteggio per periodo come controllo *indipendente* perché legge una zona diversa del referto cartaceo. Sul foglio è vero, ed è ciò che ha permesso la corroborazione umana del match 1 (§8.5(f)). **Nell'estrazione OCR non lo è**: il referto 16, misurato il 2026-07-21, ha eventi per periodo perfettamente coerenti con parziali che sono falsi — un unico atto di lettura ha prodotto entrambe le zone, e le ha rese concordi tra loro e discordi dal foglio. L'indipendenza è una proprietà della *fonte*, non del *lettore*, e un lettore unico la annulla.

Conseguenza operativa, che è il motivo per cui questa correzione va scritta e non solo capita: il check per-periodo **non è la seconda opinione** che la §8.5(b) sperava. Misura la coerenza interna dell'estratto e nulla di più. Vale in una sola direzione — quando **fallisce**, ha trovato un errore certo (D1) o quasi certo (D2); quando **passa**, non ha detto nulla sulla verità dei numeri. Per questo il check è cablato come blocco solo sui fallimenti e la tabella in review non ha alcun segnale di conferma. La corroborazione vera resta quella di §8.5(f): due letture di zone diverse fatte da **lettori diversi**, cioè in pratica la collazione umana sul cartaceo.

---

← [Macro precedente](7_profilo_fan.md) | → [Macro successiva](9_sistema_sponsor.md)
