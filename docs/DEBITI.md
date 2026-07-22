# DEBITI — Registro dei debiti tecnici aperti

Questo file contiene SOLO i debiti aperti. Alla chiusura, la voce si SPOSTA in [DEBITI_CHIUSI.md](DEBITI_CHIUSI.md) con data e riferimenti di chiusura, e si rimuove da qui. I nuovi debiti si aprono qui con ID progressivo nella numerazione esistente (§10.33, §10.34, ...). In via d'eccezione il registro (e l'archivio dei chiusi) può ospitare ID **fuori dalla serie §10.x**, quando una voce migra da un'altra sezione di OPS_RUNBOOK e la continuità di citazione impone di conservarne l'ID originale — la continuità di citazione vale più dell'uniformità di numerazione (oggi l'unico caso è §12.9, archiviato in DEBITI_CHIUSI.md).

> Origine della numerazione: gli ID §10.x nascono dalla ex sezione "10. Debiti aperti" di [OPS_RUNBOOK.md](OPS_RUNBOOK.md) (riorganizzazione doc 2026-07-22). I corpi delle voci sono spostati integralmente; la riga `>` di metadati sotto ogni titolo è aggiunta dalla riorganizzazione e sintetizza ciò che il corpo già dice. Questo file vive in `docs/` come il runbook, quindi i link relativi al codice (es. `../matches/...`) restano validi.

### §10.18 Pin di `requirements.txt` più vecchi dell'installato su prod (downgrade da pip install) — APERTO 2026-07-19

> **Severità:** non classificata · **Aperta dal:** 2026-07-19 · **Condizione di chiusura:** giro dedicato che allinea i pin di `requirements.txt` allo stato reale dei box, valutando i fix di sicurezza Django 5.0.x persi; fino ad allora non rilanciare `pip install -r requirements.txt` sui box.

Durante il deploy §2.6, `pip install -r requirements.txt` su prod ha fatto **downgrade** di pacchetti installati a mano più di recente: Django 5.0.3→5.0, openai 2.31→2.29, numpy 2.4.4→2.4.3, python-dotenv 1.2.2→1.2.1. I pin nel file sono più vecchi dello stato reale dei box. Da allineare in un giro dedicato: portare i pin allo stato corretto valutando in particolare i **fix di sicurezza Django** persi col rientro da 5.0.3 a 5.0 (i patch release 5.0.x sono in gran parte security/bugfix). Fino ad allora: **non** rilanciare `pip install -r requirements.txt` sui box se non serve.

### §10.20 Saturazione del pool worker con OCR sincrono — CAUSA RIMOSSA SU PROD 2026-07-20, voce aperta solo per il giro 4

> **Severità:** non classificata (causa rimossa, resta il cerotto) · **Aperta dal:** 2026-07-19 · **Condizione di chiusura:** giro 4 di Macro 22 (rimozione dei timeout 300s gunicorn + nginx) — "la voce si chiude col giro 4, non prima".

~~Prod ha `workers = 3` e l'OCR gira sincrono nel request cycle (~80s a referto, §3.16): **3 upload OCR concorrenti bloccano l'intero pool** per ~80s ciascuno e il sito smette di rispondere a qualunque richiesta finché un worker non si libera.~~

**La causa è rimossa nel codice** (Macro 22 giro 1): l'OCR non gira più nel request cycle. I due entry point — upload view e admin action `process_ocr` — accodano e rispondono subito; l'elaborazione avviene nel processo `ocr_worker`, fuori da gunicorn. Il pool **non è più saturabile dagli upload**: una richiesta di upload ora dura quanto una scrittura su DB, non ~80s, e nessun worker gunicorn resta occupato da una chiamata a Gemini.

Due precisazioni che impediscono di leggere questa voce come chiusa:

