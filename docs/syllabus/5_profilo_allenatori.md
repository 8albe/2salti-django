## 5. Pagina profilo pubblica degli allenatori

Stato: 🔄 In corso

Anagrafica, squadra attuale, storico squadre, partite dirette.

### 5.1 Modello

- [x] `CoachProfile` 1:1 con `User`, creato via signal `post_save`

### 5.2 Vista pubblica

- [ ] Pagina pubblica profilo coach dedicata
- [ ] Sezione squadra attuale + storico (da `Membership` ruolo HEAD_COACH)
- [ ] Sezione partite dirette (aggregazione da `Match`)

---

← [Macro precedente](4_profilo_atleti.md) | → [Macro successiva](6_profilo_presidenti.md)
