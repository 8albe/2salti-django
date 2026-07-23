# State Machines — Source of Truth

Questo documento descrive le macchine a stati implementate nel codice.
Se il blueprint di prodotto o altri documenti dicono cose diverse, **questo file vince**.

Ultimo aggiornamento: 2026-07-19 (§1: recupero orfani in PROCESSING, requeue capped — Macro 22 giro 2)
Generato leggendo:
- `accounts/models.py`
- `matches/api_views_digital.py`
- `matches/api_views_jury.py`
- `matches/services/jury_link_service.py`
- `accounts/middleware.py`
- `accounts/views.py`
- `matches/models.py`
- `matches/services/publishing_service.py`
- `matches/services/integrity_service.py`
- `matches/services/ocr_service.py`
- `matches/services/ocr_queue.py`
- `matches/management/commands/ocr_worker.py`
- `matches/views.py`
- `management/models.py`
- `management/admin.py`
- `management/services/president_personification.py`
- `core/models.py`
- `core/views.py`
- `docs/BLUEPRINT.md`
- `docs/FEATURE_SYLLABUS_LEGACY.md`
- `CLAUDE.md`

---

## 1. MatchReport workflow

**Model:** `matches.MatchReport`
**Field:** `status` (CharField, `MatchReport.Status` TextChoices)
**File:** [matches/models.py](matches/models.py) righe 150–158
**Default:** `UPLOADED`

### Stati

| Valore DB | Label | Descrizione breve | Iniziale? | Finale? |
|---|---|---|---|---|
| `DRAFT` | Bozza (Digitale) | Referto digitale nativo creato ma non ancora pronto | Sì (solo DIGITAL) | No |
| `UPLOADED` | Caricato (In attesa) | File caricato, **non** ancora accodato: in attesa di una decisione | Sì (solo FILE) | No |
| `QUEUED` | In Coda OCR | Accodato per il worker, non ancora preso in carico | No | No |
| `PROCESSING` | In Elaborazione OCR | Claim fatto da un worker, OCR provider in esecuzione | No | No |
| `EXTRACTED` | Dati Estratti (Da Revisionare) | OCR completato con successo e superato quality gate | No | No |
| `VALIDATED` | Validato (Approvato Admin) | Approvato manualmente da un reviewer | No | No |
| `PUBLISHED` | Pubblicato (Statistiche Aggiornate) | Report attivo: match aggiornato, standings ricalcolati | No | Sì (stabile) |
| `NEEDS_REVIEW` | Revisione Tecnica Necessaria | OCR fallito o quality gate non superato | No | No |
| `REJECTED` | Rifiutato/Errore | File assente o errore terminale | No | Sì |

### Transizioni

| Da | A | Trigger (funzione/endpoint) | Side effects | File |
|---|---|---|---|---|
| — | `UPLOADED` | `upload_report()` — caricamento file | `file_hash` calcolato, uploader loggato | `matches/views.py` |
| — | `DRAFT` | `create_digital_report()` — referto digitale | `match.has_report = True` | `matches/views.py` |
| `UPLOADED` | `QUEUED` | `OCRService.enqueue()` — upload view e admin action | `ocr_queued_at` valorizzato, `MatchReportAuditLog` action=`enqueue` | `matches/services/ocr_service.py` |
| `NEEDS_REVIEW` | `QUEUED` | `OCRService.enqueue()` — riprocessamento | Come sopra | `matches/services/ocr_service.py` |
| `REJECTED` | `QUEUED` | `OCRService.enqueue()` — riprocessamento | Come sopra | `matches/services/ocr_service.py` |
| `QUEUED` | `PROCESSING` | `OCRQueueService.claim()` — claim del worker | `ocr_started_at` valorizzato, `ocr_attempts` incrementato | `matches/services/ocr_queue.py` |
| `PROCESSING` | `QUEUED` | `OCRQueueService.schedule_retry()` — errore tecnico del provider | `ocr_next_attempt_at` = now + backoff (60s, 120s), `ocr_error` salvato, audit action=`ocr_retry` | `matches/services/ocr_queue.py` |
| `PROCESSING` | `QUEUED` | `OCRQueueService.requeue_stale()` — referto orfano recuperato, con tentativi residui. Innescata dalla sweep di avvio del worker (nessuna soglia) o dal backstop `recover_stale_reports` (soglia 15 min) | `ocr_started_at` azzerato, `ocr_next_attempt_at` = now (nessun backoff), `ocr_attempts` **invariato**, audit action=`ocr_stale_requeue` | `matches/services/ocr_queue.py` |
| `PROCESSING` | `NEEDS_REVIEW` | `OCRQueueService.requeue_stale()` — referto orfano con tentativi **esauriti**: delega a `fail_permanently()` | audit action=`ocr_failed`, notifica staff | `matches/services/ocr_queue.py` |
| `PROCESSING` | `NEEDS_REVIEW` | `OCRQueueService.fail_permanently()` — tentativi esauriti (3) | `validation_notes` con errore tecnico, audit action=`ocr_failed`, notifica staff | `matches/services/ocr_queue.py` |
| `UPLOADED` | `REJECTED` | `OCRService.enqueue()` — canale FILE senza file | `validation_notes` con errore (fail veloce sincrono) | `matches/services/ocr_service.py` |
| `PROCESSING` | `EXTRACTED` | `OCRService.process_claimed()` — OCR OK + quality gate OK | `normalized_data` popolato, `validation_notes` con gate results, audit log `OCR_PROCESSING_SUCCESS`, link a `match` | `matches/services/ocr_service.py` |
| `PROCESSING` | `NEEDS_REVIEW` | `OCRService.process_claimed()` — quality gate bloccante (incluso il path no-match) | `validation_notes` con gate results, `NotificationService.notify_report_needs_review()`. **Nessun retry**: è un esito, non un errore | `matches/services/ocr_service.py` |
| `PROCESSING` | `NEEDS_REVIEW` | `OCRService.process_and_update()` — eccezione OCR nel path **sincrono** (test, diagnostica) | `validation_notes` con errore, notifica staff | `matches/services/ocr_service.py` |
| `EXTRACTED` | `VALIDATED` | `report_review()` — reviewer setta stato manualmente | `validated_by`, `validated_at` settati; `MatchReportAuditLog` action=`validate` | `matches/views.py` r. 316–321 |
| `NEEDS_REVIEW` | `VALIDATED` | `report_review()` — reviewer override | Come sopra | `matches/views.py` |
| `NEEDS_REVIEW` | `EXTRACTED` | `report_review()` — reviewer ri-qualifica | Come sopra senza `validated_by` | `matches/views.py` |
| `VALIDATED` | `PUBLISHED` | `PublishingService.publish_report(level='FULL'\|'SCORE_ONLY')` | Match aggiornato (punteggi, quarti, `is_finished=True`); `publication_level` scritto (Opzione A); su `FULL`: MatchEvent ricreati, stats atleti aggiornate, abort se 0 eventi con score>0 (Policy A strict); su `SCORE_ONLY`: **nessun** MatchEvent creato, eventi esistenti cancellati, abort zero-eventi **non** valutato; standings rebuild sincrono su entrambi; `MatchReportAuditLog` action=`publish` (con `publication_level` ed `events_deleted` nel payload `after`); `AuditLog` action=`PUBLISH_REPORT` | `matches/services/publishing_service.py` |
| `PUBLISHED` | `PUBLISHED` | `PublishingService.publish_report()` — ripubblicazione | Come sopra; `MatchReportAuditLog` action=`republish` | `matches/services/publishing_service.py` r. 58 |
| `PUBLISHED` | `VALIDATED` | `PublishingService.publish_report()` — de-pubblicazione automatica | Scatta quando un *altro* report per lo stesso match viene pubblicato; `internal_notes` aggiornate; `MatchReportAuditLog` action=`depublish` | `matches/services/publishing_service.py` r. 123–137 |

