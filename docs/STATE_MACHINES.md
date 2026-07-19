# State Machines — Source of Truth

Questo documento descrive le macchine a stati implementate nel codice.
Se il blueprint di prodotto o altri documenti dicono cose diverse, **questo file vince**.

Ultimo aggiornamento: 2026-06-22
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

## Funzionalità descritte nel Blueprint ma non implementate

Le seguenti funzionalità sono descritte in `BLUEPRINT.md` ma **non hanno modelli o campo corrispondente nel codice**:

| Funzionalità | Sezione Blueprint | Stato |
|---|---|---|
| **Match_Jury_Links** — link monouso per-partita, valido fino a chiusura referto + backstop 7 giorni (sostituisce il token 30-min, decaduto per vincolo federale GUG/portale — v. [syllabus/14](syllabus/14_referto_digitale_mobile.md) §14.2) | §7.4.1 | Non implementato |
| **Firma arbitro / PIN** — referto immutabile post-firma, correzioni solo via admin | §7.4.3 | Non implementato |

**Verdetto:** sono funzionalità di roadmap futura, non implementazione attuale. Il Blueprint le include come obiettivi di progetto; non indicano un bug.

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

6. **[BASSA] Decidere il futuro di firma arbitro:**
   ~~Jury token~~ **CHIUSO il 19-lug-2026** — Blueprint §7.4.1 riscritto sul modello link monouso per-partita (`Match_Jury_Links`), ratificato in [syllabus/14](syllabus/14_referto_digitale_mobile.md) §14.2; il token federale 30-min è decaduto per vincolo GUG/portale, non emendabile (archiviato in FUTURE_IDEAS.md §1). Resta da aggiornare il Blueprint §7.4.3 con una nota esplicita che segnala la firma arbitro/PIN come "non implementata — roadmap futura".

---

*Convenzione di questa lista:* i fix marcati **CHIUSO** non vengono rimossi, ma restano come storico delle decisioni risolte. La regola è: fix chiuso = testo barrato + annotazione con data e modalità di risoluzione; fix aperto = testo invariato.
