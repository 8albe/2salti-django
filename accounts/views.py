from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import SignUpForm, UserSetupForm, AthleteSetupForm, CoachSetupForm, RefereeSetupForm, FanSetupForm
from .models import User
from matches.models import Match, MatchReport
from management.models import Membership
from django.db import models


def _followed_players_for(user):
    """Lista atleti seguiti (multi-follow Macro 7a) per pre-popolare i chip nel
    form fan. Ritorna dict {id, full_name} ordinati per cognome/nome."""
    return [
        {'id': p.id, 'full_name': p.get_full_name() or p.username}
        for p in user.favorite_players.filter(role='athlete').order_by('last_name', 'first_name')
    ]


def signup(request):
    """Registrazione con scelta ruolo"""
    if request.method == 'POST':
        from django.contrib import messages
        from accounts.services.signup_throttle import is_throttled, record_attempt

        if is_throttled(request):
            messages.warning(request, "Troppi tentativi di registrazione. Riprova tra qualche minuto.")
            return render(request, 'accounts/signup.html', {
                'form': SignUpForm(),
                'seo_title': "Registrati | 2salti",
                'seo_description': "Crea il tuo profilo su 2salti. La piattaforma per atleti, coach e appassionati di sport.",
            })
        record_attempt(request)

        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)

            from accounts.services.email_verification import send_verification_email
            send_verification_email(user, request=request)

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
        # Macro 18: il presidente NON crea da zero — sceglie la società da una
        # lista e richiede l'accesso (create_society resta come rifinitura post
        # approvazione, raggiunta da choose_society).
        return redirect('choose_society')
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
                # Multi-follow (Macro 7a): il form invia N hidden favorite_player_id;
                # .set sull'intero insieme selezionato supporta sia l'aggiunta di
                # più atleti/figli sia la rimozione, ed è idempotente.
                player_ids = request.POST.getlist('favorite_player_id')
                players = list(User.objects.filter(id__in=player_ids, role='athlete'))
                user.favorite_players.set(players)
            user.setup_completed = True
            user.save()
            
            from management.utils import log_action
            log_action(user, None, "ONBOARDING_SETUP_COMPLETED", details={"role": user.role})
            
            return redirect('profile', username=user.username)
    else:
        initial_data = {}
        if user.role == 'fan':
            fav_team = user.favorite_teams.first()
            if fav_team:
                initial_data['league'] = fav_team.league_id
                initial_data['favorite_team'] = fav_team.id

        form = FormClass(instance=profile, initial=initial_data) if profile else FormClass(initial=initial_data)
        user_form = UserSetupForm(instance=user)

    return render(request, 'accounts/setup_wizard.html', {
        'form': form,
        'user_form': user_form,
        'role': user.get_role_display(),
        'followed_players': _followed_players_for(user) if user.role == 'fan' else [],
        'seo_title': f"Configura Profilo {user.get_role_display()} | 2salti",
    })

@login_required
def verify_identity(request):
    """Fase 2: Verifica Identità — conferma email a click. Mostra "controlla
    la tua casella" e permette il reinvio del link."""
    user = request.user
    if user.identity_status == 'VERIFIED':
        return redirect('setup_wizard')

    if request.method == 'POST':
        from django.contrib import messages
        from django.utils import timezone
        from accounts.services.email_verification import (
            send_verification_email,
            EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS,
        )

        now_ts = timezone.now().timestamp()
        last_sent = request.session.get('verify_email_last_sent')
        elapsed = now_ts - last_sent if last_sent is not None else None

        if elapsed is not None and elapsed < EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS:
            remaining = int(EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS - elapsed)
            messages.warning(request, f"Attendi ancora {remaining} secondi prima di richiedere un nuovo invio.")
            return redirect('verify_identity')

        sent = send_verification_email(user, request=request)
        if sent:
            request.session['verify_email_last_sent'] = now_ts
            messages.success(request, f"Email di conferma inviata a {user.email}.")
        else:
            messages.error(request, "Invio email non riuscito. Riprova più tardi.")
        return redirect('verify_identity')

    return render(request, 'accounts/onboarding/verify_identity.html', {
        'seo_title': "Verifica il tuo indirizzo email | 2salti",
        'seo_description': "Conferma il tuo indirizzo email per completare la registrazione su 2salti.",
    })


