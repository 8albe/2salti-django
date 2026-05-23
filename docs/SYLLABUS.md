# SYLLABUS — Roadmap operativa 2salti

Aggiornato: 2026-05-22

Punto d'ingresso operativo del progetto. Per la visione di prodotto vedi [BLUEPRINT.md](BLUEPRINT.md).

---

## 1. Pagina home pubblica di ogni sport

Stato: 🔄 In corso

Hub pubblico per sport: classifica del campionato attivo, ultime partite con risultati, prossime partite. Multi-sport by design.

### 1.1 Backend e routing

- [x] Modello `Sport` con `point_system` e `period_label` configurabili
- [x] Viste pubbliche base per sport in `core/views.py` e routing in `core/urls.py`
- [x] Seed sport via `bootstrap_sports` management command

### 1.2 Sezioni pagina home sport

- [ ] Sezione "classifica campionato attivo" alimentata da `LeagueStanding`
- [ ] Sezione "ultime partite con risultati" (filtro `Match` PUBLISHED)
- [ ] Sezione "prossime partite" (filtro `Match` futuri)
- [ ] Sport navigator multi-sport (selettore sport in cima)

---

## 2. Pagina pubblica delle partite

Stato: 🔄 In corso

Tabellino partita completo: marcatori, eventi (espulsioni, cartellini, timeout), score per periodo, arbitri, venue, data.

### 2.1 Modello dati

- [x] `Match` con `score`, `quarter_scores`, `referees`
- [x] `MatchEvent` con enum canonico (GOAL, EXCLUSION_20, YELLOW_CARD, RED_CARD, TIMEOUT, OTHER)
- [x] `SportEventConfig` per mapping eventi per sport

### 2.2 Vista pubblica

- [x] Vista dettaglio partita base in `matches/views.py`
- [ ] Tabellino marcatori completo (raggruppamento per squadra)
- [ ] Cronologia eventi con timestamp e periodo
- [ ] Score per periodo visualizzato esplicitamente
- [ ] Sezione arbitri + venue + data
- [ ] Link a profili atleti/arbitri dalla pagina partita

---

## 3. Pagina pubblica della classifica

Stato: 🔄 In corso

Classifica per campionato/stagione: punti, gol fatti/subiti, partite giocate/vinte/perse/pareggiate. Filtrabile per stagione.

### 3.1 Backend classifiche

- [x] Modello `LeagueStanding` denormalizzato
- [x] `standings_service.rebuild_league_standings()` come unico punto di scrittura
- [x] `integrity_service` per check MISSING_RECORD / EXTRA_RECORD / DATA_MISMATCH
- [x] Command `rebuild_standings` e `monitor_integrity`

### 3.2 Vista pubblica

- [ ] Tabella classifica con colonne PG/V/N/P/GF/GS/PT
- [ ] Filtro per stagione (oggi `League.season` è CharField)
- [ ] Modello `Season` autonomo (gap blueprint §10)
- [ ] Modello `Venue/Impianto` autonomo (gap blueprint §10 — oggi `Match.location` CharField)

---

## 4. Pagina profilo pubblica degli atleti

Stato: 🔄 In corso

Anagrafica, squadra attuale, storico squadre, statistiche (gol, presenze, minuti), ruolo.

### 4.1 Modello e statistiche

- [x] `AthleteProfile` 1:1 con `User`, creato via signal `post_save`
- [x] Statistiche calcolate: `total_goals`, `total_matches`, `total_expulsions`
- [x] `AccountProfileLink` per claim profilo preesistente

### 4.2 Vista pubblica

- [ ] Pagina pubblica profilo atleta dedicata
- [ ] Sezione squadra attuale + storico squadre (da `Membership`)
- [ ] Sezione statistiche stagione corrente
- [ ] Statistica "minuti giocati" (non presente fra le metriche correnti)

---

## 5. Pagina profilo pubblica degli allenatori

Stato: 🔄 In corso

Anagrafica, squadra attuale, storico squadre, partite dirette.

### 5.1 Modello

- [x] `CoachProfile` 1:1 con `User`, creato via signal `post_save`

### 5.2 Vista pubblica

- [ ] Pagina pubblica profilo coach dedicata
- [ ] Sezione squadra attuale + storico (da `Membership` ruolo HEAD_COACH)
- [ ] Sezione partite dirette (aggregazione da `Match`)

---

## 6. Pagina profilo pubblica dei presidenti / dirigenti

Stato: 🔄 In corso

Anagrafica, società, ruolo.

### 6.1 Modello

- [x] `PresidentProfile` 1:1 con `User`, creato via signal `post_save`

### 6.2 Vista pubblica

- [ ] Pagina pubblica profilo presidente/dirigente
- [ ] Sezione società di riferimento e ruolo

