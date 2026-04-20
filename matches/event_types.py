
# Standard event types for the platform.
# These act as a safe fallback if no sport-specific SportEventConfig is found.

EVENT_TYPE_GOAL = 'GOAL'
EVENT_TYPE_PENALTY_GOAL = 'PENALTY_GOAL'
EVENT_TYPE_EXCLUSION_20 = 'EXCLUSION_20'
EVENT_TYPE_EXCLUSION_DEF = 'EXCLUSION_DEF'
EVENT_TYPE_YELLOW_CARD = 'YELLOW_CARD'
EVENT_TYPE_RED_CARD = 'RED_CARD'
EVENT_TYPE_SAVE = 'SAVE'
EVENT_TYPE_TIMEOUT = 'TIMEOUT'

DEFAULT_EVENT_TYPES = [
    {'code': EVENT_TYPE_GOAL, 'label': 'Gol', 'is_score': True},
    {'code': EVENT_TYPE_PENALTY_GOAL, 'label': 'Rigore Segnato', 'is_score': True},
    {'code': EVENT_TYPE_EXCLUSION_20, 'label': 'Espulsione 20s', 'is_score': False},
    {'code': EVENT_TYPE_EXCLUSION_DEF, 'label': 'Espulsione Definitiva', 'is_score': False},
    {'code': EVENT_TYPE_YELLOW_CARD, 'label': 'Cartellino Giallo', 'is_score': False},
    {'code': EVENT_TYPE_RED_CARD, 'label': 'Cartellino Rosso', 'is_score': False},
    {'code': EVENT_TYPE_SAVE, 'label': 'Parata Porta', 'is_score': False},
    {'code': EVENT_TYPE_TIMEOUT, 'label': 'Timeout Squadra', 'is_score': False},
]

# Quick lookup maps
EVENT_LABELS = {e['code']: e['label'] for e in DEFAULT_EVENT_TYPES}
SCORE_EVENT_CODES = [e['code'] for e in DEFAULT_EVENT_TYPES if e.get('is_score', False)]

def get_event_label(code, sport=None):
    """
    Returns the label for an event code.
    If sport is provided, it should ideally check SportEventConfig (not implemented here to avoid circular imports, 
    better handled in model method).
    """
    return EVENT_LABELS.get(code, code)
