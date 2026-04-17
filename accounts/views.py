from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import SignUpForm, UserSetupForm, AthleteSetupForm, CoachSetupForm, RefereeSetupForm, FanSetupForm
from .models import User
from matches.models import Match, MatchReport
from django.db import models

def signup(request):
    """Registrazione con scelta ruolo"""
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('verify_identity')  # Nuovo flusso: prima l'identità
    else:
        form = SignUpForm()
    
    return render(request, 'accounts/signup.html', {
        'form': form,
        'seo_title': "Registrati | 2salti",
        'seo_description': "Crea il tuo profilo su 2salti. La piattaforma per atleti, coach e appassionati di sport.",
    })


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
        try:
            profile = user.athlete_profile
            FormClass = AthleteSetupForm
        except:
            return redirect('claim_profile')
    elif user.role == 'coach':
        try:
            profile = user.coach_profile
            FormClass = CoachSetupForm
        except:
            return redirect('claim_profile')
    elif user.role == 'referee':
        try:
            profile = user.referee_profile
            FormClass = RefereeSetupForm
        except:
            return redirect('claim_profile')
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
            
            from management.utils import log_action
            log_action(user, None, "ONBOARDING_SETUP_COMPLETED", details={"role": user.role})
            
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
        'seo_title': f"Configura Profilo {user.get_role_display()} | 2salti",
    })

@login_required
def verify_identity(request):
    """Fase 2: Verifica Identità (Mock SPID/CIE)"""
    user = request.user
    if user.identity_status == 'VERIFIED':
        return redirect('process_payment')
    
    if request.method == 'POST':
        # Mocking verification success
        import django.utils.timezone as timezone
        from django.contrib import messages
        
        user.identity_status = 'VERIFIED'
        user.identity_verified_at = timezone.now()
        user.save()
        
        from management.utils import log_action
        log_action(user, None, "ONBOARDING_IDENTITY_VERIFIED", details={"method": "MOCK_SPID"}, request=request)
        
        messages.success(request, "Identità verificata con successo tramite SPID. Benvenuto!")
        return redirect('process_payment')
        
    return render(request, 'accounts/onboarding/verify_identity.html', {
        'seo_title': "Verifica Identità SPID/CIE | 2salti",
        'seo_description': "Procedura sicura di verifica identità digitale per l'accesso alla piattaforma 2salti.",
    })


@login_required
def process_payment(request):
    """Fase 3: Pagamento (Mock 0,50€)"""
    user = request.user
    
    # Se è un fan o ha già pagato, passa oltre
    if user.role == 'fan' or user.subscription_status == 'ACTIVE':
        return redirect('setup_wizard')
    
    if request.method == 'POST':
        # Mocking payment success
        import django.utils.timezone as timezone
        from django.contrib import messages
        
        user.subscription_status = 'ACTIVE'
        user.subscription_end_date = timezone.now() + timezone.timedelta(days=365)
        user.save()
        
        from management.utils import log_action
        log_action(user, None, "ONBOARDING_PAYMENT_COMPLETED", details={"amount": "0.50", "currency": "EUR"}, request=request)
        
        messages.success(request, "Abbonamento attivato con successo! Il tuo profilo 2salti PRO è ora attivo per 12 mesi.")
        return redirect('setup_wizard')
        
    return render(request, 'accounts/onboarding/payment.html', {
        'seo_title': "Attivazione Profilo PRO | 2salti",
        'seo_description': "Sostieni la piattaforma e sblocca tutte le funzionalità avanzate di 2salti.",
    })

