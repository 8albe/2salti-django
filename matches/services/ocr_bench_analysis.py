"""
Analisi versionata delle proposte del bench OCR (Macro 8, giro §8.20).

La lezione di §8.19 è che una misura senza strumento versionato non è
ripetibile: le proposte finivano in scratchpad e le metriche venivano
ricostruite a mano. Questo modulo mette a repo la logica di analisi che
consuma i file di proposta prodotti da `ocr_bench --repeat N` (schema
`build_gold_proposal_repeated`: `repeats[]` + `aggregate` + `summary`), senza
mai fare chiamate reali. Due famiglie di funzioni:

  1. Assi §8.19 per singolo braccio (axis_a, known_stable_errors,
     events_referto8): rileggono i bucket già calcolati dall'aggregato del
     bench, così un braccio (Pro o Flash) si riassume in modo riproducibile.

  2. Cross-check Pro↔Flash (crosscheck_fields): allinea per campo i due
     bracci sullo stesso caso gold, li classifica CONCORDI/DISCORDI e — col
     gold come verità — misura se il disaccordo predice l'errore. Il caso
     pericoloso è `concordi-e-sbagliati`: i due modelli sbagliano insieme lo
     stesso valore, e lì il cross-check è cieco per costruzione.

Nessuna scrittura sul DB, nessuna chiamata OCR: pura analisi di JSON.
"""
import glob
import json
import os
import re

# case_id dei casi con asserzioni note verificate a mano in §8.19.
CASE_REFERTO8 = "2026-03-28_unime_vs_nautilus-roma"         # 22 gol, 3 TO, 1 EDCS
CASE_BELLATOR = "2026-04-11_bellator-frusino_vs_ss-lazio-nuoto"  # finale casa truth 4
CASE_TRISCELON = "2026-04-25_nautilus-nuoto-roma_vs_triscelon-etna-sport"  # data truth 25

# I 13 campi punteggi/parziali/data + nomi confrontati per caso (asse a: 13×6=78).
SUMMARY_BUCKETS = ("stable_correct", "stable_wrong", "stable_null", "instabile", "ambiguo")


def load_arm(out_dir, model_slug):
    """Carica le proposte repeat di un braccio da una directory di output del bench.

    Ritorna {case_id: proposal}. Un braccio = un modello (model_slug è lo slug
    del modello nel nome file, es. 'gemini-2.5-pro' o 'gemini-3.6-flash').
    Se per uno stesso caso esistono più file (run ripetuti), vince il più
    recente per timestamp nel nome (ordinamento lessicografico dei nomi file).
    """
    by_case = {}
    pattern = os.path.join(out_dir, f"*__{model_slug}_repeat*.json")
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as f:
            prop = json.load(f)
        case_id = prop.get("case_id") or os.path.basename(path).split("__")[0]
        by_case[case_id] = prop  # sorted() => l'ultimo (più recente) sovrascrive
    return by_case


def axis_a(proposals):
    """Asse a §8.19: somma dei bucket `summary` sui campi punteggi/parziali/data.

    `proposals` è un iterabile di proposte repeat (una per caso). Ritorna il
    dict dei bucket sommato su tutti i casi (denominatore = 13×N casi). È
    esattamente il conteggio 'stabili-corretti / stabili-sbagliati / instabili
    / ambigui' dell'asse a, ricostruito dai summary che il bench ha già scritto.
    """
    total = {b: 0 for b in SUMMARY_BUCKETS}
    n_fields = 0
    for prop in proposals:
        summary = prop.get("summary") or {}
        for b in SUMMARY_BUCKETS:
            total[b] += summary.get(b, 0)
        n_fields += sum(summary.get(b, 0) for b in SUMMARY_BUCKETS)
    total["n_fields"] = n_fields
    return total


def _field_rep(agg_entry):
    """Valore rappresentativo di un campo aggregato: la pluralità (distinct[0]).

    distinct_values è ordinato per conteggio decrescente dal bench, quindi il
    primo è il valore più frequente (o l'unico se stabile). Ritorna
    (rep_value, stable, count_top, n_total).
    """
    dv = agg_entry.get("distinct_values") or []
    if not dv:
        return None, True, 0, 0
    n_total = sum(d["count"] for d in dv)
    top = dv[0]
    stable = len(dv) == 1
    return top["value"], stable, top["count"], n_total