def verify_email(request, token):
    """Endpoint pubblico: click sul link ricevuto via email. Nessun login
    richiesto. Token valido → identity_status=VERIFIED (idempotente se già
    verificato); scaduto/manomesso → pagina d'errore con link al reinvio."""
    from accounts.services.email_verification import verify_token

    ok, user, error = verify_token(token)

    if not ok:
        return render(request, 'accounts/onboarding/verify_email_result.html', {
            'ok': False,
            'error': error,
            'seo_title': "Verifica email non riuscita | 2salti",
        }, status=400)

    if user.identity_status != 'VERIFIED':
        import django.utils.timezone as timezone
        from management.utils import log_action

        user.identity_status = 'VERIFIED'
        user.identity_verified_at = timezone.now()
        user.save(update_fields=['identity_status', 'identity_verified_at'])

        log_action(user, None, "ONBOARDING_IDENTITY_VERIFIED", details={"method": "EMAIL_CLICK"}, request=request)

    return render(request, 'accounts/onboarding/verify_email_result.html', {
        'ok': True,
        'seo_title': "Email verificata | 2salti",
    })


@login_required
def process_payment(request):
    """Step pagamento onboarding: differito a Macro 10 pagamenti reali.

    Non più uno step del funnel (vedi User.onboarding_state); la view resta
    solo per non rompere link/bookmark esistenti verso /accounts/payment/ e
    redirige incondizionatamente al passo successivo.
    """
    return redirect('setup_wizard')

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
        from django.contrib import messages
        from management.services.membership_enrollment import (
            redeem_activation_code,
            request_manual_membership,
        )

        activation_code = request.POST.get('activation_code')
        if activation_code:
            ok, membership, err = redeem_activation_code(user, activation_code, request=request)
            if ok:
                messages.success(request, f"Benvenuto in {membership.society.name}!")
                return redirect('dashboard')
            messages.error(request, err)

        team_id = request.POST.get('team_id')
        if team_id:
            ok, mr, err = request_manual_membership(user, team_id, request=request)
            if ok:
                messages.success(
                    request,
                    f"Richiesta inviata alla società {mr.society.name}. Ti avviseremo appena sarai approvato.",
                )
                return redirect('dashboard')
            messages.error(request, err)

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
        # Macro 18: landing presidente -> scegli società + richiedi accesso.
        return redirect('choose_society')
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
                # Multi-follow (Macro 7a): vedi setup_wizard.
                player_ids = request.POST.getlist('favorite_player_id')
                players = list(User.objects.filter(id__in=player_ids, role='athlete'))
                user.favorite_players.set(players)
            user.save()
            return redirect('profile', username=user.username)
    else:
        initial_data = {}
        if user.role == 'fan':
            fav_team = user.favorite_teams.first()
            if fav_team:
                initial_data['league'] = fav_team.league_id
                initial_data['favorite_team'] = fav_team.id

        form = FormClass(instance=profile, initial=initial_data) if profile else FormClass(initial=initial_data)
        user_form = UserSetupForm(instance=user)

    return render(request, 'accounts/setup_wizard.html', {
        'form': form,
        'user_form': user_form,
        'role': user.get_role_display(),
        'followed_players': _followed_players_for(user) if user.role == 'fan' else [],
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

        # Storico squadre PLAYER (ordinato per stagione più recente, label
        # canonica AAAA/AAAA lessicograficamente ordinabile; season NULL in
        # coda; tie-breaker created_at)
        player_memberships = Membership.objects.filter(
            user=user,
            role='PLAYER'
        ).select_related('team', 'team__society', 'team__league', 'season').order_by(
            models.F('season__label').desc(nulls_last=True), '-created_at')
        context['player_memberships'] = player_memberships

        # Stat stagione corrente (workaround senza Season autonomo)
        # Stagione calcistica: 1 settembre → 31 agosto, ancorata a Europe/Rome
        from django.utils import timezone
        from datetime import datetime
        from matches.models import MatchEvent

        now = timezone.now()
        season_year = now.year if now.month >= 9 else now.year - 1
        season_start = timezone.make_aware(datetime(season_year, 9, 1))

        season_goals = MatchEvent.objects.filter(
            player=user,
            event_type='GOAL',
            match__match_date__gte=season_start,
            match__reports__status=MatchReport.Status.PUBLISHED
        ).count()

        season_matches = Match.objects.filter(
            events__player=user,
            match_date__gte=season_start,
            reports__status=MatchReport.Status.PUBLISHED
        ).distinct().count()

        context['season_goals'] = season_goals
        context['season_matches'] = season_matches

        if profile.current_team:
             context['current_team'] = profile.current_team
             context['league'] = profile.current_team.league
             context['league_standings'] = profile.current_team.league.get_standings()
             # Sponsor del club (forma ridotta): stessi sponsor della società
             # dell'atleta per la stagione corrente; degrada a vuoto.
             from core.services.sponsor_service import get_society_sponsors
             context['club_sponsors'] = get_society_sponsors(profile.current_team.society)

    elif user.role == 'coach':
        profile = user.coach_profile
        context['coach_profile'] = profile

        # Storico Allenatori: mostra tutte le Membership HEAD_COACH (incluse
        # quelle con season=None, per non nascondere record legacy/anomali);
        # ordina per stagione più recente (label canonica, NULL in coda).
        # Materializza in lista per riusarla nel loop tenure_q senza doppia query.
        coached_memberships_list = list(
            Membership.objects.filter(
                user=user,
                role='HEAD_COACH'
            ).select_related('team', 'team__society', 'team__league', 'season').order_by(
                models.F('season__label').desc(nulls_last=True), '-created_at')
        )
        context['coached_memberships'] = coached_memberships_list

        # direct_matches: partite dirette dal coach. Modello β-stagione (Macro 16
        # §16.3, fetta 2d-3): per ogni Membership HEAD_COACH con season nota,
        # attribuisci TUTTE le partite della squadra in quella stagione, senza
        # bound start_date/end_date. La stagione del match si deriva dalla catena
        # Match -> league -> league.season_fk. Record con season=None vengono
        # ignorati (ramo difensivo coerente con resolve_membership_season di 2d-1);
        # match con league.season_fk=None non eguagliano alcun season_id valorizzato
        # e cadono fuori senza crash. Nessuna disambiguazione "coach finale": il
        # cambio-coach è nota libera, quindi si attribuisce a tutti i record
        # HEAD_COACH di quella (team, season).
        season_tenures = [m for m in coached_memberships_list if m.season_id is not None]
        direct_matches = None
        if season_tenures:
            attr_q = models.Q()
            for mem in season_tenures:
                team_q = models.Q(home_team_id=mem.team_id) | models.Q(away_team_id=mem.team_id)
                attr_q |= (team_q & models.Q(league__season_fk_id=mem.season_id))
            direct_matches = Match.objects.filter(attr_q).order_by('-match_date')[:10]
            context['direct_matches'] = direct_matches

        if profile.current_team:
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
    
    # Template personalizzato per Atleta (Premium)
    if user.role == 'athlete':
        return render(request, 'accounts/athlete_profile.html', context)
        
    return render(request, 'accounts/profile.html', context)


@login_required
def request_certification(request):
    """Vista genitore (role='fan'): dichiara un figlio (atleta già nel sistema)
    e avvia la certificazione society-vouching (Macro 7b). Riusa la ricerca
    atleti di api_search_athlete per selezionare il figlio."""
    from django.contrib import messages

    user = request.user
    if user.role != 'fan':
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    if request.method == 'POST':
        from management.services.certification_service import request_certification as svc_request
        child_id = request.POST.get('child_id')
        child = User.objects.filter(id=child_id, role='athlete').first() if child_id else None
        ok, cert, err = svc_request(user, child)
        if ok:
            messages.success(
                request,
                "Richiesta inviata alla società. Riceverai un'email con il link "
                "di conferma appena la società verificherà i tuoi dati.",
            )
            return redirect('profile', username=user.username)
        messages.error(request, err or "Impossibile inviare la richiesta.")

    # Certificazioni già in corso/concluse per questo genitore
    from management.models import ParentCertification
    certifications = ParentCertification.objects.filter(parent=user).select_related('child', 'society')

    return render(request, 'accounts/request_certification.html', {
        'certifications': certifications,
        'seo_title': "Certificazione Genitore | 2salti",
    })


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

