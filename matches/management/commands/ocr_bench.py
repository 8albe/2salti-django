"""
Bench read-only per confrontare modelli OCR sulla stessa immagine di referto.

Per ogni modello richiesto esegue una estrazione reale (chiamata all'LLM,
costo reale) e stampa confidence auto-dichiarata, latenza e token usage.
Con --report-id confronta l'estrazione grezza con i dati validati
(normalized_data post-review) e stampa un accuracy exact-match per campo.
Con --show stampa un blocco leggibile per modello con i campi chiave estratti
(squadre, punteggio, quarti, roster, eventi) per il confronto a occhio col
referto fisico. Con --save-dir <path> salva il JSON completo estratto da
ciascun modello in <path>/ocr_bench_<model>_<timestamp>.json.
Con --dump-sent-image <dir> salva su disco l'immagine esattamente inviata al
modello (output del preprocessing, o i byte grezzi con --no-preprocess) come
<dir>/ocr_bench_sent_<model>_<timestamp>.<ext>; il dump avviene prima della
chiamata API, quindi anche se la chiamata poi fallisce.
Con --no-preprocess bypassa ImagePreprocessor e invia l'immagine grezza
(niente auto-rotate a portrait né downscale).

Modalità gold standard (Macro 8):
  --gold-case <case_id>   un caso di docs/ocr_gold_standard/cases/
  --gold-all              tutti i casi (glob su cases/*.json)
Confronta l'estrazione con la `truth` verificata da umano del caso, campo per
campo e mai aggregato: final_score spaccato home/away, gli 8 valori dei quarti
separati, nomi squadre contro `name_on_paper` (non il nome a DB), esito
ternario correct/wrong/null (il null è conteggiato a parte, non come errore),
check esplicito di inversione casa/trasferta, confidence auto-dichiarata
accostata a ogni verdetto. Si confrontano SOLO i campi presenti in `truth`:
ciò che sta in `not_verified` è ignorato per costruzione.
L'immagine si risolve dai `db_report_pk` del caso (file del MatchReport), o da
--image esplicito (solo con --gold-case) per i casi senza report a DB.
Ogni estrazione produce un file di PROPOSTA in --out-dir (default
<BASE_DIR>/ocr_bench_out/gold/, gitignorata), nello schema delle voci
extractions[] dei casi gold. La proposta NON viene mai scritta nel caso:
il riversamento in extractions[] resta un atto umano dopo review (decisione
D1: un bug del bench non deve poter inquinare la verità).

Con --repeat N (richiede --gold-case/--gold-all) esegue N estrazioni
indipendenti per caso/modello: l'estrazione non è deterministica (stesso
modello, stesso referto, valori diversi fra chiamate — es. "BELLATOR
FROSINONE" e "BELLATOR FROSINO" sullo stesso report, entrambi confidence
1.0), quindi una singola chiamata è un campione, non "la" lettura del
modello. Per ogni campo riporta i valori distinti con frequenza, se il
campo è stabile (tutte le ripetizioni concordi) o instabile, e — se
stabile — se è anche sbagliato: un errore riproducibile che nessuna
ripetizione da sola smaschererebbe. Un campo instabile con una maggioranza
stretta (un valore con conteggio > N/2) prende il verdetto di quel valore;
un campo instabile SENZA maggioranza stretta (pareggio, es. 2-2 su 4
chiamate) prende l'esito distinto 'ambiguo', mai risolto in correct/wrong
da un tie-break silenzioso per ordine di arrivo — un tie-break del genere
darebbe esiti diversi a seconda dell'ordine delle chiamate, quindi non è
una misura (caso reale: "BELLATOR FRUSINO" x2 corretto, "BELLATOR
FROSINONE" x2 sbagliato, pareggio). Resta per-campo, mai un'unica
percentuale aggregata sul caso, e gli ambigui hanno un bucket proprio nel
riepilogo, mai sommati ai corretti né agli sbagliati. La proposta contiene
tutte le N estrazioni in repeats[] (mai solo l'ultima) più l'aggregato in
aggregate[].

Nessuna scrittura sul DB: niente salvataggi di MatchReport,
niente transizioni di stato.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import time
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from matches.models import MatchReport
from matches.services.ocr_double_extraction import ZONES, compare_passes
from matches.services.vision_providers import (
    GeminiVisionProvider,
    OCR_ALL_PROMPTS,
    OCR_SYSTEM_PROMPT_V2,
    OCR_SYSTEM_PROMPTS,
)

# Mappa provider bench: nome CLI -> (setting del modello di default, fallback).
# NB: la CLASSE del provider viene risolta a runtime dentro handle() leggendo i
# simboli di questo modulo, così i test possono patchare GeminiVisionProvider
# senza che un riferimento catturato all'import lo scavalchi. Il seam resta
# estendibile: aggiungere un provider = una entry qui + una nel map in handle().
PROVIDER_MODEL_SETTINGS = {
    "gemini": ("GEMINI_MODEL", "gemini-2.5-pro"),
}

# Campi top-level confrontati per l'accuracy exact-match
ACCURACY_FIELDS = [
    "home_team",
    "away_team",
    "final_score",
    "quarters_count",
    "home_roster_count",
    "away_roster_count",
    "events_count",
]


def extract_comparable_fields(data):
    """Estrae i campi top-level confrontabili da un dict in schema OCR v2."""
    info = data.get("match_info") or {}
    scores = data.get("scores") or {}
    teams = data.get("teams") or {}
    return {
        "home_team": info.get("home_team"),
        "away_team": info.get("away_team"),
        "final_score": scores.get("final_score"),
        "quarters_count": len(scores.get("quarters") or {}),
        "home_roster_count": len((teams.get("home") or {}).get("players") or []),
        "away_roster_count": len((teams.get("away") or {}).get("players") or []),
        "events_count": len(data.get("events") or []),
    }


ASSENTE = "— assente"

# --- Modalità gold standard -------------------------------------------------

GOLD_CASES_DIR_DEFAULT = os.path.join("docs", "ocr_gold_standard", "cases")
GOLD_OUT_DIR_DEFAULT = os.path.join("ocr_bench_out", "gold")

# Versione del prompt registrata in ogni run: nome del simbolo + hash del testo.
# L'hash cambia se il prompt cambia, quindi due run sono confrontabili solo a
# parità di questa stringa. Read-only sulla pipeline: il prompt non si tocca.


def prompt_version_string(version):
    """Stringa identificativa del prompt selezionato: simbolo + hash del testo.

    Risolve su OCR_ALL_PROMPTS: oltre a v2/v3 accetta i prompt del secondo
    passaggio (zone), così un run di doppia estrazione registra l'hash del
    prompt zone esattamente come per le versioni di produzione.
    """
    text = OCR_ALL_PROMPTS[version]
    return f"OCR_SYSTEM_PROMPT_{version.upper()}@sha256:" + hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:12]


# Retrocompatibilità: la costante storica resta la stringa del default (v2).
PROMPT_VERSION = prompt_version_string("v2")


def normalize_team_name(name):
    """Normalizza un nome squadra per il confronto col foglio (maiuscole, solo alfanumerici).

    'S.S. LAZIO NUOTO' e 'SS LAZIO NUOTO' devono risultare uguali: la
    punteggiatura non è un errore di lettura.
    """
    if not isinstance(name, str):
        return None
    return re.sub(r"[^A-Z0-9]", "", name.upper()) or None


def parse_final_score(value):
    """'X-Y' -> (X, Y) come interi; None se null o non parsabile."""
    if not isinstance(value, str):
        return None
    m = re.match(r"^\s*(\d+)\s*[-–]\s*(\d+)\s*$", value)
    return (int(m.group(1)), int(m.group(2))) if m else None


def quarter_value(quarters, key, side):
    """Valore di un lato (0=home, 1=away) di un quarto; None se assente/null."""
    if not isinstance(quarters, dict):
        return None
    q = quarters.get(key) if key in quarters else quarters.get(str(key))
    if not isinstance(q, (list, tuple)) or len(q) != 2:
        return None
    v = q[side]
    return v if isinstance(v, int) else None


def confidence_key_for(field):
    """Mappa un campo del bench sulla chiave di metadata.confidence_fields."""
    if field.startswith("final_score"):
        return "final_score"
    if field.startswith("quarter_"):
        return "quarters"
    if field == "home_team_name":
        return "home_team"
    if field == "away_team_name":
        return "away_team"
    if field == "date":
        # Chiave presente solo nello schema del prompt v3 (confidence dedicata
        # alla data); con v2 la chiave manca e la confidence resta N/A come prima.
        return "date"
    return None


def compare_extraction_to_truth(case, data):
    """Confronta un'estrazione (schema OCR v2) con la truth di un caso gold.

    Ritorna (fields, inversion):
      fields: dict ordinato campo -> {truth, extracted, verdict, confidence}
              con verdict in {correct, wrong, null}. Solo campi presenti in
              truth (più i name_on_paper e la data del blocco match, anch'essi
              verificati da umano). null = il provider ha dichiarato di non
              saper leggere: conteggiato a parte, mai come errore.
      inversion: check esplicito casa/trasferta — valori giusti attribuiti
              alla squadra sbagliata (classe di errore del match 2), invisibile
              al confronto campo-per-campo.
    """
    truth_scores = (case.get("truth") or {}).get("scores") or {}
    case_match = case.get("match") or {}
    ext_scores = data.get("scores") or {}
    ext_info = data.get("match_info") or {}
    conf_fields = (data.get("metadata") or {}).get("confidence_fields") or {}

    fields = {}

    def add(field, truth_v, ext_v, verdict=None):
        if verdict is None:
            if ext_v is None:
                verdict = "null"
            elif ext_v == truth_v:
                verdict = "correct"
            else:
                verdict = "wrong"
        conf_key = confidence_key_for(field)
        fields[field] = {
            "truth": truth_v,
            "extracted": ext_v,
            "verdict": verdict,
            "confidence": conf_fields.get(conf_key) if conf_key else None,
        }

    # final_score spaccato in home e away separati
    truth_final = parse_final_score(truth_scores.get("final_score"))
    raw_final = ext_scores.get("final_score")
    ext_final = parse_final_score(raw_final)
    if truth_final:
        if raw_final is not None and ext_final is None:
            # Valorizzato ma non parsabile: non è un null dichiarato, è un errore.
            add("final_score_home", truth_final[0], raw_final, verdict="wrong")
            add("final_score_away", truth_final[1], raw_final, verdict="wrong")
        else:
            add("final_score_home", truth_final[0], ext_final[0] if ext_final else None)
            add("final_score_away", truth_final[1], ext_final[1] if ext_final else None)

    # gli 8 valori dei quarti, separatamente
    truth_quarters = truth_scores.get("quarters") or {}
    ext_quarters = ext_scores.get("quarters") or {}
    for k in sorted(truth_quarters, key=str):
        for side, label in ((0, "home"), (1, "away")):
            tv = quarter_value(truth_quarters, k, side)
            if tv is None:
                continue  # quarto non in truth: fuori dal confronto
            add(f"quarter_{k}_{label}", tv, quarter_value(ext_quarters, k, side))

    # nomi squadre contro name_on_paper (NON il nome a DB: la divergenza
    # foglio<->DB è un problema della discovery, non dell'OCR)
    paper = {}
    for side_key, field in (("home_team", "home_team_name"), ("away_team", "away_team_name")):
        name_on_paper = (case_match.get(side_key) or {}).get("name_on_paper")
        paper[side_key] = name_on_paper
        if name_on_paper:
            ext_name = ext_info.get(side_key)
            if ext_name is None:
                add(field, name_on_paper, None)
            else:
                equal = normalize_team_name(ext_name) == normalize_team_name(name_on_paper)
                add(field, name_on_paper, ext_name, verdict="correct" if equal else "wrong")

    # data come scritta sul referto (blocco match, verificata da umano)
    truth_date = case_match.get("date")
    if truth_date:
        add("date", truth_date, ext_info.get("date"))

    # --- check esplicito di inversione casa/trasferta ---
    inversion = {"final_score": None, "quarters": {}, "team_names": None}
    if truth_final and ext_final and truth_final[0] != truth_final[1]:
        inversion["final_score"] = (
            ext_final == (truth_final[1], truth_final[0]) and ext_final != truth_final
        )
    for k in sorted(truth_quarters, key=str):
        th = quarter_value(truth_quarters, k, 0)
        ta = quarter_value(truth_quarters, k, 1)
        eh = quarter_value(ext_quarters, k, 0)
        ea = quarter_value(ext_quarters, k, 1)
        if None in (th, ta, eh, ea) or th == ta:
            inversion["quarters"][str(k)] = None  # non computabile (null o truth simmetrica)
        else:
            inversion["quarters"][str(k)] = (eh, ea) == (ta, th)
    norm_paper_home = normalize_team_name(paper.get("home_team"))
    norm_paper_away = normalize_team_name(paper.get("away_team"))
    norm_ext_home = normalize_team_name(ext_info.get("home_team"))
    norm_ext_away = normalize_team_name(ext_info.get("away_team"))
    if all((norm_paper_home, norm_paper_away, norm_ext_home, norm_ext_away)) \
            and norm_paper_home != norm_paper_away:
        inversion["team_names"] = (
            norm_ext_home == norm_paper_away and norm_ext_away == norm_paper_home
        )
    inversion["any"] = any(
        v is True
        for v in [inversion["final_score"], inversion["team_names"], *inversion["quarters"].values()]
    )
    return fields, inversion


def _norm_surname(name):
    """Cognome normalizzato per confronto: minuscole, iniziale finale e formattazione rimosse.

    'DE LENA D.' e 'de lena d.' -> 'delena'; "D'ANGELO C." -> 'dangelo'. Il confronto
    ignora l'iniziale del nome (spesso illeggibile e non discriminante) e punteggiatura,
    perche' il segnale utile e' se il COGNOME e' stato letto, non la sua formattazione.
    Ritorna None se il nome non e' una stringa (es. casella ambigua o sconosciuta in truth).
    """
    if not isinstance(name, str):
        return None
    s = name.strip().lower()
    s = re.sub(r"\s+[a-z]\.?$", "", s)   # via l'iniziale finale ('d.', 'm')
    s = re.sub(r"[^a-z]", "", s)          # via spazi, apostrofi, punti
    return s or None


def _edit_distance_le1(a, b):
    """True se `a` e `b` distano al più 1 edit (sostituzione/inserimento/cancellazione).

    Bounded a 1: distingue 'l'OCR ha sbagliato una lettera' (pelliccione/pellicone,
    d=1) da 'ha letto un altro giocatore' (d>=2). Non serve un Levenshtein pieno.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:  # una sola sostituzione ammessa
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    # lunghezze che differiscono di 1: b deve essere a con un carattere inserito
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True  # salta il carattere in più di b
            j += 1
    return True


