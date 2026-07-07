# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**2salti** is a Django 5.0 league management platform for water polo (pallanuoto). Core workflows: user onboarding, OCR-based match report ingestion, standings management, and team convocations. The `Sport` schema remains multi-sport-capable, but the product is single-sport — pallanuoto-only (scope decision 2026-07, see [[FUTURE_IDEAS.md]] §2). The project is deployed on Linux with Gunicorn + Nginx.

## Non-Negotiable Rules

- **Never** call OpenAI in tests — use `OCR_PROVIDER=mock` or patch `vision_providers.py`.
- **Never** modify committed migrations. Always create new ones via `makemigrations`.
- **Never** reference `User` directly — always use `get_user_model()`.
- **Never** write to `LeagueStanding` directly — always go through `StandingsService.rebuild_for_league()` in `matches/services/standings_service.py`.
- **Never** write `User.plan`, `Society.tier`, or `Society.is_comped` directly — always go through `core/services/entitlement_service.py` (the entitlement seam, which writes the `ENTITLEMENT_*` audit trail). Plan/tier gating is orthogonal to RBAC. Vocabulary: [docs/DOMAIN_GLOSSARY.md](docs/DOMAIN_GLOSSARY.md) §"Piano / Tier / Entitlement".
- **Never** commit without running `python manage.py check` and the tests of the touched app.
- **Never** commit secrets or environment artifacts. Files matching `.env*`, `*.service`, `*.timer`, `psw.*`, `*_history`, `.gitconfig`, `.git-credentials`, or any file containing credentials must stay out of the repo. When introducing a new sensitive file, add the matching pattern to `.gitignore` in the same commit.
- Project language: Italian for UI, user-facing messages, and commit messages. English for code, comments, and technical errors.
- Always use `Europe/Rome` timezone-aware datetimes — never naive datetimes.

## Documentation Map

Prima di iniziare qualunque task, identifica quale documento consultare.

| Tipo di task | Documento autoritativo | Contiene |
|---|---|---|
| Macchine a stati di tutti i modelli | [[STATE_MACHINES.md]] | 10 state machine verificate sul codice con transizioni e side effects |
| Mapping termini blueprint ↔ modelli Django | [[DOMAIN_GLOSSARY.md]] | 30+ entità, note tecniche su Match.is_public e onboarding_state |
| Procedure operative infrastruttura | [[OPS_RUNBOOK.md]] | Deploy, trappole tecniche, protocollo protected file, sicurezza |
| Capire il "perché" di una decisione di prodotto | [[BLUEPRINT.md]] | visione, UX, business model (italiano) |
| Roadmap e priorità feature | [[SYLLABUS.md]] | 20 macro-obiettivi funzionali con dettaglio in [docs/syllabus/](docs/syllabus/) |
| Idee fuori scope / parcheggiate | [[FUTURE_IDEAS.md]] | feature eliminate o rinviate (Shop, Media Gallery, Venue, visione multi-sport) con motivo e cosa le riaprirebbe |
| Regole, comandi, convenzioni di sviluppo | CLAUDE.md (questo file) | regole operative |

In caso di contraddizione tra documenti: `STATE_MACHINES.md > DOMAIN_GLOSSARY.md > CLAUDE.md > BLUEPRINT.md` per questioni di codice; `BLUEPRINT.md` vince sulla visione di prodotto.

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
- `Sport` è in `core.models`, non in un'app separata: `from core.models import Sport`
- Env vars loaded from `.env` via `python-dotenv`. Language: `it`, timezone: `Europe/Rome`
- SQLite in dev, configurable for PostgreSQL in production
- URL prefixes: `/` → core, `/accounts/` → accounts, `/matches/` → matches, `/api/` → matches REST v1, `/management/` → management, `/admin/` → custom op_admin_site

### State machines

Le 10 macchine a stati del progetto (MatchReport, User onboarding, RBAC, AccountProfileLink, MembershipRequest, Convocation, TrainingAttendance, PilotBug, PilotFeedback, ParentCertification) sono documentate in [docs/STATE_MACHINES.md](docs/STATE_MACHINES.md). Non duplicare qui.

### Domain model

Mapping tra termini italiani del blueprint e modelli Django: [docs/DOMAIN_GLOSSARY.md](docs/DOMAIN_GLOSSARY.md). Usare quel file quando si legge BLUEPRINT.md e non si riconosce un'entità nel codice.

### OCR edge cases

- Multi-page PDFs: **not implemented** — `PDFProcessor` exists in `matches/services/pdf_processor.py` but is never imported (dead code, no PDF lib in requirements). Open task.
- Rotated or skewed photos: handled by `ImagePreprocessor` (EXIF fix + OpenCV auto-rotate/deskew), invoked by `GPT4oVisionProvider` before the API call — do not add further pre-processing.
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
- `STATIC_ROOT = BASE_DIR / 'staticfiles'` and `MEDIA_ROOT = BASE_DIR / 'media'` ([config/settings.py:91,96](config/settings.py)). The actual filesystem path therefore depends on the working directory of the running process: in the production deploy it resolves to `/opt/2salti-new/staticfiles/` and `/opt/2salti-new/media/`; in local dev under `/home/alberto/` it resolves to `/home/alberto/staticfiles/` and `/home/alberto/media/`. nginx serves `/static/` and `/media/` via aliases pointing at the deploy paths. Never hardcode these paths in code — read them from settings.
- Static CSS: [static/css/style.css](static/css/style.css) — custom styles, Tailwind utilities
- `django-crispy-forms` + `crispy-tailwind` for form rendering
- SEO structured data (Schema.org) generated by `core/services/seo_service.py`

### Deployment

