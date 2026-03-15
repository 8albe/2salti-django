from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import SignUpForm, UserSetupForm, AthleteSetupForm, CoachSetupForm, RefereeSetupForm, FanSetupForm
from .models import User
from matches.models import Match
from django.db import models

def signup(request):
    """Registrazione con scelta ruolo"""
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('setup_wizard')  # Reindirizza al wizard
    else:
        form = SignUpForm()
    
    return render(request, 'accounts/signup.html', {'form': form})


@login_required
def setup_wizard(request):
    """Wizard post-registrazione - personalizzato per ruolo"""
    user = request.user
    
    # Se già completato, vai al profilo
    if user.setup_completed:
        return redirect('profile', username=user.username)
    
    # Form diverso in base al ruolo
    profile = None
    FormClass = None

    if user.role == 'athlete':
        profile = user.athlete_profile
        FormClass = AthleteSetupForm
    elif user.role == 'coach':
        profile = user.coach_profile
        FormClass = CoachSetupForm
    elif user.role == 'referee':
        profile = user.referee_profile
        FormClass = RefereeSetupForm
    elif user.role == 'president':
        # Il presidente deve creare la società
        return redirect('create_society')
    else:  # fan
        FormClass = FanSetupForm
    
    if request.method == 'POST':
        form = FormClass(request.POST, request.FILES, instance=profile) if profile else FormClass(request.POST, request.FILES)
        user_form = UserSetupForm(request.POST, request.FILES, instance=user)
        
        if form.is_valid() and user_form.is_valid():
            user_form.save()
            if profile:
                form.save()
            # Per i fan, salvare preferenze
            if user.role == 'fan':
                from core.models import Team
                team_id = request.POST.get('favorite_team')
                if team_id:
                    try:
                        team = Team.objects.get(id=team_id)
                        user.favorite_teams.set([team])
                    except Team.DoesNotExist:
                        pass
                player_id = request.POST.get('favorite_player_id')
                if player_id:
                    try:
                        player = User.objects.get(id=player_id, role='athlete')
                        user.favorite_players.set([player])
                    except User.DoesNotExist:
                        pass
            user.setup_completed = True
            user.save()
            return redirect('profile', username=user.username)
    else:
        initial_data = {}
        if user.role == 'fan':
            fav_team = user.favorite_teams.first()
            fav_player = user.favorite_players.first()
            if fav_team:
                initial_data['league'] = fav_team.league_id
                initial_data['favorite_team'] = fav_team.id
            if fav_player:
                initial_data['favorite_player_id'] = fav_player.id
                initial_data['athlete_search'] = fav_player.get_full_name()
        
        form = FormClass(instance=profile, initial=initial_data) if profile else FormClass(initial=initial_data)
        user_form = UserSetupForm(instance=user)
    
    return render(request, 'accounts/setup_wizard.html', {
        'form': form,
        'user_form': user_form,
        'role': user.get_role_display()
    })

@login_required
def profile_redirect(request):
    """Reindirizza l'utente loggato al proprio profilo"""
    return redirect('profile', username=request.user.username)


@login_required
def edit_profile(request):
    """Modifica dati profilo - sempre accessibile anche dopo il setup iniziale"""
    user = request.user

    profile = None
    FormClass = None

    if user.role == 'athlete':
        profile = user.athlete_profile
        FormClass = AthleteSetupForm
    elif user.role == 'coach':
        profile = user.coach_profile
        FormClass = CoachSetupForm
    elif user.role == 'referee':
        profile = user.referee_profile
        FormClass = RefereeSetupForm
    elif user.role == 'president':
        return redirect('create_society')
    else:  # fan
        FormClass = FanSetupForm

    if request.method == 'POST':
        form = FormClass(request.POST, request.FILES, instance=profile) if profile else FormClass(request.POST, request.FILES)
        user_form = UserSetupForm(request.POST, request.FILES, instance=user)

        if form.is_valid() and user_form.is_valid():
            user_form.save()
            if profile:
                form.save()
            # Per i fan, salvare preferenze
            if user.role == 'fan':
                from core.models import Team
                team_id = request.POST.get('favorite_team')
                if team_id:
                    try:
                        team = Team.objects.get(id=team_id)
                        user.favorite_teams.set([team])
                    except Team.DoesNotExist:
                        pass
                player_id = request.POST.get('favorite_player_id')
                if player_id:
                    try:
                        player = User.objects.get(id=player_id, role='athlete')
                        user.favorite_players.set([player])
                    except User.DoesNotExist:
                        pass
            user.save()
            return redirect('profile', username=user.username)
    else:
        initial_data = {}
        if user.role == 'fan':
            fav_team = user.favorite_teams.first()
            fav_player = user.favorite_players.first()
            if fav_team:
                initial_data['league'] = fav_team.league_id
                initial_data['favorite_team'] = fav_team.id
            if fav_player:
                initial_data['favorite_player_id'] = fav_player.id
                initial_data['athlete_search'] = fav_player.get_full_name()

        form = FormClass(instance=profile, initial=initial_data) if profile else FormClass(initial=initial_data)
        user_form = UserSetupForm(instance=user)

    return render(request, 'accounts/setup_wizard.html', {
        'form': form,
        'user_form': user_form,
        'role': user.get_role_display(),
        'editing': True,
    })

