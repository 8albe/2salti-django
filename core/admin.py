from django.contrib import admin
from .models import Sport, Society, Team, League, LeagueStanding

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

@admin.register(Society)
class SocietyAdmin(admin.ModelAdmin):
    list_display = ('name', 'sport', 'city', 'setup_completed')
    list_filter = ('sport', 'setup_completed', 'city')
    search_fields = ('name', 'city')
    readonly_fields = ('slug',)

    def has_module_permission(self, request):
        return False

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'society', 'category', 'league')
    list_filter = ('category', 'society', 'league')
    search_fields = ('name', 'society__name')
    readonly_fields = ('slug',)

@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'sport', 'category', 'season', 'group_name', 'status_integrita')
    list_filter = ('sport', 'category', 'season')
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
