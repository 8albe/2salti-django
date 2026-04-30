# Test Debt Triage — matches app

**Data:** 2026-04-20

## Contesto

Documento prodotto dopo la recovery dei file `matches/` esclusi per errore da `.gitignore` e il
conseguente refactor che ha appiattito i test dal package `matches/tests/` a file flat `matches/tests_*.py`.
Su 173 test totali, 41 risultano falliti (24%): nessuno è stato introdotto oggi, tutti preesistevano.
Il log grezzo è in `/tmp/test_failures_20260420.log`.

---

## Inventario fallimenti

| # | Test | File test | Eccezione | File sorgente impattato | Categoria |
|---|------|-----------|-----------|------------------------|-----------|
| 1 | `ManualReviewTest.test_staff_can_review` | `test_manual_review.py` | `UnboundLocalError: MatchEvent` | `matches/views.py:422` | BUG-PROD |
| 2 | `PublicAPITestCase.test_api_athlete_privacy` | `tests_api.py` | `KeyError: 'name'` | `matches/api_views.py:139` (chiave rinominata `full_name`) | REFACTOR-INCOMPLETO |
| 3 | `PublicAPITestCase.test_api_league_list` | `tests_api.py` | `NoReverseMatch: 'api_league_list'` | `matches/api_urls.py` (URL rimosso) | REFACTOR-INCOMPLETO |
| 4 | `PublicAPITestCase.test_api_team_detail_roster` | `tests_api.py` | `NoReverseMatch: 'api_team_detail'` | `matches/api_urls.py` (URL rimosso) | REFACTOR-INCOMPLETO |
| 5 | `EndToEndPilotVerificationTest.test_full_lifecycle_coherence` | `tests_e2e_verification.py` | `NoReverseMatch: 'league_statistics'` | `templates/base.html:347` (URL rinominato `league_stats`) | REFACTOR-INCOMPLETO |
| 6 | `OCRHardeningTest.test_clean_pass` | `tests_ocr_hardening.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` (`evaluate()` ora ritorna 4-tuple) | REFACTOR-INCOMPLETO |
| 7 | `OCRHardeningTest.test_event_total_exceeds_final_fails` | `tests_ocr_hardening.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 8 | `OCRHardeningTest.test_low_field_confidence_fails` | `tests_ocr_hardening.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 9 | `OCRHardeningTest.test_score_inconsistency_fails` | `tests_ocr_hardening.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 10 | `OCRHardeningTest.test_team_mismatch_fails` | `tests_ocr_hardening.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 11 | `OCRHardeningTest.test_wrong_location_warns` | `tests_ocr_hardening.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 12 | `OCRQualityGateIntegrationTest.test_review_page_shows_quality_gate` | `tests_ocr_quality_gate.py` | `KeyError: 'ocr_is_valid'` | `matches/admin.py` (context rinominato `publish_safe`) | REFACTOR-INCOMPLETO |
| 13 | `OCRQualityGateTest.test_event_totals_mismatch` | `tests_ocr_quality_gate.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 14 | `OCRQualityGateTest.test_garbage_values` | `tests_ocr_quality_gate.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 15 | `OCRQualityGateTest.test_low_confidence` | `tests_ocr_quality_gate.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 16 | `OCRQualityGateTest.test_malformed_final_score` | `tests_ocr_quality_gate.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 17 | `OCRQualityGateTest.test_missing_root_sections` | `tests_ocr_quality_gate.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 18 | `OCRQualityGateTest.test_missing_team_name` | `tests_ocr_quality_gate.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 19 | `OCRQualityGateTest.test_quarter_totals_mismatch` | `tests_ocr_quality_gate.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 20 | `OCRQualityGateTest.test_teams_play_itself` | `tests_ocr_quality_gate.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 21 | `OCRQualityGateTest.test_valid_data` | `tests_ocr_quality_gate.py` | `ValueError: too many values to unpack (expected 3)` | `matches/services/ocr_quality_gate.py:30` | REFACTOR-INCOMPLETO |
| 22 | `ReviewUXTestCase.test_review_view_context_reliability` | `tests_ocr_service.py` | `KeyError: 'confidence'` | `matches/admin.py` (chiave assente nel context) | REFACTOR-INCOMPLETO |
| 23 | `PublicReadLayerTests.test_league_standings_public` | `tests_public_read.py` | `NoReverseMatch: 'league_statistics'` | `templates/base.html:347` | REFACTOR-INCOMPLETO |
| 24 | `PublicReadLayerTests.test_match_detail_public` | `tests_public_read.py` | `NoReverseMatch: 'league_statistics'` | `templates/base.html:347` | REFACTOR-INCOMPLETO |
| 25 | `ManualReviewTest.test_non_staff_cannot_review` | `test_manual_review.py` | `AssertionError: 302 != 403` | `matches/views.py` (`@onboarding_required` redirect prima di `PermissionDenied`) | REFACTOR-INCOMPLETO |
| 26 | `PublicAPITestCase.test_api_league_matches_filtering` | `tests_api.py` | `AssertionError: 1 != 0` | `matches/api_views.py:46` (assenza filtro `PUBLISHED`) | BUG-PROD |
| 27 | `MatchReportDeduplicationTest.test_duplicate_file_upload_is_blocked` | `tests_deduplication.py` | `AssertionError: True is not false` | `matches/forms.py` + `matches/views.py` (hash non persistito, primo report senza hash) | REFACTOR-INCOMPLETO |
| 28 | `MatchReportDeduplicationTest.test_unique_file_upload_stores_hash` | `tests_deduplication.py` | `AssertionError: 0 != 64` | `matches/views.py:124` (`file_hash` non copiato da `cleaned_data` al model) | BUG-PROD |
| 29 | `PilotMetricsTest.test_metrics_lifecycle` | `tests_metrics.py` | `AssertionError: unexpectedly None` | `matches/admin.py` (audit log `review_opened` mai scritto nella `review_view`) | REFACTOR-INCOMPLETO |
| 30 | `OCRProviderToggleTest.test_process_and_update_handles_init_failure_safely` | `tests_ocr_provider_toggle.py` | `AssertionError: 'REJECTED' != NEEDS_REVIEW` | `matches/services/ocr_service.py:254` (guardia no-file cortocircuita prima dell'exception path) | REFACTOR-INCOMPLETO |
| 31 | `OCRProviderToggleTest.test_process_and_update_with_mock_runs_quality_gate` | `tests_ocr_provider_toggle.py` | `AssertionError: False is not true` | `matches/services/ocr_service.py:254` (stessa guardia no-file) | REFACTOR-INCOMPLETO |
| 32 | `FullFlowRegressionTest.test_full_flow_mock_extraction_to_publish` | `tests_ocr_service.py` | `AssertionError: False is not true` | `matches/services/schema.py` (guardrail Zero Events + Riconciliazione blocca dati mock) | REFACTOR-INCOMPLETO |
| 33 | `OCRServiceTestCase.test_admin_action_ocr` | `tests_ocr_service.py` | `AssertionError: "Processati con successo 1 referti." non trovato` | `matches/admin.py:182` (messaggio cambiato in "Estraiti: X, In Review: Y, Errori: Z") | REFACTOR-INCOMPLETO |
| 34 | `OCRServiceTestCase.test_review_view_flow` | `tests_ocr_service.py` | `AssertionError: '' != 'Dati corretti manualmente.'` | `matches/admin.py` (`ReviewForm` non include il campo `validation_notes`) | REFACTOR-INCOMPLETO |
| 35 | `PublishReadinessTestCase.test_empty_rosters_block_publish` | `tests_ocr_service.py` | `AssertionError: False is not true` | `matches/services/schema.py:302` (roster vuoti demoti a warning, non blocker) | REFACTOR-INCOMPLETO |
| 36 | `PublishReadinessTestCase.test_good_data_is_publishable` | `tests_ocr_service.py` | `AssertionError: False is not true` | `matches/services/schema.py` (guardrail Zero Events blocca dati test senza eventi) | REFACTOR-INCOMPLETO |
| 37 | `PublishReadinessTestCase.test_low_confidence_generates_warning_not_blocker` | `tests_ocr_service.py` | `AssertionError: False is not true` | `matches/services/schema.py` (Zero Events blocca prima che confidence sia valutata come warning) | REFACTOR-INCOMPLETO |
| 38 | `PublicReadLayerTests.test_empty_states_render_safely` | `tests_public_read.py` | `AssertionError: "Nessuna partita pubblicata" non trovato` | `templates/accounts/profile.html` / `accounts/views.py` | INCERTO |
| 39 | `StandingsVerificationTest.test_rebuild_command` | `tests_standings.py` | `AssertionError: 'Ricalcolate 1 classifiche' non trovato` | `core/management/commands/rebuild_standings.py` (comando ora incrementale, richiede `needs_rebuild=True`) | REFACTOR-INCOMPLETO |
| 40 | `StandingsVerificationTest.test_standings_updated_on_publish` | `tests_standings.py` | `AssertionError: False is not true` | `matches/services/schema.py` (guardrail Zero Events blocca `publish_report`) | REFACTOR-INCOMPLETO |
| 41 | `StatusSemanticsTestCase.test_ocr_failure_moves_to_needs_review` | `tests_status_semantics.py` | `AssertionError: 'REJECTED' != NEEDS_REVIEW` | `matches/services/ocr_service.py:254` + typo `source_type=` nel test (doveva essere `source_channel=`) | REFACTOR-INCOMPLETO |

---

## Totali per categoria

| Categoria | Count |
|-----------|-------|
| REFACTOR-INCOMPLETO | 36 |
| BUG-PROD | 3 |
| INCERTO | 1 |
| TEST-OBSOLETO | 0 |
| **Totale** | **41** |

---

## Stato refactor staged

File attualmente in staging (`git diff --cached --name-only`):

```
matches/tests.py          (D — eliminato)
matches/tests/__init__.py (D — eliminato)
matches/tests_image_preprocessor.py   (R — spostato da tests/)
matches/tests_notifications.py        (RM — spostato + modificato da tests/)
matches/tests_ocr_infrastructure.py   (R — spostato da tests/)
matches/tests_openai_provider.py      (R — spostato da tests/)
```

**Nota:** il refactor di appiattimento dei test è applicato al filesystem e staged, ma NON committato.
Prossimo step concordato: triage → fix/skip dei 41 fallimenti → commit unico con messaggio descrittivo.

---

## Stato 28 aprile 2026 sera

**Suite KO: 30 → 14** dopo 8 commit della giornata. Tutti e 3 i `BUG-PROD` originali risolti.

### Commit della sessione (8)

Mattina (3):
- `6e5736d` fix(staff_dashboard): calcola stuck_reports mancante
- `df32885` fix(admin): esponi 8 ModelAdmin orfani su op_admin_site
- `d62c89f` test(ocr): allinea unpacking a 4-tuple in tests_ocr_hardening

Pomeriggio (5):
- `94d55ea` fix(middleware): whitelist claim_profile e team_access nel flusso onboarding
- `e7c18f3` test: aggiorna 4 setUp/assertion obsoleti rispetto al design corrente
- `f3179c1` fix(forms): persisti file_hash su MatchReport via form save() override (BUG-PROD #28)
- `9b3673e` fix(api): filtra match non PUBLISHED in api_league_matches (BUG-PROD #26)
- `ce4df80` fix(views): rimuovi 3 re-import locali in report_review (BUG-PROD #1)

### KO residui (14)

Riferimenti `#N` puntano alle voci della tabella del 20-aprile sopra.

