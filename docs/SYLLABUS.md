# 2salti — Syllabus Operativo

> Versione 1.0 — 2026-05-20
> Stato reale al 20 maggio 2026. Aggiornare dopo ogni sessione di lavoro.

## Come leggere questo documento

Il syllabus organizza il lavoro su tre livelli:

- **Macro-aree** (MACRO 1–6): grandi blocchi di attività — stabilità, feature attive, roadmap, ops, prodotto/business, documentazione.
- **Capitoli** (1.1, 1.2, ...): aree tematiche dentro una macro-area.
- **Task**: singole unità di lavoro, ciascuna con stato e priorità.

### Legenda stati

- ✅ **FATTO** — completato e verificato
- 🔄 **IN CORSO** — lavorazione attiva, non ancora chiuso
- ⏳ **TODO** — pianificato, non ancora iniziato
- ❌ **BLOCCATO** — fermato da decisione esterna o prerequisito mancante

### Legenda priorità

- 🔴 **ALTA** — bloccante per la prossima sessione o per stabilità prodotto
- 🟡 **MEDIA** — importante ma non urgente
- 🟢 **BASSA** — quando c'è tempo, o sotto soglia di valore

## Stato snapshot (20-mag-2026)

Il prodotto è in stato **pilot avanzato**: 15 feature implementate complete, 4 parziali (Identity Verification, Sponsors, AI Stats Engine v0, Season Archive), 2 sperimentali (Pilot Program, Ops Commands). Il workflow referti è operativo end-to-end (upload → OCR → review → publish → standings), il pubblico vede dati reali, l'admin cockpit è funzionante.

Test suite: **~173 test totali, 8 KO residui** distribuiti su 4 cluster aperti (Public API legacy, dedup, OCR no-file guard, reconciliation blocker). Tutti i BUG-PROD originali sono chiusi. I KO residui sono tutti REFACTOR-INCOMPLETO o decisioni di prodotto pendenti. Count da riconfermare dopo i fix del 10-mag (`a9ca246` audit trail wire + `b97e9e5` event types refactor) che possono aver mosso ulteriori test.

Documentazione allineata al 20-mag-2026 (commit `756495f`). Quattro documenti obsoleti da archiviare: `FEATURE_SYLLABUS_LEGACY.md`, `READINESS_REPORT.md`, `tasks.md`, `GEMINI.md`.

Ambiente prod `2salti.com` stabile su `/opt/2salti-new/`. Dev remoto attivo su `dev.2salti.com` (`/opt/2salti-dev/`) con auto-pull ogni 2 minuti.

---

## MACRO 1 — Stabilità e debito tecnico

### 1.1 Test suite — cluster KO residui

- ⏳ 🔴 **Cluster A: Public API legacy behavior (3 KO)** — endpoint `api_league_list` e `api_team_detail` rimossi, chiave `name` rinominata `full_name`. Richiede decisione di prodotto su backward-compatibility prima del fix. Stima: 45 min decisione + 30 min fix.
- ⏳ 🟡 **Cluster D: dedup logic (1 KO)** — verificare che `MatchReportUploadForm.clean()` interroghi davvero `MatchReport.objects.filter(file_hash=…)` dopo il fix `f3179c1` del 28-apr. Stima: ~1h analisi.
- ⏳ 🟡 **Cluster E: OCR service no-file guard (3 KO)** — guardia early-return in `ocr_service.py:254` cortocircuita prima dell'exception path che dovrebbe produrre `NEEDS_REVIEW`. Decidere se rimuovere la guardia o aggiornare gli status attesi nei test. Stima: ~1h analisi.
- ⏳ 🟢 **Cluster I: reconciliation blocker — verifica auto-risoluzione** — il fix Policy A del 2-mag (`c787b11`) ha cambiato il messaggio del blocker; il test 22 (`test_review_view_context_reliability`) potrebbe passare automaticamente. Verifica: un singolo run, 5 min.
- ⏳ 🟡 **Recount KO post-fix 10-mag** — il refactor event types `b97e9e5` e il wire audit trail `a9ca246` possono aver modificato la suite; riallineare il count residuo dopo run completo `manage.py test`.

### 1.2 Side-quest tecniche pendenti