def compare_events_to_truth(case, data):
    """Confronto ADDITIVO eventi estratti vs truth eventi di un caso gold.

    Non tocca il confronto sui punteggi (compare_extraction_to_truth): misura la
    dimensione EVENTI, oggi assente dal bench. Ritorna None se il caso non ha
    `truth.events` (retrocompatibile: i casi senza eventi verificati restano invariati).

    Usa gli stessi SCORE_EVENT_CODES della pipeline: un gol tipizzato con un codice
    fuori da quell'insieme (es. 'PENALTY_GOAL', emesso davvero dal modello sul referto
    11) NON conta come gol, esattamente come nel gate di pubblicazione — cosi' il bench
    riproduce il difetto reale invece di mascherarlo.

    Confronta cio' che entrambe le zone hanno in comune: tipo + squadra + periodo.
    L'attribuzione al singolo giocatore NON e' confrontabile qui (la truth porta la
    calottina, l'OCR il nome), ma la presenza/assenza dell'autore sul gol lo e':
    `goals_with_author` misura il blocker 'Zero Eventi'.
    """
    truth = case.get("truth") or {}
    truth_events = truth.get("events")
    if not isinstance(truth_events, list):
        return None
    from matches.event_types import SCORE_EVENT_CODES

    def summarize(events):
        goals_by_pt = {}
        goals_total = {"home": 0, "away": 0}
        goals_with_author = 0
        for e in events or []:
            if not isinstance(e, dict):
                continue
            if e.get("type") in SCORE_EVENT_CODES and e.get("team") in ("home", "away"):
                side = e["team"]
                goals_total[side] += 1
                q = e.get("quarter")
                key = f"{'' if q is None else str(q).strip()}:{side}"
                goals_by_pt[key] = goals_by_pt.get(key, 0) + 1
                if e.get("player_name") or e.get("player") or e.get("cap") is not None:
                    goals_with_author += 1
        return goals_by_pt, goals_total, goals_with_author

    t_by_pt, t_total, _ = summarize(truth_events)
    ext_events = data.get("events") or []
    e_by_pt, e_total, e_author = summarize(ext_events)

    periods = sorted(
        {k.split(":")[0] for k in set(t_by_pt) | set(e_by_pt) if k.split(":")[0]},
        key=lambda x: (0, int(x)) if x.isdigit() else (1, x),
    )
    per_period = []
    for q in periods:
        for side in ("home", "away"):
            key = f"{q}:{side}"
            per_period.append({
                "quarter": q, "team": side,
                "truth_goals": t_by_pt.get(key, 0),
                "extracted_goals": e_by_pt.get(key, 0),
            })
    return {
        "truth_goals_total": t_total,
        "extracted_goals_total": e_total,
        "extracted_goals_with_author": e_author,
        "extracted_events_total": len([e for e in ext_events if isinstance(e, dict)]),
        "truth_events_total": len(truth_events),
        "per_period_goals": per_period,
    }


