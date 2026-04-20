# Domain Glossary — Italian Terminology ↔ Django Code

Questo documento è il ponte tra il linguaggio di prodotto usato nel blueprint (italiano) e i modelli Django del codice (inglese). Fonte di verità per i nomi.

**Ultimo aggiornamento:** 2026-04-20
**Generato leggendo:**
- `docs/STATE_MACHINES.md` (fonte di verità per stati e transizioni)
- `docs/PRODUCT_BLUEPRINT.md` (vocabolario di prodotto)
- `accounts/models.py`, `core/models.py`, `matches/models.py`, `management/models.py`, `seasons/models.py`

**Legenda status:**
- ✅ Implementato — modello Django esatto presente
- 🟡 Parzialmente implementato — esiste qualcosa, ma non copre tutto quello che il blueprint descrive
- ❌ Non implementato — il blueprint ne parla, nel codice non c'è nulla
- 📋 Non nel blueprint — esiste nel codice, il blueprint non lo menziona

---

## Entità principali (§10 "Entità core")

| Termine blueprint | Modello Django | App | File | Status | Note |
|---|---|---|---|---|---|
| Partita / Match | `Match` | matches | matches/models.py | ✅ | Contiene score, quarter_scores, referees, has_report, is_finished |
| Squadra / Team | `Team` | core | core/models.py | ✅ | FK verso Society e League; nome auto-generato da Society + category |
| Società | `Society` | core | core/models.py | ✅ | Creata dal Presidente nel wizard onboarding |
| Sport | `Sport` | core | core/models.py | ✅ | Multi-sport: pallanuoto e altri; contiene point_system e period_label |
| Campionato / Competizione | `League` | core | core/models.py | ✅ | Include stagione, girone, livello; blueprint §10 la chiama "Competition" |
| Atleta (profilo sportivo) | `AthleteProfile` | accounts | accounts/models.py | ✅ | OneToOne con User; stats calcolate (total_goals, total_matches, total_expulsions) |
| Allenatore / Coach | `CoachProfile` | accounts | accounts/models.py | ✅ | OneToOne con User; specialization, years_experience |
| Arbitro / Referee | `RefereeProfile` | accounts | accounts/models.py | ✅ | OneToOne con User; license_number, total_matches_officiated |
| Presidente | `PresidentProfile` | accounts | accounts/models.py | ✅ | OneToOne con User; punta a managed_society |
| Evento partita | `MatchEvent` | matches | matches/models.py | ✅ | event_type codificato; blueprint §10 chiama la tabella "Match_Events" |
| Configurazione evento per sport | `SportEventConfig` | matches | matches/models.py | 📋 | Mappa event_code → label per sport; non menzionato nel blueprint |
| Classifica | `LeagueStanding` | core | core/models.py | ✅ | Tabella denormalizzata persistita; mai scrivere direttamente — usare `standings_service` |
| Stagione | `League.season` (CharField) | core | core/models.py | 🟡 | La stagione è un CharField su League (es. "2024-2025"), non un modello autonomo; blueprint §10 suggerisce "Seasons" come entità separata |
| Impianto / Venue | `Match.location` (CharField) | matches | matches/models.py | 🟡 | Blueprint §10 menziona "Venues" come entità; nel codice è solo stringa sul match |
| Validation_Logs | `MatchReportAuditLog` | matches | matches/models.py | ✅ | Blueprint §10 li chiama "Validation_Logs"; il codice usa `MatchReportAuditLog` |

---

## Entità business (§10 "Entità business")

| Termine blueprint | Modello Django | App | File | Status | Note |
|---|---|---|---|---|---|
| Account utente / User_Accounts | `User` | accounts | accounts/models.py | ✅ | AbstractUser con role, staff_role, identity_status, subscription_status, setup_completed |
| Subscriptions (piano abbonamento) | campi `User.subscription_status` + `subscription_end_date` | accounts | accounts/models.py | 🟡 | Nessun modello `Subscription` separato; il piano è codificato in due CharField sull'utente (INACTIVE/ACTIVE). Three-tier Freemium/Premium/Club Pro del blueprint non è implementato come enum |
| Claim_Requests (rivendica profilo) | `AccountProfileLink` | accounts | accounts/models.py | ✅ | status: PENDING → APPROVED/REJECTED; vedi STATE_MACHINES.md §4 |
| Activation_Codes (codici invito) | `ActivationCode` | management | management/models.py | ✅ | Generati dal Club Admin; max_uses, expires_at, role-specific |
| Shop_Orders | — | — | — | ❌ | Blueprint §10, §13; webhook outbound HMAC verso shop società; nessun modello nel codice |
| Sponsor_Assets | `Society.sponsors` (JSONField) | core | core/models.py | 🟡 | Lista JSON `[{"name": "...", "logo_url": "..."}]` sul modello Society; blueprint prevede un modello `Sponsor_Assets` separato con placement |
| User_Preferences (layout widget) | — | — | — | ❌ | Blueprint §10, §12; personalizzazioni widget e tema non implementate |
| Jury_Tokens | — | — | — | ❌ | Blueprint §7.4, §10, §14; token match-specific per giuria con finestra 30 min; confermato non implementato in STATE_MACHINES.md §"Funzionalità non implementate" |

