# Nota di ripartenza — 2026-04-20

## Stato filesystem al termine della sessione

Il refactor che appiattisce i test `matches/tests/*.py` → `matches/tests_*.py` è stato applicato al
filesystem e staged (`git diff --cached --name-only` mostra 6 file). NON è stato committato perché
la suite aveva 41/173 test falliti (24%) già preesistenti: committare prima di capire il debito
avrebbe reso più difficile separare i problemi.

Il log grezzo dei test è in `/tmp/test_failures_20260420.log` (665 righe, volatile al riavvio).
Il triage completo è in `docs/TEST_DEBT_TRIAGE.md`.

## Primo task di domani

Aprire `docs/TEST_DEBT_TRIAGE.md` e partire dai **3 cluster radice** che da soli coprono ~30 dei 41 fallimenti:

1. **`OCRQualityGate.evaluate()` ritorna 4-tuple** — 16 test falliscono con `ValueError: too many values to unpack (expected 3)`. La firma è cambiata da `(bool, blockers, warnings)` a `(bool, blockers, warnings, info)`. Fix: aggiornare l'unpacking in tutti i test interessati (`tests_ocr_quality_gate.py`, `tests_ocr_hardening.py`).

2. **Guardrail Zero Events in `schema.py`** — i nuovi guardrail in `assess_publish_readiness()` bloccano pubblicazioni con `events=[]` anche se il punteggio è 0-0. Almeno 6 test (`test_good_data_is_publishable`, `test_standings_updated_on_publish`, ecc.) usano dati di test senza eventi. Fix: aggiungere eventi minimi ai fixture dei test, oppure usare score `0-0` nei casi in cui gli eventi non sono rilevanti.

3. **URL `league_statistics` rinominato `league_stats`** — 4+ test e il template `base.html:347` usano ancora il vecchio nome. Il nome registrato in `core/urls.py` è `league_stats`. Fix: rinominare in `base.html` e in ogni `reverse('league_statistics', ...)` nei test.

## Sequenza di lavoro

1. Cluster 1 (4-tuple) → fix test unpacking
2. Cluster 2 (Zero Events) → fix fixture dati test
3. Cluster 3 (URL rename) → fix `base.html` + test
4. Triage residui individuale (INCERTO #38, BUG-PROD #1/#26/#28)
5. `python manage.py test matches` → verde (o skip dichiarato per i casi INCERTO)
6. **Commit unico** che include: refactor flat tests + skip/fix test debt

## File da non toccare finché non siamo lucidi

- `matches/forms.py` — modifiche pendenti pre-esistenti non ancora ispezionate in questa sessione
- Tutti i file `M` in `git status` non staged: `accounts/models.py`, `accounts/views.py`,
  `core/views.py`, `matches/models.py`, `matches/urls.py`, `matches/views.py`,
  `static/css/style.css`, `templates/accounts/dashboard.html`, `templates/base.html`,
  `templates/home.html`, `templates/matches/match_detail.html`
- Qualunque migration già applicata in produzione
