from django.db.models import Count, Q
from .models import MatchEvent
from .event_types import (
    EVENT_TYPE_GOAL,
    EVENT_TYPE_EXCLUSION_20,
    FOUL_OUT_EXCLUSIONS,
)


def get_top_scorers(league_id, limit=10):
    """
    Ritorna la lista dei marcatori ordinata per numero di gol.
    """
    scorers = (
        MatchEvent.objects
        .filter(
            match__league_id=league_id,
            event_type=EVENT_TYPE_GOAL,
            player__isnull=False
        )

        .values(
            'player__first_name',
            'player__last_name',
            'team__id',
            'team__name',
            'team__society__logo',  # Added logo
            'team__society__name'   # Added society name
        )
        .annotate(total_goals=Count('id'))
        .order_by('-total_goals', 'player__last_name')[:limit]
    )
    return scorers

def get_discipline_stats(league_id, limit=10):
    """
    Ritorna la lista dei giocatori più 'cattivi' (espulsioni).
    """
    bad_boys = (
        MatchEvent.objects
        .filter(
            match__league_id=league_id,
            event_type=EVENT_TYPE_EXCLUSION_20,
            player__isnull=False
        )

        .values(
            'player__first_name', 
            'player__last_name', 
            'team__id',
            'team__name',
            'team__society__logo',
            'team__society__name'
        )
        .annotate(total_expulsions=Count('id'))
        .order_by('-total_expulsions', 'player__last_name')[:limit]
    )
    return bad_boys


def get_fouled_out_stats(league_id, limit=10):
    """Quante volte ogni giocatore raggiunge le 3 espulsioni ("fouled out") nel campionato.

    Regola pallanuoto: alla terza espulsione il giocatore e' fuori per tutta la partita.
    E' un dato derivato, non estratto: si conta per (giocatore, partita) e si tiene chi
    raggiunge FOUL_OUT_EXCLUSIONS, poi si conta in quante partite e' successo. Segnala
    indisciplina o durezza difensiva ed e' gia' scritto sul cartaceo.
    """
    per_match = (
        MatchEvent.objects
        .filter(
            match__league_id=league_id,
            event_type=EVENT_TYPE_EXCLUSION_20,
            player__isnull=False,
        )
        .values(
            'player__id', 'player__first_name', 'player__last_name',
            'team__id', 'team__name', 'team__society__logo', 'team__society__name',
            'match_id',
        )
        .annotate(exclusions_in_match=Count('id'))
        .filter(exclusions_in_match__gte=FOUL_OUT_EXCLUSIONS)
    )

    # Aggrega per giocatore: quante partite con >=3 espulsioni, e totale espulsioni
    # in quelle partite. Fatto in Python: e' un secondo livello di aggregazione su un
    # insieme gia' ristretto (poche righe), non vale una subquery.
    by_player = {}
    for row in per_match:
        pid = row['player__id']
        agg = by_player.setdefault(pid, {
            'player__first_name': row['player__first_name'],
            'player__last_name': row['player__last_name'],
            'team__id': row['team__id'],
            'team__name': row['team__name'],
            'team__society__logo': row['team__society__logo'],
            'team__society__name': row['team__society__name'],
            'fouled_out_count': 0,
            'total_expulsions_in_fouled_out': 0,
        })
        agg['fouled_out_count'] += 1
        agg['total_expulsions_in_fouled_out'] += row['exclusions_in_match']

    result = sorted(
        by_player.values(),
        key=lambda a: (-a['fouled_out_count'], a['player__last_name'] or ''),
    )
    return result[:limit]
