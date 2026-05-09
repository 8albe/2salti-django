# State Machines — Source of Truth

Questo documento descrive le macchine a stati implementate nel codice.
Se il blueprint di prodotto o altri documenti dicono cose diverse, **questo file vince**.

Ultimo aggiornamento: 2026-04-20
Generato leggendo:
- `accounts/models.py`
- `accounts/middleware.py`
- `accounts/views.py`
- `matches/models.py`
- `matches/services/publishing_service.py`
- `matches/services/integrity_service.py`
- `matches/services/ocr_service.py`
- `matches/views.py`
- `management/models.py`
- `core/models.py`
- `docs/PRODUCT_BLUEPRINT.md`
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
| `UPLOADED` | Caricato (In attesa) | File caricato, in coda per OCR | Sì (solo FILE) | No |
| `PROCESSING` | In Elaborazione OCR | OCR provider in esecuzione | No | No |
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
| `UPLOADED` | `PROCESSING` | `OCRService.process_and_update()` | Avvio OCR provider, salvataggio intermedio | `matches/services/ocr_service.py` |
| `NEEDS_REVIEW` | `PROCESSING` | `OCRService.process_and_update()` — riprocessamento | Come sopra | `matches/services/ocr_service.py` |
| `REJECTED` | `PROCESSING` | `OCRService.process_and_update()` — riprocessamento | Come sopra | `matches/services/ocr_service.py` |
| `UPLOADED` | `REJECTED` | `OCRService.process_and_update()` | `validation_notes` con errore | `matches/services/ocr_service.py` r. 255 |
| `PROCESSING` | `EXTRACTED` | `OCRService.process_and_update()` — OCR OK + quality gate OK | `normalized_data` popolato, `validation_notes` con gate results, audit log `OCR_PROCESSING_SUCCESS`, link a `match` | `matches/services/ocr_service.py` r. 366 |
| `PROCESSING` | `NEEDS_REVIEW` | `OCRService.process_and_update()` — quality gate bloccante | `validation_notes` con gate results, `NotificationService.notify_report_needs_review()` | `matches/services/ocr_service.py` r. 361 |
| `PROCESSING` | `NEEDS_REVIEW` | `OCRService.process_and_update()` — eccezione OCR | `validation_notes` con errore, notifica staff | `matches/services/ocr_service.py` r. 385 |
| `EXTRACTED` | `VALIDATED` | `report_review()` — reviewer setta stato manualmente | `validated_by`, `validated_at` settati; `MatchReportAuditLog` action=`validate` | `matches/views.py` r. 316–321 |
| `NEEDS_REVIEW` | `VALIDATED` | `report_review()` — reviewer override | Come sopra | `matches/views.py` |
| `NEEDS_REVIEW` | `EXTRACTED` | `report_review()` — reviewer ri-qualifica | Come sopra senza `validated_by` | `matches/views.py` |
| `VALIDATED` | `PUBLISHED` | `PublishingService.publish_report()` | Match aggiornato (punteggi, quarti, `is_finished=True`); MatchEvent ricreati; stats atleti aggiornate; standings rebuild sincrono; `MatchReportAuditLog` action=`publish`; `AuditLog` action=`PUBLISH_REPORT` | `matches/services/publishing_service.py` r. 139–142 |
| `PUBLISHED` | `PUBLISHED` | `PublishingService.publish_report()` — ripubblicazione | Come sopra; `MatchReportAuditLog` action=`republish` | `matches/services/publishing_service.py` r. 58 |
| `PUBLISHED` | `VALIDATED` | `PublishingService.publish_report()` — de-pubblicazione automatica | Scatta quando un *altro* report per lo stesso match viene pubblicato; `internal_notes` aggiornate; `MatchReportAuditLog` action=`depublish` | `matches/services/publishing_service.py` r. 123–137 |

### Guardrails

- **OCR precondition:** `source_channel == 'FILE'` richiede che `report.file` esista; altrimenti → `REJECTED` immediatamente.
- **Publish readiness check:** `OCRSchemaValidator.assess_publish_readiness(data)` valuta blockers e warnings. Se `safe=False` e `force=False` la pubblicazione viene bloccata con messaggio esplicito.
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

- **PRODUCT_BLUEPRINT.md §8 dice:** `UPLOADED → EXTRACTED → NEEDS_REVIEW → VERIFIED → PUBLISHED` + `REJECTED`
  **Codice dice:** lo stato si chiama `VALIDATED` (non `VERIFIED`); esiste anche `PROCESSING` (assente nel blueprint); `DRAFT` esiste (assente nel blueprint).
  **Verdetto:** codice corretto. Nel blueprint `VERIFIED` va rinominato `VALIDATED`. `PROCESSING` e `DRAFT` vanno aggiunti alla descrizione del flusso.

