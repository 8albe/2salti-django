from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from .models import (
    Training, TrainingOccurrence, TrainingAttendance, 
    Post, Comment, ChatMessage, Convocation, ConvocationNominee,
    Membership, ActivationCode, MembershipRequest
)
from .forms import TrainingForm, ConvocationForm
from .logic import generate_occurrences
from .permissions import role_required, get_society_context, get_membership_context
from .utils import log_action
from django.utils import timezone
from django.contrib import messages
from core.models import Society, Team
from core.integrations import INTEGRATION_REGISTRY
from django.db import models
from matches.models import Match, MatchReport
from accounts.models import User
from accounts.utils import onboarding_required

@login_required
@onboarding_required
def training_list(request):
    """
    Visualizza il calendario degli allenamenti per la società.
    PRD: Tutti gli atleti della società vedono il calendario di tutte le categorie.
    """
    society = get_society_context(request)
    if not society:
        return redirect('home')
        
    occurrences = TrainingOccurrence.objects.filter(
        training__society=society,
        start_time__gte=timezone.now() - timezone.timedelta(days=1)
    ).select_related('training', 'training__team').order_by('start_time')
    
    return render(request, 'management/training_list.html', {
        'occurrences': occurrences,
    })

@login_required
@onboarding_required
@role_required(['PRESIDENT', 'HEAD_COACH'])
def training_create(request):
    """
    Crea un nuovo piano di allenamento.
    """
    society = get_society_context(request)
    if not society:
        return redirect('home')

    if request.method == 'POST':
        form = TrainingForm(request.POST, request.FILES, society=society)
        if form.is_valid():
            training = form.save(commit=False)
            training.society = society
            
            # Gestione ricorrenza (semplificata per il database)
            if training.is_recurring:
                training.recurrence_rule = {
                    'freq': form.cleaned_data['rec_freq'],
                    'days': [int(d) for d in form.cleaned_data['rec_days']],
                    'until': form.cleaned_data['rec_until'].isoformat()
                }
            
            training.save()
            
            # Genera le istanze
            generate_occurrences(training)
            
            log_action(request.user, society, "CREATE_TRAINING", target=training, request=request)
            messages.success(request, "Allenamento creato con successo.")
            return redirect('training_list')
    else:
        form = TrainingForm(society=society)
        
    return render(request, 'management/training_form.html', {'form': form})

@login_required
@onboarding_required
def training_rsvp(request, occurrence_id):
    """
    Gestisce l'RSVP con Geofencing.
    """
    # Hardening: verifica che l'allenamento appartenga alla società dell'utente
    society = get_society_context(request)
    if not society:
        raise PermissionDenied
    occurrence = get_object_or_404(TrainingOccurrence, id=occurrence_id, training__society=society)
    
    if request.method == 'POST':
        lat = request.POST.get('lat')
        lng = request.POST.get('lng')
        acc = request.POST.get('accuracy')
        status = request.POST.get('status', 'PRESENT')
        
        # Validazione Geofence (120m) - Opzionale ma consigliata nel PRD
        is_in_range = True
        # Qui andrebbe la logica Haversine se avessimo le coordinate della location
        # Per ora salviamo i dati come richiesto dal PRD
        
        attendance, created = TrainingAttendance.objects.update_or_create(
            occurrence=occurrence,
            user=request.user,
            defaults={
                'status': status,
                'latitude': lat,
                'longitude': lng,
                'accuracy': acc,
                'checkin_time': timezone.now()
            }
        )
        
        messages.success(request, f"RSVP inviato: {status}")
        return redirect('training_list')
        
    return render(request, 'management/training_rsvp.html', {'occurrence': occurrence})

