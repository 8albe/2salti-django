# Domain Glossary — Italian Terminology ↔ Django Code

Questo documento è il ponte tra il linguaggio di prodotto usato nel blueprint (italiano) e i modelli Django del codice (inglese). Fonte di verità per i nomi.

**Ultimo aggiornamento:** 2026-06-11
**Generato leggendo:**
- `docs/STATE_MACHINES.md` (fonte di verità per stati e transizioni)
- `docs/BLUEPRINT.md` (vocabolario di prodotto)
- `accounts/models.py`, `core/models.py`, `matches/models.py`, `management/models.py`, `seasons/models.py`

**Legenda status:**
- ✅ Implementato — modello Django esatto presente
- 🟡 Parzialmente implementato — esiste qualcosa, ma non copre tutto quello che il blueprint descrive
- ❌ Non implementato — il blueprint ne parla, nel codice non c'è nulla
- 📋 Non nel blueprint — esiste nel codice, il blueprint non lo menziona

> **Scope 2026-07 (pallanuoto-only):** le voci Shop (Shop_Orders / Shop vetrina), Media Gallery e Impianto/Venue sono **eliminate dallo scope** — motivo e cosa le riaprirebbe in [FUTURE_IDEAS.md](FUTURE_IDEAS.md) (§1). I loro tombstone qui sotto restano per non rompere i rimandi esistenti; lo schema `Sport` resta multi-sport-capable ma il prodotto è pallanuoto-only ([FUTURE_IDEAS.md](FUTURE_IDEAS.md) §2).

---

## Entità principali (§10 "Entità core")

| Termine blueprint | Modello Django | App | File | Status | Note |
|---|---|---|---|---|---|
| Partita / Match | `Match` | matches | matches/models.py | ✅ | Contiene score, quarter_scores, referees, has_report, is_finished, is_public (vedi note tecniche sotto) |
| Squadra / Team | `Team` | core | core/models.py | ✅ | FK verso Society e League; nome auto-generato da Society + category |
| Società | `Society` | core | core/models.py | ✅ | Creata dal Presidente nel wizard onboarding |
| Sport | `Sport` | core | core/models.py | ✅ | Schema **multi-sport-capable** (point_system, period_label, hex_color), ma **prodotto pallanuoto-only** (decisione 2026-07 → [FUTURE_IDEAS.md](FUTURE_IDEAS.md) §2) |
| Campionato / Competizione | `League` | core | core/models.py | ✅ | Include stagione, girone, livello; blueprint §10 la chiama "Competition" |
| Atleta (profilo sportivo) | `AthleteProfile` | accounts | accounts/models.py | ✅ | OneToOne con User; stats calcolate (total_goals, total_matches, total_expulsions) |
| Allenatore / Coach | `CoachProfile` | accounts | accounts/models.py | ✅ | OneToOne con User; specialization, years_experience |
| Arbitro / Referee | `RefereeProfile` | accounts | accounts/models.py | ✅ | OneToOne con User; license_number, total_matches_officiated |
| Presidente | `PresidentProfile` | accounts | accounts/models.py | ✅ | OneToOne con User; punta a `managed_society`. **RBAC presidente derivato da `managed_society`, non da una `Membership` ruolo PRESIDENT** (de-vincolato da stagione, `08f8830`, 2026-06-20). |
| Evento partita | `MatchEvent` | matches | matches/models.py | ✅ | event_type codificato; blueprint §10 chiama la tabella "Match_Events" |
| Configurazione evento per sport | `SportEventConfig` | matches | matches/models.py | 📋 | Mappa event_code → label per sport; non menzionato nel blueprint |
| Classifica | `LeagueStanding` | core | core/models.py | ✅ | Tabella denormalizzata persistita; mai scrivere direttamente — usare `standings_service` |
| Stagione | `League.season` (CharField) → `Season` (entità, deciso) | core | core/models.py | 🟡 | Oggi è un CharField su `League`, formato canonico `2025/2026` (slash). **Redesign Sprint D — Fase 1 implementata su dev (2026-06-09, syllabus Macro 16):** `Season` entità di prima classe (migration 0011, `is_current` per sport, al massimo una corrente per sport); FK transitoria `League.season_fk` (nullable, PROTECT) affiancata alla stringa `League.season`, che resta fino alla Fase 2 (rename lì — **verificato 2026-06-11: `League.season` è ancora il CharField, `season_fk` ancora transitorio**). `Membership.season`, tipo lega e prestito implementati su dev (Fasi 2-4, Macro 16, 2026-06-11; prod allineata 2026-06-12). Distinta da `SeasonArchive` (archivio storico stats): da linkare, non fondere. |
| Impianto / Venue | `Match.location` (CharField) | matches | matches/models.py | 🟡 | Solo stringa sul match; entità `Venue` autonoma **eliminata dallo scope 2026-07** → [FUTURE_IDEAS.md](FUTURE_IDEAS.md) §1 (storico: gap blueprint §10) |
| Validation_Logs | `MatchReportAuditLog` | matches | matches/models.py | ✅ | Blueprint §10 li chiama "Validation_Logs"; il codice usa `MatchReportAuditLog` |

