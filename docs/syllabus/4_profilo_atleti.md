## 4. Pagina profilo pubblica degli atleti

Stato: 🔄 In corso

Anagrafica, squadra attuale, storico squadre, statistiche (gol, presenze, minuti), ruolo.

### 4.1 Modello e statistiche

- [x] `AthleteProfile` 1:1 con `User`, creato via signal `post_save`
- [x] Statistiche calcolate: `total_goals`, `total_matches`, `total_expulsions`
- [x] `AccountProfileLink` per claim profilo preesistente

### 4.2 Vista pubblica

- [ ] Pagina pubblica profilo atleta dedicata
- [ ] Sezione squadra attuale + storico squadre (da `Membership`)
- [ ] Sezione statistiche stagione corrente
- [ ] Statistica "minuti giocati" (non presente fra le metriche correnti)

---

← [Macro precedente](3_pagina_pubblica_classifica.md) | → [Macro successiva](5_profilo_allenatori.md)
