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
