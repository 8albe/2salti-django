from django.contrib import admin
from .models import Match, MatchEvent, MatchReport, InboundEmail, SportEventConfig
from .event_types import DEFAULT_EVENT_TYPES

from .forms import MatchReportAdminForm
from core.models import Team, League, Sport
from management.models import AuditLog
from .services.ocr_service import OCRService
from .services.publishing_service import PublishingService
from .services.schema import OCRSchemaValidator
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
        """
        Force specific cross-app order on the homepage.
        1. 📄 Referti Match
        2. Partite
        3. Squadre
        4. Campionati
        5. Sport
        """
        app_list = super().get_app_list(request, app_label)
        
        operational_models = []
        for app in app_list:
            for model in app['models']:
                if model['object_name'] in ['MatchReport', 'Match', 'Team', 'League', 'Sport']:
                    operational_models.append(model)

        order_map = {
            'MatchReport': 0,
            'Match': 1,
            'Team': 2,
            'League': 3,
            'Sport': 4,
        }
        operational_models.sort(key=lambda x: order_map.get(x['object_name'], 999))

        if not operational_models:
            return []

        return [{
            'name': 'Operazioni Principali',
            'app_label': 'operations',
            'models': operational_models,
            'has_module_permission': True,
        }]

op_admin_site = OpAdminSite(name='op_admin')

class MatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'match_date', 'home_team', 'away_team', 'home_score', 'away_score', 'is_finished', 'has_report')
    list_filter = ('is_finished', 'has_report', 'league', 'match_date')
    search_fields = ('home_team__name', 'away_team__name', 'location')
    ordering = ('-match_date',)

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if obj is None:  # Add flow
            # Hide post-match fields that shouldn't be filled manually at creation
            post_match_fields = [
                'home_score', 'away_score', 'is_finished', 
                'quarter_scores', 'referees', 'has_report', 
                'is_data_verified'
            ]
            return [f for f in fields if f not in post_match_fields]
        return fields

    def has_module_permission(self, request):
        return True

