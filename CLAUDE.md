# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**2salti** is a Django 5.0 sports league management platform for multi-sport organizations. Core workflows: user onboarding, OCR-based match report ingestion, standings management, and team convocations. The project is deployed on Linux with Gunicorn + Nginx.

## Non-Negotiable Rules

- **Never** call OpenAI in tests — use `OCR_PROVIDER=mock` or patch `vision_providers.py`.
- **Never** modify committed migrations. Always create new ones via `makemigrations`.
- **Never** reference `User` directly — always use `get_user_model()`.
- **Never** write to `LeagueStanding` directly — always go through `standings_service.rebuild_league_standings()`.
- **Never** commit without running `python manage.py check` and the tests of the touched app.
- Project language: Italian for UI, user-facing messages, and commit messages. English for code, comments, and technical errors.
- Always use `Europe/Rome` timezone-aware datetimes — never naive datetimes.

## Documentation Map

Prima di iniziare qualunque task, identifica quale documento consultare.

| Tipo di task | Documento autoritativo | Contiene |
|---|---|---|
| Modifiche a stati/transizioni di un modello | [docs/STATE_MACHINES.md](docs/STATE_MACHINES.md) | 9 macchine a stati verificate sul codice |
| Cercare il modello Django da un termine italiano | [docs/DOMAIN_GLOSSARY.md](docs/DOMAIN_GLOSSARY.md) | mapping blueprint ↔ codice, 30+ entità |
| Capire se una feature esiste, dove sta, quali test la coprono | [docs/FEATURE_STATUS.md](docs/FEATURE_STATUS.md) | 21 feature operative, gap vs blueprint |
| Capire il "perché" di una decisione di prodotto | [docs/PRODUCT_BLUEPRINT.md](docs/PRODUCT_BLUEPRINT.md) | visione, UX, business model (italiano) |
| Roadmap e priorità feature | [docs/FEATURE_SYLLABUS_LEGACY.md](docs/FEATURE_SYLLABUS_LEGACY.md) | ex syllabus Antigravity, in revisione |
| Regole, comandi, convenzioni di sviluppo | CLAUDE.md (questo file) | regole operative |

In caso di contraddizione tra documenti: `STATE_MACHINES > DOMAIN_GLOSSARY > FEATURE_STATUS > CLAUDE.md > PRODUCT_BLUEPRINT` per questioni di codice; `PRODUCT_BLUEPRINT` vince sulla visione di prodotto.

## Protected Files — Ask Before Modifying

The following files require explicit confirmation before any change:

- `config/settings.py` — even seemingly harmless variables can break production.
- `gunicorn_config.py`, `2salti_nginx_config`, `*.service` — deployment configuration.
- `accounts/middleware.py` — the onboarding state machine is fragile and coupled to wizard redirects.
- `matches/services/standings_service.py` — ranking logic; any change risks corrupting historical standings.
- Any migration already applied in production.
- `.env` — credentials, never commit or overwrite.

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

## Architecture at a Glance

### Django Apps

| App | Responsibility |
|-----|---------------|
| `accounts` | Custom user model, onboarding state machine, profile types |
| `core` | Sports, societies, teams, leagues, standings |
| `matches` | Match records, events, OCR report pipeline |
| `management` | Memberships, training, convocations, audit logs |
| `seasons` | Season archives and historical stats |
| `config` | Django settings, root URL conf, WSGI |

### Key paths

- Settings: [config/settings.py](config/settings.py) — Root URLs: [config/urls.py](config/urls.py)
- User model: `accounts.User` (`AUTH_USER_MODEL`) — always use `get_user_model()`
- Env vars loaded from `.env` via `python-dotenv`. Language: `it`, timezone: `Europe/Rome`
- SQLite in dev, configurable for PostgreSQL in production
- URL prefixes: `/` → core, `/accounts/` → accounts, `/matches/` → matches, `/api/` → matches REST v1, `/management/` → management, `/admin/` → custom op_admin_site

### State machines

Le 9 macchine a stati del progetto (MatchReport, User onboarding, RBAC, AccountProfileLink, MembershipRequest, Convocation, TrainingAttendance, PilotBug, PilotFeedback) sono documentate in [docs/STATE_MACHINES.md](docs/STATE_MACHINES.md). Non duplicare qui.

### Domain model

Mapping tra termini italiani del blueprint e modelli Django: [docs/DOMAIN_GLOSSARY.md](docs/DOMAIN_GLOSSARY.md). Usare quel file quando si legge PRODUCT_BLUEPRINT.md e non si riconosce un'entità nel codice.

### Feature inventory

Per sapere se una feature esiste, dove sta, e quali test la coprono: [docs/FEATURE_STATUS.md](docs/FEATURE_STATUS.md). Aggiornato al 2026-04-20.

### OCR edge cases

- Multi-page PDFs: concatenate pages before extraction.
- Rotated or skewed photos: the provider handles orientation — do not pre-process.
- Near-duplicates (different scans of same report): **not** deduplicated automatically — reviewer must decide.

### Key Environment Variables

```
SECRET_KEY, DEBUG, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS
OPENAI_API_KEY          # GPT-4V for OCR
OCR_PROVIDER            # gpt4o | mock
EMAIL_HOST_USER / EMAIL_HOST_PASSWORD
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID  # optional ops notifications
ENVIRONMENT_NAME        # production
```

### Frontend

- Templates in `templates/` at repo root, with per-app subdirectories (Django convention).
- In production, collected static files live at `/home/alberto/staticfiles/` (served by nginx) and user uploads at `/home/alberto/media/`. These paths are environment-specific — never hardcode them in code.
- Static CSS: [static/css/style.css](static/css/style.css) — custom styles, Tailwind utilities
- `django-crispy-forms` + `crispy-tailwind` for form rendering
- SEO structured data (Schema.org) generated by `core/services/seo_service.py`

### Deployment

- Gunicorn config: [gunicorn_config.py](gunicorn_config.py) — binds to `unix:/tmp/2salti.sock`
- Nginx config: [2salti_nginx_config](2salti_nginx_config)
- Systemd service files in project root: `2salti.service`, plus timers for ops checks, pilot reports, and scheduler
- Static files collected to `STATIC_ROOT` (production: `/home/alberto/staticfiles/`), served by nginx.
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

I test vivono accanto al codice delle rispettive app, con nomi `tests_*.py` o `test_*.py`. L'inventario completo dei test per feature, incluse le aree senza copertura dedicata, è in [docs/FEATURE_STATUS.md](docs/FEATURE_STATUS.md).

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