### Note tecniche su `Match`

- **`Match.is_public` è una `@property` calcolata, non un campo DB.** Si appoggia su `reports.filter(status='PUBLISHED').exists()` — è True solo se il match ha almeno un `MatchReport` in stato `PUBLISHED`. Conseguenza pratica: **non è filtrabile via ORM QuerySet**. Una chiamata tipo `Match.objects.filter(is_public=True)` solleva `FieldError`. Per ottenere lo stesso risultato lato DB usare `Match.objects.filter(reports__status='PUBLISHED').distinct()`.
- **`Match.has_report` è un flag one-way.** Viene settato a `True` quando un `MatchReport` viene associato al match (quattro punti di scrittura noti: `matches/views.py:132`, `:505`, `:561`, `admin.py:221`), ma **non viene mai riabbassato a `False`** se il report viene successivamente eliminato o de-pubblicato. Significa che `has_report=True` indica "in passato è stato associato un report", non "esiste un report attivo adesso". Per il check "ha un report attivo" usare le relazioni dirette su `reports`.

---

## Entità business (§10 "Entità business")

| Termine blueprint | Modello Django | App | File | Status | Note |
|---|---|---|---|---|---|
| Account utente / User_Accounts | `User` | accounts | accounts/models.py | ✅ | AbstractUser con role, staff_role, identity_status, subscription_status, setup_completed |
| Subscriptions (piano abbonamento) | `User.plan` + `Society.tier`/`is_comped` | accounts, core | accounts/models.py, core/models.py | ✅ (dev) | Nessun modello `Subscription` separato; enum `FREEMIUM`/`PREMIUM` su User e `FREE`/`CLUB_PRO` su Society (dev 2026-07-02), mutabili solo via seam `entitlement_service` — vedi §"Piano / Tier / Entitlement" sotto. Legacy: `subscription_status`/`subscription_end_date` deprecati, non più letti dal runtime |
| Claim_Requests (rivendica profilo) | `AccountProfileLink` | accounts | accounts/models.py | ✅ | status: PENDING → APPROVED/REJECTED; vedi STATE_MACHINES.md §4 |
| Activation_Codes (codici invito) | `ActivationCode` | management | management/models.py | ✅ | Generati dal Club Admin; max_uses, expires_at, role-specific |
| Shop_Orders | — | — | — | ❌ | **Eliminato dallo scope 2026-07** → [FUTURE_IDEAS.md](FUTURE_IDEAS.md) §1. Storico: blueprint §10, §13; webhook outbound HMAC verso shop società; nessun modello nel codice |
| Sponsor (modello relazionale) | `core.Sponsor` | core | core/models.py | ✅ (dev) | **Macro 9 as-built (2026-06-30):** modello relazionale dedicato, FK `Society` + FK `Season`; targeting **società-wide sulla stagione corrente** via `core.services.sponsor_service`. Render in **forma piena** (scheda società) e **forma ridotta** (profilo atleta del club). Scope pilota **solo-Zero9** (le altre società degradano a zero). Gestione **seed/admin-only** (`op_admin_site`), UI CRUD differita. Migration `0022_sponsor`. Pending: `migrate` su prod + dati reali Zero9 (lato Alberto) |
| Sponsor_Assets (legacy) | `Society.sponsors` (JSONField) | core | core/models.py | 🟡 | Lista JSON `[{"name": "...", "logo_url": "..."}]` sul modello Society; **deprecato e lasciato intatto** (non rimosso; stato prod non verificato) — superato dal modello relazionale `core.Sponsor` (riga sopra) |
| User_Preferences (layout widget) | — | — | — | ❌ | Blueprint §10, §12; personalizzazioni widget e tema non implementate |
| Match_Jury_Links | — | — | — | ❌ | Blueprint §7.4.1 (riscritto 2026-07-19); link monouso per-partita, valido fino a chiusura referto + backstop 7 giorni; sostituisce il token match-specific 30-min (decaduto per vincolo federale GUG/portale, archiviato in FUTURE_IDEAS.md §1); non implementato nel codice — v. syllabus/14 §14.2, STATE_MACHINES.md §"Funzionalità non implementate" |

