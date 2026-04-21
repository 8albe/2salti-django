from django.db import models
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.contrib.auth import get_user_model
from accounts.utils import onboarding_required
from management.permissions import get_membership_context
from .models import Match, MatchEvent, MatchReport
from .forms import MatchReportUploadForm, MatchReportReviewForm
from .event_types import (
    EVENT_TYPE_GOAL, EVENT_TYPE_PENALTY_GOAL, 
    EVENT_TYPE_EXCLUSION_20, EVENT_TYPE_EXCLUSION_DEF,
    EVENT_TYPE_TIMEOUT, EVENT_TYPE_SAVE
)


User = get_user_model()

def match_detail(request, match_id):
    """Pagina dettaglio partita con tabellino"""
    match = get_object_or_404(Match.objects.select_related(
        'home_team__society',
        'away_team__society',
        'league'
    ), id=match_id)
    
    # Eventi raggruppati per tipo (Solo se pubblico)
    if match.is_public:
        goals = match.events.filter(event_type__in=[EVENT_TYPE_GOAL, EVENT_TYPE_PENALTY_GOAL]).select_related('player', 'team')
        expulsions = match.events.filter(event_type__in=[EVENT_TYPE_EXCLUSION_20, EVENT_TYPE_EXCLUSION_DEF]).select_related('player', 'team')
        timeouts = match.events.filter(event_type=EVENT_TYPE_TIMEOUT).select_related('team')
        saves = match.events.filter(event_type=EVENT_TYPE_SAVE).select_related('player', 'team')
    else:
        goals = expulsions = timeouts = saves = []


    
    # Elaborazione quarter_scores per il template
    # Default: 4 per pallanuoto/WP, 2 per calcio
    sport_slug = match.league.sport.slug if match.league and match.league.sport else 'default'
    default_q = 4 if sport_slug in ['pallanuoto', 'wp'] else 2
    
    # Trova il massimo quarto registrato in quarter_scores o negli eventi
    max_q_data = 0
    if match.quarter_scores:
        try:
            max_q_data = max([int(k) for k in match.quarter_scores.keys()])
        except (ValueError, TypeError):
            pass
            
    max_q_events = match.events.aggregate(models.Max('quarter'))['quarter__max'] or 0
    max_q = max(default_q, max_q_data, max_q_events)
    
    q_range = range(1, max_q + 1)
    qs_processed = []
    for q in q_range:
        score = match.quarter_scores.get(str(q), [0, 0])
        qs_processed.append({'q': q, 'home': score[0], 'away': score[1]})

    from core.services.seo_service import SEOService
    from django.urls import reverse
    
    # Recupera rose squadre per il roster side-by-side
    home_roster = match.home_team.get_roster() if match.home_team else []
    away_roster = match.away_team.get_roster() if match.away_team else []

    context = {
        'match': match,
        'goals': goals,
        'expulsions': expulsions,
        'timeouts': timeouts,
        'saves': saves,
        'qs_processed': qs_processed,
        'home_roster': home_roster,
        'away_roster': away_roster,
        'sport': match.league.sport,
        'sport_color': match.league.sport.hex_color,
        'reports': match.reports.all(),
        'seo_title': f"{match.home_team.name} vs {match.away_team.name} - {match.league.name}",
        'seo_description': f"Risultati e tabellino per {match.home_team.name} vs {match.away_team.name} ({match.match_date.strftime('%d/%m/%Y')}). Dettagli partita e marcatori su 2salti.",
        'structured_data': [
            SEOService.get_match_schema(request, match),
            SEOService.get_breadcrumb_schema(request, [
                (match.league.sport.name, reverse('sport_detail', args=[match.league.sport.slug])),
                ("Risultati", reverse('sport_matches', args=[match.league.sport.slug])),
                (f"{match.home_team.name} vs {match.away_team.name}", request.path)
            ])
        ]
    }
    
    return render(request, 'matches/match_detail.html', context)


@login_required
@onboarding_required
def upload_report(request, match_id):
    """View per caricare un referto PDF/Immagine per una partita"""
    match = get_object_or_404(Match, id=match_id)
    
    # RBAC Check: Solo arbitro o staff delle squadre coinvolte
    can_upload = False
    membership_h = get_membership_context(request, team=match.home_team)
    membership_a = get_membership_context(request, team=match.away_team)

    if request.user.is_superuser:
        can_upload = True
    elif request.user.role == 'referee':
        can_upload = True
    elif (membership_h and membership_h.role in ['PRESIDENT', 'HEAD_COACH']) or \
         (membership_a and membership_a.role in ['PRESIDENT', 'HEAD_COACH']):
        can_upload = True
            
    if not can_upload:
        raise PermissionDenied
    
    if request.method == 'POST':
        form = MatchReportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.match = match
            report.uploader = request.user
            report.status = 'UPLOADED'
            report.save()
            
            from management.utils import log_action
            log_action(request.user, match.home_team.society, "REPORT_UPLOADED", target=report)
            
            # Retrocompatibilità flag (aggiornato a has_report)
            match.has_report = True
            match.save()
            
            messages.success(request, "Referto caricato con successo. In attesa di elaborazione OCR.")
            return redirect('match_detail', match_id=match.id)
    else:
        form = MatchReportUploadForm()

    return render(request, 'matches/upload_report.html', {
        'match': match,
        'form': form,
        'sport_color': match.league.sport.hex_color if match.league else '#000000',
    })


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
        'seo_title': f"Statistiche e Marcatori {league.name}",
        'seo_description': f"Classifica marcatori e statistiche disciplinari per {league.name}. Scopri i top scorer e i bad boys della stagione su 2salti.",
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
        'seo_title': f"Risultati e Calendario {sport.name}",
        'seo_description': f"Tutti i risultati e le prossime partite di {sport.name}. Calendario completo e tabellini su 2salti.",
    })
