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
  - **Aggiornamento 2026-07-22: riparazione estesa a PROD (Opzione A, prerequisito 2).** Stessa riparazione del 21/07 su dev, eseguita su prod con checklist a 6 blocchi (`scratch/prereq2_repair_prod_20260722.sh`, gated su backup + dry-run su copia del backup + SHA del DB prod invariato). Blocker post-riparazione **7/7/7/4/5** (identici a dev). Confronto dev↔prod: `normalized_data` bit-identico per 7/8/10/11; per il 16 diverge il full (estrazione Gemini indipendente) ma i campi riparati coincidono. Match 1/2/3/4 e LeagueStanding invariati (nessun `PUBLISHED`, zero strutturale). Solo `normalized_data.scores` (+`match_info.date` del solo 11) toccati, audit `normalized_data_repair_gold`, status `NEEDS_REVIEW` invariato. Deploy e dettaglio operativo in OPS_RUNBOOK §2.11.
  - **Livello di pubblicazione "solo punteggio" (Opzione A, 2026-07-22).** `publish_report` guadagna un parametro `level` (`FULL` | `SCORE_ONLY`, campo `MatchReport.publication_level`, default `FULL` retrocompatibile, migration additiva `0020`). `SCORE_ONLY` pubblica **punteggio e parziali verificati senza creare `MatchEvent`** e cancellando quelli esistenti: è il livello adatto ai referti 7/8/10/11/16, il cui gold copre punteggio e parziali ma non gli eventi. **Non indebolisce la Policy A strict**: l'abort zero-eventi resta identico byte per byte sul livello `FULL` — su `SCORE_ONLY` non viene valutato perché zero eventi è il contratto dichiarato del livello, non un'anomalia. `assess_publish_readiness(data, level)` declassa i soli blocker event-scoped a warning `[fuori livello]` su `SCORE_ONLY`, lasciando i blocker score-scoped. La misura di accuratezza si valuta sul livello dichiarato: un referto `SCORE_ONLY` si giudica su punteggio e parziali, gli eventi restano fuori (già in `not_verified` nei casi gold). Lato pubblico `Match.events_published` (True solo se il referto PUBLISHED è `FULL`) distingue "cronologia non disponibile" da "0 eventi". State machine e side effects in [STATE_MACHINES.md](../STATE_MACHINES.md) §1.
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

**Terza e quarta conferma su casi reali non costruiti (2026-07-22, riparazione prod).** La riparazione `normalized_data` su prod (§8.5 aggiornamento 2026-07-22, OPS_RUNBOOK §2.11) ha esposto due estrazioni Gemini/GPT distinte dello stesso cartaceo (Bellator/Lazio, vero 4-19) che entrambe passano il check "somma parziali == finale" su un finale completamente falso:

| Referto | Finale PRE (falso) | Parziali PRE | Somma torna? | Vero |
|---|---|---|---|---|
| 10 (`gpt-4o`) | 11-19 | 2-2/4-5/2-4/3-8 | 2+4+2+3=11, 2+5+4+8=19 ✓ | 4-19 |
| 16 (`gemini-2.5-pro`) | 5-19 | 1-3/0-5/1-5/3-6 | 1+0+1+3=5, 3+5+5+6=19 ✓ | 4-19 |

**Il conteggio sale a quattro casi reali, zero rilevazioni.** Precedenti: match 4 del deploy 20/07 (OPS_RUNBOOK §6.5, blocco saltato con parziali vecchi che sommavano comunque) e il finding originale del 2026-07-19 (le due estrazioni di §8.5, entrambe con somma coerente). Non è più un limite dimostrato su un caso: è una proprietà stabile della classe di errore — il check somma-parziali è **inutile per costruzione**, confermato quattro volte su dati reali indipendenti. La rete resta il controllo per-periodo (§8.5(b)-1) contro i parziali gold e, in ultima istanza, la collazione umana sul cartaceo.

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

**Decisione di prodotto ratificata (2026-07-21): la classifica resta a una sola strada, il gate del risultato pubblico no.** Durante la propagazione su prod del merge Lazio (§8.7, OPS_RUNBOOK §2.10) la verifica browser ha rilevato la lega 4 con la classifica interamente a zero pur avendo il match 3 concluso e `is_data_verified=True`. Recon read-only ha confermato che lo zero è preesistente e strutturale (nessun referto `PUBLISHED` su prod, vedi apertura di questo §8.5). Alberto ha esaminato il caso e **ratificato** — non lasciato per inerzia — il comportamento attuale di `StandingsService` (`reports__status='PUBLISHED'`, invariato dal codice): *"la classifica si aggiorna solo quando una partita è stata ufficialmente letta e confermata da un referto, e usando i dati che stanno sul referto."* Rifiutata esplicitamente la doppia strada del gate (h): `is_data_verified` **non deve mai diventare fonte per la classifica**, perché è un atto umano (una dichiarazione), mentre la classifica deve poggiare su un artefatto verificabile — il referto pubblicato — e sui dati che quel referto contiene. Conseguenza accettata consapevolmente, non un bug da correggere in UI aggirando il criterio: **l'asimmetria fra pagina match (risultato visibile via `is_data_verified`) e classifica (a zero) è per disegno** finché nessun referto è `PUBLISHED`. L'unica strada per popolare le classifiche resta correggere i `normalized_data` dei referti (giro già dichiarato in DEBITI.md §10.22) e pubblicarli — non un secondo criterio di lettura.

Il censimento dei punti di esposizione è stato fatto in modo esaustivo prima dell'implementazione (lezione dallo stato `QUEUED`: 7 punti rotti su 14 perché nessuno li aveva enumerati) e il test `TemplateScoreExposureAuditTest` in `matches/tests_result_visibility.py` **deriva** la lista dai template invece di elencarla a mano: un nuovo template che stampa un punteggio senza gate fa fallire la suite da solo.

**Nota operativa: non pubblicare i report 7, 8, 10, 11, 16.** Questi cinque report hanno `normalized_data` con punteggio e/o attribuzione casa/trasferta sbagliati, non ancora corretti (giro separato, fuori scope Macro 8 attuale). La correzione applicata finora — su dev il 2026-07-19 e su prod il 2026-07-20 — ha toccato solo il `Match`, non il report.

> **Aggiornamento 2026-07-20.** Su prod tutti e cinque sono ora in `NEEDS_REVIEW`: il report 16, che era in `EXTRACTED` (cioè a un click dalla pubblicazione), è stato **demosso a `NEEDS_REVIEW` con audit** all'inizio della finestra di deploy, prima di ogni altra operazione, proprio per togliere di mezzo il rischio durante il lavoro. Il `normalized_data` non è stato toccato: la demozione allontana il pericolo, non lo rimuove. Non esiste tuttora **alcun guardrail a codice** che impedisca la pubblicazione — la protezione è documentale, registrata come debito in DEBITI.md §10.22. Se uno di questi report venisse pubblicato o ripubblicato, `publish_report()` (`matches/services/publishing_service.py`) sovrascriverebbe `Match.home_score`/`away_score`/`quarter_scores` (e, per match 2, ricreerebbe gli eventi con l'attribuzione squadra ancora sbagliata) leggendo dal `normalized_data` non corretto — vanificando silenziosamente la correzione appena fatta.

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

~~**Non toccato**: non accodato, non collegato, non eliminato.~~ **Superato il 2026-07-21**: il report 15 è stato accodato su prod come oggetto del collaudo end-to-end del worker (OPS_RUNBOOK §2.8) ed è ora in `NEEDS_REVIEW`, orfano. L'esito di merito dell'estrazione è in **§8.10**; la decisione di prodotto (resta orfano documentato, nessuna azione a DB) è registrata lì e in DEBITI_CHIUSI.md §10.23, ora chiusa.

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

**Report 15 — decisione presa (Alberto, 2026-07-21):** resta in `NEEDS_REVIEW` come orfano documentato, nessuna azione a DB. Le due società lette sul foglio non esistono a sistema (e quelle vere, `S.C. Salerno` e `Nautilus Nuoto Roma`, sono rispettivamente assente e presente — §8.2): il referto diventerà risolvibile solo se e quando le anagrafiche mancanti entreranno a DB. Registrato anche in DEBITI_CHIUSI.md §10.23, che si chiude con questa decisione.

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

### 8.12 Esperimento prompt V3 sul dataset gold (2026-07-22)

Primo esperimento di prompt dopo l'audit del 22/07: `OCR_SYSTEM_PROMPT_V3` = V2 più (a) anti-riconciliazione sulla griglia parziali, (b) trascrizione letterale dei nomi, (c) data cifra per cifra con confidence dedicata (`confidence_fields.date`) e trascrizione grezza (`match_info.date_digits`). V3 vive **accanto** a V2 in `vision_providers.py`, selezionabile via `settings.OCR_PROMPT_VERSION` o `ocr_bench --prompt-version v3`; **il default di produzione resta V2** — la promozione è una decisione di Alberto sui numeri qui sotto, non presa in questo giro.

