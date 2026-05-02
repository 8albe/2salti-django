# OPS Runbook — 2salti

Questo file raccoglie le procedure operative dell'infrastruttura 2salti: topologia degli ambienti, regole di allineamento fra home e deploy, trappole tecniche note, convenzioni di pulizia repo e regole metodologiche per le note di sessione. Non contiene né convenzioni di codice (quelle stanno in [CLAUDE.md](../CLAUDE.md)) né la visione di prodotto (quella sta in [PRODUCT_BLUEPRINT.md](PRODUCT_BLUEPRINT.md)); consultarlo quando si lavora sull'infrastruttura, sul deploy, sulla gestione del repo, o quando si chiude/riapre un problema nelle note di sessione. Si aggiorna man mano che emergono pattern operativi ricorrenti: se una lezione viene imparata due volte, probabilmente merita una voce qui.

## 1. Mappa ambienti

L'infrastruttura 2salti oggi è ospitata su una singola macchina Hetzner che serve il dominio `2salti.com`. Su quella macchina convivono due copie del repo, che è una topologia inusuale e va ricordata esplicitamente per non confondersi: `/home/alberto/` è l'ambiente di sviluppo locale dello sviluppatore, e `/opt/2salti-new/` è il deploy attivo da cui gira effettivamente il service in produzione. Sviluppo locale e produzione condividono quindi il filesystem — è un'asimmetria storica da cui è derivata la regola della sezione 2 di questo documento, ed è lo stato attuale con cui si lavora.

Il service systemd si chiama `2salti` e viene servito da Gunicorn con socket unix; Nginx fa da reverse proxy davanti al socket e gestisce TLS e reindirizzamento HTTPS. Il file `.env` con le credenziali di runtime vive nel deploy, in `/opt/2salti-new/.env`, mai nella home e mai nel repo. Gli static files raccolti con `collectstatic` vivono in `/home/alberto/staticfiles/` e sono serviti da whitenoise attraverso Gunicorn; i media uploadati dagli utenti vivono in `/home/alberto/media/`. Entrambi i path sono environment-specific e non vanno hardcoded nel codice — il codice legge `STATIC_ROOT` e `MEDIA_ROOT` dalle settings.

Gli ambienti di staging e dev-remote non sono attualmente attivi; il loro ripristino è tracciato dal problema #10 nel backlog della roadmap residua. Qualsiasi procedura descritta in questo runbook assume i path elencati sopra come stato attuale; se cambiano — per migrazione, per introduzione di staging, per riconfigurazione del deploy — aggiornare prima di tutto questa sezione, perché tutte le sezioni successive vi fanno riferimento implicito.

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

## 10. Debiti aperti

Registro vivo di problemi noti che richiedono follow-up. Non sono trappole (§3) né bug attivi: sono incoerenze scoperte ma non risolte, da affrontare in sessioni dedicate.

### 10.1 Report PUBLISHED con blocker quality gate (debito dati storico)

Scoperto il 2-mag durante la verifica live del wire OCRQualityGate (commit `193436b`). Il referto `MatchReport id=8` è in stato `PUBLISHED` ma il quality gate appena cablato lo blocca: i nomi squadra estratti dall'OCR ("ME", "NAUTILUS ROMA") non corrispondono ai nomi DB ("Nautilus Nuoto Roma", "Unime pallanuoto"), e c'è un'inversione home/away fra cartaceo e DB.

**Causa root:** referti pubblicati prima del wire, quando il quality gate era implementato e testato ma non chiamato dalla view admin. Pattern "feature half-shipped" — la pubblicazione è andata avanti senza il check di coerenza nomi.

**Domande aperte:**
- Quanti report `PUBLISHED` falliscono ora il quality gate? Censimento da fare.
- I match collegati hanno standings/stats coerenti, o l'inversione home/away ha contaminato i conteggi?
- I referti vanno re-validati manualmente, oppure depubblicati e riprocessati?
- Il quality gate va reso *advisory* per report `PUBLISHED` (mostra ma non blocca operazioni successive)?

**Cosa NON fare ora:** non depubblicare in massa, non re-runnare OCR sui PUBLISHED, non modificare gli standings derivati. Ogni intervento richiede analisi dell'impatto sul dato pubblico.

**Prossimi passi candidati:**
1. Censimento: query su `MatchReport.objects.filter(status='PUBLISHED')` con esecuzione di `OCRQualityGate.evaluate()` post-hoc per contare quanti hanno `is_valid=False`.
2. Per i casi rilevati, verifica caso per caso se l'inversione home/away ha effetto sui conteggi standings.
3. Decisione di prodotto: gate strict su PUBLISHED (forza re-review) oppure gate advisory (segnala ma non blocca).

