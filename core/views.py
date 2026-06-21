import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .services.dashboard_service import DashboardService
from .models import Sport, Society, Team, League
from matches.models import Match, MatchReport
from accounts.models import User
from .forms import SocietySetupForm

logger = logging.getLogger(__name__)

def home(request):
    """Homepage con lista sport e partite filtrate per data"""
    from .utils import get_calendar_dates
    import datetime
    
    sports = Sport.objects.all()
    
    # Gestione Data (default: Oggi)
    today = timezone.now().date()
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
    else:
        selected_date = today
        
    # Genera date per il calendario (centrato sulla data selezionata)
    calendar_dates = get_calendar_dates(center_date=selected_date)
    
    # Filtra partite per la data selezionata (00:00 - 23:59)
    matches = Match.objects.filter(
        match_date__date=selected_date
    ).select_related(
        'home_team__society', 
        'away_team__society', 
        'league'
    ).order_by('match_date')
    
    # --- NEW PREMIUM HOME CONTEXT ---
    # 1. Featured Match: L'ultima partita pubblicata
    featured_match = Match.objects.filter(
        is_finished=True, 
        reports__status=MatchReport.Status.PUBLISHED
    ).select_related('home_team__society', 'away_team__society', 'league').order_by('-match_date').first()
    
    # 2. Featured League: Prendi la prima lega che ha partite e genera classifica
    featured_league_data = None
    featured_league = League.objects.filter(matches__isnull=False).first()
    if featured_league:
        featured_league_data = {
            'league': featured_league,
            'standings': featured_league.get_standings()[:5] # Top 5
        }
    
    # 3. Global Stats: Numeri chiave della piattaforma
    global_stats = {
        'teams_count': Team.objects.count(),
        'athletes_count': User.objects.filter(role='athlete').count(),
        'matches_count': Match.objects.filter(is_finished=True).count(),
    }
    
    from core.services.seo_service import SEOService
    
    return render(request, 'home.html', {
        'sports': sports,
        'upcoming_matches': matches,
        'calendar_dates': calendar_dates,
        'selected_date': selected_date,
        'today': today,
        'featured_match': featured_match,
        'featured_league_data': featured_league_data,
        'global_stats': global_stats,
        'seo_title': f"Risultati e Classifiche del {selected_date.strftime('%d/%m/%Y')}",
        'seo_description': f"Segui i risultati di pallanuoto, volley e altri sport del {selected_date.strftime('%d/%m/%Y')}. Classifiche e tabellini live su 2salti.",
        'structured_data': [
            SEOService.get_website_schema(request),
            SEOService.get_organization_schema(request)
        ]
    })

def sport_detail(request, slug):
    """Dashboard sport con classifica, ultimi risultati e prossime partite per campionato."""
    sport = get_object_or_404(Sport, slug=slug)
    now = timezone.now()

    # Stagione corrente per-sport (Macro 16): default del selettore stagione.
    from core.services.season_service import get_current_season
    season = get_current_season(sport)
    if season:
        current_season = season.label
    else:
        # Fallback bit-identico al vecchio MAX lessicografico finche' Season non
        # e' popolata per questo sport. Isolato nella view: il service non cambia
        # contratto (resta Season | None).
        current_season = (
            sport.leagues.order_by('-season').first().season
            if sport.leagues.exists()
            else ''
        )

    # Macro 3: selettore stagione sulla classifica pubblica. La fonte dati e' la
    # stringa League.season (League e' gia' per-stagione, unique su name+season+
    # group_name); LeagueStanding.season non entra nel filtro perche'
    # get_standings() scopa gia' per lega. Niente FK, niente migration.
    available_seasons = list(
        sport.leagues.values_list('season', flat=True).distinct().order_by('-season')
    )
    requested_season = request.GET.get('season')
    if requested_season in available_seasons:
        selected_season = requested_season
    else:
        # Assente o non valido -> default alla stagione corrente.
        selected_season = current_season

    leagues = sport.leagues.filter(season=selected_season).prefetch_related(
        'matches__home_team__society',
        'matches__away_team__society',
    )

    leagues_data = []
    for league in leagues:
        standings = league.get_standings()[:4]

        last_matches = league.matches.filter(
            is_finished=True,
            reports__status='PUBLISHED',
        ).distinct().order_by('-match_date')[:3]

        next_matches = league.matches.filter(
            match_date__gt=now,
            is_finished=False,
        ).order_by('match_date')[:3]

        if standings or last_matches or next_matches:
            leagues_data.append({
                'league': league,
                'standings': standings,
                'last_matches': last_matches,
                'next_matches': next_matches,
            })

    all_sports = Sport.objects.filter(leagues__isnull=False).distinct().order_by('name')

    from core.services.seo_service import SEOService

    return render(request, 'sport/sport_detail.html', {
        'sport': sport,
        'leagues_data': leagues_data,
        'sport_color': sport.hex_color,
        'all_sports': all_sports,
        'current_season': current_season,
        'available_seasons': available_seasons,
        'selected_season': selected_season,
        'seo_title': f"Campionati e Classifiche {sport.name}",
        'seo_description': f"Tutte le classifiche e i risultati per il mondo {sport.name}. Segui la tua squadra su 2salti.",
        'structured_data': SEOService.get_breadcrumb_schema(request, [(sport.name, request.path)])
    })