### Piano / Tier / Entitlement (gating premium — dev 2026-07-02)

Due assi di entitlement, **ortogonali all'RBAC** (`management/permissions.py` non c'entra: qui si gatta su feature premium, non su ruoli/membership). Entrambi cambiano **solo** via il seam `core/services/entitlement_service.py`, che garantisce l'audit `ENTITLEMENT_*` — mai scrivere questi campi direttamente.

| Termine | Campo / Property | Modello | Note |
|---|---|---|---|
| Piano utente | `User.plan` | accounts | TextChoices `FREEMIUM`/`PREMIUM`, default `FREEMIUM`. Solo via seam |
| Step pagamento onboarding | `User.onboarding_payment_done` | accounts | Boolean; solo funnel onboarding (mock 0,50€). **Non** concede premium; eredita il solo ruolo funnel che aveva `subscription_status` |
| Premium utente | `User.is_premium` | accounts | Property, fonte-di-verità unica: `plan == PREMIUM` |
| Tier società | `Society.tier` | core | TextChoices `FREE`/`CLUB_PRO`, default `FREE`. Solo via seam |
| Comped | `Society.is_comped` | core | Boolean; Club Pro concesso gratis (es. società pilota Zero9), override su `tier` |
| Club Pro società | `Society.is_club_pro` | core | Property, fonte-di-verità unica: `is_comped OR tier == CLUB_PRO` (comped ha precedenza) |

`User.subscription_status` e `subscription_end_date` sono **legacy deprecati**: non più letti/scritti dal runtime e **non mappano più il piano** (rimozione fisica differita a un deploy successivo). Decorator di gating in `accounts/decorators.py`: `premium_required` (applicato su `api_ai_query`, sotto `login_required`), `club_pro_required` (creato, **non applicato** in pilota: Zero9 sarà comped → gate inerte).

---

## Altre entità e concetti del blueprint

