## 22. OCR asincrono — coda DB-backed con worker systemd

Stato: 🚧 In corso (direzione decisa 2026-07-19; **giri 1 e 2 completati su dev il 2026-07-19**; restano il deploy prod — giro 3 — e la rimozione dei timeout 300s — giro 4)

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

#### Fix post-collaudo giro 1 (2026-07-19, dev)

Il primo upload reale su dev ha prodotto un **500 sulla review page**, non nel worker: `matches/views.py` dereferenziava `report.match` senza guardia nel ramo GET (`match.home_score`, `match.quarter_scores`) e nel ramo POST. Il referto era ancora `QUEUED` e senza partita collegata, quindi `match` era `None`.

Il bug **preesisteva** all'asincrono (un referto orfano finiva in `NEEDS_REVIEW` con `match=None` anche prima), ma era raro: la redirect dopo l'upload avveniva a elaborazione conclusa. Con l'enqueue la redirect è immediata, quindi il caso "review page senza match" da eccezione è diventato la norma — e con esso sono emersi altri due dereferenziamenti nudi nel template (`report.file.url` su file assente, `{% url 'match_detail' match.id %}` con match `None`).

Sanata la classe di bug su tutti i punti che enumerano gli stati o assumono la partita:

- `matches/views.py`: initial della form difensivo; nuova costante `REVIEW_STATUS_INITIAL` con lookup **sempre** con default (`QUEUED`/`PROCESSING` → `EXTRACTED`, ogni altro stato passa inalterato); POST senza partita respinto con messaggio invece che con `AttributeError`.
- `management/views.py`: KPI `in_flight` del cockpit non contava i referti `QUEUED`.
- Template `report_review.html` (viewer file e pulsanti), `report_queue.html`, `match_detail.html`, `ops_cockpit.html` (badge di stato + partita assente).
- Verificati e già corretti: `matches/admin.py` (`status_colored` ha `QUEUED`, lookup con default), `api_views_reports.py` (`NON_FINAL_STATES`), `ocr_queue.py`/`ocr_service.py`.

Regressione: `matches/tests_review_page_states.py`, 8 test che esercitano la review page su **tutti** gli stati del modello, con e senza partita collegata. Suite: 596 test OK (2 skipped).

### As-built giro 2 (2026-07-19, dev)

Chiude la guardia sugli orfani, aggancia l'osservabilità e sana un buco di metodo.

**Backstop `recover_stale_reports`.** Comando (`--minutes`, default 15; `--dry-run`) + unit `Type=oneshot` e timer `OnCalendar=*:0/15` in `deploy/systemd/{prod,dev}/`. La semantica ratificata è il **requeue capped**, non il `NEEDS_REVIEW` diretto dello sketch di OPS_RUNBOOK §10.19: sotto il cap il referto torna in `QUEUED` con audit `ocr_stale_requeue` e ripartenza immediata (nessun backoff — non ha fallito, gli è morto sotto il worker); a tentativi esauriti va in `NEEDS_REVIEW` + notifica. Lo sketch era stato scritto quando non esistevano né worker né retry; col cap a `MAX_ATTEMPTS` che già protegge dalle poison pill, arrendersi al primo orfano brucerebbe referti sani. Il comando **delega** a `OCRQueueService.requeue_stale()`, lo stesso metodo della sweep di avvio del worker: una regola, due inneschi, e un test che verifica proprio la condivisione del code path.

**Osservabilità in `ops_check`.** Tre segnali: profondità della coda (`QUEUED > 10` → YELLOW), referti in `PROCESSING` oltre soglia (→ **RED**, è il sintomo netto di worker morto), referti con tentativi esauriti (→ YELLOW). Motivazione: un worker fermo non ha sintomi propri — i referti smettono di avanzare e basta, senza errori, senza mail, senza pagine rotte.

**Il buco di metodo — copertura parametrica estesa.** Il giro 1 aveva scoperto che l'introduzione di `QUEUED` aveva rotto **7 punti su 14** che enumeravano gli stati a mano, con la suite verde: ogni catena `{% if status == '...' %}` aveva un ramo `{% else %}` che assorbiva lo stato nuovo in silenzio, e nessun test forzava un referto attraverso le pagine in ogni stato. Il giro 1 aveva coperto solo review page e cockpit. Il giro 2 estende la tecnica a tutte le superfici e, soprattutto, rimuove la causa:

