## 15. Stabilità tecnica — test suite e debito

Stato: ⏳ Da fare

KO residui sulla test suite e debiti tecnici aperti.

### 15.1 Cluster KO residui

- [ ] Cluster A — Public API legacy behavior (3 KO): endpoint `api_league_list` e `api_team_detail` rimossi, chiave `name`→`full_name`. Richiede decisione backward-compatibility
- [ ] Cluster D — dedup logic (1 KO): verifica `MatchReportUploadForm.clean()` post-fix `f3179c1`
- [ ] Cluster E — OCR service no-file guard (3 KO): guardia early-return in `ocr_service.py:254` che cortocircuita NEEDS_REVIEW
- [ ] Cluster I — reconciliation blocker: verifica auto-risoluzione test 22 post Policy A (`c787b11`)
- [ ] Recount KO post-fix 10-mag (`a9ca246` audit trail + `b97e9e5` event types refactor)

### 15.2 Debiti aperti

- [ ] Bug slug `pallanuotopallanuoto` (Sport #6) — slug duplicato/concatenato
- [ ] Stats incoerenti `mrossi_test` — discrepanza `AthleteProfile.total_goals` vs `MatchEvent`
- [ ] Lista B audit utenti/società di test (admin_test_v2, Pro Recco Test, ecc.)
- [ ] Ridurre superuser di test da 5 a 1–2
- [ ] Fix `rebuild_standings` exit code (esce 0 anche su errore — OPS_RUNBOOK §3.6)

### 15.3 Decisione DB

- [ ] Decisione timing migrazione SQLite → PostgreSQL (concurrent writes, scala futura)
- [ ] Procedura dump/restore documentata e testata
- [ ] Test suite su PostgreSQL (verifica nessuna dipendenza da sfumature SQLite)

---

← [Macro precedente](14_referto_digitale_mobile.md)