- **CLAUDE.md (sezione "Match Report Pipeline") dice:** `source` (FILE/DIGITAL), `origin` (MANUAL/EMAIL)
  **Codice dice:** i campi si chiamano `source_channel` (FILE/DIGITAL) e `source_type` (MANUAL/EMAIL).
  **Verdetto:** codice corretto, CLAUDE.md usa nomi sbagliati.

---

## 2. Onboarding utente (flusso composito)

**Model:** `accounts.User`
**Field:** property calcolata `onboarding_state` — **non è un campo DB**
**File:** [accounts/models.py](accounts/models.py) righe 75–110
**Enforced by:** `OnboardingMiddleware.process_request()` — [accounts/middleware.py](accounts/middleware.py)

> **Nota critica:** gli "stati" dell'onboarding non sono un singolo campo sul modello.
> Sono la combinazione di tre campi reali (`identity_status`, `subscription_status`, `setup_completed`)
> più controlli relazionali su membership/claim. La property `onboarding_state` li aggrega
> in un valore logico usato solo dal middleware per i redirect.

### Campi reali sottostanti

| Campo | Tipo | Valori | Default |
|---|---|---|---|
| `identity_status` | CharField | `UNVERIFIED`, `VERIFIED` | `UNVERIFIED` |
| `subscription_status` | CharField | `INACTIVE`, `ACTIVE` | `INACTIVE` |
| `setup_completed` | BooleanField | `False`, `True` | `False` |

### Stati logici (property `onboarding_state`)

| Valore | Condizione di attivazione | Redirect middleware | Iniziale? | Finale? |
|---|---|---|---|---|
| `IDENTITY_PENDING` | `identity_status != 'VERIFIED'` | `verify_identity` | Sì | No |
| `PAYMENT_PENDING` | identità OK + `role != 'fan'` + `subscription_status != 'ACTIVE'` | `process_payment` | No | No |
| `SETUP_PENDING` | identità OK + pagamento OK (o fan) + `setup_completed == False` | `setup_wizard` | No | No |
| `MEMBERSHIP_PENDING` | tutto OK + nessuna membership attiva né claim/request pendenti (solo athlete/coach/president) | `onboarding_membership` | No | No |
| `COMPLETED` | tutte le condizioni precedenti soddisfatte | nessun redirect | No | Sì |

### Transizioni dei campi sottostanti

| Campo | Da → A | Trigger | Side effects | File |
|---|---|---|---|---|
| `identity_status` | `UNVERIFIED → VERIFIED` | `verify_identity()` POST | `identity_verified_at = timezone.now()`; `log_action('ONBOARDING_IDENTITY_VERIFIED')` | `accounts/views.py` r. 130–132 |
| `subscription_status` | `INACTIVE → ACTIVE` | `process_payment()` POST | `subscription_end_date = now + 365gg`; `log_action('ONBOARDING_PAYMENT_COMPLETED')` | `accounts/views.py` r. 160–162 |
| `setup_completed` | `False → True` | `setup_wizard()` — form valid | `log_action('ONBOARDING_SETUP_COMPLETED')` | `accounts/views.py` r. 89 |
| `setup_completed` (Society) | `False → True` | vista in `core/views.py` | `Society.setup_completed = True` parallelamente | `core/views.py` r. 166 |

### Guardrails

- Il middleware **non** redirige: utenti non autenticati, richieste `/api/*`, richieste AJAX (`X-Requested-With`), utenti `is_staff` o `is_superuser`.
- I fan (`role == 'fan'`) saltano `PAYMENT_PENDING` e `MEMBERSHIP_PENDING` → arrivano a `COMPLETED` dopo solo identità e setup.
- `MEMBERSHIP_PENDING` per athlete/coach: basta avere *uno* tra membership attiva, claim `PENDING`, o `MembershipRequest PENDING` per superarlo.
- `MEMBERSHIP_PENDING` per president: serve `president_profile.managed_society` non nullo.

### Discrepanze con la documentazione

- **CLAUDE.md (sezione "Onboarding State Machine") dice:** `IDENTITY_PENDING → PAYMENT_PENDING → SETUP_PENDING → MEMBERSHIP_PENDING → COMPLETED` come se fossero valori di un campo.
  **Codice dice:** sono stati logici di una property, non un singolo campo `status`. Il campo reale sottostante è la combinazione di `identity_status` + `subscription_status` + `setup_completed` + relazioni.
  **Verdetto:** CLAUDE.md corretto nel descrivere il flusso, ma fuorviante nell'implicare l'esistenza di un campo unico. Da aggiornare per chiarire che è una property calcolata.

