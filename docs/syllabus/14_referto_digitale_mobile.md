## 14. Referto digitale mobile (giuria)

Stato: 🔄 In corso (sbloccata 2026-07-19 — vincolo federale noto e aggirato per design; era 🧊 dal 2026-06-02)

Interfaccia web mobile con cui la giuria compila il referto al posto del cartaceo. Accesso via **link monouso per-partita** (nessun account, nessuna app da installare), offline-first, convergenza JSON con OCR su `schema_version: 2.0`.

> **Sblocco (2026-07-19) — risposta federale, verificata con contatto diretto.** Le designazioni delle giurie sono gestite dal **GUG, organo NAZIONALE**; vengono comunicate **via mail attraverso il portale federale**; il portale **non sarà reso accessibile a terzi** perché gestisce i dati personali dei tesserati FIN. Il modello Jury Token (BLUEPRINT §7.4.1 pre-2026-07-19: token `match_id`+`user_id` emesso dalla federazione/lega) presupponeva la FIN come autorità emittente e l'accesso a un'anagrafica tesserati che non avremo mai: **irrealizzabile, non emendabile** — archiviato in [FUTURE_IDEAS.md §1](../FUTURE_IDEAS.md). Il modello che lo sostituisce identifica la **PARTITA, non la persona** (§14.2). La macro quindi **non è più differita per dipendenza esterna**: il vincolo è noto e aggirato per design, si può progettare e costruire. Prossimo canale FIN: segreteria generale (mail in programma, non ancora inviata) — rileva solo per l'open question sulla consegna del link.

### 14.1 Identità giuria — decisione precedente SUPERATA

- [x] ~~Nuovo valore enum `jury` in `User.role`~~ — **SUPERATA (2026-07-19)**: nel modello a link monouso la giuria **non ha account** e non serve alcun ruolo utente per il flusso di compilazione. Il gap "ruolo jury" registrato in Macro 15 resta rilevante solo se un ruolo giuria servisse per altri scopi (oggi nessuno individuato).

### 14.2 Accesso — link monouso per-partita (riscritta 2026-07-19, sostituisce "Jury Tokens")

Decisioni di prodotto **RATIFICATE 2026-07-19**:

- [x] **Modello di accesso: link monouso per-partita.** Il link è legato alla sola partita; chi lo apre trova il referto già precompilato con squadre, data e luogo (la precompilazione da `Match` esiste già in `api_digital_report_start`). Nessun account, nessuna registrazione, nessuna app da installare, **nessun dato personale della giuria raccolto**.
- [x] **Durata: il link vive finché il referto non viene chiuso/firmato; alla chiusura muore.** Backstop assoluto di sicurezza: scadenza comunque **7 giorni dopo la generazione**, per evitare link vivi all'infinito su referti mai chiusi. *(Il backstop 7 giorni è un'aggiunta di Alberto in sede di ratifica, non una richiesta esplicita emersa dal confronto federale.)*
- [x] **Sicurezza: nessun secondo fattore in v1.** Chi ha il link può compilare. Razionale: ogni attrito aggiunto uccide l'adozione con una giuria a bassa alfabetizzazione digitale (feedback §14.5); il rischio su una singola partita è basso; il danno peggiore (referto sbagliato) è già intercettato dal quality gate e dalla review admin (il close entra in `NEEDS_REVIEW`, mai auto-publish — verificato a codice). Un **codice breve a 4-6 cifre resta PREDISPOSTO nel design ma SPENTO**: si attiva solo se emergesse un abuso reale.
- [ ] **OPEN QUESTION — consegna del link (da decidere con la FIN, NON scegliere ora).** Ipotesi sul tavolo: (a) QR code stampato/consegnato dalla società ospitante a bordo vasca; (b) link incluso nella mail di designazione GUG. Canale: segreteria generale FIN (mail in programma).

**Cosa decade del modello precedente** (mai implementato — nessuna riga di codice): modello `JuryToken` (`match_id`+`user_id`, issuer federazione/lega), endpoint `POST /api/jury/token/issue` (ripensato in emissione piattaforma-side, v. BLUEPRINT §11), finestra di validità 30 min pre-match e revoca automatica al fischio finale (sostituite da vita-fino-a-chiusura + backstop 7 giorni; resta la revoca manuale admin).

### 14.3 Form Referto Digitale mobile (invariata nella sostanza)

- [x] Workflow `DRAFT → NEEDS_REVIEW → (ramo review) → VALIDATED → PUBLISHED` per `source_channel=DIGITAL` — **verificato a codice 2026-07-19**: `api_digital_report_close` chiude in `NEEDS_REVIEW` (coda review) con audit log e guardie di idempotenza su update e close (17 test as-is in `tests_digital_referto.py`, commit `5ff6d11` + fix `03d3860`). La nota doc-vs-codice del 2026-06 è risolta: la convergenza con l'OCR avviene sul ramo review, non con salto diretto a VALIDATED.
- [x] REST CRUD draft digitale in `api_views_digital.py` + routing `api_urls.py`
- [ ] UI mobile compilazione referto (solo livello Base; Avanzato accantonato 2026-07, vedi §14.5)
- [ ] Sync offline-first (Service Worker + IndexedDB — stesso mattone tecnico della Macro 21 PWA)
- [x] **Decisione PRESA (invariata):** conflict resolution = **single-writer lock per match** (NON last-write-wins, NON merge field-level). Handover-on-failure = dettaglio implementativo aperto, da definire in fase implementazione.

### 14.4 Chiusura, firma e immutabilità

