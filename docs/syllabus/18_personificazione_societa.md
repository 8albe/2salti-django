## 18. Personificazione società (presidente)

Stato: ⏳ Da fare (design pianificato — **non as-built**)

> **Design pianificato, non ancora implementato a codice.** Il flusso `MembershipRequest` per il presidente **non esiste** a codice. La macchina a stati relativa **non** va in STATE_MACHINES.md (che resta solo as-built) finché non esiste a codice. Dettaglio di prodotto in [BLUEPRINT.md](../BLUEPRINT.md) §7.2.

Il presidente non crea una società da zero né la rivendica liberamente: la **sceglie da una lista**, **richiede l'accesso**, l'admin (Alberto) approva, poi rifinisce un setup pre-esistente.

### 18.1 Flusso

- **Scelta da una lista.** La lista è composta dalle società che hanno almeno una squadra in un campionato. È **indipendente dalla stagione corrente**: il presidente può personificare anche società che giocano in stagioni future non correnti (estrazione su `Society` con team in lega su qualsiasi stagione; legame strutturale `Team.society`).
- **Richiesta + autorizzazione admin.** Costruita riusando `MembershipRequest` (modello + pattern di approvazione atomica con lock già esistente in `management/views.py`). Il presidente invia la richiesta; l'admin approva.
- **Supera `create_society`.** L'attuale `create_society` (che crea `Society` ex-novo) viene superato. Il flusso riallinea il codice al principio BLUEPRINT §14 "gli utenti non creano da zero, rivendicano", oggi disatteso dall'as-built.

### 18.2 Nodi tecnici aperti (da risolvere in implementazione)

- [ ] **Side-effect all'approvazione.** `APPROVED` → `PresidentProfile.managed_society` valorizzato.
- [ ] **Vincolo 1:1 `managed_society`.** Gestito applicativamente: due presidenti sulla stessa società = **errore gestito**, non `IntegrityError` grezzo. Se aggiungere anche un constraint DB (OneToOne a livello schema) è una decisione da prendere in fase di implementazione.
- [ ] **Setup di rifinitura con email società obbligatoria.** Dopo l'approvazione il presidente rifinisce la società pre-esistente e **deve** valorizzare l'email di contatto. Guardrail anti-notifica-muta: garantisce che `_society_recipients` (`management/services/certification_service.py`) non sia mai vuoto per una società personificata, chiudendo by-design il debito [OPS_RUNBOOK.md](../OPS_RUNBOOK.md) §10.11.

### 18.3 Riferimenti incrociati

- **Macro 6** ([6_profilo_presidenti.md](6_profilo_presidenti.md)) — vista pubblica del profilo presidente/dirigente, già ✅; copre la sola pagina pubblica, non la personificazione.
- **BLUEPRINT §7.2** (Onboarding e Claim Profilo) — dettaglio del flusso e riconciliazione con §14.
- **BLUEPRINT §7.7** — guardrail email società lato notifica vouching.
- **OPS_RUNBOOK §10.11** — debito `_society_recipients` chiuso by-design da §18.2.

---

← [Macro precedente](17_frontend_design_system.md)