@login_required
def create_society(request):
    """Wizard creazione società - solo per presidenti"""
    if request.user.role != 'president':
        return redirect('home')
    
    if request.method == 'POST':
        form = SocietySetupForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    society = form.save()

                    # Collega società al presidente
                    president_profile = request.user.president_profile
                    president_profile.managed_society = society
                    president_profile.save()

                    # Fase 3 (Macro 16): niente più ladder di squadre per categoria —
                    # la categoria vive sulla lega. Si crea la sola prima squadra
                    # (league=None finché non viene iscritta a un campionato).
                    Team.objects.create(society=society)

                    society.setup_completed = True
                    society.save()

                    request.user.setup_completed = True
                    request.user.save()
            except Exception:
                # L'atomic garantisce il rollback di società/team/profilo:
                # nessuna entità orfana resta a DB. Si mostra un errore
                # leggibile e si ri-renderizza la form invece di propagare il 500.
                logger.exception(
                    "create_society failed for user=%s", request.user.pk
                )
                messages.error(
                    request,
                    "Si è verificato un errore durante la creazione della società. "
                    "Riprova o contatta l'amministratore.",
                )
                return render(request, 'societies/society_setup.html', {'form': form})

            return redirect('society_detail', slug=society.slug)
    else:
        form = SocietySetupForm()
    
    return render(request, 'societies/society_setup.html', {'form': form})

def society_detail(request, slug):
    """Pagina società con tutte le squadre"""
    society = get_object_or_404(Society, slug=slug)
    teams = society.teams.all().order_by('name')
    staff = society.get_staff()
    
    return render(request, 'societies/society_detail.html', {
        'society': society,
        'teams': teams,
        'staff': staff,
        'sport_color': society.sport.hex_color,
        'seo_title': f"{society.name} - Società Sportiva",
        'seo_description': f"Tutte le squadre, lo staff e la storia di {society.name}. Scopri i risultati di pallanuoto e volley della società su 2salti.",
    })

from django.db.models import Q
from django.utils import timezone

def team_detail(request, slug):
    """Dettaglio squadra"""
    team = get_object_or_404(Team, slug=slug)
    roster = team.get_roster()
    
    # Prossima partita
    now = timezone.now()
    next_match = Match.objects.filter(
        Q(home_team=team) | Q(away_team=team),
        match_date__gte=now
    ).order_by('match_date').first()
    
    # Ultime 2 partite (Solo pubblicate)
    last_matches = Match.objects.filter(
        Q(home_team=team) | Q(away_team=team),
        match_date__lt=now,
        is_finished=True,
        reports__status=MatchReport.Status.PUBLISHED
    ).distinct().order_by('-match_date')[:2]

    # Altre squadre della stessa società (per navigazione categorie)
    other_teams = Team.objects.filter(society=team.society).exclude(id=team.id).order_by('name')

    # Posizione in classifica
    standing_pos = None
    if team.league:
        standings = team.league.get_standings()
        for i, entry in enumerate(standings):
            if entry['team'].id == team.id:
                standing_pos = i + 1
                break

    from core.services.seo_service import SEOService
    from django.urls import reverse

    context = {
        'team': team,
        'roster': roster,
        'next_match': next_match,
        'last_matches': last_matches,
        'standing_pos': standing_pos,
        'other_teams': other_teams,
        'sport_color': team.league.sport.hex_color if team.league and team.league.sport else team.society.sport.hex_color,
        'seo_title': f"{team.name} - {team.league.name if team.league else team.society.name}",
        'seo_description': f"Dettagli, roster e risultati per {team.name}. Scopri la posizione in classifica e le prossime partite su 2salti.",
        'structured_data': [
            SEOService.get_team_schema(request, team),
            SEOService.get_breadcrumb_schema(request, [
                (team.league.sport.name if team.league and team.league.sport else team.society.sport.name, 
                 reverse('sport_detail', args=[team.league.sport.slug if team.league and team.league.sport else team.society.sport.slug])),
                (team.name, request.path)
            ])
        ]
    }
    return render(request, 'teams/team_detail.html', context)

@login_required
def toggle_follow_team(request, team_id):
    """Aggiunge/Rimuove una squadra dai preferiti dell'utente"""
    team = get_object_or_404(Team, id=team_id)
    
    if team in request.user.favorite_teams.all():
        request.user.favorite_teams.remove(team)
    else:
        request.user.favorite_teams.add(team)
        
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('team_detail', slug=team.slug)

def league_standings(request, league_id):
    """Classifica campionato"""
    league = get_object_or_404(League, id=league_id)
    standings = league.get_standings()
    
    user_team_id = None
    if request.user.is_authenticated:
        # Determina il team dell'utente in base al ruolo
        if request.user.role == 'athlete' and hasattr(request.user, 'athlete_profile'):
             if request.user.athlete_profile.current_team:
                 user_team_id = request.user.athlete_profile.current_team.id
        elif request.user.role == 'coach' and hasattr(request.user, 'coach_profile'):
             if request.user.coach_profile.current_team:
                 user_team_id = request.user.coach_profile.current_team.id

    # Top Scorers Widget
    from matches.stats_services import get_top_scorers
    top_scorers = get_top_scorers(league.id, limit=3)

    from core.services.seo_service import SEOService
    from django.urls import reverse

    context = {
        'league': league,
        'standings': standings,
        'top_scorers': top_scorers,
        'sport': league.sport,
        'sport_color': league.sport.hex_color,
        'user_team_id': user_team_id,
        'seo_title': f"Classifica {league.name} {league.season}",
        'seo_description': f"Classifica aggiornata per {league.name} stagione {league.season}. Punti, vittorie e statistiche squadre su 2salti.",
        'structured_data': SEOService.get_breadcrumb_schema(request, [
            (league.sport.name, reverse('sport_detail', args=[league.sport.slug])),
            (f"Classifica {league.name}", request.path)
        ])
    }
    
    return render(request, 'leagues/league_standings.html', context)

@login_required
def dashboard_me(request):
    """
    Endpoint API per la dashboard personale dell'utente loggato.
    GET /api/dashboard/me
    """
    data = DashboardService.get_dashboard_data(request.user)
    return JsonResponse(data)
