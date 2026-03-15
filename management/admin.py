from django.contrib import admin
from .models import Membership, AuditLog

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'society', 'team', 'role', 'is_active')
    list_filter = ('role', 'is_active', 'society')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'society', 'action', 'target_type')
    list_filter = ('action', 'society', 'timestamp')
    readonly_fields = ('timestamp', 'user', 'society', 'action', 'target_id', 'target_type', 'details', 'ip_address')
