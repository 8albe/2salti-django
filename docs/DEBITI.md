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

### §10.32 Reason obbligatoria in admin per downgrade a SCORE_ONLY e force publish — CHIUSA 2026-07-22 → [DEBITI_CHIUSI.md](DEBITI_CHIUSI.md) §10.32

Chiusa nel giro di riparazione della review admin (2026-07-22): `reason_message` ora letta dal POST e passata a `publish_report()` per tutte le azioni di publish, con obbligatorietà lato admin sul force e i messaggi di rifiuto del servizio resi navigabili (l'operatore resta sulla review page). Dettaglio, riferimenti e test in [DEBITI_CHIUSI.md](DEBITI_CHIUSI.md) §10.32.

### §10.33 Doppia estrazione per zona: regola di divergenza misurata ma non adottata; errore data non catturabile — DEBITO APERTO 2026-07-22 (severità bassa)

> **Severità:** bassa (è codice bench-only, default off, nessun effetto in produzione) · **Aperta dal:** 2026-07-22 · **Condizione di chiusura:** decisione esplicita su (a) adottare o no il warning somma≠finale del passaggio zona come trigger `NEEDS_REVIEW` in produzione, e (b) l'esito dell'esperimento crop/zoom sull'errore data. Fino ad allora il seam `--second-pass` resta strumento di misura, non pipeline.

L'esperimento della doppia estrazione per zona ([syllabus §8.13](syllabus/8_ocr_affidabilita.md)) ha misurato tre cose che restano da chiudere:

- **La regola di divergenza cross-passaggio NON cattura i due errori bersaglio** (Bellator finale casa, Triscelon data): misurata 0/5 su entrambi, le due letture concordano sul valore sbagliato. La regola (`matches/services/ocr_double_extraction.py`, `compare_passes`) è implementata, testata e **selezionabile solo dal bench** (`ocr_bench --second-pass`, default off): **non è cablata in produzione** e in questo giro **non va adottata così com'è**. Va tenuta viva la decisione di scartarla come meccanismo per gli errori stabili di finale/data.
- **Ciò che ha funzionato — il check somma≠finale *interno* al passaggio zona** (Bellator 4/5 vs V3 pieno 0/5) — è un candidato a diventare trigger di review in produzione, ma con una sola chiamata extra ($0,0038/referto) e senza il confronto fra passaggi. Non implementato in produzione in questo giro: è la leva del prossimo giro dedicato, da valutare insieme a Opzione A (chi scatta, su quale livello di publish).
- **L'errore data (Triscelon 28 vs 25) non è catturabile da nessun segnale di coerenza**: campo singolo, senza ridondanza, letture concordi sul valore sbagliato. Resta scoperto fino all'esperimento **crop/zoom** sulla sola testata (lettura ravvicinata), che è l'esperimento candidato successivo. La doppia estrazione **non** lo risolve: va evitato di considerarlo coperto.

**Perché severità bassa:** tutto ciò che è a codice (`OCR_SYSTEM_PROMPT_ZONE`, `compare_passes`, `--second-pass`) è **default off e bench-only**; la produzione a passaggio singolo è invariata (V2, o V3 alla promozione — §8.12). Nessun effetto su referti reali finché non c'è una decisione di adozione esplicita.

### §10.34 Gli input punteggio in review.html leggono un path inesistente nel JSON — DEBITO APERTO 2026-07-23 (severità cosmetica)

> **Severità:** cosmetica (nessun effetto a runtime) · **Aperta dal:** 2026-07-23 · **Condizione di chiusura:** gli input punteggio leggono il path reale del JSON normalizzato, allineati al resto del template.

Nel template [templates/admin/matches/matchreport/review.html](../templates/admin/matches/matchreport/review.html) gli input del punteggio leggono `teams.home.score` / `teams.away.score` (intorno alle righe 783-784: `value="{{ original.normalized_data.teams.home.score|default:0 }}"` e i parziali `normalized_data.teams.home.period_scores.N`), path che nel JSON normalizzato **non esiste**. Il path reale, quello usato dallo script di editing, è `scores.final_score` (stringa `"N-N"`) e `scores.quarters.N` (coppie `[casa, ospite]`): lo script li legge in `syncJsonToStructured()` — invocata in `window.onload` — e sovrascrive i valori degli input. Per questo il difetto è **inerte**: al caricamento della pagina l'utente vede sempre il valore giusto, non quello (a zero) prodotto dal path errato del template.

Resta un **path errato latente**: se un domani lo script smettesse di popolare quei campi (refactor, riordino dell'inizializzazione, rimozione del widget), gli input tornerebbero silenziosamente vuoti o a zero senza alcun errore — stessa forma di **fallimento silenzioso di §10.31** (una garanzia che *sembra* attiva mentre l'aggancio reale vive altrove). Il fix è meccanico: allineare i `value=` degli input al path reale `scores.final_score` / `scores.quarters.N` già usato dallo script, così il template è corretto anche a script assente.

### §10.35 `EXCLUSION_DEF` non è un `MatchEvent` canonico: al publish perde i metadati sanzione e si proietta come codice grezzo — DEBITO APERTO 2026-07-23 (severità media)

> **Severità:** media · **Aperta dal:** 2026-07-23 · **Condizione di chiusura:** integrazione del tipo nella pipeline pubblicabile — `EXCLUSION_DEF` fra i `DEFAULT_EVENT_TYPES` (con `is_score=False`), un `SportEventConfig` con label leggibile per la pallanuoto, e i campi sanzione (`regulation_article`, classificazione da `classify_definitive_exclusion`) portati fino a `MatchEvent` invece che scartati dal converter.

`EXCLUSION_DEF` (espulsione definitiva, EDCS) è oggi un tipo di **schema OCR / gold** — misurato dal bench, prodotto dal prompt V3.4 — ma **non** è un `MatchEvent` canonico pubblicabile. La nota in [matches/event_types.py](../matches/event_types.py) (blocco `EVENT_TYPE_EXCLUSION_DEF`) lo dichiara esplicitamente: non è fra i `DEFAULT_EVENT_TYPES`.

**Comportamento reale al publish, verificato sul codice (non per inferenza):**
- `OCRSchemaValidator.validate` / `assess_publish_readiness` **accettano** un evento `EXCLUSION_DEF`: la validazione eventi ([matches/services/schema.py](../matches/services/schema.py), righe ~104-109) controlla solo che ogni evento sia un dict con un campo `type`, **non** confronta il tipo con una whitelist. Nessun blocco, nessun warning.
- `MatchDataConverter.get_events_data` ([matches/services/converters.py:52-72](../matches/services/converters.py)) fa passare `event_type="EXCLUSION_DEF"` **verbatim**, ma estrae solo `type/minute/player_id/team/quarter/is_penalty/notes`: **scarta silenziosamente** `regulation_article` e `sanction_sigla`, cioè proprio i campi che rendono una definitiva distinta da un evento generico.
- In `publish_report` (ramo `LEVEL_FULL`, [matches/services/publishing_service.py](../matches/services/publishing_service.py)): se l'evento riconcilia a un `player_id` sul team giusto → `MatchEvent.objects.create(event_type="EXCLUSION_DEF", …)` **riesce** — `MatchEvent.event_type` è un `CharField(max_length=50)` senza `choices` ([matches/models.py:116](../matches/models.py)) e `save()` non chiama `full_clean()`, quindi qualunque stringa ≤50 char viene persistita. Se **non** riconcilia → l'evento viene scartato come qualunque evento non riconciliato. **Non solleva, non blocca.**
- A valle: `display_label` ([matches/models.py:139-156](../matches/models.py)) non trova alcun `SportEventConfig` per il codice → restituisce la **stringa grezza** `"EXCLUSION_DEF"`. L'Ut pubblica mostrerebbe il codice interno, non un'etichetta.

**Non è fail-closed.** È **perdita di dato silenziosa e parziale** al publish: il tipo si persiste (se riconciliato), ma i metadati sanzione (articolo `9.13`/`9.14`, classificazione, implicazioni rigore/squalifica di `classify_definitive_exclusion`) vengono **scartati senza segnale** dal converter, e l'evento finisce come codice non categorizzato. Il ramo peggiore del rubric ("scarto silenzioso = perdita di dato al publish") si applica ai metadati, non all'intero evento.

**Ciò che il debito NON è** (per costruzione, verificato): l'espulsione definitiva **non** viene mai contata come punteggio — al publish il punteggio viene da `scores.final_score`, non dagli eventi, e `EXCLUSION_DEF` non è in `SCORE_EVENT_CODES` (solo `GOAL`). E **non** corrompe il conteggio fouled-out/over-limit: `count_exclusions_per_player` opera sul default `EXCLUSION_20`, quindi una definitiva **non** viene poolata fra le tre esclusioni di 20 secondi. Questa separazione dei conteggi è la ragione di design del tipo a sé, e regge.

**Perché severità media e non alta:** blast radius oggi **nullo**. Le uniche sorgenti di eventi `EXCLUSION_DEF` sono il prompt V3.4 — **non** default in produzione (default resta V2/V3, §8.12) — e il referto 8, che è `NEEDS_REVIEW` e **non** pubblicato. Nessun `EXCLUSION_DEF` ha mai raggiunto il publish su prod. È perdita di dato latente e reale, su un percorso vivo, ma senza esposizione corrente e con i contatori critici (punteggio, fouled-out) provatamente non toccati — stessa fascia di §10.30/§10.31.

**Condizione di chiusura (integrazione nella pipeline pubblicabile):** (a) aggiungere `EXCLUSION_DEF` ai `DEFAULT_EVENT_TYPES` con `is_score=False`; (b) creare/seedare un `SportEventConfig` con label leggibile per la pallanuoto così che `display_label` non mostri il codice grezzo; (c) portare `regulation_article` e la classificazione fino a `MatchEvent` (nuovi campi o `notes` strutturate) invece di scartarli in `get_events_data`, con la relativa migration; (d) i test di publish che coprano un evento `EXCLUSION_DEF` riconciliato e uno non riconciliato. Fino ad allora V3.4 resta prompt di misura e il referto 8 non va pubblicato a livello FULL con eventi definitivi attesi.

**Aggiornamento 2026-07-23 — verifica `RED_CARD` ↔ `EXCLUSION_DEF`: sono lo STESSO evento reale, e questo cambia il disegno della chiusura.** Verificato sul codice, non per inferenza:
- **`RED_CARD` è già un tipo canonico pubblicabile.** È fra i `DEFAULT_EVENT_TYPES` ([matches/event_types.py:8,15](../matches/event_types.py), label "Cartellino Rosso", `is_score=False`) ed è **proiettato in pagina pubblica**: `MatchDetailView` lo filtra e lo mostra (`red_cards`, [matches/views.py:46](../matches/views.py)) quando `events_published`. A differenza di `EXCLUSION_DEF`, `RED_CARD` ha un **blocco di template dedicato** (🟥 "Cartellini Rossi", [templates/matches/match_detail.html](../templates/matches/match_detail.html)), mentre un `EXCLUSION_DEF` cadrebbe nel ramo generico `other_events`. **Correzione 2026-07-23:** `display_label` **non** trova però un'etichetta leggibile nemmeno per `RED_CARD` — consulta solo `SportEventConfig`, tabella **vuota** su dev e prod (verificato read-only), e ripiega sul codice grezzo; `EVENT_LABELS`/`get_event_label` ([matches/event_types.py:176-182](../matches/event_types.py)) non è chiamato dalla resa. Il punto etichetta è quindi **scorporato nel nuovo debito §10.38** e vale anche per `RED_CARD`.
- **Il prompt V3 emette `RED_CARD` di suo, da sempre.** `RED_CARD` è nell'enum `"type"` del prompt base V3 (`...|YELLOW_CARD|RED_CARD|TIMEOUT|...`, [vision_providers.py](../matches/services/vision_providers.py)), presente **fin da V3** — non insegnato da V3.4. V3.4 aggiunge solo `TIMEOUT` ed `EXCLUSION_DEF` all'enum; `RED_CARD` è ereditato. Nell'end-to-end di produzione del 2026-07-23 (V3, §8.21) il modello ha infatti emesso `RED_CARD` per l'espulsione definitiva del referto 8.
- **In pallanuoto il cartellino rosso È l'espulsione definitiva.** `RED_CARD` (tipo generico multi-sport) ed `EXCLUSION_DEF` (tipo specifico con `regulation_article`/`sanction_sigla`) descrivono **lo stesso evento reale**: l'EDCS. La ragione di design del tipo a sé — separarlo da `EXCLUSION_20` per non corrompere il conteggio fouled-out — **regge comunque** (né `RED_CARD` né `EXCLUSION_DEF` sono contati fra le esclusioni di 20 secondi), quindi mappare `EXCLUSION_DEF` su `RED_CARD` non tocca quel conteggio.

**Conseguenza sul disegno (NON riprogettata in questo giro — da ratificare):** la chiusura **non** è più "rendere canonico un tipo parallelo `EXCLUSION_DEF`" (che duplicherebbe `RED_CARD`, già canonico e già mostrato, sullo stesso evento), ma **"arricchire il `RED_CARD` esistente con i metadati sanzione"**: (a) al converter, **mappare** `EXCLUSION_DEF` → `RED_CARD` (o riconoscere che l'estrazione V3 già produce `RED_CARD`); (b) portare `regulation_article` + `sanction_sigla` + la classificazione da `classify_definitive_exclusion` fino al `MatchEvent` `RED_CARD` (nuovi campi o `notes` strutturate), invece di scartarli; (c) test di publish su un `RED_CARD`/EDCS riconciliato e uno non riconciliato. Non serve più un nuovo tipo nei `DEFAULT_EVENT_TYPES` (`RED_CARD` c'è già). **Correzione 2026-07-23:** serve invece **ancora** una via che porti un'etichetta leggibile all'utente — `SportEventConfig` è **vuota** in entrambi gli ambienti (verificato read-only) e `display_label` ripiega sul codice grezzo anche per `RED_CARD`; questo punto etichetta **non** è annullato dal nuovo disegno ma **scorporato nel nuovo debito §10.38**. La condizione di chiusura (a)/(b) sopra va quindi **rivista** in questo senso alla prossima presa in carico; il resto del debito (perdita silenziosa dei metadati al converter) è invariato.

### §10.36 Badge "AI Engine v2" nella dashboard — CHIUSA 2026-07-23 → [DEBITI_CHIUSI.md](DEBITI_CHIUSI.md) §10.36

Chiusa rimuovendo il numero di versione dal badge ([templates/accounts/dashboard.html:164](../templates/accounts/dashboard.html), `AI Engine v2` → `AI Engine`): resta il solo branding del Discovery, decorrelato dalla versione del prompt OCR come già registrato. Dettaglio e riferimenti in [DEBITI_CHIUSI.md](DEBITI_CHIUSI.md) §10.36.

### §10.37 Gli eventi senza `player_id` vengono scartati in silenzio al publish — DEBITO APERTO 2026-07-23 (severità media)

> **Severità:** media · **Aperta dal:** 2026-07-23 · **Condizione di chiusura:** decisione esplicita sul destino degli eventi team-level e degli eventi non riconciliati (persistere con `player` null? scartare ma con warning visibile in review?), e sua implementazione.

`publish_report` crea il `MatchEvent` **solo** se `ed["player_id"]` è valorizzato ([matches/services/publishing_service.py:305](../matches/services/publishing_service.py)). Conseguenze verificate sul codice:

- I **TIMEOUT**, che per contratto hanno `player_name` null (il timeout è della squadra, non del giocatore), **non vengono MAI persistiti** dalla pipeline OCR: non riconciliano a nessun `player_id`, quindi cadono nel ramo di scarto.
- Un'**espulsione definitiva / cartellino rosso** che non riconcilia per nome viene **scartata senza traccia né warning**: nessun log a livello review, nessun blocker.

**Rilevanza di prodotto:** i timeout sono elencati nel [BLUEPRINT](BLUEPRINT.md) fra le statistiche di livello Base promesse (§7.4.3). La riconciliazione avviene **per nome e non per calottina** ([matches/services/converters.py:59-60](../matches/services/converters.py)), il che allarga la superficie del problema: anche un evento con giocatore reale, ma con nome letto in modo divergente dal roster, cade nello stesso scarto silenzioso.

**Condizione di chiusura:** decidere e implementare il destino (a) degli eventi **team-level** (timeout: persistere con `player` null?) e (b) degli eventi **non riconciliati** (scartare ma con un warning visibile in review, invece che in silenzio?).

### §10.38 `display_label` mostra il codice tecnico perché `SportEventConfig` è vuota — DEBITO APERTO 2026-07-23 (severità media)

> **Severità:** media · **Aperta dal:** 2026-07-23 · **Condizione di chiusura:** le etichette degli eventi arrivano all'utente in forma leggibile in entrambi gli ambienti (dev e prod), per una via esplicita e testata.

`display_label` ([matches/models.py:139-156](../matches/models.py)) consulta **solo** `SportEventConfig` e, come fallback, restituisce `self.event_type` (il codice grezzo). La tabella `SportEventConfig` è **VUOTA** sul DB dev (verificato read-only nel giro di recon del 2026-07-23) **e anche su prod** (verificato read-only in questo giro: `count() == 0` in entrambi gli ambienti). `EVENT_LABELS` / `get_event_label` ([matches/event_types.py:176-182](../matches/event_types.py)) **non** risulta chiamato dalla resa in pagina.

**Conseguenza:** un evento pubblicato oggi mostra all'utente la **stringa tecnica** (es. `"RED_CARD"`) nel punto in cui `{{ event.display_label }}` è reso, anche se il blocco di template resta visivamente corretto (icona e intestazione dedicate). È **testo rivolto al pubblico**, non un dettaglio interno. Scorporato da §10.35 (dove la claim "`display_label` trova l'etichetta per `RED_CARD`" è stata corretta): il punto etichetta è comune a `RED_CARD` ed `EXCLUSION_DEF` e vale a prescindere dall'arricchimento dei metadati sanzione.

**Condizione di chiusura:** le etichette degli eventi arrivano all'utente in forma leggibile in entrambi gli ambienti, per una via esplicita e testata (seed/config di `SportEventConfig` per la pallanuoto, oppure un fallback su `EVENT_LABELS` in `display_label`).