- ~~**Su prod non è ancora vero.** Il codice è live solo su dev; il deploy su prod (migration gated dopo backup DB + install della unit worker) è il giro 3.~~ **Superato il 2026-07-20** (deploy §2.7): il codice è live **anche su prod** e la unit del worker è installata e in esercizio. La causa della saturazione è quindi rimossa su entrambi i box e il debito **non è più attivo** come descritto sopra. Resta però un residuo di collaudo, non di implementazione: alla data del deploy il worker su prod **non ha ancora elaborato un solo referto reale** (la coda era vuota e nessun upload è stato fatto nella finestra), quindi l'asincrono su prod è verificato come *processo che parte, si ferma e si riavvia correttamente*, non come *pipeline che porta un referto da upload a estrazione*. Il primo upload reale su prod è il collaudo end-to-end mancante.
- **I timeout 300s restano**, su entrambi i box. Gunicorn `timeout = 300` e nginx `proxy_read_timeout 300s` sono il cerotto che questa macro elimina, ma la rimozione è deliberatamente rinviata al **giro 4**, dopo un periodo di osservazione dell'asincrono su prod: toglierli prima significherebbe rimuovere la rete di sicurezza mentre si sta ancora verificando che il sostituto regga. Finché ci sono, un residuo di path sincrono (es. `process_and_update` usato in diagnostica) non causa un 500 immediato.

La voce si chiude col giro 4, non prima.

### §10.21 `MatchReport` registrato su due admin site — APERTO 2026-07-19 (minore)

> **Severità:** minore · **Aperta dal:** 2026-07-19 · **Condizione di chiusura:** rimozione della doppia registrazione admin in un giro cosmetico.

`MatchReport` è registrato sia su `op_admin_site` con `MatchReportAdmin` ([matches/admin.py:416](../matches/admin.py)) sia sul default admin site via `@admin.register(MatchReport)` su una sottoclasse `MatchReportAdminDefault` con `has_module_permission=False` ([matches/admin.py:418-420](../matches/admin.py); stesso pattern per `Match`). Doppiamente **inerte** a runtime — il default admin site non è nemmeno montato negli URL (`/admin/` punta a `op_admin_site`, [config/urls.py:27](../config/urls.py)) — ma confondente in lettura: due registrazioni dello stesso modello, di cui una nascosta e irraggiungibile. Da pulire in un giro cosmetico, non urgente.

### §10.22 Nessun guardrail a codice contro la pubblicazione dei report con `normalized_data` sbagliato — APERTO 2026-07-20

> **Severità:** non classificata (rischio di corruzione silenziosa al publish) · **Aperta dal:** 2026-07-20 · **Condizione di chiusura:** guardrail a codice che `publish_report()` controlli e rifiuti (direzione indicata: flag esplicito tipo `normalized_data_is_stale`), oppure correzione del `normalized_data` dei report 7, 8, 10, 11, 16.

I report **7, 8, 10, 11, 16** hanno `normalized_data` con punteggio e/o attribuzione casa/trasferta errati. Le correzioni del 2026-07-19 (dev) e del 2026-07-20 (prod, §2.7) hanno toccato **solo** i `Match`, mai i report: è una scelta deliberata, non una dimenticanza — correggere il `normalized_data` è un giro separato del filone OCR.

Il rischio è che `publish_report()` ([matches/services/publishing_service.py](../matches/services/publishing_service.py)) sovrascriva `home_score`, `away_score` e `quarter_scores` leggendo dal `normalized_data` non corretto — e, per il match 2, ricrei gli eventi con l'attribuzione squadra ancora invertita — **vanificando silenziosamente** la correzione. Non c'è nulla nel codice che lo impedisca: nessun flag sul report, nessun controllo in `publish_report()`, nessun blocco in admin.

Mitigazione oggi in essere, tutta non-tecnica: (a) questa voce e la nota gemella in SYLLABUS Macro 8 §8.5; (b) il fatto che dal 2026-07-20 **nessuno dei cinque è più in `EXTRACTED`** — sono tutti in `NEEDS_REVIEW`, quindi più lontani di un click dalla pubblicazione, ma non protetti. La direzione da valutare in un giro dedicato è un flag esplicito sul report (`normalized_data_is_stale` o equivalente) che `publish_report()` controlli e rifiuti, invece di affidarsi alla memoria di chi guarda la coda.

### §10.24 Naming dei `Team` incoerente con la convenzione dichiarata — APERTO 2026-07-21 (cosmetico)

> **Severità:** cosmetico · **Aperta dal:** 2026-07-21 · **Condizione di chiusura:** rinomina coerente in un giro dedicato su tutte e 13 le squadre o su nessuna — mai su una sola (ogni rinomina sposta i punteggi della discovery, §8.6).

