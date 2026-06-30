## 18. Personificazione società (presidente)

Stato: ✅ CHIUSO (verificato e2e su `dev` il 2026-06-22, **propagato a prod 2026-06-30, deploy `24bfc62`**)

_Verifica 2026-06-22 (`dev`): e2e Antigravity 6 step (happy path pres3→De Akker, guard 1:1 su Zero9 respinto col messaggio applicativo, email società obbligatoria attiva) + suite 414 verde + check DB (`managed_society` valorizzato, 0 Membership PRESIDENT, guard 1:1 ok)._

> **Implementato e verificato e2e su `dev`** (commit `feat(macro18)`; whitelist `choose_society` nel middleware `accounts/middleware.py` applicata in `941706f`), suite verde. Il flusso riusa `MembershipRequest` con `role='PRESIDENT'` come discriminatore. **CHIUSO su `dev`:** e2e Antigravity 6 step verde, suite 414 verde, check DB conforme; **propagato a prod 2026-06-30 (deploy `24bfc62`)**. La macchina a stati è ora verificata e può essere portata in STATE_MACHINES.md. Dettaglio di prodotto in [BLUEPRINT.md](../BLUEPRINT.md) §7.2.

Il presidente non crea una società da zero né la rivendica liberamente: la **sceglie da una lista**, **richiede l'accesso**, l'admin (Alberto) approva, poi rifinisce un setup pre-esistente.

### 18.1 Flusso

- **Scelta da una lista.** La lista è composta dalle società che hanno almeno una squadra in un campionato. È **indipendente dalla stagione corrente**: il presidente può personificare anche società che giocano in stagioni future non correnti (estrazione su `Society` con team in lega su qualsiasi stagione; legame strutturale `Team.society`).
- **Richiesta + autorizzazione admin.** Costruita riusando `MembershipRequest` (modello + pattern di approvazione atomica con lock già esistente in `management/views.py`). Il presidente invia la richiesta; l'admin approva.
- **Supera `create_society`.** L'attuale `create_society` (che crea `Society` ex-novo) viene superato. Il flusso riallinea il codice al principio BLUEPRINT §14 "gli utenti non creano da zero, rivendicano", oggi disatteso dall'as-built.

### 18.2 Nodi tecnici aperti (da risolvere in implementazione)

- [x] **Side-effect all'approvazione.** `APPROVED` → `PresidentProfile.managed_society` valorizzato, dentro `transaction.atomic()`, **nessuna Membership PRESIDENT** (decisione #2). Implementato in `management/services/president_personification.py` (`approve_president_request`), action admin-gated su `op_admin_site`.
- [x] **Vincolo 1:1 `managed_society`.** Gestito applicativamente: la società già con presidente → reject leggibile "Questa società ha già un presidente assegnato.", **non** `IntegrityError` grezzo. Constraint DB (OneToOne) già presente a schema, **invariato**: nessuna migrazione. Test `test_approve_one_to_one_guard_clean_reject`.
- [x] **Setup di rifinitura con email società obbligatoria.** `SocietySetupForm.email` reso obbligatorio (campo modello invariato, no migrazione); `create_society` rifinisce la società pre-esistente quando il presidente è già agganciato. Garantisce che `_society_recipients` (`management/services/certification_service.py`) non sia mai vuoto per una società personificata, chiudendo by-design il debito [OPS_RUNBOOK.md](../OPS_RUNBOOK.md) §10.11.

### 18.3 Riferimenti incrociati

- **Macro 6** ([6_profilo_presidenti.md](6_profilo_presidenti.md)) — vista pubblica del profilo presidente/dirigente, già ✅; copre la sola pagina pubblica, non la personificazione.
- **BLUEPRINT §7.2** (Onboarding e Claim Profilo) — dettaglio del flusso e riconciliazione con §14.
- **BLUEPRINT §7.7** — guardrail email società lato notifica vouching.
- **OPS_RUNBOOK §10.11** — debito `_society_recipients` chiuso by-design da §18.2.

---

← [Macro precedente](17_frontend_design_system.md)
