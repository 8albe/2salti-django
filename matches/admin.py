from django.contrib import admin
from .models import Match, MatchEvent, MatchReport, MatchReportAuditLog, InboundEmail, SportEventConfig
from .event_types import DEFAULT_EVENT_TYPES

from .forms import MatchReportAdminForm
from core.models import Team, League, Sport
from .services.ocr_service import OCRService
from .services.publishing_service import PublishingService
from .services.schema import OCRSchemaValidator
from .services.ocr_quality_gate import OCRQualityGate
from .services.entity_bootstrap import EntityBootstrapService
from django.contrib import messages
from django.urls import reverse, path
from django.utils.html import format_html
from django.shortcuts import render, redirect, get_object_or_404
from django.template.response import TemplateResponse
import json

class BlockingIssuesFilter(admin.SimpleListFilter):
    title = 'Blocchi (OCR)'
    parameter_name = 'has_blocks'
    def lookups(self, request, model_admin):
        return (('yes', 'Sì (Con Blocchi)'), ('no', 'No (Pulito)'))
    def queryset(self, request, queryset):
        from django.db import models
        if self.value() == 'yes':
            return queryset.filter(
                models.Q(validation_notes__startswith='{') & ~models.Q(validation_notes__icontains='"blocking": []') |
                ~models.Q(validation_notes__startswith='{') & models.Q(validation_notes__icontains='Fallito')
            )
        if self.value() == 'no':
            return queryset.filter(models.Q(validation_notes__icontains='"blocking": []') | models.Q(validation_notes=''))

class WarningsFilter(admin.SimpleListFilter):
    title = 'Avvisi (OCR)'
    parameter_name = 'has_warnings'
    def lookups(self, request, model_admin):
        return (('yes', 'Sì (Con Avvisi)'), ('no', 'No (Pulito)'))
    def queryset(self, request, queryset):
        from django.db import models
        if self.value() == 'yes':
            return queryset.filter(
                models.Q(validation_notes__startswith='{') & ~models.Q(validation_notes__icontains='"warnings": []') |
                ~models.Q(validation_notes__startswith='{') & models.Q(validation_notes__icontains='Avvisi')
            )
        if self.value() == 'no':
            return queryset.filter(models.Q(validation_notes__icontains='"warnings": []') | models.Q(validation_notes=''))

class OpAdminSite(admin.AdminSite):
    site_header = "2salti Operational Dashboard"
    site_title = "2salti Ops"
    index_title = "Gestione Operativa"

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)

        groups = {
            'Operazioni Principali': {
                'app_label': 'operations',
                'models': ['MatchReport', 'Match', 'Team', 'League', 'Sport'],
                'order': {'MatchReport': 0, 'Match': 1, 'Team': 2, 'League': 3, 'Sport': 4},
            },
            'Gestione Membership': {
                'app_label': 'membership',
                'models': ['Membership', 'MembershipRequest', 'ActivationCode', 'AuditLog'],
                'order': {'Membership': 0, 'MembershipRequest': 1, 'ActivationCode': 2, 'AuditLog': 3},
            },
            'Pilot Operations': {
                'app_label': 'pilot',
                'models': ['PilotDailyLog', 'PilotBug', 'PilotFeedback', 'PilotReview'],
                'order': {'PilotDailyLog': 0, 'PilotBug': 1, 'PilotFeedback': 2, 'PilotReview': 3},
            },
        }

        # TODO: refactor con attributo di classe op_admin_group sui ModelAdmin
        # per evitare lista hardcoded.

        result = []
        for group_name, config in groups.items():
            group_models = []
            for app in app_list:
                for model in app['models']:
                    if model['object_name'] in config['models']:
                        group_models.append(model)
            group_models.sort(key=lambda x: config['order'].get(x['object_name'], 999))
            if group_models:
                result.append({
                    'name': group_name,
                    'app_label': config['app_label'],
                    'models': group_models,
                    'has_module_permission': True,
                })
        return result

op_admin_site = OpAdminSite(name='op_admin')

class MatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'match_date', 'home_team', 'away_team', 'home_score', 'away_score', 'is_finished', 'has_report')
    list_filter = ('is_finished', 'has_report', 'league', 'match_date')
    search_fields = ('home_team__name', 'away_team__name', 'location')
    ordering = ('-match_date',)
    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        return fields

