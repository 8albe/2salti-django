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
