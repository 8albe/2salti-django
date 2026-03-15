from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Sport, Society, Team, League
from .forms import SocietySetupForm

def home(request):
    """Homepage con lista sport e partite filtrate per data"""
    from django.utils import timezone
    from matches.models import Match
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
    # Match.match_date è DateTimeField, quindi usiamo __date
    matches = Match.objects.filter(
        match_date__date=selected_date
    ).select_related(
        'home_team__society', 
        'away_team__society', 
        'league'
    ).order_by('match_date')
    
    return render(request, 'home.html', {
        'sports': sports,
        'upcoming_matches': matches, # Rinominato per coerenza nel template (anche se sono di oggi)
        'calendar_dates': calendar_dates,
        'selected_date': selected_date,
        'today': today,
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
            
    return render(request, 'sport/sport_detail.html', {
        'sport': sport, 
        'leagues_data': leagues_data,
        'sport_color': sport.hex_color
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
    })

from django.db.models import Q
from django.utils import timezone
from matches.models import Match

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
    
    # Ultime 2 partite
    last_matches = Match.objects.filter(
        Q(home_team=team) | Q(away_team=team),
        match_date__lt=now,
        is_finished=True 
    ).order_by('-match_date')[:2]

    # Altre squadre della stessa società (per navigazione categorie)
    other_teams = Team.objects.filter(society=team.society).exclude(id=team.id).order_by('category')

    return render(request, 'teams/team_detail.html', {
        'team': team,
        'roster': roster,
        'sport': team.society.sport,
        'sport_color': team.society.sport.hex_color,
        'next_match': next_match,
        'last_matches': last_matches,
        'other_teams': other_teams,
    })

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

    context = {
        'league': league,
        'standings': standings,
        'top_scorers': top_scorers,
        'sport': league.sport,
        'sport_color': league.sport.hex_color,
        'user_team_id': user_team_id,
    }
    
    return render(request, 'leagues/league_standings.html', context)
