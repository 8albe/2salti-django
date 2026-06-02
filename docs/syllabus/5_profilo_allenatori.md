## 5. Pagina profilo pubblica degli allenatori

Stato: ✅ Completato

Anagrafica, squadra attuale, storico squadre, partite dirette.

### 5.1 Modello

- [x] `CoachProfile` 1:1 con `User`, creato via signal `post_save`

### 5.2 Vista pubblica

- [x] Pagina pubblica profilo coach dedicata
- [x] Sezione squadra attuale + storico (da `Membership` ruolo HEAD_COACH)
  - Implementato con **opzione (a)** in Sprint A, evoluto in Sprint C: `Membership` con `role='HEAD_COACH'` ordinate per `start_date` desc. Debito `start_date`/`end_date` ✅ chiuso (OPS_RUNBOOK §10.4, commit `0f6ca64`/`0eeff1a`/`0db9307`).
- [x] Sezione partite dirette (aggregazione da `Match`)
  - Sprint C: filtro temporale `start_date <= match.match_date <= COALESCE(end_date, today)` applicato a `coached_matches`/`direct_matches`. Debito tenure ✅ chiuso (OPS_RUNBOOK §10.4, commit `0db9307`).

---

← [Macro precedente](4_profilo_atleti.md) | → [Macro successiva](6_profilo_presidenti.md)
