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
    birth_date = models.DateField(null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    bio = models.TextField(blank=True, help_text="Biografia personale")
    phone = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    
    # Setup wizard
    setup_completed = models.BooleanField(default=False, help_text="Ha completato il wizard di setup?")
    
    # Preferenze (per TUTTI i ruoli - anche atleti/allenatori possono seguire altre squadre)
    favorite_teams = models.ManyToManyField('core.Team', blank=True, related_name='followers')
    favorite_players = models.ManyToManyField('self', blank=True, related_name='fans', symmetrical=False)
    
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
        self.total_goals = MatchEvent.objects.filter(player=self.user, event_type='GOAL').count()
        self.total_expulsions = MatchEvent.objects.filter(player=self.user, event_type='EXPULSION').count()
        self.total_matches = MatchEvent.objects.filter(player=self.user).values('match').distinct().count()
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