def profile(request, username):
    """Pagina profilo utente - adattata per ruolo"""
    user = get_object_or_404(User.objects.select_related(
        'athlete_profile',
        'coach_profile',
        'referee_profile',
        'president_profile'
    ), username=username)
    
    context = {'profile_user': user}
    
    # Dati specifici per ruolo
    if user.role == 'athlete':
        profile = user.athlete_profile
        matches = Match.objects.filter(
            events__player=user
        ).distinct().order_by('-match_date')[:10]
        
        context.update({
            'athlete_profile': profile,
            'recent_matches': matches,
        })
        
        if profile.current_team:
             context['current_team'] = profile.current_team
             context['league'] = profile.current_team.league
             context['league_standings'] = profile.current_team.league.get_standings()
    
    elif user.role == 'coach':
        profile = user.coach_profile
        context['coach_profile'] = profile
        
        if profile.current_team:
            matches = Match.objects.filter(
                models.Q(home_team=profile.current_team) | 
                models.Q(away_team=profile.current_team)
            ).order_by('-match_date')[:10]
            context['team_matches'] = matches
            context['current_team'] = profile.current_team
            context['league'] = profile.current_team.league
            context['league_standings'] = profile.current_team.league.get_standings()
    
    elif user.role == 'referee':
        profile = user.referee_profile
        matches = Match.objects.filter(
            referees=user
        ).order_by('-match_date')[:10]
        context['officiated_matches'] = matches
        context['referee_profile'] = profile
    
    elif user.role == 'president':
        profile = user.president_profile
        if profile.managed_society:
            context['society'] = profile.managed_society
            context['president_profile'] = profile
    
    elif user.role == 'fan':
        # Atleti seguiti con le loro statistiche
        fan_athletes = []
        for athlete_user in user.favorite_players.filter(role='athlete'):
            try:
                ap = athlete_user.athlete_profile
                fan_athletes.append({
                    'user': athlete_user,
                    'profile': ap,
                })
            except Exception:
                pass
        context['fan_athletes'] = fan_athletes

        # Squadre seguite con classifica e prossima partita
        from django.utils import timezone
        now = timezone.now()
        fan_teams_data = []
        for team in user.favorite_teams.all().select_related('league', 'society'):
            next_match = Match.objects.filter(
                models.Q(home_team=team) | models.Q(away_team=team),
                match_date__gte=now
            ).order_by('match_date').first()
            standings = team.league.get_standings() if team.league else []
            fan_teams_data.append({
                'team': team,
                'next_match': next_match,
                'standings': standings,
                'league': team.league,
            })
        context['fan_teams_data'] = fan_teams_data
    
    # Storico stagioni
    from seasons.models import SeasonArchive
    archives = SeasonArchive.objects.filter(athlete=user).order_by('-season')
    context['season_archives'] = archives
    
    return render(request, 'accounts/profile.html', context)


# ======================
# ENDPOINT AJAX
# ======================

from django.http import JsonResponse

def api_teams_by_league(request):
    """Restituisce le squadre di un campionato (usato dal form fan)"""
    league_id = request.GET.get('league_id')
    if not league_id:
        return JsonResponse([], safe=False)
    from core.models import Team
    teams = Team.objects.filter(league_id=league_id).select_related('society').order_by('name')
    data = [{'id': t.id, 'name': t.name} for t in teams]
    return JsonResponse(data, safe=False)


def api_search_athlete(request):
    """Cerca atleti per nome/cognome (usato dal form fan)"""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)
    from django.db.models import Q, Value
    from django.db.models.functions import Concat
    athletes = User.objects.filter(role='athlete').filter(
        Q(first_name__icontains=q) | Q(last_name__icontains=q) |
        Q(username__icontains=q)
    ).select_related('athlete_profile__current_team')[:10]
    data = []
    for a in athletes:
        team_name = ''
        try:
            if a.athlete_profile.current_team:
                team_name = a.athlete_profile.current_team.name
        except Exception:
            pass
        data.append({
            'id': a.id,
            'full_name': a.get_full_name() or a.username,
            'team': team_name,
        })
    return JsonResponse(data, safe=False)

