from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, AthleteProfile, CoachProfile, RefereeProfile, PresidentProfile, AccountProfileLink

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'identity_status', 'subscription_status', 'is_staff')
    list_filter = ('role', 'identity_status', 'subscription_status', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)

    def has_module_permission(self, request):
        return False

    # Aggiungiamo i campi personalizzati ai fieldset esistenti
    fieldsets = UserAdmin.fieldsets + (
        ('Onboarding & Status', {
            'fields': (
                'role',
                'identity_status',
                'identity_verified_at',
                'subscription_status',
                'subscription_end_date',
                'setup_completed',
            ),
        }),
        ('Dati Personali Extra', {
            'fields': ('birth_date', 'profile_picture', 'bio', 'phone', 'city'),
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Informazioni Base', {
            'fields': ('role', 'email', 'first_name', 'last_name'),
        }),
    )

@admin.register(AthleteProfile)
class AthleteProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'current_team', 'position', 'total_goals', 'total_matches')
    list_filter = ('position', 'current_team')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

    def has_module_permission(self, request):
        return False

@admin.register(CoachProfile)
class CoachProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'current_team', 'specialization', 'years_experience')
    list_filter = ('specialization', 'current_team')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

    def has_module_permission(self, request):
        return False

@admin.register(RefereeProfile)
class RefereeProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'license_level', 'license_number', 'total_matches_officiated')
    list_filter = ('license_level',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'license_number')

    def has_module_permission(self, request):
        return False

@admin.register(PresidentProfile)
class PresidentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'managed_society', 'since_year')
    search_fields = ('user__username', 'managed_society__name')

    def has_module_permission(self, request):
        return False
@admin.register(AccountProfileLink)
class AccountProfileLinkAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_target_profile', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

    def has_module_permission(self, request):
        return False
    
    def get_target_profile(self, obj):
        return obj.athlete_profile or obj.coach_profile or obj.referee_profile
    get_target_profile.short_description = 'Profilo Target'