---

## 7. Pagina profilo pubblica dei fan/genitori

Stato: ⏳ Da fare

Profilo base, atleti seguiti, storico partite seguite.

### 7.1 Modello

- [ ] `FanProfile` 1:1 con `User` (oggi `User.role=fan` non ha profilo dedicato)
- [ ] Relazione "atleti seguiti" (es. genitore → figlio atleta)
- [ ] Tracking "storico partite seguite"

### 7.2 Vista pubblica

- [ ] Pagina pubblica profilo fan/genitore
- [ ] Sezione atleti seguiti
- [ ] Sezione storico partite seguite

---

## 8. OCR — Perfezionamento e affidabilità

Stato: 🔄 In corso

Miglioramento accuracy, preprocessing, gestione errori, dataset test, qualità dati estratti.

### 8.1 Pipeline esistente

- [x] Provider astratto (`vision_providers.py`), GPT-4V in prod, mock in test
- [x] Quality gate (`ocr_quality_gate.py`) pre-EXTRACTED
- [x] Dedup via SHA-256 (`hash_service.py`)
- [x] Raw response salvata (`OCRRawResponse`) per audit
- [x] Workflow stati referto completo (UPLOADED → PROCESSING → EXTRACTED → VALIDATED → PUBLISHED + branch NEEDS_REVIEW/REJECTED)

### 8.2 Affidabilità da migliorare

- [ ] Dataset di test con referti reali rappresentativi (accuracy baseline misurabile)
- [ ] Gestione multi-page PDF: concatenazione pagine prima dell'estrazione
- [ ] Metriche qualità: success rate per campo, tempo medio upload→publish
- [ ] Cluster E KO residui — guardia early-return in `ocr_service.py:254` che cortocircuita exception path per NEEDS_REVIEW
- [ ] Cluster D KO residui — verifica `MatchReportUploadForm.clean()` interroga davvero `MatchReport.objects.filter(file_hash=…)`

---

## 9. Sistema sponsor

Stato: 🔄 In corso

Sponsor associati a società/campionati, visualizzazione pubblica, modello dati dedicato (non solo JSONField).

### 9.1 Modello dati

- [x] `Society.sponsors` come `JSONField` flat (`[{"name", "logo_url"}]`)
- [ ] Modello `Sponsor_Assets` separato (blueprint §10, §13)
- [ ] Placement (pagina società, profilo atleta, footer)
- [ ] Targeting per stagione
- [ ] Test serializzazione sponsor (oggi nessuna copertura — FEATURE_STATUS Coverage Gaps)

### 9.2 Visualizzazione pubblica

- [ ] Render sponsor su pagina società
- [ ] Render sponsor su footer/profilo atleta secondo placement

---

## 10. Subscription e piani (three-tier)

Stato: 🔄 In corso

Implementazione Freemium / Premium / Club Pro come da blueprint §6. Attualmente solo INACTIVE/ACTIVE.

### 10.1 Modello dati

- [x] `User.subscription_status` con valori INACTIVE/ACTIVE
- [x] `User.subscription_end_date`
- [ ] Modello `Subscription` separato (non più 2 CharField su `User`)
- [ ] Enum FREEMIUM / PREMIUM_USER / CLUB_PRO

### 10.2 Wiring pagamenti e gating

- [ ] Integrazione provider pagamenti (Stripe o PayPal)
- [ ] Gating feature server-side per piano (Chatbot, Live Alerts, Media upload, Recap PDF)
- [ ] Pricing definitivo Premium Utente e Club Pro (bloccato — validazione product owner)
- [ ] Modello revenue projection (stima ricavi annui per piano)

---

## 11. Media Gallery e AI Tagging

Stato: ⏳ Da fare

Upload foto/video partite, tagging automatico giocatori con AI, visualizzazione pubblica. Solo Premium per upload.

### 11.1 Modello e storage

- [ ] Modello `Media` associato al match
- [ ] Storage su bucket + CDN, lifecycle policy
- [ ] Upload gated Premium

### 11.2 AI tagging

- [ ] Pipeline face detection
- [ ] Match automatico con roster ufficiale del match
- [ ] Coda di review manuale (semi-automatica per evitare mis-tagging)

### 11.3 Privacy

- [ ] Opt-in genitore obbligatorio per minorenni (GDPR)
- [ ] Opt-out atleta sempre disponibile
- [ ] Decisione moderazione: segnalazione automatica vs dashboard manuale Club Admin (pendente)

### 11.4 Visualizzazione pubblica

- [ ] Gallery pubblica per match con foto/video taggati

---

## 12. Live Alerts e notifiche push

Stato: ⏳ Da fare

Notifiche push per risultati live, variazioni orario, convocazioni. Gated Premium.

### 12.1 Infrastruttura

