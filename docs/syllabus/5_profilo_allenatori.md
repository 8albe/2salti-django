## 5. Pagina profilo pubblica degli allenatori

Stato: 🔄 In corso

Anagrafica, squadra attuale, storico squadre, partite dirette.

### 5.1 Modello

- [x] `CoachProfile` 1:1 con `User`, creato via signal `post_save`

### 5.2 Vista pubblica

- [x] Pagina pubblica profilo coach dedicata
- [x] Sezione squadra attuale + storico (da `Membership` ruolo HEAD_COACH)
  - Implementato con **opzione (a)**: tutte le `Membership` con `role='HEAD_COACH'`, ordinate per `created_at` desc, qualsiasi `is_active`. Debito: [OPS_RUNBOOK §10.4](../OPS_RUNBOOK.md#104-membership-manca-start_dateend_date--aperto) — manca `start_date`/`end_date` su `Membership`.
- [x] Sezione partite dirette (aggregazione da `Match`)
  - Implementato con **opzione (a)**: unione delle partite di tutte le squadre con `Membership` HEAD_COACH (qualsiasi stato), ordinate per `match_date` desc, limite 10. Non filtrato per periodo di tenure. Stesso debito di [OPS_RUNBOOK §10.4](../OPS_RUNBOOK.md#104-membership-manca-start_dateend_date--aperto).

---

← [Macro precedente](4_profilo_atleti.md) | → [Macro successiva](6_profilo_presidenti.md)
