## 2. Pagina pubblica delle partite

Stato: ✅ Completato

Tabellino partita completo: marcatori, eventi (espulsioni, cartellini, timeout), score per periodo, arbitri, venue, data.

### 2.1 Modello dati

- [x] `Match` con `score`, `quarter_scores`, `referees`
- [x] `MatchEvent` con enum canonico (GOAL, EXCLUSION_20, YELLOW_CARD, RED_CARD, TIMEOUT, OTHER)
- [x] `SportEventConfig` per mapping eventi per sport

### 2.2 Vista pubblica

- [x] Vista dettaglio partita base in `matches/views.py`
- [x] Tabellino marcatori completo (raggruppamento per squadra)
- [x] Cronologia eventi con timestamp e periodo
- [x] Score per periodo visualizzato esplicitamente
- [x] Sezione arbitri + venue + data
- [x] Link a profili atleti/arbitri dalla pagina partita

---

← [Macro precedente](1_pagina_home_pubblica.md) | → [Macro successiva](3_pagina_pubblica_classifica.md)