- Nuovo modulo `matches/status_presentation.py`: mappa unica stato→**tono semantico**, palette per tema (`dark`/`light`/`dot`/`border`/`admin`), e **bucket operativi come partizione totale e disgiunta**. Un solo mapping stato→tono e N palette: aggiungere un tema non tocca gli stati, aggiungere uno stato non tocca i temi.
- Le cinque catene inline nei template diventano il filtro `status_classes` (templatetag `report_status`).
- Test in `matches/tests_status_coverage.py`: la checklist si deriva da `Status.choices`, quindi un decimo stato entra in copertura da solo e fa fallire la suite finché non è classificato. Le mappe si verificano per **totalità**, non per valore (non si asserisce che PUBLISHED sia verde — è estetica che cambia — ma che ogni stato abbia tono, bucket e classe in ogni tema).
- Audit sui template sulla forma di quello del gate di visibilità del risultato: scandisce il filesystem e fallisce se un template *nuovo* reintroduce una catena inline, con allowlist motivata e guardia anti-ruggine sulla regex.

**Punti trovati rotti nel farlo, e corretti:**

| Punto | Difetto |
|---|---|
| `core/management/commands/audit_db_inventory.py` | la lista dei non-finali aveva perso `QUEUED` dal rilascio della coda: i referti accodati sparivano dall'inventario. **Bug reale già stale**, non ipotetico |
| `management/views.py` (cockpit) | `DRAFT` non ricadeva in nessuno dei 5 KPI: i referti digitali in bozza erano invisibili allo staff. Mancava anche `done` dall'aggregate |
| `matches/admin.py` `status_colored` | `DRAFT` assente dal dizionario colori → fallback nero, indistinguibile da `REJECTED` |
| `matches/api_views_reports.py` | `NON_FINAL_STATES` era una copia locale: un futuro stato transitorio sarebbe stato dichiarato `is_final` e il client avrebbe smesso di fare polling su un referto ancora in lavorazione |
| `ops_cockpit.html`, `staff_dashboard.html` | stampavano il **codice grezzo** (`NEEDS_REVIEW`) invece dell'etichetta italiana |
| badge chains dei 4 template | `report_queue` copriva 5 stati su 9; in `match_detail` un referto `REJECTED` era graficamente identico a uno `VALIDATED` |

Test: 43 nuovi (`tests_status_coverage.py`, `tests_recover_stale_command.py`). Suite: **663 test OK** (2 skipped), provider mockato.

**Rinviato per disegno:** la scadenza batch dei `MatchJuryLink` sullo stesso timer. Il lazy-at-read funziona già, e accoppiare due macchine a stati non correlate sullo stesso innesco allarga scope e superficie di test senza risolvere un problema osservato.

### Ambito

- [x] Enqueue al posto della chiamata sincrona nei **due** entry point: upload view e admin action `process_ocr`
- [x] Coda DB-backed leggera (persistenza del job, retry esplicito, nessun broker esterno)
- [x] Worker come **servizio systemd** dedicato (unit versionata in `deploy/systemd/`, pattern OPS_RUNBOOK §9)
- [x] Endpoint di polling `GET /api/referti/{id}/status` (contratto BLUEPRINT §11)
- [x] UX upload: risposta immediata + stato in polling
- [x] Guardia `recover_stale_reports` + timer systemd, e aggancio a `ops_check` (profondità coda, referti stale) — **giro 2**, chiude OPS_RUNBOOK §10.19 (su dev; install del timer su prod nel giro 3)
- [ ] Deploy su prod: migration gated dopo backup DB, install unit worker **e unit del backstop**, `OPTIONS timeout` + logging in `config/settings.py` — **giro 3**
- [ ] Rimozione dei timeout 300s — **giro 4**, dopo un periodo di osservazione su prod

### Dipendenze ops

Unit systemd nuova (install ed enable gated Alberto, comandi nel `README.md` di `deploy/systemd/`), procedura di deploy da aggiornare (su prod il worker va riavviato insieme al service), monitoring del worker e della coda da agganciare a `ops_check`/timer (giro 2).

### Uscita

A lavoro finito, **rimuovere i timeout a 300s** (gunicorn `deploy/gunicorn/{prod,dev}/` + nginx `proxy_read_timeout`): sono il cerotto che questa macro elimina. Chiude anche OPS_RUNBOOK §10.20 (saturazione pool).

---

← [Macro precedente](21_app_multipiattaforma.md)