### Coda OCR asincrona (Macro 22, giro 1 — 2026-07-19)

Dal 2026-07-19 l'OCR **non gira più nel request cycle**. I due entry point
(upload view e admin action `process_ocr`) chiamano `OCRService.enqueue()`, che
porta il referto in `QUEUED`; il worker `ocr_worker` (servizio systemd) fa
polling ogni 3s, prende il referto con un claim atomico ed esegue
`OCRService.process_claimed()`.

- **Claim atomico:** `UPDATE ... WHERE pk=? AND status='QUEUED'`. Chi vede
  rowcount 1 possiede il job. Nessuna transazione resta aperta durante la
  chiamata al provider (~80s): su SQLite bloccherebbe ogni altro writer.
- **`ocr_attempts` si incrementa al claim, non all'esito.** Un worker che muore
  a metà job ha comunque consumato un tentativo: nessun referto può diventare
  una poison pill che cicla all'infinito.
- **Due classi di fallimento.** Di *merito* (quality gate, incluso il no-match)
  → `NEEDS_REVIEW` senza retry. *Tecnico* (provider 5xx, timeout, rete) →
  ritorno in `QUEUED` con backoff 60s/120s, fino a 3 tentativi, poi
  `NEEDS_REVIEW` + notifica.
- **Orfani in `PROCESSING`:** due inneschi, **una sola regola**. La sweep di
  avvio del worker li riaccoda senza soglia temporale (girando un solo worker,
  all'avvio ogni referto in `PROCESSING` è per definizione orfano); il backstop
  periodico `recover_stale_reports` (timer ogni 15 min, giro 2) applica la
  soglia `ocr_started_at` più vecchio di 15 minuti e copre il caso che la sweep
  non vede — il worker fermo e basta, che quindi non si riavvia mai.
  Entrambi passano da `OCRQueueService.requeue_stale()`: l'esito su un dato
  referto non dipende da chi lo recupera.
  Il recupero **non** incrementa `ocr_attempts` (si contano al claim) e non
  applica backoff: l'orfano non ha fallito, gli è morto sotto il worker, quindi
  `ocr_next_attempt_at = now`.
- **`UPLOADED` non è uno stato di coda:** i referti creati da admin o da
  `ingest_emails` restano lì finché qualcuno non li accoda esplicitamente.

### Guardrails

- **OCR precondition:** `source_channel == 'FILE'` richiede che `report.file` esista; altrimenti → `REJECTED` immediatamente.
- **Publish readiness check:** `OCRSchemaValidator.assess_publish_readiness(data, level='FULL')` valuta blockers e warnings. Se `safe=False` e `force=False` la pubblicazione viene bloccata con messaggio esplicito. Su `level='SCORE_ONLY'` (Opzione A) i blocker **event-scoped** (roster vuoti, "Incoerenza eventi", "Incoerenza per-periodo", "Zero Eventi", "Riconciliazione incompleta") sono declassati a warning marcati `[fuori livello]`; i blocker **score-scoped** (punteggio, nomi squadre, "Incoerenza punteggio" somma-quarti) restano. Non è un `force`: è la valutazione al livello dichiarato. Il default `FULL` è invariato byte per byte.
- **Livello di pubblicazione (Opzione A):** `publication_level` (`FULL`|`SCORE_ONLY`, default `FULL`) è scritto **solo** da `publish_report()`. Downgrade `FULL`→`SCORE_ONLY` su republish (D3) richiede `reason` non vuota — distrugge la cronologia eventi già pubblica; senza reason ritorna `(False, messaggio)`. Upgrade `SCORE_ONLY`→`FULL` e primo publish sono liberi. Lato pubblico il gate degli eventi è `Match.events_published` (True solo se il referto PUBLISHED è `FULL`), più stretto di `Match.is_public`.
- **Reconciliazione incompleta (blocker):** dentro `assess_publish_readiness` ([matches/services/schema.py](../matches/services/schema.py) righe 356–371), per ogni evento con `player_name` o `player` valorizzato, il nome viene cercato nella mappa `reconciliation.home_players` ∪ `reconciliation.away_players`. Se anche un solo nome non risulta riconciliato, il blocker `Riconciliazione incompleta per: <nomi>` viene aggiunto e la publish è bloccata. Razionale: pubblicare con eventi che fanno riferimento a giocatori non riconciliati produrrebbe drift nelle statistiche atleti, perché l'aggregatore `update_stats` non saprebbe a quale `AthleteProfile` attribuire il gol/cartellino. Distinto dal warning "Incompletezza" delle righe 351–354 che si attiva quando >50% dei roster non è riconciliato e non blocca.
- **Force override:** `publish_report(force=True)` bypassa i blockers ma li loga come `PUBBLICAZIONE FORZATA` e li registra nell'`AuditLog.details.overridden_blockers`.
- **Concurrent publish guard:** `select_for_update()` sul report dentro la transazione; doppio check dello stato dopo lock per prevenire race conditions.
- **Status precondition per publish:** solo `VALIDATED` o `PUBLISHED` (re-publish) sono accettati; qualsiasi altro stato ritorna `(False, messaggio)`.
- **Team membership check per eventi:** un `MatchEvent` viene creato solo se `AthleteProfile.current_team == target_team`; eventi con team sbagliato vengono saltati con warning.
- **DataIntegrityService:** `check_league_standings(league)` confronta classifica persistita con attesa — rileva `MISSING_RECORD`, `EXTRA_RECORD`, `DATA_MISMATCH`; è un check diagnostico, non blocca transizioni.

### Discrepanze con la documentazione

- **CLAUDE.md (sezione "Match Report Pipeline") dice:** `DRAFT → UPLOADED → PROCESSING → EXTRACTED → VALIDATED → PUBLISHED`
  **Codice dice:** esistono anche `NEEDS_REVIEW` e `REJECTED`, e le transizioni non sono strettamente lineari (es. `NEEDS_REVIEW → PROCESSING` per riprocessamento).
  **Verdetto:** codice corretto, CLAUDE.md da aggiornare — mancano due stati e il grafo reale.

- **BLUEPRINT.md §8 dice:** `UPLOADED → EXTRACTED → NEEDS_REVIEW → VERIFIED → PUBLISHED` + `REJECTED`
  **Codice dice:** lo stato si chiama `VALIDATED` (non `VERIFIED`); esiste anche `PROCESSING` (assente nel blueprint); `DRAFT` esiste (assente nel blueprint).
  **Verdetto:** codice corretto. Nel blueprint `VERIFIED` va rinominato `VALIDATED`. `PROCESSING` e `DRAFT` vanno aggiunti alla descrizione del flusso.

- **CLAUDE.md (sezione "Match Report Pipeline") dice:** `source` (FILE/DIGITAL), `origin` (MANUAL/EMAIL)
  **Codice dice:** i campi si chiamano `source_channel` (FILE/DIGITAL) e `source_type` (MANUAL/EMAIL).
  **Verdetto:** codice corretto, CLAUDE.md usa nomi sbagliati.

---

## 2. Onboarding utente (flusso composito)

**Model:** `accounts.User`
**Field:** property calcolata `onboarding_state` — **non è un campo DB**
**File:** [accounts/models.py](accounts/models.py) righe 92–126
**Enforced by:** `OnboardingMiddleware.process_request()` — [accounts/middleware.py](accounts/middleware.py)

> **Nota critica:** gli "stati" dell'onboarding non sono un singolo campo sul modello.
> Sono la combinazione di due campi reali che gatingano il funnel (`identity_status`,
> `setup_completed`) più controlli relazionali su membership/claim. La property
> `onboarding_state` li aggrega in un valore logico usato solo dal middleware per i redirect.
> `onboarding_payment_done` resta sul modello (audit/storico) ma **non gating** più: lo
> step pagamento onboarding è stato rimosso dal funnel, differito alla Macro 19 (monetizzazione Stripe, 🧊 differita).

### Campi reali sottostanti

| Campo | Tipo | Valori | Default |
|---|---|---|---|
| `identity_status` | CharField | `UNVERIFIED`, `VERIFIED` | `UNVERIFIED` |
| `setup_completed` | BooleanField | `False`, `True` | `False` |

### Stati logici (property `onboarding_state`)

| Valore | Condizione di attivazione | Redirect middleware | Iniziale? | Finale? |
|---|---|---|---|---|
| `IDENTITY_PENDING` | `identity_status != 'VERIFIED'` | `verify_identity` | Sì | No |
| `SETUP_PENDING` | identità OK + `setup_completed == False` | `setup_wizard` | No | No |
| `MEMBERSHIP_PENDING` | tutto OK + nessuna membership attiva né claim/request pendenti (solo athlete/coach/president) | `onboarding_membership` | No | No |
| `COMPLETED` | tutte le condizioni precedenti soddisfatte | nessun redirect | No | Sì |

### Transizioni dei campi sottostanti

| Campo | Da → A | Trigger | Side effects | File |
|---|---|---|---|---|
| `identity_status` | `UNVERIFIED → VERIFIED` | click sul link di verifica email (`verify_email(token)`, token stateless firmato via `accounts/services/email_verification.py`) | `identity_verified_at = timezone.now()`; `log_action('ONBOARDING_IDENTITY_VERIFIED', method='EMAIL_CLICK')`; idempotente se già `VERIFIED` | `accounts/views.py` r. 156–186 |
| `setup_completed` | `False → True` | `setup_wizard()` — form valid | `log_action('ONBOARDING_SETUP_COMPLETED')` | `accounts/views.py` r. 108–109 |
| `setup_completed` (Society) | `False → True` | vista in `core/views.py` | `Society.setup_completed = True` parallelamente | `core/views.py` r. 166 |

### Guardrails

- Il middleware **non** redirige: utenti non autenticati, richieste `/api/*`, richieste AJAX (`X-Requested-With`), richieste `/accounts/verify-email/*` (path variabile, esentato per prefisso), utenti `is_staff` o `is_superuser`.
- `MEMBERSHIP_PENDING` per athlete/coach: basta avere *uno* tra membership attiva, claim `PENDING`, o `MembershipRequest PENDING` per superarlo.
- `MEMBERSHIP_PENDING` per president: serve `president_profile.managed_society` non nullo.

### Discrepanze con la documentazione

- ~~**CLAUDE.md (sezione "Onboarding State Machine") dice:** `IDENTITY_PENDING → PAYMENT_PENDING → SETUP_PENDING → MEMBERSHIP_PENDING → COMPLETED` come se fossero valori di un campo.~~
  **RISOLTA** — la sezione "Onboarding State Machine" non esiste più in CLAUDE.md: è stata sostituita dal puntatore a questo documento (§"State machines" in CLAUDE.md, cfr. punto 4 delle azioni chiuse in fondo). La natura di property calcolata è documentata qui sopra.

- ~~**BLUEPRINT.md §7.2 dice:** sequenza in 6 passi: Registrazione → Verifica identità → Selezione piano → Claim profilo → Autenticazione con squadra → Accesso completo.~~
  **Codice dice (onboarding reale, build corrente):** i passi che gatingano sono 3 (identity, setup, membership). Lo step "Selezione piano"/pagamento è stato rimosso dal funnel (differito alla Macro 19, monetizzazione Stripe). "Claim profilo" e "Autenticazione con squadra" restano entrambi inglobati in `MEMBERSHIP_PENDING` (uno o l'altro basta). La verifica identità non è più un mock SPID: è conferma email a click.

---

## 3. RBAC — Staff Role

**Model:** `accounts.User`
**Field:** `staff_role` (CharField)
**File:** [accounts/models.py](accounts/models.py) righe 20–27
**Default:** `NONE`

> Non è una macchina a stati con transizioni automatiche: il valore viene settato
> manualmente da admin. Determina i permessi tramite le property `can_upload`,
> `can_review`, `can_publish`.

### Stati

| Valore DB | Label | Permessi accumulati |
|---|---|---|
| `NONE` | Nessuno | Nessun accesso staff |
| `UPLOADER` | Collaboratore (Solo Upload) | `can_upload` |
| `REVIEWER` | Reviewer (Edit/Validazione) | `can_upload`, `can_review` |
| `PUBLISHER` | Publisher (Pubblicazione) | `can_upload`, `can_review`, `can_publish` |
| `SUPERADMIN` | Super Amministratore | Tutti i permessi staff |

### Guardrails

- `is_superuser` Django bypassa tutti i check di `staff_role` (accede a tutto).
- Il campo è separato da `is_staff` Django — avere `is_staff=True` non implica nessun `staff_role`.

### Discrepanze con la documentazione

- Nessuna discrepanza rilevante. CLAUDE.md e codice concordano.

---

## 4. AccountProfileLink (Claim Profilo)

**Model:** `accounts.AccountProfileLink`
**Field:** `status` (CharField)
**File:** [accounts/models.py](accounts/models.py) righe 228–235
**Default:** `PENDING`

### Stati

| Valore DB | Label | Descrizione | Iniziale? | Finale? |
|---|---|---|---|---|
| `PENDING` | In attesa | Richiesta inviata, in attesa approvazione admin | Sì | No |
| `APPROVED` | Approvato | Profilo sportivo collegato all'account | No | Sì |
| `REJECTED` | Rifiutato | Richiesta negata | No | Sì |

### Transizioni

| Da | A | Trigger | Side effects | File |
|---|---|---|---|---|
| — | `PENDING` | `claim_profile()` POST | Record creato con `status='PENDING'` | `accounts/views.py` r. 277 |
| `PENDING` | `APPROVED` o `REJECTED` | Admin via Django admin | Nessun side effect automatico rilevato nel codice | Admin site |

### Guardrails

- Un `PENDING` claim attivo è sufficiente a superare `MEMBERSHIP_PENDING` nell'onboarding.
- `unique_together` su `[user, athlete_profile, coach_profile, referee_profile]` impedisce duplicati.

---

## 5. MembershipRequest

**Model:** `management.MembershipRequest`
**Field:** `status` (CharField)
**File:** [management/models.py](management/models.py) righe 275–286
**Default:** `PENDING`

### Stati

| Valore DB | Label | Descrizione | Iniziale? | Finale? |
|---|---|---|---|---|
| `PENDING` | In attesa | Richiesta inviata al presidente della società | Sì | No |
| `APPROVED` | Approvata | Membership creata via `get_or_create` | No | Sì |
| `REJECTED` | Respinta | Richiesta negata | No | Sì |

### Transizioni

| Da | A | Trigger | Side effects | File |
|---|---|---|---|---|
| — | `PENDING` | `onboarding_membership()` POST | `get_or_create` con `defaults={'status': 'PENDING'}`; `log_action()` | `accounts/views.py` r. 239 |
| `PENDING` | `APPROVED` | `approve_membership()` POST (action=approve) | `Membership.get_or_create()` per il giocatore | `management/views.py` r. 429 |
| `PENDING` | `REJECTED` | `approve_membership()` POST (action=reject) | Solo salvataggio, messaggio warning | `management/views.py` r. 438 |

---

## 6. Convocation (Convocazioni)

**Model:** `management.Convocation`
**Field:** `status` (CharField) + property `current_effective_status`
**File:** [management/models.py](management/models.py) righe 128–166
**Default:** `DRAFT`

### Stati

| Valore DB | Label | Descrizione | Iniziale? | Finale? |
|---|---|---|---|---|
| `DRAFT` | Bozza | Creata, non ancora comunicata | Sì | No |
| `SENT_PRIVATE` | Inviata Privata | Comunicata ai convocati (non pubblica) | No | No |
| `PUBLISHED` | Pubblicata Ufficiale | Visibile pubblicamente | No | No |
| `LOCKED` | Bloccata (Gara iniziata) | Solo via property (vedi sotto) | No | Sì (temporaneo) |

### Property `current_effective_status`

Sovrascrive lo `status` persistito in base al tempo alla partita:
- Se `match_date` è passata (`diff <= 0`): restituisce `LOCKED`
- Se mancano ≤ 30 minuti (`diff <= 1800s`): restituisce `PUBLISHED`
- Altrimenti: restituisce lo `status` DB

> **Nota:** `LOCKED` non viene mai scritto nel DB — esiste solo come stato effettivo calcolato.

### Guardrails

- La property `current_effective_status` è solo lettura — non modifica il campo DB.
- AI cross-check (`perform_ai_cross_check()`) è un placeholder, non blocca nessuna transizione.

---

## 7. TrainingAttendance (Presenze Allenamenti)

**Model:** `management.TrainingAttendance`
**Field:** `status` (CharField)
**File:** [management/models.py](management/models.py) righe 101–110
**Default:** `PENDING`

### Stati

| Valore DB | Label | Descrizione | Iniziale? | Finale? |
|---|---|---|---|---|
| `PENDING` | In attesa | RSVP non ancora inviato | Sì | No |
| `PRESENT` | Presente | Check-in effettuato (geofence) | No | Sì |
| `ABSENT` | Assente | Assenza registrata | No | Sì |
| `JUSTIFIED` | Assente Giustificato | Assenza con motivazione accettata | No | Sì |

### Transizioni

| Da | A | Trigger | Side effects | File |
|---|---|---|---|---|
| `PENDING` | `PRESENT`/`ABSENT`/`JUSTIFIED` | `training_rsvp()` POST | `update_or_create` con `checkin_time = timezone.now()`; dati geofence (lat, lng, accuracy) salvati | `management/views.py` r. 103–112 |

---

## 8. PilotBug (Bug Tracking Interno)

**Model:** `management.PilotBug`
**Field:** `status` (CharField)
**File:** [management/models.py](management/models.py) righe 351–382
**Default:** `NEW`

### Stati

| Valore DB | Label | Finale? |
|---|---|---|
| `NEW` | New | No |
| `TRIAGED` | Triaged | No |
| `IN_PROGRESS` | In Progress | No |
| `MITIGATED` | Mitigated | No |
| `CLOSED` | Closed | Sì |
| `VERIFIED` | Verified | Sì |

Nessuna transizione automatica rilevata — gestito manualmente dall'admin.

---

## 9. PilotFeedback (Feedback Interno)

**Model:** `management.PilotFeedback`
**Field:** `status` (CharField)
**File:** [management/models.py](management/models.py) righe 408–425
**Default:** `NEW`

### Stati

| Valore DB | Label | Finale? |
|---|---|---|
| `NEW` | New | No |
| `ACKNOWLEDGED` | Acknowledged | No |
| `PLANNED` | Planned | No |
| `DONE` | Done | Sì |
| `WONT_FIX` | Won't Fix | Sì |

Nessuna transizione automatica rilevata — gestito manualmente dall'admin.

---

## 10. ParentCertification (Certificazione genitore — Macro 7b)

**Model:** `management.ParentCertification`
**Field di stato:** `status` (CharField, `TextChoices`)
**File modello:** [management/models.py](management/models.py) righe 627–773
**Servizio:** [management/services/certification_service.py](management/services/certification_service.py)
**Migration:** `management/migrations/0017_parentcertification.py`
**Default:** `RICHIESTA_INVIATA`

> **Natura della macchina:** macchina a stati "ricca" society-vouching via email, **ortogonale all'onboarding** (§2): il genitore resta `role='fan'` e raggiunge `COMPLETED` con sola email+setup; la certificazione è un gate **aggiuntivo** sull'accesso ai dati del figlio (`User.is_certified_parent_of`), non uno step di `onboarding_state`. Il sistema **non archivia** prove d'identità: inoltra la richiesta alla società e registra l'esito; il match nome+email lo fa un umano della società sul proprio gestionale. Razionale di prodotto in [[BLUEPRINT.md]] §7.7.

### Stati

| Valore DB | Label | Iniziale? | Finale? |
|---|---|---|---|
| `RICHIESTA_INVIATA` | Richiesta inviata | Sì | No |
| `IN_ATTESA_SOCIETA` | In attesa società | No | No |
| `CONFERMATA_SOCIETA` | Confermata società | No | No |
| `IN_ATTESA_CLICK_GENITORE` | In attesa click | No | No |
| `CERTIFICATA` | Certificata | No | Sì |
| `RIFIUTATA` | Rifiutata | No | Sì |
| `SCADUTA` | Scaduta | No | Sì |

`FINAL_STATUSES = {CERTIFICATA, RIFIUTATA, SCADUTA}`. Property `is_final` riflette l'appartenenza a questo set.

### Transizioni

| Da | A | Metodo modello | Side effects |
|---|---|---|---|
| `RICHIESTA_INVIATA` | `IN_ATTESA_SOCIETA` | `mark_in_attesa_societa()` | — (email di vouching orchestrata dal service) |
| `IN_ATTESA_SOCIETA` | `CONFERMATA_SOCIETA` | `conferma_societa()` | genera `token` (uuid4) + `token_expires_at` (`CERTIFICATION_LINK_VALIDITY_DAYS`); set `society_responded_at` |
| `IN_ATTESA_SOCIETA` | `RIFIUTATA` | `rifiuta_societa()` | set `society_responded_at`; finale |
| `CONFERMATA_SOCIETA` | `IN_ATTESA_CLICK_GENITORE` | `mark_in_attesa_click()` | — (mail con link orchestrata dal service) |
| `IN_ATTESA_CLICK_GENITORE` | `CERTIFICATA` | `certifica_via_click()` | set `certified_at`; attiva l'accesso ai dati del figlio |
| `IN_ATTESA_CLICK_GENITORE` | `SCADUTA` | `scadi()` | finestra di validità superata; finale |

### Guardrails

- **Validazione stato di partenza:** ogni metodo chiama `_require(expected)` e alza `ValueError` sulle transizioni non ammesse — non esistono salti di stato silenziosi.
- **Link scaduto:** `certifica_via_click()` rifiuta con `ValueError` se `is_link_expired` (`token_expires_at` superato), anche se lo stato è `IN_ATTESA_CLICK_GENITORE`.
- **Nessun side effect email nel modello:** i metodi mutano solo lo stato/timestamp; l'invio mail (vouching alla società, link al genitore) è orchestrato da `certification_service`.
- **Una sola richiesta aperta per coppia:** `UniqueConstraint` `uniq_parentcert_open_per_parent_child` su `(parent, child)` con condizione `~Q(status__in=[CERTIFICATA, RIFIUTATA, SCADUTA])` — le righe finali non contano, si può ri-richiedere.
- **Email società sempre valorizzata:** la notifica parte verso `_society_recipients`; il setup post-approvazione del presidente (Macro 18) richiede obbligatoriamente l'email di contatto della società, così la lista non è mai vuota.

---

## 11. Personificazione società presidente (Macro 18)

**Model:** `management.MembershipRequest` **riusato** con `role='PRESIDENT'` come discriminatore — nessun campo/stato dedicato, nessuno schema-change.
**Field di stato:** `status` (CharField, lo stesso di §5)
**File modello:** [management/models.py](management/models.py) righe 275–286
**Servizio:** [management/services/president_personification.py](management/services/president_personification.py)
**Default:** `PENDING`

> **Natura della macchina:** questa **non** è una state machine "ricca" con campo di stato proprio. È la macchina di §5 (`MembershipRequest.status`) riusata, distinta solo dal discriminatore `role='PRESIDENT'`. Il ramo PRESIDENT è isolato dal consumer player-gated (`approve_membership` in `management/views.py`): viene approvato **solo** dall'admin via op_admin_site. Di conseguenza nel ramo PRESIDENT sono raggiunti a runtime solo `PENDING` e `APPROVED`; `REJECTED` non è prodotto da alcun percorso PRESIDENT corrente (gestito solo difensivamente, vedi Guardrails).

### Stati

| Valore DB | Label | Descrizione (ramo PRESIDENT) | Iniziale? | Finale? |
|---|---|---|---|---|
| `PENDING` | In attesa | Richiesta di personificazione inviata, in attesa di approvazione admin | Sì | No |
| `APPROVED` | Approvata | Presidente agganciato alla società via `PresidentProfile.managed_society` | No | Sì |
| `REJECTED` | Respinta | Non raggiunto dal ramo PRESIDENT (solo difensivo) | No | (Sì) |

### Transizioni

| Da | A | Trigger | Side effects | File |
|---|---|---|---|---|
| — | `PENDING` | `request_president_personification()` da `choose_society` POST | `get_or_create(role='PRESIDENT', defaults={'status':'PENDING'})`, **idempotente** (richiesta PENDING esistente → ritorna senza duplicare) | [core/views.py](core/views.py) r. 276 → [president_personification.py](management/services/president_personification.py) r. 64–69 |
| `PENDING` | `APPROVED` | Action admin `approve_president_personification` → `approve_president_request()` (dentro `transaction.atomic()` + `select_for_update`) | `PresidentProfile.objects.filter(user=...).update(managed_society=...)` — **nessuna Membership** creata; `status='APPROVED'`; notifica email best-effort **fuori** dall'atomic | [management/admin.py](management/admin.py) r. 40–64 → [president_personification.py](management/services/president_personification.py) r. 99–135 |
| `PENDING` | `PENDING` (nessuna transizione) | `approve_president_request()` su società che ha **già** un presidente | **Guard 1:1 applicativo**: ritorna `(False, errore)`, lo `status` resta `PENDING`, nessun side-effect | [president_personification.py](management/services/president_personification.py) r. 116–122 |

### Guardrails

- **Guard 1:1 (`already_managed`):** `PresidentProfile.managed_society` è un `OneToOne`. Prima di agganciare, il servizio verifica che la società non abbia già un presidente; in caso positivo **blocca l'approvazione con un errore leggibile** invece di lasciar salire un `IntegrityError` grezzo. Non è una transizione di stato: la richiesta resta `PENDING`. [president_personification.py](management/services/president_personification.py) r. 116–122.
- **Guard idempotenza in creazione:** se l'utente gestisce già una società (`managed_society_id` valorizzato) o ha già una richiesta `PENDING`, `request_president_personification()` non duplica nulla. [president_personification.py](management/services/president_personification.py) r. 51–62.
- **Side-effect del solo `managed_society`:** all'approvazione **non** viene creata alcuna `Membership` PRESIDENT (coerente con `create_society` e con la bacheca del "presidente de-vincolato"). L'aggancio è una `.update()` diretta sul `PresidentProfile`, **non** passa per `_sync_profile_denorm` (quel denormalizzatore serve il ramo player/coach in `membership_enrollment.py`, non questo flusso). [president_personification.py](management/services/president_personification.py) r. 124–127.
- **Concorrenza:** l'approvazione serializza le richieste concorrenti con `select_for_update()` sul lock della richiesta, dentro `transaction.atomic()`. [president_personification.py](management/services/president_personification.py) r. 99–105.
- **`REJECTED` difensivo:** `request_president_personification()` riapre a `PENDING` una eventuale richiesta `REJECTED`/`APPROVED` sulla stessa società (r. 70–74), ma nessun percorso PRESIDENT corrente scrive `REJECTED`: il ramo non è toccato da `approve_membership`.

### Relazione con §5

§5 descrive la macchina `MembershipRequest` per il tesseramento giocatore (`role` player, `PENDING→APPROVED` con creazione `Membership`, oppure `REJECTED`). Qui lo stesso modello/campo è riusato con `role='PRESIDENT'`: stati identici, ma trigger (admin op_admin, non presidente di società), side-effect (`managed_society`, **non** `Membership`) e guard (1:1) sono diversi.

---

## 12. MatchJuryLink (Link giuria monouso — Macro 14)

**Model:** `matches.MatchJuryLink`
**Field di stato:** `status` (CharField, `TextChoices`)
**File modello:** [matches/models.py](matches/models.py) (in coda) — **Servizio:** [matches/services/jury_link_service.py](matches/services/jury_link_service.py)
**Default:** `ACTIVE`
**Migration:** `0018` (additiva: nuovo modello + partial unique index + `MatchReport.referee_signature`)

> **Natura della macchina:** link monouso per l'accesso **no-account** della giuria alla compilazione del referto digitale di **una** partita. "Monouso" = un ciclo di vita, non un singolo click: il link resta valido per più sessioni/visite durante la compilazione e **muore alla chiusura del referto** (`CONSUMED`). Nessuna transizione di ritorno da alcuno stato terminale. Scadenza **valutata a lettura** (nessun cron in questo giro): un link `ACTIVE` oltre `expires_at` è degradato lazy a `EXPIRED` al primo `resolve`/landing.

### Stati

| Valore DB | Label | Descrizione | Iniziale? | Finale? |
|---|---|---|---|---|
| `ACTIVE` | Attivo | Link emesso e valido (finché non scade o si chiude il referto) | Sì | No |
| `CONSUMED` | Consumato | Referto chiuso con successo tramite il ciclo di vita del link | No | Sì |
| `REVOKED` | Revocato | Revocato da staff/admin, o auto-revocato dall'emissione di un nuovo link sullo stesso match | No | Sì |
| `EXPIRED` | Scaduto | Backstop 7 giorni superato (degrado lazy a lettura) | No | Sì |

### Transizioni

| Da | A | Trigger | Side effects | File |
|---|---|---|---|---|
| — | `ACTIVE` | `JuryLinkService.issue(match, created_by)` | Revoca in transazione l'eventuale `ACTIVE` precedente; `token = secrets.token_urlsafe(32)`; `expires_at = now + 7gg` | [jury_link_service.py](matches/services/jury_link_service.py) `issue` |
| `ACTIVE` | `CONSUMED` | Close riuscito del referto digitale (`api_digital_report_close`) | **Atomico** col `DRAFT→NEEDS_REVIEW` del referto; `consumed_at`, `report` valorizzati; solo su close riuscito | [api_views_digital.py](matches/api_views_digital.py) `close` → `JuryLinkService.consume` |
| `ACTIVE` | `REVOKED` | `JuryLinkService.revoke(match)` (endpoint `.../jury-link/revoke/`) **oppure** nuova `issue` sullo stesso match | `revoked_at` valorizzato | [jury_link_service.py](matches/services/jury_link_service.py) `revoke` / `issue` |
| `ACTIVE` | `EXPIRED` | Primo `resolve`/landing dopo `expires_at` (lazy, niente cron) | `status='EXPIRED'` persistito; trattato come invalido | [jury_link_service.py](matches/services/jury_link_service.py) `resolve` / [api_views_jury.py](matches/api_views_jury.py) `jury_link_landing` |

### Guardrails

- **Un solo `ACTIVE` per match:** garantito a livello DB da un partial unique index `UniqueConstraint(fields=['match'], condition=Q(status='ACTIVE'))` (SQLite supporta indici parziali), rinforzato applicativamente: `issue` revoca il precedente `ACTIVE` in `transaction.atomic()` prima di crearne uno nuovo.
- **Consume solo su close riuscito:** un close respinto (guardia di stato non-DRAFT → 400; firma mancante → 400; schema invalido → 422) **non** consuma il link, che resta `ACTIVE`. Il consume è dentro l'`atomic` del close, contestuale al cambio stato del referto.
- **Token morto non riapre:** un secondo close via lo stesso token dopo `CONSUMED` fallisce in autenticazione (403), prima della guardia di stato — il link non risolve più.
- **Accesso via token ortogonale all'auth:** `resolve(token, match)` accetta il link solo se `ACTIVE`, non scaduto e appartenente a **quel** match. L'accesso autenticato esistente alle API digitali resta intatto; il token affianca l'anonimo, non lo sostituisce all'utente.
- **Emissione = riga stessa come audit:** `MatchReportAuditLog.report` non è nullable e l'emissione precede il referto, quindi l'audit dell'emissione è la riga `MatchJuryLink` (`created_by` + `created_at`). Le azioni **via** link (start/update/close) sono loggate in `MatchReportAuditLog` con `user=None`.

### Firma arbitro (collegata al close)

Il close del canale digitale richiede ora un campo firma **nome+cognome** obbligatorio (≥2 token), persistito su `MatchReport.referee_signature` e in `MatchReportAuditLog.after`. Sostituisce il PIN personale (decaduto nel modello no-account). Il close finisce **sempre** in `NEEDS_REVIEW` (invariante di sicurezza: nessun auto-publish dal canale digitale). Vedi §1 e BLUEPRINT §7.4.3.

---

## Funzionalità descritte nel Blueprint ma non implementate

Le seguenti funzionalità sono descritte in `BLUEPRINT.md` ma **non hanno modelli o campo corrispondente nel codice**:

| Funzionalità | Sezione Blueprint | Stato |
|---|---|---|
| **Match_Jury_Links** — link monouso per-partita | §7.4.1 | ✅ **Fondamenta backend as-built (2026-07-19, dev)** — modello/service/endpoint/accesso-token/landing. Macchina in §12. UI/QR/offline-first fuori scope (giri futuri) |
| **Firma arbitro** — nome+cognome al close, referto immutabile post-firma | §7.4.3 | ✅ **As-built (2026-07-19, dev)** — `MatchReport.referee_signature`, obbligatoria al close, in audit. PIN personale decaduto |
| UI mobile compilazione referto / QR / offline-first (Service Worker + IndexedDB) | §7.4 | Non implementato (giri futuri Macro 14 + Macro 21) |

**Verdetto:** le fondamenta backend del link giuria e la firma arbitro sono ora a codice su dev (v. §12); restano di roadmap futura la UI di compilazione, il QR e l'offline-first. Il Blueprint le include come obiettivi di progetto; non indicano un bug.

---

## Azioni da intraprendere

In ordine di priorità:

1. ~~**[ALTA] Aggiornare `CLAUDE.md` — sezione "Match Report Pipeline":**
   Aggiungere `NEEDS_REVIEW` e `REJECTED` al grafo degli stati. Correggere i nomi dei campi: `source_channel` (non `source`), `source_type` (non `origin`). Rendere esplicito che il flusso non è lineare (es. `NEEDS_REVIEW → PROCESSING` per riprocessamento).~~
   **CHIUSO il 24-apr-2026** — Risolto indirettamente: la sezione dedicata in `CLAUDE.md` è stata sostituita da un puntatore a questo documento (vedi §"State machines" in `CLAUDE.md`, con istruzione esplicita "Non duplicare qui"). La divergenza è eliminata alla radice: non c'è più nulla da allineare.

2. ~~**[ALTA] Aggiornare `docs/BLUEPRINT.md` §8 — rinominare `VERIFIED` → `VALIDATED`:**
   Il blueprint usa `VERIFIED` per lo stato di approvazione admin; il codice usa `VALIDATED`. Divergenza di nomenclatura che può causare confusione durante sviluppo e code review.~~
   **CHIUSO il 09-mag-2026** — Blueprint §8 corretto: la riga del workflow ora usa `VALIDATED` al posto di `VERIFIED`. Verificato con `grep -n "VERIFIED"` su `BLUEPRINT.md`: zero occorrenze residue.

3. ~~**[MEDIA] Aggiornare `docs/BLUEPRINT.md` §8 — aggiungere `PROCESSING` e `DRAFT`:**
   Il flusso nel blueprint parte da `UPLOADED` direttamente a `EXTRACTED`, saltando `PROCESSING`. E ignora `DRAFT` (usato per referti digitali). Il blueprint è incompleto rispetto all'implementazione reale.~~
   **CHIUSO il 09-mag-2026** — Blueprint §8 ora distingue il flusso cartaceo (UPLOADED → PROCESSING → EXTRACTED → VALIDATED → PUBLISHED) dal flusso digitale (DRAFT → VALIDATED → PUBLISHED), include i branch NEEDS_REVIEW/REJECTED con possibilità di ritorno a PROCESSING, e rimanda esplicitamente a STATE_MACHINES.md §1 come fonte di verità.

4. ~~**[MEDIA] Aggiornare `CLAUDE.md` — chiarire la natura della property `onboarding_state`:**
   La sezione "Onboarding State Machine" implica l'esistenza di un campo `status` sull'utente. In realtà è una property calcolata. Aggiungere una nota che spiega i tre campi reali sottostanti e la logica di composizione.~~
   **CHIUSO il 24-apr-2026** — Risolto indirettamente: la sezione "Onboarding State Machine" in `CLAUDE.md` non esiste più come blocco autonomo; la descrizione del modello è delegata a questo documento (vedi §"State machines" in `CLAUDE.md`). La property calcolata è già documentata qui, quindi non c'è più rischio di fraintendimento su un presunto campo `status`.

5. **[BASSA] Documentare le transizioni di `AccountProfileLink` lato admin:**
   L'approvazione/rifiuto del claim avviene via Django admin senza servizio dedicato. Valutare se aggiungere un servizio esplicito con audit trail (come per `MembershipRequest`).

6. ~~**[BASSA] Decidere il futuro di firma arbitro:**~~
   ~~Jury token~~ **CHIUSO il 19-lug-2026** — Blueprint §7.4.1 riscritto sul modello link monouso per-partita (`Match_Jury_Links`), ratificato in [syllabus/14](syllabus/14_referto_digitale_mobile.md) §14.2; il token federale 30-min è decaduto per vincolo GUG/portale, non emendabile (archiviato in FUTURE_IDEAS.md §1). **Firma arbitro DECISA e as-built (19-lug-2026):** nome+cognome digitati al close (obbligatorio), persistiti su `MatchReport.referee_signature` + audit; PIN personale decaduto; il codice breve 4-6 cifre resta anti-abuso spento. Blueprint §7.4.3 e syllabus/14 §14.4/§14.6-bis aggiornati; macchina del link in §12. **Fondamenta backend Macro 14 complete su dev;** UI/QR/offline-first fuori scope (giri futuri).

---

*Convenzione di questa lista:* i fix marcati **CHIUSO** non vengono rimossi, ma restano come storico delle decisioni risolte. La regola è: fix chiuso = testo barrato + annotazione con data e modalità di risoluzione; fix aperto = testo invariato.
