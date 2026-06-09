"""Service per l'elezione della stagione corrente per-sport.

Sostituisce (a partire dalla fetta 1a-ii) il MAX lessicografico su stringa
usato in core/views.py. In questa fetta (1a-i) il service esiste ma non e'
ancora cablato nelle view.
"""
from core.models import Season


def get_current_season(sport):
    """Ritorna la Season con is_current=True per lo sport dato, o None.

    Usa .filter(...).first() (non .get()) per non sollevare se assente: lo
    stato "nessuna stagione corrente" e' legittimo finche' i dati non sono
    popolati.
    """
    return Season.objects.filter(sport=sport, is_current=True).first()