def compare_roster_to_truth(case, data):
    """Confronto ADDITIVO roster estratto vs truth roster di un caso gold.

    Ritorna None se il caso non ha `truth.rosters`. Per lato confronta, per numero di
    calottina, se il COGNOME e' stato letto. Tre esiti distinti, mai collassati:
      - `surname_matched`: cognome normalizzato IDENTICO;
      - `surname_approx`: distanza di edit == 1 (una lettera sbagliata, es.
        pelliccione/pellicone) — l'OCR ha letto QUEL giocatore ma con un refuso,
        diverso dall'aver letto un altro giocatore;
      - `surname_mismatched`: distanza >= 2 (o numero assente nell'estrazione).
    Le caselle truth senza nome (ambigue o sconosciute, es. away #5 e #10 del caso
    Olympic) NON sono confrontabili e vengono contate a parte (`unresolved_in_truth`),
    mai come errore dell'OCR.
    """
    truth = case.get("truth") or {}
    rosters = truth.get("rosters")
    if not isinstance(rosters, dict):
        return None
    teams = data.get("teams") or {}
    out = {}
    for side in ("home", "away"):
        t_players = ((rosters.get(side) or {}).get("players")) or []
        e_players = ((teams.get(side) or {}).get("players")) or []
        e_by_num = {}
        for p in e_players:
            if isinstance(p, dict) and p.get("number") is not None:
                e_by_num[p["number"]] = _norm_surname(p.get("name"))
        matched = approx = mismatched = unresolved = 0
        details = []
        for tp in t_players:
            if not isinstance(tp, dict):
                continue
            num = tp.get("number")
            t_norm = _norm_surname(tp.get("name"))
            if t_norm is None:  # casella ambigua/sconosciuta in truth: fuori confronto
                unresolved += 1
                continue
            e_norm = e_by_num.get(num)
            if e_norm is not None and e_norm == t_norm:
                matched += 1
            elif e_norm is not None and _edit_distance_le1(e_norm, t_norm):
                approx += 1
                details.append({"number": num, "truth": tp.get("name"),
                                "extracted_norm": e_norm, "kind": "approx"})
            else:
                mismatched += 1
                details.append({"number": num, "truth": tp.get("name"),
                                "extracted_norm": e_norm, "kind": "mismatch"})
        out[side] = {
            "truth_size": len(t_players),
            "extracted_size": len(e_players),
            "surname_matched": matched,
            "surname_approx": approx,
            "surname_mismatched": mismatched,
            "unresolved_in_truth": unresolved,
            "mismatches": details,
        }
    return out


def aggregate_gold_repeats(per_repeat):
    """Aggrega i confronti (fields) di N estrazioni indipendenti sullo stesso caso/modello.

    L'estrazione OCR non è deterministica: due chiamate sullo stesso referto possono
    produrre valori diversi sullo stesso campo, entrambi con confidence 1.0 (caso reale:
    "BELLATOR FROSINONE" e "BELLATOR FROSINO" sullo stesso report). Una singola chiamata
    misura un campione, non "la" lettura del modello. Questa funzione rende visibile la
    varianza fra campioni invece di nasconderla dietro un'unica estrazione.

    Un campo instabile (non tutte le ripetizioni concordi) può comunque avere una
    MAGGIORANZA STRETTA (un valore con conteggio > N/2): in quel caso il verdetto è
    quello del valore maggioritario, esattamente come prima. Se invece nessun valore
    supera N/2 (pareggio, es. 2-2 su 4 chiamate), NON esiste un modo non arbitrario di
    scegliere un vincitore: assegnare il verdetto al valore comparso per primo nelle
    chiamate sarebbe un tie-break silenzioso che dipende dall'ordine di arrivo, non dal
    contenuto (bug osservato sul caso gold Bellator: "BELLATOR FRUSINO" x2 corretto,
    "BELLATOR FROSINONE" x2 sbagliato, "BELLATOR FROSINO" x1 sbagliato — nessuna
    maggioranza, eppure il tie-break per prima comparsa stampava "correct"). In questo
    caso il verdetto è 'ambiguo': esplicito, mai risolto in correct/wrong, con il
    dettaglio dei valori in pareggio e — solo come riferimento interno, mai come
    verdetto — il valore che un tie-break per prima comparsa avrebbe scelto.

    Ritorna (aggregated, summary):
      aggregated: field -> {
          truth, distinct: [(valore, conteggio), ...] per frequenza decrescente,
          stability: 'stabile' (tutte le ripetizioni concordi) o 'instabile',
          has_majority: True se un valore ha conteggio > N/2 (sempre True se stabile),
          verdict: 'correct'/'wrong'/'null' del valore maggioritario quando has_majority
              è True; 'ambiguo' quando non esiste maggioranza stretta,
          tied_values: None salvo quando verdict == 'ambiguo', nel qual caso è la lista
              dei valori in pareggio al conteggio massimo con conteggio e verdetto
              individuale ({'value', 'count', 'verdict'}) — l'informazione che serve a
              chi legge per giudicare il pareggio da sé,
          tie_break_hint: None salvo quando verdict == 'ambiguo', nel qual caso è il
              valore che un tie-break per ordine di prima comparsa fra le ripetizioni
              avrebbe scelto — SOLO riferimento interno, mai un verdetto, e va sempre
              esposto etichettato come tale (mai stampato/salvato da solo),
          stable_and_wrong: campo stabile ma sbagliato — il caso peggiore, un errore
              riproducibile che nessuna ripetizione da sola smaschererebbe,
          confidence_mean/min/max (None se il provider non ha dichiarato confidence).
      }
      summary: conteggio campi per bucket — stable_correct, stable_wrong, stable_null,
          instabile (non unanime ma con maggioranza stretta), ambiguo (non unanime e
          senza maggioranza stretta). Le categorie restano separate (mai collassate in
          un'unica percentuale): 'instabile', 'ambiguo' e 'stabile ma sbagliato' sono
          informazioni diverse con implicazioni operative diverse (varianza da
          campionare di più, esito non risolvibile senza review umana, errore
          sistematico che il campionamento non risolve).
    """
    field_keys = per_repeat[0]["fields"].keys()
    aggregated = {}
    summary = {
        "stable_correct": 0, "stable_wrong": 0, "stable_null": 0,
        "instabile": 0, "ambiguo": 0,
    }
    n = len(per_repeat)

    for field in field_keys:
        entries = [rep["fields"][field] for rep in per_repeat]
        truth_v = entries[0]["truth"]

        order = []
        counts = {}
        for e in entries:
            key = repr(e["extracted"])
            if key not in counts:
                counts[key] = [e["extracted"], 0]
                order.append(key)
            counts[key][1] += 1
        # sort() è stabile: a parità di conteggio l'ordine resta quello di prima
        # comparsa in `order` — è la base del tie_break_hint sotto, mai del verdict.
        distinct = sorted((tuple(counts[k]) for k in order), key=lambda t: -t[1])
        stable = len(distinct) == 1
        top_count = distinct[0][1]
        has_majority = top_count > n / 2

        def verdict_for(value):
            return next(e["verdict"] for e in entries if repr(e["extracted"]) == repr(value))

        confidences = [
            e["confidence"] for e in entries if isinstance(e["confidence"], (int, float))
        ]
        conf_mean = sum(confidences) / len(confidences) if confidences else None
        conf_min = min(confidences) if confidences else None
        conf_max = max(confidences) if confidences else None

        if has_majority:
            majority_value = distinct[0][0]
            field_verdict = verdict_for(majority_value)
            tied_values = None
            tie_break_hint = None
        else:
            field_verdict = "ambiguo"
            tied_values = [
                {"value": v, "count": c, "verdict": verdict_for(v)}
                for v, c in distinct if c == top_count
            ]
            tie_break_hint = tied_values[0]["value"]

        stable_and_wrong = stable and field_verdict == "wrong"

        aggregated[field] = {
            "truth": truth_v,
            "distinct": distinct,
            "stability": "stabile" if stable else "instabile",
            "has_majority": has_majority,
            "verdict": field_verdict,
            "tied_values": tied_values,
            "tie_break_hint": tie_break_hint,
            "stable_and_wrong": stable_and_wrong,
            "confidence_mean": conf_mean,
            "confidence_min": conf_min,
            "confidence_max": conf_max,
        }

        if field_verdict == "ambiguo":
            summary["ambiguo"] += 1
        elif not stable:
            summary["instabile"] += 1
        elif field_verdict == "correct":
            summary["stable_correct"] += 1
        elif field_verdict == "wrong":
            summary["stable_wrong"] += 1
        else:  # 'null': astensione dichiarata in tutte le ripetizioni
            summary["stable_null"] += 1

    return aggregated, summary


def build_gold_proposal(case, data, provider_label, model, resolved_pk, image_path,
                        image_resolved_from, preprocess, fields, inversion, run_ts,
                        prompt_version_str=PROMPT_VERSION):
    """Costruisce la voce di proposta nello schema di extractions[] dei casi gold.

    È una PROPOSTA: va salvata nella directory di output, mai dentro il caso.
    Il riversamento in extractions[] è un atto umano dopo review (decisione D1).
    """
    meta = data.get("metadata") or {}
    ext_info = data.get("match_info") or {}
    ext_scores = data.get("scores") or {}
    teams = data.get("teams") or {}
    confidence = {"overall": meta.get("confidence")}
    confidence.update(meta.get("confidence_fields") or {})
    verdict = {f: v["verdict"] for f, v in fields.items()}
    # Come nello schema esistente: ciò che non è in truth resta unverified.
    verdict.setdefault("roster", "unverified")
    verdict.setdefault("events", "unverified")
    events_comparison = compare_events_to_truth(case, data)
    roster_comparison = compare_roster_to_truth(case, data)
    return {
        "case_id": case.get("case_id"),
        "provider": meta.get("provider") or provider_label,
        "model": model,
        "db_report_pk": resolved_pk,
        "extracted_at": run_ts.date().isoformat(),
        "extracted": {
            "match_info": {k: ext_info.get(k) for k in ("home_team", "away_team", "date")},
            "scores": {
                "final_score": ext_scores.get("final_score"),
                "quarters": ext_scores.get("quarters"),
            },
            "counts": {
                "events": len(data.get("events") or []),
                "home_roster": len((teams.get("home") or {}).get("players") or []),
                "away_roster": len((teams.get("away") or {}).get("players") or []),
            },
            # Contenuto grezzo persistito additivamente: rende misurabile su dati
            # esistenti il confronto eventi/roster senza rifare la chiamata API.
            "events": data.get("events") or [],
            "rosters": {
                side: {"players": (teams.get(side) or {}).get("players") or []}
                for side in ("home", "away")
            },
        },
        "self_reported_confidence": confidence,
        "extraction_warnings": meta.get("extraction_warnings") or [],
        "verdict": verdict,
        "inversion_check": inversion,
        "comparison": fields,
        "events_comparison": events_comparison,
        "roster_comparison": roster_comparison,
        "bench_run": {
            "provider_cli": provider_label,
            "model": model,
            "prompt_version": prompt_version_str,
            "preprocessing": preprocess,
            "timestamp": run_ts.isoformat(),
            "image": image_path,
            "image_resolved_from": image_resolved_from,
        },
        "notes": [
            "Proposta generata da ocr_bench --gold: riversare in extractions[] "
            "solo dopo review umana (decisione D1)."
        ],
    }


