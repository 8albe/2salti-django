# ZERO9_DEFERRED — Item differiti a valle della collaborazione reale con Zero9

Creato il 2026-07-04, alla chiusura del bring-up Zero9 su prod. Questo file è la coda operativa degli item che si sbloccano solo con la collaborazione reale di Zero9 (presidente in carne e ossa, dati veri) — non è un parcheggio di idee (per quello c'è [FUTURE_IDEAS.md](FUTURE_IDEAS.md)): ogni voce qui è un task concreto con un gate esplicito e vincoli tecnici già verificati sul codice. Quando un item si chiude, va spuntato qui e la voce diventa storica.

**Stato di partenza (prod, 2026-07-04):** Zero9 esiste (Society pk=13, slug `zero9` + Team pk=13, slug `zero9-c`, su League pk=7 «serie C Maschile 2026/2027», Season pk=2 non corrente) ed è **comped** (`is_comped=True` via `comp_society`, audit `ENTITLEMENT_SOCIETY_COMPED_CHANGED`). **Non** è personificata (opzione B: gated dal presidente reale) e **non** ha sponsor (si inseriscono a personificazione avvenuta). La stagione corrente resta 2025/2026 (pk=1), invariata.

---

## 1. Personificazione Zero9 (Macro 18)

**Gate:** disponibilità del presidente reale di Zero9.

**Flusso:** gamba A = il presidente richiede l'accesso da `/society/choose/` (`choose_society`, [core/views.py:220](../core/views.py)); gamba B = Alberto approva con l'action «Approva personificazione presidente (Macro 18)» su MembershipRequest in op_admin (`MembershipRequestAdmin.approve_president_personification`, [management/admin.py:40-64](../management/admin.py), esposta via `MembershipRequestOpAdmin`). Flusso verificato e2e su dev il 2026-07-04 (nessun no-op silente, atterraggio REFINE precompilato).

**Vincoli critici:**

- **Il presidente DEVE registrarsi da zero via wizard con `role=president`.** Il signal `create_user_profile` ([accounts/models.py:314-315](../accounts/models.py)) crea il `PresidentProfile` **solo alla creazione dell'utente**: un account riciclato col ruolo cambiato a mano non avrebbe il profilo, e `approve_president_request` fallirebbe in **no-op silente** — il `filter().update()` ([management/services/president_personification.py:125](../management/services/president_personification.py)) aggiornerebbe 0 righe, la richiesta risulterebbe APPROVED ma `managed_society` resterebbe vuoto.
- **Durante il flusso usare SOLO `/society/choose/`, MAI il link legacy «Nuova Società»** in dashboard ([templates/accounts/dashboard.html:205](../templates/accounts/dashboard.html), url `create_society`): creerebbe una **Zero9 duplicata** invece di agganciare quella esistente. Il gating/rimozione del link è item del Deploy 3 (§4).

## 2. Sponsor reali Zero9 (Macro 9)

**Gate:** personificazione avvenuta (§1) + dati reali dagli accordi Zero9.

Inserimento via op_admin (`/admin/core/sponsor/`). **Vincolo critico:** gli sponsor vanno ancorati alla **stagione corrente `is_current`** (oggi 2025/2026, pk=1), **non** alla 2026/2027 del team Zero9 — il render (`sponsor_service.get_society_sponsors`) è società-wide sulla stagione corrente: sponsor sulla stagione sbagliata restano invisibili. Il disallineamento team-2026/2027 / sponsor-2025/2026 è by-design (vedi [syllabus/9_sistema_sponsor.md](syllabus/9_sistema_sponsor.md)). Il seed placeholder `seed_zero9_sponsors_DRAFT.py` NON è stato eseguito su prod (deciso 2026-07-04): su prod solo dati reali.

## 3. Atleti reali Zero9

**Gate:** collaborazione reale (tesseramenti veri).

Gli atleti arrivano **dall'onboarding**, non da seed: `seed_zero9_athlete_DRAFT.py` NON è stato eseguito su prod (deciso 2026-07-04) e resta uno strumento solo-dev.

## 4. Deploy 3 — debiti batchati (nessun prerequisito Zero9)

Raccolti qui perché emersi lungo il bring-up Zero9; nessuno è bloccato da Zero9, si batchano in un deploy unico:

- [ ] **Fix admin `accounts.User`**: oggi `/admin/accounts/user/` dà 404 perché `User` e `PresidentProfile` sono registrati solo sul default site non montato; registrare un `UserOpAdmin` su `op_admin_site` col pattern già in uso ([management/admin.py:158-213](../management/admin.py)).
- [ ] **Rate-limit/pulizia account bot sul signup prod** (id ~61-87, username casuali, email spam).
- [ ] **Gating/rimozione link legacy `create_society`** in dashboard ([templates/accounts/dashboard.html:205](../templates/accounts/dashboard.html)) — vedi rischio duplicazione in §1.
- [ ] **Fix copy SPID stantìo nell'onboarding**: la schermata mostra ancora «Identità verificata tramite SPID» mentre la decisione (BLUEPRINT §7.2/§14, pivot 2026-06-19) è verifica a click su email.