| # orig | Test | Sintomo | Cluster |
|--------|------|---------|---------|
| 2  | `tests_api.PublicAPITestCase.test_api_athlete_privacy` | `KeyError: 'name'` (chiave rinominata `full_name`) | A — Public API legacy |
| 3  | `tests_api.PublicAPITestCase.test_api_league_list` | `NoReverseMatch: 'api_league_list'` | A — Public API legacy |
| 4  | `tests_api.PublicAPITestCase.test_api_team_detail_roster` | `NoReverseMatch: 'api_team_detail'` | A — Public API legacy |
| 12 | `tests_ocr_quality_gate.OCRQualityGateIntegrationTest.test_review_page_shows_quality_gate` | `KeyError: 'ocr_is_valid'` nel context | B — Admin review context keys |
| 22 | `tests_ocr_service.ReviewUXTestCase.test_review_view_context_reliability` | `KeyError: 'confidence'` nel context | B — Admin review context keys |
| 25 | `test_manual_review.ManualReviewTest.test_non_staff_cannot_review` | `302 != 403` (onboarding redirect prima di `PermissionDenied`) | C — Onboarding redirect vs 403 |
| 27 | `tests_deduplication.MatchReportDeduplicationTest.test_duplicate_file_upload_is_blocked` | `True is not false` (secondo upload non bloccato) | D — Dedup logica check |
| 30 | `tests_ocr_provider_toggle.OCRProviderToggleTest.test_process_and_update_handles_init_failure_safely` | `'REJECTED' != NEEDS_REVIEW` | E — `ocr_service` guardia no-file |
| 31 | `tests_ocr_provider_toggle.OCRProviderToggleTest.test_process_and_update_with_mock_runs_quality_gate` | `False is not true` (stessa guardia no-file) | E — `ocr_service` guardia no-file |
| 32 | `tests_ocr_service.FullFlowRegressionTest.test_full_flow_mock_extraction_to_publish` | `False is not true` (Zero Events guardrail blocca mock) | F — Schema Zero Events |
| 33 | `tests_ocr_service.OCRServiceTestCase.test_admin_action_ocr` | Stringa cambiata: "Estraiti: X, In Review: Y, Errori: Z" | G — Admin message stringa |
| 39 | `tests_standings.StandingsVerificationTest.test_rebuild_command` | "Ricalcolate 1 classifiche" non trovato (comando incrementale) | H — `rebuild_standings` incrementale |
| 40 | `tests_standings.StandingsVerificationTest.test_standings_updated_on_publish` | `False is not true` (Zero Events blocca `publish_report`) | F — Schema Zero Events |
| 41 | `tests_status_semantics.StatusSemanticsTestCase.test_ocr_failure_moves_to_needs_review` | `'REJECTED' != NEEDS_REVIEW` + typo `source_type=` nel test | E — `ocr_service` guardia no-file |

