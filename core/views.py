from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .services.dashboard_service import DashboardService
from .models import Sport, Society, Team, League
from matches.models import Match, MatchReport
from accounts.models import User
from .forms import SocietySetupForm

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
    """Dashboard sport con calendario"""
    sport = get_object_or_404(Sport, slug=slug)
    
    # Raggruppa campionati e relative partite recenti
    leagues = sport.leagues.all().prefetch_related(
        'matches__home_team__society',
        'matches__away_team__society'
    )
    
    leagues_data = []
    for league in leagues:
        # Find the next matchday (first match in future + 4 days window)
        from django.utils import timezone
        import datetime
        now = timezone.now()
        
        # 1. Trova la prima partita futura
        next_match = league.matches.filter(match_date__gte=now).order_by('match_date').first()
        
        matches = []
        if next_match:
            # 2. Definisci il range del "turno" (es. Venerdì -> Lunedì = 4 giorni)
            start_date = next_match.match_date.date()
            end_date = start_date + datetime.timedelta(days=4)
            
            # 3. Prendi tutte le partite in quel range
            matches = league.matches.filter(
                match_date__date__range=[start_date, end_date]
            ).order_by('match_date')
        else:
            # Fallback: Se non ci sono partite future, mostra le ultime giocate (ultima giornata)
            last_match = league.matches.filter(match_date__lt=now).order_by('-match_date').first()
            if last_match:
                 end_date = last_match.match_date.date()
                 start_date = end_date - datetime.timedelta(days=4)
                 matches = league.matches.filter(
                    match_date__date__range=[start_date, end_date]
                ).order_by('match_date')

        if matches:
            leagues_data.append({
                'league': league,
                'matches': matches
            })
            
    from core.services.seo_service import SEOService
    
    return render(request, 'sport/sport_detail.html', {
        'sport': sport, 
        'leagues_data': leagues_data,
        'sport_color': sport.hex_color,
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
            society = form.save()
            
            # Collega società al presidente
            president_profile = request.user.president_profile
            president_profile.managed_society = society
            president_profile.save()
            
            # Crea automaticamente tutte le squadre (categorie)
            for category_code, category_name in Team.CATEGORY_CHOICES:
                Team.objects.create(
                    society=society,
                    category=category_code
                )
            
            society.setup_completed = True
            society.save()
            
            request.user.setup_completed = True
            request.user.save()
            
            return redirect('society_detail', slug=society.slug)
    else:
        form = SocietySetupForm()
    
    return render(request, 'societies/society_setup.html', {'form': form})

def society_detail(request, slug):
    """Pagina società con tutte le squadre"""
    society = get_object_or_404(Society, slug=slug)
    teams = society.teams.all().order_by('category')
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
    other_teams = Team.objects.filter(society=team.society).exclude(id=team.id).order_by('category')

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
        'seo_title': f"{team.name} - {team.league.name if team.league else team.get_category_display()}",
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
