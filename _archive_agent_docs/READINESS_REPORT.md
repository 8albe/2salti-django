# Pilot Readiness Report — 2salti MVP (Evidenceized)

**Date**: 2026-03-27  
**Status**: 🟠 **USABLE WITH STAFF ASSISTANCE (HYBRID READY)**

## 1. FLOW-BY-FLOW OPERATIONAL AUDIT

| Flow Name | Entry Point | Expected Behavior | Actual Behavior | Status | Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Guest Public Browsing** | `/` | Anonymous users see home, sports, teams, and standings. | Correct rendering of all public components. | **READY** | `core.tests_prod_readiness.test_public_pages_status_code` (PASS) |
| **Auth Athlete Access** | `/accounts/login/` | Role-based redirection to onboarding or dashboard. | Correct redirection to `/accounts/verify-identity/` for new users. | **READY** | Browser Audit (`audit_athlete_v2` registration & login) |
| **Onboarding Enforcement** | `@onboarding_required` | Redirected to wizard if identity/payment is missing. | Secured access. Attempting `/management/` redirects to `/accounts/verify-identity/`. | **READY** | `accounts/utils.py:L1-29` instrumentation. |
| **Report Upload** | `/matches/upload/` | Coaches can upload PDFs. | Files saved and `MatchReport` created in `UPLOADED` state. | **READY** | `matches/views.py:L108-115` audit trail. |
| **OCR Processing** | Admin Action | Extraction of match data (Team names, Scores, Events). | Successful extraction using `MockVisionProvider` (hardcoded simulation). | **SIMULATED** | `matches/services/vision_providers.py:L17-70`. |
| **Review / Validation** | `/matches/review/<id>/` | Staff reconciles names and validates JSON schema. | Schema validation and fuzzy name matching fully operational. | **READY** | `matches/admin.py:L165-260` (Review View logic). |
| **Publishing** | Admin Action | Report transitions to `PUBLISHED` and standings are rebuilt. | Standings rebuild triggered; data correctly persisted in `LeagueStanding`. | **READY** | `core.tests_monitoring` (PASS). |
| **Stuck Report Monitor** | `/management/staff-dashboard/` | Reports > 4h in non-final state are flagged. | Identified `#15` (UPLOADED) and `#14` (EXTRACTED) as stuck items. | **READY** | `staff_dashboard_v2_bottom.png` evidence. |

## 2. EXACT FILES CHANGED (OR RECENTLY VERIFIED)