### Composizione per categoria

| Categoria | 20 aprile | 28 aprile sera |
|-----------|-----------|----------------|
| REFACTOR-INCOMPLETO | 36 | 14 |
| BUG-PROD            | 3  | 0  |
| INCERTO             | 1  | 0  |
| TEST-OBSOLETO       | 0  | 0  |
| **Totale**          | **41** | **14** |

I 14 residui sono **tutti REFACTOR-INCOMPLETO**: codice di produzione evoluto senza aggiornare i test corrispondenti. Nessun bug funzionale residuo bloccante.

### Cluster residui per la prossima sessione

**Cluster A — Public API legacy** (3 KO: 2, 3, 4)
File: `matches/api_urls.py`, `matches/api_views.py`. Endpoint `api_league_list` e `api_team_detail` rimossi; chiave `name` rinominata `full_name`. Decisione richiesta: aggiornare i test al nuovo schema URL/serializer o ripristinare gli endpoint pubblici.

**Cluster B — Admin review context keys** (2 KO: 12, 22)
File: `matches/admin.py` (review_view). Chiavi context `ocr_is_valid` e `confidence` non più presenti. Aggiornare i test alle nuove chiavi (`publish_safe`, …).

**Cluster C — Onboarding redirect vs 403** (1 KO: 25)
File: `matches/test_manual_review.py`. Il middleware `@onboarding_required` redirige (302) prima che `PermissionDenied` produca 403. Fix probabile: completare il `setUp` di `player_user` con `identity_status='VERIFIED'` e profilo onboarding completo per arrivare al check di permessi.