- **PRODUCT_BLUEPRINT.md §7.2 dice:** sequenza in 6 passi: Registrazione → Verifica identità → Selezione piano → Claim profilo → Autenticazione con squadra → Accesso completo.
  **Codice dice:** i passi reali sono 4 (identity, payment, setup, membership). "Selezione piano" corrisponde a `PAYMENT_PENDING`. "Claim profilo" e "Autenticazione con squadra" sono entrambi inglobati in `MEMBERSHIP_PENDING` (uno o l'altro basta).
  **Verdetto:** entrambi validi, il blueprint è più granulare per la UX, il codice li unifica. Nessuna correzione urgente.

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

## Funzionalità descritte nel Blueprint ma non implementate

Le seguenti funzionalità sono descritte in `PRODUCT_BLUEPRINT.md` ma **non hanno modelli o campo corrispondente nel codice**:

| Funzionalità | Sezione Blueprint | Stato |
|---|---|---|
| **Jury token** — token match-specific con finestra 30 min, revoca automatica al fischio | §7.4.1 | Non implementato |
| **Firma arbitro / PIN** — referto immutabile post-firma, correzioni solo via admin | §7.4.3 | Non implementato |

**Verdetto:** sono funzionalità di roadmap futura, non implementazione attuale. Il Blueprint le include come obiettivi di progetto; non indicano un bug.

---

## Azioni da intraprendere

In ordine di priorità:

1. ~~**[ALTA] Aggiornare `CLAUDE.md` — sezione "Match Report Pipeline":**
   Aggiungere `NEEDS_REVIEW` e `REJECTED` al grafo degli stati. Correggere i nomi dei campi: `source_channel` (non `source`), `source_type` (non `origin`). Rendere esplicito che il flusso non è lineare (es. `NEEDS_REVIEW → PROCESSING` per riprocessamento).~~
   **CHIUSO il 24-apr-2026** — Risolto indirettamente: la sezione dedicata in `CLAUDE.md` è stata sostituita da un puntatore a questo documento (vedi §"State machines" in `CLAUDE.md`, con istruzione esplicita "Non duplicare qui"). La divergenza è eliminata alla radice: non c'è più nulla da allineare.

2. ~~**[ALTA] Aggiornare `docs/PRODUCT_BLUEPRINT.md` §8 — rinominare `VERIFIED` → `VALIDATED`:**
   Il blueprint usa `VERIFIED` per lo stato di approvazione admin; il codice usa `VALIDATED`. Divergenza di nomenclatura che può causare confusione durante sviluppo e code review.~~
   **CHIUSO il 09-mag-2026** — Blueprint §8 corretto: la riga del workflow ora usa `VALIDATED` al posto di `VERIFIED`. Verificato con `grep -n "VERIFIED"` su `PRODUCT_BLUEPRINT.md`: zero occorrenze residue.

3. ~~**[MEDIA] Aggiornare `docs/PRODUCT_BLUEPRINT.md` §8 — aggiungere `PROCESSING` e `DRAFT`:**
   Il flusso nel blueprint parte da `UPLOADED` direttamente a `EXTRACTED`, saltando `PROCESSING`. E ignora `DRAFT` (usato per referti digitali). Il blueprint è incompleto rispetto all'implementazione reale.~~
   **CHIUSO il 09-mag-2026** — Blueprint §8 ora distingue il flusso cartaceo (UPLOADED → PROCESSING → EXTRACTED → VALIDATED → PUBLISHED) dal flusso digitale (DRAFT → VALIDATED → PUBLISHED), include i branch NEEDS_REVIEW/REJECTED con possibilità di ritorno a PROCESSING, e rimanda esplicitamente a STATE_MACHINES.md §1 come fonte di verità.

4. ~~**[MEDIA] Aggiornare `CLAUDE.md` — chiarire la natura della property `onboarding_state`:**
   La sezione "Onboarding State Machine" implica l'esistenza di un campo `status` sull'utente. In realtà è una property calcolata. Aggiungere una nota che spiega i tre campi reali sottostanti e la logica di composizione.~~
   **CHIUSO il 24-apr-2026** — Risolto indirettamente: la sezione "Onboarding State Machine" in `CLAUDE.md` non esiste più come blocco autonomo; la descrizione del modello è delegata a questo documento (vedi §"State machines" in `CLAUDE.md`). La property calcolata è già documentata qui, quindi non c'è più rischio di fraintendimento su un presunto campo `status`.

5. **[BASSA] Documentare le transizioni di `AccountProfileLink` lato admin:**
   L'approvazione/rifiuto del claim avviene via Django admin senza servizio dedicato. Valutare se aggiungere un servizio esplicito con audit trail (come per `MembershipRequest`).

6. **[BASSA] Decidere il futuro di Jury token e firma arbitro:**
   Aggiornare il Blueprint §7.4.1 e §7.4.3 con una nota esplicita che segnala queste funzionalità come "non implementate — roadmap futura", per evitare che chi legge il blueprint si aspetti di trovare codice corrispondente.

---

*Convenzione di questa lista:* i fix marcati **CHIUSO** non vengono rimossi, ma restano come storico delle decisioni risolte. La regola è: fix chiuso = testo barrato + annotazione con data e modalità di risoluzione; fix aperto = testo invariato.