`Team.name` dichiara nell'`help_text` la convenzione "Society + tipo lega", ma solo alcune squadre la rispettano (il merge D1 di syllabus §8.7 ha lasciato `S.S. Lazio Nuoto Allievi` accanto a `S.S. Lazio Nuoto`, che dovrebbe essere `… Serie C`): l'asimmetria è **preesistente e generale su tutte e 13 le squadre**, quindi va sanata in un giro cosmetico dedicato su tutte o su nessuna — mai su una sola, perché ogni rinomina sposta i punteggi della discovery (§8.6).

### §10.25 `ops_check` conta i findings ma non li stampa — APERTO 2026-07-21

> **Severità:** non classificata (osservabilità) · **Aperta dal:** 2026-07-21 · **Condizione di chiusura:** esporre il dettaglio dei findings a CLI in `ops_check`.

Nello smoke del deploy §2.9 il comando ha riportato `GREEN, Findings: 1` senza alcun modo, a CLI, di sapere **quale** finding fosse (nemmeno con `--verbosity 2`: non esiste il ramo, §3.18); un segnale che non si può leggere non è un segnale, e finché resta così l'unica via è il JSON in `logs/ops/`.

### §10.26 Backup vecchi in accumulo in `/var/tmp`, uno da 0 byte — APERTO 2026-07-21

> **Severità:** non classificata (igiene backup) · **Aperta dal:** 2026-07-21 · **Condizione di chiusura:** pulizia dei backup obsoleti in `/var/tmp` (in primis quello da 0 byte, su cui nessun rollback può contare).

`/var/tmp` conserva backup DB di giri passati mai ripuliti, fra cui `db.sqlite3.match3-correction-20260719` di **0 byte** — un backup che non contiene nulla e su cui nessun rollback può contare; il gate `PRAGMA integrity_check` + dimensione plausibile del rituale attuale (§2.5) esiste proprio per non produrne altri, ma non ripulisce quelli già a terra.

### §10.27 Coerenza referto 10 / match 3 su prod a un epsilon di floating point dalla soglia — APERTO 2026-07-21

> **Severità:** non classificata (fragilità latente) · **Aperta dal:** 2026-07-21 · **Condizione di chiusura:** eliminare il pareggio esatto con `TEAM_FUZZY_THRESHOLD` (margine reale o alias dedicato); da riverificare a ogni modifica di soglia, `normalize_team_name` o `team_similarity`.

Il punteggio `team_similarity()` fra il nome squadra del referto 10 (`S.S. LAZIO NUOTO`, away) e `Team` 6 (`S.S. Lazio Nuoto Allievi`) vale, bit per bit, `0.80000000000000004441` — lo stesso double di `TEAM_FUZZY_THRESHOLD = 0.80` (`matches/services/ocr_service.py`): l'uguaglianza non è un margine, è un pareggio esatto sulla rappresentazione IEEE 754. Qualunque modifica a `TEAM_FUZZY_THRESHOLD`, `normalize_team_name` o `team_similarity` può spostare quel punteggio sotto soglia senza che nulla lo segnali, orfanizzando il referto 10 rispetto a quella squadra.

### §10.28 PII storica in `scratch/seed_pilot_data.py` — APERTO 2026-07-21 (severità bassa, nessuna bonifica decisa)

> **Severità:** bassa (nessuna bonifica decisa) · **Aperta dal:** 2026-07-21 · **Condizione di riapertura:** esplicita nel corpo — repo pubblico, o PII più estesa nella history.

Il file contiene nomi e cognomi di atleti **reali** hardcoded nel sorgente, scrapati da 1x2pallanuoto.it, ed è in git dal 2026-04-17 (commit `8f47d34`). De-trackato il 2026-07-21 (`121d210`, con `scratch/` ignorata per intero): è fuori dall'albero versionato e dai commit futuri, ma **resta nella storia** di git e resta raggiungibile a chiunque abbia il repo.

Valutazione fatta e registrata: repo privato, dati limitati a nome+cognome già pubblicati su una fonte pubblica sportiva. **Severità bassa, nessuna bonifica della storia decisa.**

Condizione di riapertura esplicita: se il repo diventasse pubblico, oppure se emergessero altri file storici con PII più estesa (date di nascita, email, contatti), il debito va rivalutato e la bonifica via `git filter-repo` torna sul tavolo — col costo noto della riscrittura di **tutti** gli hash e del re-clone obbligato di ogni copia (`/opt/2salti-new`, `/opt/2salti-dev`, `/home/alberto`).

### §10.30 `report_review` scrive il Match fuori da `publish_report` e corrompe `normalized_data` al publish — DEBITO APERTO 2026-07-22 (severità media)

