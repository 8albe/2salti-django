# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**2salti** is a Django 5.0 sports league management platform for multi-sport organizations. Core workflows: user onboarding, OCR-based match report ingestion, standings management, and team convocations. The project is deployed on Linux with Gunicorn + Nginx + whitenoise.

## Non-Negotiable Rules

- **Never** call OpenAI in tests — use `OCR_PROVIDER=mock` or patch `vision_providers.py`.
- **Never** modify committed migrations. Always create new ones via `makemigrations`.
- **Never** reference `User` directly — always use `get_user_model()`.
- **Never** write to `LeagueStanding` directly — always go through `standings_service.rebuild_league_standings()`.
- **Never** commit without running `python manage.py check` and the tests of the touched app.
- Project language: Italian for UI, user-facing messages, and commit messages. English for code, comments, and technical errors.
- Always use `Europe/Rome` timezone-aware datetimes — never naive datetimes.

## Sources of Truth

Two project documents take precedence over anything else in this file for architectural decisions and feature scope:

1. **[docs/PRODUCT_BLUEPRINT.md](docs/PRODUCT_BLUEPRINT.md)** — architectural blueprint, domain model, and design rationale. Written in Italian. Authoritative for *why* things are built the way they are.
2. **[docs/FEATURE_SYLLABUS_LEGACY.md](docs/FEATURE_SYLLABUS_LEGACY.md)** — feature inventory with completion status and roadmap. Authoritative for *what* exists and *what's next*.

When in doubt, read these two before acting. If they contradict this `CLAUDE.md`, they win — and flag the inconsistency so we can fix it.

## Protected Files — Ask Before Modifying

The following files require explicit confirmation before any change:

- `config/settings.py` — even seemingly harmless variables can break production.
- `gunicorn_config.py`, `2salti_nginx_config`, `*.service` — deployment configuration.
- `accounts/middleware.py` — the onboarding state machine is fragile and coupled to wizard redirects.
- `matches/services/standings_service.py` — ranking logic; any change risks corrupting historical standings.
- Any migration already applied in production.
- `.env` and `.env.production` — credentials, never commit or overwrite.    

## Common Commands

```bash
# Development
python manage.py runserver
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput

# Testing
python manage.py test                          # all tests
python manage.py test matches                  # single app
python manage.py test matches.tests_ocr_service  # single file
python manage.py test --verbosity=2

# Useful
python manage.py check          # config validation
python manage.py showmigrations
python manage.py shell
python manage.py dbshell

# Management commands
python manage.py ops_check
python manage.py check_pilot_alerts
python manage.py send_pilot_report
python manage.py run_scheduler
```

## Architecture

### Django Apps

| App | Responsibility |
|-----|---------------|
| `accounts` | Custom user model, onboarding state machine, profile types |
| `core` | Sports, societies, teams, leagues, standings |
| `matches` | Match records, events, OCR report pipeline |
| `management` | Memberships, training, convocations, audit logs |
| `seasons` | Season archives and historical stats |
| `config` | Django settings, root URL conf, WSGI |

### Settings & Config

- Settings: [config/settings.py](config/settings.py)
- Root URLs: [config/urls.py](config/urls.py)
- Env vars loaded from `.env` via `python-dotenv`
- `AUTH_USER_MODEL = 'accounts.User'` (custom user, always use `get_user_model()`)
- Language: Italian (`it`), timezone: `Europe/Rome`
- SQLite in dev, configurable for PostgreSQL in production

### Key Environment Variables

```
SECRET_KEY, DEBUG, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS
OPENAI_API_KEY          # GPT-4V for OCR
OCR_PROVIDER            # gpt4o | mock
EMAIL_HOST_USER / EMAIL_HOST_PASSWORD
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID  # optional ops notifications
ENVIRONMENT_NAME        # production
```

### User Onboarding State Machine

`accounts/middleware.py` (`OnboardingMiddleware`) enforces this flow for every authenticated request:

```
IDENTITY_PENDING → PAYMENT_PENDING → SETUP_PENDING → MEMBERSHIP_PENDING → COMPLETED
```

Fan role skips payment. Each state redirects to its own wizard step until `setup_completed=True`.

### RBAC (Staff Roles)

Custom `staff_role` field on `User`, separate from Django's `is_staff`:

```
NONE → UPLOADER → REVIEWER → PUBLISHER → SUPERADMIN
```

Used to gate report upload, validation, and publishing. Check via `user.staff_role` against constants in `accounts/models.py`.

### Match Report Pipeline

`MatchReport` follows this status flow:

```
DRAFT → UPLOADED → PROCESSING → EXTRACTED → VALIDATED → PUBLISHED
```

Services in `matches/services/`:
- `ocr_service.py` — extracts data from PDFs/images via OpenAI or mock provider
- `schema.py` — validates OCR output against expected JSON shape
- `converters.py` — normalizes raw OCR → structured match data
- `standings_service.py` — deferred standings rebuild (triggered on publish)
- `publishing_service.py` — publishes report, updates player stats
- `integrity_service.py` — data validation guardrails before publish
- `hash_service.py` — SHA256 deduplication of uploaded files