def build_gold_proposal_repeated(case, per_repeat, provider_label, model, resolved_pk,
                                 image_path, image_resolved_from, preprocess, aggregated,
                                 summary, run_ts, repeat,
                                 prompt_version_str=PROMPT_VERSION):
    """Come build_gold_proposal, ma per N estrazioni indipendenti (--repeat).

    Contiene TUTTE le estrazioni in repeats[] (non solo l'ultima) più l'aggregato
    per campo. Schema diverso da una singola voce extractions[]: il riversamento
    resta un atto umano (decisione D1) che deve scegliere quale/quante estrazioni
    portare nel caso, non un'operazione automatica.
    """
    meta_first = (per_repeat[0]["data"].get("metadata") or {})
    repeats_out = []
    for i, entry in enumerate(per_repeat, start=1):
        data = entry["data"]
        meta = data.get("metadata") or {}
        ext_info = data.get("match_info") or {}
        ext_scores = data.get("scores") or {}
        teams = data.get("teams") or {}
        confidence = {"overall": meta.get("confidence")}
        confidence.update(meta.get("confidence_fields") or {})
        verdict = {f: v["verdict"] for f, v in entry["fields"].items()}
        verdict.setdefault("roster", "unverified")
        verdict.setdefault("events", "unverified")
        repeats_out.append({
            "run_index": i,
            "extracted": {
                "match_info": {k: ext_info.get(k) for k in ("home_team", "away_team", "date")},
                "scores": {
                    "final_score": ext_scores.get("final_score"),
                    "quarters": ext_scores.get("quarters"),
                },
                "counts": {
                    "events": len(data.get("events") or []),
                    "home_roster": len((teams.get("home") or {}).get("players") or []),
                    "away_roster": len((teams.get("away") or {}).get("players") or []),
                },
                # Contenuto grezzo persistito additivamente (vedi build_gold_proposal).
                "events": data.get("events") or [],
                "rosters": {
                    side: {"players": (teams.get(side) or {}).get("players") or []}
                    for side in ("home", "away")
                },
            },
            "self_reported_confidence": confidence,
            "extraction_warnings": meta.get("extraction_warnings") or [],
            "verdict": verdict,
            "inversion_check": entry["inversion"],
            "comparison": entry["fields"],
            "events_comparison": compare_events_to_truth(case, data),
            "roster_comparison": compare_roster_to_truth(case, data),
        })

    aggregate_out = {
        field: {
            "truth": agg["truth"],
            "distinct_values": [{"value": v, "count": c} for v, c in agg["distinct"]],
            "stability": agg["stability"],
            "has_majority": agg["has_majority"],
            "verdict": agg["verdict"],
            "tied_values": agg["tied_values"],
            "tie_break_hint": agg["tie_break_hint"],
            "stable_and_wrong": agg["stable_and_wrong"],
            "confidence_mean": agg["confidence_mean"],
            "confidence_min": agg["confidence_min"],
            "confidence_max": agg["confidence_max"],
        }
        for field, agg in aggregated.items()
    }

    return {
        "case_id": case.get("case_id"),
        "provider": meta_first.get("provider") or provider_label,
        "model": model,
        "db_report_pk": resolved_pk,
        "extracted_at": run_ts.date().isoformat(),
        "bench_run": {
            "provider_cli": provider_label,
            "model": model,
            "prompt_version": prompt_version_str,
            "preprocessing": preprocess,
            "timestamp": run_ts.isoformat(),
            "image": image_path,
            "image_resolved_from": image_resolved_from,
            "repeat": repeat,
        },
        "repeats": repeats_out,
        "aggregate": aggregate_out,
        "summary": summary,
        "notes": [
            "Proposta generata da ocr_bench --gold --repeat: misura la varianza fra N "
            "chiamate indipendenti allo stesso modello sullo stesso referto. Riversare "
            "in extractions[] solo dopo review umana (decisione D1); lo schema con "
            "repeats[]/aggregate NON è compatibile con una singola voce extractions[] "
            "e richiede una scelta umana su quale (o quante) estrazioni riversare.",
        ],
    }