Run: `gemini-2.5-pro`, prompt `OCR_SYSTEM_PROMPT_V3@sha256:87b86a945215`, preprocessing on, `--repeat 5` × 6 casi = 30 chiamate esatte (67.980 token in, 124.703 out, **$1.33** a listino verificato $1.25/$10 per M — stima dell'audit: ~$1.10). Proposte in `ocr_bench_out/gold_v3_20260722/` su dev (D1: mai riversate nei casi). Avvertenza di confrontabilità: la baseline §8.9 girò sul V2 pre-`5758642` (`31f3335733e2`); il V2 attuale (`a0f50fbe5244`) differisce solo per la derivazione del `quarter` degli eventi, campo fuori dalla truth gold — il confronto sui 78 campi misurati resta sensato, ma va detto.

**Totali sui 78 campi (repeat-5), V3 vs baseline §8.9:** stabili-corretti **59 vs 54** (76% vs 69%), stabili-SBAGLIATI 2 vs 2, instabili 15 vs 16, ambigui **2 vs 6**. Media per singolo passaggio: **86.9%** (5 passaggi: 85-90%) vs 86%. Inversioni casa/trasferta: **0/30** vs 1/36. Nessuna chiamata fallita.

Risposte alle domande di misura del giro:

1. **Il segnale somma≠finale sul Bellator NON compare: 0/5.** I cinque run producono griglie *diverse fra loro* che sommano tutte esattamente al finale sbagliato 5-19: la ricostruzione compensativa sopravvive all'istruzione esplicita. Il segnale è però comparso **una volta altrove** (Olympic run 2: finale 20-1, parziali 25-1 per una cifra selvaggia su Q2 casa): l'istruzione *può* disaccoppiare griglia e finale, e quando lo fa il check meccanico intercetta davvero un errore — ma non disinnesca la classe di errore dove il finale stesso è letto male.
2. **Celle-parziale Bellator: nessun miglioramento di sostanza** (6 stabili-corretti + 1 stabile-sbagliato + 6 instabili, identico alla baseline; per maggioranza 8/13 → 9/13). Il finale casa resta **stabile-sbagliato 5×5 a confidence 0.998**: secondo giro consecutivo, su due versioni di prompt.
3. **FRUSINO: sì, maggioranza corretta** — `BELLATOR FRUSINO`×4 vs `FROSINONE`×1 (baseline: FROSINONE×3, maggioranza sbagliata). La trascrizione letterale funziona sul prior linguistico puro. **Non** elimina però il suffisso inventato di Libertas (`P.N.`×3, conf 1.0) né le allucinazioni da foglio illeggibile (Salerno: `CONI`×2, `S.C. TUSCOLANO`; Triscelon: `TRISKELION`×3, con la variante nuova `TRISUS VELON`): quella non è normalizzazione, è lettura impossibile.
4. **Date: miglioramento parziale, non sui due casi bersaglio.** Delta/Unime/Bellator/Olympic: data stabile-corretta 5×5 (Unime aveva un 2006×1 in baseline, sparito; Bellator e Olympic già corrette). Ma **Triscelon resta stabile-sbagliata 28×5 a conf 1.0** (invariata) e Salerno resta mai-corretta (5 valori tutti sbagliati). La confidence dedicata alla data è attiva (0.998-1.0)… anche sui valori sbagliati: non calibrata, come da §8.11.
5. **Nessuna regressione sui fogli leggibili**: Delta 13/13 stabile-corretto; Unime 12+1 instabile-con-maggioranza-corretta (`UNIME`×4/`UN.NE`×1), stesso conteggio della baseline (l'instabile era la data, ora è il nome). Olympic **migliora** (11 vs 10 stabili-corretti, sparito lo scambio Q3/Q4 away) e Salerno migliora nettamente (6 vs 2 stabili-corretti, finali 12-17 stabili-corretti 5×5, 0 inversioni).

**Lettura del giro in una riga:** V3 migliora il contorno (nomi da prior, varianza su foglio ruotato, ambigui dimezzati, date già-quasi-buone) ma **non scalfisce i due errori stabili** — Bellator finale casa e Triscelon data — che restano invisibili a qualunque ripetizione e a qualunque coerenza interna. Sono la classe di errore per cui l'audit del 22/07 aveva già indicato la strada successiva: la **doppia estrazione per zona** (secondo atto di lettura indipendente sulla sola griglia/testata), che è l'esperimento candidato del prossimo giro.

### 8.13 Doppia estrazione per zona sul dataset gold (2026-07-22)

Esperimento successivo a §8.12: un **secondo atto di lettura indipendente**, ristretto alle sole tre zone dove vivono gli errori stabili (griglia parziali, finale di ciascuna squadra, data), da confrontare col primo passaggio. Ipotesi da falsificare: *una seconda lettura indipendente discorderà dalla prima sull'errore, esponendolo*.

**Cosa è stato costruito.** `OCR_SYSTEM_PROMPT_ZONE` (`@sha256:8a25dff54e59`) — secondo passaggio, output JSON minimale (solo finale/parziali/data + confidence + warnings), eredita da V3 anti-riconciliazione e trascrizione cifra-per-cifra, **niente crop** (variabile isolata: il secondo atto di lettura, non lo zoom — il crop è l'esperimento dopo). Regola di divergenza pura in `matches/services/ocr_double_extraction.py` (`compare_passes`): discordanza su finale, parziali o data fra le due letture → `NEEDS_REVIEW`; una lettura `null` è **astensione**, non divergenza. La regola **alza la bandiera, non sceglie il valore giusto**, e in questo giro **non è attiva in produzione**: è selezionabile dal bench (`ocr_bench --second-pass --first-pass-dir …`, default off). La seconda chiamata non riceve mai il risultato della prima (indipendenza reale).

Run: `gemini-2.5-pro`, secondo passaggio `--repeat 5` × 6 casi = **30 chiamate zone** (primo passaggio **riusato** dai risultati V3 di §8.12 in `gold_v3_20260722/`, non rifatto). Proposte in `ocr_bench_out/gold_secondpass_20260722/` (D1: mai riversate nei casi). Accoppiamento delle ripetizioni indice per indice — due serie di campioni iid, l'accoppiamento è arbitrario ma equivalente a qualunque altro.

**Tabella divergenze (rip. divergenti su 5, poi per zona):**

| caso | legib. | div/5 | finale | parziali | data | natura |
|---|---|---|---|---|---|---|
| Delta vs Villa York | 3 | **0/5** | 0 | 0 | 0 | pulito, nessun falso positivo |
| Unime vs Nautilus | 2 | **0/5** | 0 | 0 | 0 | pulito, nessun falso positivo |
| **Bellator** vs Lazio | 1 | 5/5 | **0** | 5 | 0 | vero pos. sui parziali, **finale NON intercettato** |
| Olympic vs Libertas | 3 | 4/5 | 0 | 4 | 0 | rumore sui parziali (finale e data corretti) |
| Salerno vs Nautilus | 2 | 5/5 | 5 | 5 | 4 | vero pos. (foglio davvero illeggibile) |
| **Triscelon** vs Nautilus | 2 | **0/5** | 0 | 0 | 0 | **data NON intercettata** (concordi sul valore sbagliato) |

Separazione netta veri/falsi positivi: **veri positivi** = Salerno (5/5, foglio score-2 che l'OCR legge male: il secondo passaggio legge finali diversi e sbagliati, la bandiera è giusta) e Bellator sui *parziali* (5/5). **Falsi positivi puri** (foglio che l'OCR legge bene, eppure diverge) = **zero sui due controlli** Delta/Unime; ma **Olympic** diverge 4/5 sui soli parziali pur avendo finale e data corretti 5/5 → rumore operativo, la griglia dei parziali è instabile fra letture anche quando il finale è giusto.

**Risposte alle domande di misura:**

1. **Sui due errori stabili la seconda lettura NON diverge dalla prima, e non legge mai il valore giusto. Il meccanismo di confronto fra passaggi non li cattura.** Bellator finale casa: entrambi i passaggi leggono **5-19** in tutti e 5 i run (divergenza sul finale **0/5**, valore corretto 4 letto **0/5**). Triscelon data: entrambi leggono **28** in tutti e 5 (divergenza **0/5**, valore corretto 25 letto **0/5**). L'errore è stabile *fra atti di lettura*, non solo fra ripetizioni dello stesso atto: il modello rilegge "4"→"5" e "25"→"28" in modo sistematico anche nella lettura ristretta. Detto chiaramente: **per i due bersagli il meccanismo non serve.** *Silver lining su Bellator*: il secondo passaggio, ristretto alla griglia, la legge correttamente (somma casa **4**) e **auto-segnala** la discordanza somma≠finale in `extraction_warnings` in **4/5** run — segnale che il V3 a passaggio singolo non produceva mai (§8.12: 0/5). La restrizione di zona **rompe la ricostruzione compensativa**: qui è il check *interno* del secondo passaggio a mordere, non il confronto fra i due.
2. **Falsi positivi sui fogli puliti: zero sui due controlli** (Delta 0/5, Unime 0/5). Il costo operativo del meccanismo non è sui fogli puliti *certificati*, ma sulla **zona parziali** in generale: Olympic (finale+data corretti) va in review 4/5 per sola instabilità della griglia. Se il trigger scattasse su qualunque divergenza di zona, Olympic sarebbe review inutile 4/5.
3. **Quando divergono, quale è giusta? Non c'è un criterio.** Bellator parziali: giusta la **seconda** (somma 4 = truth). Salerno finale: giusta la **prima** (12-17), la seconda è sbagliata (17-17/17-12). Il vincitore cambia caso per caso: la regola **può solo alzare la bandiera**, esattamente come progettata — la scelta resta umana.
4. **Il secondo passaggio riconcilia sui fogli facili, ma NON su Bellator.** Riconcilia (somma parziali == suo finale) 5/5 su Delta, Unime, Triscelon; **1/5 su Bellator** (in 4/5 espone la discordanza: parziali corretti a 4, finale sbagliato a 5). Sulla zona ristretta la trascrizione è davvero indipendente: l'anti-riconciliazione **funziona** dove nel passaggio pieno V3 falliva 5/5.
5. **Costo reale.** 30 chiamate zone: 35.790 token in, 7.010 out (media **1.193 in / 234 out** per chiamata, latenza media 11,8s). Costo a listino ($1,25/$10 per M): **$0,1148** totali, **$0,0038/chiamata** — ~11× più economica di una chiamata piena V3 ($0,044), perché sia il prompt (breve) sia l'output (minimale) sono piccoli. **A regime la doppia estrazione aggiunge ~$0,0038 per referto** (una chiamata zona sopra il passaggio pieno): **+~8,6%** sul costo di una singola estrazione V3. Trascurabile: la decisione è di efficacia, non di costo.

**Raccomandazione: MODIFICARE, non adottare la regola così com'è né scartare tutto.**
- **Scartare** il confronto *cross-passaggio* come meccanismo per i due errori bersaglio: misurato **0/5 su entrambi**, non li cattura. Fa scattare la review sull'*instabilità dei parziali* (Olympic, Bellator-parziali), che è un segnale diverso e più rumoroso.
- **Tenere e valorizzare** ciò che ha funzionato: il **check somma≠finale *interno* al secondo passaggio zona** ha morso su Bellator (4/5) dove il V3 pieno non mordeva mai (0/5), perché la restrizione di zona disaccoppia griglia e finale. È una leva a **una sola chiamata extra** ($0,0038) che aggredisce la classe della ricostruzione compensativa (Bellator) senza bisogno del confronto fra due passaggi: candidato = far scattare `NEEDS_REVIEW` quando il warning somma≠finale del passaggio zona compare, da valutare in un giro dedicato.
- **L'errore data (Triscelon) non è catturabile da nessun segnale di coerenza**: campo singolo, senza ridondanza interna, e le due letture concordano sul valore sbagliato (28). Non lo prende né il confronto fra passaggi né un check interno. Resta il residuo per l'**esperimento crop/zoom** (lettura ravvicinata della sola testata) o la review umana — la doppia estrazione **non** lo risolve e non va spacciata come tale.

Un debito registra la non-adozione e il residuo: [DEBITI.md](../DEBITI.md) §10.33.

### 8.14 V3.1 — semantica rigori `is_penalty` nello schema OCR (2026-07-22)

Giro innescato dalla trascrizione umana di eventi e roster del referto 11 (caso gold
Olympic–Libertas, §"gold standard"): il modello, sul foglio, emetteva spontaneamente
`type: "PENALTY_GOAL"` per il gol su rigore del Libertas — un tipo **fuori** dall'enum
dello schema, quindi scartato da `SCORE_EVENT_CODES` e invisibile al conteggio. Era la
causa diretta del blocker "P3 OSPITE 0 eventi-gol vs parziale 1" del referto 11: il gol
c'era, letto, ma buttato via per tipo inventato.

**Cosa è cambiato.** Aggiunto `events[].is_penalty` (bool, default false) allo schema OCR,
in modo additivo e retrocompatibile (`_normalize_response` lo forza a false quando assente,
così V2/mock/prompt più vecchi restano validi). Il prompt **V3** ora istruisce il modello a:
(i) NON inventare tipi fuori enum (cita `PENALTY_GOAL` come esempio da **non** usare);
(ii) trascrivere il gol su rigore come `type: "GOAL"` con `is_penalty: true` (conta come
gol); (iii) marcare l'espulsione che comporta un rigore come `EXCLUSION_20` con
`is_penalty: true` (la calottina è di chi commette il fallo). Il flag si propaga a valle:
`MatchDataConverter.get_events_data` → `MatchEvent.is_penalty` (campo già esistente a DB).

**V3 cambia hash: `87b86a945215` → `be51e9c6bc42` (V3.1).** V3 è il prompt promosso a
produzione, quindi la modifica è tracciata come per V2: hash **fissato a test**
(`test_v3_hash_is_pinned`), guardrail di contenuto esteso (`is_penalty`, divieto di tipi
inventati). Conseguenza di confrontabilità: i run bench V3 di §8.12 (`87b86a945215`) e i
futuri (`be51e9c6bc42`) **non sono confrontabili** sui campi eventi — sui campi
finale/parziali/data/nomi/roster il prompt è invariato, il confronto lì regge. **Zero
chiamate API in questo giro**: il re-run V3.1 sul gold è rimandato (decisione Alberto, per
misurare la versione nuova senza spendere due volte). V2 (`a0f50fbe5244`) e il prompt zone
(`8a25dff54e59`) invariati.

**Regola di dominio derivata, non estratta.** L'accoppiamento rigore↔gol (gol allo stesso
clock+periodo di un'espulsione `is_penalty` = rigore realizzato; assenza = sbagliato) resta
**calcolato a valle**, mai chiesto al modello né codificato nella truth. Stessa natura del
"fouled out" (3 espulsioni = fuori partita): derivato dalla lista eventi
(`matches/event_types.py`: `fouled_out_players`, `players_over_exclusion_limit`, soglia
`FOUL_OUT_EXCLUSIONS=3`), esposto in `get_fouled_out_stats`. Validazione simmetrica del
limite di 3: sui casi gold (test automatico sulla trascrizione umana) e sui dati OCR
(`validate_coherence` avvisa se un giocatore supera 3 — segnale di errore di estrazione).
Le statistiche abilitate (rigori causati/ottenuti/segnati/sbagliati, % realizzazione,
fouled out per giocatore/partita/stagione) sono idee di prodotto in
[FUTURE_IDEAS.md](../FUTURE_IDEAS.md) §4: **dato già sul cartaceo**, oggi scartato — a
differenza delle statistiche avanzate del §1 di FUTURE_IDEAS, che una fonte reale non
l'hanno.

### 8.15 Misura V3.1 sul gold — eventi, roster e rigori (2026-07-22)

Primo re-run del gold sul prompt **V3.1** (`OCR_SYSTEM_PROMPT_V3@sha256:be51e9c6bc42`),
rimandato in §8.14. È anche la **prima** misura possibile su EVENTI e ROSTER: la truth
Olympic è stata promossa (44 eventi, 2 roster, §8.14) e le proposte del bench ora
persistono il contenuto grezzo eventi/roster (commit `da27fd4`) — senza quello il confronto
a contenuto è impossibile. Run: `gemini-2.5-pro`, `--repeat 5` × 6 casi = **30 chiamate**
(5 via `--gold-all` + Triscelon con `--image`, come §8.12), preprocessing on. Proposte in
`ocr_bench_out/gold_v3_1_20260722/` su dev (D1: mai riversate nei casi). **Costo reale: 30
chiamate, 76.770 token in, 142.761 out, $1,52** a listino ($1,25/$10 per M); latenza media
88s (referto Olympic denso di eventi → output alto). Zero chiamate fallite.

**Punteggi — nessuna regressione attribuibile al prompt.** Sui 78 campi (finale/parziali/
nomi/data), V3.1 vs §8.12 (V3): stabili-corretti **58 vs 59**, stabili-SBAGLIATI **3 vs 2**,
instabili **15 vs 15**, ambigui **2 vs 2**. Il prompt dei campi punteggio è **identico byte
per byte** fra V3 e V3.1 (§8.14: cambia solo la sezione eventi), quindi lo scarto 58/3 vs
59/2 è **varianza di campionamento**, non effetto del prompt rigori. Il campo che diventa
stabile-sbagliato (Bellator `quarter_3_home`, verità 3, letto **2**) leggeva già "2" in
maggioranza in §8.12 (3/5 campioni → ora 5/5): stesso valore sbagliato, solo più
concentrato. I due errori stabili duri restano **invariati** — Bellator finale casa (5≠4) e
Triscelon data (28≠25). Inversioni casa/trasferta **1/30**. **Verdetto: i rigori non hanno
introdotto regressioni sui punteggi.**

**Eventi/roster Olympic (vs truth 20 gol casa / 1 ospite, 44 eventi).**
- **Gol casa estratti: 20/21/19/21/19** sui 5 run (verità 20) — contro la **baseline 11/20**
  del referto 11. Il difetto di completezza della cronologia è **chiuso**: ±1 gol, esatto
  (20) nel run 1.
- **Gol con autore: 21/22/21/22/19** — **tutti** i gol hanno `player_name`. Baseline: **zero**.
  È la causa diretta del blocker "Zero Eventi", ora rimosso (vedi sotto).
- **Distribuzione per periodo:** il run 1 è **perfetto** (5-0/4-0/5-1/6-0 = truth). Gli altri
  sbagliano solo la collocazione dell'unico gol del Libertas.
- **Gol del Libertas nel periodo giusto (P3):** **1/5** — solo il run 1 lo mette in P3; i run
  2/4/5 lo spostano in **P4**, il run 3 mette 2 gol in P4. Errore di periodo residuo, non di
  lettura del gol.
- **Roster:** casa **14/15 esatti + 1 approx, 0 mismatch** su tutti i run; ospite **9/13
  esatti (11 confrontabili) + 2 approx, 0 mismatch** (#5 e #10 vuoti in truth, fuori
  confronto). **Lo slittamento di numerazione dal #10 NON si ripresenta:** i numeri estratti
  dell'ospite sono `[1..9, 11, 12, 13]` in tutti i 5 run — la casella vuota #10 è percepita e
  11/12/13 restano ai numeri giusti.

**Rigori (novità V3.1).**
- **Tipi fuori enum: ELIMINATI.** `PENALTY_GOAL` (e ogni tipo non-enum) **0 occorrenze** su
  tutti i 6 casi × 5 run. Baseline referto 11: `PENALTY_GOAL` ×1. Il fix del prompt V3.1
  funziona: il gol su rigore è ora `type=GOAL` con `is_penalty`, quindi **conta**.
- **Il modello USA `is_penalty`:** 158 EXCLUSION_20 + 111 GOAL marcati su tutti i run.
- **Olympic vs 7 rigori-truth:** il modello marca **esattamente 7** espulsioni `is_penalty`
  (run 1–4; 8 nel run 5). Applicando la **regola derivata** (accoppiamento clock+periodo)
  all'estrazione: realizzati/non **5/2, 5/2, 6/1, 3/4, 4/4** — la truth derivata è **5/2**
  (run 1–2 esatti, run 3 vicino). **Limite di merito:** l'estrazione salva solo il minuto
  intero (`minute`), non `mm:ss`, quindi il match posizionale esatto (squadra+periodo+clock)
  con la truth non è calcolabile; sul multiset (squadra, periodo) l'overlap è **5/7**. Il
  modello marca tutte le 7 come `away` e **manca l'unica espulsione `home`** (fallo B#12 che
  dà il rigore al Libertas). Falsi positivi modesti (sovra-marcatura P3/P4, +1 nel run 5).

**Ricalcolo dei 4 blocker del referto 11 (livello FULL, per run).**
| Blocker baseline (referto 11) | Esito V3.1 |
|---|---|
| Zero Eventi (0 gol con autore) | **CHIUSO** — 0/5 run: tutti i gol hanno autore |
| Incoerenza eventi CASA (11 ≠ 20) | **Sostanzialmente chiuso** — ora 20/21/19/21/19; sparisce nel run 1, altrove ±1 |
| Per-periodo P3 OSPITE 0 vs 1 (difetto, PENALTY_GOAL scartato) | **Chiuso nel run 1**; riappare 2–5 solo perché il gol Libertas finisce in P4 |
| Per-periodo P4 OSPITE (eccesso) | Legato allo stesso errore di periodo del gol Libertas |

Nota: sul dato **grezzo del bench** compare un blocker "Riconciliazione incompleta" in tutti
i run — è un **artefatto**: il bench non esegue lo step di riconciliazione della pipeline
(mappa vuota → ogni evento con nome scatta), non si presenta in produzione. I blocker
*strutturali* del referto 11 sono chiusi o ridotti a rumore ±1; il residuo reale è la
**collocazione di periodo** dell'unico gol ospite.

**Validazione >3 espulsioni su dati reali: SCATTA.** Il check `players_over_exclusion_limit`
si attiva su più casi/run (es. Salerno `muro p.` 5, `garessan c.` 5; Triscelon `chinnici a.`
5; Olympic run 3 due giocatori a 4) — segnala correttamente lo sforamento del limite di 3,
sintomo di errore di lettura (nomi collassati o eventi duplicati). Il limite noto (raggruppa
per `player_name`) qui **non morde**, perché V3.1 fornisce gli autori: con nome presente il
check attribuisce e conta. Su un run degradato (Olympic run 5) compare un "giocatore" di
nome `4` — lettura degradata che il check comunque intercetta.

**Raccomandazione — cosa attaccare dopo.** Il prompt V3.1 ha **risolto la classe che lo ha
motivato** (autori dei gol → Zero Eventi chiuso; `PENALTY_GOAL` → tipo enum; completezza
cronologia 11→~20). I due residui, in ordine di valore:
1. **Collocazione di periodo del gol isolato** (Libertas P3→P4 in 4/5): è il difetto che
   tiene vivi i blocker per-periodo. Candidato: nel prompt, legare esplicitamente ogni gol al
   confine di periodo del cronometro (il clock a scalare riparte a ~8:00 a ogni periodo).
2. **Granularità del clock degli eventi** (`minute` intero invece di `mm:ss`): senza i
   secondi l'accoppiamento rigore↔gol e il match posizionale coi rigori-truth non sono
   verificabili con precisione. Candidato: chiedere il clock `mm:ss` nello schema eventi.
I due errori stabili sui **punteggi** (Bellator finale, Triscelon data) restano fuori portata
di V3.1 e appartengono alla strada §8.13 (doppia estrazione / check zona), non a questo giro.

### 8.16 Esperimento prompt V3.2 — clock mm:ss e ancoraggio di periodo (2026-07-22)

Variante sperimentale **V3.2** (`OCR_SYSTEM_PROMPT_V3_2@sha256:9661b340d9e1`), attacco ai
due residui di §8.15, entrambi sulla stessa riga del foglio (P3, clock 1:13: il gol isolato
del Libertas e l'unica espulsione-rigore lato CASA, fallo B#12). **Due sole modifiche additive
alla sezione EVENTI**, costruite per sostituzione mirata su V3 così che punteggi/nomi/data/
rigori restino **identici byte-per-byte** a V3.1 (verificato in test): (a) campo `clock`
(cronometro a scalare mm:ss) accanto a `minute`, con l'istruzione esplicita che gli stessi
valori si ripetono nei quattro periodi (il clock **non** identifica il periodo); (b) ancoraggio
di periodo rinforzato per gli **eventi isolati** (un evento appartiene alla SEZIONE in cui è
scritto anche quando è l'unico della squadra; quarter=null preferibile a un periodo indovinato).
V3.2 **non promossa**: V3.1 (`v3`) resta il default di produzione.

**Run parziale per cap di spesa.** `gemini-2.5-pro`, `--prompt-version v3_2 --repeat 5`. Il
run ha colpito a metà il **cap di spesa mensile del progetto Google** (429 RESOURCE_EXHAUSTED):
completati **4 casi su 6 × 5 = 20 chiamate riuscite** (pol-delta, unime, bellator, **Olympic**
— tutti 5/5 reali), falliti Salerno e Triscelon (10×429, costo ~0). **Costo reale: 20 chiamate,
57.120 token in, 102.561 out, ~$1,10** a listino ($1,25/$10 per M), latenza media 90s. Le
domande di misura sono tutte Olympic-centriche → rispondibili; le regressioni punteggi si
leggono sul **sottoinsieme comparabile dei 4 casi comuni** vs V3.1. Proposte in
`ocr_bench_out/gold_v3_2_20260722/` su dev (D1: mai riversate nei casi). **Nota ops: cap Gemini
esaurito** — nessuna chiamata reale passa finché Alberto non lo rialza/resetta.

**Risposte alle domande di misura.**
1. **Gol del Libertas in P3:** **1/5** (solo run 4) — **identico** al baseline V3.1 (1/5).
   L'ancoraggio rinforzato **non ha spostato il residuo**. Peggio: nei run 2 e 3 il gol away
   **sparisce del tutto** (0 gol ospite), mentre in V3.1 era presente in tutti e 5 i run.
2. **Espulsione-rigore CASA (B#12, home/P3/clock 1:13):** ora **misurabile per posizione
   esatta** grazie al clock. Estratta nella posizione esatta (home, P3, 1:13) in **2/5 run**
   (run 2 e 5) — baseline esatto **0/5**. Guadagno modesto e rumoroso, in realtà **sottoprodotto
   del clock** (risoluzione di posizione), non dell'ancoraggio.
3. **Clock mm:ss:** **popolato su ~100% degli eventi** (47–48/47–48 per run) e **plausibile**
   (formato mm:ss, valori a scalare). Baseline: 0. **Vittoria netta e indipendente dai residui.**
   Sblocca l'accoppiamento posizionale rigore↔gol, impossibile in V3.1.
4. **Completezza cronologia:** gol casa **21/25/23/21/21** (truth 20) — **più rumorosa** del
   baseline V3.1 (20/21/19/21/19): due run in **sovra-conteggio** (25, 23). Autori: **22/25/0/22/21**
   — il run 3 **perde tutti gli autori** (0/23), degrado assente in V3.1.
5. **Regressioni punteggi (4 casi comuni, 20 run):** V3.2 **40 stabili-corretti / 1 sbagliato /
   9 instabili / 2 ambigui** vs V3.1 **43 / 2 / 7 / 0** sugli stessi 52 campi. Il prompt dei campi
   punteggio è **byte-identico** fra V3.1 e V3.2 → lo scarto (−3 corretti, +2 instabili, +2 ambigui)
   è **varianza di campionamento, non regressione attribuibile al prompt**. Inversioni casa/
   trasferta **0/20** (V3.1 0/20 sugli stessi 4 casi).

**Accoppiamento rigore↔gol per posizione esatta (novità V3.2).** Truth Olympic derivata: **5
realizzati / 2 non** su 7 rigori. Match posizionale delle 7 espulsioni `is_penalty` estratte
contro la truth per (squadra+periodo+clock): **5/3/5/4/2 su 7** per run (in V3.1 era **0/7**
ovunque, il clock mancava). Coupling realizzati/non ricalcolato sull'estrazione: **5/2, 2/5,
6/2, 4/4, 2/7** (truth 5/2) — il run 1 azzecca esattamente 5/2, gli altri divergono. Il clock
rende la misura **possibile** ma l'estrazione degli eventi resta **instabile** su questo referto
denso.

**Lettura.** Il clock è una **vittoria di capacità di misura** (popolazione ~100%, sblocca il
match posizionale). L'**ancoraggio di periodo rinforzato NON ha ridotto il residuo 1** (gol
isolato in P3: 1/5 → 1/5) e la sezione eventi più pesante coincide con **più rumore** (gol away
droppato in 2/5, sovra-conteggio casa, un run senza autori). Il residuo di **collocazione di
periodo dell'evento isolato appare irriducibile via questo prompt**: la leva mirata (istruzione
esplicita sull'evento isolato) ha prodotto zero movimento. Va instradato alla strada §8.13
(doppia estrazione / lettura di zona), come i residui stabili sui punteggi, non a un altro giro
di prompt.

**Raccomandazione — NON promuovere V3.2.** Il residuo 1 è irriducibile via prompt (misurato:
nessun movimento). Il clock, però, è un guadagno reale e **indipendente**: se serve, va isolato
in una variante **clock-only** (senza il paragrafo di ancoraggio, che ha aggiunto peso e rumore
senza beneficio) e rimisurato **quando il cap Gemini è rialzato**. Decisione sui numeri: Alberto.
I due errori stabili sui punteggi restano in §8.13.

### 8.17 Variante clock-only V3.3 — implementata, misura RIMANDATA per cap di spesa Gemini (2026-07-23)

Seguito operativo diretto della raccomandazione di §8.16: isolare il **solo** guadagno reale e
indipendente di V3.2 — il campo `clock` mm:ss per evento — scartando l'ancoraggio di periodo per
gli eventi isolati, che in §8.16 ha prodotto **zero movimento** sul residuo di collocazione (gol
isolato Libertas P3: 1/5 → 1/5) e ha aggiunto peso e rumore alla sezione EVENTI (gol away droppato
in 2/5 run, un run senza autori, sovra-conteggio casa).

**Implementazione (fatta, a repo su dev).** Variante **V3.3** `OCR_SYSTEM_PROMPT_V3_3@sha256:dd9f2af28a1d`,
costruita per **sostituzione mirata su V3** con le **stesse due `.replace()` del clock di V3.2**
(istruzione mm:ss nella sezione EVENTI + riga di schema `"clock"`), **byte-identiche** a quelle di
V3.2, e **omessa** la terza `.replace()` dell'ancoraggio. Conseguenza strutturale, blindata a test
(`tests_ocr_bench.py`): **V3.3 = V3.1 + solo le due righe del clock** (togliendole si riottiene V3
byte-per-byte) e **V3.3 = V3.2 meno il solo blocco di ancoraggio** (riscrivendo in V3.2 l'ancoraggio
rinforzato con quello originale di V3.1 si ottiene V3.3). Quindi qualunque scarto misurato tra
V3.1/V3.2 e V3.3 sulle zone invariate è **varianza di campionamento, non effetto del prompt**.
Selezionabile dal bench (`ocr_bench --prompt-version v3_3`, registry-driven come le altre) e via
`settings.OCR_PROMPT_VERSION`. **NON promossa**: il default di produzione resta `v3` (V3.1); l'hash
è fissato a test come per V2/V3/V3.2 (un cambio deve essere esplicito, non silenzioso).

**Misura sul gold: RIMANDATA — cap di spesa Gemini ancora attivo.** Prima mossa del giro (come da
§8.16 "Stato aperto"): **una singola** chiamata reale di sonda sul caso più economico (Unime,
`--repeat 1`, prompt di default). Esito **429 RESOURCE_EXHAUSTED**, ma con un messaggio ora
**esplicito** che **falsifica l'ipotesi rate-limit di §8.16**: `"Your project has exceeded its
monthly spending cap"`. Non è un limite per-minuto auto-resettato: è il **cap di spesa mensile del
progetto Google**, un blocco duro che si sblocca **solo** rialzando/resettando il cap dalla console
AI Studio (`https://ai.studio/spend`) — azione di Alberto, fuori dal perimetro batch. Nessuna altra
chiamata reale tentata dopo la sonda. La misura sul gold di V3.3 (protocollo §8.12/§8.15, tutti e 6
i casi **inclusi Salerno e Triscelon**, con le domande Olympic-centriche di §8.16: stabilità del
clock, match posizionale dei rigori per (squadra+periodo+clock), completezza cronologia, regressioni
punteggi sui casi comuni) resta **da eseguire al primo giro a cap rialzato**.

**Attesa da falsificare alla misura.** Sul residuo di collocazione di periodo dell'evento isolato:
**nessun movimento atteso** — V3.3 non tocca l'ancoraggio, e il muro è già dichiarato in §8.16 come
irriducibile via prompt (va alla strada §8.13, doppia estrazione per zona). L'ipotesi vera da
verificare è che V3.3 **conservi il guadagno del clock** (popolazione ~100%, sblocco del match
posizionale rigore↔gol) **senza** il rumore sugli eventi introdotto dal blocco di ancoraggio di
V3.2. Decisione di promozione: Alberto, sui numeri del bench.

### 8.18 Gold referto 8 a truth + variante V3.4 (timeout + espulsione definitiva) — implementata, misura RIMANDATA per cap Gemini (2026-07-23)

Giro interamente **offline** (cap di spesa Gemini ancora attivo, §8.17: nessuna chiamata reale tentata). Due obiettivi entrambi non-OCR.

**(1) Referto 8 (Unime vs Nautilus Roma, 12-10) promosso a truth su EVENTI e ROSTER.** Trascrizione umana del cartaceo (Alberto), stessa forma del referto 11 (§8.14). **51 eventi**: 22 gol (12 casa Unime + 10 ospite Nautilus), 24 esclusioni di 20 secondi, **3 timeout** e **1 espulsione definitiva** (EDCS, art. 9.13); 2 roster (casa 14, ospite 12). `match_info` e attribuzione casa/trasferta **non toccati** (restano quelli già fissati: home = Unime). Le **4 asserzioni derivate esterne** (calcolate a valle dalla cronologia, non dal dato stesso) sono verificate e **TUTTE COINCIDONO**:
- parziali per tempo **4-2 / 3-1 / 3-4 / 2-3**, finale **12-10** (corroborazione: gol-per-periodo derivati dalla storia cronometrica == riquadro parziali, registrata in `corroboration`, stato *concorde* — necessaria perché il caso è a `legibility.score` 2);
- **fouled out** (≥3 esclusioni di 20 secondi): **SOLO casa #3 e casa #12**, nessun altro in nessuna delle due squadre;
- **nessun giocatore supera 3** esclusioni (il check gold `players_over_exclusion_limit` resta a zero violazioni);
- **3 rigori**, di cui **2 realizzati** (P3 6:48 → gol ospite #9 stesso clock; P4 4:23 → gol ospite #4 stesso clock, entrambi del Nautilus su fallo Unime) e **1 NON realizzato** (P2 6:20, nessun gol a quel clock). L'accoppiamento rigore→gol resta una **regola derivata a valle**, non codificata in truth.

**Due casi-limite ratificati da Alberto, non-errori:** (a) **omonimia legittima** roster casa #11 e #13 = `sciabà g.` (fratelli, stesso cognome e iniziale); (b) **buco di numerazione** roster ospite senza il #3 (l'allenatore non ha convocato il massimo). Validazione **verificata, nessuna modifica richiesta**: il duplicato-nome emette al massimo un **warning informativo** (`"Duplicati: Nomi giocatore duplicati"`), **mai** un blocker (non è fra i `critical_keywords` di `assess_publish_readiness`); il buco di numerazione non genera **né** warning **né** blocker (l'unicità opera sui numeri presenti, la dimensione tollera 7-15). Il `normalized_data` del report 8 resta invariato: la truth eventi è **materiale di misura del bench**, non si riversa nel report (che resta NEEDS_REVIEW).

**(2) Variante prompt V3.4** `OCR_SYSTEM_PROMPT_V3_4@sha256:4e9751eded9b` — **V3.4 = V3.3 (clock-only) + due semantiche nuove**, costruita per **sostituzione mirata su V3.3** (stesso meccanismo `.replace()` di V3.2/V3.3; ogni altra zona identica byte-per-byte a V3.3, blindato a test: rimuovendo le tre aggiunte si riottiene V3.3 e l'hash di V3.3 `dd9f2af28a1d` resta invariato):
- **(A) TIMEOUT di squadra**: sul foglio `T.O.` con asterisco nella colonna della squadra; estratto come evento con `team` e `clock`, **senza calottina** (`player_name` null — il timeout è della squadra, non del giocatore);
- **(B) ESPULSIONE DEFINITIVA** (`EXCLUSION_DEF`, sigla EDCS o equivalente): il prompt **NON** insegna la tassonomia degli articoli — riconosce solo che la riga è un'espulsione definitiva e non un gol, estrae l'**articolo verbatim** (`regulation_article`, es. `"9.13"`) e la **sigla verbatim** (`sanction_sigla`). Trappola OCR neutralizzata **esplicitamente**: l'articolo sta nella colonna del punteggio (nel referto 8 la riga sopra è il gol del 10-8) e **assomiglia a un punteggio**, ma è un ARTICOLO e non deve **mai** entrare nella progressione del punteggio.

La **mappatura articolo → tipo** vive nel **nostro codice** (`matches/event_types.py`: `DEFINITIVE_EXCLUSION_ARTICLES` + `classify_definitive_exclusion`), non nel prompt, come **tabella dati esplicita** popolata **solo** con i due articoli verificati (`9.13` = cattiva condotta, senza rigore; `9.14` = brutalità, con rigore e squalifica). Qualunque altro articolo finisce nel ramo **sconosciuto** che conserva la stringa grezza e non blocca. Scelta di modello: `EXCLUSION_DEF` è un **tipo a sé** (non un attributo di `EXCLUSION_20`) perché il conteggio fouled-out/over-limit opera su `EXCLUSION_20` e il pooling corromperebbe quel conteggio (una definitiva non è una delle tre esclusioni di 20 secondi); inoltre porta campi che nessun altro evento porta. **NON** ancora fra i `DEFAULT_EVENT_TYPES` canonici pubblicabili: l'integrazione nel pipeline di pubblicazione (MatchEvent) è **fuori scope** di questo giro (report 8 non pubblicato).

**V3.4 NON promossa**: default di produzione resta `v3` (V3.1). Selezionabile dal bench (`ocr_bench --prompt-version v3_4`) e via `settings.OCR_PROMPT_VERSION`. Hash fissato a test come per le altre versioni.

**Stato di misura: sia V3.3 sia V3.4 sono DA MISURARE, bloccate dal cap di spesa Gemini** (§8.17). Nessuna chiamata reale in questo giro. La misura sul gold di entrambe resta al primo giro a cap rialzato (azione di Alberto sulla console AI Studio). Nuovi test a guardia (tutti mockati, verdi): hash V3.4, semantiche A/B presenti in V3.4 e assenti in V3.3, reversibilità V3.4→V3.3, mappatura `9.13`/`9.14`/sconosciuto, e le asserzioni derivate del referto 8 (fouled out casa #3/#12, timeout senza calottina, articolo mai come punteggio, rigore P2 non accoppiato).

### 8.19 Misura tre bracci V3 / V3.3 / V3.4 sul gold — clock, timeout, espulsione definitiva (2026-07-23)

Cap Gemini **ripristinato** (progetto `careful-yew-501810-s1` a 100 €/mese). Prima misura reale delle due varianti mai misurate (§8.17 V3.3, §8.18 V3.4) contro il baseline V3, **tre bracci nello stesso run** — protocollo §8.12/§8.15 (`--repeat 5`, tutti e 6 i casi gold, Triscelon con `--image`, preprocessing on):
- `v3` baseline `OCR_SYSTEM_PROMPT_V3@sha256:be51e9c6bc42` (V3.1, default di produzione)
- `v3_3` clock-only `@sha256:dd9f2af28a1d`
- `v3_4` clock + timeout + espulsione definitiva `@sha256:4e9751eded9b`

**90 chiamate reali** (3 × 6 × 5), `gemini-2.5-pro`, **zero 429** in tutto il run (~2h30, sequenziale). **Costo effettivo: $5,05** (256.080 tok in @1,25/M = $0,32; 472.901 tok out @10/M = $4,73 — l'output alto è il referto 8, 50+ eventi). Proposte in scratchpad (D1: mai riversate nei casi). **Baseline rimisurato in questo run**, non ripreso da §8.15: il gold è cambiato (referto 8 promosso a truth, §8.18) e l'estrazione è stocastica.

**Trappola del denominatore neutralizzata**: timeout ed espulsione definitiva sono FUORI dal contratto di V3 e V3.3. Le metriche generali (assi a-f) li **escludono** dal confronto; timeout ed `EXCLUSION_DEF` vivono in un **asse separato (g), misurato solo su V3.4**.

**Tabella per braccio (assi a-h):**

| Asse | v3 (baseline) | v3_3 (clock) | v3_4 (clock+TO+EDCS) |
|---|---|---|---|
| **a** punteggi/parziali/data — *stabili-corretti* (su 78 campi = 13×6) | **57** sc / 1 sw / 15 inst / 5 amb | **60** sc / 1 sw / 13 inst / 4 amb | **61** sc / 2 sw / 11 inst / 4 amb |
| **b** completezza eventi-gol referto 8 (denom = solo GOAL, 22) | 22–23/22 (5 rip) | 22/22 (5 rip) | 22/22 (5 rip) |
| **c** clock mm:ss su gol referto 8 — copertura / *giusto-e-al-posto* | **0/22** (nessun clock) | **22/22** / [20,14,20,19,18] ≈ **83%** | **22/22** / [10,15,14,19,19] ≈ **70%** |
| **d** rigori referto 8 (2 realizzati P3 6:48 + P4 4:23; 1 NON P2 6:20) | non collocabile (no clock) | 2 realizzati agganciati, **P2 6:20 mai accoppiato** ✓ | come v3_3 ✓ (flag `is_penalty` sull'esclusione incostante, ~2-3/5) |
| **e** fouled out derivato (atteso casa `geloso`#3 + `cama`#12, nessun altro) | **rumoroso**: manca spesso #3/#12, aggiunge nomi spuri | **rumoroso** (1 rip `over-limit` >3) | **rumoroso** (1 rip `over-limit` >3) |
| **f** collocazione periodo referto 8 (residuo §8.16) | **nessun movimento** (5/5 match) | **nessun movimento** (5/5) | **nessun movimento** (5/5) |
| **g** timeout / EDCS (solo V3.4) | fuori contratto | fuori contratto | **timeout 3,3,2,3,3** (4/5 pieni); **EDCS 1/1 ogni rip**, art `9.13` + sigla `EDCS` verbatim, `classify`→noto *misconduct*; **finale 12-10 in tutte** (articolo NON entra nel punteggio), **mai tipizzato GOAL** ✓ |
| **h** errori stabili noti | Bellator finale casa **5** (truth 4) *stabile*; Triscelon data **28** (truth 25) instabile 4/5 | Bellator **5** *stabile*; Triscelon **28** instabile 4/5 | Bellator finale casa **8** (instabile 8×4/5×1) — **valore DIVERSO**; Triscelon data **28** *ora stabile 5/5* |

**Lettura onesta — asse a (ciò che la produzione pubblica oggi):** i tre bracci sono **statisticamente indistinguibili** sui punteggi/parziali/data. Lo scarto 57→60→61 stabili-corretti **non è un guadagno di qualità**: è la stessa banda di rumore (instabile 15→13→11) che si risolve diversamente fra campioni. La prova è nell'asse h — **nessun braccio corregge un solo errore stabile**, si limitano a **spostarlo**: Bellator finale casa passa `5`→`5`→`8` (V3.4 lo legge *peggio* e lo destabilizza), Triscelon data resta `28` e V3.4 la **stabilizza sul valore sbagliato** (5/5, peggio per la rilevabilità di un'instabile 4/5), e su V3.4 spunta un nuovo stabile-sbagliato (Olympic Q3 ospite `0`). Conferma diretta di §8.13/§8.16: **gli errori stabili di finale/parziali/data appartengono alla strada doppia-estrazione/zona, non al prompt.**

**Guadagni reali e unici:**
- **V3.3 → clock (asse c):** copertura da 0 a **100%**, correttezza-e-collocazione ≈ **83%**; additivo, **nessuna regressione** su punteggi (asse a non-inferiore) e **zero movimento di periodo** (asse f). L'aggancio posizionale dei rigori (asse d) diventa possibile e sul referto 8 **non produce falsi accoppiamenti** sul rigore NON realizzato.
- **V3.4 → timeout + espulsione definitiva (asse g):** è l'unico braccio che estrae 3 timeout (4/5 pieni) e l'EDCS con articolo `9.13` verbatim, **senza corrompere il punteggio** (finale 12-10 in tutte le 5, articolo mai nella progressione) e **senza tipizzarla GOAL**. Esattamente il contratto di V3.4, verificato. Ma il clock di V3.4 è **più rumoroso** di V3.3 (70% vs 83%) e Bellator vi deriva a un valore peggiore.

**Guadagno mancato (asse e):** il **fouled out derivato è inaffidabile in tutti e tre i bracci** — nessuno ricostruisce stabilmente `{geloso #3, cama #12}`, tutti aggiungono nomi spuri e V3.3/V3.4 producono in una ripetizione un `over-limit` >3 (impossibile a regolamento). Derivare il fouled-out dalle esclusioni OCR **non è affidabile a nessun prompt**: dipende da una lettura pulita di 24 esclusioni per calottina, che il modello non garantisce.

**RACCOMANDAZIONE (la decisione è di Alberto, nulla promosso a default in questo giro):** **non promuovere né V3.3 né V3.4 a default di produzione su questi numeri.** L'unica cosa che la produzione pubblica oggi — punteggi/parziali/data — è indistinguibile fra i tre bracci, e i guadagni genuini di V3.3 (clock) e V3.4 (timeout/EDCS) sono su campi che la **pipeline pubblicabile non consuma ancora**: il clock non è persistito da nessuna parte, e `TIMEOUT`/`EXCLUSION_DEF` non sono `MatchEvent` canonici (**debito §10.35**). Promuovere ora cambierebbe il prompt di produzione per **zero beneficio visibile in produzione**, con V3.4 che costa più token in output e legge il clock un po' peggio.

**Cosa falsificherebbe questa raccomandazione (e giustificherebbe la promozione):**
- **V3.3** diventa promuovibile quando il **clock viene effettivamente consumato a valle** (ordinamento eventi dentro il periodo, o aggancio rigore→gol cablato nella pipeline): a quel punto, se una rimisura conferma clock ≥ ~80% e punteggi non-inferiori, si promuove V3.3 (additiva, a rischio zero sull'asse a).
- **V3.4** diventa promuovibile quando **§10.35 è chiuso** (`EXCLUSION_DEF`/`TIMEOUT` nei `DEFAULT_EVENT_TYPES` + `MatchEvent` + sport config + migration) **e** una rimisura su un gold con più referti a eventi conferma estrazione timeout/EDCS ≥ ~4/5 **senza regressione di punteggio** vs V3.3 — V3.4 sussume il clock di V3.3.
- In negativo: se una **ri-esecuzione** mostrasse V3.3/V3.4 **materialmente** meglio sull'asse a (es. +5 stabili-corretti con instabile che scende, e che **sopravvive** al ricampionamento), la tesi "è solo rumore" cadrebbe. Questo run mostra il contrario: le differenze sono nella banda di rumore e gli errori stabili si limitano a rilocarsi.

**Nessun movimento su §8.16** (asse f): il muro di collocazione periodo regge in tutti e tre i bracci (5/5 match sul referto 8). La conclusione registrata in §8.16 non è contraddetta.

### 8.20 Braccio Gemini 3 Flash + cross-check Pro↔Flash come rilevatore d'errore (2026-07-23)

Doppio obiettivo, prompt **invariato** (`v3_4 @sha256:4e9751eded9b`, nessuna V3.5): (1) misurare **gemini-3.6-flash** contro il baseline di produzione `gemini-2.5-pro` sul gold; (2) esperimento cross-check — verificare se il **disaccordo** fra i due modelli sullo stesso campo predice l'errore vero (gold = arbitro), come possibile flag della review page che catturi anche gli **errori stabili** che l'instabilità intra-modello non vede (§8.19, caso Triscelon).

**Selezione modello e minimizzazione reasoning.** Fra le flash stabili di generazione 3+ disponibili sull'API (`gemini-3.5-flash`, `gemini-3.6-flash`; `gemini-3-flash-preview` è preview → esclusa) la 3.6 è **strettamente la più economica**: stesso input (\$1,50/M) di 3.5 ma output **\$7,50/M** vs \$9,00 e ~17% meno token di output. Reasoning azzerato con `thinking_level='minimal'` (verificato: `'none'` rifiutato, `'low'` brucia già ~44 thought token, `'minimal'` → **0 thought token** su tutte le 30 chiamate). Nessun tocco a `config/settings.py`: la selezione modello passa da `--models`, il reasoning da un nuovo seam per-chiamata `extract_data(thinking_level/thinking_budget)` con **default None su entrambi ⇒ config di generazione byte-identica alla produzione** (guardie mockate). Il braccio Pro v3_4 è **riusato** dal run §8.19 (stesse 30 proposte, hash prompt identico): nessuna ri-esecuzione, budget risparmiato.

**Braccio Flash — 30 chiamate reali** (6 casi × `--repeat 5`, Triscelon con `--image`), zero 429, **0 thought token**. **Costo \$1,41** (121.610 tok in @1,50/M = \$0,18; 163.752 tok out @7,50/M = \$1,23). Media 4.054 in / 5.458 out per chiamata → **~\$0,047 per estrazione**, contro ~\$0,056 del blended Pro §8.19 (\$5,05/90): Flash **~16% più economico per referto**, non il 65% dei titoli (quello è agentico long-horizon; sull'OCR a singolo colpo l'output domina e lo sconto è modesto, per giunta l'input Flash è più caro di Pro).

> **Correzione costo Pro (§8.21).** Il ~\$0,056/referto di Pro qui **omette i token di thinking**, fatturati come output: il costo reale di Pro misurato in produzione è **~\$0,14/referto** (thinking ~1,9× l'output visibile). Flash girava a `thinking_level='minimal'` (0 thought token), quindi **il confronto ~16% è distorto in favore di Pro**: a parità di misura (thinking incluso per entrambi) Flash è **molto** più economico. Dettaglio in §8.21.

**Asse a (78 campi = 13×6, ricalcolato dal modulo versionato — riproduce §8.19 su Pro):**

| Braccio | stabili-corretti | stabili-SBAGLIATI | instabili | ambigui |
|---|---|---|---|---|
| Pro v3_4 (2.5-pro, §8.19) | 61 | **2** | 11 | 4 |
| **Flash v3_4 (3.6-flash)** | **65** | **0** | 12 | 1 |

Lettura onesta (regola §8.12/§8.19): il +4 stabili-corretti è **nella banda di rumore** e non basta da solo a giustificare uno switch. Il dato più solido è **stabili-sbagliati 2→0**: Flash **non riproduce nessuno dei due errori stabili di Pro** (Olympic Q3 ospite `0` e Triscelon data `28`), li legge entrambi **giusti**. Nessuna inversione casa/trasferta.

**Blocco duro sugli eventi: Flash non attribuisce gli autori dei gol.** Su **tutti e 6** i casi Flash estrae i gol (conteggio e clock) ma con `player_name` **null**: gol-con-autore **0/22, 0/24, 0/23, 0/21, 0/28, 0/32**. Pro attribuisce su 5/6 (22, 24, 27, 17/20, **0** su Salerno ruotato, 32). Il campo esiste nello schema Flash, resta vuoto. Conseguenza diretta: al livello `FULL` il gate autori / "Zero Eventi" (Policy A strict) **abortirebbe ogni pubblicazione**. Timeout/EDCS invece Flash li legge bene (timeout 3,3,3,3,3 — meglio del 3,3,2,3,3 di Pro; EDCS 1/1 ovunque). Avvertenza di causalità: `v3_4` è stato scritto e tarato **su Pro**; lo zero-autori potrebbe essere un artefatto di prompt-interaction su Flash, non un limite del modello — è una condizione di falsificazione, non una condanna.

**Cross-check Pro↔Flash (78 campi comparabili, 0 esclusi null):**

| Classe | Conteggio |
|---|---|
| concordi-e-giusti | 70 |
| **concordi-e-SBAGLIATI (cieco)** | **0** |
| discordi, almeno uno giusto | 4 |
| discordi, entrambi sbagliati | 4 |

| Metrica del disaccordo come predittore d'errore | Valore |
|---|---|
| campi in errore (≥1 braccio sbagliato) | 8 |
| **recall_union** (errori catturati dal disaccordo) | **100% (8/8)** |
| **blind_rate** (concordi-e-sbagliati / errori) | **0% (0/8)** |
| precision_union | 100% (per costruzione: due valori diversi non sono entrambi la verità) |
| tasso concordi-e-sbagliati / comparabili | **0% (0/78)** |
| recall_pro (errori del braccio di produzione catturati) | **100% (7/7)**, ciechi 0 |

**Verifica esplicita dei casi noti (§8.19):**
- **Triscelon data** (Pro stabile-sbagliato `2026-04-28`, truth `2026-04-25`): Flash la legge **giusta e stabile** → **DISCORDI, catturato**. Esattamente ciò che l'instabilità intra-modello *non* può fare (l'errore è stabile 5/5 su Pro): il cross-check inter-modello lo espone perché Flash non lo condivide.
- **Bellator finale casa** (truth 4): Pro `8`, Flash `7` — **entrambi sbagliati ma su valori diversi** → DISCORDI, flaggato (nessuno dei due dà la verità: il flag dice "rivedi qui", non corregge).
- L'altro stabile-sbagliato di Pro (Olympic Q3 ospite `0`, truth 1): Flash legge `1` → DISCORDI, catturato.

Gli altri disaccordi (Salerno home/away name, Triskelion/Triskelon, date Salerno) sono in parte **varianti ortografiche di nome squadra** che il layer alias risolve in produzione: contano come "errore" solo sul confronto stretto `name_on_paper`, e vanno normalizzati **prima** di flaggare per non generare falsi allarmi.

**Limiti del metodo (dove è cieco).** Il cross-check è un **rilevatore**, non un correttore: 4 disaccordi su 8 hanno **entrambi** i bracci sbagliati (flag corretto, ma la verità la mette l'umano). Il rischio unico è la cella **concordi-e-sbagliati**, qui **0/8**: ma 8 errori su 6 referti è un campione sottile, e lo zero **non è strutturale** — su Bellator i due modelli *potevano* convergere sullo stesso "4→8" e non l'hanno fatto per caso. Un singolo referto con una cifra fisicamente ambigua che *entrambi* leggono uguale-sbagliata sposterebbe la metrica.

**Precisazione statistica — il denominatore che conta è 8, non 78.** Il "0% concordi-e-sbagliati su 78 campi" è corretto, ma per un **rilevatore d'errore** il denominatore rilevante è il numero di **errori** (8), non i campi totali (78). Con **8 errori e 0 mancati**, la regola del tre dà un limite superiore al 95% sul tasso di mancati ≈ **3/8**: il **recall vero potrebbe essere anche solo ~62%**. Lo 0% osservato è quindi compatibile con un tasso di cattura reale ben sotto il 100%. Il cross-check resta giustificato come **flag per l'occhio umano**, **non** come garanzia di cattura totale — serve un gold più grande per stringere l'intervallo.

**RACCOMANDAZIONE (decisione di Alberto sui numeri, nulla promosso in questo giro):**
- **Flash NON sostituisce Pro** come OCR di produzione al livello `FULL`: lo zero-autori sui gol romperebbe il gate Policy A. Il guadagno su asse a è banda di rumore e il risparmio (~16%/referto) non compensa la regressione eventi. **Nicchia reale**: Flash è candidato per i publish `SCORE_ONLY` (Opzione A) — legge punteggi/parziali/data **non-inferiore** a Pro e lì gli autori sono irrilevanti (nessun `MatchEvent`).
- **Il cross-check MERITA un pilot** come flag della review page sui campi **punteggi/parziali/data** (non sugli eventi, dove l'output senza-autore di Flash sarebbe rumore): su questo gold cattura il 100% degli errori-campo, **inclusi i due stabili di Pro che il ricampionamento non vede**, con 0 ciechi. Costo del secondo lettore trascurabile (~+\$0,047/referto con Flash). È un **detector per l'umano**, non un auto-correttore.

**Cosa lo falsificherebbe:**
- *Cross-check*: un gold più grande/difficile con **concordi-e-sbagliati > 0 in modo materiale** (i due modelli che convergono sulla stessa cifra sbagliata) — il blind spot è tutto il rischio e 6 referti sono pochi. O reviewer che ignorano il flag perché scatta troppo su varianti-nome benigne (serve normalizzazione alias **prima** del flag).
- *Flash-come-secondo-lettore*: se su volume la diversità architetturale che oggi dà blind=0 si rivelasse correlata (stessi OCR sbagliano insieme sui fogli degradati).
- *Flash-sostituisce-Pro* si riapre se un prompt **tarato su Flash** recupera l'attribuzione autori ≥ Pro senza regressione sui punteggi (lo zero-autori attuale può essere artefatto del prompt Pro-centrico).

Strumento versionato a repo (lezione §8.19): `matches/services/ocr_bench_analysis.py` (assi a/eventi + cross-check) e `matches/management/commands/ocr_crosscheck.py`, con test mockati; le proposte restano fuori repo (D1, gitignore). Costo totale reale del giro: **\$1,41** (solo il braccio Flash; Pro riusato, probe modello trascurabili).

### 8.21 End-to-end di produzione sul referto 8 — V3 / gemini-2.5-pro (2026-07-23)

Con il deploy §2.12 in esercizio (prompt di produzione **V3**, `gemini-2.5-pro`), estrazione end-to-end sul referto 8 (Unime vs Nautilus Roma) attraverso la pipeline reale.

**Campi che la produzione pubblica (asse a): 12/13 corretti.** Punteggio finale, tutti i parziali e i nomi squadra giusti. **Unico errore: la data**, letta `2006` invece di `2026` (errore di cifra sull'anno). È la classe di errore dichiarata **irriducibile via prompt in §8.16** (come la data Triscelon): campo singolo, senza ridondanza interna, che nessun check di coerenza cattura.

**Eventi e roster (assi che il bench NON confronta), collazionati contro la truth del gold:**
- **Gol: 22/22**, distribuzione per periodo `4-2 / 3-1 / 3-4 / 2-3` — coincide con la truth (finale 12-10). Nessun gol inventato o mancante sul campione rappresentativo.
- **Roster ospite: 12 voci, buco al #3 rispettato, nessun giocatore inventato** (`unresolved_in_truth = 0`).
- **Timeout**: conteggio corretto (3) ma **squadra sbagliata** sulla coppia del 4° periodo (i due timeout casa dell'Unime confusi con l'ospite).
- **Espulsione definitiva**: emessa come `RED_CARD` (V3 non conosce `EXCLUSION_DEF`, introdotto solo in V3.4 §8.18): l'evento reale — casa #7 d'angelo v., art. 9.13 — c'è, ma il tipo è generico e **instabile** fra le ripetizioni (0–2 `RED_CARD` per estrazione), con occorrenze **inventate** (es. ospite #7 cionfi m.: **stesso numero di calottina attribuito all'altra squadra**). In pallanuoto `RED_CARD` ed `EXCLUSION_DEF` sono lo **stesso evento reale** (il rosso *è* l'espulsione definitiva): vedi **debito §10.35** (riformulato di conseguenza).
- **Espulsioni di 20 secondi**: **attribuzione di squadra sbagliata nel 1° tempo** (truth 2 casa + 2 ospite).

**Questi errori vanno alla strada §8.13 (doppia estrazione per zona), NON a un altro giro di prompt engineering.** Squadra dei timeout, rosso duplicato per numero di calottina uguale, attribuzione di squadra delle espulsioni: sono errori di **collocazione/attribuzione sulla griglia**, la stessa famiglia dei residui stabili di finale/parziali/data. **Il muro è già dichiarato in §8.16** e cambiare il prompt non lo ha scalfito (§8.16, §8.19): la leva è la lettura di zona indipendente, non un'altra V3.x.

**Costo reale per referto — correzione: ~\$0,14, non ~\$0,06.** Misurato oggi in produzione su `gemini-2.5-pro`: **2.559 token in, 4.613 out, 8.784 di thinking**. I token di ragionamento sono **fatturati come output**, quindi il costo reale è `2.559 × \$1,25/M + (4.613 + 8.784) × \$10/M ≈ \$0,003 + \$0,134 ≈` **\$0,14 per referto**. Le stime precedenti (~\$0,044 §8.13, ~\$0,056 §8.20) contavano **solo l'output visibile** e **omettevano il thinking** (qui ~1,9× l'output visibile), sottostimando di ~2,5×. **Il braccio Flash (§8.20) risultava vicino a Pro anche perché girava con `thinking_level='minimal'` (0 thought token)**: a parità di misura — thinking incluso per Pro, assente per Flash — Flash è **molto** più economico di Pro, non ~16%. I costi-totali-run storici del §8 (a listino sui soli token di output visibili) vanno letti come **limite inferiore**.

### 8.22 Zero-autori di Flash: la causa è il budget di ragionamento, non il prompt né il modello (2026-07-23)

Giro dedicato a spiegare il **blocco duro** registrato in §8.20: con `gemini-3.6-flash`, prompt `v3_4`, `thinking_level='minimal'` (0 thought token), su tutti e 6 i casi del gold Flash estraeva i gol (conteggio e clock) ma con `player_name` **null** — gol-con-autore 0/22, 0/24, 0/23, 0/21, 0/28, 0/32 — mentre leggeva punteggi/parziali/data bene. §8.20 aveva chiuso con "Flash solo `SCORE_ONLY`", ma segnalando che lo zero-autori *poteva* essere un artefatto del prompt Pro-centrico, **condizione di falsificazione, non condanna**. Questo giro la falsifica.

**Tre ipotesi, in ordine di costo crescente per essere smentite.** H1 — budget di ragionamento: `thinking_level='minimal'` non basta a leggere i nomi manoscritti (è un **parametro**, non il prompt). H2 — prompt: `v3_4` è tarato su Pro e non insiste sull'obbligatorietà dell'autore. H3 — limite del modello: Flash non sa leggere quei nomi. Si procede a scala, ci si ferma al primo gradino che risponde.

**GRADINO 1 — H1 CONFERMATA al primo colpo.** Una sola chiamata sul referto 8 (il più denso, roster verificato, gold=truth), Flash + `v3_4` **invariato byte-per-byte**, `thinking_level='high'` (contro `'minimal'` di §8.20). Comando:
```
python manage.py ocr_bench --gold-case 2026-03-28_unime_vs_nautilus-roma \
  --models gemini-3.6-flash --prompt-version v3_4 --thinking-level high
```
Esito: **22/22 gol con `player_name` valorizzato** (IANNE P., D'ANGELO V., GARRIA A., MILANA L., …) — a `minimal` erano 0/22. `tok_thk` 0 → **10.516**. La causa dello zero-autori è il **budget di ragionamento**: a `minimal` il modello non spende ragionamento sui nomi manoscritti; alzato a `high` li legge. **H2 e H3 non vanno nemmeno testate** (protocollo a scala): H3 in particolare è falsificata dal fatto stesso che gli autori compaiano. **`v3_4` NON è stato toccato** — resta identico a §8.19/§8.20, nessuna variante `v3_4_flash` creata.

**GRADINO 3 — misura sulla configurazione vincente** (Flash 3.6 + `v3_4` invariato + `thinking_level='high'`), 6 casi, `--repeat 3`. Due assi separati.

**Asse AUTORI (sui gol):**

| Caso | gol estratti (r1/r2/r3) | con `player_name` | con calottina | coincidenza cognome↔truth |
|---|---|---|---|---|
| pol-delta | 24/24/24 | **100%** | 0 | n/d (truth senza roster/cap) |
| unime (ref. 8) | 22/22/22 | **100%** | 0 | **18 esatti + 4 a-una-lettera + 0 sbagliati / 22** (repeat allineato) |
| bellator-frusino | 21/22/21 | **100%** | 0 | n/d |
| olympic | 21/21/21 | **100%** | 0 | 5–9 esatti, 1–2 sbagliati (dove allineato) |
| sc-salerno | 29/29/30 | **100%** | 0 | n/d |
| triscelon | 32/30/32 | **100%** | 0 | n/d |

- **Nomi**: recuperati sul **100% dei gol**, tutti i casi, tutte le ripetizioni. È la metrica operativa: rimuove il gate autori / "Zero Eventi" (Policy A strict) che a `minimal` avrebbe abortito ogni publish `FULL`.
- **Calottine**: **0 ovunque**, e non è un errore di Flash: lo schema evento di `v3_4` **non ha un campo calottina** sul gol (solo `player_name`; il `number` esiste solo nel roster). Flash emette il **nome**, che è per giunta la chiave con cui la pipeline riconcilia (`converters.py` aggancia per nome, non per calottina) — quindi il nome recuperato è esattamente ciò che sblocca il `FULL`.
- **Coincidenza col la truth**: misurabile **solo su unime e olympic**, gli unici due casi con roster verificato + calottina sui gol nella truth (gli altri quattro hanno `goal_events_with_cap=0`: nessun ground-truth per l'autore, quindi "n/d", non un errore). Dove misurabile i cognomi agganciano la truth in larga maggioranza, con **zero cognomi palesemente sbagliati** su report 8 nella ripetizione ben allineata.

**Asse A (punteggi/parziali/data) — NESSUNA regressione.** Bucket stability-aware su 78 campi (13×6), confronto diretto con la baseline `minimal` di §8.20:

| | stabili-corretti | stabili-SBAGLIATI | instabili | ambigui |
|---|---|---|---|---|
| §8.20 Flash `minimal` | 65 | **0** | 12 | 1 |
| §8.22 Flash `high` | **66** | **0** | 12 | 0 |

Zero stabili-sbagliati su finale/parziali/data in entrambe le configurazioni: alzare il ragionamento **non degrada** ciò che Flash già faceva bene (il +1 stabile-corretto è banda di rumore). I campi finale/quarto che a occhio sembravano "sbagliati" (bellator finale casa, salerno quarti) sono **instabili**, non stabili-sbagliati, e pre-esistenti (bellator finale casa Flash lo leggeva già `7` a `minimal`, §8.20).

**Costo.** Giro intero: **19 chiamate reali** (1 gradino 1 + 18 gradino 3), **77.027 tok in / 108.363 tok out / 243.672 tok di thinking**, **$2,76** (sotto il tetto di $3). Tutto BENCH-ONLY: nessun default di produzione toccato (`OCR_PROMPT_VERSION` resta `v3`, modello `gemini-2.5-pro`, thinking di default `None`).

**Conseguenza economica — la leva che risolve gli autori erode il vantaggio di costo di Flash.** A `thinking_level='high'` Flash consuma ~12–16k thought token/referto (fatturati come output a $7,50/M): costo reale ~**$0,15/referto**, sostanzialmente **pari a Pro** (~$0,14, §8.21). Il ~16% di risparmio di §8.20 valeva **solo** perché Flash girava a `minimal` (0 thinking) — cioè nella configurazione che *non attribuisce gli autori*. Attivare gli autori e mantenere il risparmio sono, su questi numeri, **mutuamente esclusivi**.

**Esito e riapertura.** §8.20 aveva chiuso "Flash → solo `SCORE_ONLY`" con l'esplicita clausola "si riapre se un prompt tarato su Flash recupera l'attribuzione". Il giro mostra che **non serve un prompt nuovo**: basta il **parametro** `thinking_level='high'`, e `v3_4` resta invariato. Flash + `v3_4` + `high` è quindi tecnicamente candidabile anche al `FULL` (autori 100%, asse A non-inferiore). Ma la scelta non è più tecnica bensì **economica**: a parità di costo con Pro e con Pro già in produzione e collaudato end-to-end (§8.21), promuovere Flash a `FULL` non ha una giustificazione di risparmio. **Nulla promosso: questo giro misura, non decide.** La nicchia `SCORE_ONLY` per Flash-a-`minimal` (economico, autori irrilevanti) resta valida e distinta.

---

← [Macro precedente](7_profilo_fan.md) | → [Macro successiva](9_sistema_sponsor.md)
