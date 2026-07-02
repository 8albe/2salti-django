## 4. Pagina profilo pubblica degli atleti

Stato: ✅ Completa (residuo «minuti giocati» eliminato dallo scope 2026-07 → [FUTURE_IDEAS.md](../FUTURE_IDEAS.md) §1)

Anagrafica, squadra attuale, storico squadre, statistiche (gol, presenze, espulsioni), ruolo.

### 4.1 Modello e statistiche

- [x] `AthleteProfile` 1:1 con `User`, creato via signal `post_save`
- [x] Statistiche calcolate: `total_goals`, `total_matches`, `total_expulsions`
- [x] `AccountProfileLink` per claim profilo preesistente

### 4.2 Vista pubblica

- [x] Pagina pubblica profilo atleta dedicata
- [x] Sezione squadra attuale + storico squadre (da `Membership`)
- [x] Sezione statistiche stagione corrente
  - Cutoff stagione: 1 settembre → 31 agosto, ancorato a `Europe/Rome` via `timezone.make_aware`. Aggregazione da `MatchEvent` con `match__reports__status=PUBLISHED`.

---

← [Macro precedente](3_pagina_pubblica_classifica.md) | → [Macro successiva](5_profilo_allenatori.md)
