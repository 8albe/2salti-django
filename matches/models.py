from django.db import models
from django.contrib.auth import get_user_model
from core.models import Team, League

User = get_user_model()


class Match(models.Model):
    """Partita - dati inseriti manualmente o da AI (futuro)"""
    # Contesto
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='matches')
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_matches')
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_matches')
    
    # Data e luogo
    match_date = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True, help_text="Piscina/Palazzetto")
    
    # Risultato (null se partita non ancora giocata)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    is_finished = models.BooleanField(default=False)
    
    # Arbitri (many-to-many perché possono essere 2-3)
    referees = models.ManyToManyField(User, blank=True, limit_choices_to={'role': 'referee'}, related_name='officiated_matches')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # AI fields (per futuro OCR)
    referee_report_uploaded = models.BooleanField(default=False)
    ai_processed = models.BooleanField(default=False)
    
    @property
    def google_maps_url(self):
        """Genera link google maps per la location"""
        if not self.location:
            return None
        import urllib.parse
        query = urllib.parse.quote(self.location)
        return f"https://www.google.com/maps/search/?api=1&query={query}"

    def __str__(self):
        score = f"{self.home_score}-{self.away_score}" if self.is_finished else "vs"
        return f"{self.home_team} {score} {self.away_team} ({self.match_date.strftime('%d/%m/%Y')})"
    
    class Meta:
        ordering = ['-match_date']
        verbose_name_plural = "Matches"


class MatchEvent(models.Model):
    """Evento durante una partita (gol, espulsione, timeout)"""
    EVENT_TYPE_CHOICES = [
        ('GOAL', 'Gol'),
        ('EXPULSION', 'Espulsione'),
        ('TIMEOUT', 'Timeout'),
    ]
    
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    
    # Chi (può essere null per timeout squadra)
    player = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'role': 'athlete'}, related_name='match_events')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='match_events')
    
    # Quando
    minute = models.IntegerField(help_text="Minuto di gioco")
    quarter = models.IntegerField(default=1, help_text="Tempo/Quarto")
    
    # Extra info
    notes = models.CharField(max_length=200, blank=True, help_text="Es: 'Su rigore', 'Doppia espulsione'")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        player_name = self.player.get_full_name() if self.player else "Squadra"
        return f"{self.get_event_type_display()} - {player_name} ({self.minute}')"
    
    class Meta:
        ordering = ['match', 'quarter', 'minute']
