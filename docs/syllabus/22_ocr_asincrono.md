## 22. OCR asincrono — coda DB-backed con worker systemd

Stato: ⏳ Da fare (direzione decisa 2026-07-19, non avviata)

Togliere l'elaborazione OCR dal request cycle. Oggi `OCRService.process_and_update()` gira **sincrono** dentro la richiesta HTTP (upload view `matches/views.py:158` + admin action `process_ocr` `matches/admin.py:206`), ~80s a referto con Gemini: worker gunicorn bloccato per tutta la durata, pool saturabile con 3 upload concorrenti (OPS_RUNBOOK §10.20), timeout gunicorn+nginx alzati a 300s come **cerotto provvisorio** (OPS_RUNBOOK §3.16).

### Decisione architetturale (2026-07-19)

**Opzione (ii): coda DB-backed leggera + worker come servizio systemd.** Scartate le alternative:

- **Thread in background (opzione i):** i thread muoiono a ogni deploy/reload di gunicorn lasciando job appesi — richiederebbero comunque la guardia anti-stale, senza dare in cambio né persistenza né retry.
- **Celery + Redis (opzione iii):** sovradimensionato per un singolo VPS con SQLite; introduce un broker da operare per un volume di job che il DB regge senza sforzo.

### Contratto

Il contratto API è già descritto nel BLUEPRINT §11: l'upload restituisce `job_id` (= id del `MatchReport`) + stato iniziale; il client fa polling su `GET /api/referti/{id}/status`. **L'endpoint di polling non esiste ancora e va creato** (nessuna view di status in `matches/urls.py`/`api_urls.py`; `matches/views.py:445` è solo la gestione del campo `report_status` nella form di review, non un endpoint — la memoria di sessione lo indicava erroneamente come già esistente).

### Ambito

- [ ] Enqueue al posto della chiamata sincrona nei **due** entry point: upload view (`matches/views.py:158`) e admin action `process_ocr` (`matches/admin.py:206`)
- [ ] Coda DB-backed leggera (persistenza del job, retry esplicito, nessun broker esterno)
- [ ] Worker come **servizio systemd** dedicato (unit versionata in `deploy/systemd/` col pattern OPS_RUNBOOK §9)
- [ ] Endpoint di polling `GET /api/referti/{id}/status` (contratto BLUEPRINT §11)
- [ ] Guardia `recover_stale_reports`: referti in `PROCESSING` oltre soglia → `NEEDS_REVIEW` + audit log, agganciata ai timer systemd esistenti (chiude OPS_RUNBOOK §10.19)
- [ ] UX upload: risposta immediata + stato in polling (oggi l'utente attende ~80s la risposta sincrona)

### Dipendenze ops

Unit systemd nuova (deploy + enable gated Alberto), aggiornamento procedura di deploy (il worker va riavviato insieme al service), monitoring del worker e della coda (aggancio a `ops_check`/timer esistenti).

### Uscita

A lavoro finito, **rimuovere i timeout a 300s** (gunicorn `deploy/gunicorn/{prod,dev}/` + nginx `proxy_read_timeout`): sono il cerotto che questa macro elimina. Chiude anche OPS_RUNBOOK §10.20 (saturazione pool).

---

← [Macro precedente](21_app_multipiattaforma.md)