class MatchReportAdmin(admin.ModelAdmin):
    form = MatchReportAdminForm
    list_display = ('id', 'priority_label', 'status_colored', 'match_link', 'match_date', 'has_blocking_issues', 'has_warnings', 'created_at', 'review_action')
    list_filter = ('status', BlockingIssuesFilter, WarningsFilter, 'match__league', 'created_at', 'uploader', 'in_review_by')
    
    def has_blocking_issues(self, obj):
        if not obj.validation_notes: return False
        if obj.validation_notes.startswith("{"): return '"blocking": []' not in obj.validation_notes
        return 'Fallito' in obj.validation_notes
    has_blocking_issues.boolean = True
    
    def has_warnings(self, obj):
        if not obj.validation_notes: return False
        if obj.validation_notes.startswith("{"): return '"warnings": []' not in obj.validation_notes
        return 'Avvisi' in obj.validation_notes
    has_warnings.boolean = True

    def get_queryset(self, request):
        from django.db.models import Case, When, Value, IntegerField, Q
        qs = super().get_queryset(request)
        return qs.annotate(priority=Case(
            When(Q(status='NEEDS_REVIEW') & Q(validation_notes__startswith='{') & ~Q(validation_notes__icontains='"blocking": []'), then=Value(1)),
            When(Q(status='NEEDS_REVIEW') & ~Q(validation_notes__startswith='{') & Q(validation_notes__icontains='Fallito'), then=Value(1)),
            When(Q(status='NEEDS_REVIEW') & Q(validation_notes__startswith='{') & ~Q(validation_notes__icontains='"warnings": []'), then=Value(2)),
            When(Q(status='NEEDS_REVIEW') & ~Q(validation_notes__startswith='{') & Q(validation_notes__icontains='Avvisi'), then=Value(2)),
            When(status='EXTRACTED', then=Value(3)),
            default=Value(4), output_field=IntegerField()
        ))
    
    def priority_label(self, obj):
        if obj.priority == 1: return format_html('<span style="color:red; font-weight:bold;">1 - Urgente (Blocchi)</span>')
        if obj.priority == 2: return format_html('<span style="color:orange; font-weight:bold;">2 - Media (Avvisi)</span>')
        if obj.priority == 3: return format_html('<span style="color:blue; font-weight:bold;">3 - Da Iniziare</span>')
        return "4 - Bassa"
    priority_label.short_description = 'Priorità'
    priority_label.admin_order_field = 'priority'
    
    def match_link(self, obj):
        if not obj.match: return format_html('<span style="color: red; font-style: italic;">Discovery necessaria</span>')
        url = reverse('admin:matches_match_change', args=[obj.match.id])
        return format_html('<a href="{}">{}</a>', url, obj.match)
    match_link.short_description = 'Match'

    def match_date(self, obj): return obj.match.match_date if obj.match else "-"
    match_date.short_description = 'Data Match'

    def review_action(self, obj):
        url = reverse('admin:matches_matchreport_review', args=[obj.id])
        return format_html('<a class="button" href="{}" style="padding: 2px 8px; background: #0366d6; color: white; border-radius: 4px; font-size: 10px; font-weight: bold;">Review &rarr;</a>', url)
    review_action.short_description = 'Azione'
    
    readonly_fields = ('raw_extracted_data', 'validation_notes', 'created_at', 'updated_at', 'source_metadata', 'file_hash')
    fields = ['match', 'file', 'source_channel', 'status', 'uploader', 'internal_notes', 'validation_notes', 'raw_extracted_data', 'created_at', 'updated_at']

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            for f in ['match', 'status', 'uploader']:
                if f not in readonly: readonly.append(f)
        else:
            for f in ['status', 'uploader']:
                if f not in readonly: readonly.append(f)
        return readonly

    search_fields = ('match__home_team__name', 'match__away_team__name')
    actions = ['process_ocr', 'publish_reports']

    def changelist_view(self, request, extra_context=None):
        from django.db.models import Q

        from matches.status_presentation import OPEN_STATUSES
        response = super().changelist_view(request, extra_context)
        if hasattr(response, 'context_data'):
            try: qs = response.context_data['cl'].queryset
            except: qs = self.get_queryset(request)
            queue_kpi = {
                'total': qs.filter(status__in=OPEN_STATUSES).count(),
                'needs_review': qs.filter(status='NEEDS_REVIEW').count(),
                'blocked': qs.filter(Q(validation_notes__startswith='{') & ~Q(validation_notes__icontains='"blocking": []') | ~Q(validation_notes__startswith='{') & Q(validation_notes__icontains='Fallito')).count(),
                'ready_to_publish': qs.filter(status='VALIDATED').count(),
            }
            if extra_context is None: extra_context = {}
            extra_context['queue_kpi'] = queue_kpi
            response.context_data.update(extra_context)
        return response

    def status_colored(self, obj):
        # Il colore arriva dalla mappa unica in `matches.status_presentation`:
        # il dizionario che stava qui ometteva DRAFT, che finiva sul fallback
        # 'black' e diventava graficamente indistinguibile da REJECTED.
        from matches.status_presentation import classes_for
        color = classes_for(obj.status, 'admin')
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
    status_colored.short_description = 'Stato'

    @admin.action(description="Elabora OCR (accoda)")
    def process_ocr(self, request, queryset):
        # Macro 22: l'azione accoda, non elabora. L'esito arriva in background
        # (worker `ocr_worker`) e si legge dalla colonna Stato / dalle notifiche
        # NEEDS_REVIEW: contarlo qui non avrebbe senso, e' asincrono per natura.
        queued_count = 0
        skipped_count = 0
        for report in queryset:
            if report.status not in OCRService.ENQUEUEABLE_STATES:
                skipped_count += 1
                continue
            if OCRService.enqueue(report, user=request.user):
                queued_count += 1
            else:
                # Precondizione fallita dopo il filtro (es. file mancante -> REJECTED).
                skipped_count += 1
        self.message_user(
            request,
            f"Accodati: {queued_count}, Saltati: {skipped_count}. "
            f"L'elaborazione avviene in background: aggiorna la lista per vedere lo stato.",
            messages.INFO,
        )

    @admin.action(description="Pubblica Referti")
    def publish_reports(self, request, queryset):
        success_count = 0
        for report in queryset:
            if report.status != MatchReport.Status.VALIDATED: continue
            success, msg = PublishingService.publish_report(report, user=request.user)
            if success: success_count += 1
        # TODO(ux): messaggi bulk-action telegraphic; migliorare con conteggio esclusi e frase completa quando si fa il pass UX admin.
        self.message_user(request, f"Pubblicati: {success_count}", messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        if not obj.pk or not obj.uploader: obj.uploader = request.user
        super().save_model(request, obj, form, change)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [path('<path:object_id>/review/', self.admin_site.admin_view(self.review_view), name='matches_matchreport_review')]
        return custom_urls + urls

    def _handle_match_creation(self, report, request):
        from core.models import Team, League
        from .services.ocr_service import resolve_team_entity
        from .models import Match
        from datetime import datetime
        data = report.normalized_data or {}
        info = data.get('match_info', {})
        home_name, away_name, league_name, date_str = info.get('home_team'), info.get('away_team'), info.get('league'), info.get('date')
        target_date = None
        if date_str:
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y']:
                try: target_date = datetime.strptime(date_str, fmt).date(); break
                except: continue
        if not target_date: return False, "Data non valida."
        all_teams = Team.objects.all()
        home_team, away_team = resolve_team_entity(home_name, all_teams), resolve_team_entity(away_name, all_teams)
        if not home_team or not away_team: return False, "Squadre non risolte."
        league = League.objects.filter(name__icontains=league_name).first() if league_name else None
        match = Match.objects.create(home_team=home_team, away_team=away_team, match_date=datetime.combine(target_date, datetime.min.time()), league=league, is_finished=True, has_report=True)
        report.match = match
        report.save()
        return True, f"Match creato: {match}"

    def review_view(self, request, object_id):
        from django import forms
        from django.utils import timezone
        now = timezone.now()
        obj = get_object_or_404(MatchReport.objects.select_related('match__home_team', 'match__away_team'), id=object_id)
        if obj.in_review_by and obj.in_review_by != request.user and obj.in_review_at > (now - timezone.timedelta(minutes=30)):
            self.message_user(request, f"In lavorazione da {obj.in_review_by.username}.", messages.WARNING)
        else:
            obj.in_review_by, obj.in_review_at = request.user, now
            obj.save(update_fields=['in_review_by', 'in_review_at'])

        # Audit: log apertura review (solo GET, dedup 5 min per evitare rumore su redirect)
        if request.method == 'GET':
            recent_open = MatchReportAuditLog.objects.filter(
                report=obj, user=request.user, action='review_opened',
                created_at__gte=now - timezone.timedelta(minutes=5),
            ).exists()
            if not recent_open:
                MatchReportAuditLog.objects.create(
                    report=obj, user=request.user, action='review_opened',
                    old_status=obj.status, new_status=obj.status,
                )

        match = obj.match
        home_team, away_team = (match.home_team, match.away_team) if match else (None, None)
        
        potential_matches = []
        if not match and obj.normalized_data:
            from core.models import Team
            from .services.ocr_service import resolve_team_entity
            info = obj.normalized_data.get('match_info', {})
            all_teams = Team.objects.all()
            h_t, a_t = resolve_team_entity(info.get('home_team'), all_teams), resolve_team_entity(info.get('away_team'), all_teams)
            if h_t or a_t:
                q = models.Q()
                if h_t: q |= models.Q(home_team=h_t) | models.Q(away_team=h_t)
                if a_t: q |= models.Q(home_team=a_t) | models.Q(away_team=a_t)
                potential_matches = Match.objects.filter(q).order_by('-match_date')[:10]

        class ReviewForm(forms.ModelForm):
            class Meta:
                model = MatchReport
                fields = ['normalized_data']
                widgets = {'normalized_data': forms.Textarea(attrs={'class': 'vLargeTextField json-textarea'})}

        if request.method == 'POST':
            action = request.POST.get('_action', 'validate')
            if action == 'create_athlete':
                name, side = request.POST.get('player_name_to_create'), request.POST.get('team_side_to_create', 'home')
                if name:
                    import uuid
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    parts = name.split()
                    new_user = User.objects.create(username=f"ath_{uuid.uuid4().hex[:8]}", first_name=" ".join(parts[:-1]) if len(parts)>1 else "", last_name=parts[-1] if len(parts)>1 else name, role='athlete', setup_completed=True)
                    profile = new_user.athlete_profile
                    profile.current_team = home_team if side == 'home' else away_team
                    profile.save()
                    data = obj.normalized_data or {}
                    if 'reconciliation' not in data: data['reconciliation'] = {}
                    side_key = f"{side}_players"
                    if side_key not in data['reconciliation']: data['reconciliation'][side_key] = {}
                    data['reconciliation'][side_key][name] = new_user.id
                    obj.normalized_data = data
                    obj.save()
                    self.message_user(request, f"Atleta '{name}' creato.", messages.SUCCESS)
                    return redirect('admin:matches_matchreport_review', object_id)
            
            if action == 'bootstrap_entities' and obj.match:
                success, msg, _ = EntityBootstrapService.execute_bootstrap(obj.normalized_data, obj.match, user=request.user)
                self.message_user(request, msg, messages.SUCCESS if success else messages.ERROR)
                return redirect('admin:matches_matchreport_review', object_id)
            
            if action == 'link_match':
                m_id = request.POST.get('selected_match_id')
                if m_id:
                    obj.match = get_object_or_404(Match, id=m_id); obj.save()
                    return redirect('admin:matches_matchreport_review', object_id)

            if action == 'create_match':
                s, m = self._handle_match_creation(obj, request)
                self.message_user(request, m, messages.SUCCESS if s else messages.ERROR)
                return redirect('admin:matches_matchreport_review', object_id)

            form = ReviewForm(request.POST, instance=obj)
            if form.is_valid():
                if action == 'save_draft':
                    obj.save()
                    MatchReportAuditLog.objects.create(
                        report=obj, user=request.user, action='save_draft',
                        old_status=obj.status, new_status=obj.status,
                        reason='Salvataggio intermedio (draft) senza cambio di stato',
                    )
                    return redirect('admin:matches_matchreport_review', object_id)
                old_status = obj.status
                obj.status, obj.validated_by, obj.validated_at = MatchReport.Status.VALIDATED, request.user, timezone.now()
                obj.save()
                MatchReportAuditLog.objects.create(
                    report=obj, user=request.user, action='validate',
                    old_status=old_status, new_status=obj.status,
                )
                # publish_now / publish_force: PublishingService scrive già il proprio audit log
                # (action='publish' o 'republish'), quindi non duplichiamo qui.
                if action in ['publish_now', 'publish_force']:
                    success, msg = PublishingService.publish_report(obj, user=request.user, force=(action=='publish_force'))
                    self.message_user(request, msg, messages.SUCCESS if success else messages.WARNING)
                return redirect('admin:matches_matchreport_changelist')
        else:
            if not obj.normalized_data: obj.normalized_data = obj.raw_extracted_data
            form = ReviewForm(instance=obj)

        from difflib import SequenceMatcher
        from django.contrib.auth import get_user_model
        User = get_user_model()
        db_h = User.objects.filter(role='athlete', athlete_profile__current_team=home_team) if home_team else []
        db_a = User.objects.filter(role='athlete', athlete_profile__current_team=away_team) if away_team else []
        
        extracted = {
            "home": [p.get("name") for p in obj.normalized_data.get("teams", {}).get("home", {}).get("players", []) if p.get("name")],
            "away": [p.get("name") for p in obj.normalized_data.get("teams", {}).get("away", {}).get("players", []) if p.get("name")]
        }
        def suggestions(n, aths):
            res = []
            for a in aths:
                ratio = SequenceMatcher(None, n.lower(), a.get_full_name().lower()).ratio()
                if ratio > 0.6: res.append({"id": a.id, "name": a.get_full_name(), "score": round(ratio * 100)})
            return sorted(res, key=lambda x: x["score"], reverse=True)[:3]
            
        recon_ui = {"home": [], "away": []}
        cur_recon = obj.normalized_data.get("reconciliation", {})
        for side in ["home", "away"]:
            for n in extracted[side]:
                db_list = db_h if side == "home" else db_a
                c_id = cur_recon.get(f"{side}_players", {}).get(n)
                recon_ui[side].append({"extracted_name": n, "suggestions": suggestions(n, db_list), "current_id": c_id, "is_unresolved": not c_id, "db_athletes": [{"id": a.id, "name": a.get_full_name()} for a in db_list]})
        
        safe, blockers, p_w = OCRSchemaValidator.assess_publish_readiness(obj.normalized_data)
        gate_ctx = {}
        if match:
            if home_team:
                gate_ctx['home_team'] = home_team.society.name
            if away_team:
                gate_ctx['away_team'] = away_team.society.name
            if match.location:
                gate_ctx['location'] = match.location
        ocr_is_valid, ocr_blockers, ocr_warnings, _ = OCRQualityGate.evaluate(
            obj.normalized_data or {}, context=gate_ctx
        )
        meta = (obj.normalized_data or {}).get('metadata', {}) if isinstance(obj.normalized_data, dict) else {}
        confidence = meta.get('confidence', 0.0) or 0.0
        context = self.admin_site.each_context(request)
        context.update({'opts': self.model._meta, 'original': obj, 'title': f"Review: {obj}", 'potential_matches': potential_matches, 'form': form, 'is_image': obj.file.name.lower().endswith(('.png', '.jpg', '.jpeg')) if obj.file else False, 'reconciliation_data': recon_ui, 'publish_safe': safe, 'publish_blockers': blockers, 'unresolved_count': sum(1 for s in ["home", "away"] for item in recon_ui[s] if item["is_unresolved"]), 'bootstrap': EntityBootstrapService.preview_creation(obj.normalized_data, obj.match) if obj.match else None, 'ocr_is_valid': ocr_is_valid, 'ocr_blockers': ocr_blockers, 'ocr_warnings': ocr_warnings, 'confidence': confidence, 'confidence_percent': round(confidence * 100), 'extraction_warnings': meta.get('extraction_warnings', []), 'report_audit_logs': obj.audit_logs.select_related('user').all()})
        return TemplateResponse(request, 'admin/matches/matchreport/review.html', context)

op_admin_site.register(Match, MatchAdmin)
from core.admin import TeamAdmin, LeagueAdmin, SportAdmin, SponsorAdmin
from core.models import Sponsor
op_admin_site.register(Team, TeamAdmin)
op_admin_site.register(League, LeagueAdmin)
op_admin_site.register(Sport, SportAdmin)
op_admin_site.register(Sponsor, SponsorAdmin)
op_admin_site.register(MatchReport, MatchReportAdmin)

@admin.register(MatchReport)
class MatchReportAdminDefault(MatchReportAdmin):
    def has_module_permission(self, request): return False
@admin.register(Match)
class MatchAdminDefault(MatchAdmin):
    def has_module_permission(self, request): return False
