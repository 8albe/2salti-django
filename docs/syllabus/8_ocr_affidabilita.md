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

- [x] **Dataset gold standard — struttura creata il 2026-07-19** in [docs/ocr_gold_standard/](../ocr_gold_standard/) (un file JSON per referto verificato in `cases/`, schema e procedura nel `README.md`). Prima riga: il match 3 dell'11/04/2026. Resta da fare l'aggancio `ocr_bench --gold-case`.
  - **Aggiornamento 2026-07-19: dataset a 5 casi.** Aggiunti 4 referti collazionati a mano (punteggio e parziali soltanto; roster/eventi/ufficiali in `not_verified`), tutti stagione 2025/2026: Olympic Roma P.N. vs Libertas Roma Eur (12/04, 20-1), Unime vs Nautilus Roma (28/03, 12-10), Nautilus Nuoto Roma vs Trisceloni Etna Sport (25/04, 20-12), S.C. Salerno vs Nautilus Nuoto Roma (18/04, 12-17). Nessuna estrazione OCR associata (`extractions: []`): pronti per il bench, non ancora fatti girare. Verifica DB soggetti nuovi: 'Trisceloni Etna Sport' e 'S.C. Salerno' **assenti** sia da Team sia da Society (confermato sul sistema vivo) — un loro referto andrebbe orfano per assenza reale, non per fallimento fuzzy matching (§8.6). 'Olympic Roma P.N.' presente ma con divergenza di grafia a DB ('Olimpic Roma P.N.', stesso pattern del caso Bellator/Frosinone in §8.6).
  - **Aggiornamento 2026-07-19 (secondo giro, stesso giorno): censimento + correzione su dev.** Censimento read-only su dev e prod (identici): 4 Match totali, 4 `is_finished`, 4 con punteggio valorizzato, **0 con un report mai `PUBLISHED`** — l'intera popolazione match è a rischio, non solo i 3 casi noti (dettaglio §8.5(d)). 0 `LeagueStanding` non a zero: nessun dato errato ha ancora raggiunto la classifica, perché `StandingsService` filtra su `reports__status='PUBLISHED'`. Confermate sul sistema vivo le due discrepanze: match Olympic/Libertas (id 4) con parziali sbagliati a DB nonostante il finale giusto; match Unime/Nautilus (id 2) con casa/trasferta invertiti a DB (nuova classe di errore, §8.5(e)). **Corrette su dev** (transazione + audit `MATCH_SCORE_CORRECTED`, `is_data_verified=True`, `rebuild_standings --verify` + `check_data_integrity` puliti su entrambe le leghe). **Prod non toccato**, correzione preparata non eseguita. `normalized_data` dei report 8, 10, 11, 16 non toccato: non pubblicarli finché non corretto separatamente (nota operativa in §8.5).
  - **Aggiornamento 2026-07-19 (terzo giro, stesso giorno): dataset a 6 casi, popolazione match chiusa al 100% di errore.** Verificato a mano il quarto e ultimo referto cartaceo disponibile (match 1, Pol. Delta vs Villa York, 06/12/2025, lega 2, report 7): finale 15-9 corretto a DB, **tutti e quattro i parziali sbagliati** (veri 6-2 / 1-2 / 3-4 / 5-1), verità corroborata dalla storia cronometrica del referto (§8.5(f)). Con questo **tutti e 4 i match a DB risultano sbagliati: 4/4** e il controllo "somma parziali == finale" li attraversa tutti — **0% di rilevazione su 100% di errore** (§8.5(d)). Corretto su dev con lo stesso rigore (transazione + audit, `is_data_verified=True`, rebuild lega 2 + `check_data_integrity` puliti); backfill anche di `has_report`, incoerente per una causa applicativa registrata e **non** corretta (§8.5(g)). **Prod non toccato**: sequenza consolidata delle 4 correzioni preparata a parte.
  - Caso motivante: lo stesso match (Bellator Frusino vs SS. Lazio Nuoto, 11/04/2026) ha **due estrazioni divergenti sul punteggio finale** — report 10 (`gpt-4o`): 11-19; report 16 (`gemini-2.5-pro`): 5-19. La verità umana, collazionata sul cartaceo il 2026-07-19, è **4-19**: sbagliano **entrambe**. Il gold standard serve a **due scopi distinti**: (1) misurare l'accuratezza per campo; (2) verificare la calibrazione della confidence per tarare la soglia del quality gate.
  - Nota (2026-07-19): Mistral OCR 4 registrato come provider candidato da benchmarcare contro `gemini-2.5-pro` con `ocr_bench` sul dataset gold quando sarà costruito — nessuna implementazione ora.
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
| 1 — Pol. Delta/Villa York | giusto (15-9) | tutti e 4 sbagliati (vero 6-2/1-2/3-4/5-1) | 5+4+3+3=15, 2+2+1+4=9 ✓ | dev sì, prod no |
| 2 — Unime/Nautilus | giusto nei due totali, **squadre invertite** | tutti e 4 sbagliati | 3+2+4+3=12, 2+3+3+2=10 ✓ | dev sì, prod no |
| 3 — Bellator/Lazio | sbagliato (11-19, vero 4-19) | tutti e 4 sbagliati | 2+4+2+3=11, 2+5+4+8=19 ✓ | dev sì, prod no |
| 4 — Olympic/Libertas | giusto (20-1) | tutti e 4 sbagliati | 5+5+5+5=20, 0+0+0+1=1 ✓ | dev sì, prod no |

**La statistica che conta: il controllo strutturale "somma parziali == finale" ha un tasso di rilevazione dello 0% su una popolazione con tasso di errore del 100%.** Quattro match sbagliati, zero segnalati. Non è un controllo debole da tarare meglio: su questa classe di errore è **inutile per costruzione**, perché il modello deriva parziali e totale dalla stessa lettura (o ricostruisce i parziali a partire dal totale). Un controllo che non può fallire non può nemmeno rilevare — vedi (b) per le alternative indipendenti.

