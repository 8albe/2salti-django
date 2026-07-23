"""
Regola di divergenza fra due letture OCR indipendenti dello stesso referto
(doppia estrazione per zona — Macro 8, giro 2026-07-22).

Il PRIMO passaggio è l'estrazione completa (prompt di produzione, es. V3); il
SECONDO è la lettura "solo zona" (OCR_SYSTEM_PROMPT_ZONE), ristretta a punteggio
finale, griglia dei parziali e data. Le due letture sono indipendenti: il secondo
passaggio non vede il risultato del primo. Se le due letture discordano su una
delle tre zone, il referto va marcato NEEDS_REVIEW — nessuna delle due è
autorevole di per sé: la divergenza segnala solo che quella zona non è affidabile
e serve una review umana. La regola ALZA la bandiera, non sceglie il valore giusto.

Funzione pura: nessun effetto collaterale, nessun accesso a DB, nessun import di
Django. Si presta sia al bench (misura di questo giro) sia, in futuro, alla
pipeline di produzione (in questo giro NON adottata: è una misura, non un'adozione).
"""
import re

# Le tre zone confrontate. La regola guarda SOLO queste: sono quelle dove vivono
# gli errori stabili misurati sul gold (finale casa Bellator, data Triscelon) e
# le uniche estratte dal secondo passaggio.
ZONES = ("final_score", "quarters", "date")

QUARTER_KEYS = ("1", "2", "3", "4")


def _parse_final_score(value):
    """'X-Y' -> (X, Y) come interi; None se null o non parsabile."""
    if not isinstance(value, str):
        return None
    m = re.match(r"^\s*(\d+)\s*[-–]\s*(\d+)\s*$", value)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _quarter_cell(quarters, key, side):
    """Valore di un lato (0=home, 1=away) di un quarto; None se assente/null."""
    if not isinstance(quarters, dict):
        return None
    q = quarters.get(key) if key in quarters else quarters.get(str(key))
    if not isinstance(q, (list, tuple)) or len(q) != 2:
        return None
    v = q[side]
    return v if isinstance(v, int) else None


def _cell_status(a, b):
    """Confronto di una singola cella fra i due passaggi.

    Ritorna uno di: 'agree' (entrambe presenti e uguali), 'diverge' (entrambe
    presenti e diverse), 'abstain' (almeno una è null: meno informazione, NON una
    contraddizione — non fa scattare la review da sola).
    """
    if a is None or b is None:
        return "abstain"
    return "agree" if a == b else "diverge"


def compare_passes(first, second):
    """Confronta due estrazioni (schema OCR v2 / zone) sulle tre zone.

    `first` e `second` sono i dict di estrazione (con 'scores' e 'match_info').
    Ritorna un dict strutturato:

      {
        "diverges": bool,          # True se ALMENO una zona diverge
        "review": bool,            # == diverges: la regola manda in NEEDS_REVIEW
        "diverging_zones": [...],  # sottoinsieme di ZONES che diverge
        "zones": {
            "final_score": {"first","second","status"},
            "quarters": {"cells": {"1_home": {...}, ...}, "status"},
            "date": {"first","second","status"},
        },
      }

    Divergenza di una zona = almeno una cella/valore 'diverge' (entrambi presenti
    e diversi). Una lettura null (astensione) NON conta come divergenza: è meno
    informazione, non una contraddizione — riportata come 'abstain' e mai come
    trigger di review. `review` coincide con `diverges` (la regola: discordanza su
    finale, parziali o data -> NEEDS_REVIEW).
    """
    first = first or {}
    second = second or {}
    f_scores = first.get("scores") or {}
    s_scores = second.get("scores") or {}
    f_info = first.get("match_info") or {}
    s_info = second.get("match_info") or {}

    zones = {}

    # --- zona 1: punteggio finale (confronto sui due lati, non sulla stringa) ---
    f_final_raw = f_scores.get("final_score")
    s_final_raw = s_scores.get("final_score")
    f_final = _parse_final_score(f_final_raw)
    s_final = _parse_final_score(s_final_raw)
    if f_final is None or s_final is None:
        final_status = "abstain"
    else:
        final_status = "agree" if f_final == s_final else "diverge"
    zones["final_score"] = {
        "first": f_final_raw,
        "second": s_final_raw,
        "status": final_status,
    }

    # --- zona 2: griglia parziali (8 celle, ognuna confrontata separatamente) ---
    f_q = f_scores.get("quarters") or {}
    s_q = s_scores.get("quarters") or {}
    cells = {}
    quarters_status = "agree"
    saw_comparable = False
    for k in QUARTER_KEYS:
        for side, label in ((0, "home"), (1, "away")):
            a = _quarter_cell(f_q, k, side)
            b = _quarter_cell(s_q, k, side)
            st = _cell_status(a, b)
            cells[f"{k}_{label}"] = {"first": a, "second": b, "status": st}
            if st == "diverge":
                quarters_status = "diverge"
            elif st == "agree":
                saw_comparable = True
    if quarters_status != "diverge" and not saw_comparable:
        quarters_status = "abstain"
    zones["quarters"] = {"cells": cells, "status": quarters_status}

    # --- zona 3: data ---
    f_date = f_info.get("date")
    s_date = s_info.get("date")
    zones["date"] = {
        "first": f_date,
        "second": s_date,
        "status": _cell_status(f_date, s_date),
    }

    diverging_zones = [z for z in ZONES if zones[z]["status"] == "diverge"]
    diverges = bool(diverging_zones)
    return {
        "diverges": diverges,
        "review": diverges,
        "diverging_zones": diverging_zones,
        "zones": zones,
    }


