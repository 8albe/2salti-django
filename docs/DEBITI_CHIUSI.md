# DEBITI CHIUSI — Archivio

Archivio dei debiti chiusi. Le voci arrivano qui da [DEBITI.md](DEBITI.md) (o storicamente da OPS_RUNBOOK) alla chiusura, con ID originale, data di chiusura e riferimenti (commit, session note).

> Provenienza (riorganizzazione doc 2026-07-22): le voci §10.1–§10.16 — più una voce cosmetica non numerata — arrivano dalla ex "Appendice A — Archivio debiti e fragilità risolti" di [OPS_RUNBOOK.md](OPS_RUNBOOK.md); le voci §10.17, §10.19, §10.23 e §10.29 dalla ex sezione "10. Debiti aperti". Niente è cancellato: ogni voce conserva cosa era, come è stata chiusa e dove vive nel codice/test; il dettaglio blow-by-blow resta recuperabile da git e dalle session note. Gli identificatori §10.x sono preservati perché OPS_RUNBOOK (§2.3 fra gli altri), la voce §10.5 e vari doc di syllabus vi puntano. Questo file vive in `docs/` come il runbook, quindi i link relativi (es. `../matches/...`, `ZERO9_DEFERRED.md`) restano validi.

### §10.1 Report PUBLISHED con blocker quality gate — CHIUSO 2026-05-02
*Cosa era:* 4 `MatchReport` PUBLISHED con `created_events_count=0` e `score>0`
(stat atleti a zero, classifiche corrette perché calcolate da `match.score`, non
dagli eventi); causa OCRQualityGate half-shipped + drop silenzioso di eventi senza
`player_id` riconciliato in `publishing_service.py`.
*Chiuso:* Policy A strict (commit `c787b11`) — `schema.py` conta solo eventi con
`player`/`player_name` valorizzato; `publishing_service.py` fa `set_rollback(True)`
se `created_events_count==0 & score>0` anche con `force=True` (audit
`action='abort_zero_events'`). I 4 referti esistenti revertati PUBLISHED→NEEDS_REVIEW
(id 7,8,10,11) da Alberto.
*Vive in:* `matches/services/schema.py`, `publishing_service.py`.
*Residuo prodotto (aperto):* se un revert dovesse togliere anche il punteggio dalla
classifica serve modifica a `standings_service` — decisione rinviata.

### §10.2 Audit trail non visibile nella review page admin — CHIUSO 2026-05-10
*Cosa era:* la review page admin non mostrava le entry `MatchReportAuditLog` pur
presenti nel DB (zero impatto funzionale, solo visibilità reviewer).
*Chiuso:* commit `a9ca246` — aggiunta query `report_audit_logs` nel context di
`review_view()` + scritture audit `review_opened`/`save_draft`/`validate`; il
blocco template esisteva già (classico "1,2,4 senza 3", §3.11).
*Vive in:* `matches/admin.py`, `templates/admin/matches/matchreport/review.html`.

### §10.3 EXTENDED_EVENT_TYPES non allineato a event_types.py — CHIUSO 2026-05-10
*Cosa era:* whitelist parallela in `schema.py` non derivata dall'autorità centrale
`event_types.py`; un `EXCLUSION_BRUTAL` passava il validator ma non veniva conteggiato
da stats/match detail.
*Chiuso:* commit `b97e9e5` — event types ridotti ai 5 canonici (GOAL, EXCLUSION_20,
YELLOW_CARD, RED_CARD, TIMEOUT) + OTHER catch-all; eliminato `EXTENDED_EVENT_TYPES`
(codice morto), allineati prompt OCR e consumer.
*Vive in:* `matches/services/schema.py`, `vision_providers.py`.

### §10.4 Membership senza start_date/end_date — CHIUSO Sprint C (2026-05-27/28), poi superato da Macro 16
*Cosa era:* `Membership` senza intervallo di tenure → storico coach ordinabile solo
per `created_at`, partite dirette non filtrabili per periodo.
*Chiuso (Sprint C):* aggiunti `start_date`/`end_date` + `MembershipQuerySet.active_at(date)`
+ filtro temporale su `coached_matches`/`direct_matches` (commit `0f6ca64`, `6e0243e`,
`0eeff1a`, `0db9307`, `cbb1491`).
*Superato:* Macro 16 Fase 2 ha **rimosso** `start_date`/`end_date` da `Membership`
(migration `management/0014`); l'asse temporale è ora la FK `season` (NOT NULL dalla
`0015`). I follow-up sono confluiti in §10.6.
*Vive in:* `management/models.py` (storico in git), `accounts/views.py`,
test `management.tests_membership_dates`, `accounts.tests_temporal_views`.