@login_required
@onboarding_required
@role_required(['PRESIDENT', 'HEAD_COACH'])
def convocation_create(request, match_id):
    """
    Crea una nuova convocazione per una partita.
    Include la logica di riuso del setup precedente.
    """
    match = get_object_or_404(Match, id=match_id)
    # Hardening: verifica che la partita riguardi la società dell'utente
    society = get_society_context(request)
    if not society or (match.home_team.society != society and match.away_team.society != society):
        raise PermissionDenied
    
    team = match.home_team if match.home_team.society == society else match.away_team
    
    # 1. Recupera la convocazione precedente per il riuso
    previous_conv = Convocation.objects.filter(
        match__home_team=team,
        match__match_date__lt=match.match_date
    ).order_by('-match__match_date').first()
    
    if request.method == 'POST':
        form = ConvocationForm(request.POST, request.FILES, team=team)
        if form.is_valid():
            convocation = form.save(commit=False)
            convocation.creator = request.user
            convocation.save()
            
            # Salva i convocati
            for player in form.cleaned_data['nominees']:
                is_starter = player in form.cleaned_data['starters']
                ConvocationNominee.objects.create(
                    convocation=convocation,
                    player=player,
                    is_starter=is_starter
                )
            
            log_action(request.user, team.society, "CREATE_CONVOCATION", target=convocation, request=request)
            messages.success(request, "Convocazione salvata.")
            return redirect('core:team_detail', slug=team.slug)
    else:
        # Precompilazione eventuale (se cliccato "usa questo setup" nel template)
        initial_data = {}
        if previous_conv and request.GET.get('use_previous'):
            initial_data = {
                'capitano': previous_conv.capitano,
                'vicecapitano': previous_conv.vicecapitano,
                'notes': previous_conv.notes,
                'nominees': list(previous_conv.nominees.values_list('player_id', flat=True)),
                'starters': list(previous_conv.nominees.filter(is_starter=True).values_list('player_id', flat=True))
            }
        form = ConvocationForm(initial=initial_data, team=team)
        
    return render(request, 'management/convocation_form.html', {
        'form': form,
        'match': match,
        'previous_conv': previous_conv
    })

@login_required
@onboarding_required
def bacheca_view(request, team_slug=None):
    """
    Bacheca della squadra o della società.
    PRD 5.1/5.2: Head Coach postare/pinnare, President broadcast ovunque.
    """
    if team_slug:
        team = get_object_or_404(Team, slug=team_slug)
        # Filtra post della squadra + broadcast societari
        posts = Post.objects.filter(
            models.Q(team=team) | models.Q(is_broadcast=True, society=team.society)
        ).select_related('author', 'team').prefetch_related('comments__author')
    else:
        # Se non c'è team_slug, mostra tutto ciò che l'utente può vedere nella società corrente
        society = get_society_context(request)
        
        # Fallback: se accediamo globalmente senza slug, cerchiamo la società tramite membership o profili
        if not society and request.user.is_authenticated:
            # 1. Membership
            first_membership = request.user.memberships.filter(is_active=True).first()
            if first_membership:
                society = first_membership.society
            
            # 2. CoachProfile
            if not society and hasattr(request.user, 'coach_profile') and request.user.coach_profile.current_team:
                society = request.user.coach_profile.current_team.society
                
            # 3. AthleteProfile
            if not society and hasattr(request.user, 'athlete_profile') and request.user.athlete_profile.current_team:
                society = request.user.athlete_profile.current_team.society
                
            # 4. PresidentProfile
            if not society and hasattr(request.user, 'president_profile') and request.user.president_profile.managed_society:
                society = request.user.president_profile.managed_society

        if not society:
            return redirect('home')
            
        posts = Post.objects.filter(society=society).select_related('author', 'team')
        team = None

    # Assicuriamoci che user_membership sia disponibile nel contesto anche per URL globali
    user_membership = get_membership_context(request, team=team, society=society)

    # Logica RBAC robusta per il template (considera sia Membership che Profile Fallback)
    can_post = False
    is_president = False

    if user_membership and user_membership.role in ['PRESIDENT', 'HEAD_COACH', 'ASSISTANT_COACH']:
        can_post = True
        if user_membership.role == 'PRESIDENT':
            is_president = True
    elif request.user.is_authenticated:
        if request.user.role in ['coach', 'president']:
            can_post = True
            if request.user.role == 'president':
                is_president = True

    return render(request, 'management/bacheca.html', {
        'posts': posts,
        'team': team,
        'user_membership': user_membership,
        'can_post': can_post,
        'is_president': is_president,
    })

