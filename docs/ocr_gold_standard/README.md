# Gold standard OCR — dataset di verità umana

Dataset di referti la cui **verità è stata verificata da un umano sull'originale
cartaceo**, non da un modello. Serve a misurare l'accuratezza reale dei provider
OCR (Macro 8) invece della loro confidence auto-dichiarata, che si è dimostrata
attivamente fuorviante (§"Perché esiste" sotto).

**Stato (2026-07-20): 6 casi, tutti benchabili.** 2 con estrazioni già
confrontate (il caso fondativo 11/04/2026 — vedi §"Perché esiste" — e il
06/12/2025 Pol. Delta vs Villa York); 4 pronti per il bench ma senza alcuna
estrazione OCR associata (`extractions: []`) — si popoleranno quando verranno
fatti girare. Non esistono più casi truth-only: l'ultimo a mancare
dell'immagine (Triscelon Etna Sport, 25/04/2026) l'ha ricevuta il 2026-07-20;
non avendo `db_report_pk` (nessun report a DB per questa coppia/data), va
benchato con `--image` esplicito — vedi `image_status` nel suo file caso.

Con il sesto caso i **quattro** match presenti a DB sono tutti stati collazionati
sul cartaceo e tutti e quattro avevano dati sbagliati (4/4). In tutti e quattro la
somma dei parziali tornava al finale dichiarato: il controllo strutturale ha
rilevato **0 casi su 4**. Dettaglio in
[docs/syllabus/8_ocr_affidabilita.md](../syllabus/8_ocr_affidabilita.md) §8.5(d).

## Perché sta in `docs/` e non in `matches/fixtures/`

Non è una fixture Django: non si carica con `loaddata`, non popola un DB di test
e non descrive lo stato dell'applicazione. È **materiale curato a mano**, che si
rivede in code review come si rivede un documento, e che cresce una riga alla
volta ogni volta che un umano collaziona un referto. Vive quindi accanto alla
documentazione della macro che lo usa, ma in formato macchina — in una directory
propria, così `ocr_bench` può fare glob su `cases/*.json` senza sfiorare la prosa.

## Struttura

```
docs/ocr_gold_standard/
├── README.md          questo file (schema + procedura)
└── cases/
    └── <data>_<home-slug>_vs_<away-slug>.json    un file per referto verificato
```

Un file per caso, non un unico dataset monolitico: i casi si aggiungono in
momenti diversi da persone diverse, e file separati non producono conflitti di
merge.

## Schema di un caso

| Campo | Significato |
|---|---|
| `case_id` | Identificatore stabile del caso. Mai riusato, mai rinumerato. |
| `verified_by` / `verified_at` | **Chi** ha collazionato e **quando**. Senza questi il caso non è gold standard: è un'altra opinione. |
| `verification_method` | Come è stata stabilita la verità (es. `referto cartaceo originale`). |
| `match` | Aggancio al DB (`db_match_pk`, `db_league_pk`) e alle squadre, con **`name_on_paper`** accanto a `db_team_name`: la divergenza fra i due è essa stessa un dato (fallimento della discovery). |
| `match.legibility` | *(opzionale)* Quanto è leggibile il cartaceo: `{score, assessed_by, assessed_at, notes}`. Vedi §"Leggibilità del foglio" sotto per la scala e il criterio. Senza questo campo non si assume nulla sulla leggibilità: niente default. |
| `truth` | **Solo i campi effettivamente verificati da umano.** Ogni campo non collazionato sta in `not_verified` — mai inferito, mai copiato da un'estrazione. |
| `not_verified` | Elenco esplicito di ciò che nessuno ha ancora controllato. Impedisce che un campo non verificato venga scambiato per verità. |
| `extractions[]` | Una voce per estrazione, con `provider`, `model`, `db_report_pk`, quanto estratto, la confidence auto-dichiarata e il `verdict` campo per campo. **Può essere vuoto (`[]`)**: un caso è gold standard per la sola `truth` verificata, anche prima che qualunque provider lo abbia mai letto — le estrazioni si aggiungono quando il referto viene fatto girare nel bench. |
| `findings` | Cosa insegna questo caso, in forma citabile dalla documentazione. |
| `corrections[]` | *(opzionale)* Correzioni applicate alla `truth` **dopo** la prima collazione, con `field`, `before`, `after`, `corrected_at`/`corrected_by` e `reason`. Un caso gold non si riscrive in silenzio: la storia delle sue correzioni è parte del dato. Vedi §"Il metro misura anche chi lo ha costruito". |
| `pending_reverification[]` | *(opzionale)* Campi **sospesi**: non modificati, ma segnalati come non affidabili in attesa che un umano torni sull'originale. Usato quando un errore accertato su un caso mette in dubbio i casi collazionati nella stessa sessione. Una volta che la riverifica arriva, il blocco si rimuove e si sostituisce con `reverification` (conferma) o `corrections[]` (se anche questa lettura era sbagliata). |
| `reverification` | *(opzionale)* Esito di una riverifica che **conferma** un valore già in `truth`/`match` dopo che era stato messo in dubbio: `{reverified_at, reverified_by, field, outcome, context}`. A differenza di `corrections[]`, qui il valore non cambia — si registra solo che è stato ricontrollato e regge. |
| `corroboration` | *(opzionale)* Conferma (o tentativo di conferma) della `truth` da una **seconda zona indipendente** del foglio (es. storia cronometrica dei gol vs riquadro parziali). Tre stati: concorde (`method_note` lo dichiara, vedi `2025-12-06_pol-delta_vs_villa-york.json`), divergente (il caso non si chiude, si torna sul cartaceo — procedura 3b sotto), o **non ottenibile** (`status: "non ottenibile"` + `reason`, tipicamente per leggibilità: vedi `2026-04-11_bellator-frusino_vs_ss-lazio-nuoto.json`). Il terzo stato non è un caso chiuso senza corroborazione taciuta: è dichiarato esplicitamente. |

