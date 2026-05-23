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

### 15.4 RBAC Staff Roles

- [x] Sistema 5 livelli (UPLOADER ⊂ REVIEWER ⊂ PUBLISHER ⊂ SUPERADMIN, separato da `is_staff` Django)
- [x] Property `can_upload`, `can_review`, `can_publish` su `User`
- [x] Decorator/check in `management/permissions.py` — vedi STATE_MACHINES.md §3
- [ ] Ruolo "Giuria"/`jury` non presente nell'enum `User.role` (gap blueprint §7.1; valori attuali: athlete, coach, referee, fan, president)

### 15.5 Audit Logging

- [x] `AuditLog` (management) per azioni critiche di sistema (PUBLISH_REPORT, ONBOARDING_*)
- [x] `MatchReportAuditLog` (matches) per ogni transizione di stato del referto
- [x] Scrittura entrambi i log alla pubblicazione in `publishing_service.py`

### 15.6 AI Stats Engine v0 → v1

- [x] v0 endpoint query→risposta statico (`api_views.py`) + `AIQueryLog` + matching atleta basico
- [x] Calcolo statistiche aggregate via `stats_services.py`
- [ ] v1 chatbot interattivo multi-turn con history (blueprint §7.5)
- [ ] v1 hybrid mode redirect/direct answer (blueprint §9.1)
- [ ] v1 function calling con whitelist comandi
- [ ] v1 RBAC enforcement server-side per query private

### 15.7 Pilot Program

- [x] Modelli `PilotDailyLog`, `PilotBug`, `PilotFeedback`, `PilotReview`
- [x] Service `pilot_services.py` per aggregazione e analisi
- [x] Command `check_pilot_alerts` (alert automatici su soglie)
- [x] Command `send_pilot_report` (report periodico)
- [x] State machines PilotBug (6 stati) e PilotFeedback (5 stati) — STATE_MACHINES.md §8-§9

### 15.8 Ops Commands

- [x] `ops_check` — health check completo applicazione
- [x] `run_scheduler` — dispatcher tasks schedulati
- [x] `rebuild_standings` — rebuild classifica manuale
- [x] `monitor_integrity` — monitoraggio integrità dati
- [x] `ingest_emails` — pull email in ingresso
- [x] `send_pilot_report` — report operativo periodico
- [ ] Fix exit code `rebuild_standings` (vedi §15.2)

### 15.9 Coverage Gaps — feature senza test dedicati

- [ ] Aggiungere test dedicati per **Convocations** (state machine 4 stati + property time-based)
- [ ] Aggiungere test dedicati per **Training Management** (presenze + geofencing)
- [ ] Aggiungere test dedicati per **Team Communications** (Post, Comment, ChatMessage)
- [ ] Aggiungere test dedicati per **Sponsors** (JSONField serialization)

---

← [Macro precedente](14_referto_digitale_mobile.md)
