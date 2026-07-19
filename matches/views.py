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
    EVENT_TYPE_GOAL,
    EVENT_TYPE_EXCLUSION_20,
    EVENT_TYPE_YELLOW_CARD,
    EVENT_TYPE_RED_CARD,
    EVENT_TYPE_TIMEOUT,
)

STANDARD_EVENT_TYPES = {
    EVENT_TYPE_GOAL,
    EVENT_TYPE_EXCLUSION_20,
    EVENT_TYPE_YELLOW_CARD,
    EVENT_TYPE_RED_CARD,
    EVENT_TYPE_TIMEOUT,
}


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
        goals = list(match.events.filter(event_type=EVENT_TYPE_GOAL).select_related('player', 'team'))
        expulsions = match.events.filter(event_type=EVENT_TYPE_EXCLUSION_20).select_related('player', 'team')
        yellow_cards = match.events.filter(event_type=EVENT_TYPE_YELLOW_CARD).select_related('player', 'team')
        red_cards = match.events.filter(event_type=EVENT_TYPE_RED_CARD).select_related('player', 'team')
        timeouts = match.events.filter(event_type=EVENT_TYPE_TIMEOUT).select_related('team')
        other_events = match.events.exclude(event_type__in=STANDARD_EVENT_TYPES).select_related('player', 'team')
    else:
        goals = []
        expulsions = yellow_cards = red_cards = timeouts = other_events = []

    # Marcatori raggruppati per squadra e giocatore (per il tabellino sintetico)
    home_scorers = {}
    away_scorers = {}
    for event in goals:
        if not event.player or not event.team:
            continue
        bucket = home_scorers if event.team_id == match.home_team_id else away_scorers
        entry = bucket.setdefault(event.player_id, {'player': event.player, 'minutes': []})
        entry['minutes'].append(event.minute)
    home_scorers_list = sorted(home_scorers.values(), key=lambda e: e['player'].get_full_name())
    away_scorers_list = sorted(away_scorers.values(), key=lambda e: e['player'].get_full_name())


    
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
        'yellow_cards': yellow_cards,
        'red_cards': red_cards,
        'timeouts': timeouts,
        'other_events': other_events,
        'home_scorers': home_scorers_list,
        'away_scorers': away_scorers_list,
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
def upload_report(request, match_id=None):
    """View per caricare un referto PDF/Immagine (con o senza partita pre-selezionata)"""
    match = None
    if match_id:
        match = get_object_or_404(Match, id=match_id)
    
    # RBAC Check: Se c'e' un match, logica specifica. Altrimenti Staff/Referee.
    can_upload = False
    if request.user.is_superuser or request.user.role == 'referee':
        can_upload = True
    elif match:
        membership_h = get_membership_context(request, team=match.home_team)
        membership_a = get_membership_context(request, team=match.away_team)
        if (membership_h and membership_h.role in ['PRESIDENT', 'HEAD_COACH']) or \
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
            
            # --- ACCODAMENTO OCR ASINCRONO (Macro 22) ---
            # L'elaborazione la esegue il worker `ocr_worker`: qui si accoda e
            # si risponde subito. Lo stato lo segue la review page in polling.
            from .services.ocr_service import OCRService
            OCRService.enqueue(report, user=request.user)

            if match:
                match.has_report = True
                match.save()
                from management.utils import log_action
                log_action(request.user, match.home_team.society, "REPORT_UPLOADED", target=report)
            
            messages.success(request, "Referto caricato: elaborazione in corso.")
            return redirect('report_review', report_id=report.id)
    else:
        form = MatchReportUploadForm()

    return render(request, 'matches/upload_report.html', {
        'match': match,
        'form': form,
        'sport_color': match.league.sport.hex_color if match and match.league else '#0366d6',
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
    """Lista di tutte le partite di uno sport (filtrate per stagione e data)"""
    from core.models import Sport
    from core.utils import get_calendar_dates
    from core.services.season_service import get_current_season
    from django.utils import timezone
    import datetime

    sport = get_object_or_404(Sport, slug=sport_slug)

    # Stagione corrente per-sport (Macro 16): default del selettore stagione.
    season = get_current_season(sport)
    if season:
        current_season = season.label
    else:
        # Fallback bit-identico al MAX lessicografico finche' Season non e'
        # popolata per questo sport (stesso pattern di sport_detail / fetta 1).
        current_season = (
            sport.leagues.order_by('-season').first().season
            if sport.leagues.exists()
            else ''
        )

    # Macro 3 fetta 2: selettore stagione sulla pagina pubblica Partite. Stessa
    # fonte dati della fetta 1: la stringa League.season (League e' gia'
    # per-stagione). Il filtro stagione e' il filtro grossolano; il filtro data
    # (?date=) resta sotto-filtro per-giorno. Niente FK, niente migration.
    available_seasons = list(
        sport.leagues.values_list('season', flat=True).distinct().order_by('-season')
    )
    requested_season = request.GET.get('season')
    if requested_season in available_seasons:
        selected_season = requested_season
    else:
        # Assente o non valido -> default alla stagione corrente.
        selected_season = current_season

    # Gestione Data (sotto-filtro invariato rispetto alla versione precedente).
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
        league__season=selected_season,
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
        'available_seasons': available_seasons,
        'selected_season': selected_season,
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
    
    # Candidate Discovery for unlinked reports
    potential_matches = []
    if not match and report.normalized_data:
        from core.models import Team
        from .services.ocr_service import resolve_team_entity
        from django.db.models import Q
        info = report.normalized_data.get('match_info', {})
        all_teams = Team.objects.all()
        h_team = resolve_team_entity(info.get('home_team'), all_teams)
        a_team = resolve_team_entity(info.get('away_team'), all_teams)
        if h_team or a_team:
            q = Q()
            if h_team: q |= Q(home_team=h_team) | Q(away_team=h_team)
            if a_team: q |= Q(home_team=a_team) | Q(away_team=a_team)
            potential_matches = Match.objects.filter(q).order_by('-match_date')[:5]

    home_roster = match.home_team.get_roster() if match and match.home_team else []
    away_roster = match.away_team.get_roster() if match and match.away_team else []
    
    if request.method == 'POST':
        action = request.POST.get('_action')
        
        # --- NEW: Match Discovery Actions ---
        if action == 'link_match':
            m_id = request.POST.get('selected_match_id')
            if m_id:
                new_match = get_object_or_404(Match, id=m_id)
                report.match = new_match
                report.save()
                messages.success(request, f"Referto collegato con successo: {new_match}")
                return redirect('report_review', report_id=report.pk)
        
        if action == 'create_match':
            # Relying on a helper or same logic as admin
            success, msg = _handle_match_creation_logic(report, request)
            if success:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return redirect('report_review', report_id=report.pk)
        # -----------------------------------

        form = MatchReportReviewForm(request.POST, home_roster=home_roster, away_roster=away_roster)
        if form.is_valid():
            # 1. Update Match Scores & Quarters
            match.home_score = form.cleaned_data['home_score']
            match.away_score = form.cleaned_data['away_score']
            match.is_finished = form.cleaned_data['is_finished']
            
            qs = {}
            for i in range(1, 5):
                qs[str(i)] = [form.cleaned_data[f'home_q{i}'], form.cleaned_data[f'away_q{i}']]
            match.quarter_scores = qs
            match.save()
            
            # 2. Update Report Metadata
            report.status = form.cleaned_data['report_status']
            report.validation_notes = form.cleaned_data['validation_notes']
            report.internal_notes = form.cleaned_data['internal_notes']
            report.validated_by = request.user
            report.validated_at = timezone.now()
            report.save()
            
            # 3. Create/Update MatchEvents (Goals)
            # This is a basic implementation for manual review/digital reports
            # If it's an OCR report, we might want to sync normalized_data instead,
            # but for MVP, manual override on the form is the priority.

            # Delete old manual events to re-sync
            match.events.filter(event_type=EVENT_TYPE_GOAL).delete()
            
            for athlete in home_roster:
                count = form.cleaned_data.get(f'player_goals_home_{athlete.user.id}', 0)
                for _ in range(count):
                    MatchEvent.objects.create(
                        match=match,
                        player=athlete.user,
                        team=match.home_team,
                        event_type=EVENT_TYPE_GOAL,
                        minute=0, # Manual review doesn't track minutes yet
                        quarter=1
                    )
            
            for athlete in away_roster:
                count = form.cleaned_data.get(f'player_goals_away_{athlete.user.id}', 0)
                for _ in range(count):
                    MatchEvent.objects.create(
                        match=match,
                        player=athlete.user,
                        team=match.away_team,
                        event_type=EVENT_TYPE_GOAL,
                        minute=0,
                        quarter=1
                    )
            
            # 4. Finalize Publish if requested
            if report.status == MatchReport.Status.PUBLISHED:
                from .services.publishing_service import PublishingService
                # If we have normalized_data from OCR, keep it in sync if possible,
                # but for manual form submission, we rely on the form data.
                # PublishingService usually takes normalized_data, so we should update it if it exists.
                if report.normalized_data:
                    # Update normalized_data with form values to keep it as Source of Truth
                    report.normalized_data['match_info'] = {
                        'home_score': match.home_score,
                        'away_score': match.away_score,
                    }
                    report.save()
                
                success, msg = PublishingService.publish_report(report, user=request.user)
                if success:
                    messages.success(request, f"Referto pubblicato con successo! {msg}")
                else:
                    messages.warning(request, f"Dati salvati, ma pubblicazione fallita: {msg}")
            else:
                messages.success(request, "Modifiche salvate con successo.")
                
            return redirect('match_detail', match_id=match.id)

    else:
        # 1. Base initial data from Match
        initial_data = {
            'home_score': match.home_score or 0,
            'away_score': match.away_score or 0,
            'is_finished': match.is_finished,
            'report_status': report.status if report.status != 'PROCESSING' else 'EXTRACTED',
            'validation_notes': report.validation_notes,
            'internal_notes': report.internal_notes,
        }
        
        # 2. Quarter scores
        qs = match.quarter_scores or {}
        # If match has no scores but report has normalized_data, try to use converter
        if not qs and report.normalized_data:
            from .services.converters import MatchDataConverter
            match_data = MatchDataConverter.get_match_scores(report.normalized_data)
            initial_data['home_score'] = match_data['home_score']
            initial_data['away_score'] = match_data['away_score']
            qs = match_data['quarter_scores']
            
        for i in range(1, 5):
            q_data = qs.get(str(i), [0, 0])
            initial_data[f'home_q{i}'] = q_data[0]
            initial_data[f'away_q{i}'] = q_data[1]
        
        # 3. Player Goals (Initial from MatchEvents or OCR normalized_data)
        # Priority 1: MatchEvents (previously saved)
        # Priority 2: normalized_data (extracted by AI and reconciled)
        
        # Mapping for OCR data pre-fill
        ocr_goals = {}
        if report.normalized_data:
            from .services.converters import MatchDataConverter
            events = MatchDataConverter.get_events_data(report.normalized_data)
            for e in events:
                if e['event_type'] == EVENT_TYPE_GOAL and e['player_id']:
                    ocr_goals[e['player_id']] = ocr_goals.get(e['player_id'], 0) + 1

        for athlete in home_roster:
            count = MatchEvent.objects.filter(match=match, player=athlete.user, event_type=EVENT_TYPE_GOAL).count()
            if count == 0 and athlete.user.id in ocr_goals:
                count = ocr_goals[athlete.user.id]
            initial_data[f'player_goals_home_{athlete.user.id}'] = count
            
        for athlete in away_roster:
            count = MatchEvent.objects.filter(match=match, player=athlete.user, event_type=EVENT_TYPE_GOAL).count()
            if count == 0 and athlete.user.id in ocr_goals:
                count = ocr_goals[athlete.user.id]
            initial_data[f'player_goals_away_{athlete.user.id}'] = count

        form = MatchReportReviewForm(initial=initial_data, home_roster=home_roster, away_roster=away_roster)
        
    return render(request, 'matches/report_review.html', {
        'report': report,
        'match': match,
        'form': form,
        'home_roster': home_roster,
        'away_roster': away_roster,
        'potential_matches': potential_matches,
        'sport_color': match.league.sport.hex_color if match and match.league else '#0366d6',
    })

@login_required
def report_queue(request):
    """Dashboard operativa per arbitri e staff."""
    # RBAC: Arbitri possono vedere i propri, Staff vede tutto
    is_staff = request.user.is_staff or request.user.is_superuser
    
    if is_staff:
        reports = MatchReport.objects.all()
    elif request.user.role == 'referee':
        # Arbitro vede i referti che ha caricato o i match che arbitra
        reports = MatchReport.objects.filter(
            models.Q(uploader=request.user) | 
            models.Q(match__referees=request.user)
        ).distinct()
    else:
        # Altri ruoli vedono solo se legati a societa? Per ora blocchiamo
        raise PermissionDenied
        
    reports = reports.select_related('match', 'uploader', 'validated_by').order_by('-created_at')
    
    status_filter = request.GET.get('status')
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

def _handle_match_creation_logic(report, request):
    """Logica condivisa per creare un match dai dati OCR (Dashboard)."""
    from core.models import Team, League
    from .services.ocr_service import resolve_team_entity
    from .models import Match
    from datetime import datetime
    
    data = report.normalized_data or {}
    info = data.get('match_info', {})
    
    home_name = info.get('home_team')
    away_name = info.get('away_team')
    league_name = info.get('league')
    date_str = info.get('date')
    
    # 1. Resolve Date
    target_date = None
    if date_str:
        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y']:
            try:
                target_date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
    if not target_date:
        return False, "Data mancante o non valida nell'OCR."
        
    # 2. Resolve Teams
    all_teams = Team.objects.all()
    home_team = resolve_team_entity(home_name, all_teams)
    away_team = resolve_team_entity(away_name, all_teams)
    if not home_team or not away_team:
        return False, f"Squadre non risolte ({home_name} vs {away_name}). Crea le entità prima."
        
    # 3. Resolve League
    league = None
    if league_name:
        league = League.objects.filter(name__icontains=league_name).first()
    
    # 4. Create Match
    score_h, score_a = 0, 0
    try:
        score_h = int(data.get('teams', {}).get('home', {}).get('score', 0))
        score_a = int(data.get('teams', {}).get('away', {}).get('score', 0))
    except: pass
    
    match = Match.objects.create(
        home_team=home_team, away_team=away_team,
        match_date=datetime.combine(target_date, datetime.min.time()),
        league=league, home_score=score_h, away_score=score_a,
        is_finished=True, has_report=True
    )
    report.match = match
    report.save()
    return True, f"Match creato e collegato: {match}"