### §10.5 Pulizia utenti/società di test su prod — CHIUSO 2026-07-06 (verificato via recon read-only)
*Cosa era:* inventario aperto dal 26-mag 2026 (Sprint B) su utenti/società di test
residui su prod, mai verificato con accesso VPS diretto; il 2026-07-05 (Task 4) ne
era stata affrontata la sola parte bot-signup (27 husk id 61–89 cancellati via
`cleanup_bot_users.py`), lasciando aperta la domanda sull'inventario più ampio e sul
sospetto di bot nati dopo il backup delle 19:12 (id ≥ 90).
*Chiuso:* Risolto/verificato il 2026-07-06 via recon read-only su prod: inventario
test users/società di fatto pulito — nessun utente di test orfano (59 utenti = 1
admin + 58 seed pilota con legami reali), 13 società tutte league-wired, nessuna
shell di test. La premessa "bot id ≥ 90" era infondata: nessun id sopra 60 esiste nel
DB (`max(id)=60`), DB fermo dal 2026-07-05 19:14. Vettore signup storicamente
abusato (27 husk id 61–89 già rimossi il 2026-07-05); rate-limit tracciato
separatamente e poi implementato il 2026-07-06 (vedi §10.16 in questa appendice).
*Vive in:* nessun codice toccato — verifica read-only via query ORM su venv prod
(`accounts.User`, `management.Membership`, `core.Society`); comando di riferimento
`core/management/commands/cleanup_bot_users.py` (dry-run confermato "niente da
fare" il 2026-07-06, i 27 id già assenti). Evoluzione scanner-by-signature del
command: DIFFERITA per decisione 2026-07-06 — resta a lista fissa (`DEFAULT_BOT_IDS`,
id ≤ 89); trigger di riapertura e razionale in [ZERO9_DEFERRED.md](ZERO9_DEFERRED.md)
§4, voce "Pulizia account bot sul signup prod".

### §10.6 Debiti residui post-Sprint C (BUG-001, DEBT-001/002/003/004) — CHIUSI 2026-06-19
*Cosa era:* cinque item tracciati durante Sprint C, non bloccanti.
- **BUG-001** — 500 su `base.html` con sport a 0 leghe (`VariableDoesNotExist` su
  `sport.leagues.first.slug`, il `|default` non protegge). **Chiuso (Sprint D, commit
  dev `5eaab746`):** guard `{% if sport.leagues.exists %}` in `templates/base.html`;
  regression `core/tests_navbar.py`.
- **DEBT-001** — `unique_together (user,society,team,role)` bloccava il rientro storico.
  **Chiuso (assorbito Macro 16):** sostituito da `UniqueConstraint(user,society,team,role,
  season)` → rientro in stagione diversa = riga distinta, stessa stagione resta bloccata.
  No codice. Test `management/tests_membership_debts.py::Debt001CrossSeasonReentryTests`.
- **DEBT-002** — dual-role coach: `sync_coach_membership` hardcodava `HEAD_COACH` e
  fabbricava una HEAD_COACH spuria a un coach solo-assistant. **Chiuso rendendo il signal
  role-aware** (deriva i ruoli coach dalle membership attive e sincronizza ciascuno in
  isolamento; HEAD_COACH e ASSISTANT_COACH coesistono; default HEAD_COACH se nessuna
  membership coach pregressa). **Nessuna 2-FK su `CoachProfile`, nessun cambio schema.**
  Test `Debt002DualRoleCoachTests`.
- **DEBT-003** — `Membership` con `end_date < start_date`. **Chiuso poi RITIRATO:**
  `CheckConstraint membership_end_date_after_start` (migration `0009`, commit `068ec8e`)
  decaduto quando Macro 16 Fase 2 (`management/0014`) ha rimosso le date.
- **DEBT-004** — race redeem/approve su stesso user. **Chiuso con limitazione:**
  `select_for_update()` difensivo in `approve_membership` e `redeem_activation_code`,
  e transizione-stato + creazione Membership rese un'unica unità atomica (prima la
  Membership poteva restare orfana). La race in sé NON è falsificabile su SQLite
  (write serializzati, `select_for_update` no-op); fix valido per PostgreSQL prod. Il
  test copre il sub-bug di atomicità in modo deterministico. Test `Debt004ApproveAtomicityTests`.
*Vive in:* `management/models.py` (signal `sync_coach_membership`), `management/services`
(approve/redeem), `templates/base.html`, `management/tests_membership_debts.py`.

### §10.7 Fragilità test migration Macro 16 (leaf hardcoded) — CHIUSO 2026-06-19
*Cosa era:* `core/tests_migrations_season.py` pinnava il leaf `accounts@0005_staff_role_pii`
in `project_state`; poiché accounts non viene retrocessa e resta al leaf fisico, la prima
migration accounts non-additiva avrebbe spostato il leaf lasciando il modello storico a
0005 → mismatch schema → lockstep manuale test↔migration a ogni migration. Introdotto Fase
1b (commit `c7cef79`, 2026-06-09); lockstep manuale applicato il 2026-06-11 (Fasi 2-4).
*Chiuso:* reso **leaf-agnostic** — il leaf accounts è risolto a runtime via
`loader.graph.leaf_nodes("accounts")` (helper `_current_leaf`, assert leaf unico). Stessi
assert, ma il test segue il leaf da solo: nessuna migration accounts futura tocca più il
test. NO-SCHEMA, test-only.
*Anchor intenzionali (non debito):* i pin `core@0008`/`core@0010` (pre/post-bonifica) e
`management@0009` (rewind imposto da `management/0010+ → core.Season`) NON sono leaf ma
anchor storici semantici → restano hardcoded di proposito (management 0014→0016 senza rotture).
*Vive in:* `core/tests_migrations_season.py::SeasonBonificaMigrationTest` (5 test); suite
core/accounts/management 177/177.
*Aggiornamento 2026-07-05:* anche il leaf di GRAFO si rompe se una migration accounts dipende
da una core recente (accounts/0012 → core/0025): il pin trascina core in avanti nel modello
storico mentre il rewind ha retrocesso lo schema ("no column named is_comped", 12 test).
Sostituito `_current_leaf` con `_applied_leaf`: pin all'ultima migration accounts ancora
APPLICATA dopo il rewind (verità fisica dal recorder) — coincidenza modello↔schema per costruzione.

### §10.8 Macro 16 — propagazione prod — CHIUSO 2026-06-12
*Cosa era:* Macro 16 chiusa su `dev`/dev-box ma prod `/opt/2salti-new/` a `01427d59` senza
codice né migration; propagazione da fare via pattern §2.3 (no SHA prod-local), history `dev`
riscritta con `git-filter-repo`.
*Chiuso:* merge `--no-ff` dev→master da home + push; deploy su prod via `git fetch` +
`git reset --hard origin/master` (NO pull). Backup DB pre-migrate; 21 migrazioni applicate
(numeri identici al dry-run); smoke `ops_check --mode afternoon` GREEN, HTTP/2 200.
*Nota:* allo step 3 prod risultava "ahead by 54 commits" (lineage prod-local §2.3), non HEAD
orfana pura; il `reset --hard` ha riagganciato correttamente.