`verdict` usa tre soli valori: `correct`, `wrong`, `unverified`.

## Regola di dominio: la stagione non si deduce dalla data

La stagione sportiva va da **settembre a luglio** e attraversa due anni solari
(es. `2025/2026`). Dedurre la stagione dall'anno solare della data di gara è
**sbagliato per definizione**: una gara datata aprile, maggio, giugno o luglio
appartiene alla stagione iniziata l'anno solare *precedente*, non a quello
scritto nella data. Nei casi di questo dataset si trascrive sempre la **data
come scritta sul referto** (campo `match.date`); il campo `match.season` va
compilato leggendo la stagione effettiva del campionato (calendario/lega), mai
inferendola a mano dall'anno della data. Registrata anche in
[DOMAIN_GLOSSARY.md](../DOMAIN_GLOSSARY.md) §"Stagione".

## Nessuna lettura di un modello entra in `truth` senza verifica umana

Vale per i provider OCR **e per Claude in chat**. In questa stessa sessione,
mentre si preparavano i casi 2–5 di questo dataset, Claude in chat ha letto
"2025" dove il referto originale riportava "2026" — con la stessa sicurezza
con cui i provider OCR di §"Perché esiste" hanno dichiarato `confidence 1.0`
su valori sbagliati. Il pattern è lo stesso indipendentemente dal modello: un
sistema che legge un documento denso può essere internamente coerente e
comunque falso. Il campo `truth` di questo dataset accetta **solo** valori
riportati da un umano che ha guardato l'originale cartaceo (`verified_by` +
`verification_method`); nessuna eccezione per "il modello sembrava sicuro".

## Il metro misura anche chi lo ha costruito (2026-07-20)

La regola sopra resta valida, ma da sola non basta: **anche la collazione umana
sbaglia**, e il primo errore che questo dataset ha prodotto non è venuto da un
modello.

Cos'è successo. Il caso fondativo 11/04/2026 registrava
`name_on_paper = "BELLATOR FROSINONE"` accanto al nome a DB `Bellator Frusino`,
e da lì si era dedotto un finding di discovery: divergenza di grafia foglio↔DB,
con direzione di lavoro conseguente (tabella di alias, §8.6 del syllabus). Il
bench ha esposto la discrepanza, Alberto è tornato sul cartaceo, e sul foglio
c'era scritto **`BELLATOR FRUSINO`** — cioè esattamente il nome a DB. La
divergenza non esisteva: era un errore di collazione umana introdotto il
2026-07-19. La diagnosi corretta è opposta: l'OCR ha letto male un nome scritto
bene, e la discovery ha fallito su un input già corrotto a monte.

Da cui due regole operative:

1. **Una discrepanza bench↔truth non è automaticamente un errore del modello.**
   È un disaccordo fra due letture, e finché non si torna sull'originale non si
   sa quale delle due è sbagliata. Attribuirla al provider per default significa
   usare la `truth` come assioma invece che come misura — e una `truth` non
   riverificata è un'opinione con più autorità delle altre, non una verità.
