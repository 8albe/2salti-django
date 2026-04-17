# Tasks — 2salti Project

## TODO
- [ ] Monitor Afternoon Run (14:00) — Verify that the systemd timer triggers `ops_check` and emails are sent.
- [ ] Monitor Evening Run (20:00) — Verify that the systemd timer triggers `ops_check` and emails are sent.
- [ ] Perform Manual Operator Checklist — Ensure all services are GREEN and no logs show errors.
- [ ] Action 3: Async Standings Rebuild — Decouple `StandingsService.rebuild_for_league` in `PublishingService` using threading or async.

## DONE
- [x] Status Semantics Refactor: OCR failure now transitions to `NEEDS_REVIEW` instead of `REJECTED`.
    - Files: `models.py`, `ocr_service.py`, `admin.py`, `review.html`
    - Tests: `matches/tests_status_semantics.py`
- [x] OCR Fallback Hardening (Verified)
- [x] Inline Athlete Creation from Review UI (Verified)

## BLOCKED
- None

## DONE
- [x] System Hardening: Persistent Operational Memory — Recreating `tasks.md`, `implementation_plan.md`, and `walkthrough.md`.
- [x] Phase 10: Admin UX Hardening — Sticky action bar, priority problems, dirty state tracking, inline validation.
- [x] Phase 9: MatchReport Review Flow — Multi-action submit, structured score editor, live sync, atomic publishing.
- [x] Phase 8: Intelligent Ops Checks — `ops_services.py`, `ops_check` command, email hardening (Gmail SMTP).
