from django.contrib import admin
from .models import (
    Membership, AuditLog, ActivationCode, MembershipRequest,
    PilotDailyLog, PilotBug, PilotFeedback, PilotReview,
)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'society', 'team', 'role', 'is_active')
    list_filter = ('role', 'is_active', 'society')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

    def has_module_permission(self, request):
        return False


@admin.register(ActivationCode)
class ActivationCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'society', 'team', 'role', 'current_uses', 'max_uses', 'is_active', 'created_by')
    list_filter = ('society', 'is_active', 'role', 'created_by')
    search_fields = ('code',)

    def has_module_permission(self, request):
        return False


@admin.register(MembershipRequest)
class MembershipRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'society', 'team', 'role', 'status', 'created_at')
    list_filter = ('status', 'society', 'role')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

    def has_module_permission(self, request):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'society', 'action', 'target_type')
    list_filter = ('action', 'society', 'timestamp')
    readonly_fields = ('timestamp', 'user', 'society', 'action', 'target_id', 'target_type', 'details', 'ip_address')

    def has_module_permission(self, request):
        return False


# ──────────────────────────────────────────────────────────────
# PILOT OPERATIONS ADMIN
# ──────────────────────────────────────────────────────────────

@admin.register(PilotDailyLog)
class PilotDailyLogAdmin(admin.ModelAdmin):
    list_display = ('date', 'operator', 'status', 'updated_at')
    list_filter = ('status',)
    date_hierarchy = 'date'
    ordering = ('-date',)

    def has_module_permission(self, request):
        return False
    fieldsets = (
        (None, {
            'fields': ('date', 'operator', 'status')
        }),
        ('Operational Details', {
            'fields': ('blockers', 'workarounds', 'notes', 'next_day_decision'),
        }),
    )


@admin.register(PilotBug)
class PilotBugAdmin(admin.ModelAdmin):
    list_display = ('title', 'severity', 'status', 'reported_by', 'owner', 'created_at')

    def has_module_permission(self, request):
        return False
    list_filter = ('severity', 'status', 'reproducibility')
    search_fields = ('title', 'observed_behavior', 'expected_behavior')
    list_editable = ('status', 'owner')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('title', 'severity', 'status', 'reported_by', 'owner')
        }),
        ('Bug Details', {
            'fields': ('role_context', 'observed_behavior', 'expected_behavior', 'reproducibility', 'workaround'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(PilotFeedback)
class PilotFeedbackAdmin(admin.ModelAdmin):
    list_display = ('summary_short', 'category', 'source', 'status', 'owner', 'created_at')

    def has_module_permission(self, request):
        return False
    list_filter = ('category', 'status')
    search_fields = ('summary', 'source', 'flow_step')
    list_editable = ('status', 'owner')
    readonly_fields = ('created_at', 'updated_at')

    def summary_short(self, obj):
        return obj.summary[:80] + ('…' if len(obj.summary) > 80 else '')
    summary_short.short_description = 'Summary'


@admin.register(PilotReview)
class PilotReviewAdmin(admin.ModelAdmin):
    list_display = ('review_type', 'review_date', 'recommendation', 'created_by', 'created_at')

    def has_module_permission(self, request):
        return False
    list_filter = ('review_type', 'recommendation')
    readonly_fields = ('created_at',)
    fieldsets = (
        (None, {
            'fields': ('review_date', 'review_type', 'created_by', 'recommendation')
        }),
        ('Assessment', {
            'fields': ('what_worked', 'blockers_summary', 'recurring_issues', 'staff_load', 'notes'),
        }),
    )


# === Registrazioni su op_admin_site ===
# I ModelAdmin sopra hanno has_module_permission=False per nasconderli dal
# default admin.site. Le sottoclassi *OpAdmin sotto sovrascrivono quel
# metodo per essere visibili sull'op_admin_site (l'unico admin esposto
# in produzione, vedi matches/admin.py).
from matches.admin import op_admin_site


class MembershipOpAdmin(MembershipAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff


class ActivationCodeOpAdmin(ActivationCodeAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff


class MembershipRequestOpAdmin(MembershipRequestAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff


class AuditLogOpAdmin(AuditLogAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff


class PilotDailyLogOpAdmin(PilotDailyLogAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff


class PilotBugOpAdmin(PilotBugAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff


class PilotFeedbackOpAdmin(PilotFeedbackAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff


class PilotReviewOpAdmin(PilotReviewAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff


op_admin_site.register(Membership, MembershipOpAdmin)
op_admin_site.register(ActivationCode, ActivationCodeOpAdmin)
op_admin_site.register(MembershipRequest, MembershipRequestOpAdmin)
op_admin_site.register(AuditLog, AuditLogOpAdmin)
op_admin_site.register(PilotDailyLog, PilotDailyLogOpAdmin)
op_admin_site.register(PilotBug, PilotBugOpAdmin)
op_admin_site.register(PilotFeedback, PilotFeedbackOpAdmin)
op_admin_site.register(PilotReview, PilotReviewOpAdmin)
