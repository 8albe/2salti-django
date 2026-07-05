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

Raccolti qui perché emersi lungo il bring-up Zero9; nessuno è bloccato da Zero9, si batchano in un deploy unico:

- [x] **Fix admin `accounts.User`** — fatto su dev (`4eaf433`, 2026-07-05): `UserOpAdmin` registrato su `op_admin_site` in `accounts/admin.py`, pattern `management/admin.py:158-213`. `PresidentProfile` resta solo sul default site (fuori scope, non serviva per il 404 su `User`).
- [ ] **Rate-limit/pulizia account bot sul signup prod** (id ~61-87, username casuali, email spam). **Correzione 2026-07-06**: il criterio "UNVERIFIED + email vuota" è BANDITO come selettore di pulizia — su dev seleziona i pk 3-60 (58 utenti), che sono il **roster seed delle 4 società pilota** (membership PLAYER attive + `AthleteProfile`, non bot). I bot prod id ~61-87 vanno caratterizzati da zero, read-only, con un criterio più stringente (nessuna membership/profile_link/AthleteProfile). Honeypot anti-bot aggiunto sul signup (`4aa48e7`, 2026-07-06) per prevenire nuovi bot self-service; rate-limit IP e pulizia dei bot prod esistenti restano aperti.
- [x] **Rimozione link legacy `create_society`** dalla dashboard — fatto su dev (`24cf0d6`, 2026-07-05). Il ramo CREATE della view resta raggiungibile via URL diretto (nessun gate lato view): item separato, vedi B4 sotto.
- [x] **Fix copy SPID stantìo**: il funnel onboarding era già pulito (verificato 2026-07-05); residuo trovato fuori funnel in `core/integrations.py` (voce `IDENTITY_VERIFICATION` della staff dashboard, ancora "Mock SPID/CIE") — corretto su dev (`152df97`, 2026-07-05). Copy `PAYMENTS` stantia ("Mock Stripe/PayPal") corretta a sua volta (`d5fa145`, 2026-07-06).
- [x] **Throttle reinvio email di verifica** (cooldown 60s, session-based, condiviso tra worker via sessioni DB-backed) — fatto su dev (`3a75a0c`, 2026-07-06).
- [x] **Honeypot anti-bot su `SignUpForm`** — fatto su dev (`4aa48e7`, 2026-07-06). Chiude il vettore self-service dei bot "dumb"; non sostituisce un rate-limit IP né la pulizia dei bot prod già esistenti (voce sopra).
- [ ] **Email `unique` su `User` — BLOCCATO (2026-07-06)**: bonifica del duplicato pk 83/92 su dev NON eseguita. `pk=92` (`president_test`) gestisce Zero9 su dev (`president_profile.managed_society_id=17`, richiesta PRESIDENT APPROVED) — non è un account di test scartabile. Nessuna migration scritta. Riaprire solo dopo decisione esplicita su quale dei due account tiene l'email (il token di verifica lega uid+email: nessuna confusione d'identità nel frattempo, resta solo il buco di integrità dati).
- [ ] **Gate ramo CREATE di `create_society`** (recon fatto 2026-07-06, NON costruito): guard proposto a inizio view — se `existing is None` (nessuna `managed_society`) redirect a `choose_society` invece di renderizzare il form CREATE. Interamente fuori dai file protetti (`core/views.py` non lo è; `accounts/middleware.py` non richiede modifiche, l'allowlist resta valida). Rischio aperto: `choose_society`/personificazione oggi offre **solo società già esistenti** (`societies_for_personification()` filtra `teams__isnull=False`) — non esiste un percorso self-service per una società genuinamente nuova (mai vista a DB). Chiudere CREATE del tutto elimina quel percorso: decisione di prodotto, non tecnica.
