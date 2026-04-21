from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

class User(AbstractUser):
    """Utente base - tutti si registrano qui"""
    ROLE_CHOICES = [
        ('athlete', 'Atleta'),
        ('coach', 'Allenatore'),
        ('referee', 'Arbitro'),
        ('fan', 'Genitore/Fan'),
        ('president', 'Presidente Società'),
    ]
    
    # Campi base
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    
    # RBAC Granulare per Staff
    STAFF_ROLE_CHOICES = [
        ('NONE', 'Nessuno'),
        ('UPLOADER', 'Collaboratore (Solo Upload)'),
        ('REVIEWER', 'Reviewer (Edit/Validazione)'),
        ('PUBLISHER', 'Publisher (Pubblicazione)'),
        ('SUPERADMIN', 'Super Amministratore'),
    ]
    staff_role = models.CharField(max_length=20, choices=STAFF_ROLE_CHOICES, default='NONE')
    
    birth_date = models.DateField(null=True, blank=True)

    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    bio = models.TextField(blank=True, help_text="Biografia personale")
    phone = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    
    # Setup wizard
    setup_completed = models.BooleanField(default=False, help_text="Ha completato il wizard di setup?")
    
    @property
    def can_upload(self):
        return self.staff_role in ['UPLOADER', 'REVIEWER', 'PUBLISHER', 'SUPERADMIN'] or self.is_superuser
    
    @property
    def can_review(self):
        return self.staff_role in ['REVIEWER', 'PUBLISHER', 'SUPERADMIN'] or self.is_superuser
        
    @property
    def can_publish(self):
        return self.staff_role in ['PUBLISHER', 'SUPERADMIN'] or self.is_superuser

    
    # Stato Onboarding e Pagamenti
    IDENTITY_STATUS_CHOICES = [
        ('UNVERIFIED', 'Non verificato'),
        ('VERIFIED', 'Verificato'),
    ]
    SUBSCRIPTION_STATUS_CHOICES = [
        ('INACTIVE', 'Inattivo'),
        ('ACTIVE', 'Attivo'),
    ]
    identity_status = models.CharField(max_length=20, choices=IDENTITY_STATUS_CHOICES, default='UNVERIFIED')
    identity_verified_at = models.DateTimeField(null=True, blank=True)
    subscription_status = models.CharField(max_length=20, choices=SUBSCRIPTION_STATUS_CHOICES, default='INACTIVE')
    subscription_end_date = models.DateTimeField(null=True, blank=True)
    
    # Preferenze (per TUTTI i ruoli - anche atleti/allenatori possono seguire altre squadre)
    favorite_teams = models.ManyToManyField('core.Team', blank=True, related_name='followers')
    favorite_players = models.ManyToManyField('self', blank=True, related_name='fans', symmetrical=False)
    
    @property
    def is_verified(self):
        return self.identity_status == 'VERIFIED'
    
    @property
    def onboarding_state(self):
        """Ritorna lo stato attuale dell'avanzamento utente (SPID -> Pagamento -> Setup -> Member)"""
        # Step 1: Identity (SPID/CIE) - Obbligatorio per tutti
        if self.identity_status != 'VERIFIED':
            return 'IDENTITY_PENDING'
        
        # Step 2: Payment (Subscription)
        # I Fan sono esenti dall'abbonamento PRO per ora
        if self.role != 'fan' and self.subscription_status != 'ACTIVE':
            return 'PAYMENT_PENDING'
        
        # Step 3: Profile Setup (Dati anagrafici minimi e foto)
        if not self.setup_completed:
            return 'SETUP_PENDING'
        
        # Step 4: Membership / Society Association
        # Solo per atleti, coach e presidenti (i fan sono subito completati)
        if self.role in ['athlete', 'coach']:
            # L'utente è a posto se ha ALMENO una di queste:
            # - Una membership attiva (già parte di una squadra)
            # - Un claim profilo in attesa di approvazione
            # - Una richiesta di membership (manuale) in attesa di approvazione
            has_membership = self.memberships.filter(is_active=True).exists()
            has_pending_claim = self.profile_links.filter(status='PENDING').exists()
            has_pending_membership = self.membership_requests.filter(status='PENDING').exists()
            
            if not has_membership and not has_pending_claim and not has_pending_membership:
                return 'MEMBERSHIP_PENDING'
        
        if self.role == 'president':
            # Il presidente deve avere una società associata (creata o assegnata)
            has_society = hasattr(self, 'president_profile') and self.president_profile.managed_society
            if not has_society:
                return 'MEMBERSHIP_PENDING'
                
        return 'COMPLETED'

    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


# PROFILI SPECIFICI PER RUOLO (creati automaticamente via signals)

