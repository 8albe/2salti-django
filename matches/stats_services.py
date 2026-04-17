from django.db.models import Count, Q
from .models import MatchEvent
from .event_types import (
    EVENT_TYPE_GOAL, EVENT_TYPE_PENALTY_GOAL,
    EVENT_TYPE_EXCLUSION_20, EVENT_TYPE_EXCLUSION_DEF
)


def get_top_scorers(league_id, limit=10):
    """
    Ritorna la lista dei marcatori ordinata per numero di gol.
    """
    scorers = (
        MatchEvent.objects
        .filter(
            match__league_id=league_id,
            event_type__in=[EVENT_TYPE_GOAL, EVENT_TYPE_PENALTY_GOAL],
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
            event_type__in=[EVENT_TYPE_EXCLUSION_20, EVENT_TYPE_EXCLUSION_DEF],
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
