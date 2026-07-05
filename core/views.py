import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction
from django.db.models import BooleanField, Case, Value, When
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .services.dashboard_service import DashboardService
from .models import Sport, Society, Team, League
from matches.models import Match, MatchReport
from accounts.models import User
from .forms import SocietySetupForm

logger = logging.getLogger(__name__)

def home(request):
    """Homepage pubblica: sport, featured match, classifica teaser e numeri chiave"""
    sports = Sport.objects.all()

    today = timezone.now().date()

    # --- NEW PREMIUM HOME CONTEXT ---
    # 1. Featured Match: L'ultima partita pubblicata
    featured_match = Match.objects.filter(
        is_finished=True, 
        reports__status=MatchReport.Status.PUBLISHED
    ).select_related('home_team__society', 'away_team__society', 'league').order_by('-match_date').first()
    
    # 2. Featured League: lega in vetrina — stagione corrente, seniores prima
    #    delle giovanili, tiebreak pk per determinismo. Fallback senza filtro
    #    stagione: su prod season_fk può essere ancora NULL su leghe non migrate.
    featured_league_data = None
    featured_qs = League.objects.filter(matches__isnull=False).annotate(
        is_senior=Case(
            When(league_type__in=League.SENIOR_LEAGUE_TYPES, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        )
    ).order_by('-is_senior', 'league_type', 'group_name', 'pk')
    featured_league = (
        featured_qs.filter(season_fk__is_current=True).first()
        or featured_qs.first()
    )
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
        'featured_match': featured_match,
        'featured_league_data': featured_league_data,
        'global_stats': global_stats,
        'seo_title': f"Risultati e Classifiche del {today.strftime('%d/%m/%Y')}",
        'seo_description': f"Segui i risultati di pallanuoto, volley e altri sport del {today.strftime('%d/%m/%Y')}. Classifiche e tabellini live su 2salti.",
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
    """Wizard società - solo per presidenti.

    Due modalità (Macro 18):
    - CREATE: strumento operativo riservato allo staff (account role='president'
      + is_staff) per onboardare una società non ancora a DB. Crea società +
      prima squadra SENZA agganciarla all'operatore: la società resta
      rivendicabile dal presidente reale via /society/choose/ (personificazione).
    - REFINE: il presidente è già stato agganciato a una società pre-esistente
      (via personificazione approvata dall'admin) -> rifinisce quella società
      (email obbligatoria, #5). Non crea né società né squadra: evita duplicati.
    """
    if request.user.role != 'president':
        return redirect('home')

    profile = getattr(request.user, 'president_profile', None)
    existing = profile.managed_society if profile else None

    if existing is None and not (request.user.is_staff or request.user.is_superuser):
        return redirect('choose_society')

    if request.method == 'POST':
        form = (
            SocietySetupForm(request.POST, request.FILES, instance=existing)
            if existing else
            SocietySetupForm(request.POST, request.FILES)
        )
        if form.is_valid():
            try:
                with transaction.atomic():
                    society = form.save()

                    if existing is None:
                        # CREATE (staff): la società NON viene agganciata al
                        # profilo dell'operatore — resta rivendicabile dal
                        # presidente reale via choose_society, e lo strumento
                        # resta riusabile dallo stesso account.

                        # Fase 3 (Macro 16): niente più ladder di squadre per
                        # categoria — la categoria vive sulla lega. Si crea la
                        # sola prima squadra (league=None finché non viene
                        # iscritta a un campionato).
                        Team.objects.create(society=society)

                        society.setup_completed = True
                        society.save()
                    else:
                        # REFINE: chiude il setup del presidente agganciato
                        # (choose_society smette di rimandare qui).
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
                return render(request, 'societies/society_setup.html', {
                    'form': form,
                    'is_refine': existing is not None,
                })

            return redirect('society_detail', slug=society.slug)
    else:
        form = SocietySetupForm(instance=existing) if existing else SocietySetupForm()

    return render(request, 'societies/society_setup.html', {
        'form': form,
        'is_refine': existing is not None,
    })


@login_required
def choose_society(request):
    """Macro 18 — Landing presidente: scegli la tua società e richiedi accesso.

    Stati (coerenti con §10.10, nessun loop: la vista RENDERIZZA, non rimbalza
    verso una vista che a sua volta redirige):
    - società già gestita + setup non completato -> rifinitura (create_society);
    - società già gestita + setup completato     -> dashboard;
    - richiesta PRESIDENT PENDING                 -> schermata "in attesa";
    - altrimenti                                  -> lista società + richiesta.
    """
    from management.services.president_personification import (
        societies_for_personification,
        request_president_personification,
    )

    if request.user.role != 'president':
        return redirect('home')

    profile = getattr(request.user, 'president_profile', None)
    if profile is not None and profile.managed_society_id is not None:
        if not request.user.setup_completed:
            return redirect('create_society')
        return redirect('dashboard')

    from management.models import MembershipRequest
    pending = (
        MembershipRequest.objects
        .filter(user=request.user, role='PRESIDENT', status='PENDING')
        .select_related('society')
        .first()
    )

    if request.method == 'POST' and pending is None:
        society_id = request.POST.get('society_id')
        society = (
            societies_for_personification().filter(id=society_id).first()
            if society_id else None
        )
        if society is None:
            messages.error(request, "Seleziona una società valida dall'elenco.")
        else:
            ok, pending, err = request_president_personification(request.user, society)
            if ok:
                messages.success(
                    request,
                    f"Richiesta inviata per {society.name}. "
                    "Un amministratore la valuterà a breve.",
                )
            else:
                messages.error(request, err)

    return render(request, 'societies/choose_society.html', {
        'societies': societies_for_personification(),
        'pending': pending,
    })

def society_detail(request, slug):
    """Pagina società con tutte le squadre"""
    from core.services.sponsor_service import get_society_sponsors
    society = get_object_or_404(Society, slug=slug)
    teams = society.teams.all().order_by('name')
    staff = society.get_staff()

    return render(request, 'societies/society_detail.html', {
        'society': society,
        'teams': teams,
        'staff': staff,
        'sponsors': get_society_sponsors(society),
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