class MatchReportAdmin(admin.ModelAdmin):
    form = MatchReportAdminForm
    # Task 3 & Launch Hardening: improved visibility for operators
    list_display = ('id', 'priority_label', 'status_colored', 'match_link', 'match_date', 'has_blocking_issues', 'has_warnings', 'created_at', 'review_action')
    list_filter = ('status', BlockingIssuesFilter, WarningsFilter, 'match__league', 'created_at', 'uploader', 'in_review_by')
    
    def has_blocking_issues(self, obj):
        if not obj.validation_notes: return False
        if obj.validation_notes.startswith("{"):
            return '"blocking": []' not in obj.validation_notes
        return 'Fallito' in obj.validation_notes
    has_blocking_issues.short_description = "Blocchi"
    has_blocking_issues.boolean = True

    def has_warnings(self, obj):
        if not obj.validation_notes: return False
        if obj.validation_notes.startswith("{"):
            return '"warnings": []' not in obj.validation_notes
        return 'Avvisi' in obj.validation_notes
    has_warnings.short_description = "Avvisi"
    has_warnings.boolean = True

    def get_queryset(self, request):
        from django.db.models import Case, When, Value, IntegerField, Q
        qs = super().get_queryset(request)
        return qs.annotate(
            priority=Case(
                When(Q(status='NEEDS_REVIEW') & Q(validation_notes__startswith='{') & ~Q(validation_notes__icontains='"blocking": []'), then=Value(1)),
                When(Q(status='NEEDS_REVIEW') & ~Q(validation_notes__startswith='{') & Q(validation_notes__icontains='Fallito'), then=Value(1)),
                
                When(Q(status='NEEDS_REVIEW') & Q(validation_notes__startswith='{') & ~Q(validation_notes__icontains='"warnings": []'), then=Value(2)),
                When(Q(status='NEEDS_REVIEW') & ~Q(validation_notes__startswith='{') & Q(validation_notes__icontains='Avvisi'), then=Value(2)),
                
                When(status='EXTRACTED', then=Value(3)),
                default=Value(4),
                output_field=IntegerField()
            )
        )
    
    def priority_label(self, obj):
        if obj.priority == 1:
            return format_html('<span style="color:red; font-weight:bold;">1 - Urgente (Blocchi)</span>')
        if obj.priority == 2:
            return format_html('<span style="color:orange; font-weight:bold;">2 - Media (Avvisi)</span>')
        if obj.priority == 3:
            return format_html('<span style="color:blue; font-weight:bold;">3 - Da Iniziare</span>')
        return "4 - Bassa"
    priority_label.short_description = 'Priorità'
    priority_label.admin_order_field = 'priority'
    
    def match_link(self, obj):
        from django.urls import reverse
        url = reverse('admin:matches_match_change', args=[obj.match.id])
        return format_html('<a href="{}">{}</a>', url, obj.match)
    match_link.short_description = 'Match'

    def match_date(self, obj):
        return obj.match.match_date
    match_date.short_description = 'Data Match'

    def review_action(self, obj):
        from django.urls import reverse
        url = reverse('admin:matches_matchreport_review', args=[obj.id])
        return format_html('<a class="button" href="{}" style="padding: 2px 8px; background: #0366d6; color: white; border-radius: 4px; font-size: 10px; font-weight: bold;">Review &rarr;</a>', url)
    review_action.short_description = 'Azione'
    
    readonly_fields = (
        'status', 'uploader', 'raw_extracted_data', 'validation_notes', 'created_at', 
        'updated_at', 'match', 'source_metadata', 'file_hash'
    )
    search_fields = ('match__home_team__name', 'match__away_team__name')
    actions = ['process_ocr', 'publish_reports']

    def has_module_permission(self, request):
        return True

    def changelist_view(self, request, extra_context=None):
        from django.db.models import Q
        response = super().changelist_view(request, extra_context)
        
        if hasattr(response, 'context_data'):
            try:
                qs = response.context_data['cl'].queryset
            except (AttributeError, KeyError):
                qs = self.get_queryset(request)
            
            queue_kpi = {
                'total': qs.exclude(status__in=['PUBLISHED', 'REJECTED']).count(),
                'needs_review': qs.filter(status='NEEDS_REVIEW').count(),
                'blocked': qs.filter(
                    Q(validation_notes__startswith='{') & ~Q(validation_notes__icontains='"blocking": []') |
                    ~Q(validation_notes__startswith='{') & Q(validation_notes__icontains='Fallito')
                ).count(),
                'ready_to_publish': qs.filter(status='VALIDATED').count(),
            }
            
            if extra_context is None:
                extra_context = {}
            extra_context['queue_kpi'] = queue_kpi
            response.context_data.update(extra_context)
            
        return response

    def status_colored(self, obj):
        colors = {
            'UPLOADED': 'gray',
            'PROCESSING': 'orange',
            'EXTRACTED': 'blue',
            'NEEDS_REVIEW': 'red',
            'VALIDATED': 'green',
            'PUBLISHED': 'darkgreen',
            'REJECTED': 'black',
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = 'Stato'

    @admin.action(description="Elabora OCR")
    def process_ocr(self, request, queryset):
        extracted_count = 0
        needs_review_count = 0
        skipped_count = 0
        error_count = 0
        
        for report in queryset:
            if report.status not in [MatchReport.Status.UPLOADED, MatchReport.Status.REJECTED, MatchReport.Status.NEEDS_REVIEW]:
                skipped_count += 1
                continue
            
            if OCRService.process_and_update(report):
                # Ricarichiamo per vedere lo stato finale dopo il gate
                report.refresh_from_db()
                if report.status == MatchReport.Status.EXTRACTED:
                    extracted_count += 1
                elif report.status == MatchReport.Status.NEEDS_REVIEW:
                    needs_review_count += 1
                else:
                    extracted_count += 1 # Default success
            else:
                error_count += 1
        
        if extracted_count:
            self.message_user(request, f"Estraiti con successo {extracted_count} referti.", messages.SUCCESS)
        if needs_review_count:
            self.message_user(request, f"{needs_review_count} referti pronti ma con problemi di qualità (NEEDS_REVIEW).", messages.WARNING)
        if skipped_count:
            self.message_user(request, f"{skipped_count} referti saltati (già processati).", messages.WARNING)
        if error_count:
            self.message_user(request, f"Errore tecnico durante l'elaborazione di {error_count} referti.", messages.ERROR)

    @admin.action(description="Pubblica Referti (VALIDATED -> PUBLISHED)")
    def publish_reports(self, request, queryset):
        success_count = 0
        error_count = 0
        skipped_count = 0
        for report in queryset:
            if report.status != MatchReport.Status.VALIDATED:
                skipped_count += 1
                continue
            success, msg = PublishingService.publish_report(report, user=request.user)
            if success:
                success_count += 1
            else:
                self.message_user(request, f"Errore ID {report.id}: {msg}", messages.WARNING)
                error_count += 1
        if success_count:
            self.message_user(request, f"Pubblicati con successo {success_count} referti.", messages.SUCCESS)
        if skipped_count:
            self.message_user(request, f"{skipped_count} referti saltati (non in stato VALIDO).", messages.WARNING)

    def save_model(self, request, obj, form, change):
        if not obj.pk or not obj.uploader:
            obj.uploader = request.user
        super().save_model(request, obj, form, change)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/review/', self.admin_site.admin_view(self.review_view), name='matches_matchreport_review'),
        ]
        return custom_urls + urls

    def review_view(self, request, object_id):
        from django import forms
        from django.utils import timezone
        now = timezone.now()
        timeout = now - timezone.timedelta(minutes=30)
        
        obj = get_object_or_404(MatchReport, pk=object_id)
        
        # Soft-lock logic
        if obj.in_review_by and obj.in_review_by != request.user and obj.in_review_at > timeout:
            self.message_user(request, f"⚠️ ATTENZIONE: Questo referto è già in lavorazione da {obj.in_review_by.username} (preso il {obj.in_review_at.strftime('%H:%M')}).", messages.WARNING)
        else:
            # Prendi o rinfresca il lock (ogni 5 min per efficienza)
            if not obj.in_review_by or obj.in_review_by != request.user or obj.in_review_at < (now - timezone.timedelta(minutes=5)):
                obj.in_review_by = request.user
                obj.in_review_at = now
                obj.save(update_fields=['in_review_by', 'in_review_at'])
        class ReviewForm(forms.ModelForm):
            class Meta:
                model = MatchReport
                fields = ['normalized_data']
                widgets = {
                    'normalized_data': forms.Textarea(attrs={'class': 'vLargeTextField json-textarea'}),
                }
            def clean_normalized_data(self):
                data = self.cleaned_data.get('normalized_data')
                if data:
                    success, msg = OCRSchemaValidator.validate(data)
                    if not success:
                        raise forms.ValidationError(f"Schema JSON non valido: {msg}")
                return data

        if request.method == 'POST':
            # Handle bootstrap action BEFORE form validation (no form fields needed)
            action = request.POST.get('_action', 'validate')
            reason_message = request.POST.get('reason_message', '').strip()
            if action == 'bootstrap_entities':
                data = obj.normalized_data or {}
                success, msg, boot_warnings = EntityBootstrapService.execute_bootstrap(
                    data, obj.match, user=request.user
                )
                if success:
                    self.message_user(request, f"Bootstrap completato: {msg}", messages.SUCCESS)
                else:
                    self.message_user(request, f"Bootstrap fallito: {msg}", messages.ERROR)
                for w in boot_warnings:
                    self.message_user(request, f"⚠️ {w}", messages.WARNING)
                return redirect('admin:matches_matchreport_review', object_id)

            form = ReviewForm(request.POST, instance=obj)
            if form.is_valid():
                from django.utils import timezone
                
                old_obj = MatchReport.objects.get(pk=obj.pk)
                previous_status = old_obj.status
                b_data = old_obj.normalized_data or {}
                a_data = form.cleaned_data.get('normalized_data') or {}

                def _create_audit_log(report_obj, user, action_name, b_json, a_json, old_status='', new_status='', reason=''):
                    from .models import MatchReportAuditLog
                    from django.utils import timezone
                    diff_b = {}
                    diff_a = {}
                    
                    # Base diff calculation
                    if a_json and b_json:
                        for k, v in a_json.items():
                            if b_json.get(k) != v:
                                diff_b[k] = b_json.get(k)
                                diff_a[k] = v
                    elif a_json:
                        diff_a = a_json
                    elif b_json:
                        diff_b = b_json
                        
                    # Pilot Metrics Enrichment for Publish
                    if action_name in ['publish_now', 'publish_force']:
                        # Calculate Duration
                        first_open = MatchReportAuditLog.objects.filter(report=report_obj, action='review_opened').order_by('created_at').first()
                        duration = 0
                        if first_open:
                            duration = (timezone.now() - first_open.created_at).total_seconds()
                        
                        # Calculate Reconciliation Stats
                        total_players = 0
                        matched = 0
                        auto_matched_at_start = 0
                        
                        if first_open and first_open.after:
                            auto_matched_at_start = first_open.after.get('auto_matched', 0)
                        
                        recon = a_json.get('reconciliation', {}) if a_json else {}
                        for side in ['home', 'away']:
                            players = a_json.get('teams', {}).get(side, {}).get('players', []) if a_json else []
                            total_players += len(players)
                            recon_side = recon.get(f"{side}_players", {})
                            matched += sum(1 for p in players if recon_side.get(p.get('name')))
                        
                        diff_a['_metrics'] = {
                            'duration_seconds': round(duration, 2),
                            'total_players': total_players,
                            'final_matched': matched,
                            'auto_matched_at_start': auto_matched_at_start,
                            'manual_fixes': max(0, matched - auto_matched_at_start),
                            'is_forced': action_name == 'publish_force'
                        }

                    if diff_b or diff_a or old_status != new_status or action_name in ['validate', 'publish_now', 'publish_force', 'save_draft']:
                        MatchReportAuditLog.objects.create(
                            report=report_obj, user=user, action=action_name,
                            old_status=old_status or '', new_status=new_status or '',
                            reason=reason or '',
                            before=diff_b, after=diff_a
                        )
                
                if obj.status == MatchReport.Status.PUBLISHED and action in ['save_draft', 'validate']:
                    self.message_user(request, "MODIFICA BLOCCATA: Un referto già pubblicato non può essere retrocesso o salvato in bozza. Usa 'Valida & Pubblica Ora' per mantenere la coerenza statistica.", messages.ERROR)
                    return redirect('admin:matches_matchreport_review', object_id)

                report = form.save(commit=False)
                if action == 'create_athlete':
                    player_name = request.POST.get('player_name_to_create', '').strip()
                    side = request.POST.get('team_side_to_create', 'home')
                    if player_name:
                        import uuid
                        from django.contrib.auth import get_user_model
                        User = get_user_model()
                        parts = player_name.split()
                        if len(parts) > 1:
                            first_name = " ".join(parts[:-1])
                            last_name = parts[-1]
                        else:
                            first_name = ""
                            last_name = player_name
                        unique_id = str(uuid.uuid4())[:8]
                        new_user = User.objects.create(
                            username=f"ath_{unique_id}",
                            first_name=first_name,
                            last_name=last_name,
                            role='athlete',
                            setup_completed=True
                        )
                        team = obj.match.home_team if side == 'home' else obj.match.away_team
                        profile = new_user.athlete_profile
                        profile.current_team = team
                        profile.save()
                        data = form.cleaned_data.get('normalized_data', obj.normalized_data)
                        if not data or not isinstance(data, dict):
                            data = obj.normalized_data or {}
                        if 'reconciliation' not in data:
                            data['reconciliation'] = {}
                        side_key = f"{side}_players"
                        if side_key not in data['reconciliation']:
                            data['reconciliation'][side_key] = {}
                        data['reconciliation'][side_key][player_name] = new_user.id
                        obj.normalized_data = data
                        obj.save()
                        self.message_user(request, f"Atleta '{player_name}' creato e associato al team {team}.", messages.SUCCESS)
                        return redirect('admin:matches_matchreport_review', object_id)
                if action == 'save_draft':
                    report.save()
                    _create_audit_log(report, request.user, 'save_draft', b_data, a_data,
                                      old_status=previous_status, new_status=previous_status, reason=reason_message)
                    self.message_user(request, f"Bozza del referto {report.id} salvata.", messages.SUCCESS)
                    return redirect('admin:matches_matchreport_review', object_id)
                report.status = MatchReport.Status.VALIDATED
                report.validated_by = request.user
                report.validated_at = timezone.now()
                report.save()
                
                if action in ['publish_now', 'publish_force']:
                    force = (action == 'publish_force')
                    _create_audit_log(report, request.user, action, b_data, a_data,
                                      old_status=previous_status, new_status='PUBLISHED', reason=reason_message)
                    success, msg = PublishingService.publish_report(report, user=request.user, force=force, reason=reason_message)
                    if success:
                        # Clear lock on publish
                        report.in_review_by = None
                        report.in_review_at = None
                        report.save(update_fields=['in_review_by', 'in_review_at'])
                        self.message_user(request, f"Referto {report.id}: {msg}", messages.SUCCESS)
                    else:
                        self.message_user(request, f"Referto {report.id} validato, ma pubblicazione fallita: {msg}", messages.WARNING)
                else:
                    _create_audit_log(report, request.user, 'validate', b_data, a_data,
                                      old_status=previous_status, new_status='VALIDATED', reason=reason_message)
                    self.message_user(request, f"Referto {report.id} validato con successo.", messages.SUCCESS)
                return redirect('admin:matches_matchreport_changelist')
        else:
            if not obj.normalized_data or obj.normalized_data == {}:
                obj.normalized_data = obj.raw_extracted_data
            
            # PILOT METRICS: Track first opening of review
            if obj.status == MatchReport.Status.NEEDS_REVIEW:
                from .models import MatchReportAuditLog
                if not MatchReportAuditLog.objects.filter(report=obj, action='review_opened').exists():
                    total_ocr_players = 0
                    auto_matched = 0
                    data = obj.normalized_data or {}
                    recon = data.get('reconciliation', {})
                    for side in ['home', 'away']:
                        players = data.get('teams', {}).get(side, {}).get('players', [])
                        total_ocr_players += len(players)
                        recon_side = recon.get(f"{side}_players", {})
                        auto_matched += sum(1 for p in players if recon_side.get(p.get('name')))
                    
                    MatchReportAuditLog.objects.create(
                        report=obj, 
                        user=request.user, 
                        action='review_opened',
                        after={
                            'total_players': total_ocr_players,
                            'auto_matched': auto_matched,
                            'unresolved': total_ocr_players - auto_matched,
                            'timestamp': timezone.now().isoformat()
                        }
                    )

            form = ReviewForm(instance=obj)

        is_coherent, warnings = OCRSchemaValidator.validate_coherence(obj.normalized_data)
        from django.contrib.auth import get_user_model
        from difflib import SequenceMatcher
        User = get_user_model()
        home_team = obj.match.home_team
        away_team = obj.match.away_team
        db_home_athletes = User.objects.filter(role='athlete', athlete_profile__current_team=home_team) if home_team else []
        db_away_athletes = User.objects.filter(role='athlete', athlete_profile__current_team=away_team) if away_team else []
        extracted_names = {
            "home": [p.get("name") for p in obj.normalized_data.get("teams", {}).get("home", {}).get("players", []) if p.get("name")],
            "away": [p.get("name") for p in obj.normalized_data.get("teams", {}).get("away", {}).get("players", []) if p.get("name")]
        }
        def get_suggestions(extracted_name, db_athletes):
            suggestions = []
            for athlete in db_athletes:
                full_name = athlete.get_full_name().lower()
                ratio = SequenceMatcher(None, extracted_name.lower(), full_name).ratio()
                if ratio > 0.6:
                    suggestions.append({
                        "id": athlete.id,
                        "name": athlete.get_full_name(),
                        "score": round(ratio * 100)
                    })
            return sorted(suggestions, key=lambda x: x["score"], reverse=True)[:3]
        reconciliation_data = {"home": [], "away": []}
        current_recon = obj.normalized_data.get("reconciliation", {})
        for side in ["home", "away"]:
            for name in extracted_names[side]:
                db_list = db_home_athletes if side == "home" else db_away_athletes
                current_id = current_recon.get(f"{side}_players", {}).get(name)
                reconciliation_data[side].append({
                    "extracted_name": name,
                    "suggestions": get_suggestions(name, db_list),
                    "current_id": current_id,
                    "is_unresolved": not current_id,
                    "db_athletes": [{"id": a.id, "name": a.get_full_name()} for a in db_list]
                })
        
        unresolved_count = sum(1 for side in ["home", "away"] for item in reconciliation_data[side] if item["is_unresolved"])
        events = obj.normalized_data.get('events', [])
        total_events_with_player = sum(1 for e in events if e.get('player') or e.get('player_name'))
        player_map = {}
        for side_key in ["home_players", "away_players"]:
            player_map.update(current_recon.get(side_key, {}))
        reconciled_count = sum(1 for e in events if (e.get('player') or e.get('player_name')) in player_map)
        reconciliation_stats = {
            'total': total_events_with_player,
            'reconciled': reconciled_count,
            'percent': int((reconciled_count / total_events_with_player * 100)) if total_events_with_player > 0 else 100,
            'is_complete': reconciled_count == total_events_with_player
        }
        meta = obj.raw_extracted_data.get("metadata", {})
        confidence = meta.get("confidence", 0.0)
        confidence_fields = meta.get("confidence_fields", {})
        extraction_warnings = meta.get("extraction_warnings", [])
        safe, blockers, pub_warnings = OCRSchemaValidator.assess_publish_readiness(obj.normalized_data)
        
        # OCR Quality Gate evaluation
        from .services.ocr_quality_gate import OCRQualityGate
        ocr_is_valid, ocr_blockers, ocr_warnings, ocr_info = OCRQualityGate.evaluate(obj.normalized_data)

        # Entity bootstrap detection
        bootstrap = EntityBootstrapService.preview_creation(obj.normalized_data, obj.match)
        context = self.admin_site.each_context(request)
        is_image = False
        if obj.file and obj.file.name:
            is_image = obj.file.name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))
        # Operational History (AuditLogs)
        publish_history = AuditLog.objects.filter(
            target_id=str(obj.id), 
            target_type="MatchReport",
            action__in=["PUBLISH_REPORT", "REPUBLISH_REPORT"]
        ).select_related('user').order_by('-timestamp')

        # Full Audit Trail (MatchReportAuditLog)
        from .models import MatchReportAuditLog
        report_audit_logs = MatchReportAuditLog.objects.filter(
            report=obj
        ).select_related('user').order_by('-created_at')[:50]

        # Discovery dei tipi di evento supportati
        # Defaults centralized in matches/event_types.py
        event_types = [dict(e) for e in DEFAULT_EVENT_TYPES]

        # Arricchimento da DB se presenti configurazioni specifiche
        db_configs = SportEventConfig.objects.filter(sport=obj.match.league.sport) if obj.match.league else []
        for conf in db_configs:
            if conf.event_code not in [e['code'] for e in event_types]:
                event_types.append({'code': conf.event_code, 'label': conf.label})

        # Lista nomi estratti pulita per i dropdown
        roster_names = {
            'home': extracted_names['home'],
            'away': extracted_names['away']
        }

        context.update({
            'opts': self.model._meta,
            'original': obj,
            'title': f"Review OCR: {obj}",
            'form': form,
            'raw_data_json': obj.raw_api_response or json.dumps(obj.raw_extracted_data, indent=4, ensure_ascii=False),
            'is_image': is_image,
            'coherence_warnings': warnings,
            'reconciliation_data': reconciliation_data, 
            'rec_stats': reconciliation_stats,
            'confidence': confidence,
            'confidence_percent': int(confidence * 100),
            'confidence_fields': confidence_fields,
            'extraction_warnings': extraction_warnings,
            'publish_safe': safe,
            'publish_blockers': blockers,
            'publish_warnings': pub_warnings,
            'bootstrap': bootstrap,
            'ocr_is_valid': ocr_is_valid,
            'ocr_blockers': ocr_blockers,
            'ocr_warnings': ocr_warnings,
            'ocr_info': ocr_info,
            'publish_history': publish_history,
            'event_types': event_types,
            'roster_names': roster_names,
            'unresolved_count': unresolved_count,
            'report_audit_logs': report_audit_logs,
        })
        return TemplateResponse(request, 'admin/matches/matchreport/review.html', context)

# Registrations on the Operational Admin Site (Task 2: Specific Order)
op_admin_site.register(Match, MatchAdmin)
from core.admin import TeamAdmin, LeagueAdmin, SportAdmin
op_admin_site.register(Team, TeamAdmin)
op_admin_site.register(League, LeagueAdmin)
op_admin_site.register(Sport, SportAdmin)
op_admin_site.register(MatchReport, MatchReportAdmin)

# Hide from default admin for double security
@admin.register(MatchReport)
class MatchReportAdminDefault(MatchReportAdmin):
    def has_module_permission(self, request): return False
@admin.register(Match)
class MatchAdminDefault(MatchAdmin):
    def has_module_permission(self, request): return False