@login_required
@onboarding_required
def post_create(request, team_id=None):
    """
    Crea un post in bacheca.
    """
    if request.method == 'POST':
        content = request.POST.get('content')
        title = request.POST.get('title', '')
        is_pinned = request.POST.get('is_pinned') == 'on'
        is_broadcast = request.POST.get('is_broadcast') == 'on'
        
        if team_id and int(team_id) > 0:
            team = get_object_or_404(Team, id=team_id)
            society = team.society
        else:
            team = None
            society = get_society_context(request)
        
        # RBAC Check (PRD 5.2)
        can_post = False
        if request.user.is_superuser:
            can_post = True
        elif request.user_membership:
            if request.user_membership.role == 'PRESIDENT':
                can_post = True
            elif team and request.user_membership.team == team and request.user_membership.role in ['HEAD_COACH', 'ASSISTANT_COACH']:
                can_post = True

        if not can_post:
            messages.error(request, "Non hai i permessi per postare qui.")
            return redirect('home')

        post = Post.objects.create(
            society=society,
            team=team,
            author=request.user,
            title=title,
            content=content,
            is_pinned=is_pinned,
            is_broadcast=is_broadcast if request.user_membership.role == 'PRESIDENT' else False
        )
        
        log_action(request.user, society, "CREATE_POST", target=post, request=request)
        return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required
@onboarding_required
def chat_view(request, team_slug):
    """
    Chat di squadra.
    """
    team = get_object_or_404(Team, slug=team_slug)
    membership = get_membership_context(request, team=team)
    
    # Verifica che l'utente sia membro della squadra o presidente
    can_access = False
    if request.user.is_superuser:
        can_access = True
    elif membership:
        if membership.role == 'PRESIDENT':
            can_access = True
        elif membership.team == team:
            can_access = True
            
    if not can_access:
        messages.error(request, "Non hai accesso alla chat di questa squadra.")
        return redirect('home')

    messages_list = ChatMessage.objects.filter(team=team).select_related('author').order_by('created_at')[:100]
    
    return render(request, 'management/chat.html', {
        'team': team,
        'chat_messages': messages_list,
    })

@login_required
@onboarding_required
def chat_message_add(request, team_id):
    # RBAC Check
    team = get_object_or_404(Team, id=team_id)
    membership = get_membership_context(request, team=team)
    
    can_access = False
    if request.user.is_superuser:
        can_access = True
    elif membership:
        if membership.role == 'PRESIDENT':
            can_access = True
        elif membership.team == team:
            can_access = True
            
    if not can_access:
        raise PermissionDenied

    if request.method == 'POST':
        team = get_object_or_404(Team, id=team_id)
        content = request.POST.get('content')
        if content:
            ChatMessage.objects.create(team=team, author=request.user, content=content)
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required
@onboarding_required
def team_access(request):
    """Fase 4: Accesso Squadra (Sezione 7)"""
    if request.method == 'POST':
        code_str = request.POST.get('activation_code')
        if code_str:
            try:
                code_obj = ActivationCode.objects.get(code=code_str, is_active=True)
                # Verifica usi e scadenza...
                if code_obj.expires_at and code_obj.expires_at < timezone.now():
                    messages.error(request, "Codice scaduto.")
                elif code_obj.current_uses >= code_obj.max_uses:
                    messages.error(request, "Codice già utilizzato il massimo numero di volte.")
                else:
                    # Crea Membership
                    Membership.objects.get_or_create(
                        user=request.user,
                        society=code_obj.society,
                        team=code_obj.team,
                        role=code_obj.role
                    )
                    code_obj.current_uses += 1
                    code_obj.save()
                    messages.success(request, f"Benvenuto nella squadra {code_obj.team or code_obj.society}!")
                    return redirect('profile', username=request.user.username)
            except ActivationCode.DoesNotExist:
                messages.error(request, "Codice non valido.")
        
        # Gestione Richiesta Manuale
        manual_team_id = request.POST.get('team_id')
        if manual_team_id:
            team = get_object_or_404(Team, id=manual_team_id)
            MembershipRequest.objects.get_or_create(
                user=request.user,
                society=team.society,
                team=team,
                role='PLAYER', # Default per richiesta manuale atleta
                status='PENDING'
            )
            messages.success(request, "Richiesta inviata al Club Admin. Sarai avvisato via email.")
            return render(request, 'management/onboarding/pending_approval.html')

    teams = Team.objects.all().select_related('society')
    return render(request, 'management/onboarding/team_access.html', {'teams': teams})