### §10.9 Certificato SSL 2salti.com — CHIUSO 2026-06-14 (verificato 2026-06-19)
*Cosa era:* certificato scaduto (curl senza `-k` falliva), scoperto allo smoke post-Macro 16;
non legato al deploy. Causa-radice: `certbot.timer` Dummy.
*Chiuso:* `certbot renew` + automazione via `/etc/cron.d/certbot-2salti` scoped ai domini di
Alberto; verificato con `openssl s_client`/`x509 -dates` (valido 2026-06-14 → 2026-09-12,
Let's Encrypt). Il `curl -k` in diagnosi era prudenza superflua.

### §10.10 Loop onboarding presidente self-service (PROD) — CHIUSO 2026-06-21
*Cosa era:* `create_society` non in `allowed_urls` del middleware onboarding
(`accounts/middleware.py`): un presidente in `MEMBERSHIP_PENDING` (società non ancora
creata) veniva rediretto a `onboarding_membership` → `ERR_TOO_MANY_REDIRECTS`. Sistemico,
pre-esistente, su **prod**. Scoperto 2026-06-20.
*Chiuso:* deploy `f697c0f` su prod (merge `dev`→`master` `--no-ff`); 3 migration applicate
`[X]`, backfill 7/7 `FanProfile` = dry-run, gunicorn sano, smoke pubblico GREEN. Commit
chiave: `e4f1efc` (`create_society` aggiunto alla whitelist del middleware) + `08f8830`
(presidente de-vincolato da `Membership` PRESIDENT, RBAC derivato da `managed_society`); i
3 fix bacheca emersi in verifica `50e3396`/`17edacc`/`6a42763`.
*Nota onesta:* riprova autenticata su prod (login presidente `managed_society`-only) **non
eseguita di proposito**, per non creare account fittizi su produzione. Comportamento
verificato end-to-end su dev (Antigravity Check 1–3, sessione 2026-06-20); codice in prod
bit-identico a dev (tree del merge identico, suite 221 verde sul merge di prova). Riprova
demandata al primo login reale di un presidente. Per §5 è una chiusura solida proprio
perché dichiara il suo unico angolo non coperto: chi rilegge il runbook non deve dedurre
"verificato col login in prod" — la verità è dev verde + codice identico, riprova al primo
presidente reale.
*Vive in:* `accounts/middleware.py` (whitelist onboarding), `management/services` (RBAC da
`managed_society`); regression suite `management` 126 GREEN su dev.

### §10.11 `_society_recipients` — candidato debito INVESTIGATO, no-bug — CHIUSA 2026-06-21
*Cosa era:* sospetto (test 7b) che la notifica vouching alla società non fosse recapitata
perché `getattr(society, 'president', None)` puntava a una relation inesistente.
*Chiusa (no-bug):* `society.president` è il reverse OneToOne di
`PresidentProfile.managed_society` (`related_name='president'`); in questo Django
`RelatedObjectDoesNotExist` è sottoclasse di `AttributeError`, quindi `getattr(..., None)`
ritorna `None` senza sollevare. `_society_recipients` ritorna `[society.email]`,
`[president.user.email]` o `[]` correttamente. **Nessun bug**: il sintomo reale è assorbito
da §10.12 (SMTP non configurato), non da un difetto di codice.
*Chiusura by-design (implementato e verificato e2e su `dev`, non ancora in prod):* il caso `[]` (notifica muta) per una società personificata è eliminato alla radice dal setup di personificazione presidente, che rende **obbligatoria** l'email società (BLUEPRINT §7.2 / §7.7; SYLLABUS Macro 18).

### §10.12 SMTP non configurato — CHIUSO 2026-06-21 (dev console + prod Brevo)
*Cosa era:* `EMAIL_BACKEND=smtp` su `localhost:25` senza server → le email best-effort
(incluse vouching/certificazione) saltavano silenziosamente (gestite via `_safe_send`,
nessun recapito). Causa reale del sintomo "notifica società non arrivata" (test 7b, vedi §10.11).
*Chiuso in due tempi:*
- **Lato-dev** (`baa69b3`, su prod con deploy `f697c0f`): `EMAIL_BACKEND` console di default
  in dev, env-gated fail-safe.
- **Lato-prod** (2026-06-21): migrazione da Gmail App Password → **Brevo SMTP**. Prod spedisce
  via `smtp-relay.brevo.com` da `noreply@2salti.com`, dominio `2salti.com` autenticato
  (SPF/DKIM/DMARC su Aruba: TXT `brevo-code`, CNAME `brevo1`/`brevo2` `_domainkey`, TXT `_dmarc`,
  TXT SPF). Verificato con test reale: consegna in inbox confermata. La certificazione genitore
  ora recapita davvero in produzione.
*Rotazione credenziali:* via §11.1 (Brevo SMTP key in `.env`, mai in chat/log).

### §10.13 API `/accounts/api/...` fuori whitelist onboarding — CHIUSO 2026-06-21
*Cosa era:* l'esenzione middleware `request.path.startswith('/api/')` non copriva gli
endpoint AJAX accounts sotto `/accounts/api/...` (`search-athlete` e simili) → intercettati
durante onboarding e rediretti (HTML invece di JSON). Pre-esistente, scoperto 2026-06-20.
*Chiuso:* `/accounts/api/` aggiunto alla whitelist del redirect middleware (commit
`04cc484`); su prod con deploy `f697c0f`.

### Cosmetico — tag `{{ }}` template spezzati su due righe — CHIUSO 2026-06-21
*Cosa era:* 10 tag di template `{{ ... }}` spezzati su due righe (refuso cosmetico, **non**
una voce §10 tracciata) che rendevano letterale il markup in pagina.
*Chiuso:* 10 tag ricomposti su riga singola (commit `35ae324`); verificato in prod via HTTP
e Antigravity Test 2. Fix chiuso, non un debito residuo.

### §10.14 Git credential helper sul VPS — CHIUSO 2026-06-21 (diagnosticato + fragilità #1 mitigata)
*Cosa era:* sospetto che qualcosa "resettasse" `credential.helper` sul VPS condiviso facendo
fallire `git push` con 401, da cui la domanda "cosa resetta la config git". Premessa errata: vedi
diagnosi.
*Diagnosi (read-only, nessun segreto esposto):* il meccanismo attivo è `credential.helper=store`
(global, `/home/alberto/.gitconfig`) + PAT in chiaro in `~/.git-credentials` (perms `0600
alberto:alberto`), remote **HTTPS** `https://github.com/8albe/2salti-django.git` (URL pulito, nessun
token embeddato). Tutti e tre i repo (`/home/alberto`, `/opt/2salti-dev`, `/opt/2salti-new`) ereditano
lo stesso global, nessun override locale, nessun `url.insteadOf`. **"Niente 401" è il comportamento
NORMALE di `store`**, non un'anomalia: restituisce il token in modo non-interattivo. La voce originale
partiva da una premessa errata — non c'è nulla che resetti la config. (mtime di `~/.git-credentials` =
ultima auth riuscita, non una scrittura pre-deploy → il PAT preesisteva al deploy; chiave SSH
`id_ed25519_github_8albe` presente in `~/.ssh` ma non attiva, alternativa latente.)
*Mitigazione applicata (fragilità #1 — scadenza/revoca del PAT):* il token era un PAT **classic**
`2salti-hetzner-push` con scope `repo` (tutti i repo), scad. **20 lug 2026**; sostituito da un PAT
**fine-grained** limitato al solo `8albe/2salti-django` (**Contents: read/write**), scad. **21 giu 2027**.
Backup di `~/.git-credentials` in `~/.git-credentials.bak.20260621`, sostituita solo la stringa token
nella riga esistente (username `8albe` e struttura HTTPS invariati), perms `0600` riapplicati; `fetch`
di verifica **senza 401**; vecchio classic **revocato** su GitHub (esposizione scope-largo chiusa).
Meccanismo invariato (`store`/HTTPS/PAT in chiaro come `alberto`), ma token ora fine-grained single-repo.
*Fragilità residue (non debito, avvertenze permanenti):* #2 (deploy con utente ≠ `alberto`/HOME diverso
→ 401) e #3 (reset/cancellazione di `~/.git-credentials` → 401) sono ricollocate come trappola operativa
in **§3.13**. La mitigazione **SSH** (chiave già presente) resta opzionale, non implementata.
*Rotazione credenziali:* via §11.1.