- ⏳ 🟡 **Bug slug pallanuotopallanuoto (Sport #6)** — slug duplicato/concatenato sul record Sport; investigare causa e ripulire.
- ⏳ 🟡 **Stats incoerenti utente mrossi_test** — discrepanza fra `AthleteProfile.total_goals` e `MatchEvent` reali; diagnosticare e decidere se rebuild o data fix.
- ⏳ 🟢 **Eliminare backup DB pre-wipe 12-mag** — `db.sqlite3.backup-pre-wipe-20260512` in `/home/alberto/`, tenere fino a ~19-mag e poi cancellare.
- ⏳ 🟢 **Backup git pre-filter-repo (109MB)** — backup dell'history pre-cleanup del 22-apr; tenere ancora 1–2 mesi per safety net.
- ⏳ 🟡 **Lista B audit (admin_test_v2, Pro Recco Test, ecc.)** — utenti e società di test creati in fase pilot; valutare cleanup massivo o singolo.
- ⏳ 🟡 **Ridurre superuser di test da 5 a 1–2** — ripulire account creati per debugging accumulati durante il pilot.
- ⏳ 🔴 **Decisione SQLite → PostgreSQL** — produzione attuale è SQLite; valutare migrazione prima del go-live pubblico (concurrent writes, dump/restore, replica). Vedi 4.1.

### 1.3 Debiti documentali

- ✅ 🟢 **Allineamento doc 20-mag-2026** — commit `756495f` chiude 5 fix chirurgici (OPS_RUNBOOK §1, STATE_MACHINES header, DOMAIN_GLOSSARY VERIFIED/source-origin, FEATURE_STATUS gap VERIFIED, TEST_DEBT_TRIAGE §10.2 §10.3).
- ✅ 🟢 **Creazione BLUEPRINT.md + SYLLABUS.md** — questa sessione, master document e mappa operativa unificati.
- ⏳ 🟢 **Archiviare `FEATURE_SYLLABUS_LEGACY.md`** — superato da BLUEPRINT + SYLLABUS + FEATURE_STATUS. Spostare in `_archive_agent_docs/`.
- ⏳ 🟢 **Archiviare `READINESS_REPORT.md`** — snapshot del 27-mar pre-pilot, superato dalla baseline corrente.
- ⏳ 🟢 **Rimuovere `tasks.md`** — ToDo personale di aprile, sostituita dal syllabus.
- ⏳ 🟢 **Rimuovere `GEMINI.md`** — file vuoto residuo da sperimentazione Gemini CLI.

---

## MACRO 2 — Feature in sviluppo attivo

Le altre feature 🟡 Parziale (Identity Verification, AI Stats Engine v0, Season Archive) sono confluite nelle voci roadmap corrispondenti in MACRO 3 (3.8, 3.10, 3.7) per evitare duplicazione.

### 2.1 Sponsors (🟡 Parziale)

- ⏳ 🟢 **Modello `Sponsor_Assets` separato** — oggi è `JSONField` flat su `Society` (lista `[{"name", "logo_url"}]`). Migrare a modello dedicato con placement (pagina società, profilo atleta, footer) e targeting per stagione. Riferimento: blueprint §10, §13.
- ⏳ 🟢 **Test serializzazione sponsor** — area senza copertura dedicata (FEATURE_STATUS Coverage Gaps).

---

## MACRO 3 — Feature da implementare (roadmap)

### 3.1 Jury Tokens e firma arbitro

- ⏳ 🔴 **Modello `JuryToken`** — match-specific, `user_id` + `match_id`, finestra validità 30 min pre-match, revoca automatica al fischio finale, revoca manuale admin. Riferimento: blueprint §7.4.1, §10, §14. Prerequisito: ruolo "Giuria" nell'enum `User.role` (vedi 3.9). Stima: media.
- ⏳ 🔴 **Endpoint emissione token + workflow validazione** — `POST /api/jury/token/issue` con verifica federazione/lega. Bloccato su decisione "chi emette" (vedi 5.1).
- ⏳ 🔴 **Firma PIN arbitro + immutabilità referto** — workflow firma a fine gara, hash/lock sul `MatchReport`, correzioni post-firma solo via admin con audit. Riferimento: blueprint §7.4.3, §14.

### 3.2 Media Gallery + AI Tagging

- ⏳ 🟡 **Modello `Media` + upload Premium** — foto/video associati al match, storage su bucket+CDN, lifecycle policy.
- ⏳ 🟡 **Pipeline AI tagging** — face detection + match automatico con roster ufficiale. Riferimento: blueprint §7.6.
- ⏳ 🟡 **Coda di review manuale** — almeno inizialmente semi-automatica per evitare mis-tagging.
- ⏳ 🔴 **Opt-in minorenni + opt-out atleti** — privacy GDPR-compliant; opt-in genitore obbligatorio per minori. Stima complessità: alta (legale + tecnica).

### 3.3 Live Alerts push

- ⏳ 🟡 **Infrastruttura push notifications** — service worker, registrazione device, channel per match. Gating Premium.
- ⏳ 🟡 **Trigger su transizioni MatchReport** — gol live, fine periodo, fine partita (collegato a Referto Digitale online).
- ⏳ 🟢 **Preferenze utente per categoria alert** — solo squadra propria, solo match con figlio, ecc. (collegato a 3.5).

### 3.4 Shop vetrina + webhook HMAC

- ⏳ 🟡 **Modello `Shop_Orders` + bottone "Richiesta Materiale"** — niente checkout in-app, 2salti è intermediario.
- ⏳ 🟡 **Webhook outbound firmato HMAC verso società** — retry policy, dashboard delivery status.
- ⏳ 🟢 **Notifica admin club su failure webhook** — SLA aperto (vedi 5.1).

### 3.5 User Preferences / Widget Dashboard

- ⏳ 🟡 **Modello `UserPreferences`** — layout widget per utente, tema colore, opt-in notifiche. Riferimento: blueprint §7.1, §12.
- ⏳ 🟡 **Sistema slot riordinabili** — NON drag&drop libero. Pre-set di widget riordinabili e nascondibili.
- ⏳ 🟢 **Profili default per ruolo** — atleta, genitore, allenatore, dirigente, arbitro hanno layout di default sovrascrivibili da Premium.

### 3.6 Subscription three-tier

- ⏳ 🔴 **Modello `Subscription` separato** — oggi è codificato in 2 CharField su `User` (`subscription_status` INACTIVE/ACTIVE + `subscription_end_date`). Migrare a modello dedicato con enum FREEMIUM / PREMIUM / CLUB_PRO.
- ⏳ 🔴 **Wiring pagamenti** — Stripe o PayPal, gating feature server-side per piano.
- ❌ 🔴 **Pricing definitivo** — bloccato su validazione con product owner (vedi 5.2).

### 3.7 Season Recap PDF

Il modello `SeasonArchive` esiste già (🟡 Parziale in FEATURE_STATUS) ma la generazione PDF no. Riferimento: blueprint §7.1, §13.

- ⏳ 🟡 **Generatore PDF Season Recap** — Premium-gated, stagione atleta/squadra.
- ⏳ 🟡 **Template grafico Recap** — definire layout PDF (cover, stats principali, highlights, footer sponsor); colori squadra opt-in.
- ⏳ 🟢 **Distribuzione asincrona via email/dashboard** — coda batch, non on-demand.
- ⏳ 🟢 **Decisione privacy minori** — opt-in genitore richiesto per generazione o solo per condivisione? (vedi 5.1).

### 3.8 SPID/CIE automatico

Identity Verification è 🟡 Parziale in FEATURE_STATUS: il campo `identity_status` esiste e la vista `verify_identity()` è funzionante ma manuale. Riferimento: blueprint §7.3.

- ⏳ 🔴 **Integrazione SPID/CIE reale** — scelta provider (Aruba ID, Poste ID Multi-IDP, redirect SPID nazionale) e wiring completo.
- ⏳ 🟡 **Workflow fallback documento + selfie per casi eccezionali** — stranieri, minorenni; decisione di prodotto aperta su chi valida (vedi 5.1).

### 3.9 Ruolo "Giuria" nell'enum `User.role`

- ⏳ 🔴 **Decisione enum** — aggiungere valore `jury` a `User.role` (oggi: athlete, coach, referee, fan, president) oppure gestire come sotto-ruolo di referee. Riferimento: blueprint §7.1. Prerequisito per 3.1.
- ⏳ 🟡 **Migrazione DB e backfill** — dopo decisione, migration con eventuale conversione utenti esistenti.

### 3.10 Chatbot AI (Premium)

AI Stats Engine v0 è 🟡 Parziale in FEATURE_STATUS: endpoint query-risposta basilare presente, chatbot interattivo no. Riferimento: blueprint §7.5.

- ⏳ 🟡 **Stabilizzare hybrid mode redirect/direct answer** — completare la logica router pagina-esistente vs risposta diretta DB; copy CTA "Vedi classifica completa marcatori".
- ⏳ 🟡 **Estendere `AIQueryLog` per metriche di qualità** — tracciare hit rate redirect vs direct answer, query non risolte, ambiguità.
- ⏳ 🟡 **Chatbot interattivo multi-turn** — v1 richiede memoria conversazione, RBAC server-side rigoroso e audit log per comando.
- ⏳ 🟡 **Function calling per comandi operativi** — spostare widget, cambiare tema, applicare colori squadra, gestire notifiche. Decisione aperta: function calling aperto vs whitelist chiusa (vedi 5.1).
- ⏳ 🟢 **Audit log visibile all'utente** — ogni comando bot tracciato per reversibilità e trasparenza.

---

## MACRO 4 — Infrastruttura e operations

### 4.1 Migrazione SQLite → PostgreSQL

- ⏳ 🔴 **Decisione timing migrazione** — SQLite oggi regge il pilot, ma concurrent writes e scala futura richiedono PostgreSQL. Pre-go-live pubblico, non oltre. Stima: 1–2 giornate inclusa procedura backup/restore testata.
- ⏳ 🟡 **Procedura dump/restore documentata** — script ripetibile per migrazione, verifica integrità dati post-migrazione.
- ⏳ 🟡 **Test suite su PostgreSQL** — verificare che nessun test si appoggi a sfumature SQLite (SAVEPOINT, LIKE case-sensitivity, ecc.).

### 4.2 Ambiente staging dedicato

- ⏳ 🟡 **Setup staging separato** — oggi dev e prod convivono sulla stessa VPS (`/home/alberto/` + `/opt/2salti-new/` + `/opt/2salti-dev/`). Staging "vero" su VPS separata o subdomain dedicato (es. `staging.2salti.com`).
- ⏳ 🟢 **Pipeline deploy staging → prod** — checklist pre-promote, smoke test automatici.

### 4.3 Monitoring e alerting

- ✅ 🟢 **Logging strutturato gunicorn** — `/var/log/2salti/error.log` settimanale x12, `access.log` daily x7.
- ✅ 🟢 **Monitor integrità classifiche** — `2salti-monitor.timer` ogni 6h UTC, email su discrepanze.
- ⏳ 🟡 **Sentry o equivalente per error tracking applicativo** — oggi cattura solo via log. Sentry attiva la dashboard remota e gli alert.
- ⏳ 🟢 **Dashboard metriche pipeline OCR** — tempi medi upload→publish, success rate, backlog NEEDS_REVIEW.
- ⏳ 🟢 **Fix `rebuild_standings` exit code** — il management command esce 0 anche su errore interno (OPS_RUNBOOK §3.6); aggiungere `sys.exit(1)` su eccezioni catturate.

### 4.4 Backup automatico DB e media

- ⏳ 🔴 **Backup automatico schedulato DB** — cron + rsync su storage esterno. Oggi backup manuale (vedi backup pre-wipe 12-mag).
- ⏳ 🟡 **Backup automatico media uploads** — `/opt/2salti-new/media/` mirror su storage esterno con lifecycle.
- ⏳ 🟡 **Procedura restore testata** — runbook documentato + drill periodico.

### 4.5 Disciplina deploy

- ✅ 🟢 **Deploy flow documentato** — CLAUDE.md §Deployment + OPS_RUNBOOK §2.
- ⏳ 🟢 **Checklist pre-merge** — `manage.py check` + test app toccata + grep segreti.
- ⏳ 🟢 **Checklist pre-deploy** — pull deploy + reload service + verifica `curl -I https://2salti.com/`.
- ⏳ 🟡 **Hook post-commit home → reminder pull deploy** — automazione anti-drift home/deploy (oggi disciplina manuale, vedi OPS_RUNBOOK §2).

---

## MACRO 5 — Prodotto e business

### 5.1 Decisioni di prodotto pendenti

Dal blueprint §"Punti da validare con il product owner".

- ❌ 🔴 **Federazione token giuria** — chi è l'autorità che emette i token? Nazionale, lega o club? Bloccante per 3.1.
- ❌ 🟡 **Conflict resolution sync multi-device** — policy se due dispositivi giuria editano lo stesso match contemporaneamente.
- ❌ 🟡 **SLA webhook shop** — quante ore di retry, notifica admin club su failure?
- ❌ 🟢 **UX sito esterno club** — redirect diretto al sito club (A) vs pagina teaser con badge (B)?
- ❌ 🟡 **Gallery moderazione** — segnalazione automatica o dashboard manuale Club Admin?
- ❌ 🟡 **Chatbot function calling scope** — aperto vs whitelist chiusa di comandi?
- ❌ 🟢 **Season Recap minorenni** — opt-in per generazione PDF o solo per condivisione?
- ❌ 🟡 **Identity fallback validator** — chi valida documenti nel fallback SPID? Staff 2salti vs Club Admin?

### 5.2 Validazione pricing three-tier con Damiano

- ❌ 🔴 **Definire prezzi Premium Utente e Club Pro** — TBD nel blueprint Cap. 13. Da validare con campione di famiglie (Premium) e società (Club Pro).
- ⏳ 🟡 **Modello revenue projection** — stima ricavi annui per piano in funzione di N utenti / N società iscritte.
- ⏳ 🟢 **Verifica conversion rate ipotizzato** — % Freemium → Premium e % Club Pro come baseline planning.

### 5.3 Proposta federazione (demo Referto Digitale)

- ⏳ 🟡 **Demo funzionante Referto Digitale mobile** — Phase 2 della roadmap referto digitale; oggi backend pronto (Phase 1 ✅), manca form mobile Base + Avanzato.
- ⏳ 🔴 **Documento proposta federazione** — pitch deck + demo video per proporre il passaggio dal cartaceo al digitale.
- ⏳ 🟡 **Contratto tipo società ↔ 2salti** — Club Pro, Sponsor, policy minori.

---

## MACRO 6 — Documentazione e memoria

### 6.1 Obsidian setup

- ⏳ 🟢 **Cartella `docs/` clonata su PC Windows** — sync via git per editing fluido in Obsidian.
- ⏳ 🟢 **Vault Obsidian dedicato** — link interni `[[file]]`, tag, search nativi.
- ⏳ 🟢 **Plugin Obsidian utili** — Git, Templater, Dataview per query su feature/state machines.

### 6.2 Claude Code Work configurazione e skill

- ⏳ 🟢 **Allowlist Bash comuni** — applicare skill `fewer-permission-prompts` per ridurre prompt su comandi read-only ricorrenti.
- ⏳ 🟢 **Skill ed agent custom utili** — valutare creazione skill per workflow ricorrenti (es. "sync home → deploy", "diag KO test").
- ⏳ 🟢 **Memoria auto-aggiornata** — sistema memory già attivo, verificare aggiornamento dopo ogni sessione significativa.

### 6.3 Pulizia file obsoleti

- ⏳ 🟢 **Spostare `FEATURE_SYLLABUS_LEGACY.md` in `_archive_agent_docs/`** — superato da BLUEPRINT + SYLLABUS + FEATURE_STATUS.
- ⏳ 🟢 **Spostare `READINESS_REPORT.md` in `_archive_agent_docs/`** — snapshot del 27-mar pre-pilot.
- ⏳ 🟢 **Eliminare `tasks.md`** — ToDo personale di aprile sostituita dal syllabus.
- ⏳ 🟢 **Eliminare `GEMINI.md`** — file vuoto residuo.
- ⏳ 🟢 **Consolidare `_session_notes/` vs `docs/_session_notes/`** — due directory parallele per session note, decidere quale mantenere come unica.

### 6.4 Aggiornamento memoria dopo ogni sessione

- ⏳ 🟢 **Disciplina sessione** — al termine di ogni sessione attiva, scrivere session note in `/home/alberto/_session_notes/` e aggiornare SYLLABUS se cambia il quadro task.
- ⏳ 🟢 **Verificare voce `2salti_dev_environment` in MEMORY.md** — la memoria menziona auto-pull `/opt/2salti-dev/`; conferma vs runbook §1 (ora allineati post-fix 20-mag).
- ⏳ 🟢 **Revisione periodica obsolescenza memorie** — memorie sono point-in-time, verificare contro stato corrente almeno una volta al mese.

---

*Fonti incrociate: [BLUEPRINT.md](BLUEPRINT.md) (visione), [FEATURE_STATUS.md](FEATURE_STATUS.md) (inventario feature), [STATE_MACHINES.md](STATE_MACHINES.md) (workflow), [TEST_DEBT_TRIAGE.md](TEST_DEBT_TRIAGE.md) (cluster KO), [OPS_RUNBOOK.md](OPS_RUNBOOK.md) (infrastruttura), [DOMAIN_GLOSSARY.md](DOMAIN_GLOSSARY.md) (mapping termini).*