@login_required
def onboarding_membership(request):
    """Fase 5: Associazione Team / Società (Activation Code o Membership Request)"""
    user = request.user
    
    # Se ha già una membership attiva o un claim approvato/pendente, può passare oltre
    if user.memberships.filter(is_active=True).exists() or user.profile_links.filter(status__in=['PENDING', 'APPROVED']).exists():
        return redirect('dashboard')
    
    # Se è un fan, questo step è opzionale o saltabile
    if user.role == 'fan':
        return redirect('dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        
        # 1. Uso di Activation Code
        activation_code = request.POST.get('activation_code')
        if activation_code:
            from management.models import ActivationCode, Membership
            try:
                code_obj = ActivationCode.objects.get(code=activation_code, is_active=True)
                # Verifica usi
                if code_obj.current_uses < code_obj.max_uses:
                    # Crea Membership
                    Membership.objects.create(
                        user=user,
                        society=code_obj.society,
                        team=code_obj.team,
                        role=code_obj.role,
                        is_active=True
                    )
                    code_obj.current_uses += 1
                    code_obj.save()
                    
                    from management.utils import log_action
                    log_action(user, code_obj.society, "ONBOARDING_MEMBERSHIP_CODE_REDEEMED", target=code_obj, request=request)
                    
                    import django.contrib.messages as messages
                    messages.success(request, f"Benvenuto in {code_obj.society.name}!")
                    return redirect('dashboard')
                else:
                    import django.contrib.messages as messages
                    messages.error(request, "Questo codice ha esaurito gli utilizzi disponibili.")
            except ActivationCode.DoesNotExist:
                import django.contrib.messages as messages
                messages.error(request, "Codice di attivazione non valido o scaduto.")

        # 2. Richiesta manuale (senza codice)
        team_id = request.POST.get('team_id')
        if team_id:
            from core.models import Team
            from management.models import MembershipRequest
            try:
                team = Team.objects.get(id=team_id)
                # Determina il ruolo in base al tipo di utente
                role = 'PLAYER' if user.role == 'athlete' else 'HEAD_COACH'
                
                # Crea richiesta
                mr, created = MembershipRequest.objects.get_or_create(
                    user=user,
                    society=team.society,
                    team=team,
                    role=role,
                    defaults={'status': 'PENDING'}
                )
                
                from management.utils import log_action
                log_action(user, team.society, "ONBOARDING_MEMBERSHIP_REQUESTED", target=team, request=request)
                
                import django.contrib.messages as messages
                messages.success(request, f"Richiesta inviata alla società {team.society.name}. Ti avviseremo appena sarai approvato.")
                return redirect('dashboard')
            except Team.DoesNotExist:
                import django.contrib.messages as messages
                messages.error(request, "Squadra non trovata.")

    return render(request, 'accounts/onboarding/membership.html', {
        'role': user.get_role_display(),
        'seo_title': "Associa il tuo Profilo | 2salti",
    })


@login_required
def claim_profile(request):
    """Fase 4: Ricerca e Claim del proprio Profilo Sportivo"""
    user = request.user
    
    # Se ha già un profilo o un claim in attesa/approvato
    if user.profile_links.filter(status__in=['PENDING', 'APPROVED']).exists():
        return redirect('team_access')
        
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'skip':
            return redirect('team_access')
            
        profile_id = request.POST.get('profile_id')
        role = request.POST.get('role')
        
        if profile_id and role:
            from .models import AccountProfileLink, AthleteProfile, CoachProfile, RefereeProfile
            link = AccountProfileLink(user=user, status='PENDING')
            try:
                if role == 'athlete':
                    link.athlete_profile = AthleteProfile.objects.get(id=profile_id)
                elif role == 'coach':
                    link.coach_profile = CoachProfile.objects.get(id=profile_id)
                elif role == 'referee':
                    link.referee_profile = RefereeProfile.objects.get(id=profile_id)
                link.save()
                import django.contrib.messages as messages
                messages.success(request, "Richiesta di claim inviata con successo. In attesa di approvazione.")
                return redirect('team_access')
            except Exception as e:
                import django.contrib.messages as messages
                messages.error(request, "Errore durante la richiesta di claim.")
                
    return render(request, 'accounts/onboarding/claim_profile.html', {
        'role': user.role,
        'seo_title': "Rivendica il tuo Profilo | 2salti",
    })


@login_required
def dashboard(request):
    """Hub centrale per l'utente loggato"""
    user = request.user
    context = {
        'user': user,
        'title': 'La tua Dashboard',
        # Recupero info profilo per riepilogo
        'has_profile': hasattr(user, 'athlete_profile') or hasattr(user, 'coach_profile'),
    }
    
    # Squadre seguite
    context['followed_teams'] = user.favorite_teams.all().select_related('society', 'league')
    
    # Se atleta, aggiungi statistiche e squadra attuale
    if hasattr(user, 'athlete_profile'):
        context['athlete_profile'] = user.athlete_profile
        context['current_team'] = user.athlete_profile.current_team
        
    return render(request, 'accounts/dashboard.html', context)


@login_required
def profile_redirect(request):
    """Reindirizza l'utente loggato alla propria dashboard"""
    return redirect('dashboard')


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
    
    context = {
        'profile_user': user,
        'seo_title': f"Profilo {user.get_full_name() or user.username} | 2salti",
        'seo_description': f"Statistiche, squadra e risultati recenti di {user.get_full_name() or user.username}. Scopri il profilo completo dell'atleta su 2salti.",
    }
    
    # Dati specifici per ruolo
    if user.role == 'athlete':
        profile = user.athlete_profile
        matches = Match.objects.filter(
            events__player=user,
            reports__status=MatchReport.Status.PUBLISHED
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
    
    # Inietta Structured Data
    from core.services.seo_service import SEOService
    from django.urls import reverse
    
    sd = [SEOService.get_user_schema(request, user)]
    bc_items = [("Atleti", reverse('home'))] # Fallback
    if user.role == 'athlete' and hasattr(user, 'athlete_profile') and user.athlete_profile.current_team:
        team = user.athlete_profile.current_team
        if team.league and team.league.sport:
            bc_items = [
                (team.league.sport.name, reverse('sport_detail', args=[team.league.sport.slug])),
                (team.name, reverse('team_detail', args=[team.slug]))
            ]
    bc_items.append((user.get_full_name() or user.username, request.path))
    sd.append(SEOService.get_breadcrumb_schema(request, bc_items))
    
    context['structured_data'] = sd
    
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


@login_required
def api_search_profile_claim(request):
    from django.http import JsonResponse
    from .models import AthleteProfile, CoachProfile, RefereeProfile
    
    query = request.GET.get('q', '').strip()
    role = request.GET.get('role', 'athlete')
    
    if len(query) < 2:
        return JsonResponse({'results': []})
        
    results = []
    if role == 'athlete':
        from django.db.models import Q
        profiles = AthleteProfile.objects.filter(
            Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(user__username__icontains=query)
        ).select_related('user', 'current_team')[:10]
        
        for p in profiles:
            team_name = p.current_team.name if p.current_team else "Svincolato"
            results.append({
                'id': p.id,
                'name': p.user.get_full_name() or p.user.username,
                'info': team_name
            })
    elif role == 'coach':
        from django.db.models import Q
        profiles = CoachProfile.objects.filter(
            Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(user__username__icontains=query)
        ).select_related('user', 'current_team')[:10]
        
        for p in profiles:
            team_name = p.current_team.name if p.current_team else "Svincolato"
            results.append({
                'id': p.id,
                'name': p.user.get_full_name() or p.user.username,
                'info': team_name
            })
    elif role == 'referee':
        from django.db.models import Q
        profiles = RefereeProfile.objects.filter(
            Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(user__username__icontains=query)
        ).select_related('user')[:10]
        
        for p in profiles:
            results.append({
                'id': p.id,
                'name': p.user.get_full_name() or p.user.username,
                'info': f"Licenza: {p.get_license_level_display()}"
            })
            
    return JsonResponse({'results': results})
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