> **Severità:** media · **Aperta dal:** 2026-07-22 · **Condizione di chiusura:** esplicita nel corpo — ramo POST di `report_review` che deleghi a `publish_report`, con i suoi test.

La view staff `report_review` ([matches/views.py](../matches/views.py), ramo POST della review manuale) **viola l'Opzione A** (ratificata 2026-07-21: `Match` è una proiezione del referto, `publish_report` ne è l'unico scrittore legittimo). Tre difetti distinti nello stesso ramo:
1. scrive `match.home_score`/`away_score`/`quarter_scores`/`is_finished` **direttamente** dai campi della form, non via `publish_report` — il Match smette di essere una proiezione del referto;
2. crea/cancella `MatchEvent` a mano (loop sui `player_goals_*` della form), fuori dal converter e dai guardrail;
3. al publish, se `report.normalized_data` esiste, lo **sovrascrive** con `{'home_score', 'away_score'}` in `normalized_data['match_info']` — **distruggendo** nomi squadre, data e tutto il resto di `match_info`, poi chiama `publish_report` su quel payload mutilato.

**Perché non è esploso finora:** il percorso reale dei 5 referti gold passa dalla **review admin** (`MatchReportAdmin.review_view`), non da questa view; e nessun referto è ancora stato pubblicato in produzione. Ma è un percorso vivo e raggiungibile da uno staff, e con l'arrivo del publish score-only (Opzione A) la superficie di pubblicazione cresce.

**Severità media:** non tocca dati pubblici oggi (nessun `PUBLISHED` su prod), ma può corrompere `normalized_data` — l'evidenza-livello-di-correzione — in modo silenzioso e irreversibile appena qualcuno usa questa view per pubblicare.

**Condizione di riapertura / fix:** riscrivere il ramo POST di `report_review` perché deleghi a `publish_report` (proiezione, eventi, guardrail, livello) invece di scrivere Match e `MatchEvent` a mano, e **non** rimpiazzare mai `match_info` con un dict di soli punteggi. Da fare in un giro dedicato con i suoi test; **non** toccato dalla task Opzione A del 2026-07-22 (che lo ha solo registrato qui).

### §10.31 Il declassamento dei blocker event-scoped su SCORE_ONLY dipende dal wording umano dei blocker — DEBITO APERTO 2026-07-22 (severità media)

> **Severità:** media · **Aperta dal:** 2026-07-22 · **Condizione di chiusura:** codice strutturato per i blocker (declassamento deciso sul codice, non sulla stringa) · **Trigger di attenzione:** esplicito nel corpo — ogni modifica al wording dei blocker, o il primo publish `SCORE_ONLY` reale.

Il livello di pubblicazione `SCORE_ONLY` (Opzione A) declassa a warning i blocker che dipendono dagli eventi (roster vuoti, incoerenza eventi, incoerenza per-periodo, zero eventi, riconciliazione incompleta): su `SCORE_ONLY` non devono bloccare, perché il referto dichiara "eventi non disponibili". Il declassamento vive in `OCRSchemaValidator.assess_publish_readiness` ([matches/services/schema.py](../matches/services/schema.py), ramo `level == LEVEL_SCORE_ONLY`) e riconosce quali blocker sono event-scoped **per match di sottostringa sul testo umano del blocker** contro `_EVENT_SCOPED_BLOCKER_MARKERS` (`"Entrambi i roster sono vuoti"`, `"Incoerenza eventi"`, `PERIOD_BLOCKER_PREFIX`, `"Zero Eventi"`, `"Riconciliazione incompleta"`).

**Il difetto:** il comportamento del publish è così **accoppiato alle stringhe di visualizzazione**. I marker sono le stesse frasi che l'utente legge in review; non c'è un identificatore strutturale che leghi il blocker alla sua categoria. Se qualcuno cambia il wording di un blocker event-scoped nel punto in cui viene generato (rinomina, ritocco di copy, correzione di refuso) senza aggiornare in modo speculare la tupla dei marker, il match per sottostringa smette di agganciare — e il declassamento **smette di funzionare in modo silenzioso**: nessuna eccezione, nessun warning, il blocker semplicemente resta blocker. Un referto legittimamente pubblicabile a solo-punteggio resta bloccato da un blocker che a quel livello doveva essere fuori livello.

