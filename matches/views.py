from django.shortcuts import render, get_object_or_404
from .models import Match, MatchEvent

def match_detail(request, match_id):
    """Pagina dettaglio partita con tabellino"""
    match = get_object_or_404(Match.objects.select_related(
        'home_team__society',
        'away_team__society',
        'league'
    ), id=match_id)
    
    # Eventi raggruppati per tipo
    goals = match.events.filter(event_type='GOAL').select_related('player', 'team')
    expulsions = match.events.filter(event_type='EXPULSION').select_related('player', 'team')
    timeouts = match.events.filter(event_type='TIMEOUT').select_related('team')
    
    context = {
        'match': match,
        'goals': goals,
        'expulsions': expulsions,
        'timeouts': timeouts,
        'sport': match.league.sport,
        'sport_color': match.league.sport.hex_color,
    }
    
    return render(request, 'matches/match_detail.html', context)


def league_statistics(request, league_slug):
    """Pagina statistiche avanzate campionato"""
    from core.models import League
    from .stats_services import get_top_scorers, get_discipline_stats
    
    league = get_object_or_404(League, slug=league_slug)
    
    # 1. Recupera la classifica per determinare il ranking delle squadre
    # league.get_standings() ritorna una lista ordinata di dict
    standings = league.get_standings()
    
    # Crea una mappa {team_id: posizione} (1-based index)
    team_rank_map = {entry['team'].id: idx + 1 for idx, entry in enumerate(standings)}
    
    # Crea una mappa {team_id: partite_giocate} per il calcolo media espulsioni
    team_matches_map = {entry['team'].id: entry['played'] for entry in standings}

    # 2. Top Scorers (Sorting: Gol > Posizione Squadra > Cognome)
    # Nota: limit=100 per prendere un buon numero prima di ordinare, poi tagliamo
    top_scorers_list = list(get_top_scorers(league.id, limit=50))
    
    def scorer_sort_key(scorer):
        goals = scorer['total_goals']
        # Usa 999 se il team non è in classifica (non dovrebbe succedere)
        team_rank = team_rank_map.get(scorer['team__id'], 999)
        name = scorer['player__last_name']
        # Tuple comparison:
        # -goals (desc), team_rank (asc), name (asc)
        return (-goals, team_rank, name)
    
    top_scorers_list.sort(key=scorer_sort_key)
    
    # 3. Bad Boys (Sorting: Espulsioni > Cognome) + Media
    bad_boys_list = list(get_discipline_stats(league.id, limit=50))
    
    for bb in bad_boys_list:
        start_matches = team_matches_map.get(bb['team__id'], 1) # Evita division by zero
        if start_matches == 0: start_matches = 1
        bb['avg_expulsions'] = bb['total_expulsions'] / start_matches

    def bad_boy_sort_key(bb):
        expulsions = bb['total_expulsions']
        name = bb['player__last_name']
        return (-expulsions, name)
        
    bad_boys_list.sort(key=bad_boy_sort_key)

    context = {
        'league': league,
        'top_scorers': top_scorers_list[:15], # Show top 15
        'bad_boys': bad_boys_list[:15],       # Show top 15
        'sport': league.sport,
        'sport_color': league.sport.hex_color,
    }
    
    return render(request, 'leagues/league_stats.html', context)


def sport_matches(request, sport_slug):
    """Lista di tutte le partite di uno sport (filtrate per data)"""
    from core.models import Sport
    from core.utils import get_calendar_dates
    from django.utils import timezone
    import datetime
    
    sport = get_object_or_404(Sport, slug=sport_slug)
    
    # Gestione Data
    today = timezone.now().date()
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
    else:
        selected_date = today

    calendar_dates = get_calendar_dates(center_date=selected_date)

    matches = Match.objects.filter(
        league__sport=sport,
        match_date__date=selected_date
    ).select_related(
        'home_team__society', 
        'away_team__society', 
        'league'
    ).order_by('match_date')
    
    return render(request, 'sport/sport_matches.html', {
        'sport': sport, 
        'matches': matches, 
        'sport_color': sport.hex_color,
        'calendar_dates': calendar_dates,
        'selected_date': selected_date,
        'today': today,
    })