| Termine blueprint | Modello / Campo Django | App | Status | Note |
|---|---|---|---|---|
| Referto (cartaceo + OCR) | `MatchReport` con `source_channel='FILE'` | matches | ✅ | Vedi STATE_MACHINES.md §1 per stati e transizioni complete |
| Referto Digitale In-App | `MatchReport` con `source_channel='DIGITAL'` | matches | ✅ | Stesso modello `MatchReport`, non una classe separata; source_channel discrimina |
| Pipeline OCR / Workflow referto | `MatchReport.status` TextChoices | matches | ✅ | Stati: DRAFT, UPLOADED, PROCESSING, EXTRACTED, VALIDATED, PUBLISHED, NEEDS_REVIEW, REJECTED |
| Onboarding utente | `User.onboarding_state` (property calcolata) | accounts | ✅ | **Non è un campo DB** — è una property che aggrega identity_status + setup_completed (onboarding_payment_done resta sul modello per audit ma non gating: step pagamento rimosso dal funnel, differito a Macro 10); vedi STATE_MACHINES.md §2 |
| Verifica identità (email a click) | `User.identity_status` + `User.identity_verified_at` | accounts | ✅ | SPID/CIE **accantonato** (pivot 2026-06-19). Implementato: conferma a click su link email, token stateless firmato (`accounts/services/email_verification.py`), validità 7 giorni. |
| Ruolo utente | `User.role` (CharField) | accounts | ✅ | Valori: athlete, coach, referee, fan, president |
| Ruolo staff RBAC | `User.staff_role` (CharField) | accounts | ✅ | Valori: NONE, UPLOADER, REVIEWER, PUBLISHER, SUPERADMIN; vedi STATE_MACHINES.md §3 |
| Membership (appartenenza squadra) | `Membership` | management | ✅ | Lega User a Society+Team con role: PRESIDENT, HEAD_COACH, ASSISTANT_COACH, PLAYER. **Redesign Macro 16 — implementato su dev (2026-06-11; prod allineata 2026-06-12):** campo `Membership.season` (FK a `Season`, NOT NULL da migration `0015`), nuova unique key 5-field `(user, society, team, role, season)`, rimozione di `start_date`/`end_date` (migration `0014`). |
| Prestito (loan) | `Membership.is_loan` + `Membership.tesseramento_society` | management | ✅ (dev) | **Implementato su dev (Macro 16 Fase 4, 2026-06-11; prod allineata 2026-06-12).** Migration `management/0016`: marcatore `is_loan`, FK `tesseramento_society` (PROTECT, related_name `loaned_out_memberships`) alla società d'origine, stato `Membership.LoanStatus` (ACTIVE/ENDED) come **etichetta** (non macchina a stati → STATE_MACHINES.md invariato). Coerenza campi via `CheckConstraint membership_loan_fields_coherent`; vincolo cross-row "una sola società attiva per (user, season) salvo prestito" in `Membership.clean()`. Unica eccezione a "una società per stagione", solo squadre dei grandi (A1–D). Vedi syllabus Macro 16 §16.5. |
| Tipo lega (grandi / giovanili) | `League.league_type` | core | ✅ (dev) | **Implementato su dev (Macro 16 Fase 3, 2026-06-11; prod allineata 2026-06-12).** `League.league_type` (TextChoices A1–D / U10–U20, nullable = non classificata), display via `League.LEAGUE_TYPE_DISPLAY` + property `league_type_label`; helper `League.is_senior_league` (True per A1–D). `Team.category` **rimosso** (migration `core/0018`); display via `Team.category_label` derivato dalla lega. La lega è la fonte di verità. Lista chiusa: A1, A2, B, C, D = "dei grandi"; U10–U20 = giovanili. Etichette tradizionali display 1:1 sull'Under canonico (U12=Esordienti, U14=Ragazzi, U16=Allievi, U18=Juniores; U10=Pulcini, U20=Under 20). Vedi syllabus Macro 16 §16.4. |
| Richiesta Membership | `MembershipRequest` | management | ✅ | Percorso manuale quando l'utente non ha codice di attivazione; vedi STATE_MACHINES.md §5 |
| Firma arbitro / PIN referto | — | — | ❌ | Blueprint §7.4.3, §14; referto immutabile post-firma + correzioni solo via admin; non implementato |
| AI Stats Engine / Chatbot AI | `AIQueryLog` (log query) | matches | 🟡 | Log v0 presente; engine di risposta esiste in forma basilare (`AIQueryLog`); chatbot AI interattivo (§7.5) non implementato |
| Media Gallery | — | — | ❌ | **Eliminata dallo scope 2026-07** → [FUTURE_IDEAS.md](FUTURE_IDEAS.md) §1. Storico: blueprint §7.6; upload foto/video, face detection, tagging atleti; nessun modello |
| Live Alerts push | — | — | ❌ | Blueprint §2, §13; notifiche push per utenti Premium; nessuna infrastruttura |
| Season Recap (PDF stagione) | `SeasonArchive` | seasons | 🟡 | Archivio JSON stats per stagione/atleta/squadra; nessuna generazione PDF |
| Shop vetrina | — | — | ❌ | **Eliminata dallo scope 2026-07** → [FUTURE_IDEAS.md](FUTURE_IDEAS.md) §1. Storico: blueprint §2, §3, §13; webhook outbound verso shop società; nessun modello |
| Bacheca squadra / Comunicazioni | `Post`, `Comment` | management | ✅ | Post e commenti per bacheca società/squadra |
| Chat di squadra | `ChatMessage` | management | 📋 | Messaggistica istantanea squadra; non menzionata nel blueprint come funzionalità distinta |
| Widget / Dashboard personalizzata | — | — | ❌ | Blueprint §7.1, §12; sistema slot riordinabili per utenti Premium; nessun modello preferenze |
| Profilo fan / genitore | `FanProfile` | accounts | ✅ | Implementato (Macro 7a); 1:1 con `User`. "Follow atleti" = riuso di `favorite_players` (M2M self su `User`), multi-follow. |
| Certificazione genitore | `ParentCertification` | management | ✅ | Implementato (Macro 7b). Society-vouching via email; macchina a stati in BLUEPRINT §7.7. |
| Giuria (ruolo) | `User.role` (non presente come valore) | accounts | ❌ | **Deciso (2026-07-19):** non serve — nel modello a link monouso per-partita (§7.4.1) la giuria non ha account; i valori di `User.role` restano athlete/coach/referee/fan/president per design, non per gap. V. syllabus/14 §14.2 |

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
| "VERIFIED" (stato referto nel blueprint §8) | Nel codice lo stato si chiama `VALIDATED` | CHIUSO il 09-mag-2026 — fix applicato in BLUEPRINT.md v3.3, rinomina VERIFIED → VALIDATED in §8 |
| `source` / `origin` (campi menzionati in CLAUDE.md) | Nel codice i campi si chiamano `source_channel` e `source_type` | CHIUSO il 24-apr-2026 — sezione obsoleta rimossa da CLAUDE.md, ora delega a STATE_MACHINES.md |
| "Subscriptions" (entità business §10) | Non è un modello separato — il piano è `User.plan` (FREEMIUM/PREMIUM) + `Society.tier`/`is_comped` (Club Pro), mutabili solo via seam `entitlement_service`; `subscription_status`/`subscription_end_date` sono legacy deprecati e non mappano più il piano | Three-tier del blueprint ora modellato come due assi (utente + società); vedi §"Piano / Tier / Entitlement" |
| "Giuria (ruolo)" (blueprint §7.1) | Nel codice non esiste un valore 'jury' o 'giuria' per `User.role` — e nel modello attuale (link monouso per-partita, §7.4.1) non deve esistere: la giuria non ha account | **Deciso (2026-07-19):** nessun valore 'jury' da aggiungere — l'accesso passa da `Match_Jury_Links`, non da un ruolo utente. V. syllabus/14 §14.2 |
| "Seasons / Stagioni" (entità §10) | Oggi la stagione è un CharField formato `2025/2026` (slash) su `League`; il redesign Macro 16 (implementato su dev 2026-06-11, prod allineata 2026-06-12) la promuove a entità `Season` — già presente su dev; `League.season` resta CharField transitorio affiancato da `season_fk`. `SeasonArchive` (seasons app) è cosa diversa: solo archivio storico delle stats | Stagione corrente = `Season.is_current` per sport (post-redesign); storico = `SeasonArchive`. I due concetti restano **distinti**: da linkare, non fondere |
| "onboarding_state" (descritto come stato) | È una **property calcolata** su `User`, non un campo DB; aggrega `identity_status` + `onboarding_payment_done` + `setup_completed` + relazioni; non assegnabile direttamente | Mai fare `user.onboarding_state = '...'` — non funziona |
| "Venues / Impianti" | Solo `Match.location` come CharField; nessun modello `Venue` autonomo | Entità `Venue` **eliminata dallo scope 2026-07** → [FUTURE_IDEAS.md](FUTURE_IDEAS.md) §1; resta solo `Match.location` |
