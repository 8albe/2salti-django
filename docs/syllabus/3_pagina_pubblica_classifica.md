## 3. Pagina pubblica della classifica

Stato: 🔄 In corso (filtro stagione completo e **LIVE su prod 2026-06-19**; unico residuo: modello Venue/Impianto, differito)

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
- [ ] Modello `Venue/Impianto` autonomo (gap blueprint §10 — oggi `Match.location` CharField)
  - Rimandato (deciso): si affronterà quando servirà popolare il sito con dati reali. Unica voce della macro con schema-change/migration.

---

← [Macro precedente](2_pagina_pubblica_partite.md) | → [Macro successiva](4_profilo_atleti.md)
