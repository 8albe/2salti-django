## 3. Pagina pubblica della classifica

Stato: 🔄 In corso

Classifica per campionato/stagione: punti, gol fatti/subiti, partite giocate/vinte/perse/pareggiate. Filtrabile per stagione.

### 3.1 Backend classifiche

- [x] Modello `LeagueStanding` denormalizzato
- [x] `standings_service.rebuild_league_standings()` come unico punto di scrittura
- [x] `integrity_service` per check MISSING_RECORD / EXTRA_RECORD / DATA_MISMATCH
- [x] Command `rebuild_standings` e `monitor_integrity`

### 3.2 Vista pubblica

- [ ] Tabella classifica con colonne PG/V/N/P/GF/GS/PT
- [ ] Filtro per stagione (oggi `League.season` è CharField)
- [ ] Modello `Season` autonomo (gap blueprint §10)
- [ ] Modello `Venue/Impianto` autonomo (gap blueprint §10 — oggi `Match.location` CharField)

---

← [Macro precedente](2_pagina_pubblica_partite.md) | → [Macro successiva](4_profilo_atleti.md)