@login_required
@role_required(['PRESIDENT'])
def club_admin_dashboard(request):
    """Pannello essenziale per Club Admin (Sezione 3)"""
    society = get_society_context(request)
    if not society:
        return redirect('home')

    requests = MembershipRequest.objects.filter(society=society, status='PENDING')
    codes = ActivationCode.objects.filter(society=society)
    
    return render(request, 'management/club_admin/dashboard.html', {
        'society': society,
        'membership_requests': requests,
        'activation_codes': codes,
    })

@login_required
@role_required(['PRESIDENT'])
def approve_membership(request, request_id):
    # Hardening: verifica che la richiesta appartenga alla società gestita dall'utente
    if not get_society_context(request):
         # Fallback per presidenti senza società nel middleware
        if hasattr(request.user, 'president_profile'):
            society = request.user.president_profile.managed_society
        else:
            raise PermissionDenied
    else:
        society = get_society_context(request)

    req = get_object_or_404(MembershipRequest, id=request_id, society=society)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            req.status = 'APPROVED'
            Membership.objects.get_or_create(
                user=req.user,
                society=req.society,
                team=req.team,
                role=req.role
            )
            messages.success(request, f"Membro {req.user.username} approvato.")
        else:
            req.status = 'REJECTED'
            messages.warning(request, f"Richiesta di {req.user.username} respinta.")
        req.save()
    return redirect('club_admin_dashboard')

import random
import string

@login_required
@role_required(['PRESIDENT'])
def generate_code(request):
    """View per generare nuovi codici di attivazione (Club Admin)"""
    society = get_society_context(request)
    if not society:
        messages.error(request, "Devi essere associato a una società.")
        return redirect('home')

    if request.method == 'POST':
        team_id = request.POST.get('team_id')
        role = request.POST.get('role', 'PLAYER')
        max_uses = int(request.POST.get('max_uses', 50))
        
        team = Team.objects.filter(id=team_id, society=society).first() if team_id else None
        
        # Generatore sicuro di codici custom
        prefix = ''.join(e for e in society.name if e.isalnum())[:4].upper()
        if len(prefix) < 4:
            prefix = prefix.ljust(4, 'X')
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        code_str = f"{prefix}-{random_str[:3]}-{random_str[3:]}"
        
        from core.models import Team # Se non importato
        from .models import ActivationCode
        
        ActivationCode.objects.create(
            code=code_str,
            society=society,
            team=team,
            role=role,
            max_uses=max_uses
        )
        
        messages.success(request, f"Nuovo codice generato: {code_str}")
        return redirect('club_admin_dashboard')
        
    from core.models import Team
    teams = Team.objects.filter(society=society)
    return render(request, 'management/club_admin/generate_code.html', {'teams': teams, 'society': society})