Reports track `source` (FILE/DIGITAL), `origin` (MANUAL/EMAIL), and full audit trail via `MatchReportAuditLog`.

### OCR Output Contract

`ocr_service.py` returns a JSON object validated by `schema.py`. Consumers downstream (`converters.py`) rely on this exact shape — **do not change keys or nesting without updating the schema, converters, and fixtures together**.

Expected top-level keys:
- `match_metadata` — date, teams, league, referee
- `events` — list of ordered match events (goals, cards, substitutions)
- `players_home`, `players_away` — rosters with jersey numbers and minutes
- `raw_confidence` — per-field confidence scores from the provider

Known edge cases to preserve:
- Multi-page PDFs: concatenate pages before extraction.
- Rotated or skewed photos: the provider handles orientation, do not pre-process.
- Duplicate uploads: `hash_service.sha256_of_file()` blocks re-ingestion of identical files; near-duplicates (different scans of same report) are **not** deduplicated automatically — reviewer must decide.

When extending the OCR pipeline, update in this order:
1. `schema.py` (contract)
2. `ocr_service.py` (extraction)
3. `converters.py` (normalization)
4. Tests and fixtures in `matches/tests_ocr_service.py`

### Standings

`LeagueStanding` is a **persistent denormalized table** (not computed on the fly). After publishing a match report, `standings_service.rebuild_league_standings(league)` recalculates the full table. The `League` model has a `needs_rebuild` flag for deferred/scheduled rebuilds.

### URL Structure

```
/               → core.urls      (home, sport, society, team, player, league)
/accounts/      → accounts.urls  (signup, setup wizard, profile, claim)
/matches/       → matches.urls   (match detail, report upload/digital, queue)
/api/           → matches.api_urls (v1 REST: standings, matches, athlete, digital report CRUD)
/management/    → management.urls (trainings, club admin, ops cockpit)
/admin/         → custom op_admin_site
```

### Frontend

- Templates in `templates/` at repo root, with per-app subdirectories (Django convention).
- In production, collected static files live at `/home/alberto/staticfiles/` (served by whitenoise) and user uploads at `/home/alberto/media/`. These paths are environment-specific — never hardcode them in code.
- Static CSS: [static/css/style.css](static/css/style.css) — custom styles, Tailwind utilities
- `django-crispy-forms` + `crispy-tailwind` for form rendering
- SEO structured data (Schema.org) generated by `core/services/seo_service.py`

### Deployment

- Gunicorn config: [gunicorn_config.py](gunicorn_config.py) — binds to `unix:/tmp/2salti.sock`
- Nginx config: [2salti_nginx_config](2salti_nginx_config)
- Systemd service files in project root: `2salti.service`, plus timers for ops checks, pilot reports, and scheduler
- Static files collected to `STATIC_ROOT` (production: `/home/alberto/staticfiles/`), served by whitenoise.
- Media uploads stored at `MEDIA_ROOT` (production: `/home/alberto/media/`).

## Development Workflow

### Environment setup

- Python 3.11+ required.
- Clone the repo, then:
```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env   # then fill in secrets
  python manage.py migrate
  python manage.py runserver
```

### Branching and commits

- Branch naming: `feature/<short-name>`, `fix/<short-name>`, `chore/<short-name>`.
- Commit messages in Italian, imperative mood: "aggiungi validazione OCR", not "added OCR validation".
- One migration per feature, with a descriptive name.
- Before every commit:
```bash
  python manage.py check
  python manage.py test <touched_app>
```

### Code style

- Follow PEP 8.
- Django conventions over custom patterns.
- Type hints encouraged on service-layer functions, optional elsewhere.

## Test Layout

Tests live alongside their app code:

```
matches/tests_ocr_service.py        # OCR extraction
matches/tests_publish_guardrails.py # publish logic
matches/tests_status_semantics.py   # report state machine
matches/tests_stats_integrity.py    # stats calculation
matches/tests_email_ingestion.py    # email-received reports
matches/tests_reconciliation_logic.py
accounts/tests_onboarding.py        # onboarding flow
management/test_rbac.py             # role-based access
management/tests_cockpit.py         # ops cockpit
```

Mock the OCR provider via `OCR_PROVIDER=mock` or by patching `vision_providers.py` — never call OpenAI in tests.

## Task Examples

**Good prompts:**

- "Add an `INVALIDATED` status to `MatchReport` between `VALIDATED` and `PUBLISHED`. Update the state machine in `publishing_service.py`, add the transition to `tests_status_semantics.py`, and generate the migration."
- "In the setup wizard (`SETUP_PENDING` step), add a required `birth_date` field for athlete profiles. Update the form, the template, and `tests_onboarding.py`."
- "Refactor `standings_service.rebuild_league_standings()` to emit a structured log per league rebuild, including duration and number of matches processed. Keep the public signature unchanged."

**Bad prompts — too vague:**

- "Fix the report logic."
- "Make onboarding work better."
- "Clean up the OCR service."

Always name the app, the service, the expected output, and which tests to update.