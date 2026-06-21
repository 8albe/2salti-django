## 4. Pagina profilo pubblica degli atleti

Stato: 🧊 Differito (unico residuo «minuti giocati» bloccato a monte: richiede eventi SUB_IN/SUB_OUT oggi inesistenti)

Anagrafica, squadra attuale, storico squadre, statistiche (gol, presenze, minuti), ruolo.

### 4.1 Modello e statistiche

- [x] `AthleteProfile` 1:1 con `User`, creato via signal `post_save`
- [x] Statistiche calcolate: `total_goals`, `total_matches`, `total_expulsions`
- [x] `AccountProfileLink` per claim profilo preesistente

### 4.2 Vista pubblica

- [x] Pagina pubblica profilo atleta dedicata
- [x] Sezione squadra attuale + storico squadre (da `Membership`)
- [x] Sezione statistiche stagione corrente
  - Cutoff stagione calcistica: 1 settembre → 31 agosto, ancorato a `Europe/Rome` via `timezone.make_aware`. Aggregazione da `MatchEvent` con `match__reports__status=PUBLISHED`.
- [ ] Statistica "minuti giocati" (non presente fra le metriche correnti)
  - ⏸ Deferito — richiede SUB_IN/SUB_OUT events, fuori scope Sprint A. Gap aperto in §10.

---

← [Macro precedente](3_pagina_pubblica_classifica.md) | → [Macro successiva](5_profilo_allenatori.md)