2. **Il metro va ricontrollato quando lo strumento lo contraddice.** Un
   disaccordo persistente su un campo è un segnale che punta in entrambe le
   direzioni. Se la riverifica corregge la `truth`, la correzione si registra
   nel caso (campo `corrections`: valore prima/dopo, data, motivo) e i `verdict`
   delle estrazioni già presenti si riclassificano di conseguenza — nel caso
   Bellator, `home_team_name` è passato da `correct` a `wrong` per entrambi i
   provider.

Corollario sui casi vicini: un errore di collazione raramente è isolato, perché
nasce dalle condizioni di una sessione (foglio illeggibile, fretta, un nome
raro). Quando un caso viene corretto, i casi collazionati nella **stessa
sessione** che sostengono lo **stesso tipo di finding** vanno marcati
`pending_reverification` — non corretti, non cancellati: sospesi finché un umano
non li ha riguardati. È stato fatto per Olympic Roma P.N. e per le tre
occorrenze di Nautilus, e la riverifica del 2026-07-20 ha dato esito **diverso
caso per caso**: Olympic e Nautilus erano letture corrette fin dall'inizio (la
divergenza di grafia foglio↔DB è reale — `reverification` nei casi), mentre nel
frattempo la stessa riverifica ha trovato un **secondo** errore di collazione,
indipendente dal primo, su un caso diverso (Triscelon Etna Sport, trascritto
"Trisceloni" il 19/07 — `corrections` nel caso). La lezione non è "diffidare di
un caso specifico": è che ogni lettura da quella sessione andava ricontrollata
prima di fondarci sopra una direzione di lavoro, e il sospetto non garantiva da
solo quali letture fossero sbagliate.

## Leggibilità del foglio (2026-07-20)

Un errore del provider su un referto compilato male e un errore sullo stesso
campo su un foglio pulito non sono lo stesso segnale: confrontare provider su
casi di difficoltà molto diversa senza saperlo confonde "il modello legge
male" con "il foglio è illeggibile". Il campo `match.legibility` rende
misurabile questa differenza:

```json
"legibility": {
  "score": 2,
  "assessed_by": "Alberto Galbiati",
  "assessed_at": "2026-07-20",
  "notes": "testo libero: cosa rende il foglio difficile"
}
```

Scala a 4 livelli, ancorata a un'azione umana (non a un giudizio soggettivo di
"pulito/sporco"):

| `score` | Criterio |
|---|---|
| 4 — pulito | Un umano legge ogni campo al primo colpo, senza esitare. |
| 3 — leggibile | Qualche campo richiede una seconda occhiata, nessuno richiede di dedurre. |
| 2 — faticoso | Almeno un campo si legge solo **per contesto** (aritmetica dei parziali, conoscenza delle squadre). |
| 1 — al limite | Almeno un campo resta **indecifrabile** anche dopo riverifica: due lettori potrebbero trascrivere valori diversi. |

**Regola: un caso a `score` 1 o 2 richiede `corroboration` per essere chiuso.**
Sotto il 3 la truth stessa è a rischio (è quanto successo sul caso Bellator,
`score` 2), quindi non basta una lettura, per quanto attenta: serve una seconda
fonte indipendente dentro il foglio (procedura 3b sotto). **Se la
corroborazione non è ottenibile** — perché anche la seconda zona del foglio
è illeggibile, non perché nessuno l'ha cercata — questo va dichiarato
esplicitamente nel campo `corroboration` (`status: "non ottenibile"` +
`reason`), non lasciato implicito. Un caso a `score` 1-2 senza `corroboration`
e senza una dichiarazione esplicita di non ottenibilità è un caso aperto, non
chiuso.

Nessun default: un caso senza `match.legibility` non è "presunto leggibile",
è semplicemente **non ancora valutato**. La valutazione richiede il cartaceo
sotto gli occhi, come la collazione stessa — si popola con lo stesso rigore,
non retroattivamente a memoria.

**Lettura del dataset (2026-07-20).** Con tutti e sei i casi valutati, la
distribuzione di `legibility.score` è: **0 a 4, due a 3, tre a 2, uno a 1** —
cioè **quattro casi su sei sotto la soglia (< 3) in cui la truth stessa è a
rischio** (regola sopra). Non è un dato sul dataset, cioè su come è stato
costruito: è un dato sul **dominio** — referti compilati a mano a bordo vasca,
spesso in fretta e in condizioni difficili — e va tenuto presente in ogni
confronto fra provider OCR. Un campione con questa distribuzione di
leggibilità non è un caso limite scelto ad arte: è rappresentativo della
popolazione reale di referti che il sistema deve affrontare.

## Come aggiungere un caso

1. Collaziona il referto cartaceo a mano. Se non hai l'originale sotto gli occhi,
   fermati: non esiste gold standard di seconda mano.