@login_required
@onboarding_required
def report_review(request, report_id):
    """View per la revisione manuale di un referto caricato. Solo Staff."""
    if not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied
        
    report = get_object_or_404(MatchReport.objects.select_related('match__home_team', 'match__away_team'), id=report_id)
    match = report.match
    home_roster = match.home_team.get_roster() if match.home_team else []
    away_roster = match.away_team.get_roster() if match.away_team else []
    
    if request.method == 'POST':
        messages.error(request, "Questo percorso di revisione è deprecato. Per salvare modifiche ai dati OCR, usa l'Operational Dashboard (Admin).")
        return redirect('report_review', report_id=report.id)
    else:
        # Warning for read-only mode in deprecation
        messages.warning(request, "MODALITÀ SOLA LETTURA: Questo percorso di revisione è deprecato per garantire l'integrità dei dati OCR. Usa l'Operational Dashboard nell'Admin per modificare o validare il referto.")
        
        # Pre-populate quarter scores from JSON if they exist
        qs = match.quarter_scores or {}
        
        initial_data = {
            'home_score': match.home_score or 0,
            'away_score': match.away_score or 0,
            'is_finished': match.is_finished,
            'report_status': report.status,
            'validation_notes': report.validation_notes,
            'internal_notes': report.internal_notes,
        }
        
        for i in range(1, 5):
            q_data = qs.get(str(i), [0, 0])
            initial_data[f'home_q{i}'] = q_data[0]
            initial_data[f'away_q{i}'] = q_data[1]
        
        # Initial goals from MatchEvents if any
        for athlete in home_roster:
            count = MatchEvent.objects.filter(match=match, player=athlete.user, event_type=EVENT_TYPE_GOAL).count()
            initial_data[f'player_goals_home_{athlete.user.id}'] = count
        for athlete in away_roster:
            count = MatchEvent.objects.filter(match=match, player=athlete.user, event_type=EVENT_TYPE_GOAL).count()
            initial_data[f'player_goals_away_{athlete.user.id}'] = count


        form = MatchReportReviewForm(initial=initial_data, home_roster=home_roster, away_roster=away_roster)
        
    return render(request, 'matches/report_review.html', {
        'report': report,
        'match': match,
        'form': form,
        'home_roster': home_roster,
        'away_roster': away_roster,
        'sport_color': match.league.sport.hex_color if match.league else '#000000',
    })

@login_required
def report_queue(request):
    """Coda di validazione per staff/admin."""
    if not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied
        
    status_filter = request.GET.get('status')
    reports = MatchReport.objects.select_related('match', 'uploader').order_by('-created_at')
    
    if status_filter:
        reports = reports.filter(status=status_filter)
        
    return render(request, 'matches/report_queue.html', {
        'reports': reports,
        'status_choices': MatchReport.Status.choices,
        'current_status': status_filter,
    })

@login_required
@onboarding_required
def create_digital_report(request, match_id):
    """Crea un referto digitale nativo per una partita (senza OCR)."""
    match = get_object_or_404(Match, id=match_id)
    
    # RBAC Check: Stessa logica dell'upload
    can_create = False
    membership_h = get_membership_context(request, team=match.home_team)
    membership_a = get_membership_context(request, team=match.away_team)

    if request.user.is_superuser:
        can_create = True
    elif request.user.role == 'referee':
        can_create = True
    elif (membership_h and membership_h.role in ['PRESIDENT', 'HEAD_COACH']) or \
         (membership_a and membership_a.role in ['PRESIDENT', 'HEAD_COACH']):
        can_create = True
            
    if not can_create:
        raise PermissionDenied
    
    # Crea il report digitale
    report = MatchReport.objects.create(
        match=match,
        uploader=request.user,
        source_channel='DIGITAL',
        status=MatchReport.Status.EXTRACTED, # Salta direttamente a extracted perché non c'è OCR
    )
    
    match.has_report = True
    match.save()
    
    messages.success(request, "Referto digitale inizializzato. Puoi procedere alla compilazione dei dati.")
    return redirect('report_review', report_id=report.id)
