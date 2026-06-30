"""Service per gli sponsor relazionali di una società (Macro 9).

Sorgente di verità per il render: gli sponsor attivi della società nella
stagione corrente del suo sport. La granularità è società-wide per stagione
(non per-lega). Degrada a queryset vuoto — senza sollevare — quando non c'è una
stagione corrente o la società non ha sponsor, così le superfici di render
(scheda società, profilo atleta) possono nascondere il blocco con un semplice
`{% if %}`.
"""
from core.models import Sponsor
from core.services.season_service import get_current_season


def get_society_sponsors(society):
    """Ritorna gli Sponsor attivi della società nella stagione corrente.

    Usa `get_current_season(society.sport)` per scegliere la stagione: se non
    esiste una stagione corrente per quello sport ritorna un queryset vuoto
    (nessuno sponsor mostrato), non un errore. L'ordinamento segue il
    `Meta.ordering` del modello (`order`, poi `name`).
    """
    if society is None:
        return Sponsor.objects.none()
    season = get_current_season(society.sport)
    if season is None:
        return Sponsor.objects.none()
    return Sponsor.objects.filter(
        society=society, season=season, is_active=True
    ).select_related('society', 'season')
