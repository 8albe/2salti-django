## 1. Pagina home pubblica di ogni sport

Stato: 🔄 In corso

Hub pubblico per sport: classifica del campionato attivo, ultime partite con risultati, prossime partite. Multi-sport by design.

### 1.1 Backend e routing

- [x] Modello `Sport` con `point_system` e `period_label` configurabili
- [x] Viste pubbliche base per sport in `core/views.py` e routing in `core/urls.py`
- [x] Seed sport via `bootstrap_sports` management command

### 1.2 Sezioni pagina home sport

- [ ] Sezione "classifica campionato attivo" alimentata da `LeagueStanding`
- [ ] Sezione "ultime partite con risultati" (filtro `Match` PUBLISHED)
- [ ] Sezione "prossime partite" (filtro `Match` futuri)
- [ ] Sport navigator multi-sport (selettore sport in cima)

---

→ [Macro successiva](2_pagina_pubblica_partite.md)
