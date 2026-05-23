# Feature Status — Code Inventory

Fotografia delle feature operative del progetto al 2026-04-20. Descrive il PRESENTE del codice. Per la visione di prodotto vedi [docs/BLUEPRINT.md](BLUEPRINT.md); per la roadmap futura vedi [docs/FEATURE_SYLLABUS_LEGACY.md](FEATURE_SYLLABUS_LEGACY.md) (in corso di revisione).

Fonti correlate:
- [docs/STATE_MACHINES.md](STATE_MACHINES.md) — macchine a stati (9 documentate, verificate sul codice)
- [docs/DOMAIN_GLOSSARY.md](DOMAIN_GLOSSARY.md) — glossario dominio ↔ codice con status per entità

Legenda:
- ✅ Implementata — funzionante
- 🟡 Parziale — base presente, mancano pezzi rispetto al blueprint
- 🧪 Sperimentale / Pilot — feature interna o beta

## Come leggere questo documento

Ogni feature è descritta in modo uniforme: status, codice chiave, test, entità correlate, gap rispetto al blueprint. I rimandi ai documenti correlati (STATE_MACHINES.md, DOMAIN_GLOSSARY.md, BLUEPRINT.md) sono sempre espliciti — questo file non duplica le loro informazioni, le indicizza.

In caso di contraddizione: vince il documento più specifico. STATE_MACHINES.md vince su FEATURE_STATUS.md che vince sul blueprint per questioni di codice; il blueprint vince sulla visione di prodotto.

## Indice