def _norm(field, v):
    """Normalizza un valore di campo per il confronto fra bracci.

    I nomi squadra si confrontano su alfanumerici maiuscoli (la punteggiatura
    non è un errore di lettura, coerente con normalize_team_name del bench);
    gli altri campi (punteggi interi, data stringa) si confrontano tal quali.
    """
    if v is None:
        return None
    if field.endswith("_team_name"):
        return re.sub(r"[^A-Z0-9]", "", str(v).upper()) or None
    return v


def crosscheck_fields(pro_by_case, flash_by_case):
    """Cross-check Pro↔Flash per campo, col gold come verità.

    Per ogni caso comune e ogni campo dell'aggregato, prende il valore
    rappresentativo (pluralità) dei due bracci. Confronta SOLO i campi dove la
    truth è nota e ENTRAMBI i bracci hanno prodotto un valore (le astensioni
    null, come in §8.19, sono escluse e contate a parte). Classifica:

      - concordi-e-giusti:   rep_pro == rep_flash == truth
      - concordi-e-sbagliati: rep_pro == rep_flash != truth  (CIECO: il metodo
                              non può vederlo, i due modelli sbagliano insieme)
      - discordi-uno-giusto:  rep_pro != rep_flash, almeno uno == truth
      - discordi-entrambi-sbagliati: rep_pro != rep_flash, nessuno == truth

    Metriche del disaccordo come predittore d'errore:
      - error_fields = campi con almeno un braccio sbagliato
      - recall_union = disaccordi / error_fields  (errori catturati dal flag)
      - blind_rate   = concordi_sbagliati / error_fields  (= 1 - recall_union)
      - precision_union = disaccordi-con-errore / disaccordi (=1.0 per
        costruzione: due valori diversi non possono essere entrambi la verità)
      - recall_pro / blind_pro: la stessa cosa ristretta agli errori del
        modello di PRODUZIONE (Pro), perché è quello che oggi pubblica.

    Ritorna (buckets, metrics, rows): rows è la lista per-campo con il
    dettaglio (case_id, field, valori, stabilità, correttezza, agree, classe).
    """
    buckets = {
        "concordi_giusti": 0, "concordi_sbagliati": 0,
        "discordi_uno_giusto": 0, "discordi_entrambi_sbagliati": 0,
    }
    excluded_null = 0
    rows = []
    caught_pro = missed_pro = pro_error = 0

    common = [c for c in pro_by_case if c in flash_by_case]
    for case_id in sorted(common):
        pro_agg = (pro_by_case[case_id].get("aggregate") or {})
        flash_agg = (flash_by_case[case_id].get("aggregate") or {})
        for field in pro_agg:
            if field not in flash_agg:
                continue
            truth = pro_agg[field].get("truth")
            if truth is None:
                continue
            p_rep, p_stable, _, _ = _field_rep(pro_agg[field])
            f_rep, f_stable, _, _ = _field_rep(flash_agg[field])
            if p_rep is None or f_rep is None:
                excluded_null += 1
                continue

            p_norm, f_norm, t_norm = (_norm(field, p_rep), _norm(field, f_rep),
                                      _norm(field, truth))
            agree = p_norm == f_norm
            p_correct = p_norm == t_norm
            f_correct = f_norm == t_norm

            if agree and p_correct:
                cls = "concordi_giusti"
            elif agree and not p_correct:
                cls = "concordi_sbagliati"
            elif p_correct or f_correct:
                cls = "discordi_uno_giusto"
            else:
                cls = "discordi_entrambi_sbagliati"
            buckets[cls] += 1

            # Prospettiva produzione (Pro): errore Pro catturato dal disaccordo?
            if not p_correct:
                pro_error += 1
                if agree:
                    missed_pro += 1  # Flash sbaglia lo stesso valore -> cieco
                else:
                    caught_pro += 1

            rows.append({
                "case_id": case_id, "field": field, "truth": truth,
                "pro": p_rep, "pro_stable": p_stable, "pro_correct": p_correct,
                "flash": f_rep, "flash_stable": f_stable, "flash_correct": f_correct,
                "agree": agree, "class": cls,
            })

    disagreements = buckets["discordi_uno_giusto"] + buckets["discordi_entrambi_sbagliati"]
    error_fields = buckets["concordi_sbagliati"] + disagreements
    comparable = sum(buckets.values())
    metrics = {
        "comparable_fields": comparable,
        "excluded_null_fields": excluded_null,
        "error_fields": error_fields,
        "disagreements": disagreements,
        "concordi_sbagliati": buckets["concordi_sbagliati"],
        "concordi_sbagliati_rate": (buckets["concordi_sbagliati"] / comparable) if comparable else None,
        "recall_union": (disagreements / error_fields) if error_fields else None,
        "blind_rate_union": (buckets["concordi_sbagliati"] / error_fields) if error_fields else None,
        "precision_union": (disagreements / disagreements) if disagreements else None,
        "pro_error_fields": pro_error,
        "recall_pro": (caught_pro / pro_error) if pro_error else None,
        "missed_pro": missed_pro,
    }
    return buckets, metrics, rows