Il campione resta piccolo (4 casi), ma non è più un campione: è la popolazione intera.

**Corollario (ipotesi con n=4, non legge): il totale è il campo più affidabile, i parziali il meno affidabile.** Il punteggio finale è corretto in 3 casi su 4 (match 1, 2, 4 — nel match 2 i due totali sono giusti, solo attribuiti alla squadra sbagliata), mentre i parziali sono sbagliati in 4 su 4. Se regge su più casi, ha una conseguenza operativa concreta: la review umana va concentrata sui parziali, e i parziali non andrebbero trattati come dato pubblicabile senza collazione. Da riverificare a ogni nuovo caso gold prima di trasformarla in una regola.

**(e) Nuova classe di errore: INVERSIONE CASA/TRASFERTA (match 2, 2026-07-19).**

Il match Unime vs Nautilus Roma (28/03/2026) aveva a DB **le squadre scambiate**: `home_team=Nautilus (12)`, `away_team=Unime (10)`, mentre il cartaceo dice il contrario — ospitante Unime, vincitore 12-10. I due punteggi totali (12 e 10) erano entrambi presenti e corretti, solo attribuiti alla squadra sbagliata. **Nessun controllo aritmetico può rilevare questa classe di errore**: la somma dei parziali torna, il totale torna, tutti i numeri sono quelli giusti — cambia solo *a chi* sono assegnati. La conseguenza pratica è che falsa il vincitore e quindi, se il referto venisse pubblicato, i punti in classifica (3 punti alla squadra sbagliata). Corretto su dev il 2026-07-19 scambiando le FK `home_team`/`away_team` insieme a punteggio e parziali nella stessa transazione (recon preventivo: zero `MatchEvent` e zero `Convocation` collegati a quel match, quindi nessun effetto collaterale su altre tabelle); prod ancora da correggere.

**Ipotesi da verificare, non conclusione:** il pattern dei parziali sbagliati sul match 4 (`5-0 / 5-0 / 5-0 / 5-1` a DB) ha una regolarità sospetta — tre quarti identici e il quarto che assorbe il resto — che potrebbe essere una firma di allucinazione (il modello "inventa" una distribuzione plausibile invece di leggere davvero la griglia) piuttosto che un errore di lettura genuino. Da tenere d'occhio sui prossimi casi gold, non abbastanza dati per concludere su un solo campione.

**(f) Corroborazione incrociata sul foglio: la storia cronometrica come seconda fonte (match 1, 2026-07-19).**

Sul match 1 la verità dei parziali (6-2 / 1-2 / 3-4 / 5-1) non viene da una sola lettura: è confermata dalla **storia cronometrica** del referto, la sequenza dei gol col minuto, che dà la progressione 6-2 → 7-4 → 10-8 → 15-9 e coincide con i cumulati dei parziali collazionati. È una zona del foglio **indipendente** dal riquadro dei parziali, compilata separatamente durante la gara: la concordanza non è una ricopiatura, è una conferma. Regola metodologica per i casi futuri: quando le due zone concordano la fiducia nella `truth` è più alta di una singola lettura; quando divergono il caso va marcato e non chiuso. È anche la conferma pratica che la strada indicata in (b)-1 esiste davvero sul foglio.

**(g) Flag `has_report` incoerente sul match 1 (dato corretto, causa applicativa aperta).**

Il match 1 aveva `has_report=False` pur avendo il report 7 collegato. Causa: `Match.has_report` viene scritto **solo** nei percorsi di upload/creazione (`matches/views.py:163` upload con match noto, `:591` referto digitale, `:647` creazione match da OCR) e **non** nei due percorsi che collegano un referto a una partita *a posteriori* — `link_match` (`matches/views.py:361`) e l'auto-aggancio di `MatchDiscoveryService` (`matches/services/ocr_service.py:380`). Entrambi fanno `report.match = ...; report.save()` senza toccare il flag sul `Match`. Con l'asincrono (Macro 22) la discovery è il percorso *normale*, quindi l'incoerenza è sistematica, non un caso isolato: ogni referto agganciato dalla discovery lascia il match con `has_report=False`. Impatto: `matches/views.py:647` e `core/services/dashboard_service.py:203` filtrano su questo flag, quindi il match risulta invisibile in quelle viste. Su dev è stato fatto il **backfill del solo dato** (audit `MATCH_HAS_REPORT_BACKFILLED`); gli altri 3 match non ne sono affetti. **La logica applicativa non è stata toccata**: la correzione naturale è derivare il flag dal collegamento invece di replicarlo (proprietà `has_report` calcolata su `self.reports.exists()`, come già fa `is_public`) oppure scriverlo nei due percorsi mancanti — decisione da prendere a parte.

**Nota operativa: non pubblicare i report 7, 8, 10, 11, 16.** Questi cinque report hanno `normalized_data` con punteggio e/o attribuzione casa/trasferta sbagliati, non ancora corretti (giro separato, fuori scope Macro 8 attuale). La correzione applicata finora ha toccato solo il `Match`, non il report. Se uno di questi report venisse pubblicato o ripubblicato, `publish_report()` (`matches/services/publishing_service.py`) sovrascriverebbe `Match.home_score`/`away_score`/`quarter_scores` (e, per match 2, ricreerebbe gli eventi con l'attribuzione squadra ancora sbagliata) leggendo dal `normalized_data` non corretto — vanificando silenziosamente la correzione appena fatta.

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

---

← [Macro precedente](7_profilo_fan.md) | → [Macro successiva](9_sistema_sponsor.md)
