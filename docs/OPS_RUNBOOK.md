# OPS Runbook — 2salti

Questo file raccoglie le procedure operative dell'infrastruttura 2salti: topologia degli ambienti, regole di allineamento fra home e deploy, trappole tecniche note, convenzioni di pulizia repo e regole metodologiche per le note di sessione. Non contiene né convenzioni di codice (quelle stanno in [CLAUDE.md](../CLAUDE.md)) né la visione di prodotto (quella sta in [BLUEPRINT.md](BLUEPRINT.md)); consultarlo quando si lavora sull'infrastruttura, sul deploy, sulla gestione del repo, o quando si chiude/riapre un problema nelle note di sessione. Si aggiorna man mano che emergono pattern operativi ricorrenti: se una lezione viene imparata due volte, probabilmente merita una voce qui.

## 1. Mappa ambienti

L'infrastruttura 2salti oggi è ospitata su una singola macchina Hetzner che serve il dominio `2salti.com`. Su quella macchina convivono due copie del repo, che è una topologia inusuale e va ricordata esplicitamente per non confondersi: `/home/alberto/` è l'ambiente di sviluppo locale dello sviluppatore, e `/opt/2salti-new/` è il deploy attivo da cui gira effettivamente il service in produzione. Sviluppo locale e produzione condividono quindi il filesystem — è un'asimmetria storica da cui è derivata la regola della sezione 2 di questo documento, ed è lo stato attuale con cui si lavora.

Il service systemd si chiama `2salti` e viene servito da Gunicorn con socket unix; Nginx fa da reverse proxy davanti al socket e gestisce TLS e reindirizzamento HTTPS. Il file `.env` con le credenziali di runtime vive nel deploy, in `/opt/2salti-new/.env`, mai nella home e mai nel repo. Gli static files raccolti con `collectstatic` vivono in `/home/alberto/staticfiles/` e sono serviti da whitenoise attraverso Gunicorn; i media uploadati dagli utenti vivono in `/home/alberto/media/`. Entrambi i path sono environment-specific e non vanno hardcoded nel codice — il codice legge `STATIC_ROOT` e `MEDIA_ROOT` dalle settings.

L'ambiente dev-remote dev.2salti.com è attivo su /opt/2salti-dev/, branch dev, con auto-pull ogni 2 minuti. L'ambiente di staging separato non è attivo. Qualsiasi procedura descritta in questo runbook assume i path elencati sopra come stato attuale; se cambiano — per migrazione, per introduzione di staging, per riconfigurazione del deploy — aggiornare prima di tutto questa sezione, perché tutte le sezioni successive vi fanno riferimento implicito.

Un dettaglio sulla topologia dei remote git, oggi semplice ma con una storia. Sia la home `/home/alberto/` sia il deploy `/opt/2salti-new/` hanno `origin` puntato direttamente a `github.com/8albe/2salti-django.git`: entrambi i repo parlano direttamente con GitHub, e la propagazione dei commit segue lo schema lineare `home → GitHub → deploy`. Questa è una semplificazione recente. Fino al 25 aprile 2026 il deploy aveva `origin` puntato al path locale della home (`file:///home/alberto`), generando una topologia a due salti `deploy → home → GitHub` con due rischi noti: commit nella home non pushati a GitHub finivano comunque in produzione al successivo pull del deploy, e commit atterrati su GitHub via altri canali (PR merged via web, push da altre macchine) restavano invisibili al deploy finché qualcuno non li tirava prima nella home. Il problema #15 del 25 aprile ha allineato la topologia alla forma attuale, eliminando entrambi i rischi. La conseguenza pratica è che oggi un `git pull origin dev` sul deploy tira direttamente da GitHub, e qualsiasi divergenza fra home e GitHub diventa immediatamente visibile come divergenza fra deploy e GitHub — il deploy non fa più da specchio passivo della home.

## 2. Asimmetria home ↔ deploy

Il deploy `/opt/2salti-new/` non si autoallinea con `/home/alberto/`. Non esiste automazione, non esiste alert, non esiste monitoring che segnali la divergenza fra i due repo. Il 23 aprile 2026 abbiamo scoperto per caso che il deploy era tre commit indietro rispetto alla home, senza che nessuno se ne fosse accorto — asimmetria accumulata in meno di 24 ore attraverso commit fatti nella home e mai propagati al deploy. Non si era rotto nulla solo perché i commit riguardavano pulizia di artefatti non importati a runtime, ma l'assenza di visibilità sulla divergenza è il problema di fondo.

La regola operativa è semplice e va applicata a mano finché non esiste automazione: dopo ogni commit significativo sul ramo `dev` effettuato nella home, eseguire manualmente in `/opt/2salti-new/` il pull:

```bash
git pull origin dev
```

Se il pull tocca file di runtime — codice Python delle app, `config/settings.py`, un `gunicorn_config.py` committato, template, URL conf — o configurazione di servizio, far seguire il pull da un reload del service:

```bash
sudo systemctl reload 2salti
```

Se il pull tocca solo documentazione, test, fixture di dati o altri artefatti non letti dal runtime, il reload non serve e il deploy è allineato al momento in cui il pull termina. Nel dubbio, fare comunque il reload: il costo è minimo e il rischio di saltarlo è che una modifica di runtime non diventi attiva.

L'introduzione di un meccanismo di allineamento automatico — post-commit hook nella home che ricordi il pull, cron che rilevi divergenze, o qualsiasi altra soluzione equivalente — vive nel backlog come side-quest aperta. Finché non è implementata, la disciplina manuale è l'unico meccanismo; se la nota di sessione del giorno include un commit significativo e non menziona il pull sul deploy, è probabile che il deploy stia già accumulando deriva.

### 2.1 Workflow standard di sessione

Tre workflow da seguire in modo disciplinato ogni sessione.

**A. Sviluppo e deploy codice**

