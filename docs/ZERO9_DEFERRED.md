# ZERO9_DEFERRED — Item differiti a valle della collaborazione reale con Zero9

Creato il 2026-07-04, alla chiusura del bring-up Zero9 su prod. Questo file è la coda operativa degli item che si sbloccano solo con la collaborazione reale di Zero9 (presidente in carne e ossa, dati veri) — non è un parcheggio di idee (per quello c'è [FUTURE_IDEAS.md](FUTURE_IDEAS.md)): ogni voce qui è un task concreto con un gate esplicito e vincoli tecnici già verificati sul codice. Quando un item si chiude, va spuntato qui e la voce diventa storica.

**Stato di partenza (prod, 2026-07-04):** Zero9 esiste (Society pk=13, slug `zero9` + Team pk=13, slug `zero9-c`, su League pk=7 «serie C Maschile 2026/2027», Season pk=2 non corrente) ed è **comped** (`is_comped=True` via `comp_society`, audit `ENTITLEMENT_SOCIETY_COMPED_CHANGED`). **Non** è personificata (opzione B: gated dal presidente reale) e **non** ha sponsor (si inseriscono a personificazione avvenuta). La stagione corrente resta 2025/2026 (pk=1), invariata.

---

## 1. Personificazione Zero9 (Macro 18)

**Gate:** disponibilità del presidente reale di Zero9.

**Flusso:** gamba A = il presidente richiede l'accesso da `/society/choose/` (`choose_society`, [core/views.py:220](../core/views.py)); gamba B = Alberto approva con l'action «Approva personificazione presidente (Macro 18)» su MembershipRequest in op_admin (`MembershipRequestAdmin.approve_president_personification`, [management/admin.py:40-64](../management/admin.py), esposta via `MembershipRequestOpAdmin`). Flusso verificato e2e su dev il 2026-07-04 (nessun no-op silente, atterraggio REFINE precompilato).

**Vincoli critici:**

- **Il presidente DEVE registrarsi da zero via wizard con `role=president`.** Il signal `create_user_profile` ([accounts/models.py:314-315](../accounts/models.py)) crea il `PresidentProfile` **solo alla creazione dell'utente**: un account riciclato col ruolo cambiato a mano non avrebbe il profilo, e `approve_president_request` fallirebbe in **no-op silente** — il `filter().update()` ([management/services/president_personification.py:125](../management/services/president_personification.py)) aggiornerebbe 0 righe, la richiesta risulterebbe APPROVED ma `managed_society` resterebbe vuoto.
- **Durante il flusso usare SOLO `/society/choose/`, MAI il link legacy «Nuova Società»**, url `create_society`: creerebbe una **Zero9 duplicata** invece di agganciare quella esistente. Il link in dashboard è stato rimosso (`24cf0d6`, 2026-07-05); il ramo CREATE della view resta raggiungibile via URL diretto — gate ancora aperto, vedi §4.

## 2. Sponsor reali Zero9 (Macro 9)

**Gate:** personificazione avvenuta (§1) + dati reali dagli accordi Zero9.

Inserimento via op_admin (`/admin/core/sponsor/`). **Vincolo critico:** gli sponsor vanno ancorati alla **stagione corrente `is_current`** (oggi 2025/2026, pk=1), **non** alla 2026/2027 del team Zero9 — il render (`sponsor_service.get_society_sponsors`) è società-wide sulla stagione corrente: sponsor sulla stagione sbagliata restano invisibili. Il disallineamento team-2026/2027 / sponsor-2025/2026 è by-design (vedi [syllabus/9_sistema_sponsor.md](syllabus/9_sistema_sponsor.md)). Il seed placeholder `seed_zero9_sponsors_DRAFT.py` NON è stato eseguito su prod (deciso 2026-07-04): su prod solo dati reali.

## 3. Atleti reali Zero9

**Gate:** collaborazione reale (tesseramenti veri).

Gli atleti arrivano **dall'onboarding**, non da seed: `seed_zero9_athlete_DRAFT.py` NON è stato eseguito su prod (deciso 2026-07-04) e resta uno strumento solo-dev.

## 4. Deploy 3 — debiti batchati (nessun prerequisito Zero9)

Raccolti qui perché emersi lungo il bring-up Zero9; nessuno è bloccato da Zero9, si batchano in un deploy unico. **Deployato a prod 2026-07-05** (batch onboarding reale + Deploy 3, `master` `37f5e43`, merge no-ff da `dev` `5496cec`) — pulizia bot signup e footgun `ensure_superuser.py`, allora ancora aperti, sono stati chiusi nel batch successivo (Task 1-4, `master` `275ad3e`, 2026-07-05), vedi sotto:

- [x] **Fix admin `accounts.User`** — fatto su dev (`4eaf433`, 2026-07-05): `UserOpAdmin` registrato su `op_admin_site` in `accounts/admin.py`, pattern `management/admin.py:158-213`. `PresidentProfile` resta solo sul default site (fuori scope, non serviva per il 404 su `User`).
- [x] **Pulizia account bot sul signup prod** — **ESEGUITA su prod il 2026-07-05** (Task 4). Criterio "UNVERIFIED + email vuota" confermato BANDITO (seleziona i 58 seed pilota, non bot, vedi sotto); criterio nuovo usato: 0 legami reali (Membership/AthleteProfile/CoachProfile/PresidentProfile) + firma spam. Recon read-only su backup prod, poi delete via management command `core/management/commands/cleanup_bot_users.py` (dry-run default, `--apply`, `--flush-sessions`, guard hard su staff/superuser e legami reali) eseguita da Alberto: **27 id cancellati** (18 certi + 8 husk + 1 test manuale id 89) = 54 record (27 `User` + 27 profili husk), utenti prod **86 → 59**, i 58 seed pilota e `albe_admin` intatti. Procedura in [OPS_RUNBOOK.md](OPS_RUNBOOK.md) §10.5. **Risolto/verificato 2026-07-06** (recon read-only prod): nessun account con id ≥ 90 esiste (max id = 60); l'ipotesi "bot nati dopo il backup 19:12" è falsificata. `--flush-sessions` usa `clearsessions` globale, non per-utente (nota tecnica invariata). Honeypot anti-bot sul signup (`4aa48e7`, 2026-07-06) resta a prevenire nuovi bot self-service; rate-limit IP-based implementato su dev il 2026-07-06 (commit `ae0ecee`, chiusura in [OPS_RUNBOOK.md](OPS_RUNBOOK.md) Appendice A §10.16).
- [x] **Rimozione link legacy `create_society`** dalla dashboard — fatto su dev (`24cf0d6`, 2026-07-05). Il ramo CREATE della view resta raggiungibile via URL diretto (nessun gate lato view): item separato, vedi B4 sotto.
- [x] **Fix copy SPID stantìo**: il funnel onboarding era già pulito (verificato 2026-07-05); residuo trovato fuori funnel in `core/integrations.py` (voce `IDENTITY_VERIFICATION` della staff dashboard, ancora "Mock SPID/CIE") — corretto su dev (`152df97`, 2026-07-05). Copy `PAYMENTS` stantia ("Mock Stripe/PayPal") corretta a sua volta (`d5fa145`, 2026-07-06).
- [x] **Throttle reinvio email di verifica** (cooldown 60s, session-based, condiviso tra worker via sessioni DB-backed) — fatto su dev (`3a75a0c`, 2026-07-06).
- [x] **Honeypot anti-bot su `SignUpForm`** — fatto su dev (`4aa48e7`, 2026-07-06). Chiude il vettore self-service dei bot "dumb"; non sostituisce un rate-limit IP né la pulizia dei bot prod già esistenti (voce sopra).
- [x] **Email `unique` su `User`** — fatto su dev (`1f802d8`, 2026-07-06). Bonifica preliminare sul DB dev vivo: email duplicata `president@test.com` tenuta su `pk=92` (`president_test`, gestisce Zero9), svuotata su `pk=83` (`president1`, genuinamente libero — nessuna `managed_society`, nessuna `MembershipRequest`). Constraint `UniqueConstraint(Lower('email'), condition=~Q(email=''))` su `User.Meta` + `clean_email` in `SignUpForm`. Prerequisito prima del deploy su prod: verificare che prod non abbia duplicati email non vuoti (case-insensitive) — la migration fallirebbe altrimenti in produzione come sarebbe fallita su dev senza la bonifica.
- [x] **Gate ramo CREATE di `create_society`** — fatto su dev (`bebf271`, 2026-07-05). Guard staff-only: se `existing is None` (nessuna `managed_society`) e l'utente non è staff, redirect a `choose_society`; lo staff mantiene CREATE come strumento operativo. Nessun redirect-loop (verificato: `choose_society` renderizza per un presidente senza società, non rimbalza). **Consolidato (opzione A, 2026-07-05)**: CREATE crea la società senza agganciarla all'operatore staff (riusabile, side-effect-free; la società resta rivendicabile dal presidente reale via personificazione); requisito account operatore documentato in [OPS_RUNBOOK.md](OPS_RUNBOOK.md). Il consolidamento definitivo arriverà con l'import calendario FIN come fonte canonica delle società.
- [x] **Footgun `ensure_superuser.py`** — fatto su dev (2026-07-05): credenziali parametrizzate via `DJANGO_SUPERUSER_USERNAME`/`DJANGO_SUPERUSER_EMAIL`/`DJANGO_SUPERUSER_PASSWORD` (convenzione Django `createsuperuser --noinput`), fail-fast (`CommandError`) se una manca — nessun fallback debole. Idempotente: se un superuser esiste già, non fa nulla.
