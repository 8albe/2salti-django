
# Standard event types for the platform.
# These act as a safe fallback if no sport-specific SportEventConfig is found.

EVENT_TYPE_GOAL = 'GOAL'
EVENT_TYPE_EXCLUSION_20 = 'EXCLUSION_20'
EVENT_TYPE_YELLOW_CARD = 'YELLOW_CARD'
EVENT_TYPE_RED_CARD = 'RED_CARD'
EVENT_TYPE_TIMEOUT = 'TIMEOUT'

DEFAULT_EVENT_TYPES = [
    {'code': EVENT_TYPE_GOAL, 'label': 'Gol', 'is_score': True},
    {'code': EVENT_TYPE_EXCLUSION_20, 'label': 'Espulsione 20s', 'is_score': False},
    {'code': EVENT_TYPE_YELLOW_CARD, 'label': 'Cartellino Giallo', 'is_score': False},
    {'code': EVENT_TYPE_RED_CARD, 'label': 'Cartellino Rosso', 'is_score': False},
    {'code': EVENT_TYPE_TIMEOUT, 'label': 'Timeout Squadra', 'is_score': False},
]

# Quick lookup maps
EVENT_LABELS = {e['code']: e['label'] for e in DEFAULT_EVENT_TYPES}
SCORE_EVENT_CODES = [e['code'] for e in DEFAULT_EVENT_TYPES if e.get('is_score', False)]

# Regolamento pallanuoto: alla TERZA espulsione un giocatore e' fuori per tutta la
# partita ("fouled out"). Non e' solo plausibilita': e' uno stato di gioco reale.
# 3 e' quindi il MASSIMO possibile di espulsioni per giocatore in una partita: un
# 4o valore e' impossibile per costruzione (errore di trascrizione o di estrazione).
FOUL_OUT_EXCLUSIONS = 3


def _player_identity(event):
    """Chiave di identita' del giocatore in un evento (schema OCR o truth gold).

    Preferisce il nome (`player_name`/`player`), poi la calottina (`cap`/`number`).
    Ritorna None se l'evento non identifica alcun giocatore (es. gol senza autore,
    timeout di squadra): quegli eventi restano fuori dal conteggio per-giocatore.
    """
    if not isinstance(event, dict):
        return None
    name = event.get("player_name") or event.get("player")
    if name:
        return str(name).strip().lower()
    cap = event.get("cap")
    if cap is None:
        cap = event.get("number")
    return f"#{cap}" if cap is not None else None


def count_exclusions_per_player(events, exclusion_codes=(EVENT_TYPE_EXCLUSION_20,)):
    """Conta le espulsioni per (team, giocatore) da una lista eventi in schema OCR/truth.

    Regola di dominio, non estratta dal modello: si deriva dalla lista eventi. Usata sia
    per le statistiche (fouled out) sia per la validazione (>3 = impossibile). Gli eventi
    senza identita' del giocatore sono ignorati (non attribuibili). Ritorna
    {(team, identity): count}.
    """
    codes = set(exclusion_codes)
    counts = {}
    for e in events or []:
        if not isinstance(e, dict) or e.get("type") not in codes:
            continue
        identity = _player_identity(e)
        if identity is None:
            continue
        key = (e.get("team"), identity)
        counts[key] = counts.get(key, 0) + 1
    return counts


def players_over_exclusion_limit(events, exclusion_codes=(EVENT_TYPE_EXCLUSION_20,)):
    """(team, giocatore) che superano il limite di 3 espulsioni: sempre un errore.

    Un 4o cartellino per lo stesso giocatore e' impossibile a regolamento, quindi la
    sua presenza segnala un errore di trascrizione umana (sui casi gold) o di estrazione
    (sull'OCR). Ritorna la lista di (team, identity, count) con count > FOUL_OUT_EXCLUSIONS.
    """
    counts = count_exclusions_per_player(events, exclusion_codes)
    return [
        (team, identity, c)
        for (team, identity), c in sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
        if c > FOUL_OUT_EXCLUSIONS
    ]


def fouled_out_players(events, exclusion_codes=(EVENT_TYPE_EXCLUSION_20,)):
    """(team, giocatore) che raggiungono le 3 espulsioni (fouled out) in questa lista eventi.

    Applicata alla lista eventi di UNA partita restituisce chi e' uscito per falli in quella
    partita. Ritorna la lista di (team, identity, count) con count >= FOUL_OUT_EXCLUSIONS.
    """
    counts = count_exclusions_per_player(events, exclusion_codes)
    return [
        (team, identity, c)
        for (team, identity), c in sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
        if c >= FOUL_OUT_EXCLUSIONS
    ]

def get_event_label(code, sport=None):
    """
    Returns the label for an event code.
    If sport is provided, it should ideally check SportEventConfig (not implemented here to avoid circular imports,
    better handled in model method).
    """
    return EVENT_LABELS.get(code, code)