### §10.15 Dependency superflua su migration già applicata su dev — CHIUSO 2026-07-05
*Cosa era:* `accounts/0012_unique_email_constraint` dichiarava `('core','0025_delete_orphan_sports')`
come dependency auto-generata da `makemigrations`, non reale (0012 tocca solo `accounts.User.email`).
*Nota:* `django_migrations` non persiste il grafo delle dependency, solo `(app, name, applied)` — non
c'è quindi un vero rischio "file dice una cosa, tabella un'altra" nel rimuovere una dependency su una
migration già applicata. Il rischio reale è sui TEST che rigiocano l'ordine (rewind/`_applied_leaf`,
§10.7): un cambio di grafo cambia quali app vengono trascinate da un rewind, va sempre riverificato.
*Procedura usata (dev, replicabile):* confermare che la migration è foglia (nessun `dependencies`/
`run_before` la referenzia) e che le `operations` non toccano l'app rimossa dal grafo; poi, come
validazione empirica del reverse (non strettamente necessaria per la tabella ma utile su dati reali):
unapply → verifica `--plan` (deve mostrare solo il reverse delle operations, nessuna cascata) → copia
locale del file nuovo → reapply con nuovo grafo → `git checkout --` per ripulire il working tree →
push + pull normale. Suite 478/478 e i 12 test `_applied_leaf` invariati dopo il cambio.
### §10.16 Rate-limit IP sul signup — IMPLEMENTATO 2026-07-06 (su dev, live al prossimo merge/deploy)
*Cosa era:* hardening differito, registrato il 2026-07-06: vettore signup pubblico
storicamente abusato (27 husk bot id 61–89 rimossi il 2026-07-05, dettaglio §10.5),
mitigato dal solo honeypot (`4aa48e7`); throttle IP-based pianificato ma non costruito.
*Chiuso:* implementato su dev (commit `ae0ecee`): cap **5 tentativi POST / 10 minuti
per IP**, sliding window di timestamp nella cache Django di default, chiave
`signup_throttle:<ip>` (IP da `X-Forwarded-For` col fallback `REMOTE_ADDR`, stessa
estrazione di `management.utils.log_action`). Errore soft: messaggio "Troppi tentativi
di registrazione. Riprova tra qualche minuto." + ri-render del form, mai un 500; reset
automatico a fine finestra (sliding). Nessuna migration, `config/settings.py` non toccato.
**Limite noto, accettato:** nessun backend `CACHES` configurato → LocMemCache di default,
contatore per-process: con N worker gunicorn il cap effettivo è fino a N×5 per IP.
Difesa-in-profondità (honeypot + verifica email restano indipendenti), non un hard gate;
si rivaluta solo se/quando comparirà una cache condivisa — nessuna nuova infra (no Redis)
introdotta per questo.
*Vive in:* `accounts/services/signup_throttle.py` (service, costanti cap/finestra),
`accounts/views.py::signup` (gate sul POST), test `accounts/tests_signup_throttle.py`
(6° tentativo bloccato, sblocco a finestra scaduta, honeypot indipendente dal throttle).

### §10.17 `2salti_nginx_config` fuori repo — CHIUSO 2026-07-19

~~La config nginx attiva vive solo su sistema (`/etc/nginx/`)~~ **Risolto:** copie canoniche versionate in `deploy/nginx/prod/2salti` e `deploy/nginx/dev/2salti-dev` (dettaglio §9), verificato testualmente che `prod/2salti` contenga `proxy_read_timeout 300s` (§3.16) nella location `/`. Il debito residuo non è più "config assente dal repo" ma il rituale di allineamento manuale repo↔sistema, stesso tema di §9 per systemd e gunicorn: una modifica fatta direttamente su `/etc/nginx/sites-available/` non si sincronizza da sola in repo. Il vecchio pattern `2salti_nginx_config` citato in `.gitignore`/`CLAUDE.md` resta un riferimento storico a un file mai esistito in questa copia del repo.

### §10.19 Nessuna guardia sui referti appesi in `PROCESSING` — CHIUSO 2026-07-19 (Macro 22 giro 2)