**Cluster D — Dedup logica check** (1 KO: 27)
File: `matches/forms.py` + `matches/views.py`. Dopo `f3179c1` il primo upload salva l'hash; verificare che `MatchReportUploadForm.clean()` interroghi davvero `MatchReport.objects.filter(file_hash=…)` per bloccare il duplicato.

**Cluster E — `ocr_service` guardia no-file** (3 KO: 30, 31, 41)
File: `matches/services/ocr_service.py:254`. La guardia early-return su `report.file` mancante cortocircuita prima dell'exception path che dovrebbe produrre `NEEDS_REVIEW`. Decidere se rimuovere la guardia o aggiornare lo status atteso nei test. Voce 41 ha anche un typo `source_type=` (deve essere `source_channel=`).

**Cluster F — Schema Zero Events** (2 KO: 32, 40)
File: `matches/services/schema.py`. Il guardrail Zero Events blocca `publish_report` per payload mock senza eventi. Opzioni: arricchire i fixture mock con almeno un evento, o relaxare il guardrail ad un warning con dati di test.

**Cluster G — Admin message stringa** (1 KO: 33)
File: `matches/tests_ocr_service.py`. Aggiornare l'assert: il messaggio admin è ora "Estraiti: X, In Review: Y, Errori: Z" (non più "Processati con successo 1 referti.").

**Cluster H — `rebuild_standings` incrementale** (1 KO: 39)
File: `matches/tests_standings.py`. Il management command è ora incrementale e processa solo `Match.needs_rebuild=True`. Il test deve settare il flag o esercitare la modalità full-rebuild.

### Quick wins ordinati per costo/beneficio

1. **Cluster G** (1 riga, aggiorna stringa)
2. **Cluster H** (1-2 righe nel setUp)
3. **Cluster C** (completa setUp utente)
4. **Cluster B** (rinomina 2 chiavi nei test)
5. **Cluster A** (decisione di prodotto + sostituzione URL/chiavi)
6. **Cluster F** (decisione di prodotto su guardrail)
7. **Cluster E** (richiede analisi del flusso OCR + decisione su guardia)
8. **Cluster D** (richiede analisi della clean() del form)
