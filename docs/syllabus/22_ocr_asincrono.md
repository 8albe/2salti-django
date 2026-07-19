## 22. OCR asincrono — coda DB-backed con worker systemd

Stato: 🚧 In corso (direzione decisa 2026-07-19; **giro 1 completato su dev il 2026-07-19**)

Togliere l'elaborazione OCR dal request cycle. Fino al 2026-07-19 `OCRService.process_and_update()` girava **sincrono** dentro la richiesta HTTP (upload view + admin action `process_ocr`), ~80s a referto con Gemini: worker gunicorn bloccato per tutta la durata, pool saturabile con 3 upload concorrenti (OPS_RUNBOOK §10.20), timeout gunicorn+nginx alzati a 300s come **cerotto provvisorio** (OPS_RUNBOOK §3.16).

### Decisione architetturale (2026-07-19)

**Opzione (ii): coda DB-backed leggera + worker come servizio systemd.** Scartate le alternative:

- **Thread in background (opzione i):** i thread muoiono a ogni deploy/reload di gunicorn lasciando job appesi — richiederebbero comunque la guardia anti-stale, senza dare in cambio né persistenza né retry.
- **Celery + Redis (opzione iii):** sovradimensionato per un singolo VPS con SQLite; introduce un broker da operare per un volume di job che il DB regge senza sforzo.

### Contratto

Il contratto API è descritto nel BLUEPRINT §11: l'upload restituisce `job_id` (= id del `MatchReport`) + stato iniziale; il client fa polling su `GET /api/referti/{id}/status`. L'endpoint **non esisteva** ed è stato creato nel giro 1 (la nota storica che indicava `matches/views.py:445` come endpoint di status era una discrepanza: quella riga è solo la gestione del campo `report_status` nella form di review).

### As-built giro 1 (2026-07-19, dev)

- **Coda sul modello `MatchReport`**, non su un modello job separato: nuovo stato `QUEUED` + campi `ocr_attempts`, `ocr_queued_at`, `ocr_next_attempt_at`, `ocr_started_at`, `ocr_error` (migration `matches/0019_ocr_queue`, additiva). Il contratto `job_id = report_id` è così soddisfatto per costruzione, e non esistono due fonti di verità da tenere in sync.
- **`QUEUED` è distinto da `UPLOADED`**: l'accodamento è un atto esplicito, perché admin e `ingest_emails` creano referti `UPLOADED` che non devono partire da soli.
- **`OCRService`** spezzato in `enqueue()` (precondizioni storiche + fail veloce sincrono sul file mancante) e `process_claimed()` (corpo storico invariato: discovery, riconciliazione, quality gate, notifiche, path no-match). Le eccezioni tecniche propagano al chiamante: la politica di errore la decide il worker.
- **`OCRQueueService`** (`matches/services/ocr_queue.py`): claim atomico, backoff, requeue degli orfani. La funzione di requeue è già quella che userà `recover_stale_reports` nel giro 2.
- **Worker `python manage.py ocr_worker`**: polling 3s, claim atomico `UPDATE ... WHERE status='QUEUED'`, sweep di avvio sugli orfani in `PROCESSING`, SIGTERM che finisce il job corrente, self-restart (exit 0, `Restart=always`) quando `HEAD` cambia — ma solo a coda vuota, mai a metà job.
- **Retry**: solo sugli errori tecnici, 3 tentativi con backoff 60s/120s, poi `NEEDS_REVIEW` + notifica. I fallimenti di merito (quality gate, no-match) restano senza retry.
- **`GET /api/referti/{id}/status`**: payload `report_id`, `status`, `status_display`, `is_final`, `queued_at`, `started_at`, `attempts`, `updated_at`. Gate: uploader, superuser, staff `UPLOADER+`, referee, presidente/head coach di una delle due squadre. Niente dettagli di blocco nel payload: sono materia della review page.
- **UX**: la upload view risponde subito ("Referto caricato: elaborazione in corso") e la review page mostra un banner con polling ogni 4s, che ricarica la pagina a esito pronto.
- **Unit systemd** versionate in `deploy/systemd/{prod,dev}/`, con lo split della unit gunicorn preesistente e il fix delle negazioni `.gitignore` (`!deploy/systemd/**/*.service`: col pattern precedente le unit nelle sottodirectory sparivano in silenzio).

Suite: 588 test OK (2 skipped), provider mockato.

### Ambito

- [x] Enqueue al posto della chiamata sincrona nei **due** entry point: upload view e admin action `process_ocr`
- [x] Coda DB-backed leggera (persistenza del job, retry esplicito, nessun broker esterno)
- [x] Worker come **servizio systemd** dedicato (unit versionata in `deploy/systemd/`, pattern OPS_RUNBOOK §9)
- [x] Endpoint di polling `GET /api/referti/{id}/status` (contratto BLUEPRINT §11)
- [x] UX upload: risposta immediata + stato in polling
- [ ] Guardia `recover_stale_reports` + timer systemd, e aggancio a `ops_check` (profondità coda, referti stale) — **giro 2**, chiude OPS_RUNBOOK §10.19
- [ ] Deploy su prod: migration gated dopo backup DB, install unit worker — **giro 3**
- [ ] Rimozione dei timeout 300s — **giro 4**, dopo un periodo di osservazione su prod

### Dipendenze ops

Unit systemd nuova (install ed enable gated Alberto, comandi nel `README.md` di `deploy/systemd/`), procedura di deploy da aggiornare (su prod il worker va riavviato insieme al service), monitoring del worker e della coda da agganciare a `ops_check`/timer (giro 2).

### Uscita

A lavoro finito, **rimuovere i timeout a 300s** (gunicorn `deploy/gunicorn/{prod,dev}/` + nginx `proxy_read_timeout`): sono il cerotto che questa macro elimina. Chiude anche OPS_RUNBOOK §10.20 (saturazione pool).

---

← [Macro precedente](21_app_multipiattaforma.md)