---

## Altre entità e concetti del blueprint

| Termine blueprint | Modello / Campo Django | App | Status | Note |
|---|---|---|---|---|
| Referto (cartaceo + OCR) | `MatchReport` con `source_channel='FILE'` | matches | ✅ | Vedi STATE_MACHINES.md §1 per stati e transizioni complete |
| Referto Digitale In-App | `MatchReport` con `source_channel='DIGITAL'` | matches | ✅ | Stesso modello `MatchReport`, non una classe separata; source_channel discrimina |
| Pipeline OCR / Workflow referto | `MatchReport.status` TextChoices | matches | ✅ | Stati: DRAFT, UPLOADED, PROCESSING, EXTRACTED, VALIDATED, PUBLISHED, NEEDS_REVIEW, REJECTED |
| Onboarding utente | `User.onboarding_state` (property calcolata) | accounts | ✅ | **Non è un campo DB** — è una property che aggrega identity_status + subscription_status + setup_completed; vedi STATE_MACHINES.md §2 |
| Verifica identità (SPID/CIE) | `User.identity_status` + `User.identity_verified_at` | accounts | 🟡 | Campo presente; il flusso SPID/CIE reale non è implementato — la verifica è oggi manuale via vista `verify_identity()` |
| Ruolo utente | `User.role` (CharField) | accounts | ✅ | Valori: athlete, coach, referee, fan, president |
| Ruolo staff RBAC | `User.staff_role` (CharField) | accounts | ✅ | Valori: NONE, UPLOADER, REVIEWER, PUBLISHER, SUPERADMIN; vedi STATE_MACHINES.md §3 |
| Membership (appartenenza squadra) | `Membership` | management | ✅ | Lega User a Society+Team con role: PRESIDENT, HEAD_COACH, ASSISTANT_COACH, PLAYER |
| Richiesta Membership | `MembershipRequest` | management | ✅ | Percorso manuale quando l'utente non ha codice di attivazione; vedi STATE_MACHINES.md §5 |
| Firma arbitro / PIN referto | — | — | ❌ | Blueprint §7.4.3, §14; referto immutabile post-firma + correzioni solo via admin; non implementato |
| AI Stats Engine / Chatbot AI | `AIQueryLog` (log query) | matches | 🟡 | Log v0 presente; engine di risposta esiste in forma basilare (`AIQueryLog`); chatbot AI interattivo (§7.5) non implementato |
| Media Gallery | — | — | ❌ | Blueprint §7.6; upload foto/video, face detection, tagging atleti; nessun modello |
| Live Alerts push | — | — | ❌ | Blueprint §2, §13; notifiche push per utenti Premium; nessuna infrastruttura |
| Season Recap (PDF stagione) | `SeasonArchive` | seasons | 🟡 | Archivio JSON stats per stagione/atleta/squadra; nessuna generazione PDF |
| Shop vetrina | — | — | ❌ | Blueprint §2, §3, §13; webhook outbound verso shop società; nessun modello |
| Bacheca squadra / Comunicazioni | `Post`, `Comment` | management | ✅ | Post e commenti per bacheca società/squadra |
| Chat di squadra | `ChatMessage` | management | 📋 | Messaggistica istantanea squadra; non menzionata nel blueprint come funzionalità distinta |
| Widget / Dashboard personalizzata | — | — | ❌ | Blueprint §7.1, §12; sistema slot riordinabili per utenti Premium; nessun modello preferenze |
| Giuria (ruolo) | `User.role` (non presente come valore) | accounts | ❌ | Il blueprint distingue "Giuria (Cert)" come ruolo; nel codice i valori di role sono athlete/coach/referee/fan/president — nessun valore "jury" o "giuria" |

---

## Entità solo nel codice (non nel blueprint)