@login_required
def staff_dashboard(request):
    """
    Dashboard operativa per lo staff:
    - Funnel dei referti
    - Utenti bloccati in onboarding
    - Stato integrazioni
    - Referti bloccati (> 4h)
    """
    if not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied

    # 1. Statistiche Referti
    report_stats = MatchReport.objects.values('status').annotate(count=models.Count('id'))
    report_stats_dict = {s['status']: s['count'] for s in report_stats}
    # Ensure all statuses are present
    for status_code, status_label in MatchReport.Status.choices:
        report_stats_dict.setdefault(status_code, 0)

    # 2. Utenti bloccati in onboarding
    # Usiamo la property onboarding_state definita in User model (necessita calcolo Python o annotazione)
    # Per semplicità in dashboard, facciamo un conteggio rapido:
    from django.db.models import Count, Q
    functional_roles = ['athlete', 'coach', 'referee', 'president']
    onboarding_stats = {
        'IDENTITY_PENDING': User.objects.filter(role__in=functional_roles, identity_status='UNVERIFIED').count(),
        'PAYMENT_PENDING': User.objects.filter(role__in=functional_roles, identity_status='VERIFIED', subscription_status='INACTIVE').count(),
        'SETUP_PENDING': User.objects.filter(role__in=functional_roles, identity_status='VERIFIED', subscription_status='ACTIVE', setup_completed=False).count(),
    }

    # 4. Republish Rate (Efficienza OCR/Validazione)
    from .models import AuditLog
    publish_count = AuditLog.objects.filter(action='PUBLISH_REPORT').count()
    republish_count = AuditLog.objects.filter(action='REPUBLISH_REPORT').count()
    total_publishes = publish_count + republish_count
    republish_rate = int(republish_count / total_publishes * 100) if total_publishes > 0 else 0

    return render(request, 'management/staff_dashboard.html', {
        'report_stats': report_stats_dict,
        'onboarding_stats': onboarding_stats,
        'stuck_reports': stuck_reports,
        'integrations': INTEGRATION_REGISTRY,
        'republish_rate': republish_rate,
        'publish_count': publish_count,
        'republish_count': republish_count,
    })

@login_required
def ops_cockpit(request):
    """
    Cockpit Operativo per Admin/Staff.
    Monitoraggio flussi MatchReport in tempo reale.
    """
    if not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied

    now = timezone.now()
    last_24h = now - timezone.timedelta(hours=24)

    # I KPI richiesti basati sugli stati reali del modello MatchReport
    # Status.EXTRACTED e Status.VALIDATED sono quelli pronti per la revisione/pubblicazione
    # Status.UPLOADED e Status.PROCESSING sono quelli ancora in coda tecnica
    stats = MatchReport.objects.aggregate(
        pending_review=models.Count('id', filter=models.Q(status__in=[MatchReport.Status.EXTRACTED, MatchReport.Status.VALIDATED])),
        in_flight=models.Count('id', filter=models.Q(status__in=[MatchReport.Status.UPLOADED, MatchReport.Status.PROCESSING])),
        needs_review=models.Count('id', filter=models.Q(status=MatchReport.Status.NEEDS_REVIEW)),
        failed=models.Count('id', filter=models.Q(status=MatchReport.Status.REJECTED)),
        published_24h=models.Count('id', filter=models.Q(status=MatchReport.Status.PUBLISHED, published_at__gte=last_24h))
    )

    # Conteggio partite senza alcun referto pubblicato
    matches_no_report = Match.objects.exclude(reports__status=MatchReport.Status.PUBLISHED).distinct().count()

    # Liste Operative (Oldest Pending e Latest Published)
    oldest_unpublished = MatchReport.objects.exclude(
        status=MatchReport.Status.PUBLISHED
    ).select_related('match', 'match__home_team', 'match__away_team').order_by('created_at')[:10]
    
    latest_published = MatchReport.objects.filter(
        status=MatchReport.Status.PUBLISHED
    ).select_related('match', 'match__home_team', 'match__away_team', 'published_by').order_by('-published_at')[:10]

    return render(request, 'management/ops_cockpit.html', {
        'stats': stats,
        'matches_no_report': matches_no_report,
        'oldest_unpublished': oldest_unpublished,
        'latest_published': latest_published,
    })