- [ ] Service worker e registrazione device
- [ ] Channel per match
- [ ] Gating Premium server-side

### 12.2 Trigger

- [ ] Trigger su transizioni `MatchReport` (gol live, fine periodo, fine partita)
- [ ] Trigger su variazioni convocazione (`Convocation`)
- [ ] Trigger su variazioni orario partita

### 12.3 Preferenze utente

- [ ] Preferenze per categoria alert (solo squadra propria, solo match con figlio, ecc.) — collegato a User Preferences

---

## 13. Season Archive e Season Recap PDF

Stato: 🔄 In corso

Archivio stagioni chiuse, generazione PDF riepilogo stagione. Recap PDF gated Premium.

### 13.1 Archivio stagionale

- [x] Modello `SeasonArchive` con snapshot JSON statistiche atleti e squadre
- [x] Vista archivio in `seasons/views.py`
- [x] Gestione manuale stagioni via admin

### 13.2 Generazione PDF Recap

- [ ] Generatore PDF Season Recap (atleta + squadra), gated Premium
- [ ] Template grafico (cover, stats principali, highlights, footer sponsor)
- [ ] Opzione colori squadra opt-in
- [ ] Distribuzione asincrona via email/dashboard (coda batch, non on-demand)
- [ ] Decisione privacy minori: opt-in per generazione o solo per condivisione (pendente)

---

## 14. Referto digitale mobile (Jury App)

Stato: ⏳ Da fare

App/interfaccia mobile per arbitri/giuria. Jury Tokens, firma PIN, offline-first. Convergenza JSON con OCR su `schema_version: 2.0`.

### 14.1 Ruolo e identità giuria

- [ ] Decisione: aggiungere `jury` all'enum `User.role` (oggi: athlete/coach/referee/fan/president) oppure sotto-ruolo di referee
- [ ] Migrazione DB e backfill utenti esistenti

### 14.2 Jury Tokens

- [ ] Modello `JuryToken` (match-specific, `user_id` + `match_id`)
- [ ] Finestra validità 30 min pre-match
- [ ] Revoca automatica al fischio finale
- [ ] Revoca manuale admin
- [ ] Endpoint emissione token `POST /api/jury/token/issue`
- [ ] Decisione "chi emette" — federazione, lega o club (pendente, bloccante)

### 14.3 Form Referto Digitale mobile

- [ ] UI mobile compilazione referto (Base + Avanzato)
- [ ] Sync offline-first
- [ ] Conflict resolution sync multi-device (policy pendente)

### 14.4 Firma arbitro

- [ ] Firma PIN arbitro a fine gara
- [ ] Immutabilità referto firmato (hash/lock sul `MatchReport`)
- [ ] Correzioni post-firma solo via admin con audit log completo

---

## 15. Stabilità tecnica — test suite e debito

Stato: ⏳ Da fare

KO residui sulla test suite e debiti tecnici aperti.

### 15.1 Cluster KO residui

- [ ] Cluster A — Public API legacy behavior (3 KO): endpoint `api_league_list` e `api_team_detail` rimossi, chiave `name`→`full_name`. Richiede decisione backward-compatibility
- [ ] Cluster D — dedup logic (1 KO): verifica `MatchReportUploadForm.clean()` post-fix `f3179c1`
- [ ] Cluster E — OCR service no-file guard (3 KO): guardia early-return in `ocr_service.py:254` che cortocircuita NEEDS_REVIEW
- [ ] Cluster I — reconciliation blocker: verifica auto-risoluzione test 22 post Policy A (`c787b11`)
- [ ] Recount KO post-fix 10-mag (`a9ca246` audit trail + `b97e9e5` event types refactor)

### 15.2 Debiti aperti

- [ ] Bug slug `pallanuotopallanuoto` (Sport #6) — slug duplicato/concatenato
- [ ] Stats incoerenti `mrossi_test` — discrepanza `AthleteProfile.total_goals` vs `MatchEvent`
- [ ] Lista B audit utenti/società di test (admin_test_v2, Pro Recco Test, ecc.)
- [ ] Ridurre superuser di test da 5 a 1–2
- [ ] Fix `rebuild_standings` exit code (esce 0 anche su errore — OPS_RUNBOOK §3.6)

### 15.3 Decisione DB

- [ ] Decisione timing migrazione SQLite → PostgreSQL (concurrent writes, scala futura)
- [ ] Procedura dump/restore documentata e testata
- [ ] Test suite su PostgreSQL (verifica nessuna dipendenza da sfumature SQLite)

---

## Legenda

- ✅ Completato — tutti i task sono [x]; il blocco verrà rimosso nella sessione successiva
- 🔄 In corso — almeno un task [x] e almeno uno [ ]
- ⏳ Da fare — nessun task ancora iniziato