| Modello Django | App | File | Descrizione |
|---|---|---|---|
| `Convocation` | management | management/models.py | Convocazione ufficiale atleti per una partita; status: DRAFT, SENT_PRIVATE, PUBLISHED, LOCKED (calcolato) |
| `ConvocationNominee` | management | management/models.py | Singolo giocatore convocato; FK verso Convocation; flag is_starter |
| `Training` | management | management/models.py | Piano di allenamento singolo o ricorrente; recurrence_rule JSON |
| `TrainingOccurrence` | management | management/models.py | Singola istanza di un allenamento (generata dalla ricorrenza) |
| `TrainingAttendance` | management | management/models.py | Presenza/RSVP con geofencing; status: PENDING, PRESENT, ABSENT, JUSTIFIED |
| `InboundEmail` | matches | matches/models.py | Traccia email ricevute per idempotenza deduplication; RFC822 message_id |
| `OCRRawResponse` | matches | matches/models.py | Risposta originale del provider OCR (es. GPT-4V); per debug e audit; collegato a MatchReport |
| `AuditLog` | management | management/models.py | Log generico di azioni critiche di sistema (es. PUBLISH_REPORT, ONBOARDING_*); cf. `MatchReportAuditLog` dedicato ai referti |
| `SeasonArchive` | seasons | seasons/models.py | Snapshot JSON delle statistiche di atleta/squadra per stagione passata |
| `PilotDailyLog` | management | management/models.py | Log operativo giornaliero fase pilot; status: GREEN/YELLOW/RED; staff-only |
| `PilotBug` | management | management/models.py | Bug tracker interno pilot; severity S1–S4; non è il sistema bug pubblico |
| `PilotFeedback` | management | management/models.py | Feedback UX/operativo raccolto durante il pilot; staff-only |
| `PilotReview` | management | management/models.py | Sintesi go/no-go Day-7 / Day-14 del pilot |
| `AIQueryLog` | matches | matches/models.py | Log delle query all'AI Stats Engine v0; traccia query, risposta, atleta matchato |

---

## Relazioni chiave

Le 8 relazioni più strutturali del dominio:

1. **`User` 1:1 `AthleteProfile` / `CoachProfile` / `RefereeProfile` / `PresidentProfile`** — ogni utente ha al massimo un profilo di ruolo, creato automaticamente via signal `post_save`.

2. **`User` 1:N `AccountProfileLink` N:1 `AthleteProfile`** — un utente può richiedere la rivendica di più profili sportivi preesistenti; ogni profilo sportivo può essere rivendicato da al massimo un utente (APPROVED).

3. **`Society` 1:N `Team`** — una società ha più squadre (una per categoria); `Team` ha FK verso `Society` e verso `League`.

4. **`User` N:M `Membership` N:1 `Society`/`Team`** — un utente può essere membro di più squadre/società in ruoli diversi; ogni membership ha is_active e role.

5. **`League` 1:N `Match` e `League` 1:N `LeagueStanding`** — un campionato ha più partite e una classifica persistita; la classifica va sempre attraverso `standings_service.rebuild_league_standings()`, mai scritta direttamente.

6. **`Match` 1:N `MatchReport`** — una partita può avere più referti (uno pubblicato, altri de-pubblicati automaticamente); il workflow completo è in STATE_MACHINES.md §1.

7. **`MatchReport` 1:N `MatchReportAuditLog`** — ogni transizione di stato sul referto genera un audit log con old_status, new_status, user, reason.

8. **`Match` 1:1 `Convocation` → 1:N `ConvocationNominee`** — ogni partita ha al massimo una convocazione; la convocazione include la lista dei convocati e il calcolo dello status effettivo in base al tempo.

---

## Terminologia blueprint ambigua o divergente dal codice

| Termine nel blueprint | Come funziona nel codice | Azione |
|---|---|---|
| "Referto Digitale" (sembra un oggetto separato) | È `MatchReport` con `source_channel='DIGITAL'` — stesso modello, stesso workflow | Nessuna modifica al codice; nota da tenere presente in ogni discussione di feature |
| "VERIFIED" (stato referto nel blueprint §8) | Nel codice lo stato si chiama `VALIDATED` | Blueprint da correggere — confermato da STATE_MACHINES.md §"Discrepanze" |
| `source` / `origin` (campi menzionati in CLAUDE.md) | Nel codice i campi si chiamano `source_channel` e `source_type` | CLAUDE.md da correggere (vedi STATE_MACHINES.md §"Discrepanze") |
| "Subscriptions" (entità business §10) | Non è un modello separato — il piano è codificato in `User.subscription_status` (INACTIVE/ACTIVE) e `User.subscription_end_date`; il three-tier Freemium/Premium/Club Pro non è ancora modellato | Tenere a mente quando si lavora sulla feature abbonamenti |
| "Giuria (ruolo)" (blueprint §7.1) | Nel codice non esiste un valore 'jury' o 'giuria' per `User.role`; il ruolo più vicino sarebbe 'referee', ma la giuria ha poteri diversi (token, firma) | Da decidere se aggiungere 'jury' come valore di role o gestirlo come sotto-ruolo di referee |
| "Seasons / Stagioni" (entità §10) | Non è un modello autonomo — la stagione è un CharField "2024-2025" su `League`; `SeasonArchive` (seasons app) gestisce solo l'archivio storico delle stats | Distinction importante: stagione corrente = campo su League; storico = SeasonArchive |
| "onboarding_state" (descritto come stato) | È una **property calcolata** su `User`, non un campo DB; aggrega `identity_status` + `subscription_status` + `setup_completed` + relazioni; non assegnabile direttamente | Mai fare `user.onboarding_state = '...'` — non funziona |
| "Venues / Impianti" (entità §10) | Solo `Match.location` come CharField; nessun modello `Venue` autonomo | Tenere presente per la roadmap se si vuole profilazione impianti |