class AthleteProfile(models.Model):
    """Profilo atleta - dati personali + statistiche auto-generate"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='athlete_profile')
    
    # DATI COMPILATI DALL'ATLETA
    height = models.IntegerField(null=True, blank=True, help_text="Altezza in cm")
    weight = models.IntegerField(null=True, blank=True, help_text="Peso in kg")
    position = models.CharField(max_length=50, blank=True, help_text="Es: Portiere, Centroboa, Ala")
    jersey_number = models.IntegerField(null=True, blank=True, help_text="Numero maglia")
    current_team = models.ForeignKey('core.Team', on_delete=models.SET_NULL, null=True, blank=True, related_name='athletes')
    
    # STATISTICHE AUTO-GENERATE (da AI che legge referti)
    total_goals = models.IntegerField(default=0)
    total_matches = models.IntegerField(default=0)
    total_expulsions = models.IntegerField(default=0)
    
    def update_stats(self):
        """Metodo chiamato dopo inserimento match events"""
        from matches.models import MatchEvent
        from matches.event_types import EVENT_TYPE_GOAL, EVENT_TYPE_PENALTY_GOAL, EVENT_TYPE_EXCLUSION_20, EVENT_TYPE_EXCLUSION_DEF
        
        self.total_goals = MatchEvent.objects.filter(
            player=self.user, 
            event_type__in=[EVENT_TYPE_GOAL, EVENT_TYPE_PENALTY_GOAL]
        ).count()
        
        self.total_expulsions = MatchEvent.objects.filter(
            player=self.user, 
            event_type__in=[EVENT_TYPE_EXCLUSION_20, EVENT_TYPE_EXCLUSION_DEF]
        ).count()
        
        self.total_matches = MatchEvent.objects.filter(
            player=self.user
        ).values('match').distinct().count()
        
        self.save()
    
    def __str__(self):
        return f"Atleta: {self.user.get_full_name()}"


class CoachProfile(models.Model):
    """Profilo allenatore"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='coach_profile')
    
    SPECIALIZATION_CHOICES = [
        ('portieri', 'Portieri'),
        ('attacco', 'Attacco'),
        ('difesa', 'Difesa'),
        ('atletica', 'Preparazione Atletica'),
        ('tattica', 'Tattica'),
        ('giovanile', 'Settore Giovanile'),
        ('altro', 'Altro'),
    ]
    
    current_team = models.ForeignKey('core.Team', on_delete=models.SET_NULL, null=True, blank=True, related_name='coaches')
    years_experience = models.IntegerField(null=True, blank=True)
    specialization = models.CharField(max_length=100, blank=True, choices=SPECIALIZATION_CHOICES)
    specialization_other = models.CharField(max_length=100, blank=True, help_text="Specifica se hai scelto Altro")
    
    def __str__(self):
        return f"Coach: {self.user.get_full_name()}"


class RefereeProfile(models.Model):
    """Profilo arbitro"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='referee_profile')
    
    LICENSE_LEVEL_CHOICES = [
        ('regionale', 'Regionale'),
        ('interregionale', 'Interregionale'),
        ('nazionale', 'Nazionale'),
        ('internazionale', 'Internazionale'),
        ('altro', 'Altro'),
    ]
    
    license_number = models.CharField(max_length=50, blank=True)
    license_level = models.CharField(max_length=50, blank=True, choices=LICENSE_LEVEL_CHOICES)
    license_level_other = models.CharField(max_length=100, blank=True, help_text="Specifica se hai scelto Altro")
    
    # Auto-calcolato
    total_matches_officiated = models.IntegerField(default=0)
    
    def update_stats(self):
        """Conta partite arbitrate"""
        from matches.models import Match
        self.total_matches_officiated = Match.objects.filter(referees=self.user).count()
        self.save()
    
    def __str__(self):
        return f"Arbitro: {self.user.get_full_name()}"


class PresidentProfile(models.Model):
    """Profilo presidente - crea e gestisce la società"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='president_profile')
    managed_society = models.OneToOneField('core.Society', on_delete=models.SET_NULL, null=True, blank=True, related_name='president')
    
    since_year = models.IntegerField(null=True, blank=True, help_text="Anno inizio mandato")
    
    def __str__(self):
        return f"Presidente: {self.user.get_full_name()}"


class AccountProfileLink(models.Model):
    """
    Collega un account User a un profilo sportivo esistente (Athlete, Coach, Referee).
    Fase 4 dell'onboarding.
    """
    STATUS_CHOICES = [
        ('PENDING', 'In attesa'),
        ('APPROVED', 'Approvato'),
        ('REJECTED', 'Rifiutato'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='profile_links')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    notes = models.TextField(blank=True, default="", help_text="Note sulla richiesta")
    
    # Riferimenti ai profili (uno di questi sarà popolato)
    athlete_profile = models.ForeignKey(AthleteProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='account_links')
    coach_profile = models.ForeignKey(CoachProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='account_links')
    referee_profile = models.ForeignKey(RefereeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='account_links')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        profile = self.athlete_profile or self.coach_profile or self.referee_profile
        return f"Link: {self.user.username} -> {profile} [{self.get_status_display()}]"

    class Meta:
        verbose_name = "Collegamento Profilo"
        verbose_name_plural = "Collegamenti Profilo"
        unique_together = ['user', 'athlete_profile', 'coach_profile', 'referee_profile']


# SIGNALS: Crea automaticamente il profilo specifico quando un utente si registra
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.role == 'athlete':
            AthleteProfile.objects.create(user=instance)
        elif instance.role == 'coach':
            CoachProfile.objects.create(user=instance)
        elif instance.role == 'referee':
            RefereeProfile.objects.create(user=instance)
        elif instance.role == 'president':
            PresidentProfile.objects.create(user=instance)