2. Copia un file esistente in `cases/`, sostituisci **tutti** i campi.
3. Riporta in `truth` solo ciò che hai verificato davvero; tutto il resto in
   `not_verified`. Se un campo l'ha letto un modello e non un umano, va in
   `not_verified` anche se sembra ovvio (es. impianto, città, orario).
3b. **Cerca la corroborazione dentro il foglio.** Il riquadro dei parziali e la
   storia cronometrica (sequenza dei gol col minuto) sono due zone compilate
   separatamente: se i cumulati della progressione coincidono con i parziali,
   la `truth` ha due fonti concordi e va registrata nel campo `corroboration`
   (vedi `2025-12-06_pol-delta_vs_villa-york.json`). Se divergono, il caso non
   si chiude: si marca e si torna sul cartaceo. Se il caso ha `match.legibility`
   1 o 2, la corroborazione non è opzionale (vedi §"Leggibilità del foglio"); se
   la seconda zona è a sua volta illeggibile, dichiaralo esplicitamente in
   `corroboration` (`status: "non ottenibile"` + `reason`) invece di lasciare
   il campo assente (vedi `2026-04-11_bellator-frusino_vs_ss-lazio-nuoto.json`).
4. Per ogni estrazione già esistente a DB, incolla i valori reali da
   `MatchReport.normalized_data` (non a memoria) e compila `verdict`.
5. Se la correzione tocca dati a DB, registrala anche nell'audit log
   (`MATCH_SCORE_CORRECTED`) e cita qui il `db_match_pk`.

## Uso da `ocr_bench` (harness di misura, dal 2026-07-20)

`ocr_bench --report-id N` confronta l'estrazione con `normalized_data`
post-review, cioè con **dati validati da un umano dentro il sistema**. È un
proxy: se la review ha lasciato passare un errore, il bench misura l'aderenza
all'errore.

La modalità gold confronta invece con la `truth` di questo dataset, che umana
lo è per costruzione:

```bash
python manage.py ocr_bench --gold-case <case_id>          # un caso
python manage.py ocr_bench --gold-all                     # tutti i casi
python manage.py ocr_bench --gold-case <case_id> --image <path>  # caso senza report a DB
```

L'immagine si risolve dai `db_report_pk` del caso (top-level, poi
`extractions[]`); i casi senza immagine risolvibile vengono saltati con avviso
in `--gold-all`. Cosa misura, per campo e mai aggregato:

- `final_score` spaccato in home e away separati; gli 8 valori dei quarti
  separatamente;
- nomi squadre contro **`name_on_paper`**, mai contro il nome a DB (la
  divergenza foglio↔DB è un problema della discovery, non dell'OCR);
- esito ternario `correct` / `wrong` / `null`: il null ("dichiaro di non saper
  leggere") è conteggiato a parte, non come errore;
- check esplicito di **inversione casa/trasferta** (valori giusti attribuiti
  alla squadra sbagliata: la classe di errore del match 2, invisibile al
  confronto campo-per-campo);
- accanto a ogni verdetto, la confidence auto-dichiarata del provider (curva
  di calibrazione);
- **solo i campi presenti in `truth`** (più `name_on_paper` e la data del
  blocco `match`, anch'essi verificati da umano): ciò che sta in
  `not_verified` è ignorato per costruzione.

Ogni run registra modello, versione del prompt (nome + hash), preprocessing
on/off e timestamp: senza questi il bench non è ripetibile.

**Le estrazioni del bench NON vengono mai scritte in `extractions[]`**
(decisione D1, 2026-07-20): ogni estrazione produce un file di **proposta**
nello schema delle voci `extractions[]`, salvato in `--out-dir` (default
`ocr_bench_out/gold/`, gitignorata). Il riversamento nel caso resta un atto
umano dopo review: un bug del bench non deve poter inquinare la verità.

## Perché esiste

Sul primo caso collazionato (11/04/2026) **entrambi** i provider hanno sbagliato
il punteggio, **entrambi** hanno dichiarato `confidence_fields.final_score = 1.0`,
ed **entrambi** hanno prodotto errori sui parziali che si compensano: la somma
dei parziali torna al totale dichiarato in tutte e due le estrazioni sbagliate.
Il controllo strutturale "somma parziali == punteggio finale" (BLUEPRINT §9)
quindi **passa su dati falsi**: verifica la coerenza interna, non la verità.

Finché non esiste un controllo indipendente, l'unica cosa che discrimina il vero
dal coerente è un umano davanti al cartaceo. Questo dataset è il prodotto di
quel lavoro, reso riutilizzabile.
