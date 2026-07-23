
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

# --- Espulsione definitiva (EDCS) -------------------------------------------
# Sanzione DISTINTA dall'esclusione di 20 secondi: e' definitiva (il giocatore
# esce per il resto della partita), porta una sostituzione e - a seconda
# dell'articolo di regolamento - puo' comportare un rigore per gli avversari e
# una squalifica per le partite successive. Modellata come TIPO a se'
# (EXCLUSION_DEF), non come attributo di EXCLUSION_20, per una ragione precisa:
# il conteggio fouled-out/over-limit opera su EXCLUSION_20; pooling di una
# definitiva fra le 20" corromperebbe quel conteggio (una definitiva NON e' una
# delle tre esclusioni di 20 secondi). Inoltre porta campi che nessun altro
# evento porta (regulation_article, sanction_sigla).
#
# NB: EXCLUSION_DEF e' un tipo di SCHEMA OCR / gold (misura del bench). NON e'
# ancora fra i DEFAULT_EVENT_TYPES canonici pubblicabili: l'integrazione nel
# pipeline di pubblicazione (MatchEvent) e' fuori dallo scope di questo giro
# (il report 8 resta NEEDS_REVIEW e non viene pubblicato).
EVENT_TYPE_EXCLUSION_DEF = 'EXCLUSION_DEF'

# Tabella dati esplicita articolo di regolamento -> classificazione dell'espulsione
# definitiva. Popolata SOLO con gli articoli VERIFICATI a mano da un umano sul
# regolamento. La tassonomia vive QUI, nel nostro codice, MAI nel prompt OCR: il
# modello estrae l'articolo verbatim come stringa, e la mappatura avviene a valle,
# cosi' un articolo mai visto resta grezzo e mappabile in seguito invece di essere
# inventato dal modello. Un articolo assente da questa tabella NON e' un errore:
# finisce nel ramo 'sconosciuto' di classify_definitive_exclusion.
DEFINITIVE_EXCLUSION_ARTICLES = {
    "9.13": {
        "kind": "misconduct",
        "label": "Cattiva condotta",
        "penalty_awarded": False,
        "substitution": "immediate",
        "next_matches_ban": False,
        "description": (
            "Espulsione definitiva per il resto della partita, con sostituzione "
            "(immediata, senza inferiorita' a tempo)."
        ),
    },
    "9.14": {
        "kind": "brutality",
        "label": "Atto di brutalita'",
        "penalty_awarded": True,
        "substitution": "after_4_minutes",
        "next_matches_ban": True,
        "description": (
            "Atto di brutalita': espulsione definitiva; rigore alla squadra "
            "avversaria; sostituzione solo allo scadere di 4 minuti di gioco "
            "effettivo (la squadra gioca 4 minuti in inferiorita'); squalifica "
            "per le partite successive."
        ),
    },
}


def classify_definitive_exclusion(article):
    """Classifica un'espulsione definitiva dal numero d'articolo (stringa verbatim).

    `article` e' la stringa grezza estratta dal referto (es. "9.13"), NON un valore
    che il modello ha interpretato. Ritorna sempre un dict con `article` (la stringa
    normalizzata sugli spazi) e `known` (bool):
    - se l'articolo e' in DEFINITIVE_EXCLUSION_ARTICLES: `known=True` + i campi noti;
    - altrimenti il ramo 'sconosciuto': `known=False`, `kind="unknown"`, gli altri
      campi a None. La stringa grezza si CONSERVA (in `article`) e la funzione NON
      solleva: un articolo mai visto non si inventa, resta mappabile dopo.
    """
    raw = None if article is None else str(article).strip()
    known = DEFINITIVE_EXCLUSION_ARTICLES.get(raw)
    if known is not None:
        return {"article": raw, "known": True, **known}
    return {
        "article": raw,
        "known": False,
        "kind": "unknown",
        "label": None,
        "penalty_awarded": None,
        "substitution": None,
        "next_matches_ban": None,
        "description": None,
    }


def get_event_label(code, sport=None):
    """
    Returns the label for an event code.
    If sport is provided, it should ideally check SportEventConfig (not implemented here to avoid circular imports,
    better handled in model method).
    """
    return EVENT_LABELS.get(code, code)
