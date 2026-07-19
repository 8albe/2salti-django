# Gold standard OCR — dataset di verità umana

Dataset di referti la cui **verità è stata verificata da un umano sull'originale
cartaceo**, non da un modello. Serve a misurare l'accuratezza reale dei provider
OCR (Macro 8) invece della loro confidence auto-dichiarata, che si è dimostrata
attivamente fuorviante (§"Perché esiste" sotto).

**Stato (2026-07-19): 5 casi.** 1 con estrazioni già confrontate (il caso
fondativo, 11/04/2026 — vedi §"Perché esiste"); 4 pronti per il bench ma senza
alcuna estrazione OCR associata (`extractions: []`) — si popoleranno quando
verranno fatti girare.

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
| `truth` | **Solo i campi effettivamente verificati da umano.** Ogni campo non collazionato sta in `not_verified` — mai inferito, mai copiato da un'estrazione. |
| `not_verified` | Elenco esplicito di ciò che nessuno ha ancora controllato. Impedisce che un campo non verificato venga scambiato per verità. |
| `extractions[]` | Una voce per estrazione, con `provider`, `model`, `db_report_pk`, quanto estratto, la confidence auto-dichiarata e il `verdict` campo per campo. **Può essere vuoto (`[]`)**: un caso è gold standard per la sola `truth` verificata, anche prima che qualunque provider lo abbia mai letto — le estrazioni si aggiungono quando il referto viene fatto girare nel bench. |
| `findings` | Cosa insegna questo caso, in forma citabile dalla documentazione. |

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

## Come aggiungere un caso

1. Collaziona il referto cartaceo a mano. Se non hai l'originale sotto gli occhi,
   fermati: non esiste gold standard di seconda mano.
2. Copia un file esistente in `cases/`, sostituisci **tutti** i campi.
3. Riporta in `truth` solo ciò che hai verificato davvero; tutto il resto in
   `not_verified`.
4. Per ogni estrazione già esistente a DB, incolla i valori reali da
   `MatchReport.normalized_data` (non a memoria) e compila `verdict`.
5. Se la correzione tocca dati a DB, registrala anche nell'audit log
   (`MATCH_SCORE_CORRECTED`) e cita qui il `db_match_pk`.

## Uso previsto da `ocr_bench`

Oggi `ocr_bench --report-id N` confronta l'estrazione con `normalized_data`
post-review, cioè con **dati validati da un umano dentro il sistema**. È un
proxy: se la review ha lasciato passare un errore, il bench misura l'aderenza
all'errore.

Il passo previsto è un `--gold-case <case_id>` che confronti l'estrazione con
`truth` di questo dataset, che umano lo è per costruzione, e che riporti
l'accuracy **solo sui campi presenti in `truth`** ignorando quelli in
`not_verified`. Lo schema di `truth` ricalca già lo schema OCR v2
(`scores.final_score`, `scores.quarters`) proprio per rendere il confronto una
diff diretta e non una traduzione.

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