1. Lavora in `/home/alberto/` su branch `dev`.
2. `git push origin dev` — GitHub aggiornato.
3. Entro 2 minuti `dev.2salti.com` si aggiorna automaticamente (auto-pull attivo su `/opt/2salti-dev/`).
4. Testa su `dev.2salti.com`.
5. Quando OK: `git checkout master && git merge dev && git push origin master`.
6. Sul VPS: `cd /opt/2salti-new && git pull origin master` + `sudo systemctl reload 2salti` (o `restart` se cambia `ExecStart` o variabili d'ambiente).
7. `2salti.com` aggiornato — verifica con `curl -I https://2salti.com/` dopo `sleep 3` (vedi §12.2).

**B. Fine sessione — aggiornamento memoria**

1. Claude Code aggiorna i file in `docs/` toccati nella sessione (BLUEPRINT.md, SYLLABUS.md, OPS_RUNBOOK.md, session note).
2. Commit + push su GitHub (branch `dev`).
3. Sul PC Windows: Syncthing sincronizza automaticamente entro pochi minuti.
4. Obsidian mostra la situazione aggiornata.

**C. Approvazione modifiche memoria via Claude Code Work**

1. Claude Code Work deposita le modifiche proposte nella cartella `cowork/` sul PC.
2. Produce un riassunto: quali file, cosa ha cambiato (evidenziato con callout `> [!CHANGE]`).
3. Alberto legge in Obsidian e rimuove il callout dai blocchi che non approva.
4. Dice "approvato" — Claude Code Work sposta il contenuto ancora evidenziato nella cartella `alberto/`.
5. Alberto esegue `git add` + `git commit` + `git push` dei file approvati.

### 2.2 Meccanismo autopull dev — dettaglio tecnico

L'ambiente `dev.2salti.com` ospitato in `/opt/2salti-dev/` è allineato a GitHub via auto-pull schedulato. Diversamente dal deploy di produzione `/opt/2salti-new/` (sezione 2, allineamento manuale), qui la propagazione `GitHub → runtime` è automatica entro ~2-3 minuti dal push sul branch `dev`.

**Componenti systemd:**

- Timer `2salti-dev-autopull.timer` con `OnUnitActiveSec=2min` e `AccuracySec=10s`: scatta ogni 2 minuti circa rispetto alla fine dell'esecuzione precedente, con tolleranza di 10 secondi.
- Service `2salti-dev-autopull.service` di tipo `oneshot`, eseguito come `User=alberto` / `Group=www-data`, `WorkingDirectory=/opt/2salti-dev`.

**Comportamento per invocazione** (eseguito solo se `git ls-remote origin dev` restituisce un SHA diverso da `git rev-parse HEAD`):

1. `git pull --ff-only origin dev`
2. `manage.py migrate --noinput`
3. `manage.py collectstatic --noinput`
4. `sudo /bin/systemctl reload 2salti-dev.service` (richiede sudoers `NOPASSWD` per `alberto` sul comando specifico)

**Runtime service:** `2salti-dev.service` esegue gunicorn con SIGHUP-reload: il `reload` fa exit pulito dei worker, respawn, e reimporta WSGI (e quindi tutto il codice Python applicativo). Non è abilitato il flag `--reload` di gunicorn (no file watcher).

**Diagnostica:**

```bash
journalctl -u 2salti-dev-autopull.service -n 50         # log ultima esecuzione
systemctl list-timers 2salti-dev-autopull.timer        # prossimo trigger
```

**Limiti noti:**

- Se `manage.py migrate` fallisce, la pipeline si ferma allo step 2: il codice nuovo è già su disco (post step 1) ma il runtime non viene ricaricato. Sintomo: push avvenuto ma `dev.2salti.com` non riflette la modifica. Diagnosi via `journalctl -u 2salti-dev-autopull.service`.
- `git pull --ff-only` aborta se il working tree di `/opt/2salti-dev/` è dirty. Il dev environment non dovrebbe avere edit locali; verificare con `git -C /opt/2salti-dev status`.
- Se il NOPASSWD sudoers per il reload si rompe (ad esempio dopo edit a `/etc/sudoers.d/`), lo step 4 fallisce silenziosamente: i worker continuano a servire il codice vecchio. Diagnosi nello stesso log del service.
- Race window di ~1 secondo fra fine `migrate` e SIGHUP. In quel breve intervallo i worker vecchi servono codice vecchio su DB già migrato — finestra trascurabile in dev, ma non assumibile sicura per produzione.

Tempo tipico push → runtime aggiornato: meno di 3 minuti. La produzione resta manuale per disegno (vedi §2 e workflow A in §2.1).

### 2.3 Lineage `prod` ↔ `origin/master` divergente by design — e chiusura FASE 3 git (2026-06-02)

Il deploy di produzione `/opt/2salti-new/` **non pusha mai** per policy (vedi workflow A in §2.1: no push da prod). Di conseguenza la sua lineage `master` accumula commit prod-local — per esempio il merge `--no-ff` che chiude BUG-001, `01427d59` — che **non esistono e non sono raggiungibili** da `/home/alberto/` né da `origin`: in home `git cat-file -t 01427d59` (o `0876243a`) risponde `Not a valid object name`. È atteso, non un errore e non un history-rewrite.

L'allineamento di `origin/master` si fa **ricostruendo** il merge `dev → master` da home e pushando da home, mai propagando le SHA di prod. Esito strutturale: `prod master` e `origin/master` restano **contenuto-equivalenti ma con SHA diverse**, by design. In una sessione futura, **non interpretare lo scarto di SHA prod ↔ origin come regressione o rewrite**: confrontare il *contenuto* (`git diff <sha_a> <sha_b>`, atteso vuoto), non le SHA.

**Chiusura FASE 3 git (2026-06-02)** — i 4 debiti git (tracciati nella session note 28-mag, non nell'§10) risolti:

1. `master` home behind prod di 1 commit → **CHIUSO**: home `master` ricostruito a `7d1d135` via merge `--no-ff dev→master`, contenuto-equivalente a prod.
2. `origin/master` behind di 54 commit (Sprint A/B/C + BUG-001 + syllabus 12/14/15) → **CHIUSO**: pushato `c4b68da..7d1d135`; `git diff master b58506d` vuoto, suite 264 OK / 2 skipped.
3. Branch `dev` locale residuo su `/opt/2salti-new/` (`6159c352`, artefatto storico) → **CHIUSO**: `git branch -D dev` su prod (HEAD prod = `master`, delete sicura).
4. Untracked `find_coach.py` / `find_coach2.py` su `/opt/2salti-dev/` (script debug HEAD_COACH) → **CHIUSO**: rimossi.

Questi erano debiti **git/infrastruttura**, distinti dai debiti di **codice** DEBT-001..004 in §10.6, che sono stati CHIUSI il 2026-06-19 (vedi §10.6).

**Aggiornamento 2026-06-12 (propagazione Macro 16, §10.8):** prod è stato riagganciato a `origin/master` via `git fetch` + `git reset --hard origin/master` — ora prod HEAD e `origin/master` sono **SHA-identici** (`7d8a937f`) e la lineage prod-local accumulata (incluso `01427d59`) è stata abbandonata. La regola di questa sezione — confrontare il **contenuto**, non le SHA — resta valida per eventuali future divergenze.

### 2.4 Deploy reale con `dev` ↔ `master` divergenti — merge `--no-ff` (2026-06-19)

Quando `master` ha accumulato merge pubblici **mai rifusi in `dev`** e `dev` ha il payload nuovo, i due branch sono **divergenti** (la merge-base reale non è il tip di nessuno dei due) e il deploy **non** è un fast-forward. Procedura usata per il giro slug `core/0019` + Macro 3 filtro stagione:

- **Test-merge in worktree scratch** prima del merge reale: si verifica il tree risultante senza sporcare i branch.
- **Merge `--no-ff` `dev` → `master`** (vero merge, niente ff): il tree finale deve risultare **`== dev`** su tutti i path del payload. Nessuna riscrittura di storia. Esito di questo giro: `master` = `e0c928f` (commit di merge), `dev` resta al suo tip — **contenuto-equivalenti, SHA diverse** (coerente con §2.3).
- **Dry-run della migration** su **copia scratch del DB prod**, verificando **SHA-256 del DB prod reale invariato** prima/dopo il dry-run.
- **Backup fresco e separato** pre-apply (`db.sqlite3.bak.predeploy-YYYYMMDD`), distinto dai backup di deploy precedenti, che restano intoccati.
- **`migrate` scoped alla singola migration** (`migrate core 0019`), non `migrate` globale.

**Gotcha — verificare la merge-base reale, non la narrativa.** La session note (o il contesto di sessione) può contenere affermazioni topologiche **errate**: in questo giro "`dev` discende da `master`" era falso (erano divergenti dalla merge-base `b6d8ae2`). Prima di scegliere ff vs merge, controllare `git merge-base dev master` e `git log --oneline master ^dev` / `dev ^master`; **mai** dedurre dal racconto.

**Gotcha — `curl -k` maschera lo stato reale del certificato.** Un `curl -k` "funziona" anche con un certificato scaduto: non è una verifica TLS. Per confermare l'SSL usare `openssl s_client -connect host:443 -servername host </dev/null | openssl x509 -noout -dates -issuer`, non dedurre da un `curl -k`.

**Gotcha — il delta `master..dev` si calcola solo da `/home/alberto/`.** I conteggi `git rev-list --count master..dev` / `git log master..dev` sono affidabili **solo nella home**, dove `master` e `origin/master` sono freschi (oggi entrambi `e0c928f`, merge-base `7df3643a`, delta reale **23 commit**). Sul **dev box** `/opt/2salti-dev/` i ref `master`/`origin/master` sono **stantii** (l'autopull aggiorna solo `dev`) → lo stesso comando lì restituisce numeri **spuri molto più alti**. Prima di citare un delta in una nota, calcolarlo **dalla home**, mai dal dev box.

### 2.5 Deploy 2026-06-30 — `f697c0f` → `24bfc62` (Macro 9/17/18, 69 commit)

Deploy reale dev→prod con lo stesso pattern di §2.4 (merge `--no-ff` `dev`→`master` da home + push; pull **ff** su prod; `migrate` manuale gated dopo backup DB). Prod portato da `f697c0f` a **`24bfc62`** (69 commit). Migration applicate **0020/0021/0022**: `0021` è una data-migration che ha toccato **1 row** (pallanuoto `#00ffff`→`#2563eb`); `0022` crea la tabella `core_sponsor` (Macro 9). `collectstatic` ha **rigenerato il manifest** (load-bearing pre-restart). Smoke end-to-end GREEN: HTTP 200, login→`/accounts/dashboard/`, tema pallanuoto blu confermato.

**Learning — gate del backup = integrity, non byte-identità.** Il criterio di validità di un backup DB pre-deploy è **`PRAGMA integrity_check` + dimensione plausibile**, **non** l'uguaglianza byte sorgente==backup. Un `.backup` di SQLite preso su un DB live è un backup **valido e consistente** ma **non byte-identico** alla sorgente (il WAL/lo stato live evolvono): pretendere l'uguaglianza byte fa fallire il gate su un backup buono.

**Learning — il file `.sha256` deve contenere SOLO la riga del backup.** Se nel `.sha256` si mette anche la riga del DB live, al rollback `sha256sum -c` **fallisce legittimamente sulla riga del db live** (che nel frattempo è cambiato, com'è giusto) e maschera l'esito reale sul backup. Il checksum va calcolato e verificato **solo sull'artefatto immutabile** (il backup), una riga sola.

**Correzione — SSL `2salti.com`/`dev.2salti.com` VALIDO (non scaduto).** Il certificato è **valido**, rinnovato il **14-giu** (vedi §10.9, Let's Encrypt 2026-06-14 → 2026-09-12). La nota "SSL forse scaduto" rimasta in coda da Macro 16 è **stale**: era vera allo smoke post-Macro 16 ma chiusa il 14-giu. L'automazione di rinnovo ancora rotta riguarda i **domini di Damiano**, non quelli di Alberto (cron `certbot-2salti` scoped, §10.9).

### 2.6 Deploy 2026-07-19 — `2276290` → `d7bf3cd` → `394e7fd` → `62f5a16` (filone OCR, migration distruttiva `0017`)

Deploy reale dev→prod con lo stesso pattern di §2.4/§2.5 (merge `--no-ff` `dev`→`master` da home + push; pull ff su prod; `migrate` manuale gated dopo backup). Tre merge in giornata: **`d7bf3cd`** (filone OCR completo, 26 commit: Gemini provider unico, rimozione `OCRRawResponse` con `matches/0017`, fix crash no-match, guardia di stato su close referto digitale), **`394e7fd`** (timeout gunicorn 300s + config versionate in `deploy/gunicorn/`, vedi §3.16 e §9), **`62f5a16`** (fix `KeyError 'match'` nella changeform admin di `MatchReport`, `matches/forms.py` — `f408cab`). Prod portato da `2276290` a **`62f5a16`**.

**Rituale eseguito per la `0017`** (distruttiva, `DeleteModel` → `DROP TABLE matches_ocrrawresponse`):

1. **Backup DB fresco pre-apply**; gate di validità = `PRAGMA integrity_check` + dimensione plausibile, **non** byte-identità (learning §2.5); file `.sha256` con la **sola riga del backup**, una riga.
2. **Verifica che `matches_ocrrawresponse` fosse vuota** su prod (mai scritta dal path vivo — la raw response vive in `MatchReport.raw_api_response`).
3. **Dry-run della migration su copia dell'intero progetto in `/tmp`** — non basta puntare una env var a una copia del DB, perché il path del DB è hardcoded in `config/settings.py` (gotcha §3.15) — con SHA256 del DB prod reale verificato **invariato** prima/dopo il dry-run.
4. **Restart del service PRIMA del `migrate`.** Il pull aveva già portato su disco il codice nuovo (che non referenzia più `OCRRawResponse`), ma i worker in RAM giravano ancora col codice vecchio che conosceva la tabella. Riavviare prima del `DROP` garantisce che nessun processo attivo referenzi la tabella al momento della cancellazione; l'ordine inverso (migrate → restart) lascia una finestra in cui il codice vecchio può toccare una tabella già droppata.
5. `migrate` scoped sulla `0017`, poi smoke.

**Smoke OCR reale su prod — esito.** Lo smoke con Gemini vivo ha fatto emergere in cascata i due timeout mancanti: prima il **timeout gunicorn 30s di default** (worker abortito a metà chiamata Gemini ~80s → 500 al client, referto appeso in `PROCESSING`), poi — alzato quello a 300s — il **`proxy_read_timeout` nginx 60s di default** (504 al browser mentre il backend completava comunque). Dettaglio e regola in §3.16. Dopo entrambi i fix, estrazione end-to-end **completata su prod** (report 16, `gemini-2.5-pro`); l'esito ha però evidenziato una **divergenza di estrazione ad alta confidence** sullo stesso match rispetto a un report storico — caso registrato nel syllabus Macro 8 come motivazione del gold standard. I referti rimasti appesi in `PROCESSING` sono stati sbloccati a mano (comando in §10.19; guardia automatica mancante = debito, parte della Macro 22).

## 3. Trappole tecniche note

### 3.1 `git rm --cached` + file dirty = pull abortito

Il problema emerge quando in un repo (tipicamente la home) viene eseguito `git rm --cached <file>` per smettere di tracciare un file mantenendone il contenuto su disco, e successivamente si prova a pullare quel commit in un altro repo (tipicamente il deploy) dove lo stesso file ha modifiche uncommitted sul working tree. Git aborta il merge con il messaggio:

```
error: Your local changes to the following files would be overwritten by merge:
  <file>
Please commit your changes or stash them before you merge.
```

Il messaggio non è autoesplicativo sulla causa. Quello che sta succedendo è che git tratta `--cached` come un'operazione che "tocca" il file ai fini del merge, anche se formalmente non modifica il contenuto del file su disco — tocca l'indice, e questo basta a rendere il merge non più fast-forward rispetto alle modifiche uncommitted locali. Non si può risolvere con uno `stash` se l'obiettivo è preservare il contenuto dirty come untracked post-pull, non si vuole committare nel deploy (il deploy non è un ramo di sviluppo), e `git checkout --theirs` alla cieca è troppo grezzo.

La soluzione pulita è una strategia reset-then-restore in quattro passi:

1. **Backup safety del file dirty**, fuori dal percorso git e fuori dal deploy. La location standard è `/var/tmp/`, con naming datato e contestualizzato:
   ```bash
   cp -p <file> /var/tmp/<file>.<context>-safety-YYYYMMDD
   ```
2. **Riportare il working tree allo stato indice**, così il merge non ha più conflitti:
   ```bash
   git checkout HEAD -- <file>
   ```
3. **Eseguire il pull pulito**:
   ```bash
   git pull origin dev
   ```
4. **Restaurare il contenuto dirty dal backup**:
   ```bash
   cp -p /var/tmp/<file>.<context>-safety-YYYYMMDD <file>
   ```

Dopo lo step 4, il file è untracked sul working tree. Se è coperto da un pattern nel `.gitignore` del repo — ed è il caso naturale quando si arriva a questa procedura, perché il `git rm --cached` a monte è quasi sempre accompagnato dall'aggiunta del pattern — non appare nemmeno in `git status`. Se non è coperto, va aggiunto al `.gitignore` prima di committare qualsiasi altra cosa, altrimenti al prossimo `git add -A` si ritorna alla situazione di partenza.

Una nota specifica su Gunicorn, perché la procedura è stata inaugurata proprio su `gunicorn_config.py` il 23 aprile 2026. Gunicorn carica la configurazione allo startup del processo master e non rilegge il file durante la vita del processo. Il "buco temporale" fra lo step 2 (working tree riportato alla versione indice, senza logging) e lo step 4 (restauro del contenuto dirty con logging) è quindi innocuo per il runtime, anche se durasse minuti: la config attiva in memoria resta quella caricata allo startup. Il rischio scatta solo se nel mezzo si fa un restart del service — da evitare finché il file non è stato restaurato.

### 3.2 `git add` con path errato fallisce silenziosamente

Il comando `git add <path>` non restituisce alcun errore se il path passato non corrisponde a nessun file presente nel working tree, e non restituisce alcun errore se il path corrisponde a un file ma quel file è ignored da `.gitignore`. In entrambi i casi il comando termina con exit code 0 e non produce output, dando l'impressione che l'operazione sia avvenuta — quando in realtà nessun file è stato aggiunto all'indice.

Il problema è doppiamente insidioso. Il caso path-errato emerge tipicamente per typo, abbreviazione mnemonica, o copia-incolla da una sessione precedente in cui la directory di lavoro era diversa. Il caso ignored-by-gitignore emerge quando si vuole versionare consapevolmente un file che ricade sotto un pattern generico del `.gitignore` (per esempio `*.service` versionato intenzionalmente sotto `deploy/systemd/`), e ci si dimentica che serve un'eccezione mirata nel `.gitignore` stesso prima di poter aggiungere il file.

La regola operativa è semplice: dopo ogni `git add`, eseguire `git status` come step esplicito per verificare che il file (o i file) compaia effettivamente nella sezione "Changes to be committed". Mai dare per scontato l'effetto di un `git add`. Costa tre secondi, evita di scoprire l'omissione dopo il commit — quando il file è invisibile a chiunque pulli il repo, ma sembra a posto sul terminale di chi ha committato.

Per il caso specifico ignored-by-gitignore, il comando diagnostico è `git add --dry-run <file>`: se il file appare nell'output, sarà aggiunto; se non appare, è ignored e serve agire sul `.gitignore` prima. Vedi sezione 3.3 per il dettaglio sul comportamento di `git check-ignore`, che non è il comando giusto per questo check.

### 3.3 `git check-ignore -v` restituisce il pattern, non un boolean

Il comando `git check-ignore -v <file>` è spesso usato come check rapido per capire se un file è ignored dal `.gitignore` prima di provare a fare `git add`. Il problema è che il suo output non risponde alla domanda "è ignored sì o no", ma alla domanda "se è ignored, quale pattern è responsabile". Le due domande sembrano equivalenti, non lo sono.

Quando il file è ignored, l'output è del tipo `.gitignore:42:*.service	deploy/systemd/2salti.service`, che mostra il file `.gitignore` responsabile, la riga del pattern, il pattern, e il file ignored. Quando il file non è ignored, l'output è semplicemente vuoto, e l'exit code è 1. Il problema è il caso intermedio: se il file non esiste, o se il path è sbagliato, l'output è ugualmente vuoto e l'exit code è ugualmente 1, indistinguibile dal caso "file esiste ma non è ignored". Non c'è modo di distinguere "non ignored" da "non esiste" con `check-ignore` da solo.

Il comando giusto per il check funzionale "questo file finirà nell'indice se faccio `git add`" è `git add --dry-run <file>`. Se il file appare nell'output, sarà aggiunto. Se non appare e l'exit code è zero, è ignored o non esiste — ma in questo caso il dubbio si risolve banalmente con `ls <file>`. Il `dry-run` ha il vantaggio di rispondere alla domanda operativa diretta, senza il livello di indirezione del "quale pattern".

`check-ignore` resta utile esattamente per il suo caso d'uso nominale: dato un file che si sa ignored, capire quale pattern lo sta ignorando, per poi decidere se modificare il pattern o aggiungere un'eccezione mirata. Per qualsiasi altro uso, `dry-run` è più diretto e meno ambiguo.

### 3.4 Attributi su oggetti Django dopo `delete()`

Quando un metodo Django ORM `instance.delete()` viene eseguito su un oggetto, l'attributo `pk` (e quindi `id`) dell'oggetto in memoria viene riportato a `None`. Gli altri attributi del modello — campi caricati dal DB come `name`, `score`, foreign key risolte — restano accessibili come valori in memoria, perché Python non sa né si interessa che il record sottostante non esista più. Solo `pk` viene esplicitamente azzerato dall'ORM, come parte della contract di `delete()`.

La conseguenza pratica è una trappola in tutti i loop di cancellazione che fanno logging dopo la `delete()`. Pattern tipico del bug:

```python
for match in matches_to_delete:
    match.delete()
    logger.info(f"Deleted match id={match.id} home={match.home} score={match.score}")
```

L'output sarà `Deleted match id=None home=Foo score=12-8` per ogni record, con `home` e `score` corretti e `id=None` su tutti. Il logging è strutturalmente inutile ai fini di audit — non si può ricostruire quale record specifico è stato cancellato — e l'errore è silenzioso: nessuna eccezione, nessun warning, solo dati persi.

Il pattern corretto è la cattura dei valori loggati in variabili locali prima della delete:

```python
for match in matches_to_delete:
    match_id = match.id
    match_home = match.home
    match_score = match.score
    match.delete()
    logger.info(f"Deleted match id={match_id} home={match_home} score={match_score}")
```

La regola di review è esplicita: per ogni campo che il logger legge dopo l'operazione che invalida l'oggetto, verificare che sia stato catturato in variabile locale prima. La verifica va fatta su tutti i campi loggati, non solo su quelli più "ovviamente fragili" — è facile dimenticare proprio `id` perché è il PK e si dà per scontato che ci sia sempre. Dopo `delete()` non c'è più. La stessa logica vale, in misura minore, per altre operazioni che invalidano lo stato dell'oggetto: `bulk_delete`, `cascade`, `clear()` su relation manager. In dubbio, cattura.

### 3.5 `from X import Y` dentro una funzione = scoping locale per tutta la funzione

Python è static-scoped: `from X import Y` *all'interno* di una funzione assegna `Y` come nome locale per l'**intera** funzione, non solo dalla riga del re-import in poi. Questo maschera l'import globale anche nei rami che non eseguono mai il re-import, causando `UnboundLocalError` in branch apparentemente non correlati.

Sintomo classico: una vista Django con un re-import locale in un branch (es. POST handler) che rompe il branch GET con `UnboundLocalError: local variable 'X' referenced before assignment`, anche se GET non passa mai per il re-import.

Diagnosi: `grep -n "^\s*from .* import .*" <file>` filtrato sul nome simbolo sospetto. Cercare *tutte* le occorrenze nel file, non fermarsi alla prima. Una funzione lunga può avere re-import nascosti in branch poco esercitati.

Cosa fare: rimuovere tutti i re-import locali, lasciare solo l'import globale a inizio file. Se serve davvero shadowing locale (raro), rinominare la variabile.

Caso reale: fix `ce4df80` su `report_review` — tre re-import di `MatchEvent` in branch diversi, ricognizione iniziale ne aveva trovati solo due, il terzo è emerso dall'estensione del check al resto del file.

### 3.6 `rebuild_standings` exit code 0 anche su errore interno

Il management command `rebuild_standings` ([core/management/commands/rebuild_standings.py](../core/management/commands/rebuild_standings.py)) termina con exit code 0 anche quando il rebuild interno fallisce. Le eccezioni dentro il loop di ricostruzione vengono catturate e logate ma non risalgono al codice di uscita: dal punto di vista di systemd, di un cron, o di un wrapper script il comando è "andato bene" anche quando le `LeagueStanding` non sono state aggiornate.

Sintomo: `echo $?` restituisce `0` ma il monitor di integrità segnala discrepanze sulla lega che credevi appena ricostruita.

Cosa fare: non usare l'exit code come segnale di successo. Verificare lato dati con una query diretta sulle `LeagueStanding` della lega target, o concatenare `monitor_integrity --league <id>` come check di chiusura. In alternativa, cercare le stringhe `ERRORE` o `OK` nello stdout del comando.

### 3.7 `monitor_integrity` exit code 1 è semantico, non un errore

`monitor_integrity` esce con codice 1 quando trova discrepanze nelle `LeagueStanding` — è il modo in cui comunica "ho fatto il check e ho trovato `MISSING_RECORD` o `DATA_MISMATCH` da rivedere", non "il comando è crashato". Per questo motivo il systemd unit `2salti-monitor.service` ha `SuccessExitStatus=1` esplicito: senza quella riga systemd marcherebbe l'unit come `failed` ad ogni esecuzione che trova drift.

Cosa fare: trattare exit code 1 di `monitor_integrity` come informazione semantica, non come failure. Se si scrive un wrapper o un alert sopra a questo comando, replicare la stessa convenzione (`SuccessExitStatus=1` o equivalente lato shell).

Coppia con §3.6: gli ops command di questo progetto hanno exit code inaffidabili in entrambe le direzioni — `rebuild_standings` non segnala errori veri come tali, `monitor_integrity` segnala stato come "errore". Mai dedurre il successo o il fallimento di un'operazione dal solo exit code dei nostri management command.

### 3.8 `monitor_integrity` in run manuale invia notifiche

Il management command `monitor_integrity` invia mail (e Telegram, se configurato) ad ogni esecuzione che trova discrepanze, indipendentemente dal fatto che l'esecuzione sia partita dal timer systemd o lanciata a mano da Django shell per diagnostica. Conseguenza: se durante un'indagine si lancia il comando da terminale per "vedere lo stato", si sveglia la stessa pipeline di notifiche del cron, generando rumore per chi riceve gli alert e potenzialmente svegliando qualcuno alle tre di notte.

Cosa fare: per audit silenzioso usare direttamente `DataIntegrityService.check_league_standings(league)` da Django shell:

```python
from core.models import League
from matches.services.integrity_service import DataIntegrityService
issues = DataIntegrityService().check_league_standings(League.objects.get(id=<id>))
```

Restituisce la lista di issue senza side effects. Il management command resta lo strumento giusto solo quando si *vuole* generare l'alert.

### 3.9 `gunicorn_config.py` auto-caricato se presente nel CWD

Gunicorn cerca un file `gunicorn_config.py` nella working directory all'avvio e lo carica automaticamente se lo trova, anche quando il service passa esplicitamente `--config /path/to/altro_config.py`. Il config esplicito vince sui valori in conflitto, ma direttive presenti solo nel `gunicorn_config.py` di CWD entrano nel runtime senza che nessuno le abbia chieste.

Il rischio concreto è in due scenari: (a) `WorkingDirectory=` nel unit file viene cambiato e punta a una directory che contiene un `gunicorn_config.py` legacy o orfano — è esattamente l'incidente del 23 aprile 2026 risolto col problema #3, dove il config in repo era inerte ma stava per tornare attivo a un cambio di working dir; (b) il `gunicorn_config.py` nel repo viene rinominato o spostato e qualcuno ne ricrea uno in quella posizione per altri motivi.

Cosa fare: tenere il `gunicorn_config.py` nel repo coerente con il config esplicito caricato via `--config`, oppure non averlo affatto in CWD del service. Dal 2026-07-19 il file alla root del repo è **gitignorato** (nella home non esiste proprio) e le copie canoniche vivono in `deploy/gunicorn/{prod,dev}/` col pattern §9: sui box di deploy il file in CWD **è** quello caricato via `--config`, quindi lo scenario (b) resta l'unico rischio residuo. Verificare a freddo con `lsof -p <gunicorn_pid> | grep config` o leggendo l'output di `systemctl cat 2salti` per vedere `WorkingDirectory` e `ExecStart` insieme.

### 3.10 Tag Django con newline interno emesso come testo letterale

Il template tokenizer di Django non usa il flag `re.DOTALL` quando matcha tag template. Conseguenza: un tag scritto su più righe nel sorgente template — tipico esito di un autoformatter HTML che manda a capo `}}` per rispettare la max line length — non viene riconosciuto come tag e viene emesso come testo grezzo nella pagina renderizzata.

Esempio del bug, scoperto il 2 maggio 2026 sulla classifica pubblica:

```django
{{ entry.goals_against
}}
```

renderizza letteralmente `{{ entry.goals_against }}` nella pagina invece del valore numerico.

Cosa fare: tenere ogni tag template `{{ ... }}` o `{% ... %}` su una riga sola. Configurare l'editor o il prettier HTML per non spezzare le righe dentro questi delimitatori. In code review su template, segnalare ogni tag che attraversa newline.

Corollario (scoperto 2026-06-23, regressione introdotta in `07122e0`): i delimitatori `{% ... %}` e `{{ ... }}` vengono parsati da Django **anche dentro i commenti HTML** `<!-- ... -->` — il commento HTML è opaco al browser, non al template engine. Un commento che cita un tag a scopo descrittivo (es. `<!-- {% static %} risolve... -->`) viene compilato come tag reale: se è malformato (qui `static` senza argomento) alza `TemplateSyntaxError` a compile-time e rompe il rendering di ogni pagina che estende quel template, dev/prod inclusi. Cosa fare: nei commenti non scrivere mai la sintassi `{% %}`/`{{ }}` letterale — parafrasare ("il tag static"), oppure usare il commento Django `{# ... #}` (che invece è opaco al parser), oppure `{% templatetag %}`.

### 3.11 "1, 2, 4 senza 3" è la firma del refactor incompleto

Quando in un blocco di codice o in un test trovi una sequenza numerica con un buco — commenti `# 1.`, `# 2.`, `# 4.` senza `# 3.`, oppure variabili `step1`, `step2`, `step4` senza `step3` — quasi sempre il pezzo mancante esisteva e un refactor lo ha rimosso senza aggiornare la numerazione né i punti che vi si appoggiavano. Il bug del 28 aprile 2026 sul `staff_dashboard` (`NameError: stuck_reports`) era esattamente questo: il commit di consolidamento `668b406` aveva rimosso la sezione `# 3. Calcola stuck reports` lasciando intatti i `# 1.`, `# 2.` e `# 4.` adiacenti, e nessuno aveva notato il salto.

Cosa fare: quando vedi una sequenza numerata con un buco, prima di assumere che il buco sia intenzionale, fare `git log -p --follow <file>` cercando il pattern del numero mancante. Se il pezzo c'era ed è stato rimosso, decidere se va ripristinato o se la numerazione va riallineata per riflettere la nuova realtà. Il salto silenzioso fra due numeri è quasi sempre debito tecnico, raramente intenzione.

### 3.12 Due `CLAUDE.md` (per scelta, non un errore)

Esistono due `CLAUDE.md` e devono coesistere:
- `CLAUDE.md` alla **root** del repo — tracciato, canonico, auto-caricato da Claude Code.
- `docs/CLAUDE.md` — **gitignored** (`.gitignore:121`), copia esposta a Obsidian via Syncthing perché sia leggibile lì.

`docs/CLAUDE.md` va tenuto allineato alla root ogni volta che la root cambia. Non è un bug: non segnalarlo come discrepanza in recon, non aggiungerlo a git, non cancellarlo.

### 3.13 Credential helper `store`: 401 se deploy come utente ≠ `alberto` o se `~/.git-credentials` viene resettato

L'autenticazione `git push`/`fetch` sul VPS verso `github.com/8albe/2salti-django.git` (remote **HTTPS**) si appoggia a `credential.helper=store`, configurato nel `.gitconfig` di `alberto`, con il PAT in chiaro in `~/.git-credentials` (perms `0600 alberto:alberto`). Tutti e tre i repo (`/home/alberto`, `/opt/2salti-dev`, `/opt/2salti-new`) ereditano lo stesso global, senza override locale. Quando funziona, il meccanismo è silenzioso e non-interattivo: **"niente 401" è il suo comportamento normale, non un'anomalia**. Ma ha due punti di rottura permanenti — non sono debito da risolvere, sono comportamenti noti da conoscere:

1. **Deploy eseguito con utente ≠ `alberto` o con HOME diverso** (es. via `sudo`/root): l'helper `store` vive nel `.gitconfig` di `alberto`, root non lo vede (`sudo -H git -C /opt/2salti-new config --get-all credential.helper` → exit 1, nessuna riga; `/root/.git-credentials` assente). Un `git push` lanciato come root fa **401** anche se da `alberto` funziona.
2. **Reset/cancellazione di `~/.git-credentials`** o cambio dei suoi permessi: senza il file (o se non più leggibile da `alberto`), `store` non ha nulla da restituire → prompt interattivo o **401**.

Quindi: se un deploy che prima passava comincia a fare 401, prima di sospettare GitHub o il token, controllare *con quale utente* gira il comando e che `~/.git-credentials` di `alberto` esista con perms `0600`. La diagnosi read-only completa del meccanismo (più la mitigazione del PAT applicata il 2026-06-21) è archiviata in Appendice A §10.14.

### 3.14 OCR — provider Gemini unico: configurazione e billing (ratificato 2026-07-09)

Dal 2026-07-09 l'OCR ha **un solo provider concreto: Google Gemini**, modello di default `gemini-2.5-pro` (scelto dopo bench su referti reali; il più accurato sulle grafie difficili, latenza ~90s tollerata perché l'estrazione gira in background). OpenAI è stato rimosso dal codice/test/deps OCR. Il **seam** provider resta (`BaseVisionProvider` + factory `OCRService.get_provider()` + `OCR_PROVIDER`): riaggiungere un provider = una sottoclasse `extract_data` + un ramo nella factory, senza toccare il resto.

**Variabili d'ambiente OCR (`.env`):**

| Var | Default | Ruolo |
|---|---|---|
| `OCR_PROVIDER` | `gemini` | `gemini` (reale) o `mock` (test/dev). Un valore diverso da `gemini`/`mock` cade sul mock. |
| `GEMINI_API_KEY` | `""` | Chiave API Google Gemini. Se vuota con `OCR_PROVIDER=gemini`, la factory alza `ValueError` (nessun fallback silenzioso al mock). |
| `GEMINI_MODEL` | `gemini-2.5-pro` | Model-string inviata all'SDK. Sovrascrivibile per test A/B senza toccare il codice. |
| `OCR_MAX_OUTPUT_TOKENS` | `32000` | Tetto output token. Alzato da 16000 a 32000 come assicurazione anti-troncamento: i referti densi (molti eventi + due roster) coi modelli *thinking* troncavano il JSON. Env-configurabile: se un referto tronca ancora (`finish_reason=MAX_TOKENS` nel log), alzarlo qui senza deploy di codice. |

> `OPENAI_API_KEY` resta in `.env`/`requirements.txt` ma **non** serve più all'OCR: la usa solo `AIStatsEngine` (chat stats NL→ORM, feature non-OCR). Non rimuoverla finché quella feature è viva.


**Billing Gemini (prepagato).** L'account Google dietro la `GEMINI_API_KEY` è a **credito prepagato**: carta associata + credito ricaricato in anticipo, con **ricarica automatica** attiva per non esaurire il saldo durante l'ingestion. Attivazione/gestione del billing delegata al padre di Alberto. Se l'OCR reale inizia a fallire con errori di quota/autorizzazione lato Gemini, verificare **prima** il saldo prepagato e lo stato della ricarica automatica, poi la validità della chiave (rotazione via protocollo §8/§11, revoca lato Google prima della sostituzione). **Tetto di spesa (chiuso 2026-07-10):** su Google AI Studio è impostato un **Project Spend Cap ~$15/mese** — hard block reale denominato in dollari, con enforcement ~10 min di ritardo; failure mode = OCR in pausa fino al ciclo successivo. È distinto dal **tier cap** dell'account (~$250/mese Tier 1, indipendente). `AIStatsEngine` gira su OpenAI e **non** è coperto da questo tetto.

**Deploy prod del filone OCR — attenzione: migration distruttiva.** Il delta `master..dev` del filone OCR include la migration **`matches/0017_delete_ocrrawresponse`** (`DeleteModel` → `DROP TABLE matches_ocrrawresponse`; il modello morto `OCRRawResponse` è stato rimosso, la raw response vive ora nel campo `MatchReport.raw_api_response`). A differenza del resto del filone (solo config/codice), questo deploy **non è a sola migration nulla**: prima del `migrate` su prod, **backup DB**, **verificare che `matches_ocrrawresponse` sia vuota** (in prod non è mai stata scritta dal path vivo), dry-run su copia scratch + hash SHA256, poi `migrate` eseguito a mano da Alberto. **Eseguito il 2026-07-19** — sequenza completa, rituale e learning in **§2.6**.

### 3.15 Dry-run di una migration: il path del DB è hardcoded, serve copiare l'intero progetto

`config/settings.py` **non legge alcuna variabile d'ambiente per il path del DB**: `DATABASES['default']['NAME'] = BASE_DIR / 'db.sqlite3'` ([config/settings.py:76](../config/settings.py)), hardcoded su `BASE_DIR`. Quindi il dry-run di una migration **non si può fare puntando una env var a una copia del DB** — quell'env var non esiste. L'unico modo è copiare l'**intero progetto** in `/tmp` (tar escludendo `.venv`, `.git`, `media`, `staticfiles`), mettere la copia del DB dentro la copia del progetto, ed eseguire lì il `migrate` con il **python del venv del box** (su prod, il venv di `/opt/2salti-new/`): `BASE_DIR` della copia risolve sul DB della copia. Verificare **sempre** lo SHA256 del DB reale prima/dopo il dry-run per provare che non sia stato toccato. Inaugurato per la `0017` (deploy §2.6).

### 3.16 OCR sincrono nel request cycle: servono DUE timeout (gunicorn E nginx)

L'OCR gira **sincrono dentro il request cycle**: `OCRService.process_and_update(report)` è chiamato inline dalla upload view ([matches/views.py:158](../matches/views.py)) e dall'admin action `process_ocr` ([matches/admin.py:206](../matches/admin.py)), ~80s a referto con Gemini. Col `timeout` gunicorn di default (30s) il master abortisce il worker a metà chiamata: 500 al client e referto appeso in `PROCESSING` (§10.19). Il fix richiede **due timeout, non uno**: `timeout = 300` in `gunicorn_config.py` **e** `proxy_read_timeout 300s` nel blocco `location /` di nginx (default nginx: 60s). Alzare solo il primo sposta l'errore, non lo risolve: gunicorn completa, ma nginx chiude la connessione a 60s → **504 lato browser** mentre il backend finisce comunque il lavoro. Entrambi i 300s sono un **cerotto provvisorio**: cadono quando l'OCR esce dal request cycle (Macro 22, syllabus).

## 4. Pulizia repo: history vs indice corrente

Sono due operazioni distinte che affrontano due problemi distinti, e confonderle è un errore di categoria. È esattamente l'errore commesso il 22 aprile 2026 sulla chiusura del problema #7 e corretto il 23 aprile; la lezione merita di vivere in un posto stabile.

La **pulizia della history** si fa con `git-filter-repo` (o con il vecchio `git filter-branch`, sconsigliato) e riscrive il passato del repo, rimuovendo i file indicati da *tutti* i commit storici. Serve quando si vuole eliminare dal repo per sempre artefatti sensibili (credenziali finite in commit passati, ad esempio) o voluminosi (binari, dataset, dump) che altrimenti continuerebbero a pesare sulla dimensione del `.git` anche se rimossi con un semplice `git rm`.

La **pulizia dell'indice corrente** si fa con `git rm` (per cancellare anche dal working tree) o `git rm --cached` (per smettere di tracciare mantenendo il file su disco) e rimuove file dall'HEAD corrente senza toccare la history. I file restano visibili nei commit passati, ma dall'HEAD in poi spariscono.

Il punto chiave, che è la vera lezione, è che **la pulizia della history senza un `.gitignore` appropriato è una vittoria temporanea**. Se la history viene ripulita con `git-filter-repo` ma i `.gitignore` non bloccano i pattern degli artefatti rimossi, al primo commit successivo in cui quegli artefatti vengono re-inclusi — tipicamente per abitudine, perché "tanto erano lì prima" — l'indice corrente si ripopola silenziosamente. Il problema viene dichiarato chiuso sulla base della history pulita, ma di fatto è già riaperto nell'indice.

La regola derivata, da applicare sempre quando si pulisce il repo da una categoria di artefatti, è che servono tre passi coordinati:

1. Pulire la history con `git-filter-repo` (solo se serve rimuovere gli artefatti anche dal passato — non sempre è necessario)
2. Pulire l'indice corrente con `git rm` o `git rm --cached` a seconda che si voglia eliminare anche dal working tree o solo smettere di tracciare
3. Aggiungere pattern generici al `.gitignore` per prevenire reintroduzioni future

Saltare il terzo passo significa avere il problema chiuso oggi e riaperto entro una settimana, spesso senza che nessuno se ne accorga finché non si guarda lo stato del repo a freddo. Il passo tre è quello che trasforma la pulizia da operazione puntuale a decisione stabile.

## 5. Regola "CHIUSO end-to-end"

Questa è una regola metodologica che riguarda la redazione delle note di sessione. Marcare un problema come CHIUSO in una nota implica che la chiusura è stata verificata su tutti gli ambienti interessati, non solo su quello più visibile o su quello su cui è avvenuta l'azione principale. Quando la chiusura tocca artefatti di repo — che è la maggior parte dei casi nel lavoro su 2salti — la verifica minima include:

- La home `/home/alberto/` come repo di sviluppo
- Il deploy `/opt/2salti-new/` come repo di produzione
- Il remote GitHub come repo pubblico — perché, come spiegato in sezione 1, il deploy non parla direttamente con GitHub e la home potrebbe essere allineata a uno dei due ma non all'altro
- Dove esistano, anche staging e dev-remote (oggi non attivi)

Il contro-esempio storico è esattamente il caso che ha generato questa regola. Il 22 aprile 2026 il problema #7 è stato marcato come CHIUSO in nota di sessione dopo aver ripulito la history con `git-filter-repo`. Era chiuso solo a metà: la history era stata pulita correttamente, ma l'indice della home si era silenziosamente ripopolato attraverso commit successivi nella stessa giornata, e il deploy era tre commit indietro rispetto alla home. La chiusura vera è arrivata solo il 23 aprile, quando abbiamo verificato home più deploy end-to-end e aggiunto i pattern generici al `.gitignore`.

In pratica, prima di scrivere "CHIUSO" in una nota, fare il check esplicito sugli altri ambienti. Costa due minuti di comandi — un `git status`, un `git log -1`, un confronto di HEAD — e previene scoperte imbarazzanti una settimana o un mese dopo, quando il problema riemerge e costringe a ricostruire il contesto da zero.

## 6. Regole operative trasversali

### 6.1 I 5 minuti di ispezione a freddo

Prima di qualsiasi operazione che tocca history, indice git o stato condiviso in un ambiente divergente, dedicare cinque minuti a un'ispezione a freddo. Gli esempi concreti sono: un `git pull` sul deploy quando home e deploy sono potenzialmente disallineati, l'esecuzione di uno script ops come `rebuild_standings.py` su una lega in stato ambiguo, un `reset` o `checkout` di file con modifiche uncommitted, qualsiasi migration su produzione, qualsiasi `rm -rf` su directory non triviali.

L'ispezione comprende la lettura dei commit che si stanno per pullare (`git log --oneline origin/dev..HEAD` e viceversa), la verifica dello stato locale (`git status`, `git diff`), e la lettura dello script che si sta per eseguire se non è un comando standard di cui si conosce già il comportamento. Sono cinque minuti, non una revisione completa.

Il beneficio è asimmetrico rispetto al costo: cinque minuti spesi prima evitano ore di rollback dopo, e soprattutto evitano di entrare in modalità reattiva — che è la modalità in cui si commettono gli errori peggiori. Il pattern è emerso più volte nelle sessioni del 22 e 23 aprile 2026, prima sulla lettura di `rebuild_standings.py` prima dell'esecuzione, poi sull'ispezione pre-pull del deploy. Vale per qualsiasi operazione "non routine", e la definizione di "non routine" è: se non l'hai già fatta dieci volte questa settimana, è non routine.

### 6.2 Backup safety per operazioni reversibili-con-cautela

Per le operazioni reset-then-restore, per le modifiche distruttive con rollback previsto, e per qualsiasi operazione in cui "mi serve il contenuto attuale anche se l'operazione va storta" è una preoccupazione legittima, fare un backup safety esterno. Il backup va in `/var/tmp/`, fuori dal percorso dell'operazione, fuori dal deploy, fuori dal repo, con naming datato e contestualizzato nello stile `/var/tmp/<file>.<context>-YYYYMMDD`. Va cestinato quando l'operazione è stabilmente verificata, tipicamente entro fine settimana, e la cestinatura va tracciata come side-quest nella nota di sessione corrente.

Il punto sottile è che il backup safety resta utile anche se l'operazione va a buon fine. Nel caso del 23 aprile 2026 il backup di `gunicorn_config.py` non è stato usato per rollback d'emergenza: è stato usato esattamente come previsto dal piano, come sorgente della `cp` finale per restaurare il contenuto dirty come untracked+ignored dopo il pull. Senza quel backup la manovra reset-then-restore non sarebbe stata possibile in modo sicuro. L'abitudine di metterlo a prescindere — anche quando "probabilmente non serve" — è un'assicurazione che si paga una volta e che abilita manovre che altrimenti sarebbero rischiose o impossibili.

### 6.3 Output troncato di Claude Code: chiedere il completo, non assumere

Quando un messaggio inoltrato da Claude Code contiene riferimenti tipo "vedi sopra" o "come confermato prima" senza essere stato preceduto da output completo nella stessa finestra, è probabile che sia arrivata solo la coda del messaggio. Non assumere, chiedere esplicitamente il completo.

Sintomo: Claude in chat riferisce a contenuto che non è in contesto. Manca un blocco a monte.

Cosa fare: chiedere all'utente di reinoltrare l'output completo dell'ultimo turno di Claude Code, non interpretare a vuoto.

### 6.4 Verificare la struttura del documento prima di scrivere riferimenti numerici

Prima di scrivere un prompt che dice "modifica §3.2 del file X", verificare che §3.2 esista davvero nel file e che la sotto-numerazione corrisponda alle attese. Documenti che evolvono nel tempo possono avere sotto-sezioni rinumerate, accorpate o assenti.

Sintomo: prompt rifiutato da Claude Code con "la struttura non corrisponde", oppure modifica applicata in punto sbagliato.

Cosa fare: prima di scrivere riferimenti numerici, chiedere a Claude Code `grep -n "^#" <file>` per mappare l'indice header attuale.

## 7. Convenzioni di lavoro

### 7.1 Scratch root-level

Gli scratch di verifica e test ad-hoc che vivono nella root del repo (file con nomi tipo `verify_*.py` e `test_*.py`, non nelle app Django) sono by-convention ignorati dal repo. I pattern generici nel `.gitignore` della home sono:

```
/verify_*.py
/test_*.py
```

(più altri pattern specifici per config file di deploy: `/gunicorn_config.py`, `/2salti_nginx_config`, `/nginx_config`, `/git-filter-repo`.)

Se si vuole committare consapevolmente un file con questo naming, serve una decisione esplicita e un pattern più specifico nel `.gitignore` che lo esenti — e soprattutto serve spostarlo nella directory dell'app a cui appartiene, perché scratch in root non sono mai la sede giusta per codice stabile.

I test veri delle app vivono nelle directory delle app stesse, seguendo la convenzione `matches/tests_*.py`, `accounts/tests_*.py`, eccetera. Quelli sono tracked, coperti dal test runner di Django, e non hanno nulla a che fare con il pattern di esclusione root-level.

### 7.2 Session note

Le note di sessione out-of-repo vivono in `/home/alberto/_session_notes/`. La directory non è tracked — è ignorata dal `.gitignore` della home — e i suoi file non finiscono mai nel repo. È una scelta deliberata: le note sono strumento di lavoro personale dello sviluppatore, non documentazione di progetto, e vivono separate dal codice.

Il naming convenzionale è:

```
SESSION_RIPARTENZA_YYYYMMDD.md
SESSION_RIPARTENZA_YYYYMMDD_<momento>.md    (es: _mattina, _pomeriggio, _sera)
```

Lo scopo è la ricostruzione del contesto a inizio sessione successiva, quando il contesto della chat AI si è azzerato e serve un'ancora per ripartire senza rifare tutto il lavoro di orientamento. Per questo motivo le note sono scritte in prosa narrativa, non in bullet point secchi: devono trasmettere il ragionamento, le lezioni e le scelte, non solo i fatti. Una nota scritta bene permette alla sessione successiva di ripartire in cinque minuti invece che in un'ora.

### 7.3 Build frontend Tailwind (CSS compilato committato)

Dal 17.1 Fase 1 il CSS Tailwind non è più servito da CDN runtime ma compilato e committato. Convenzione: **se modifichi un template / `forms.py` / JS introducendo classi Tailwind nuove, ricompila e ricommitta il CSS** — `npm run build:css` genera `static/css/tailwind.build.css`, che va committato **insieme** alla modifica che lo richiede. Il versioning della cache è automatico (`ManifestStaticFilesStorage`, hash nel nome dell'asset): i link in `base.html` non portano più il `?v=N` manuale — vedi §12.8. Il glob `content` in `tailwind.config.js` deve coprire la sorgente delle classi nuove (template, app `*.py`, JS, e i template di `crispy_tailwind` nel venv); le utility usate solo dentro selettori di `style.css` (isole `.dark-surface`) stanno in `safelist`. Dev e prod fanno solo `collectstatic`, **non** eseguono `npm`: un asset non ricompilato = classe mancante a video (purge silenzioso). La build gira solo su una macchina con node (`npm install` locale, non-sudo).

**Gotcha — "verde ≠ reso".** La regola di rebuild vale anche per modifiche ad **arbitrary values** (literali `rgba(...)`/hex dentro `shadow-[…]`, colori inline nei template), non solo per le classi nuove: cambiare un literale senza rigenerare `tailwind.build.css` lascia il vecchio CSS committato e la modifica **non viene resa**, pur con suite verde e deploy ok. È esattamente l'incidente `ac9b970` (vedi §12.9): i literali rgba degli aloni erano già stati portati a blu nel template ma il CSS non era stato ricostruito → 13 aloni blu non resi su `dev`, latenti finché A2 non ha rigenerato la build. Suite verde e build stantia non si escludono a vicenda: dopo ogni tocco a classi o arbitrary values, `npm run build:css` e committa il `.css` rigenerato nello stesso commit.

**Gotcha — il glob `content` scansiona anche i `.py`.** Le classi Tailwind vivono anche nei widget di `matches/forms.py` (e in altri `*.py`), non solo nei template. Due conseguenze: (a) ogni stima del tipo "N riferimenti nei template" è **incompleta** se non include i `.py` — il conteggio va esteso a `*.py` e JS; (b) un `cyan-*` (o qualunque classe) residuo in un widget viene compilato nel colore reale e **sopravvive** a un remap/rimozione applicato solo ai template (post-rimozione del token-remap `cyan` compilerebbe nel ciano vero). Prima di dichiarare "rimosse tutte le occorrenze di X", grepare template **e** `*.py` **e** JS.

### 7.4 Suite test e storage statico (manifest disattivato solo nei test)

La suite si lancia con il comando standard `python manage.py test` (nessun flag). `ManifestStaticFilesStorage` (dev/prod) risolve `{% static %}` via `staticfiles.json`, che è prodotto da `collectstatic` e **non** esiste nell'ambiente di test → ogni template con `{% static %}` alzerebbe `ValueError: Missing staticfiles manifest entry`. Soluzione (2026-06-23): `config/settings_test.py` eredita `config.settings` e sovrascrive **solo** lo storage `staticfiles` con il non-manifest `StaticFilesStorage`; `manage.py` lo auto-seleziona quando `test` è in `argv`. `config/settings.py` (protetto) e lo storage di dev/prod restano `ManifestStaticFilesStorage`. Per forzarlo esplicitamente: `python manage.py test --settings=config.settings_test`. Non reintrodurre il manifest nei test (rompe la suite) e non disattivarlo per dev/prod.

### 7.5 Onboarding manuale di una società nuova (strumento staff `create_society`)

Il ramo CREATE di `/society/create/` è uno **strumento operativo staff** (opzione A, 2026-07-05) per onboardare una società non ancora a DB, in attesa dell'import calendario FIN come fonte canonica. Requisito account operatore: `role='president'` **e** `is_staff=True` (o superuser) — un account staff con altro role viene rediretto a `home`, un presidente non-staff a `choose_society`. La creazione produce Società + una prima squadra e **non** aggancia la società all'operatore (riusabile, side-effect-free): il presidente reale la rivendica poi via "Scegli la tua società" (personificazione, Macro 18). Entrypoint: card "Onboarda società (staff)" negli Strumenti Operativi della dashboard.

## 8. Protocollo protected file

Il "protocollo protected file" è una procedura disciplinata per modificare file critici dell'infrastruttura — settings Django, configurazione Gunicorn, configurazione Nginx, middleware di onboarding, servizi che toccano la persistenza delle classifiche, migrazioni applicate, file `.env`, unit systemd. Questi file sono elencati nominalmente in [CLAUDE.md](../CLAUDE.md) sotto "Protected Files", e la regola di base è che ogni modifica richiede conferma esplicita prima dell'esecuzione. Questa sezione codifica come applicare quella regola in pratica.

Il protocollo è stato validato tre volte fra il 24 e il 25 aprile 2026, ogni volta su un file diverso (la rimozione di whitenoise da `requirements.txt` e l'allineamento documentale in `CLAUDE.md`, l'aggiunta di `ExecReload` alla unit systemd via drop-in `override.conf`, il versionamento della unit in `deploy/systemd/`). Lo schema procedurale comune che è emerso dalle tre applicazioni è il seguente, in sette passi, con indicazione esplicita di cosa serve a cosa.

Il primo passo è la **ricognizione a freddo**. Prima di toccare il file, leggerlo per intero, anche se "si conosce già". Verificare lo stato attuale via i comandi diagnostici pertinenti al file: per file git-tracked, `git log -1 -- <file>` per sapere quando è stato toccato l'ultima volta e da quale commit; per file di configurazione runtime, un comando di verifica dello stato corrente del servizio (`systemctl cat`, `nginx -t`, eccetera); per file Python, un `manage.py check` come baseline pre-modifica. Questo passo non costa quasi nulla in tempo ed evita la classe di errori "il file aveva già una modifica che non ricordavo" o "il file è diverso da quello che ho in mente".

Il secondo passo è la **modifica mirata**. Una sola modifica logica per volta, anche se il file richiederebbe più cambi indipendenti. Ogni modifica deve essere descrivibile in una frase. Se serve modificare due cose, fare due cicli del protocollo, non uno con due modifiche. Il rationale è che la verifica end-to-end del passo 7 deve poter attribuire eventuali regressioni a una singola causa identificabile, e una modifica multipla rompe questa proprietà.

Il terzo passo è il **diff check**. Dopo la modifica, leggere il diff (`git diff <file>` per file git-tracked, o `diff <backup> <file>` per file fuori repo) e verificarlo riga per riga. Non scorrere: leggere. Il diff check serve per due cose distinte. La prima è verificare che la modifica sia effettivamente quella attesa — typo, indentazione sbagliata, sostituzione applicata al posto sbagliato. La seconda, meno ovvia, è verificare che non ci siano modifiche collaterali non volute: whitespace di fine riga aggiunti dall'editor, riformattazioni automatiche, conversioni di line ending. Il rendering visivo dell'editor nasconde queste cose; il diff testuale no.

Il quarto passo è il **sanity sintattico**. Per file Python, `python -m py_compile <file>`; per file YAML, un parser; per file di configurazione di servizio, il comando di validazione del servizio (`nginx -t`, `gunicorn --check-config`, `systemd-analyze verify`). Lo scopo è prendere errori di sintassi prima che diventino errori a runtime. La maggior parte dei protected file ha un comando di validazione dedicato, ed è quello che va usato.

Il quinto passo è il **Django check** (per modifiche che toccano qualcosa che il framework legge). `python manage.py check` in home `/home/alberto/`, *e separatamente* in deploy `/opt/2salti-new/`. Questa è la lezione operativa derivata dal problema #18 del 25 aprile: la home può non essere in stato runnable per Django (mancanza del file `.env`, dipendenze non installate, settings con import condizionali) e un check eseguito solo lì può dare falsi positivi o falsi negativi rispetto a quello che il deploy effettivamente vede. Il cross-check sul deploy non è un'aggiunta opzionale — è parte stabile del protocollo, quando la modifica tocca runtime Django.

Il sesto passo è il **dry-run** (per operazioni che hanno una modalità dry-run nativa: management command, script di migrazione, operazioni distruttive con flag `--dry-run` o `--no-confirm`). Eseguire il dry-run, leggere l'output integrale, verificare che le azioni proposte corrispondano all'intenzione. Se il comando non ha modalità dry-run nativa ma è distruttivo (`rm`, `git reset --hard`, eccetera), questo passo si trasforma nel suo equivalente: backup safety esterno (vedi sezione 6.2), in modo che l'esecuzione vera del passo 7 sia reversibile.

Il settimo passo è l'**esecuzione reale e verifica end-to-end**. Eseguire la modifica vera (rimozione del flag dry-run, applicazione del cambio runtime, commit e push se git-tracked, propagazione al deploy con il pull seguito dal `systemctl reload` se serve). Subito dopo, verifica funzionale: il servizio risponde, il sito è raggiungibile, il comportamento atteso è quello osservato. La verifica end-to-end include tutti gli ambienti interessati come definito nella sezione 5 ("CHIUSO end-to-end"): home, deploy, GitHub, e dove esistano staging e dev-remote.

C'è un effetto strutturale del protocollo che merita di essere dichiarato esplicitamente, non lasciato come scoperta accidentale. Ogni applicazione del protocollo con cura tende a rivelare qualcosa che il protocollo stesso aveva dato per scontato. Questo si è ripetuto nelle tre validazioni del 24-25 aprile in modo identificabile: la rimozione di whitenoise ha rivelato l'assenza strutturale del file `.env` in home (problema #18); il versionamento della unit systemd ha rivelato il pattern `*.service` nel `.gitignore` che bloccava il versionamento intenzionale (parte del problema #16); il cleanup della unit ha rivelato un backup laterale del 22 aprile in `/var/tmp/` di cui nessuno si ricordava più. Il pattern non è coincidenza: il passo 1 (ricognizione a freddo) impone una lettura attenta su zone del sistema che altrimenti restano fuori dalla memoria attiva, e quella lettura è esattamente ciò che genera scoperte. Il protocollo non è solo prudenza — è uno strumento di scoperta architetturale, e le sessioni di applicazione del protocollo vanno previste con margine sufficiente per gestire le scoperte laterali, non solo per chiudere la modifica nominale.

Tre regole accessorie completano il protocollo, derivate da errori specifici del 24-25 aprile.

La prima è il **path completo prima di rilanciare verifiche citate da session note**. Le note di sessione abbreviano i path per leggibilità ("`main.js`" invece di "`static/js/main.js`"). Quando la sessione successiva rilancia una verifica citata in una nota, è facile ereditare l'abbreviazione e fornirla come path letterale a un tool — con il risultato che il tool cerca il file dove non sta e segnala un finto problema. La regola è: prima di lanciare una verifica su un path citato in una nota, leggere il file che contiene il riferimento (template, settings, configurazione) e citare il path completo come è realmente, non come la nota lo abbreviava.

La seconda è la **verifica indipendente prima di promuovere un log a problema strutturale**. Un'osservazione in un log — un 404 in nginx, un warning in un test, una entry in un audit trail — è dato grezzo. Promuoverla a "problema aperto nel backlog" senza una verifica indipendente che il problema esista davvero porta a falsi positivi che restano aperti per giorni e generano lavoro inutile. La regola è: ogni volta che si apre un problema sulla base di un log, fare almeno un check indipendente (grep nel codice, ispezione filesystem, riproduzione della richiesta) prima di numerarlo.

La terza è la **doppia lettura del diff a freddo**. Il diff check del passo 3 va fatto due volte se la prima è avvenuta "subito dopo la scrittura". L'attenzione di chi ha appena scritto il codice è la peggior attenzione possibile per fare review — si vede quello che si voleva scrivere, non quello che si è scritto. La seconda lettura, anche solo a cinque minuti di distanza, intercetta cose che la prima ha mancato. Il pattern di cattura-prima-della-delete del 25 aprile (vedi sezione 3.4) è un esempio: il diff era stato letto e il bug `id=None` era stato mancato pur essendo nel blocco esaminato. Una seconda passata l'avrebbe intercettato.

Quando un protected file è git-tracked, l'esecuzione vera del passo 7 include sempre il commit con messaggio descrittivo. Niente commit "fix" o "update" — la message convention del progetto (italiano, imperativo, descrittiva del cosa e del perché) vale e si applica.

## 9. Procedura systemd unit

La unit systemd `2salti.service` è versionata in repo sotto `deploy/systemd/`, insieme al drop-in `2salti.service.d/override.conf` che fornisce `ExecReload=` per supportare `systemctl reload`. La directory contiene anche un `README.md` con la procedura di sync passo-passo: il README è la fonte di verità tecnica, questa sezione del runbook è il rimando contestualizzato all'interno del flusso operativo dell'infrastruttura.

Il setup è stato introdotto il 25 aprile 2026 con il problema #16, prima del quale la unit viveva soltanto in `/etc/systemd/system/2salti.service` senza alcun versionamento, con due copie obsolete divergenti su disco e nessuna procedura di sync formalizzata. Lo stato attuale è: la unit attiva su sistema sta in `/etc/systemd/system/2salti.service`, la copia versionata e canonica sta in `/home/alberto/deploy/systemd/2salti.service`, e la sincronizzazione fra le due è manuale.

La regola operativa è la stessa dell'asimmetria home ↔ deploy della sezione 2, ma applicata al filesystem di sistema invece che al repo: la copia in repo non si autoallinea con `/etc/systemd/system/`, e il drift fra le due si accumula silenziosamente se modifiche dirette via `systemctl edit` o via editing manuale di `/etc/systemd/system/2salti.service` non vengono propagate indietro in repo. La direzione critica del drift è entrambe: modifica in repo non propagata al sistema significa che la modifica non è attiva, modifica nel sistema non propagata in repo significa che il prossimo deploy della unit dal repo cancellerà la modifica fatta sul sistema.

La procedura di sync repo → sistema, da eseguire dopo aver modificato la unit in repo, è la copia dei due file (unit principale e drop-in) sotto `/etc/systemd/system/`, seguita da `daemon-reload` per far rileggere a systemd la nuova unit, seguito a sua volta da `reload` o `restart` del service in base al tipo di modifica. La distinzione fra `reload` e `restart` è importante: `reload` invia SIGHUP ai worker gunicorn senza toccare il master process, ed è quello che si vuole per modifiche a configurazione runtime che gunicorn rilegge a SIGHUP; `restart` ferma e riavvia l'intero service, ed è obbligatorio quando cambia `ExecStart` (perché il master process è quello, e va riavviato per rispettare la nuova invocazione) o quando cambiano variabili d'ambiente che gunicorn legge solo all'avvio. Il dettaglio dei comandi esatti — path completi, ordine, mkdir per la directory drop-in se necessario — è nel `README.md` di `deploy/systemd/`.

La verifica post-deploy della unit include `systemctl cat 2salti` per leggere la unit effettivamente caricata da systemd (utile per confermare che il `daemon-reload` abbia preso la versione nuova, non la vecchia in cache), `systemctl status 2salti` per stato e ultime righe di log, e una richiesta HTTP al sito (`curl -I https://2salti.com/`) come check funzionale che il service stia effettivamente servendo. Una unit che parte senza errori ma non risponde sul socket è un caso reale che `systemctl status` da solo non rileva.

C'è una direzione di drift inversa che merita menzione esplicita perché è il caso più subdolo. Modifiche fatte direttamente in `/etc/systemd/system/2salti.service` o via `systemctl edit` (che crea o modifica drop-in in `/etc/systemd/system/2salti.service.d/`) non vengono mai propagate indietro in repo automaticamente. Se serve fare una modifica veloce in produzione e il tempo non c'è per il ciclo completo (modifica in repo, copia nel sistema, daemon-reload), va comunque ricordato di tornare in repo dopo l'emergenza e portare la modifica in `deploy/systemd/`, altrimenti il prossimo deploy "pulito" dal repo cancellerà la modifica di emergenza senza che nessuno se ne accorga. Per drift check rapido, `xxd /etc/systemd/system/2salti.service | diff - <(xxd /home/alberto/deploy/systemd/2salti.service)` confronta byte-by-byte le due copie: output vuoto significa allineate, output non vuoto rivela esattamente la divergenza.

Il punto strutturale, simmetrico alla sezione 2, è che il versionamento del 25 aprile non ha eliminato la classe di problemi del drift — ha solo creato l'infrastruttura per gestirlo. Finché la sincronizzazione resta manuale, la disciplina operativa è l'unico meccanismo. Un eventuale meccanismo di allineamento automatico — file watcher su `/etc/systemd/system/2salti.service` che alerti su divergenza dalla copia in repo, o pre-commit hook che blocchi commit della unit se il sistema ha una copia diversa — vive nel backlog come side-quest aperta, accanto al meccanismo simmetrico per il drift home ↔ deploy.

**Config gunicorn — stesso pattern dal 2026-07-19.** Le copie canoniche delle config gunicorn sono versionate in `deploy/gunicorn/prod/` e `deploy/gunicorn/dev/`, con un `README.md` di procedura che è la fonte di verità tecnica (come il README di `deploy/systemd/`). I file attivi vivono fuori repo (`/opt/2salti-new/gunicorn_config.py` e `/opt/2salti-dev/gunicorn_config.py`, caricati dalle unit via `--config`); il `gunicorn_config.py` alla root del repo è **gitignorato** e le due config **divergono volutamente** (socket, worker, logging) — mai copiare prod su dev o viceversa. Sync repo→`/opt` manuale: `cp` + `systemctl reload` (o `restart` se cambia `bind` o altri parametri letti solo all'avvio del master).

**Config nginx — stesso pattern, chiuso il 2026-07-19.** Le copie canoniche vivono in `deploy/nginx/prod/2salti` e `deploy/nginx/dev/2salti-dev`, con `README.md` di procedura (stesso schema di `deploy/gunicorn/`). I file attivi vivono fuori repo in `/etc/nginx/sites-available/` (symlink in `sites-enabled/`); sync repo→sistema manuale via `sudo cp` + `nginx -t` + `systemctl reload nginx` — il `nginx -t` prima del reload non è opzionale, un errore di sintassi non deve arrivare a un reload che uccide il proxy. Le due config divergono volutamente (dev non ha `proxy_read_timeout` esteso). Debito §10.17 chiuso da questo versionamento.

## 10. Debiti aperti

Registro vivo di problemi noti che richiedono follow-up. Non sono trappole (§3) né bug attivi: sono incoerenze scoperte ma non risolte, da affrontare in sessioni dedicate.
> Le voci §10.1-10.16 sono CHIUSE e archiviate in Appendice A, che ne conserva razionale, commit e test. Le voci §10.17-10.21 (aperte 2026-07-19, emerse dal deploy §2.6) sono APERTE.

### §10.17 `2salti_nginx_config` fuori repo — CHIUSO 2026-07-19

~~La config nginx attiva vive solo su sistema (`/etc/nginx/`)~~ **Risolto:** copie canoniche versionate in `deploy/nginx/prod/2salti` e `deploy/nginx/dev/2salti-dev` (dettaglio §9), verificato testualmente che `prod/2salti` contenga `proxy_read_timeout 300s` (§3.16) nella location `/`. Il debito residuo non è più "config assente dal repo" ma il rituale di allineamento manuale repo↔sistema, stesso tema di §9 per systemd e gunicorn: una modifica fatta direttamente su `/etc/nginx/sites-available/` non si sincronizza da sola in repo. Il vecchio pattern `2salti_nginx_config` citato in `.gitignore`/`CLAUDE.md` resta un riferimento storico a un file mai esistito in questa copia del repo.

### §10.18 Pin di `requirements.txt` più vecchi dell'installato su prod (downgrade da pip install) — APERTO 2026-07-19

Durante il deploy §2.6, `pip install -r requirements.txt` su prod ha fatto **downgrade** di pacchetti installati a mano più di recente: Django 5.0.3→5.0, openai 2.31→2.29, numpy 2.4.4→2.4.3, python-dotenv 1.2.2→1.2.1. I pin nel file sono più vecchi dello stato reale dei box. Da allineare in un giro dedicato: portare i pin allo stato corretto valutando in particolare i **fix di sicurezza Django** persi col rientro da 5.0.3 a 5.0 (i patch release 5.0.x sono in gran parte security/bugfix). Fino ad allora: **non** rilanciare `pip install -r requirements.txt` sui box se non serve.

### §10.19 Nessuna guardia sui referti appesi in `PROCESSING` — APERTO 2026-07-19

Se il worker muore a metà OCR (timeout gunicorn, deploy/restart, crash), il referto resta in `PROCESSING` **per sempre**: nessun recovery automatico, e la review queue non lo ripropone. Successo il 2026-07-19 con i timeout 30s (§3.16). Serve un comando `recover_stale_reports` (referti in `PROCESSING` da più di N minuti → `NEEDS_REVIEW` + audit log) agganciabile ai timer systemd esistenti — incluso nello scope della **Macro 22** (OCR asincrono). Sblocco manuale usato il 2026-07-19, nella forma (dal box, python del venv, pk espliciti dei referti appesi):

```bash
python manage.py shell -c "from matches.models import MatchReport; MatchReport.objects.filter(pk__in=[...], status='PROCESSING').update(status='NEEDS_REVIEW')"
```

riporta i referti in coda di revisione umana senza rilanciare l'OCR (nessun retry automatico: rilanciare è una scelta del reviewer via admin action `process_ocr`).

### §10.20 Saturazione del pool worker con OCR sincrono — APERTO 2026-07-19

Prod ha `workers = 3` e l'OCR gira sincrono nel request cycle (~80s a referto, §3.16): **3 upload OCR concorrenti bloccano l'intero pool** per ~80s ciascuno e il sito smette di rispondere a qualunque richiesta finché un worker non si libera. Mitigato oggi solo dalla bassa concorrenza reale (pilot). Non si risolve alzando i worker: si risolve togliendo l'OCR dal request cycle (**Macro 22**).

### §10.21 `MatchReport` registrato su due admin site — APERTO 2026-07-19 (minore)

`MatchReport` è registrato sia su `op_admin_site` con `MatchReportAdmin` ([matches/admin.py:416](../matches/admin.py)) sia sul default admin site via `@admin.register(MatchReport)` su una sottoclasse `MatchReportAdminDefault` con `has_module_permission=False` ([matches/admin.py:418-420](../matches/admin.py); stesso pattern per `Match`). Doppiamente **inerte** a runtime — il default admin site non è nemmeno montato negli URL (`/admin/` punta a `op_admin_site`, [config/urls.py:27](../config/urls.py)) — ma confondente in lettura: due registrazioni dello stesso modello, di cui una nascosta e irraggiungibile. Da pulire in un giro cosmetico, non urgente.

## 11. Sicurezza operativa e frontiera reversibile

Questa sezione codifica le regole di sicurezza operativa emerse dalle sessioni di aprile-maggio 2026, e in particolare consolidate dopo l'incidente del 4 maggio 2026 in cui una password sudo in chiaro è stata trovata nella history pubblica del repo (`install_service.sh`, commit `473c296` del 15 marzo 2026). La regola madre è che le operazioni con effetti permanenti, distruttivi o privilegiati passano per Alberto e mai per l'agente, e che i segreti non transitano mai in contesti condivisi.

### 11.1 Rotazione segreti

Le rotazioni di segreto — chiavi API in `.env`, password sudo, credenziali SMTP, app password Google, qualunque cosa abbia valore di credenziale viva — vanno fatte da Alberto direttamente sul VPS via `nano` (o editor equivalente che non transita su pipe). Mai via prompt dell'agente, mai via incolla in chat, mai via heredoc passato a un tool. La ragione tecnica è che ogni transito in un contesto condiviso (chat, log dell'agente, terminale dell'agente) crea una copia residua del valore, e quella copia sopravvive in punti che non vengono ruotati insieme alla credenziale reale.

Il protocollo standard è: backup del file `.env` in `/var/tmp/.env.backup.pre-<rotation>-YYYYMMDD`, edit con `nano` da terminale di Alberto con il nuovo valore incollato direttamente, verifica che il valore sia cambiato senza stamparlo (confronto SHA256 della riga rispetto al backup, oppure lunghezza), restart del service per far rileggere la nuova variabile d'ambiente. Il valore vecchio va revocato lato provider (OpenAI, Google, ecc.) **prima** della rotazione, non dopo, in modo che non ci sia finestra in cui due credenziali siano entrambe attive.

### 11.2 Frontiera reversibile / irreversibile

Tutti i comandi `sudo` sono eseguiti da Alberto, mai dall'agente. Tutte le operazioni irreversibili — `rm -rf` su directory non triviali, `git reset --hard`, `git push --force`, `systemctl restart/reload` su service di produzione, edit di unit systemd, scritture sul DB di produzione, edit di crontab, `git filter-repo` — sono eseguite da Alberto, mai dall'agente. L'agente propone, mostra il comando esatto, mostra il diff o la preview dell'effetto, e si ferma esplicitamente prima dell'esecuzione, aspettando conferma scritta da Alberto.

La frontiera è asimmetrica per disegno: l'agente può fare tutto ciò che è reversibile in un comando (modifica file in repo, commit locale, dry-run di management command, lettura, grep, query SELECT su DB *non*-produzione) senza chiedere conferma; deve fermarsi a ogni operazione che attraversa la soglia. La definizione di "irreversibile" è generosa: include anche operazioni tecnicamente reversibili ma con visibilità esterna immediata (es. `nginx reload` su produzione — reversibile ma il sito vive il cambio in chiaro). Nel dubbio, fermarsi.

### 11.3 DB produzione: autorizzazione esplicita anche per query read-only

Anche una query `SELECT` via Django shell o psql sul DB di produzione richiede autorizzazione esplicita di Alberto prima dell'esecuzione. Le query read-only sembrano innocue ma hanno tre rischi non ovvi: (a) carico — uno scan full-table sbagliato può degradare il servizio sotto pilot, (b) leak — il risultato della query finisce nei log dell'agente, e se contiene dati personali o sensibili crea un'eco fuori dal DB, (c) errore di context — è facile pensare di essere su DB di dev mentre si è su prod, e il primo segnale di sbaglio è il risultato della query stessa, ormai troppo tardi se conteneva una `UPDATE` mascherata.

La regola in pratica: prima di lanciare una qualunque interazione col DB di prod, l'agente prepara la query, la mostra integrale, e chiede conferma. Alberto la rilegge e dà ok, oppure la lancia lui da shell. Per diagnostica frequente che richiede conferma ripetuta, valutare di scriversi script idempotenti read-only in repo (es. `scripts/diag_<area>.py`) con autorizzazione una volta sola allo script, non a ogni esecuzione.

## 12. Verifiche e regole di processo

Raccoglie le regole sulle attività di verifica post-azione e sui pattern di processo applicabili a sessioni intere. Dove §6 codifica regole trasversali sulle singole operazioni e §11 codifica regole di sicurezza, §12 codifica regole sui flussi più ampi: come si verifica la fine di un'azione, come si stima il tempo di una sessione, come si gestisce il bilanciamento autonomia/conferma fra sessione corta e sessione lunga.

### 12.1 Verifiche visuali via Antigravity: "Disable cache" obbligatoria

Per ogni verifica visuale post-deploy in Antigravity (o in qualunque browser usato come sentinella di produzione), aprire DevTools e attivare "Disable cache" prima di ricaricare la pagina. Senza, il browser può servire dalla sua cache una versione precedente dell'asset e restituire un 200 anche quando il server in realtà non è ancora aggiornato o sta servendo un asset rotto. Il falso positivo è particolarmente subdolo per CSS, JS e immagini, che sono cacheable di default.

Cosa fare: prima del primo `Ctrl-R` di verifica, DevTools aperto → tab Network → checkbox "Disable cache" attivo. Tenerlo attivo per tutta la sessione di verifica visuale. Se si vuole essere ancora più paranoici, hard reload (`Ctrl-Shift-R`) come ulteriore garanzia.

### 12.2 Post restart: `sleep 3-5` prima del `curl` di verifica

Dopo `sudo systemctl restart 2salti`, i worker gunicorn impiegano qualche secondo a bootare prima che il socket unix sia pronto a servire richieste. Un `curl https://2salti.com/` lanciato immediatamente dopo il restart può ricevere un 502 transitorio anche se il restart è andato a buon fine — è la finestra fra "master process up, socket creato" e "worker pronti a rispondere". Questo 502 non è errore di runtime, è naturale del ciclo di restart, ed è stato osservato il 4 maggio 2026 durante il restart post-rotazione delle chiavi `.env`.

Cosa fare: aggiungere `sleep 3` (o `sleep 5` se il sistema è sotto carico) fra il `restart` e il `curl` di verifica. Se il primo `curl` restituisce 502, ripetere dopo altri 2-3 secondi prima di considerarlo errore vero.

### 12.3 Una chat alla volta — mai sessioni 2salti parallele

Lavorare su 2salti in più chat o più istanze dell'agente in parallelo è anti-pattern garantito. Le sessioni concorrenti scoprono indipendentemente le stesse trappole — la dualità home/deploy, il bug nginx degli alias, i path obsoleti in CLAUDE.md — senza sapere che le altre le hanno già viste, e ognuna ripaga lo stesso debito di contesto rifacendo il lavoro. Il pattern è stato osservato in modo netto fra il 17 e il 22 aprile 2026 con sei istanze in parallelo, sei volte lo stesso onboarding al contesto del progetto.

Regola: una chat alla volta. Quando una chat si allunga e comincia a esaurire il contesto, si scrive una session note puntuale, si chiude la chat, si apre la successiva con la nuova session note come ancora di ripartenza. Le session note in `/home/alberto/_session_notes/` (vedi §7.2) sono il meccanismo che rende possibile la sequenza di chat senza dispersione.

### 12.4 Regola di stima: triage sottostima 2-3x sistematicamente

Ogni triage di un cluster di lavoro sottostima il costo reale di un fattore 2-3x. Pattern confermato sei volte fra il 28 aprile e il 4 maggio 2026: cluster G stimato 5 minuti, reale 10; cluster F stimato 30 minuti, reale 95; fase 4.5 (pulizia script obsoleti) stimata 30 minuti, reale 3 ore (perché ha rivelato il leak della password sudo); e così via. La causa è strutturale: il triage misura solo la modifica nominale, non le scoperte laterali che il protocollo protected file (§8) inevitabilmente genera.

Cosa fare: usare il moltiplicatore 2-3x come default nella pianificazione. Se il triage dice "1 ora", pianificare 2-3 ore. Se dice "mezza giornata", pianificare una giornata. Quando si propongono opzioni di sessione corta vs lunga, applicare il moltiplicatore *prima* di presentare la stima all'utente, non dopo.

### 12.5 TODO `(ux)` "sull'altro lato" = allinea il test, non il codice

Quando un test fallisce e nel codice di produzione adiacente c'è un commento del tipo `// TODO (ux)`, `# TODO (ux)`, o annotazioni di scope dichiarato (es. `messaggio telegrafico — vedi UX`), il segnale è quasi sempre che il codice è giusto come scelta consapevole e il test è stale rispetto a quella scelta. Il TODO sull'altro lato è la firma di "qualcuno ha già pensato a questo, l'ha lasciato così di proposito".

Cosa fare: prima di toccare il codice per far passare il test, leggere i commenti adiacenti al codice. Se c'è un TODO che inquadra la scelta corrente come consapevole o WIP, allineare il test al codice (cambiare la stringa attesa, cambiare l'assertion) invece di cambiare il codice. Caso reale: cluster G del 2 maggio 2026 sull'`admin.py:219`, stringa telegrafica deliberata, test stale.

### 12.6 Bilanciamento autonomia/conferma degrada oltre 6h di sessione

Dopo 6 ore di sessione continua, la qualità della review cala anche quando la meccanica delle modifiche resta lineare. Il pattern è stato osservato il 28 aprile 2026 con il fix `ce4df80` delle 21:30 — tre re-import locali mancati nella ricognizione iniziale, recuperati solo perché Claude Code ha esteso il check di sua iniziativa. Il problema non era il fix in sé, era che l'agente aveva smesso di chiedere conferma su ogni passaggio per "fluidità", e quella mancanza di check intermedi ha abbassato la rete di sicurezza proprio nel momento in cui serviva di più.

Regola: oltre le 6 ore di sessione attiva, tornare a chiedere conferma esplicita anche su operazioni che in sessione fresca sarebbero autonome. La fatica riduce il giudizio prima di ridurre la velocità di esecuzione, quindi serve un meccanismo esterno (la conferma utente) per riportare attenzione sui dettagli.

### 12.7 Manipolazione del wording delle opzioni è disonestà sottile

Quando l'agente propone più opzioni all'utente, il framing del wording è esso stesso una forma di scelta. Mettere l'opzione preferita per prima nella lista, evidenziarla in grassetto, marcarla "(Recommended)", o presentare le altre come "da giustificare" mentre la preferita appare "naturale", non è neutrale — è una preferenza camuffata da scelta libera. Ed è una forma di disonestà sottile: l'utente non si accorge del bias e finisce per scegliere ciò che l'agente avrebbe scelto comunque, ma con l'illusione di averlo deciso lui.

Regola: o le opzioni sono presentate in modo genuinamente neutro (ordinamento neutro, pari peso visivo, descrizione bilanciata di pro/contro), o il bias va dichiarato esplicitamente come tale ("io preferirei A perché X, ma Y e Z sono alternative valide e legittime"). Nascondere la preferenza dietro una struttura che sembra neutra è la versione più insidiosa del problema, perché toglie all'utente la possibilità di accettare o rifiutare il bias consapevolmente. Pattern osservato il 2 maggio 2026 e corretto in tempo reale dopo che Alberto ha segnalato la dinamica.

### 12.8 Cache-busting manuale del CSS: bumpare `?v=N` a ogni modifica di `style.css`

> **Superato dal 2026-06-23 (Macro 17.1 Fase 1).** Con `ManifestStaticFilesStorage` attivo gli asset statici sono fingerprintati (nome con hash) e il cache-busting è automatico: il `?v=N` manuale su `style.css` e `tailwind.build.css` è stato rimosso da `base.html`. Questa procedura **non si applica più** — non bumpare nulla a mano. Il resto della sezione è conservato come contesto storico.

Il link a `static/css/style.css` in `templates/base.html` porta un query string `?v=N` usato come cache-buster manuale (al 2026-06-22 è `?v=179`). Non è automatico: finché non esiste la pipeline compilata (Macro 17.1), il numero **va incrementato a mano** a ogni modifica di `style.css`, altrimenti browser e CDN possono continuare a servire la versione precedente del foglio di stile anche dopo un deploy andato a buon fine. È il complemento server-side della §12.1 (lì si disattiva la cache del browser in verifica; qui si forza il refresh per tutti gli utenti).

Cosa fare: quando si tocca `style.css`, nello stesso commit bumpare `?v=N` in `base.html`. La Macro 17.1 (pipeline Tailwind compilata con hashing degli asset) supera del tutto questa procedura manuale.

### 12.9 Debito semantico A1: utility `cyan-*` che rendono blue (Macro 17 Fase 2)

> **✅ SALDATO da A2 il 2026-06-30 (`dev`).** I nomi-classe ora coincidono con la resa: le `cyan-*` sono state rinominate `blue-*` in template, `matches/forms.py` e nei selettori light-theme di `style.css`; il token-remap `cyan` è stato **rimosso** da `tailwind.config.js` (la scala rimappata era un 1:1 esatto dello stock `blue`, quindi rinomina pixel-identica). `tailwind.build.css` rigenerato — il commit ha anche corretto un build **stale** da `ac9b970` (literali rgba dei glow già blu ma CSS non rigenerato: 13 aloni blu mancanti + 13 utility cyan morte). Verificato: 0 classi `cyan` in sorgenti e build. **Residuo aperto** (punto 4 sotto): `Sport.hex_color` di 7 sport fittizi del DB dev resta `#00ffff` — normalizzazione a `#2563eb` gated su backup+scrittura DB di Alberto. Lo storico sotto è conservato per contesto.

> **Aperto dal 2026-06-23 (`dev`, commit `819db21`).** Il re-skin Cap. 12 ha adottato la strategia **token-remap (A1)**: in `tailwind.config.js` la scala `cyan` è ridefinita sui valori `blue` di Tailwind. Conseguenza: le ~480 utility scritte `cyan-*` nei template (`text-cyan-400`, `bg-cyan-500`, …) **rendono blue** senza essere state rinominate. È deliberato — evita un find-replace di massa — ma è **debito**: chi legge i template vede `cyan` e ottiene blue.

Cosa sapere: (1) **non fidarsi del nome classe** per il colore reale: la fonte di verità è `tailwind.config.js`. (2) Nuove UI: preferire `blue-*` esplicito; non aggiungere altri `cyan-*`. (3) **Literali orfani**: hex/rgba ciano hardcoded (`rgba(6,182,212,…)` nei glow `shadow-[…]`, qualche `#06b6d4`/`#0891b2`) NON sono raggiunti dal remap — vanno cambiati a mano dove emergono (al 2026-06-23 ne restano in ~15 template non-base, delegati al giro visivo Antigravity). (4) **Per-sport color**: `Sport.hex_color` è in DB (pallanuoto `#00ffff`) — il remap CSS non lo tocca; allinearlo a blue richiede una migration dati (gate backup + ratifica). La ripulitura completa dei nomi-classe `cyan-*`→`blue-*` è un **task A2 futuro**, non urgente (nessun impatto funzionale/a11y).

## 13. Gating premium server-side (entitlements, dev 2026-07-02)

### 13.1 `api_ai_query` hardened

L'endpoint AI (`matches/api_views.py`) è esposto su due rotte — `/matches/api/v1/ai-query/` (`matches/urls.py`) e `/api/v1/ai-query/` (`matches/api_urls.py`) — ma è la stessa funzione decorata: il gating copre entrambe. Hardening in due passi, entrambi su `dev`:

- `b188349`: da `@csrf_exempt` + accesso anonimo a `@login_required` + CSRF standard (il JS in `base.html` manda `X-CSRFToken`).
- `e7b91d5`: aggiunto `@premium_required` **sotto** `login_required` (ordine login → premium): anonimo → redirect al login; freemium autenticato → `403 {'error': 'premium_required'}`, che la barra AI traduce in CTA "Passa a Premium" (`75ec92d`) invece di un errore grezzo.

### 13.2 `entitlement_service` — unico seam premium/comped con audit

Tutte le mutazioni di `User.plan` e `Society.tier`/`Society.is_comped` passano da `core/services/entitlement_service.py`: `grant_premium`, `revoke_premium`, `set_society_tier`, `set_society_comped`. Ogni funzione è idempotente (no-op se il valore non cambia) e, quando scrive, logga su `AuditLog` con azione `ENTITLEMENT_*` (`ENTITLEMENT_PLAN_GRANTED`, `ENTITLEMENT_PLAN_REVOKED`, `ENTITLEMENT_SOCIETY_TIER_CHANGED`, `ENTITLEMENT_SOCIETY_COMPED_CHANGED`) e `details={'from', 'to', 'source'}`.

Chiamanti oggi: le action dell'admin (`op_admin_site`; `User.plan` e `Society.tier` sono read-only nel form, si cambiano solo via action → seam) e — per il solo lato società/pilota — i seed. Il mock 0,50€ dell'onboarding **non** concede premium: setta solo `User.onboarding_payment_done` (asse funnel, separato dal piano). Domani il webhook di pagamento reale si aggancia qui (`source='stripe_webhook'`), in un punto solo — scope e trigger formalizzati nella macro dedicata [syllabus/19_monetizzazione_stripe.md](syllabus/19_monetizzazione_stripe.md) (🧊 differita). Gating ortogonale all'RBAC; vocabolario completo in DOMAIN_GLOSSARY.md §"Piano / Tier / Entitlement".

## Appendice A — Archivio debiti e fragilità risolti

Voci di §10 chiuse e verificate, spostate qui dalla testa del file per tenere
`## 10. Debiti aperti` ridotto a ciò che è davvero aperto. Niente è cancellato:
ogni voce conserva cosa era, come è stata chiusa, e dove vive nel codice/test.
Il dettaglio blow-by-blow resta recuperabile da git e dalle session note; qui
sta il razionale che spiega perché il codice attuale è fatto così. Gli
identificatori §10.x sono preservati perché §2.3 e §10.5 vi puntano.

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