1.  [`config/settings.py`](file:///home/alberto/config/settings.py): Added structured `LOGGING` dictionary and `LOGS_DIR` creation.
2.  [`management/models.py`](file:///home/alberto/management/models.py): Fixed `AuditLog` to allow `society=null` for onboarding events.
3.  [`management/views.py`](file:///home/alberto/management/views.py): Implemented `staff_dashboard` with metrics and stuck item logic.
4.  [`management/urls.py`](file:///home/alberto/management/urls.py): Routed `/management/staff-dashboard/`.
5.  [`accounts/views.py`](file:///home/alberto/accounts/views.py): Instrument `log_action` for Identity Verification and Payment completion.
6.  [`matches/views.py`](file:///home/alberto/matches/views.py): Instrument `log_action` for Report Upload and Status Changes.
7.  [`matches/services/ocr_service.py`](file:///home/alberto/matches/services/ocr_service.py): Instrument `log_action` for OCR lifecycle.
8.  [`core/integrations.py`](file:///home/alberto/core/integrations.py): [NEW] Registry of component states (REAL vs SIMULATED).
9.  [`templates/management/staff_dashboard.html`](file:///home/alberto/templates/management/staff_dashboard.html): [NEW] Dashboard UI template.

## 3. DATABASE CHANGES
- **Models Changed**: `management.AuditLog`.
- **Migrations Created**: `management/migrations/0006_alter_auditlog_society.py`.
- **Fields Added**: None (Altered `society` to `null=True`).
- **Data Backfill**: No backfill required (old records already have society).

## 4. LOGGING / OBSERVABILITY EVIDENCE
- **Logger Names**: `django`, `core`, `matches`, `management`.
- **Log File**: `/home/alberto/logs/ops.log`.
- **Observable Events**:
    - `ONBOARDING_IDENTITY_VERIFIED`: Triggered on Step 1 completion.
    - `ONBOARDING_PAYMENT_COMPLETED`: Triggered on Step 2 completion.
    - `REPORT_UPLOADED`: Triggered on file save.
    - `OCR_PROCESSING_SUCCESS`: Triggered on extraction finish.
    - `REPORT_STATUS_CHANGE`: Triggered on transition to PUBLISHED.

## 5. STAFF DASHBOARD EVIDENCE
- **URL**: `http://localhost:8001/management/staff-dashboard/`.
- **Access**: Staff only (`is_staff` or `is_superuser` check).
- **Widgets**:
    - **Report Funnel**: Query: `MatchReport.objects.values('status').annotate(count=Count('id'))`.
    - **Integration Map**: Data Source: `core.integrations.INTEGRATION_REGISTRY`.
    - **Onboarding Blockages**: Query: Individual `User.objects.filter(...)` counts per state.
    - **Stuck Reports**: Calculation: `created_at < now - 4h AND status IN [UPLOADED, PROCESSING, EXTRACTED]`.

## 6. REAL VS SIMULATED INTEGRATIONS MAP

| Component | Status | Code Evidence | Live Requirement |
| :--- | :--- | :--- | :--- |
| **OCR / Extraction** | **SIMULATED** | `MockVisionProvider` (Hardcoded matching) | API Key + `settings.OCR_PROVIDER='gpt4o'`. |
| **Email Ingestion** | **PLACEHOLDER** | `EmailIngestionService` (Unwired) | Webhook or IMAP background job. |
| **Identity Verification** | **SIMULATED** | `accounts/views.py:126` (Mock SPID success) | Real SPID Gateway integration. |
| **Payments** | **SIMULATED** | `accounts/views.py:147` (Instant mock activation) | Stripe/PayPal API key & flow wiring. |
| **Public Statistics** | **REAL** | `StandingsService.rebuild_for_league` | Active data (Publishing reports). |

## 7. TEST EVIDENCE
- **Command**: `/home/alberto/.venv/bin/python3 manage.py test core.tests_monitoring core.tests_prod_readiness`.
- **Result**: `OK` (11 tests).
- **Verified Areas**: Standings integrity, SEO, Sitemap, Robots.txt, Public response codes.
- **Missing Coverage**: No automated tests for specific `StaffDashboard` metrics logic (verified manually via browser).

## 8. BROWSER VERIFICATION EVIDENCE

| Persona | Action | URL | Result |
| :--- | :--- | :--- | :--- |
| `staff_audit` | Visit Dashboard | `/management/staff-dashboard/` | **PASS**: Widgets rendered, counts visible. |
| `audit_athlete_v2` | Registration | `/accounts/signup/` | **PASS**: Account created. |
| `audit_athlete_v2` | Onboarding Step 1 | `/accounts/verify-identity/` | **PASS**: `AuditLog` saved (after fix). |
| `audit_athlete_v2` / `final_pilot_user` | Full Onboarding | `/accounts/signup/` | **PASS**: Registration, Identity, Payment, and Setup completed. |

## 10. MICRO-HARDENING AUDIT (2026-03-27 16:00)

- **Setup Completion Logging**: **READY** (`ONBOARDING_SETUP_COMPLETED` verified in DB).
- **Dashboard Logic**: **READY** (Staff/Superusers now excluded from metrics; verified via `management.tests_ops`).
- **Pilot Mode Indicator**: **READY** (Banner visible on `/management/staff-dashboard/`).

### TOP 3 FINAL RECOMMENDATIONS:
1.  **Staff Instruction**: Ensure staff reads the "PILOT MODE" banner and understands that Identity/Payments are simulated.
2.  **Monitor `ops.log`**: Check for any `IntegrityError` during the first 24h of pilot.
3.  **GPT-4o Transition**: Plan the switch from `MockVision` to `GPT4oVision` for real ingestion.

## 11. FINAL PILOT-GO RECOMMENDATION
The system is ready for the first pilot club ("Polisportiva Delta") to begin manual report uploads and athlete onboarding in the current simulated/hybrid environment.