def safe_model_slug(model):
    """Rende il nome del modello sicuro per l'uso in un nome di file."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def build_show_block(model, data):
    """Righe leggibili con i campi chiave estratti da un modello (per --show)."""
    info = data.get("match_info") or {}
    scores = data.get("scores") or {}
    teams = data.get("teams") or {}
    events = data.get("events") or []

    lines = [f"=== {model} ==="]
    lines.append(f"  home_team:   {info.get('home_team') or ASSENTE}")
    lines.append(f"  away_team:   {info.get('away_team') or ASSENTE}")
    lines.append(f"  final_score: {scores.get('final_score') or ASSENTE}")

    quarters = scores.get("quarters") or {}
    if quarters:
        parts = " | ".join(f"{q}: {v}" for q, v in quarters.items())
        lines.append(f"  quarti ({len(quarters)}): {parts}")
    else:
        lines.append(f"  quarti: {ASSENTE}")

    for side, label in (("home", "roster casa"), ("away", "roster ospiti")):
        players = (teams.get(side) or {}).get("players") or []
        if players:
            elenco = ", ".join(
                f"{p.get('number') if p.get('number') is not None else '?'} "
                f"{p.get('name') or ASSENTE}"
                for p in players
            )
            lines.append(f"  {label} ({len(players)}): {elenco}")
        else:
            lines.append(f"  {label}: {ASSENTE}")

    if events:
        lines.append(f"  eventi ({len(events)}):")
        for ev in events:
            desc = ev.get("type") or ASSENTE
            if ev.get("player_name"):
                desc += f" — {ev['player_name']}"
            extra = [str(x) for x in (ev.get("team"),) if x]
            if ev.get("quarter") is not None:
                extra.append(f"Q{ev['quarter']}")
            if extra:
                desc += f" ({', '.join(extra)})"
            lines.append(f"    - {desc}")
    else:
        lines.append(f"  eventi: {ASSENTE}")
    return lines


class Command(BaseCommand):
    help = (
        "Confronta modelli OCR sulla stessa immagine (read-only, chiamate reali all'LLM). "
        "Uso: ocr_bench --image <path> [--provider gemini] "
        "[--models gemini-2.5-pro,gemini-2.5-flash] [--report-id <id>] [--show] [--save-dir <path>] "
        "| ocr_bench --gold-case <case_id> [--image <path>] | ocr_bench --gold-all "
        "(confronto con la truth dei casi gold; proposte in --out-dir, mai nei casi) "
        "| aggiungi --repeat N a --gold-case/--gold-all per misurare la varianza fra "
        "N chiamate indipendenti allo stesso modello"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--image",
            default=None,
            help="Path dell'immagine del referto (obbligatorio senza --gold-case/--gold-all; "
                 "con --gold-case è l'override per i casi senza report a DB)",
        )
        parser.add_argument(
            "--gold-case",
            default=None,
            metavar="CASE_ID",
            help="Confronta l'estrazione con la truth del caso gold indicato "
                 "(nome file senza .json in docs/ocr_gold_standard/cases/)",
        )
        parser.add_argument(
            "--gold-all",
            action="store_true",
            help="Come --gold-case, per tutti i casi (glob su cases/*.json); "
                 "i casi senza immagine risolvibile vengono saltati con avviso",
        )
        parser.add_argument(
            "--cases-dir",
            default=None,
            help=f"Directory dei casi gold (default: <BASE_DIR>/{GOLD_CASES_DIR_DEFAULT})",
        )
        parser.add_argument(
            "--out-dir",
            default=None,
            help="Directory dove salvare le proposte di estrazione in modalità gold "
                 f"(default: <BASE_DIR>/{GOLD_OUT_DIR_DEFAULT}, gitignorata). "
                 "Le proposte non vengono MAI scritte nei file dei casi.",
        )
        parser.add_argument(
            "--provider",
            choices=sorted(PROVIDER_MODEL_SETTINGS.keys()),
            default="gemini",
            help="Provider da istanziare per questo run (default: gemini).",
        )
        parser.add_argument(
            "--models",
            default=None,
            help="Lista di modelli separati da virgola "
                 "(default: modello del provider da settings, es. GEMINI_MODEL)",
        )
        parser.add_argument(
            "--report-id",
            type=int,
            default=None,
            help="Se il report ha normalized_data validati, calcola accuracy exact-match per campo",
        )
        parser.add_argument(
            "--show",
            action="store_true",
            help="Stampa un blocco leggibile per modello con i campi chiave estratti",
        )
        parser.add_argument(
            "--save-dir",
            default=None,
            help="Salva il JSON completo estratto da ciascun modello in <path>/ocr_bench_<model>_<timestamp>.json",
        )
        parser.add_argument(
            "--dump-sent-image",
            default=None,
            metavar="DIR",
            help=(
                "Salva in DIR l'immagine esattamente inviata al modello come "
                "ocr_bench_sent_<model>_<timestamp>.<ext> (crea DIR se manca)"
            ),
        )
        parser.add_argument(
            "--no-preprocess",
            action="store_true",
            help="Bypassa ImagePreprocessor e invia l'immagine grezza (no auto-rotate, no downscale)",
        )
        parser.add_argument(
            "--prompt-version",
            choices=sorted(OCR_ALL_PROMPTS.keys()),
            default="v2",
            help=(
                "Versione del prompt di sistema da usare per l'estrazione "
                "(default: v2, il prompt di produzione). La versione e l'hash "
                "del prompt selezionato finiscono nei metadati di run: due run "
                "sono confrontabili solo a parità di questa stringa."
            ),
        )
        parser.add_argument(
            "--thinking-level",
            default=None,
            metavar="LEVEL",
            help=(
                "Livello di ragionamento per i modelli Gemini 3.x "
                "('minimal' azzera i thought token, 'low', 'high'). "
                "Default None: nessun ThinkingConfig, comportamento di produzione "
                "invariato. Seam per-chiamata, non tocca settings."
            ),
        )
        parser.add_argument(
            "--thinking-budget",
            type=int,
            default=None,
            metavar="TOKENS",
            help=(
                "Budget di thinking token per i modelli Gemini 2.5 (alternativa a "
                "--thinking-level, che ha precedenza se entrambi valorizzati). "
                "Default None: comportamento di produzione invariato."
            ),
        )
        parser.add_argument(
            "--repeat",
            type=int,
            default=1,
            metavar="N",
            help=(
                "Esegue N estrazioni indipendenti per caso/modello, per misurare la "
                "varianza fra chiamate ripetute allo stesso modello (l'estrazione non "
                "è deterministica). Richiede --gold-case o --gold-all. Con N=1 "
                "(default) il comportamento è invariato."
            ),
        )
        parser.add_argument(
            "--second-pass",
            action="store_true",
            help=(
                "Doppia estrazione per zona (Macro 8, giro 22/07): esegue il SECONDO "
                "passaggio (prompt 'zone', solo finale/parziali/data) e lo confronta col "
                "PRIMO passaggio riletto da --first-pass-dir, applicando la regola di "
                "divergenza (discordanza su finale/parziali/data -> NEEDS_REVIEW). "
                "Default OFF. Richiede modalità gold e --first-pass-dir. Non attiva nulla "
                "in produzione: è una misura selezionabile dal bench."
            ),
        )
        parser.add_argument(
            "--first-pass-dir",
            default=None,
            metavar="DIR",
            help=(
                "Directory delle proposte del PRIMO passaggio (schema --repeat, es. i "
                "risultati V3) da riusare come prima lettura in --second-pass, invece di "
                "rifarle. Per ogni caso/modello si cerca il file "
                "'<case_id>__<model>_repeat*.json' e si accoppiano le N ripetizioni "
                "indice per indice con quelle del secondo passaggio."
            ),
        )

    def handle(self, *args, **options):
        image_opt = options["image"]
        gold_case_id = options["gold_case"]
        gold_all = options["gold_all"]
        gold_mode = bool(gold_case_id or gold_all)
        repeat = options["repeat"]

        if gold_case_id and gold_all:
            raise CommandError("--gold-case e --gold-all sono alternativi.")
        if gold_all and image_opt:
            raise CommandError(
                "--image non è combinabile con --gold-all: usalo con --gold-case "
                "per i casi senza report a DB."
            )
        if not gold_mode and not image_opt:
            raise CommandError("Serve --image, oppure --gold-case/--gold-all.")
        if gold_mode and options["report_id"] is not None:
            raise CommandError(
                "--report-id non è combinabile con la modalità gold: "
                "la baseline dei casi gold è la loro truth."
            )
        if image_opt and not os.path.isfile(image_opt):
            raise CommandError(f"Immagine non trovata: {image_opt}")
        if repeat < 1:
            raise CommandError("--repeat deve essere >= 1.")
        if repeat > 1 and not gold_mode:
            raise CommandError("--repeat > 1 richiede --gold-case o --gold-all.")

        second_pass = options["second_pass"]
        first_pass_dir = options["first_pass_dir"]
        if second_pass:
            if not gold_mode:
                raise CommandError("--second-pass richiede --gold-case o --gold-all.")
            if not first_pass_dir:
                raise CommandError(
                    "--second-pass richiede --first-pass-dir (la directory delle "
                    "proposte del primo passaggio da riusare)."
                )
            if not os.path.isdir(first_pass_dir):
                raise CommandError(f"--first-pass-dir non trovata: {first_pass_dir}")
            if options["prompt_version"] not in ("v2", "zone"):
                raise CommandError(
                    "--second-pass usa sempre il prompt 'zone' per il secondo "
                    f"passaggio: --prompt-version {options['prompt_version']!r} è "
                    "incompatibile (ometti --prompt-version o passa 'zone')."
                )
            # Il secondo passaggio è, per definizione, la lettura 'zone'.
            options["prompt_version"] = "zone"
        elif first_pass_dir:
            raise CommandError("--first-pass-dir ha senso solo con --second-pass.")

        provider_name = options["provider"]
        model_setting, model_fallback = PROVIDER_MODEL_SETTINGS[provider_name]
        # Risoluzione a runtime: rispetta gli eventuali patch dei test.
        provider_cls = {
            "gemini": GeminiVisionProvider,
        }[provider_name]

        if options["models"]:
            models = [m.strip() for m in options["models"].split(",") if m.strip()]
        else:
            models = [getattr(settings, model_setting, model_fallback)]
        if not models:
            raise CommandError("Nessun modello specificato.")

        validated_fields = None
        if options["report_id"] is not None:
            try:
                report = MatchReport.objects.get(pk=options["report_id"])
            except MatchReport.DoesNotExist:
                raise CommandError(f"MatchReport {options['report_id']} non trovato.")
            if report.normalized_data:
                validated_fields = extract_comparable_fields(report.normalized_data)
                self.stdout.write(
                    f"Baseline validata: report {report.pk} (normalized_data post-review)"
                )
            else:
                self.stdout.write(self.style.WARNING(
                    f"Report {report.pk} senza normalized_data: accuracy non calcolabile."
                ))

        provider = provider_cls()
        provider_label = provider_name

        preprocess = not options["no_preprocess"]
        dump_dir = options["dump_sent_image"]
        if dump_dir:
            os.makedirs(dump_dir, exist_ok=True)

        prompt_version = options["prompt_version"]
        prompt_version_str = prompt_version_string(prompt_version)
        thinking_level = options["thinking_level"]
        thinking_budget = options["thinking_budget"]
        if thinking_level or thinking_budget is not None:
            self.stdout.write(
                f"  thinking: level={thinking_level!r} budget={thinking_budget!r}"
            )

        if not gold_mode:
            results = self._run_models(
                provider, provider_name, models, image_opt, preprocess, dump_dir,
                prompt_version=prompt_version,
                thinking_level=thinking_level, thinking_budget=thinking_budget,
            )
            self._print_show_and_save(results, options)
            if validated_fields is not None and results:
                self.stdout.write("\nAccuracy exact-match vs dati validati:")
                for model, data in results.items():
                    extracted = extract_comparable_fields(data)
                    hits = [f for f in ACCURACY_FIELDS if extracted[f] == validated_fields[f]]
                    misses = [f for f in ACCURACY_FIELDS if f not in hits]
                    self.stdout.write(
                        f"  {model:<20} {len(hits)}/{len(ACCURACY_FIELDS)}"
                        + (f"  (mismatch: {', '.join(misses)})" if misses else "")
                    )
                    for f in misses:
                        self.stdout.write(
                            f"    - {f}: estratto={extracted[f]!r} vs validato={validated_fields[f]!r}"
                        )
            return

        # --- modalità gold: confronto con la truth verificata da umano ---
        cases_dir = options["cases_dir"] or os.path.join(
            settings.BASE_DIR, GOLD_CASES_DIR_DEFAULT
        )
        if gold_case_id:
            case_paths = [os.path.join(cases_dir, f"{gold_case_id}.json")]
            if not os.path.isfile(case_paths[0]):
                available = sorted(
                    os.path.splitext(os.path.basename(p))[0]
                    for p in glob.glob(os.path.join(cases_dir, "*.json"))
                )
                raise CommandError(
                    f"Caso gold '{gold_case_id}' non trovato in {cases_dir}. "
                    f"Disponibili: {', '.join(available) or 'nessuno'}"
                )
        else:
            case_paths = sorted(glob.glob(os.path.join(cases_dir, "*.json")))
            if not case_paths:
                raise CommandError(f"Nessun caso gold in {cases_dir}.")

        out_dir = options["out_dir"] or os.path.join(settings.BASE_DIR, GOLD_OUT_DIR_DEFAULT)
        os.makedirs(out_dir, exist_ok=True)

        run_ts = timezone.localtime()
        self.stdout.write(f"Run gold: provider={provider_name} modelli={', '.join(models)}")
        self.stdout.write(f"  prompt: {prompt_version_str}")
        self.stdout.write(f"  preprocessing: {'on' if preprocess else 'off'}")
        self.stdout.write(f"  timestamp: {run_ts.isoformat()}")
        self.stdout.write(f"  output proposte: {out_dir}")

        skipped = []
        for case_path in case_paths:
            case = self._load_gold_case(case_path, strict=bool(gold_case_id))
            if case is None:
                skipped.append((os.path.basename(case_path), "JSON non leggibile"))
                continue
            case_id = case.get("case_id") or os.path.splitext(os.path.basename(case_path))[0]

            if gold_case_id and image_opt:
                image_path, resolved_pk, resolved_from = image_opt, None, "--image"
            else:
                image_path, resolved_pk, err = self._resolve_case_image(case)
                resolved_from = f"db_report_pk={resolved_pk}" if resolved_pk else None
                if image_path is None:
                    if gold_case_id:
                        raise CommandError(
                            f"Caso '{case_id}': {err} Usa --image per fornire il file."
                        )
                    self.stdout.write(self.style.WARNING(f"\nCaso '{case_id}' SALTATO: {err}"))
                    skipped.append((case_id, err))
                    continue

            self.stdout.write(f"\n=== Caso gold: {case_id} ===")

            if second_pass:
                self._process_gold_case_second_pass(
                    case, case_id, provider, provider_name, provider_label, models,
                    image_path, resolved_pk, resolved_from, preprocess, dump_dir,
                    out_dir, run_ts, repeat, options, first_pass_dir,
                    prompt_version=prompt_version,
                    prompt_version_str=prompt_version_str,
                )
                continue

            if repeat > 1:
                self._process_gold_case_repeated(
                    case, case_id, provider, provider_name, provider_label, models,
                    image_path, resolved_pk, resolved_from, preprocess, dump_dir,
                    out_dir, run_ts, repeat, options,
                    prompt_version=prompt_version,
                    prompt_version_str=prompt_version_str,
                )
                continue

            results = self._run_models(
                provider, provider_name, models, image_path, preprocess, dump_dir,
                prompt_version=prompt_version,
                thinking_level=thinking_level, thinking_budget=thinking_budget,
            )
            self._print_show_and_save(results, options, case_id=case_id)

            for model, data in results.items():
                fields, inversion = compare_extraction_to_truth(case, data)
                self._print_gold_comparison(case_id, model, fields, inversion)
                proposal = build_gold_proposal(
                    case, data, provider_label, model, resolved_pk, image_path,
                    resolved_from, preprocess, fields, inversion, run_ts,
                    prompt_version_str=prompt_version_str,
                )
                fname = (
                    f"{case_id}__{safe_model_slug(model)}_"
                    f"{run_ts.strftime('%Y%m%d_%H%M%S')}.json"
                )
                path = os.path.join(out_dir, fname)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(proposal, f, indent=2, ensure_ascii=False)
                self.stdout.write(
                    f"Proposta salvata: {path} "
                    "(riversamento in extractions[] manuale, dopo review umana)"
                )

        if skipped:
            self.stdout.write(self.style.WARNING(
                "\nCasi saltati: " + "; ".join(f"{cid} ({why})" for cid, why in skipped)
            ))

    def _load_gold_case(self, path, strict):
        """Carica un caso gold; con strict=False (gold-all) salta i file illeggibili."""
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError) as e:
            if strict:
                raise CommandError(f"Caso gold non leggibile: {path}: {e}")
            self.stdout.write(self.style.WARNING(f"Caso non leggibile, saltato: {path}: {e}"))
            return None

    def _resolve_case_image(self, case):
        """Risolve l'immagine del caso dai db_report_pk (top-level, poi extractions[]).

        Ritorna (path, report_pk, None) oppure (None, None, motivo).
        Sola lettura sul DB.
        """
        candidates = []
        top_pk = case.get("db_report_pk")
        if top_pk:
            candidates.append(top_pk)
        for entry in case.get("extractions") or []:
            pk = entry.get("db_report_pk")
            if pk and pk not in candidates:
                candidates.append(pk)
        if not candidates:
            return None, None, (
                "nessun db_report_pk nel caso (né top-level né in extractions[])."
            )
        tried = []
        for pk in candidates:
            report = MatchReport.objects.filter(pk=pk).first()
            if report is None:
                tried.append(f"report {pk}: non a DB")
                continue
            if not (report.file and report.file.name):
                tried.append(f"report {pk}: senza file")
                continue
            path = report.file.path
            if not os.path.isfile(path):
                tried.append(f"report {pk}: file mancante su disco ({report.file.name})")
                continue
            return path, pk, None
        return None, None, "nessuna immagine risolvibile — " + "; ".join(tried) + "."

    def _run_models(self, provider, provider_name, models, image_path, preprocess, dump_dir,
                    prompt_version="v2", thinking_level=None, thinking_budget=None):
        """Esegue l'estrazione per ogni modello e stampa la tabella. Ritorna {model: data}."""
        # Stub minimale: extract_data usa solo .id (logging) e .file.path
        bench_report = SimpleNamespace(
            id=f"bench:{os.path.basename(image_path)}",
            file=SimpleNamespace(path=image_path),
        )

        self.stdout.write(f"\nImmagine: {image_path}")
        self.stdout.write(f"Provider: {provider_name}")
        self.stdout.write(f"Modelli: {', '.join(models)}")
        if not preprocess:
            self.stdout.write("Preprocessing: BYPASSATO (--no-preprocess)")
        self.stdout.write("")
        header = (
            f"{'modello':<20} {'confidence':>10} {'latenza':>9} "
            f"{'tok_in':>8} {'tok_out':>8} {'tok_thk':>8}"
        )
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        results = {}
        dumped_paths = []
        for model in models:
            # Solo kwargs non-default: il contratto della chiamata senza nuovi
            # flag resta identico a prima.
            extract_kwargs = {"model": model}
            if not preprocess:
                extract_kwargs["preprocess"] = False
            if prompt_version != "v2":
                extract_kwargs["prompt_version"] = prompt_version
            if thinking_level is not None:
                extract_kwargs["thinking_level"] = thinking_level
            if thinking_budget is not None:
                extract_kwargs["thinking_budget"] = thinking_budget
            if dump_dir:
                ts = timezone.localtime().strftime("%Y%m%d_%H%M%S")

                def dump_sent(sent_path, _model=model, _ts=ts):
                    ext = os.path.splitext(sent_path)[1] or ".jpg"
                    dest = os.path.join(
                        dump_dir, f"ocr_bench_sent_{safe_model_slug(_model)}_{_ts}{ext}"
                    )
                    shutil.copyfile(sent_path, dest)
                    dumped_paths.append(dest)

                extract_kwargs["sent_image_callback"] = dump_sent

            start = time.monotonic()
            try:
                data, _raw = provider.extract_data(bench_report, **extract_kwargs)
            except Exception as e:
                elapsed = time.monotonic() - start
                self.stdout.write(self.style.ERROR(
                    f"{model:<20} {'ERRORE':>10} {elapsed:>8.1f}s  {e}"
                ))
                continue
            elapsed = time.monotonic() - start
            meta = data.get("metadata") or {}
            confidence = meta.get("confidence")
            usage = meta.get("token_usage") or {}
            conf_str = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "N/A"
            tok_in = usage.get("prompt_tokens")
            tok_out = usage.get("completion_tokens")
            tok_thk = usage.get("thoughts_tokens")
            self.stdout.write(
                f"{model:<20} {conf_str:>10} {elapsed:>8.1f}s "
                f"{tok_in if tok_in is not None else 'N/A':>8} "
                f"{tok_out if tok_out is not None else 'N/A':>8} "
                f"{tok_thk if tok_thk is not None else 'N/A':>8}"
            )
            results[model] = data

        if dumped_paths:
            self.stdout.write("")
            for path in dumped_paths:
                self.stdout.write(f"Immagine inviata salvata: {path}")

        return results

    def _print_show_and_save(self, results, options, case_id=None):
        """Blocchi --show e --save-dir, comuni a modalità classica e gold."""
        if options["show"] and results:
            for model, data in results.items():
                self.stdout.write("")
                for line in build_show_block(model, data):
                    self.stdout.write(line)

        if options["save_dir"] and results:
            save_dir = options["save_dir"]
            os.makedirs(save_dir, exist_ok=True)
            ts = timezone.localtime().strftime("%Y%m%d_%H%M%S")
            # In modalità gold il case_id entra nel nome: evita collisioni
            # tra casi diversi estratti nello stesso secondo.
            prefix = f"ocr_bench_{case_id}__" if case_id else "ocr_bench_"
            self.stdout.write("")
            for model, data in results.items():
                path = os.path.join(
                    save_dir, f"{prefix}{safe_model_slug(model)}_{ts}.json"
                )
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self.stdout.write(f"Salvato: {path}")

    def _print_gold_comparison(self, case_id, model, fields, inversion):
        """Tabella per-campo del confronto con la truth + check di inversione.

        Le colonne 'truth' ed 'estratto' portano testo libero letto dall'OCR
        (nomi squadra) e non hanno una lunghezza massima nota: la larghezza si
        calcola sul contenuto più lungo di questo run, mai su una costante
        fissa, altrimenti un valore più lungo della colonna sbanda
        l'allineamento delle colonne successive e può leggersi come troncato
        (successo con "BELLATOR FROSINONE" contro una colonna larga 18).
        """
        self.stdout.write(f"\n--- Confronto con truth: {case_id} — {model} ---")
        headers = ("campo", "truth", "estratto", "esito", "confidence")
        rows = []
        for field, row in fields.items():
            conf = row["confidence"]
            conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "N/A"
            extracted = "null" if row["extracted"] is None else str(row["extracted"])
            rows.append((field, str(row["truth"]), extracted, row["verdict"], conf_str))
        widths = [
            max(len(headers[i]), max((len(r[i]) for r in rows), default=0))
            for i in range(len(headers))
        ]

        def fmt_row(cells):
            return "  ".join(
                cell.ljust(widths[i]) if i == 0 else cell.rjust(widths[i])
                for i, cell in enumerate(cells)
            )

        header_line = fmt_row(headers)
        self.stdout.write(header_line)
        self.stdout.write("-" * len(header_line))
        for r in rows:
            self.stdout.write(fmt_row(r))

        def fmt(v):
            return {True: "SÌ", False: "no", None: "n/c"}[v]

        q_parts = " ".join(f"Q{k}={fmt(v)}" for k, v in inversion["quarters"].items())
        self.stdout.write(
            "Inversione casa/trasferta: "
            f"finale={fmt(inversion['final_score'])} {q_parts} "
            f"nomi={fmt(inversion['team_names'])}"
            + ("  ← INVERSIONE RILEVATA" if inversion["any"] else "")
        )
        counts = {"correct": 0, "wrong": 0, "null": 0}
        for row in fields.values():
            counts[row["verdict"]] += 1
        self.stdout.write(
            f"Esito campi: {counts['correct']} correct, {counts['wrong']} wrong, "
            f"{counts['null']} null su {len(fields)} confrontati "
            "(null = astensione dichiarata, conteggiata a parte)"
        )

    def _process_gold_case_repeated(self, case, case_id, provider, provider_name,
                                     provider_label, models, image_path, resolved_pk,
                                     resolved_from, preprocess, dump_dir, out_dir, run_ts,
                                     repeat, options, prompt_version="v2",
                                     prompt_version_str=PROMPT_VERSION):
        """--repeat N: esegue N estrazioni indipendenti per modello e ne misura la varianza.

        Ogni ripetizione è una chiamata reale indipendente (stesso modello, stessa
        immagine): l'estrazione non è deterministica, quindi N chiamate possono
        produrre N valori diversi sullo stesso campo. Aggrega e stampa la varianza
        invece di trattare una singola chiamata come "la" lettura del modello.
        """
        data_lists = {model: [] for model in models}
        thinking_level = options.get("thinking_level")
        thinking_budget = options.get("thinking_budget")
        for i in range(1, repeat + 1):
            self.stdout.write(f"\n-- Ripetizione {i}/{repeat} --")
            results = self._run_models(
                provider, provider_name, models, image_path, preprocess, dump_dir,
                prompt_version=prompt_version,
                thinking_level=thinking_level, thinking_budget=thinking_budget,
            )
            self._print_show_and_save(results, options, case_id=f"{case_id}__run{i}")
            for model, data in results.items():
                data_lists[model].append(data)

        for model, data_list in data_lists.items():
            if not data_list:
                self.stdout.write(self.style.WARNING(
                    f"\nModello '{model}': nessuna estrazione riuscita su {repeat} "
                    "tentativi, saltato."
                ))
                continue

            per_repeat = []
            for data in data_list:
                fields, inversion = compare_extraction_to_truth(case, data)
                per_repeat.append({"data": data, "fields": fields, "inversion": inversion})

            aggregated, summary = aggregate_gold_repeats(per_repeat)
            self._print_gold_repeat_comparison(
                case_id, model, aggregated, summary, len(data_list)
            )

            proposal = build_gold_proposal_repeated(
                case, per_repeat, provider_label, model, resolved_pk, image_path,
                resolved_from, preprocess, aggregated, summary, run_ts, len(data_list),
                prompt_version_str=prompt_version_str,
            )
            fname = (
                f"{case_id}__{safe_model_slug(model)}_repeat{len(data_list)}_"
                f"{run_ts.strftime('%Y%m%d_%H%M%S')}.json"
            )
            path = os.path.join(out_dir, fname)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(proposal, f, indent=2, ensure_ascii=False)
            self.stdout.write(
                f"Proposta salvata: {path} "
                "(riversamento in extractions[] manuale, dopo review umana)"
            )

    def _print_gold_repeat_comparison(self, case_id, model, aggregated, summary, repeat):
        """Tabella per-campo aggregata su N ripetizioni: valori distinti, stabilità, confidence."""
        self.stdout.write(
            f"\n--- Confronto con truth (--repeat {repeat}): {case_id} — {model} ---"
        )
        headers = ("campo", "truth", f"valori (n={repeat})", "stabilita'", "esito", "confidence")
        rows = []
        for field, agg in aggregated.items():
            values_str = ", ".join(
                f"{'null' if v is None else v} x{c}" for v, c in agg["distinct"]
            )
            stability = agg["stability"]
            if agg["stable_and_wrong"]:
                stability += " — STABILE MA SBAGLIATO"
            elif agg["verdict"] == "ambiguo":
                stability += " — SENZA MAGGIORANZA"
            if agg["confidence_mean"] is None:
                conf_str = "N/A"
            elif agg["confidence_min"] == agg["confidence_max"]:
                conf_str = f"{agg['confidence_mean']:.2f}"
            else:
                conf_str = (
                    f"{agg['confidence_mean']:.2f} "
                    f"[{agg['confidence_min']:.2f}-{agg['confidence_max']:.2f}]"
                )
            rows.append((
                field, str(agg["truth"]), values_str, stability, agg["verdict"], conf_str
            ))
        widths = [
            max(len(headers[i]), max((len(r[i]) for r in rows), default=0))
            for i in range(len(headers))
        ]

        def fmt_row(cells):
            return "  ".join(
                cell.ljust(widths[i]) if i == 0 else cell.rjust(widths[i])
                for i, cell in enumerate(cells)
            )

        header_line = fmt_row(headers)
        self.stdout.write(header_line)
        self.stdout.write("-" * len(header_line))
        for r in rows:
            self.stdout.write(fmt_row(r))

        total = sum(summary.values())
        self.stdout.write(
            f"Riepilogo campi: {summary['stable_correct']} stabili-corretti, "
            f"{summary['stable_wrong']} stabili-sbagliati, "
            f"{summary['instabile']} instabili-con-maggioranza, "
            f"{summary['ambiguo']} ambigui-senza-maggioranza, "
            f"{summary['stable_null']} stabili-null (astensione consistente) "
            f"su {total} campi confrontati"
        )
        if summary["stable_wrong"]:
            self.stdout.write(self.style.WARNING(
                f"  ← {summary['stable_wrong']} campo/i STABILE MA SBAGLIATO: errore "
                "riproducibile, nessuna ripetizione lo smaschererebbe."
            ))
        if summary["ambiguo"]:
            self.stdout.write(self.style.WARNING(
                f"  ← {summary['ambiguo']} campo/i AMBIGUO/I (pareggio, nessun valore "
                f"supera {repeat}/2 chiamate): esito NON risolvibile automaticamente, "
                "richiede review umana. Dettaglio pareggi:"
            ))
            for field, agg in aggregated.items():
                if agg["verdict"] != "ambiguo":
                    continue
                parts = ", ".join(
                    f"{'null' if tv['value'] is None else tv['value']!r} "
                    f"x{tv['count']} ({tv['verdict']})"
                    for tv in agg["tied_values"]
                )
                self.stdout.write(self.style.WARNING(
                    f"      {field}: pareggio fra {parts} — tie-break per prima "
                    f"comparsa (SOLO riferimento interno, MAI un verdetto): "
                    f"{agg['tie_break_hint']!r}"
                ))

    # --- doppia estrazione per zona (--second-pass) --------------------------

    def _load_first_pass_repeats(self, first_pass_dir, case_id, model):
        """Carica le estrazioni del primo passaggio per (case_id, model) da first_pass_dir.

        Cerca '<case_id>__<model_slug>_repeat*.json' (schema di
        build_gold_proposal_repeated). Ritorna (repeats_extracted, source_file,
        first_prompt_version); (None, None, None) se non trovato.
        repeats_extracted è la lista dei dict 'extracted' (match_info + scores),
        cioè le singole letture del primo passaggio, nell'ordine delle ripetizioni.
        """
        pattern = os.path.join(
            first_pass_dir, f"{case_id}__{safe_model_slug(model)}_repeat*.json"
        )
        found = sorted(glob.glob(pattern))
        if not found:
            return None, None, None
        source = found[-1]  # se più d'uno, il più recente (timestamp nel nome)
        with open(source, encoding="utf-8") as f:
            proposal = json.load(f)
        extracted = [r.get("extracted") or {} for r in (proposal.get("repeats") or [])]
        first_prompt = (proposal.get("bench_run") or {}).get("prompt_version")
        return extracted, source, first_prompt

    @staticmethod
    def _summarize_divergence(per_repeat):
        """Riepiloga le divergenze su N ripetizioni accoppiate."""
        by_zone = {z: 0 for z in ZONES}
        diverging = 0
        for entry in per_repeat:
            div = entry["divergence"]
            if div["diverges"]:
                diverging += 1
            for z in div["diverging_zones"]:
                by_zone[z] += 1
        return {
            "repeats_compared": len(per_repeat),
            "repeats_diverging": diverging,
            "by_zone": by_zone,
            "needs_review_any": diverging > 0,
        }

    def _process_gold_case_second_pass(self, case, case_id, provider, provider_name,
                                       provider_label, models, image_path, resolved_pk,
                                       resolved_from, preprocess, dump_dir, out_dir,
                                       run_ts, repeat, options, first_pass_dir,
                                       prompt_version="zone", prompt_version_str=None):
        """--second-pass: esegue il secondo passaggio (zone) e lo confronta col primo (riusato).

        Per ogni modello esegue `repeat` estrazioni zone (chiamate reali indipendenti),
        carica le estrazioni del primo passaggio da --first-pass-dir per lo stesso
        caso/modello e accoppia le ripetizioni indice per indice, applicando la regola
        di divergenza (compare_passes). Le due letture sono indipendenti: il secondo
        passaggio NON riceve il risultato del primo (nessun confronto guidato). Salva una
        proposta per caso/modello con la divergenza per ripetizione e il riepilogo.
        """
        data_lists = {model: [] for model in models}
        sp_thinking_level = options.get("thinking_level")
        sp_thinking_budget = options.get("thinking_budget")
        for i in range(1, repeat + 1):
            self.stdout.write(f"\n-- Secondo passaggio (zone) {i}/{repeat} --")
            results = self._run_models(
                provider, provider_name, models, image_path, preprocess, dump_dir,
                prompt_version=prompt_version,
                thinking_level=sp_thinking_level, thinking_budget=sp_thinking_budget,
            )
            self._print_show_and_save(results, options, case_id=f"{case_id}__zone_run{i}")
            for model, data in results.items():
                data_lists[model].append(data)

        for model, second_list in data_lists.items():
            if not second_list:
                self.stdout.write(self.style.WARNING(
                    f"\nModello '{model}': nessuna estrazione zone riuscita su {repeat} "
                    "tentativi, saltato."
                ))
                continue

            first_list, first_src, first_prompt = self._load_first_pass_repeats(
                first_pass_dir, case_id, model
            )
            if not first_list:
                self.stdout.write(self.style.WARNING(
                    f"\nModello '{model}': nessuna proposta di primo passaggio in "
                    f"{first_pass_dir} per '{case_id}' (attesa "
                    f"'{case_id}__{safe_model_slug(model)}_repeat*.json'), confronto saltato."
                ))
                continue

            k = min(len(first_list), len(second_list))
            if len(first_list) != len(second_list):
                self.stdout.write(self.style.WARNING(
                    f"Modello '{model}': primo passaggio {len(first_list)} ripetizioni, "
                    f"secondo {len(second_list)}: accoppio le prime {k}."
                ))

            per_repeat = [
                {
                    "run_index": i + 1,
                    "first": first_list[i],
                    "second": second_list[i],
                    "divergence": compare_passes(first_list[i], second_list[i]),
                }
                for i in range(k)
            ]
            summary = self._summarize_divergence(per_repeat)
            self._print_second_pass_comparison(case_id, model, per_repeat, summary, k)

            proposal = self._build_second_pass_proposal(
                case_id, model, provider_label, resolved_pk, image_path, resolved_from,
                preprocess, per_repeat, summary, run_ts, k, first_src, first_prompt,
                prompt_version_str,
            )
            fname = (
                f"{case_id}__{safe_model_slug(model)}_secondpass{k}_"
                f"{run_ts.strftime('%Y%m%d_%H%M%S')}.json"
            )
            path = os.path.join(out_dir, fname)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(proposal, f, indent=2, ensure_ascii=False)
            self.stdout.write(
                f"Proposta salvata: {path} "
                "(regola di divergenza NON attiva in produzione: misura)"
            )

    def _build_second_pass_proposal(self, case_id, model, provider_label, resolved_pk,
                                    image_path, resolved_from, preprocess, per_repeat,
                                    summary, run_ts, k, first_src, first_prompt,
                                    prompt_version_str):
        """Proposta della doppia estrazione: divergenza per ripetizione + riepilogo."""
        return {
            "case_id": case_id,
            "mode": "second_pass_divergence",
            "provider": provider_label,
            "model": model,
            "db_report_pk": resolved_pk,
            "extracted_at": run_ts.date().isoformat(),
            "first_pass": {
                "source_file": os.path.basename(first_src) if first_src else None,
                "prompt_version": first_prompt,
            },
            "second_pass": {"prompt_version": prompt_version_str},
            "bench_run": {
                "provider_cli": provider_label,
                "model": model,
                "preprocessing": preprocess,
                "timestamp": run_ts.isoformat(),
                "image": image_path,
                "image_resolved_from": resolved_from,
                "repeat": k,
            },
            "repeats": [
                {
                    "run_index": e["run_index"],
                    "first": {
                        "final_score": (e["first"].get("scores") or {}).get("final_score"),
                        "quarters": (e["first"].get("scores") or {}).get("quarters"),
                        "date": (e["first"].get("match_info") or {}).get("date"),
                    },
                    "second": {
                        "final_score": (e["second"].get("scores") or {}).get("final_score"),
                        "quarters": (e["second"].get("scores") or {}).get("quarters"),
                        "date": (e["second"].get("match_info") or {}).get("date"),
                        "date_digits": (e["second"].get("match_info") or {}).get("date_digits"),
                        "extraction_warnings": (
                            (e["second"].get("metadata") or {}).get("extraction_warnings") or []
                        ),
                    },
                    "divergence": e["divergence"],
                }
                for e in per_repeat
            ],
            "summary": summary,
            "notes": [
                "Proposta generata da ocr_bench --second-pass: misura la regola di "
                "divergenza fra primo passaggio (riusato da --first-pass-dir) e secondo "
                "passaggio (zone). Le ripetizioni sono accoppiate indice per indice: due "
                "serie di campioni indipendenti, l'accoppiamento è arbitrario ma "
                "equivalente a qualunque altro. La regola (divergenza -> NEEDS_REVIEW) "
                "NON è attiva in produzione in questo giro: è solo misurata.",
            ],
        }

    def _print_second_pass_comparison(self, case_id, model, per_repeat, summary, k):
        """Tabella per-ripetizione della doppia estrazione: stato di ogni zona + dettaglio."""
        self.stdout.write(
            f"\n--- Doppia estrazione (--second-pass, {k} ripetizioni): {case_id} — {model} ---"
        )
        headers = ("rip.", "finale", "parziali", "data", "esito")
        rows = []
        for e in per_repeat:
            z = e["divergence"]["zones"]
            rows.append((
                str(e["run_index"]),
                z["final_score"]["status"],
                z["quarters"]["status"],
                z["date"]["status"],
                "DIVERGE" if e["divergence"]["diverges"] else "concorde",
            ))
        widths = [
            max(len(headers[i]), max((len(r[i]) for r in rows), default=0))
            for i in range(len(headers))
        ]

        def fmt_row(cells):
            return "  ".join(
                cell.ljust(widths[i]) if i == 0 else cell.rjust(widths[i])
                for i, cell in enumerate(cells)
            )

        header_line = fmt_row(headers)
        self.stdout.write(header_line)
        self.stdout.write("-" * len(header_line))
        for r in rows:
            self.stdout.write(fmt_row(r))

        detail_lines = []
        for e in per_repeat:
            div = e["divergence"]
            if not div["diverges"]:
                continue
            for zone in div["diverging_zones"]:
                zd = div["zones"][zone]
                if zone == "quarters":
                    cells = ", ".join(
                        f"{name}={c['first']}|{c['second']}"
                        for name, c in zd["cells"].items() if c["status"] == "diverge"
                    )
                    detail_lines.append(f"  rip {e['run_index']} — parziali: {cells}")
                else:
                    detail_lines.append(
                        f"  rip {e['run_index']} — {zone}: "
                        f"primo {zd['first']!r} vs secondo {zd['second']!r}"
                    )
        if detail_lines:
            self.stdout.write("Dettaglio divergenze (primo|secondo):")
            for line in detail_lines:
                self.stdout.write(line)

        by_zone = summary["by_zone"]
        self.stdout.write(
            f"Riepilogo: {summary['repeats_diverging']}/{summary['repeats_compared']} "
            f"ripetizioni divergenti; per zona final_score={by_zone['final_score']}, "
            f"quarters={by_zone['quarters']}, date={by_zone['date']}; "
            f"NEEDS_REVIEW su {summary['repeats_diverging']}/{summary['repeats_compared']}."
        )
