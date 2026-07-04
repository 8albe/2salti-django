## 1. Pagina home pubblica pallanuoto

Stato: ✅ Completato

Hub pubblico dello sport: classifica del campionato attivo, ultime partite con risultati, prossime partite.

### 1.1 Backend e routing

- [x] Modello `Sport` con `point_system` e `period_label` configurabili
- [x] Viste pubbliche base per sport in `core/views.py` e routing in `core/urls.py`
- [x] Seed sport via `bootstrap_sports` management command

### 1.2 Sezioni pagina home sport

- [x] Sezione "classifica campionato attivo" alimentata da `LeagueStanding`
- [x] Sezione "ultime partite con risultati" (filtro `Match` PUBLISHED)
- [x] Sezione "prossime partite" (filtro `Match` futuri)
- [x] Sport navigator (selettore sport in cima)
  - Nota tecnica: lo sport navigator resta a codice e si auto-nasconde quando un solo sport ha league; lo schema `Sport` resta intatto per decisione 2026-07 (prodotto pallanuoto-only, schema multi-sport-capable) — vedi [FUTURE_IDEAS.md §2](../FUTURE_IDEAS.md)

---

→ [Macro successiva](2_pagina_pubblica_partite.md)