- [x] **Immutabilità post-chiusura (principio invariato, già de facto a codice):** fuori da `DRAFT`, update e close vengono rifiutati (400, `test_double_close_rejected`); correzioni post-chiusura solo via admin con audit log completo.
- [x] **Firma arbitro = nome e cognome digitati al close (DECISA 2026-07-19, as-built).** Il PIN *personale* è decaduto: presupponeva un'identità registrata che nel modello no-account non esiste. Al close del canale digitale è ora obbligatorio un campo firma **nome+cognome** (validazione: ≥2 token), persistito su `MatchReport.referee_signature` e nell'audit log (`after.referee_signature`) con timestamp. Il **codice breve 4-6 cifre resta predisposto-ma-spento come anti-abuso** (§14.2), **NON come firma**: i due concetti non vanno mescolati (zero codice in questo giro). Test: `test_close_requires_signature`, `test_close_rejects_signature_without_surname`, `test_close_valid_payload_transitions_to_needs_review`.

### 14.5 Aggiornamento 2026-07 (contatto federale) — integrato 2026-07-19

- Contatto federale stabilito alle finali nazionali U18 (2026-07); **risposta ricevuta il 2026-07-19** (vedi nota di sblocco in testa).
- **Feedback giuria (invariato, ora centrale):** il problema principale non è la compilazione ma la **distribuzione e l'accesso** — età media della giuria alta, molti non usano dispositivi elettronici. Il modello a link monouso (+ ipotesi QR a bordo vasca) è la risposta diretta a questo feedback.
- ~~Open question sull'identificativo federale (badge/tessera/numero ID)~~ — **chiusa negativamente 2026-07-19**: nessun accesso all'anagrafica federale (vedi nota di sblocco). Resta aperta solo la consegna del link (§14.2).
- **Livello statistiche Avanzato accantonato** (invariato): resta il solo livello Base; idea conservata in [FUTURE_IDEAS.md](../FUTURE_IDEAS.md) §1.

### 14.6 Cosa servirà a codice (lista per il giro di build — NON design dettagliato)

- Modello del link per-partita (proposta: `MatchJuryLink`): FK a `Match`, token URL-safe generato server-side, stato (attivo/consumato/revocato), `expires_at` (backstop 7 giorni), campo predisposto per il codice breve (spento). Migration additiva.
- View pubblica di compilazione **senza login** via token nel path: i tre endpoint digitali esistenti sono `@login_required` + `_check_digital_report_permissions` (staff/referee/superuser) — il canale pubblico li **affianca**, non li sostituisce, riusando la precompilazione di `api_digital_report_start` e il CRUD esistente, vincolato al solo referto della partita del link.
- Aggancio del ciclo di vita: consumo/morte del link alla transizione `DRAFT → NEEDS_REVIEW` di `api_digital_report_close`; revoca manuale admin.
- Generazione QR del link (necessaria per l'ipotesi (a) di consegna; utile in entrambe).
- Emissione: endpoint/azione staff per generare il link di una partita (proposta BLUEPRINT §11: `POST /api/matches/{id}/jury-link`).
- Igiene anti-enumerazione: token lungo non indovinabile + throttling sugli accessi falliti (non è un secondo fattore, è igiene minima).

### 14.6-bis As-built — fondamenta backend (giro 2026-07-19)

Costruito e verde (49 test dedicati; suite intera 561 OK). La **view pubblica di compilazione (UI), il QR e l'offline-first restano fuori scope** (giri futuri).

- **Modello `MatchJuryLink`** (in `matches/models.py`): FK `match`, `token` (secrets, `token_urlsafe(32)`, unique+index), `status` (`ACTIVE→CONSUMED/REVOKED/EXPIRED`, nessun ritorno), `created_by` (SET_NULL), `created_at`, `expires_at` (= created + 7gg), `revoked_at`, `consumed_at`, `report` (SET_NULL, valorizzato al consume). **Un solo ACTIVE per match** garantito da un partial unique index (`UniqueConstraint(fields=['match'], condition=Q(status='ACTIVE'))` — SQLite supporta indici parziali), rinforzato dal service che revoca in transazione il precedente. Migration additiva `0018`.
- **Service `JuryLinkService`** (`matches/services/jury_link_service.py`): `issue` (revoca precedente + crea), `revoke`, `resolve` (ACTIVE + non scaduto; **scadenza valutata a lettura**, degrada lazy a `EXPIRED`; niente cron), `consume`, `active_for_match`.
- **Firma al close** = nome+cognome digitati, obbligatoria, su `MatchReport.referee_signature` + audit (§14.4).
- **Emissione/revoca**: `POST /api/matches/{id}/jury-link/` e `.../revoke/`, gate `_check_digital_report_permissions` (staff digitale/admin). ⚠️ **Il RBAC non è society-scoped**: `staff_role` è globale, quindi "staff della società del match" non esiste come gate; scelto il gate esistente più coerente e restrittivo. Vera scoping per-società = debito futuro. Risposta neutra rispetto al canale: fornisce l'URL `/r/{token}`, **nessun QR generato**.
- **Accesso via token** su start/update/close (`api_views_digital.py`): l'anonimo con token ACTIVE valido per QUEL match affianca l'utente autenticato (path autenticato **intatto**); nessun account creato, `uploader=None`, ogni azione via link tracciata in audit con `user=None`.
- **Ciclo di vita agganciato al close**: transizione referto `DRAFT→NEEDS_REVIEW` e link `→CONSUMED` **atomici** (`transaction.atomic`); consume solo su close **riuscito**; guardia idempotenza `03d3860` preservata. Un close autenticato consuma comunque l'eventuale link ACTIVE pendente sul match.
- **Landing `GET /r/{token}`**: risoluzione minima JSON (match/bozza) — valido 200, scaduto/revocato/consumato 410, inesistente 404. **Nessuna UI.**

---

← [Macro precedente](13_season_archive.md) | → [Macro successiva](15_stabilita_tecnica.md)
