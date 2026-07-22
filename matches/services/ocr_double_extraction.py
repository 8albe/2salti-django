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
