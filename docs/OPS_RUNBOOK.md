# OPS Runbook — 2salti

Questo file raccoglie le procedure operative dell'infrastruttura 2salti: topologia degli ambienti, regole di allineamento fra home e deploy, trappole tecniche note, convenzioni di pulizia repo e regole metodologiche per le note di sessione. Non contiene né convenzioni di codice (quelle stanno in [CLAUDE.md](../CLAUDE.md)) né la visione di prodotto (quella sta in [PRODUCT_BLUEPRINT.md](PRODUCT_BLUEPRINT.md)); consultarlo quando si lavora sull'infrastruttura, sul deploy, sulla gestione del repo, o quando si chiude/riapre un problema nelle note di sessione. Si aggiorna man mano che emergono pattern operativi ricorrenti: se una lezione viene imparata due volte, probabilmente merita una voce qui.

## 1. Mappa ambienti

L'infrastruttura 2salti oggi è ospitata su una singola macchina Hetzner che serve il dominio `2salti.com`. Su quella macchina convivono due copie del repo, che è una topologia inusuale e va ricordata esplicitamente per non confondersi: `/home/alberto/` è l'ambiente di sviluppo locale dello sviluppatore, e `/opt/2salti-new/` è il deploy attivo da cui gira effettivamente il service in produzione. Sviluppo locale e produzione condividono quindi il filesystem — è un'asimmetria storica da cui è derivata la regola della sezione 2 di questo documento, ed è lo stato attuale con cui si lavora.

Il service systemd si chiama `2salti` e viene servito da Gunicorn con socket unix; Nginx fa da reverse proxy davanti al socket e gestisce TLS e reindirizzamento HTTPS. Il file `.env` con le credenziali di runtime vive nel deploy, in `/opt/2salti-new/.env`, mai nella home e mai nel repo. Gli static files raccolti con `collectstatic` vivono in `/home/alberto/staticfiles/` e sono serviti da whitenoise attraverso Gunicorn; i media uploadati dagli utenti vivono in `/home/alberto/media/`. Entrambi i path sono environment-specific e non vanno hardcoded nel codice — il codice legge `STATIC_ROOT` e `MEDIA_ROOT` dalle settings.

Gli ambienti di staging e dev-remote non sono attualmente attivi; il loro ripristino è tracciato dal problema #10 nel backlog della roadmap residua. Qualsiasi procedura descritta in questo runbook assume i path elencati sopra come stato attuale; se cambiano — per migrazione, per introduzione di staging, per riconfigurazione del deploy — aggiornare prima di tutto questa sezione, perché tutte le sezioni successive vi fanno riferimento implicito.

Un dettaglio importante sulla topologia dei remote git, che va ricordato perché la sua implicazione non è ovvia. La home `/home/alberto/` ha `origin` puntato a `github.com/8albe/2salti-django.git`: è il repo che parla direttamente con GitHub. Il deploy `/opt/2salti-new/` invece ha `origin` puntato al path locale della home (`/home/alberto`), non a GitHub. La topologia è quindi a due salti: `deploy → home → GitHub`, e il deploy non parla direttamente con GitHub. Questo significa che il `git pull origin dev` sul deploy, menzionato nella sezione 2, tira dalla home locale, non da GitHub. Nello scenario ordinario — lavoro da una sola macchina, home sempre allineata a GitHub — la cosa è trasparente. Ma genera due rischi conosciuti da tenere presenti. Primo: se si commette nella home e si dimentica il push a GitHub, un successivo pull sul deploy porta comunque il commit in produzione, e GitHub resta indietro — l'inverso del caso documentato nella sezione 5. Secondo: se un commit atterra su GitHub senza passare dalla home (PR merged via web, push da un'altra macchina, commit fatto da un CI bot futuro), il deploy non lo vedrà finché qualcuno non lo tira prima nella home. Oggi entrambi gli scenari sono teorici perché si lavora solo dal server, ma sono dipendenze fragili — se il workflow cambia, vanno rivalutate, probabilmente aggiungendo un secondo remote `github` al deploy per permettere verifica diretta contro GitHub.

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