# --- doppia estrazione per zona sugli EVENTI (§8.24 stadio B) -----------------
# Gemello di compare_passes per la STORIA CRONOMETRICA. Il PRIMO passaggio è
# l'estrazione completa (V3.5, con eventi e calottina); il SECONDO è la lettura
# "solo zona eventi" (OCR_SYSTEM_PROMPT_ZONE_EVENTS) sul ritaglio. Le due letture
# sono indipendenti. La regola ALZA la bandiera (divergenza -> NEEDS_REVIEW), non
# sceglie il valore giusto.

def _event_identity(e):
    """Chiave d'identità di un evento fra i due passaggi: (type, quarter, clock).

    Normalizza: type stringa upper, quarter a int quando possibile (altrimenti
    stringa/None), clock stringa strip (altrimenti None). Due eventi con la stessa
    (type, quarter, clock) sono "lo stesso evento" ai fini del confronto; il payload
    confrontato è (cap, team). Ritorna None se `e` non è un dict.
    """
    if not isinstance(e, dict):
        return None
    etype = e.get("type")
    etype = str(etype).strip().upper() if etype is not None else None
    q = e.get("quarter")
    if isinstance(q, bool):
        q = None
    if q is not None:
        try:
            q = int(str(q).strip())
        except (ValueError, TypeError):
            q = str(q).strip()
    clock = e.get("clock")
    clock = str(clock).strip() if isinstance(clock, str) and clock.strip() else None
    return (etype, q, clock)


def _index_events(events):
    """Mappa identità -> lista di eventi (schema OCR). Gli eventi senza clock (chiave
    con clock None) restano indicizzati ma sono meno affidabili: più eventi possono
    collassare sulla stessa chiave, gestiti come multiset per conteggio."""
    idx = {}
    for e in events or []:
        key = _event_identity(e)
        if key is None:
            continue
        idx.setdefault(key, []).append(e)
    return idx


def compare_event_passes(first, second):
    """Confronta gli eventi di due estrazioni sulla chiave (type, quarter, clock).

    `first` e `second` sono i dict di estrazione (con `events`). Per ogni identità
    presente in almeno un passaggio confronta il payload (cap, team) con la stessa
    tricotomia di compare_passes (_cell_status: agree/diverge/abstain). Un evento
    presente in un solo passaggio è 'abstain' su entrambi i campi (meno
    informazione, non contraddizione: non fa scattare la review da solo), con
    `presence` = 'first_only'/'second_only'. Quando la stessa identità compare più
    volte in un passaggio (clock null o gol contemporanei), si confronta il primo di
    ciascun lato e si segnala `ambiguous_multiplicity`.

    Ritorna:
      {
        "diverges": bool,             # True se ALMENO un evento diverge su cap o team
        "review": bool,               # == diverges
        "events": [ { "type","quarter","clock","presence",
                      "first": {"cap","team"}, "second": {"cap","team"},
                      "cap_status","team_status","ambiguous_multiplicity" }, ... ],
        "diverging_events": [...],     # sottoinsieme che diverge
        "counts": {"compared","agree","diverge","first_only","second_only"},
      }
    """
    f_idx = _index_events((first or {}).get("events"))
    s_idx = _index_events((second or {}).get("events"))

    def _payload(e):
        cap = e.get("cap")
        if isinstance(cap, bool):
            cap = None
        team = e.get("team")
        team = team if team in ("home", "away") else (team or None)
        return cap, team

    events_out = []
    counts = {"compared": 0, "agree": 0, "diverge": 0, "first_only": 0, "second_only": 0}

    for key in sorted(set(f_idx) | set(s_idx), key=lambda k: (str(k[0]), str(k[1]), str(k[2]))):
        etype, q, clock = key
        f_list = f_idx.get(key, [])
        s_list = s_idx.get(key, [])
        ambiguous = len(f_list) > 1 or len(s_list) > 1

        if f_list and s_list:
            presence = "both"
            counts["compared"] += 1
            f_cap, f_team = _payload(f_list[0])
            s_cap, s_team = _payload(s_list[0])
            cap_status = _cell_status(f_cap, s_cap)
            team_status = _cell_status(f_team, s_team)
            if cap_status == "diverge" or team_status == "diverge":
                counts["diverge"] += 1
            elif cap_status == "agree" or team_status == "agree":
                counts["agree"] += 1
        elif f_list:
            presence = "first_only"
            counts["first_only"] += 1
            f_cap, f_team = _payload(f_list[0])
            s_cap, s_team = None, None
            cap_status = team_status = "abstain"
        else:
            presence = "second_only"
            counts["second_only"] += 1
            f_cap, f_team = None, None
            s_cap, s_team = _payload(s_list[0])
            cap_status = team_status = "abstain"

        events_out.append({
            "type": etype,
            "quarter": q,
            "clock": clock,
            "presence": presence,
            "first": {"cap": f_cap, "team": f_team},
            "second": {"cap": s_cap, "team": s_team},
            "cap_status": cap_status,
            "team_status": team_status,
            "ambiguous_multiplicity": ambiguous,
        })

    diverging_events = [
        e for e in events_out
        if e["cap_status"] == "diverge" or e["team_status"] == "diverge"
    ]
    diverges = bool(diverging_events)
    return {
        "diverges": diverges,
        "review": diverges,
        "events": events_out,
        "diverging_events": diverging_events,
        "counts": counts,
    }