def known_stable_error_rows(rows):
    """Estrae dalle rows del cross-check le righe dei due errori stabili noti.

    Bellator finale casa (truth 4) e Triscelon data (truth 25 -> '2026-04-25'):
    §8.19 li dà stabili-sbagliati su Pro. La domanda del cross-check è: Flash
    sbaglia lo stesso valore (concordi-e-sbagliati -> cieco) o legge diverso
    (discordi -> catturabile)?
    """
    wanted = {
        (CASE_BELLATOR, "final_score_home"),
        (CASE_TRISCELON, "date"),
    }
    return [r for r in rows if (r["case_id"], r["field"]) in wanted]


def events_referto8(proposals_by_case, case_id=CASE_REFERTO8):
    """Asse b/g §8.19 sul referto 8: conteggi eventi per ripetizione.

    Per ogni ripetizione conta dai `repeats[].extracted.events`: gol per lato,
    gol con autore, TIMEOUT, EXCLUSION_DEF. Ritorna None se il caso manca.
    Denominatori noti (§8.18): 12 gol casa + 10 ospite = 22; 3 timeout; 1 EDCS.
    """
    prop = proposals_by_case.get(case_id)
    if prop is None:
        return None
    per_repeat = []
    for rep in prop.get("repeats") or []:
        events = (rep.get("extracted") or {}).get("events") or []
        goals_home = goals_away = goals_author = timeouts = edcs = 0
        for e in events:
            if not isinstance(e, dict):
                continue
            t = e.get("type")
            if t == "GOAL":
                if e.get("team") == "home":
                    goals_home += 1
                elif e.get("team") == "away":
                    goals_away += 1
                if e.get("player_name") or e.get("player") or e.get("cap") is not None:
                    goals_author += 1
            elif t == "TIMEOUT":
                timeouts += 1
            elif t == "EXCLUSION_DEF":
                edcs += 1
        per_repeat.append({
            "goals_home": goals_home, "goals_away": goals_away,
            "goals_total": goals_home + goals_away, "goals_with_author": goals_author,
            "timeouts": timeouts, "edcs": edcs,
        })
    return per_repeat


def sum_token_cost(proposals, price_in_per_m, price_out_per_m):
    """Somma i token (in / out+thoughts) dei repeats e calcola il costo del braccio.

    Legge `repeats[].self_reported_confidence`? No: i token stanno nel
    token_usage dei metadati grezzi, che il bench non ricopia nella proposta.
    Questa funzione somma invece dai dati che la proposta espone se presenti;
    quando i token non sono persistiti nella proposta ritorna None e il costo
    va calcolato dal log del run. Additiva e tollerante.
    """
    tok_in = tok_out = 0
    found = False
    for prop in proposals:
        for rep in prop.get("repeats") or []:
            usage = ((rep.get("extracted") or {}).get("token_usage")
                     or rep.get("token_usage") or {})
            if usage:
                found = True
                tok_in += usage.get("prompt_tokens") or 0
                tok_out += (usage.get("completion_tokens") or 0) + (usage.get("thoughts_tokens") or 0)
    if not found:
        return None
    return {
        "tokens_in": tok_in, "tokens_out": tok_out,
        "cost_usd": tok_in / 1e6 * price_in_per_m + tok_out / 1e6 * price_out_per_m,
    }
