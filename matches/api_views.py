from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from accounts.decorators import premium_required
from django.db.models import Q
import re
import json
from core.models import League, Team
from .models import Match, MatchEvent, MatchReport, AIQueryLog
from accounts.models import User
from .services.ai_services import AIStatsEngine

def _is_match_public(match):
    """Internal helper to check if a match is safe for public API consumption."""
    return match.is_finished and match.reports.filter(status=MatchReport.Status.PUBLISHED).exists()

def api_league_standings(request, league_id):
    """Returns the standings for a league in JSON format"""
    league = get_object_or_404(League, id=league_id)
    standings = league.get_standings()
    
    data = []
    for entry in standings:
        data.append({
            'rank': entry.get('rank', 0),
            'team_id': entry['team'].id,
            'team_name': entry['team'].name,
            'played': entry['played'],
            'won': entry['won'],
            'drawn': entry['drawn'],
            'lost': entry['lost'],
            'goals_for': entry['goals_for'],
            'goals_against': entry['goals_against'],
            'goal_diff': entry['goal_diff'],
            'points': entry['points'],
        })
    
    return JsonResponse({
        'league': {
            'id': league.id,
            'name': league.name,
            'season': league.season,
        },
        'standings': data
    })

def api_league_matches(request, league_id):
    """Returns matches for a league in JSON format"""
    league = get_object_or_404(League, id=league_id)
    matches = league.matches.filter(
        is_finished=True,
        reports__status=MatchReport.Status.PUBLISHED,
    ).distinct().select_related('home_team', 'away_team')
    
    data = []
    for m in matches:
        data.append({
            'id': m.id,
            'date': m.match_date.isoformat(),
            'home_team': m.home_team.name,
            'away_team': m.away_team.name,
            'home_score': m.home_score,
            'away_score': m.away_score,
            'is_finished': m.is_finished,
        })
    
    return JsonResponse({
        'league': {
            'id': league.id,
            'name': league.name,
        },
        'matches': data
    })

def api_match_detail(request, match_id):
    """Returns full match data in JSON format"""
    match = get_object_or_404(Match, id=match_id)
    
    if not _is_match_public(match):
        raise Http404("Match data not yet published")
        
    events = match.events.all().select_related('player', 'team')
    
    events_data = []
    for e in events:
        events_data.append({
            'type': e.event_type,
            'player': e.player.get_full_name() if e.player else None,
            'team': e.team.name,
            'minute': e.minute,
            'quarter': e.quarter,
        })
    
    return JsonResponse({
        'id': match.id,
        'league': match.league.name if match.league else None,
        'home_team': match.home_team.name,
        'away_team': match.away_team.name,
        'home_score': match.home_score,
        'away_score': match.away_score,
        'is_finished': match.is_finished,
        'quarter_scores': match.quarter_scores,
        'events': events_data
    })

@login_required
@premium_required
def api_ai_query(request):
    """
    AI Query Interface v2 (Live SQL Engine)
    Uses AIStatsEngine for hybrid intent resolution (Redirect/Query).

    Access: authenticated + Premium. Catena: login_required (anonimo → redirect
    login, CTA accesso) POI premium_required (freemium → 403 premium_required, la
    barra AI mostra il CTA upgrade). CSRF enforced (no @csrf_exempt); il JS in
    base.html manda X-CSRFToken. Gating ORTOGONALE all'RBAC. Copre entrambe le
    rotte (matches/urls.py e matches/api_urls.py: stessa funzione decorata).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        body = json.loads(request.body)
        query = body.get('query', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    if not query:
        return JsonResponse({'error': 'Empty query'}, status=400)

    engine = AIStatsEngine()
    result = engine.process_query(query)
    
    return JsonResponse(result)


def api_athlete_detail(request, athlete_id):
    """Returns athlete profile and basic stats in JSON format"""
    athlete = get_object_or_404(User, id=athlete_id, role='athlete')
    profile = getattr(athlete, 'athlete_profile', None)
    
    stats = {
        'total_goals': profile.total_goals if profile else 0,
        'total_matches': profile.total_matches if profile else 0,
        'total_expulsions': profile.total_expulsions if profile else 0,
    }
    
    return JsonResponse({
        'id': athlete.id,
        'full_name': athlete.get_full_name(),
        'role': athlete.role,
        'stats': stats
    })
