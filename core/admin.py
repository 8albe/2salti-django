from django.contrib import admin, messages
from .models import Sport, Society, Team, League, LeagueStanding, Season, Sponsor

@admin.register(LeagueStanding)
class LeagueStandingAdmin(admin.ModelAdmin):
    list_display = ('rank', 'team', 'league', 'points', 'played', 'won', 'drawn', 'lost', 'goal_diff', 'last_updated')
    list_filter = ('league', 'season')
    search_fields = ('team__name', 'league__name')
    ordering = ('league', 'rank')
    readonly_fields = ('last_updated',)

    def has_module_permission(self, request):
        return False

@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'hex_color')
    readonly_fields = ('slug',)

@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('sport', 'label', 'is_current')
    list_filter = ('sport', 'is_current')

@admin.register(Society)
class SocietyAdmin(admin.ModelAdmin):
    list_display = ('name', 'sport', 'city', 'setup_completed', 'tier', 'is_comped')
    list_filter = ('sport', 'setup_completed', 'tier', 'is_comped', 'city')
    search_fields = ('name', 'city')
    # tier è SOLO in lettura: si cambia via le action (seam) per garantire l'audit.
    # is_comped resta editabile (usato dai seed pilota) ma le action lo instradano nel seam.
    readonly_fields = ('slug', 'tier')
    actions = ['attiva_club_pro', 'disattiva_club_pro', 'attiva_comped', 'disattiva_comped']

    def has_module_permission(self, request):
        return False

    @admin.action(description="Attiva Club Pro (tier, via seam)")
    def attiva_club_pro(self, request, queryset):
        from core.services.entitlement_service import set_society_tier
        for society in queryset:
            set_society_tier(society, Society.Tier.CLUB_PRO, source='admin',
                             actor=request.user, request=request)
        self.message_user(request, f"Club Pro attivato per {queryset.count()} società.", messages.SUCCESS)

    @admin.action(description="Disattiva Club Pro (tier, via seam)")
    def disattiva_club_pro(self, request, queryset):
        from core.services.entitlement_service import set_society_tier
        for society in queryset:
            set_society_tier(society, Society.Tier.FREE, source='admin',
                             actor=request.user, request=request)
        self.message_user(request, f"Club Pro disattivato per {queryset.count()} società.", messages.SUCCESS)

    @admin.action(description="Concedi comped (Club Pro gratis, via seam)")
    def attiva_comped(self, request, queryset):
        from core.services.entitlement_service import set_society_comped
        for society in queryset:
            set_society_comped(society, True, source='admin', actor=request.user, request=request)
        self.message_user(request, f"Comped concesso a {queryset.count()} società.", messages.SUCCESS)

    @admin.action(description="Revoca comped (via seam)")
    def disattiva_comped(self, request, queryset):
        from core.services.entitlement_service import set_society_comped
        for society in queryset:
            set_society_comped(society, False, source='admin', actor=request.user, request=request)
        self.message_user(request, f"Comped revocato a {queryset.count()} società.", messages.SUCCESS)

@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = ('name', 'society', 'season', 'order', 'is_active')
    list_filter = ('season', 'is_active', 'society')
    search_fields = ('name', 'society__name')
    ordering = ('society', 'season', 'order')


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'society', 'league')
    list_filter = ('society', 'league')
    search_fields = ('name', 'society__name')
    readonly_fields = ('slug',)

@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'sport', 'league_type', 'season', 'group_name', 'status_integrita')
    list_filter = ('sport', 'league_type', 'season')
    search_fields = ('name', 'group_name')
    prepopulated_fields = {}
    readonly_fields = ('slug', 'needs_rebuild', 'status_integrita')
    
    def status_integrita(self, obj):
        from matches.services.integrity_service import DataIntegrityService
        from django.utils.html import format_html
        
        issues = DataIntegrityService.check_league_standings(obj)
        if not issues:
            return format_html('<span style="color: green;">✔ OK</span>')
        return format_html('<span style="color: red;">✘ {} Errori</span>', len(issues))
    status_integrita.short_description = 'Stato Integrità'