~~Se il worker muore a metà OCR il referto resta in `PROCESSING` per sempre: nessun recovery automatico, e la review queue non lo ripropone.~~ **Risolto** su dev dal giro 2 con due inneschi che condividono una sola regola: la sweep di avvio del worker (nessuna soglia — girando un solo worker, all'avvio ogni referto in `PROCESSING` è per definizione orfano) e il comando `recover_stale_reports` su timer ogni 15 minuti, che copre il caso che la sweep non vede: il worker fermo e basta, che quindi non si riavvia mai. Entrambi passano da `OCRQueueService.requeue_stale()`, quindi l'esito su un dato referto non dipende da chi lo recupera.

**La semantica implementata devia dallo sketch qui sopra, ed è la deviazione il punto.** Lo sketch prescriveva `PROCESSING` da più di N minuti → `NEEDS_REVIEW`, ed era scritto il mattino del 2026-07-19, quando non esistevano né worker né retry: mandare tutto in revisione umana era l'unica opzione disponibile. Col claim che incrementa `ocr_attempts` e il backoff introdotti nel giro 1, quella regola brucerebbe un referto perfettamente sano per un singolo restart sfortunato. La semantica ratificata è quindi il **requeue capped**:

| Condizione | Azione |
|---|---|
| `PROCESSING`, `ocr_started_at` più vecchio di `--minutes` (default 15), `ocr_attempts < 3` | torna in `QUEUED`, audit `ocr_stale_requeue`, `ocr_next_attempt_at = now` (nessun backoff: non ha fallito, gli è morto sotto il worker) |
| idem ma `ocr_attempts >= 3` | `NEEDS_REVIEW` + audit `ocr_failed` + notifica staff |

Il cap a `MAX_ATTEMPTS` regge già la protezione contro le poison pill — un referto che uccide il worker ogni volta esaurisce i tentativi e si ferma — quindi il backstop può permettersi di riprovare invece di arrendersi al primo orfano.

Diagnostica prima di agire: `python manage.py recover_stale_reports --dry-run` stampa cosa farebbe, distinguendo i due esiti, senza scrivere nulla. `--minutes` sposta la soglia. Lo sblocco manuale via `shell -c` usato il 2026-07-19 non serve più e **non va più usato**: scavalcava l'audit trail e non passava dalla notifica.

Osservabilità agganciata nello stesso giro (§ `ops_check`): profondità della coda, referti in `PROCESSING` oltre soglia (RED — è il sintomo netto di worker morto), referti con tentativi esauriti. Serviva perché un worker fermo non ha sintomi propri: i referti smettono di avanzare e basta, senza errori né pagine rotte.

~~Residuo: install ed enable del timer su **prod** restano da fare (giro 3, gated Alberto). Su prod la guardia non è quindi ancora attiva.~~ **Residuo chiuso il 2026-07-20** (deploy §2.7): `2salti-recover-stale.service` e `.timer` installati ed enabled su prod insieme alla unit del worker; verificato `active (waiting)` con trigger ogni 15 minuti. La guardia è ora attiva su **entrambi** i box.

### §10.23 Report 15 orfano in `UPLOADED`, mai accodato — DECISO E CHIUSO 2026-07-21

Censito su prod il 2026-07-20, **non presente** nel censimento del 2026-07-19 (che copriva 7, 8, 10, 11, 16). Stato verificato a DB, in sola lettura:

| Campo | Valore |
|---|---|
| `status` | `UPLOADED` (non `QUEUED`) |
| `match_id` | `None` — è l'**unico** referto orfano a DB |
| `source_channel` | `FILE`, con file allegato presente (`match_reports/reale_05_*.jpg`) |
| `normalized_data` | vuoto (`{}`) — **mai elaborato** |
| `ocr_attempts` / `ocr_queued_at` / `ocr_started_at` | `0` / `None` / `None` |
| `created_at` | 2026-04-19 |

**Non è raggiungibile dal worker** e non lo sarà mai da solo: l'accodamento è **esplicito** per disegno (Macro 22 giro 1 — `QUEUED` è distinto da `UPLOADED` proprio perché i referti creati da admin o da `ingest_emails` non devono partire da soli). Un referto in `UPLOADED` resta fermo a tempo indefinito senza che nulla lo segnali: **non compare in nessuno dei tre segnali di coda** di `ops_check` (che guardano `QUEUED`, `PROCESSING` stale ed `esauriti`), e il backstop `recover_stale_reports` guarda solo `PROCESSING`. È un punto cieco della strumentazione, non un malfunzionamento.

Anomalia minore rilevata nello stesso censimento: `in_review_at` è valorizzato (2026-04-19) pur essendo lo stato `UPLOADED` — residuo di una transizione passata, non coerente con lo stato attuale.

~~**Non toccato per disegno**: non accodato, non collegato a un match, non eliminato.~~

**Esito 2026-07-21.** Il report 15 è stato usato come oggetto del **collaudo end-to-end del worker OCR su prod** (§2.8): accodato deliberatamente, elaborato dal worker, finito in `NEEDS_REVIEW` **orfano** — la discovery non l'ha agganciato a nulla, correttamente, perché le due squadre estratte non esistono a DB.

**Decisione presa (Alberto, 2026-07-21): resta in `NEEDS_REVIEW` come orfano documentato.** Nessuna azione a DB. Le squadre lette sul foglio non hanno anagrafica a sistema, quindi non c'è nulla a cui collegarlo: il referto diventerà risolvibile solo se e quando quelle società entreranno a DB. Non è più un punto cieco della strumentazione — è ora in uno stato finale, visibile in review e nel cockpit come ogni altro `NEEDS_REVIEW`.

Resta aperta l'osservazione generale che l'ha originato: **uno stato `UPLOADED` non accodato non è coperto da alcun segnale** di `ops_check`. Nessun referto è oggi in quella condizione, ma nulla impedisce che ne ricompaiano; se accadrà, il segnale va aggiunto.

### §10.29 Data "oggi" calcolata in UTC invece che in Europe/Rome — CHIUSA 2026-07-22 (bug di PRODUZIONE `e435a95` + sibling LATO-TEST `2e7f9ee` il 21/07; fratelli pilot fixati il 22/07)

Due difetti della stessa famiglia (data UTC dove serviva Europe/Rome), **severità incomparabili**, tenuti distinti apposta.

**Il bug di produzione (commit A, `e435a95`).** In `matches/views.py` la view pubblica `sport_matches` usava `today = timezone.now().date()` come default del sotto-filtro data, ma il filtro `match_date__date` opera in `Europe/Rome` (Django, `USE_TZ=True`, `TIME_ZONE='Europe/Rome'`). Il server gira in UTC. Fra le **00:00 e le 02:00 ora di Roma** (server UTC+2 d'estate, +1 d'inverno → finestra di 1-2 ore) `now().date()` restituisce il giorno UTC — ieri, per un utente italiano — mentre le partite del giorno cadono sotto il giorno di Roma. Effetto utente reale: in quella finestra notturna **le partite odierne sparivano dalla lista pubblica** e l'evidenziazione "oggi" del calendario era sfasata di un giorno. Fix: `timezone.localdate()`.

**Come è emerso, e la prova di ortogonalità.** Tre test in `matches/tests_public_read.py` (`test_default_is_current_season`, `test_querystring_overrides_default`, `test_date_subfilter_still_works`, classe `SportMatchesSeasonSelectorTest`) sono passati **rossi** durante il giro del 2026-07-21. Il file era stato toccato l'ultima volta il **2026-06-14** (`62c582c`, Macro 3) — non in questa sessione, i cui commit di codice erano fino a quel momento **solo-doc** e la cui riparazione dati girava su una tabella `MatchReport` invisibile ai test (DB di test isolato, costruito in `setUp`). Nessun meccanismo collegava la sessione a quei rossi: erano ortogonali.

**La prova che è il calendario/orologio, non una regressione.** La stessa suite era **verde il 2026-07-21 alle ~12:36 UTC** (`Ran 749 tests — OK (skipped=2)`, session note del 21/07) e **rossa lo stesso 2026-07-21 alle ~22:35 UTC** (`Ran 770 — failures=3`; i +21 test sono le fette cross-check di questa sessione). Stesso giorno **solare UTC**, ma il secondo run cade **dopo la mezzanotte di Roma**: alle 12:36 UTC `now().date()` e `localdate()` coincidevano (entrambi 2026-07-21), alle 22:35 UTC divergevano (UTC 2026-07-21 vs Roma 2026-07-22). Il delta verde→rosso è la firma della **dipendenza dall'orario**, non dal confine stagionale.

**Ipotesi (i) — "test fragili al season hardcoded" — ESCLUSA.** L'assert `selected_season == "2025/2026"` *passava*: la stagione era calcolata giusta (`Season.is_current`). A svuotarsi era l'insieme delle partite per via del sotto-filtro data. La causa non è mai stata il confine stagionale.

**Il sibling lato-test (commit B, `2e7f9ee`).** Dopo il fix della view, `test_date_subfilter_still_works` restava rosso per un difetto **suo**: costruiva il parametro `?date` con `other_day.date()` — `.date()` su un `datetime` aware, quindi la data **UTC** — incoerente col filtro Roma della view (ormai corretta). Difetto di aritmetica **lato-test, mai visibile a un utente**: lo vede solo chi lancia la suite nella finestra notturna. Fix: `timezone.localtime(other_day).date()`. Tenuto in un commit separato dal bug di produzione apposta: severità incomparabili, la storia di git non deve annacquare la prima nella seconda.

**Prove eseguite dentro la finestra 00:00-02:00 di Roma** (2026-07-21 ~23:00 UTC = 22-07 ~01:00 Roma), perché **fuori dalla finestra non sono riproducibili** (dopo le 02:00 di Roma i tre test tornano verdi da soli, che si fixi o no): view — rosso con `now().date()`, verde con `localdate()`, controprova che i due test default tornano rossi rimettendo il bug; test — rosso prima, verde dopo, controprova che il test fixato **fallisce ancora** sul view buggato (guarda ancora la view, non è stato neutralizzato). Suite intera dopo entrambi i fix: `Ran 770 — OK (skipped=2)`, in-window.

**Fratelli dello stesso pattern trovati col grep — ri-verificati sul codice il 2026-07-22, esito differenziato:**
- `management/pilot_services.py:28` (`report_date = date.today()`, alimenta `filter(date=…)`, `created_at__date`, `updated_at__date`) e `:128` (`today = date.today()`, alimenta il dedup `AuditLog.filter(timestamp__date=today)`): **bug reali confermati e FIXATI il 2026-07-22** (`timezone.localdate()`, stesso pattern di `e435a95`; import `date` rimosso perché non più usato). Il flip è blindato da due test in `management/tests_pilot_ops.py` (`PilotTimezoneTodayTest`) che **congelano l'orologio** con `mock.patch('django.utils.timezone.now', …)` all'istante `2025-07-15 23:30 UTC` (Roma `2025-07-16`): rossi sul codice buggato, verdi sul fixato, **riproducibili sempre** e non solo nella finestra 00:00-02:00 reale. Controprova eseguita nei due versi.
- `core/views.py:21` (`today = timezone.now().date()`): **ri-verificato COSMETICO** — `today` è usato **solo** in `seo_title`/`seo_description` via `strftime` (righe ~65-66 di `home()`), **nessuna query** lo consuma. Nella finestra il titolo SEO mostra la data di ieri; nessun dato nascosto, nessun conteggio sfasato. **Non fixato** (nulla di funzionale da correggere).
- `core/utils.py:10` (default `center_date` di `get_calendar_dates`): **ri-verificato LATENTE/morto** — l'unico chiamante nel repo è `matches/views.py:307` (`get_calendar_dates(center_date=selected_date)`), che passa `center_date` **esplicito**; il default `timezone.now().date()` non è mai esercitato. **Non fixato** (percorso non raggiungibile).

**Grep di chiusura (2026-07-22):** fuori dai tre fratelli noti **non restano** altri `timezone.now().date()` / `date.today()` / `datetime.now().date()` nel codice applicativo (esclusi `.venv`, test e migration). Le due occorrenze superstiti (`core/views.py:21`, `core/utils.py:10`) sono quelle qui sopra, cosmetica e latente. **Voce §10.29 CHIUSA:** il solo bug funzionale (pilot) è fixato e testato; il resto è documentato come non-bug.

**Non-fratelli, verificati:** `matches/services/match_discovery.py:70` (`match_date__date=target_date`) — `target_date` è la data **estratta dal referto**, non "oggi": scenario diverso, non questo bug. `management/ops_services.py:120` usa già `timezone.localdate()` — è il pattern corretto, precedente da imitare.

### §10.32 Reason obbligatoria in admin per downgrade a SCORE_ONLY e force publish — CHIUSA 2026-07-22

*Cosa era:* la review admin invocava `publish_report(obj, user=…, force=…, level=…)` **senza mai passare `reason`**. Il campo "Motivazione" (`name="reason_message"`) era POSTato ma `admin.py` non lo leggeva: raccolto e scartato. Il seam di servizio ([matches/services/publishing_service.py](../matches/services/publishing_service.py)) esige una `reason` non vuota su due gesti — downgrade `FULL`→`SCORE_ONLY` su republish (D3) e force su match con dato verificato — quindi da questa UI quei gesti fallivano **sempre**, anche compilando il campo, con un rifiuto senza via d'uscita (redirect in changelist).

*Chiuso (parte del giro di riparazione della review admin, 2026-07-22):*
- `matches/admin.py` (`review_view`, ramo `publish_now`/`publish_force`/`publish_score_only`): legge `reason_message` dal POST (trim) e la passa a `publish_report(..., reason=reason)`.
- **Obbligatorietà lato admin sul force:** il gesto più discrezionale (override blocchi) era l'unico che passava senza motivazione umana (audit povero). Ora `publish_force` senza `reason` è rifiutato in UI, **prima** di invocare il servizio, con messaggio leggibile. Downgrade e force-su-verificato restano obbligati dal servizio, ora navigabili.
- **Via d'uscita:** su rifiuto (di servizio o della guardia force) l'operatore **resta sulla review page** invece di finire in changelist, così può compilare Motivazione e ritentare.
- La motivazione dell'operatore finisce nell'audit trail come già previsto dal servizio (`reason` nei log di publish).

*JS morto correlato, nato e morto nello stesso giro (nessun debito a sé):* il blocco `<script>` della review page moriva per `SyntaxError` a causa di payload Python renderizzati via `|safe` (`rawExtractedData` col repr, `roster_names`/`event_types` mai passati → `const … = ;`). La causa radice è stata rimossa (serializzazione via `json_script`, variabili di context passate, codice diff-vs-OCR residuo eliminato perché leggeva uno schema inesistente). Senza quella riparazione la reason non sarebbe comunque bastata: i widget di editing perdevano silenziosamente le correzioni perché il sync JSON era morto.

*Vive in:* [matches/admin.py](../matches/admin.py), [templates/admin/matches/matchreport/review.html](../templates/admin/matches/matchreport/review.html); test in [matches/tests_review_ui.py](../matches/tests_review_ui.py) (`ReviewContextAndReasonTest`).

*Residuo:* nessuno per §10.32. La correttezza end-to-end su prod (console pulita, widget che salvano, Motivazione richiesta) va confermata a occhio nel browser su dev (prompt di verifica Antigravity preparato nel giro). Restano aperti, distinti: §10.30 (`report_review` frontend) e §10.31 (declassamento SCORE_ONLY per wording).

### §10.36 Badge "AI Engine v2" nella dashboard — CHIUSA 2026-07-23

*Cosa era:* nel riquadro **Caricamento Rapido** della dashboard ([templates/accounts/dashboard.html:164](../templates/accounts/dashboard.html)) un badge hardcoded `AI Engine v2`. Il badge sta nella sezione **"AI DISCOVERY QUICK UPLOAD"**, il cui testo parla di *discovery* (identificare squadre/data/campionato dal contenuto), **non** di qualità/versione dell'estrazione OCR. La stringa era **statica**, non legata a `settings.OCR_PROMPT_VERSION` né ad alcuna altra sorgente di versione: **non** era quindi la versione del prompt OCR (v3 in produzione dal 2026-07-23, §8.21). L'ambiguità: un lettore poteva leggere "v2" come numero di versione dell'AI/OCR e confonderlo con le versioni di prompt (v2/v3/V3.x).

*Chiuso:* rimosso il numero di versione dalla stringa (`AI Engine v2` → `AI Engine`), lasciando il solo branding del Discovery **senza** legarlo a `OCR_PROMPT_VERSION` (il badge è correttamente decorrelato dal prompt OCR; il problema era solo il "v2" che suggeriva una versione inesistente come tale). Occorrenza unica (grep), nessun test asserisce la stringa. `python manage.py check` e la suite `accounts` verdi.

*Vive in:* [templates/accounts/dashboard.html](../templates/accounts/dashboard.html) (riga ~164).

*Residuo:* nessuno.

### §10.35 `EXCLUSION_DEF` perde i metadati sanzione al publish e si proietta come codice grezzo — CHIUSA 2026-07-23

*Cosa era:* l'espulsione definitiva (EDCS) era un tipo di schema OCR/gold non integrato nella pipeline pubblicabile. Al converter `MatchDataConverter.get_events_data` faceva passare il tipo verbatim ma **scartava silenziosamente** `regulation_article` e `sanction_sigla` — proprio i campi che distinguono una definitiva da un evento generico. A valle l'evento si proiettava come codice tecnico (punto etichetta poi scorporato in §10.38). Blast radius allora nullo (V3.4 non default di produzione, referto 8 non pubblicato), ma perdita di dato latente e reale su un percorso vivo.

*Disegno ratificato:* `RED_CARD` ed `EXCLUSION_DEF` descrivono **lo stesso evento reale** in pallanuoto (l'EDCS), e `RED_CARD` è già un tipo canonico pubblicabile con blocco di template dedicato. La chiusura non introduce un tipo parallelo ma **arricchisce il `RED_CARD` esistente**.

*Chiuso:*
- **Modello + migration** ([matches/models.py](../matches/models.py), migration `0021_matchevent_sanction_metadata`): due `CharField` nullable additivi su `MatchEvent` — `regulation_article` (max 20) e `sanction_sigla` (max 50). Migration unica, puramente additiva, nessuna data-migration. Il campo `player` era già nullable: non toccato.
- **Converter** ([matches/services/converters.py](../matches/services/converters.py)): `EXCLUSION_DEF` → `RED_CARD`; `regulation_article` e `sanction_sigla` portati a valle **verbatim**. Possono restare **null** su un rosso legittimo (forma V3 di produzione, che emette `RED_CARD` senza articolo): nessuna validazione li pretende. La classificazione **non** si persiste — si deriva a render-time da `classify_definitive_exclusion`.
- **Publishing** ([matches/services/publishing_service.py](../matches/services/publishing_service.py)): i due campi passati a `MatchEvent.objects.create(...)`.
- **Invarianza fouled-out:** il conteggio opera solo su `EXCLUSION_20` ([matches/stats_services.py](../matches/stats_services.py)) e la mappatura porta a `RED_CARD`, non a `EXCLUSION_20` — un test lo asserisce esplicitamente.

*Test:* [matches/tests_event_enrichment.py](../matches/tests_event_enrichment.py) — mappatura, metadati verbatim (forma V3.4), rosso senza articolo (forma V3), l'`EXCLUSION_DEF` che non diventa mai `EXCLUSION_20`, e la persistenza al publish con metadati. Suite intera verde (886 test, skipped=2).

*Residuo:* nessuno per §10.35. Il prompt V3.4 resta prompt di misura (non default): la promozione è una decisione di prodotto separata. Il warning sugli eventi non riconciliati e il fallback etichetta sono §10.37 / §10.38, chiusi nello stesso giro.

### §10.37 Gli eventi senza `player_id` vengono scartati in silenzio al publish — CHIUSA 2026-07-23

*Cosa era:* `publish_report` creava il `MatchEvent` **solo** se `ed["player_id"]` era valorizzato. Conseguenze: i **TIMEOUT** (per contratto `player_name` null: il timeout è della squadra) **non venivano mai persistiti** — cadevano nel ramo di scarto pur essendo statistiche di livello Base promesse dal BLUEPRINT §7.4.3; un **rosso/esclusione non riconciliato per nome** veniva scartato **senza traccia né warning**.

*Chiuso:* distinzione per natura dell'evento resa **strutturale** — attributo `is_team_level` del tipo in [matches/event_types.py](../matches/event_types.py) (con helper `is_team_level_event`), non un elenco di stringhe nel publishing:
- Eventi **team-level** (TIMEOUT): persistiti con `player=None`, squadra e riferimento temporale (`minute`/`quarter`).
- Eventi **player-level non riconciliati**: **non** persistiti (non attribuibili) ma **non** più inghiottiti — confluiscono nella lista `warnings` già usata da audit/log e resa nel messaggio di review, con l'evento e il nome che non ha agganciato il roster.

*Vincolo rispettato:* è un **WARNING, non un blocker**. Nessun blocker nuovo introdotto: la lista `warnings` esistente non alimenta i marker event-scoped di `schema.py`, quindi i publish SCORE_ONLY non sono toccati. Nessun campo `clock` aggiunto a `MatchEvent` (fuori scope, deciso a monte): i timeout usano i campi temporali esistenti `minute`/`quarter`.

*Test:* [matches/tests_event_enrichment.py](../matches/tests_event_enrichment.py) — persistenza TIMEOUT con `player` null; warning col nome sull'evento player-level non riconciliato + sua non-persistenza.

*Residuo:* la riconciliazione resta **per nome, non per calottina** ([matches/services/converters.py](../matches/services/converters.py)): un giocatore reale con nome divergente dal roster produce ora un warning (non più uno scarto silenzioso), ma non viene agganciato — il match per calottina resta un possibile miglioramento futuro, fuori dallo scope di questo giro.

### §10.38 `display_label` mostra il codice tecnico perché `SportEventConfig` è vuota — CHIUSA 2026-07-23

*Cosa era:* `display_label` consultava **solo** `SportEventConfig` e ripiegava su `self.event_type` (codice grezzo). La tabella è **vuota** su dev e prod (verificato read-only), quindi ogni evento pubblicato mostrava all'utente la stringa tecnica (es. `"RED_CARD"`) dove `{{ event.display_label }}` è reso — testo rivolto al pubblico. `EVENT_LABELS`/`get_event_label` esistevano ma non erano chiamati dalla resa.

*Chiuso:* [matches/models.py](../matches/models.py) — `display_label` è ora una catena a tre livelli: `SportEventConfig` (override per sport) → `get_event_label`/`EVENT_LABELS` (default centralizzati a codice, [matches/event_types.py](../matches/event_types.py)) → codice grezzo (ultima spiaggia). Fix **a codice**, nessun dato seminato: funziona in ogni ambiente senza dipendere da righe in tabella. `SportEventConfig` **resta** l'override più alto (personalizzazione per sport). `EVENT_LABELS` copre per costruzione tutti i `DEFAULT_EVENT_TYPES`.

*Test:* [matches/tests_display_label.py](../matches/tests_display_label.py) — con `SportEventConfig` vuota restituisce l'etichetta leggibile e non il codice; l'override quando presente vince; il tipo mai visto ripiega sul grezzo; copertura di tutti i `DEFAULT_EVENT_TYPES`.

*Residuo:* nessuno.

### §12.9 Debito semantico A1: utility `cyan-*` che rendono blue (Macro 17 Fase 2) — SALDATO 2026-06-30 (A2, `dev`); archiviato qui 2026-07-22

> **ID fuori serie** (unica voce non-§10.x): la voce nasce come §12.9 di OPS_RUNBOOK — sezione 12 "Verifiche e regole di processo", non la sezione 10 dei debiti — e conserva l'ID originale perché syllabus Macro 17, session note e memorie la citano come "OPS §12.9": la continuità di citazione vale più dell'uniformità di numerazione. In OPS_RUNBOOK §12.9 resta il rimando.
>
> **Sul "residuo aperto" dichiarato nel primo capoverso storico qui sotto** (`Sport.hex_color` di "7 sport fittizi del DB dev" fermi a `#00ffff`, normalizzazione gated su Alberto): era **già superato quando fu scritto**. La verifica dello stesso 2026-06-30 (SESSION_NOTE_20260630, learning a: "la realtà DB dev è 6 sport, 0 ciano" → task DB #3 **no-op**) smentì la stima della nota del 23-giu, ma il blockquote di OPS §12.9 non venne mai allineato. Ri-verificato il 2026-07-22 via query read-only: `core_sport` sul box dev contiene **solo** pallanuoto `#2563eb`. La voce è quindi **interamente chiusa**: nessun residuo migra in DEBITI.md. (Osservazione collaterale della stessa verifica, fuori dal perimetro del residuo: il DB **locale** `/home/alberto/db.sqlite3` conserva 5 sport fittizi di test con `#00ffff`, id 7/8/12/13/14 — artefatto di working copy senza alcuna superficie servita; nessuna voce aperta, da rivalutare solo se quel DB tornasse sorgente di verità.) Corpo storico integrale qui sotto.

> **✅ SALDATO da A2 il 2026-06-30 (`dev`).** I nomi-classe ora coincidono con la resa: le `cyan-*` sono state rinominate `blue-*` in template, `matches/forms.py` e nei selettori light-theme di `style.css`; il token-remap `cyan` è stato **rimosso** da `tailwind.config.js` (la scala rimappata era un 1:1 esatto dello stock `blue`, quindi rinomina pixel-identica). `tailwind.build.css` rigenerato — il commit ha anche corretto un build **stale** da `ac9b970` (literali rgba dei glow già blu ma CSS non rigenerato: 13 aloni blu mancanti + 13 utility cyan morte). Verificato: 0 classi `cyan` in sorgenti e build. **Residuo aperto** (punto 4 sotto): `Sport.hex_color` di 7 sport fittizi del DB dev resta `#00ffff` — normalizzazione a `#2563eb` gated su backup+scrittura DB di Alberto. Lo storico sotto è conservato per contesto.

> **Aperto dal 2026-06-23 (`dev`, commit `819db21`).** Il re-skin Cap. 12 ha adottato la strategia **token-remap (A1)**: in `tailwind.config.js` la scala `cyan` è ridefinita sui valori `blue` di Tailwind. Conseguenza: le ~480 utility scritte `cyan-*` nei template (`text-cyan-400`, `bg-cyan-500`, …) **rendono blue** senza essere state rinominate. È deliberato — evita un find-replace di massa — ma è **debito**: chi legge i template vede `cyan` e ottiene blue.

Cosa sapere: (1) **non fidarsi del nome classe** per il colore reale: la fonte di verità è `tailwind.config.js`. (2) Nuove UI: preferire `blue-*` esplicito; non aggiungere altri `cyan-*`. (3) **Literali orfani**: hex/rgba ciano hardcoded (`rgba(6,182,212,…)` nei glow `shadow-[…]`, qualche `#06b6d4`/`#0891b2`) NON sono raggiunti dal remap — vanno cambiati a mano dove emergono (al 2026-06-23 ne restano in ~15 template non-base, delegati al giro visivo Antigravity). (4) **Per-sport color**: `Sport.hex_color` è in DB (pallanuoto `#00ffff`) — il remap CSS non lo tocca; allinearlo a blue richiede una migration dati (gate backup + ratifica). La ripulitura completa dei nomi-classe `cyan-*`→`blue-*` è un **task A2 futuro**, non urgente (nessun impatto funzionale/a11y).
