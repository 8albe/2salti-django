## 3. Pagina pubblica della classifica

Stato: ✅ Completa (tutto il pubblicabile è **LIVE su prod 2026-06-19**; residuo Venue/Impianto → vedi [Macro 20](20_venue_impianto.md), 🧊 differita dal 2026-07-06; storico del parcheggio in [FUTURE_IDEAS.md](../FUTURE_IDEAS.md) §1)

Classifica per campionato/stagione: punti, gol fatti/subiti, partite giocate/vinte/perse/pareggiate. Filtrabile per stagione.

### 3.1 Backend classifiche

- [x] Modello `LeagueStanding` denormalizzato
- [x] `standings_service.rebuild_league_standings()` come unico punto di scrittura
- [x] `integrity_service` per check MISSING_RECORD / EXTRA_RECORD / DATA_MISMATCH
- [x] Command `rebuild_standings` e `monitor_integrity`

### 3.2 Vista pubblica

- [x] Tabella classifica con colonne PG/V/N/P/GF/GS/PT
- [x] Filtro per stagione (classifica pubblica `sport_detail`, commit f2fbe83; pagina Partite `sport_matches` + date_picker, commit 62c582c) — **LIVE su prod 2026-06-19** (merge e0c928f)
- [x] Slug leghe "serie B Maschile" normalizzati (bonifica dati `core/0019`, Girone C/D → `…-girone-c` / `…-girone-d`) — **LIVE su prod 2026-06-19**; abilitano i path per-slug `/league/<slug>/stats/`
- [x] Modello `Season` autonomo — soddisfatto dalla Macro 16 (Season implementato, live su prod 2026-06-12, §10.8); blocco precedente rimosso

---

← [Macro precedente](2_pagina_pubblica_partite.md) | → [Macro successiva](4_profilo_atleti.md)