**È la stessa forma d'errore del `.gitignore` del 21/07 (§10.28 area):** una protezione che *sembra* attiva e in realtà non copre più il caso, senza alcun segnale di rottura. La sicurezza è nel wording, non nella struttura; il giorno in cui il wording cambia, la garanzia evapora senza rumore.

**Severità media:** non corrompe dati e non allarga la superficie pubblica (il fallimento è restrittivo — blocca di più, non di meno); ma vanifica in modo invisibile una feature deliberata (il publish score-only) e il sintomo — "un referto score-only non si pubblica" — non punta al wording come causa, quindi costa tempo di diagnosi.

**Soluzione indicata:** dare a ogni blocker un **codice strutturato** (enum/costante) separato dal testo umano, e far decidere il declassamento sul codice, non sulla stringa di visualizzazione. La categoria event-scoped diventa un attributo del blocker, non un indovinello sul suo testo.

**Condizione di riapertura:** qualsiasi modifica al wording dei blocker in [matches/services/schema.py](../matches/services/schema.py) (sia i letterali in `_EVENT_SCOPED_BLOCKER_MARKERS`, sia le frasi generate a monte che quei marker devono agganciare), **oppure** il primo publish `SCORE_ONLY` reale — il quale è anche il primo momento in cui il declassamento viene esercitato sul campo e in cui un aggancio silenziosamente rotto diventerebbe visibile.

### §10.32 Reason obbligatoria in admin per downgrade a SCORE_ONLY e force publish — DEBITO APERTO 2026-07-22 (severità bassa)

> **Severità:** bassa (fail-closed oggi sui due gesti più pericolosi; superficie staff-only; zero referti `PUBLISHED` su prod) · **Aperta dal:** 2026-07-22 · **Condizione di chiusura:** la superficie admin raccoglie e **obbliga** la `reason` per downgrade e force publish e la passa a `publish_report()`, allineandosi al seam di servizio; la motivazione dell'operatore finisce nell'audit trail come già avviene lato servizio. · **Trigger di rialzo severità:** primo publish reale, o deploy di Opzione A (SCORE_ONLY) su prod.

Il seam di servizio richiede una `reason` non vuota in due punti ([matches/services/publishing_service.py](../matches/services/publishing_service.py)): (1) **downgrade `FULL`→`SCORE_ONLY` su republish** (cross-check D3, [STATE_MACHINES.md](STATE_MACHINES.md) §MatchReport/Guardrails "Livello di pubblicazione") — distrugge la cronologia eventi già pubblica, senza reason ritorna `(False, msg)`; (2) **force publish su match con dato verificato** — sovrascrive una verifica umana, stessa regola. La review admin ([matches/admin.py](../matches/admin.py), ramo `publish_now`/`publish_force`/`publish_score_only`) invoca però `publish_report(obj, user=…, force=…, level=…)` **senza mai passare `reason`**: la `ReviewForm` non ha alcun campo per raccoglierla.

Conseguenze oggi, distinte:
- **Downgrade D3 e force su dato verificato da admin: impossibili.** Il servizio li rifiuta per reason mancante — fail-closed, nessun rischio dati, ma i due gesti legittimi non sono eseguibili dalla superficie che dovrebbe ospitarli: al primo bisogno reale l'operatore troverà un rifiuto senza via d'uscita in UI.
- **Force "semplice" (override di blocker, senza conflitto su dato verificato): passa senza motivazione umana.** L'audit registra i blocker scavalcati (`overridden_blockers`) e la reason generica `Pubblicazione forzata (override blocchi)`, ma non il **perché** dell'operatore — l'audit trail resta scoperto proprio sul gesto più discrezionale.

**Perché severità bassa:** la superficie è la review admin, staff-only; su prod non esiste alcun referto `PUBLISHED` e il livello `SCORE_ONLY` è a codice solo su dev (deploy prod pendente); il downgrade D3 presuppone un referto già `PUBLISHED FULL`, che oggi non esiste su nessun box. Il fallimento attuale è **restrittivo** (blocca o pubblica con audit povero), mai corruttivo. La severità va rialzata al trigger indicato sopra.

**Nota di contesto:** la definizione precisa della UI (dove vive il campo reason, per quali azioni) era stata deliberatamente rimandata "a quando la superficie di publish viene esercitata davvero" (session note 22/07); questa voce esiste perché quel rinvio non era registrato da nessuna parte e sarebbe diventato una dimenticanza.
