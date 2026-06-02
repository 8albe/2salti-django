## 1. Pagina home pubblica di ogni sport

Stato: ✅ Completato

Hub pubblico per sport: classifica del campionato attivo, ultime partite con risultati, prossime partite. Multi-sport by design.

### 1.1 Backend e routing

- [x] Modello `Sport` con `point_system` e `period_label` configurabili
- [x] Viste pubbliche base per sport in `core/views.py` e routing in `core/urls.py`
- [x] Seed sport via `bootstrap_sports` management command

### 1.2 Sezioni pagina home sport

- [x] Sezione "classifica campionato attivo" alimentata da `LeagueStanding`
- [x] Sezione "ultime partite con risultati" (filtro `Match` PUBLISHED)
- [x] Sezione "prossime partite" (filtro `Match` futuri)
- [x] Sport navigator multi-sport (selettore sport in cima)
  - Nota: Nascosto automaticamente se un solo sport ha league — comportamento corretto by design

---

→ [Macro successiva](2_pagina_pubblica_partite.md)