- Gunicorn config: [gunicorn_config.py](gunicorn_config.py) — binds to `unix:/tmp/2salti.sock`
- Nginx config: [2salti_nginx_config](2salti_nginx_config)
- Systemd service files in project root: `2salti.service`, plus timers for ops checks, pilot reports, and scheduler
- `2salti-monitor.timer` fires `OnCalendar=*-*-* 00,06,12,18:00:00` in UTC; it sends email only when `DataIntegrityService` detects standings discrepancies. Times are UTC, so perceived hours shift by ±1h across DST transitions (March/October).
- Structured logging: gunicorn writes to `/var/log/2salti/error.log` (weekly rotation, 12 copies kept) and `/var/log/2salti/access.log` (daily rotation, 7 copies kept), configured via `/etc/logrotate.d/2salti`. The `gunicorn_config.py` is loaded explicitly via `--config` in the systemd unit; `journalctl -u 2salti.service` only carries unit lifecycle events, not application logs.
- Static files collected to `STATIC_ROOT` = `BASE_DIR / 'staticfiles'` (resolves to `/opt/2salti-new/staticfiles/` in the production deploy), served by nginx via `/static/` alias.
- Media uploads stored at `MEDIA_ROOT` = `BASE_DIR / 'media'` (resolves to `/opt/2salti-new/media/` in the production deploy), served by nginx via `/media/` alias.
- **Deploy flow**: commit on `dev` in `/home/alberto/` → `git push origin dev` → on the VPS `cd /opt/2salti-new && git pull` → `sudo systemctl restart 2salti` (or `reload` for non-runtime changes) → verify with `curl -I https://2salti.com/`. Both `/home/alberto/` and `/opt/2salti-new/` have `origin` pointed directly at `github.com/8albe/2salti-django.git` (since 25-apr-2026); the deploy does **not** pull from the home repo.
- **Auto-migrate solo su dev.** Il dev box `/opt/2salti-dev/` **auto-migra** via `2salti-dev-autopull.service` (pull `--ff-only` → `migrate --noinput` → `collectstatic --noinput` → reload gunicorn; data-migration incluse; dettaglio in [docs/OPS_RUNBOOK.md](docs/OPS_RUNBOOK.md) §2.2). Prod `/opt/2salti-new/` resta **pull e `migrate` manuali**, gated dopo backup DB (Alberto). Dopo un pull che alza lo schema su prod, il DB resta indietro finché non si migra a mano — atteso, non un bug.

## Development Workflow

### Modalità "Macro-intera (batch dev)"

Quando il task lo dichiara esplicitamente, si lavora un'intera macro in batch sul dev senza chiedere autorizzazione fetta per fetta. Regole della modalità:

- Auto-verifica a ogni step: suite verde dopo ogni fetta; per ogni migration (schema o dati) dry-run su una **copia scratch** del DB dev e verifica che lo SHA256 del DB dev reale sia invariato prima/dopo.
- Ci si ferma solo in tre casi: (a) serve un comando riservato ad Alberto (sudo, backup DB, git push verso prod/master); (b) decisione di prodotto; (c) blocco vero. I bivi tecnici si risolvono con un default solido e si registrano.
- Decision log obbligatorio: ogni bivio risolto va tracciato ("tecnico" / "possibile-prodotto") e consegnato a fine giro in italiano, in prosa, senza codice.
- Prima della prima migration che scrive sui dati: fermarsi e far lanciare ad Alberto il backup del DB dev.
- Nessun output di PII reale (nomi, email); pk, conteggi e stringhe stagione sì. Il logging per-record delle data migration logga pk + campi tecnici, mai nomi.
- Nei giri batch **mai** `git add .` / `git add -A`: aggiungere **per path esplicito** e verificare con `git status` / `git add --dry-run` prima del commit. (Origine 2026-06-11: binari `.antigravity-ide-server/` ~525MB + 3 scratch `.py` finiti in un commit per add troppo largo → push rifiutato `GH001`.)

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
- Il `git push origin dev` lo esegue Claude Code in autonomia (Opzione 1, dal 2026-06-21). Il `git push` verso prod/`master` resta di Alberto.
- Before every commit:
```bash
  python manage.py check
  python manage.py test <touched_app>
```

### Code style

- Follow PEP 8.
- Django conventions over custom patterns.
- Type hints encouraged on service-layer functions, optional elsewhere.

### Selezione modello Claude (prompt CC)

- **Fable**: intelligenza e pianificazione — design di macro, audit, review architetturali, decisioni con trade-off.
- **Opus 4.8**: default potente per esecuzione complessa — implementazioni multi-file, refactoring, debugging non banale.
- **Sonnet 5**: economico per esecuzione meccanica ben specificata — fette già progettate nel dettaglio, doc, task ripetitivi.
- Ogni prompt per Claude Code arriva con la raccomandazione di modello inclusa.

## Test Layout

I test vivono accanto al codice delle rispettive app, con nomi `tests_*.py` o `test_*.py`.

Mock the OCR provider via `OCR_PROVIDER=mock` or by patching `vision_providers.py` — never call OpenAI in tests.

## Task Examples

**Good prompts:**

- "Add an `INVALIDATED` status to `MatchReport` between `VALIDATED` and `PUBLISHED`. Update the state machine in `publishing_service.py`, add the transition to `tests_status_semantics.py`, and generate the migration."
- "In the setup wizard (`SETUP_PENDING` step), add a required `birth_date` field for athlete profiles. Update the form, the template, and `tests_onboarding.py`."
- "Refactor `StandingsService.rebuild_for_league()` to emit a structured log per league rebuild, including duration and number of matches processed. Keep the public signature unchanged."

**Bad prompts — too vague:**

- "Fix the report logic."
- "Make onboarding work better."
- "Clean up the OCR service."

Always name the app, the service, the expected output, and which tests to update.