| Feature | Status | App principale |
|---------|--------|---------------|
| [Sports & Organization Registry](#sports--organization-registry) | ✅ | core |
| [Match Core](#match-core) | ✅ | matches |
| [Standings Engine](#standings-engine) | ✅ | core |
| [Match Report Workflow](#match-report-workflow) | ✅ | matches |
| [OCR Pipeline](#ocr-pipeline) | ✅ | matches |
| [Email Ingestion](#email-ingestion) | ✅ | matches |
| [User Onboarding](#user-onboarding) | ✅ | accounts |
| [Identity Verification](#identity-verification) | 🟡 | accounts |
| [Role Profiles](#role-profiles) | ✅ | accounts |
| [Profile Claim](#profile-claim) | ✅ | accounts |
| [RBAC Staff Roles](#rbac-staff-roles) | ✅ | accounts |
| [Membership Management](#membership-management) | ✅ | management |
| [Convocations](#convocations) | ✅ | management |
| [Training Management](#training-management) | ✅ | management |
| [Sponsors](#sponsors) | 🟡 | core |
| [Team Communications](#team-communications) | ✅ | management |
| [AI Stats Engine v0](#ai-stats-engine-v0) | 🟡 | matches |
| [Season Archive](#season-archive) | 🟡 | seasons |
| [Audit Logging](#audit-logging) | ✅ | management / matches |
| [Pilot Program](#pilot-program) | 🧪 | management |
| [Ops Commands](#ops-commands) | 🧪 | management |

---

## Sports & Organization Registry

**Status:** ✅ Implementata
**App principale:** core
**Descrizione:** Registro delle entità strutturali del dominio: sport, società sportive, squadre e campionati. Base dati su cui si appoggiano tutte le altre feature. Nessun workflow, solo configurazione e relazioni.

### Codice chiave
- `core/models.py` — Sport, Society, Team, League, LeagueStanding
- `core/views.py` — viste pubbliche per sport, società, team, campionato
- `core/urls.py` — routing pubblico
- `core/management/commands/bootstrap_sports.py` — seeding dati sport di base
- `core/management/commands/rebuild_standings.py` — rebuild manuale classifica da CLI

### Test
- `core/tests.py`
- `core/tests_prod_readiness.py`

### Entità correlate
- Sport, Society, Team, League → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- Nessuna

### Gap rispetto al blueprint
- Blueprint §10 prevede "Venues / Impianti" come entità separata. Nel codice è solo `Match.location` (CharField).
- Blueprint §10 prevede "Seasons" come modello autonomo. Nel codice la stagione è un CharField su `League` (es. "2024-2025").

---

## Match Core

**Status:** ✅ Implementata
**App principale:** matches
**Descrizione:** Gestione delle partite: anagrafica, punteggi per quarto/tempo, eventi di gioco (gol, cartellini, sostituzioni) e configurazione degli event type per sport. Prerequisito per il workflow referti e le convocazioni.

### Codice chiave
- `matches/models.py` — Match, MatchEvent, SportEventConfig
- `matches/event_types.py` — costanti e mapping dei tipi evento
- `matches/views.py` — vista dettaglio partita
- `matches/services/entity_bootstrap.py` — creazione entità match da dati OCR (giocatori, eventi)
- `core/models.py` — League (FK da Match)

### Test
- `matches/tests.py`
- `matches/tests_entity_bootstrap.py`
- `matches/tests_e2e_verification.py`

### Entità correlate
- Match, MatchEvent, SportEventConfig → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- Nessuna (Match non ha stato proprio; lo stato del workflow è sul MatchReport)

### Gap rispetto al blueprint
- Nessun gap identificato rispetto al blueprint.

---

## Standings Engine

**Status:** ✅ Implementata
**App principale:** core
**Descrizione:** Classifica di campionato persistita in `LeagueStanding` come tabella denormalizzata. Il rebuild è sempre tramite `standings_service.rebuild_league_standings(league)` — mai scrittura diretta. Il flag `League.needs_rebuild` supporta rebuild differiti.

### Codice chiave
- `core/models.py` — LeagueStanding
- `matches/services/standings_service.py` — rebuild completo della classifica
- `matches/services/integrity_service.py` — check diagnostico (MISSING_RECORD, EXTRA_RECORD, DATA_MISMATCH)
- `core/management/commands/rebuild_standings.py` — rebuild manuale da CLI
- `core/management/commands/monitor_integrity.py` — monitoraggio continuo integrità classifica

### Test
- `matches/tests_standings.py`
- `matches/tests_integrity.py`
- `matches/tests_reconciliation_logic.py`

### Entità correlate
- LeagueStanding, League → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- Nessuna

### Known data states
- **Falsi positivi strutturali del monitor di integrità.** `DataIntegrityService.check_league_standings(league)` confronta la classifica persistita con quella attesa, dove "attesa" è calcolata da `_calculate_expected_standings(league)` che produce un placeholder a zero per ogni squadra in `league.teams.all()`, **indipendentemente dai match giocati**. Conseguenza: una lega con N squadre iscritte e zero `MatchReport` in stato `PUBLISHED` produce sempre N segnalazioni `MISSING_RECORD` finché non viene eseguito un rebuild che popoli i placeholder. Non è un bug — è il comportamento atteso del check, ma genera mail dal monitor che sembrano allarmi e non lo sono. Prima di trattare un alert come problema, verificare quanti match `PUBLISHED` ha la lega segnalata: se sono zero, l'alert è strutturale.

### Gap rispetto al blueprint
- Nessun gap identificato rispetto al blueprint.

---

## Match Report Workflow

**Status:** ✅ Implementata
**App principale:** matches
**Descrizione:** Gestione del ciclo di vita del referto partita — dalla creazione alla pubblicazione. Un unico modello `MatchReport` gestisce sia i referti cartacei (source_channel=FILE, processati via OCR) sia i referti digitali nativi (source_channel=DIGITAL, inseriti manualmente in-app). Le due varianti differiscono nel punto di ingresso e nel path di transizione iniziale (FILE parte da UPLOADED, DIGITAL da DRAFT); condividono lo stesso percorso VALIDATED→PUBLISHED.

### Codice chiave
- `matches/models.py` — MatchReport, MatchReportAuditLog
- `matches/services/publishing_service.py` — pubblicazione, de-pubblicazione automatica, republish
- `matches/services/integrity_service.py` — guardrails pre-publish (blockers/warnings)
- `matches/views.py` — upload file, digital report UI, review UI
- `matches/api_views_digital.py` — REST CRUD per referto digitale
- `matches/api_urls.py` — routing API v1

### Test
- `matches/tests_status_semantics.py`
- `matches/tests_publish_guardrails.py`
- `matches/tests_publishing.py`
- `matches/test_manual_review.py`
- `matches/tests_review_ui.py`

### Entità correlate
- MatchReport, MatchReportAuditLog → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §1 (MatchReport workflow) — 8 stati, transizioni complete, guardrails

### Gap rispetto al blueprint
- ~~Blueprint §8 chiama `VALIDATED` con il nome `VERIFIED` — divergenza di nomenclatura confermata in STATE_MACHINES.md §"Discrepanze".~~ **CHIUSO il 09-mag-2026** — fix applicato in BLUEPRINT.md v3.3.
- ~~Blueprint §8 omette `PROCESSING` e `DRAFT` dal grafo degli stati.~~ **CHIUSO il 09-mag-2026** — Blueprint §8 ora distingue flusso cartaceo (UPLOADED → PROCESSING → EXTRACTED → VALIDATED → PUBLISHED) e flusso digitale (DRAFT → VALIDATED → PUBLISHED).

---

## OCR Pipeline

**Status:** ✅ Implementata
**App principale:** matches
**Descrizione:** Estrazione dati da referti cartacei (PDF o immagini) tramite provider OCR configurabile (GPT-4V in produzione, mock in test). Include quality gate, normalizzazione, deduplication via hash SHA-256, e salvataggio della risposta grezza per audit. L'ordine di modifica obbligatorio è: schema.py → ocr_service.py → converters.py → test e fixtures.

### Codice chiave
- `matches/services/ocr_service.py` — orchestrazione estrazione e transizioni di stato
- `matches/services/schema.py` — contratto JSON dell'output OCR
- `matches/services/converters.py` — normalizzazione raw OCR → structured data
- `matches/services/hash_service.py` — SHA-256 deduplication file
- `matches/services/ocr_quality_gate.py` — quality gate pre-EXTRACTED
- `matches/services/vision_providers.py` — astrazione provider (OpenAI / mock)
- `matches/models.py` — OCRRawResponse

### Test
- `matches/tests_ocr_service.py`
- `matches/tests_ocr_quality_gate.py`
- `matches/tests_ocr_hardening.py`
- `matches/tests_ocr_provider_toggle.py`
- `matches/tests_deduplication.py`

### Entità correlate
- MatchReport, OCRRawResponse → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §1 (transizioni UPLOADED→PROCESSING→EXTRACTED/NEEDS_REVIEW/REJECTED)

### Gap rispetto al blueprint
- Nessun gap identificato rispetto al blueprint.

---

## Email Ingestion

**Status:** ✅ Implementata
**App principale:** matches
**Descrizione:** Ricezione di referti via email: parsing del messaggio, estrazione allegati, deduplication tramite RFC822 message-id (idempotenza). Attiva il workflow OCR a partire da un'email invece che da un upload manuale. Il `source_type=EMAIL` discrimina l'origine sul MatchReport risultante.

### Codice chiave
- `matches/services/email_ingestion.py` — parsing email e creazione MatchReport
- `matches/models.py` — InboundEmail (deduplication idempotente per message-id)
- `matches/management/commands/ingest_emails.py` — pull manuale/schedulato da casella

### Test
- `matches/tests_email_ingestion.py`

### Entità correlate
- InboundEmail, MatchReport → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §1 (l'email ingestion genera un MatchReport con source_type=EMAIL; poi segue il workflow standard da UPLOADED)

### Gap rispetto al blueprint
- Nessun gap identificato rispetto al blueprint.

---

## User Onboarding

**Status:** ✅ Implementata
**App principale:** accounts
**Descrizione:** Flusso guidato di attivazione account in 4 step: verifica identità → pagamento → setup profilo → membership. Enforced da `OnboardingMiddleware` su ogni request autenticata. Lo stato è una property calcolata (non un campo DB) che aggrega tre campi reali: `identity_status`, `subscription_status`, `setup_completed`.

### Codice chiave
- `accounts/middleware.py` — OnboardingMiddleware, redirect per stato logico
- `accounts/models.py` — User (property `onboarding_state`, campi sottostanti)
- `accounts/views.py` — `verify_identity`, `process_payment`, `setup_wizard`, `onboarding_membership`
- `core/views.py` — setup society (Society.setup_completed)

### Test
- `accounts/tests_onboarding.py`

### Entità correlate
- User → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §2 (Onboarding utente) — 5 stati logici, campi reali, guardrails per ruolo fan

### Gap rispetto al blueprint
- Blueprint §7.2 descrive 6 passi UX; il codice ne implementa 4. "Claim profilo" e "Autenticazione con squadra" sono inglobati nello step `MEMBERSHIP_PENDING` (uno o l'altro è sufficiente).

---

## Identity Verification

**Status:** 🟡 Parziale
**App principale:** accounts
**Descrizione:** Verifica dell'identità dell'utente come prerequisito al completamento dell'onboarding. Il campo `identity_status` e la vista `verify_identity` sono presenti e funzionanti, ma il flusso SPID/CIE automatico non è implementato — la verifica avviene manualmente via vista Django tramite operazione admin..

### Codice chiave
- `accounts/models.py` — `User.identity_status` (UNVERIFIED/VERIFIED), `User.identity_verified_at`
- `accounts/views.py` — `verify_identity()` — vista manuale

### Test
- `accounts/tests_onboarding.py` (copre la transizione identity nell'onboarding)

### Entità correlate
- User → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §2 (transizione `UNVERIFIED → VERIFIED` su `identity_status`)

### Gap rispetto al blueprint
- Blueprint §7.3 prevede verifica automatica tramite SPID/CIE. Nel codice la verifica è manuale.

---

## Role Profiles

**Status:** ✅ Implementata
**App principale:** accounts
**Descrizione:** Profili sportivi specializzati per ruolo utente: atleta, allenatore, arbitro, presidente. Ogni profilo è 1:1 con un `User` e viene creato automaticamente via signal `post_save`. Include statistiche calcolate per l'atleta (`total_goals`, `total_matches`, `total_expulsions`) e campi specifici per ciascun ruolo.

### Codice chiave
- `accounts/models.py` — AthleteProfile, CoachProfile, RefereeProfile, PresidentProfile
- `management/signals.py` — creazione automatica profilo post-save User
- `accounts/views.py` — aggiornamento profilo nel wizard setup

### Test
- `accounts/tests.py`
- `accounts/tests_onboarding.py`

### Entità correlate
- AthleteProfile, CoachProfile, RefereeProfile, PresidentProfile → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- Nessuna

### Gap rispetto al blueprint
- Nessun gap identificato rispetto al blueprint.

---

## Profile Claim

**Status:** ✅ Implementata
**App principale:** accounts
**Descrizione:** Permette a un utente di rivendicare un profilo sportivo preesistente (atleta, allenatore, arbitro) creato prima della registrazione. La richiesta è approvata/rifiutata manualmente via Django admin. Un claim PENDING attivo è sufficiente a superare lo step `MEMBERSHIP_PENDING` nell'onboarding.

### Codice chiave
- `accounts/models.py` — AccountProfileLink
- `accounts/views.py` — `claim_profile()`

### Test
- `accounts/test_claim_flow.py`

### Entità correlate
- AccountProfileLink → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §4 (AccountProfileLink) — 3 stati: PENDING, APPROVED, REJECTED

### Gap rispetto al blueprint
- Approvazione/rifiuto avviene via Django admin senza servizio dedicato né audit trail strutturato (a differenza di `MembershipRequest` che usa `management/views.py` con logging esplicito).

---

## RBAC Staff Roles

**Status:** ✅ Implementata
**App principale:** accounts
**Descrizione:** Controllo accessi per le operazioni sul workflow referti: upload, revisione, pubblicazione. Gestito tramite `User.staff_role`, separato da `is_staff` Django. I permessi sono accumulativi: ogni livello include i permessi del livello inferiore (UPLOADER ⊂ REVIEWER ⊂ PUBLISHER ⊂ SUPERADMIN).

### Codice chiave
- `accounts/models.py` — `User.staff_role`, property `can_upload`, `can_review`, `can_publish`
- `management/permissions.py` — decorator/check per le viste gated

### Test
- `management/test_rbac.py`

### Entità correlate
- User → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §3 (RBAC Staff Role) — 5 livelli, guardrails is_superuser

### Gap rispetto al blueprint
- Blueprint §7.1 menziona il ruolo "Giuria (Cert)" come valore di `User.role`. Nel codice i valori di `role` sono: athlete, coach, referee, fan, president — nessun valore "jury"/"giuria". Nota: la lacuna è nell'enum `User.role`, non nel RBAC (`staff_role`). Vedi anche sezione "Feature non ancora implementate".

---

## Membership Management

**Status:** ✅ Implementata
**App principale:** management
**Descrizione:** Gestione dell'appartenenza di un utente a una società/squadra. Tre percorsi di ingresso: codice di attivazione (`ActivationCode`), richiesta manuale con approvazione del presidente (`MembershipRequest`), o creazione diretta da admin. Le membership hanno ruolo specifico (PLAYER, HEAD_COACH, ecc.) e flag `is_active`.

### Codice chiave
- `management/models.py` — Membership, MembershipRequest, ActivationCode
- `management/views.py` — `approve_membership()`, gestione codici attivazione
- `accounts/views.py` — `onboarding_membership()` — step onboarding

### Test
- `accounts/tests_onboarding.py` (percorso membership nell'onboarding)
- `management/test_rbac.py`

### Entità correlate
- Membership, MembershipRequest, ActivationCode → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §5 (MembershipRequest) — 3 stati: PENDING, APPROVED, REJECTED

### Gap rispetto al blueprint
- Nessun gap identificato rispetto al blueprint.

---

## Convocations

**Status:** ✅ Implementata
**App principale:** management
**Descrizione:** Convocazione ufficiale degli atleti per una partita. Lo stato effettivo viene calcolato dalla property `current_effective_status` in base al tempo alla partita: LOCKED scatta automaticamente quando la gara è passata. LOCKED non viene mai scritto nel DB — esiste solo come stato calcolato.

### Codice chiave
- `management/models.py` — Convocation, ConvocationNominee
- `management/views.py` — creazione, invio, pubblicazione convocazioni
- `management/forms.py` — form convocazione

### Test
- Nessun test dedicato identificato (`management/tests_cockpit.py` e `test_rbac.py` coprono parzialmente le viste)

### Entità correlate
- Convocation, ConvocationNominee → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §6 (Convocation) — 4 stati (3 DB + 1 calcolato), property `current_effective_status`

### Gap rispetto al blueprint
- Nessun gap identificato rispetto al blueprint.

---

## Training Management

**Status:** ✅ Implementata
**App principale:** management
**Descrizione:** Pianificazione degli allenamenti con supporto a ricorrenze (regola JSON su `Training`). Ogni istanza è tracciata in `TrainingOccurrence`. Le presenze/assenze degli atleti sono registrate in `TrainingAttendance` con supporto a geofencing (lat, lng, accuracy).

### Codice chiave
- `management/models.py` — Training, TrainingOccurrence, TrainingAttendance
- `management/views.py` — `training_rsvp()` — check-in con geolocalizzazione
- `management/forms.py` — form allenamento

### Test
- Nessun test dedicato identificato

### Entità correlate
- Training, TrainingOccurrence, TrainingAttendance → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §7 (TrainingAttendance) — 4 stati: PENDING, PRESENT, ABSENT, JUSTIFIED

### Gap rispetto al blueprint
- Nessun gap identificato rispetto al blueprint.

---

## Sponsors

**Status:** 🟡 Parziale
**App principale:** core
**Descrizione:** Gestione degli sponsor di una società. Implementata come JSONField su `Society` (`sponsors`: lista di oggetti `{"name": "...", "logo_url": "..."}`). Nessun modello autonomo, nessuna logica di placement o targeting.

### Codice chiave
- `core/models.py` — `Society.sponsors` (JSONField)

### Test
- Nessun test dedicato identificato

### Entità correlate
- Society → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- Nessuna

### Gap rispetto al blueprint
- Blueprint §10, §13 prevede un modello `Sponsor_Assets` separato con attributi di placement. Nel codice è un JSONField flat su Society.

---

## Team Communications

**Status:** ✅ Implementata
**App principale:** management
**Descrizione:** Comunicazione interna alle squadre tramite due canali: bacheca (Post + Comment) per comunicazioni asincrone strutturate, e chat (ChatMessage) per messaggistica informale. Tutti e tre i modelli sono in `management/models.py`. `ChatMessage` non è menzionata nel blueprint come funzionalità distinta.

### Codice chiave
- `management/models.py` — Post, Comment, ChatMessage
- `management/views.py` — viste bacheca e chat
- `management/urls.py` — routing comunicazioni

### Test
- Nessun test dedicato identificato

### Entità correlate
- Post, Comment, ChatMessage → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- Nessuna

### Gap rispetto al blueprint
- Nessun gap identificato rispetto al blueprint (Post/Comment sono citati come "Bacheca squadra"; ChatMessage è solo nel codice).

---

## AI Stats Engine v0

**Status:** 🟡 Parziale
**App principale:** matches
**Descrizione:** Engine minimale per query sulle statistiche di atleti e partite. La v0 gestisce il logging delle query (`AIQueryLog`) e un matching basico dell'atleta. L'engine di risposta esiste in forma basilare; il chatbot AI interattivo con storia della conversazione descritto nel blueprint non è implementato. Il suffisso v0 indica l'iterazione iniziale minimale; la v1 con chatbot interattivo è menzionata nel blueprint ma non pianificata qui.

### Codice chiave
- `matches/models.py` — AIQueryLog
- `matches/services/ai_services.py` — engine query
- `matches/stats_services.py` — calcolo statistiche atleta
- `matches/api_views.py` — endpoint REST stats

### Test
- `matches/tests_api.py`
- `matches/tests_stats_integrity.py`
- `matches/tests_metrics.py`

### Entità correlate
- AIQueryLog → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- Nessuna

### Gap rispetto al blueprint
- Blueprint §7.5 descrive un chatbot AI interattivo con storia della conversazione e risposta in linguaggio naturale. L'implementazione attuale è un endpoint query-risposta senza contesto multi-turn.

---

## Season Archive

**Status:** 🟡 Parziale
**App principale:** seasons
**Descrizione:** Snapshot JSON delle statistiche di atleti e squadre per stagioni passate. Consente di congelare i dati storici al termine di una stagione. Il modello `SeasonArchive` esiste; la generazione di un PDF riassuntivo non è implementata.

### Codice chiave
- `seasons/models.py` — SeasonArchive
- `seasons/views.py` — visualizzazione archivio stagionale
- `seasons/admin.py` — gestione manuale stagioni

### Test
- `seasons/tests.py`

### Entità correlate
- SeasonArchive → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- Nessuna

### Gap rispetto al blueprint
- Blueprint §7.1, §13 prevede la generazione di un "Season Recap PDF" per utenti Premium. Il modello `SeasonArchive` esiste ma la generazione PDF non è implementata.

---

## Audit Logging

**Status:** ✅ Implementata
**App principale:** management / matches
**Descrizione:** Due livelli di audit trail complementari: `AuditLog` in `management` per azioni critiche di sistema (PUBLISH_REPORT, ONBOARDING_*); `MatchReportAuditLog` in `matches` per ogni transizione di stato del referto (old_status, new_status, user, reason). I due log non si sovrappongono.

### Codice chiave
- `management/models.py` — AuditLog (log generico di sistema)
- `matches/models.py` — MatchReportAuditLog (log dedicato workflow referti)
- `matches/services/publishing_service.py` — scrive entrambi i log alla pubblicazione

### Test
- `matches/tests_publishing.py`
- `matches/tests_status_semantics.py`
- `test_audit_trail.py` (root)

### Entità correlate
- AuditLog, MatchReportAuditLog → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §1 (ogni transizione MatchReport genera un MatchReportAuditLog)

### Gap rispetto al blueprint
- Nessun gap identificato rispetto al blueprint.

---

## Pilot Program

**Status:** 🧪 Sperimentale / Pilot
**App principale:** management
**Descrizione:** Infrastruttura interna per il monitoraggio operativo della fase pilota: log giornaliero con semaforo (PilotDailyLog GREEN/YELLOW/RED), bug tracker interno (PilotBug, severity S1–S4), raccolta feedback UX (PilotFeedback), review periodica go/no-go (PilotReview). Non visibile agli utenti finali.

### Codice chiave
- `management/models.py` — PilotDailyLog, PilotBug, PilotFeedback, PilotReview
- `management/pilot_services.py` — logica aggregazione e analisi pilot
- `management/management/commands/check_pilot_alerts.py` — alert automatici su soglie
- `management/management/commands/send_pilot_report.py` — report periodico

### Test
- `management/tests_pilot_ops.py`

### Entità correlate
- PilotDailyLog, PilotBug, PilotFeedback, PilotReview → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- STATE_MACHINES.md §8 (PilotBug) — 6 stati
- STATE_MACHINES.md §9 (PilotFeedback) — 5 stati

### Gap rispetto al blueprint
- Il Pilot Program non è menzionato nel blueprint — è infrastruttura operativa interna. Nessun gap.

---

## Ops Commands

**Status:** 🧪 Sperimentale / Pilot
**App principale:** management (+ core + matches)
**Descrizione:** Management commands Django per operazioni di sistema: health check applicazione, rebuild classifiche, seeding dati, monitoraggio integrità, ingestione email, metriche pilot. Strumenti CLI usati da admin e scheduler cron.

### Codice chiave
- `management/management/commands/ops_check.py` — health check completo applicazione
- `management/management/commands/run_scheduler.py` — dispatcher tasks schedulati
- `management/management/commands/send_pilot_report.py` — report operativo periodico
- `core/management/commands/rebuild_standings.py` — rebuild classifica manuale
- `core/management/commands/monitor_integrity.py` — monitoraggio integrità dati
- `matches/management/commands/ingest_emails.py` — pull email in ingresso

### Test
- `management/tests_ops.py`
- `core/tests_monitoring.py`

### Entità correlate
- PilotDailyLog, LeagueStanding, AuditLog → vedi DOMAIN_GLOSSARY.md

### State machine correlata
- Nessuna

### Gap rispetto al blueprint
- I management commands non sono menzionati nel blueprint. Nessun gap.

---

## Coverage Gaps — Feature senza test dedicati

Le seguenti feature risultano senza file di test dedicato al 2026-04-20. Quando si interviene su queste aree, valutare di aggiungere test prima di modificare il codice:

- **Convocations** — stato machine con 4 stati e property time-based non coperta.
- **Training Management** — presenze con geofencing non coperte.
- **Team Communications** — Post, Comment, ChatMessage senza test.
- **Sponsors** — JSONField, test di serializzazione assenti.

## Riepilogo numerico

- Feature totali documentate: 21
- ✅ Implementate: 15
- 🟡 Parziali: 4 (Identity Verification, Sponsors, AI Stats Engine v0, Season Archive)
- 🧪 Sperimentali/Pilot: 2 (Pilot Program, Ops Commands)
- Feature senza test dedicato: 4 (Convocations, Training, Team Communications, Sponsors)
- Feature del blueprint non implementate: 10 (vedi sezione dedicata)

## Feature non ancora implementate

Elenco features descritte nel blueprint ma assenti nel codice. Per la roadmap vedi [docs/FEATURE_SYLLABUS_LEGACY.md](FEATURE_SYLLABUS_LEGACY.md).

- Jury Tokens — blueprint §7.4, §10, §14
- Firma arbitro (PIN referto) — blueprint §7.4.3, §14
- Ruolo "Giuria" nell'enum `User.role` — blueprint §7.1 (i valori attuali sono: athlete, coach, referee, fan, president; nessun valore "jury"/"giuria")
- Media Gallery + AI Tagging — blueprint §7.6
- Live Alerts push — blueprint §2, §13
- Shop vetrina + webhook HMAC — blueprint §2, §3, §13
- User Preferences / Widget Dashboard personalizzata — blueprint §7.1, §12
- Subscription three-tier (FREEMIUM/PREMIUM/CLUB_PRO) — blueprint §13 (attualmente `User.subscription_status` è solo INACTIVE/ACTIVE)
- Season Recap PDF generation — blueprint §7.1, §13 (il modello `SeasonArchive` esiste, la generazione PDF no)
- SPID/CIE identity verification automatica — blueprint §7.3 (il campo `identity_status` esiste, la verifica automatica no)

---

## Domande per Alberto

Nessuna domanda aperta.

