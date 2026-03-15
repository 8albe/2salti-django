from django.db import models
from django.contrib.auth import get_user_model
from core.models import Team

User = get_user_model()


class SeasonArchive(models.Model):
    """Archivio stagione passata - creato automaticamente a fine anno"""
    season = models.CharField(max_length=9, help_text="Es: 2023-2024")
    entity_type = models.CharField(max_length=20, choices=[
        ('athlete', 'Atleta'),
        ('team', 'Squadra'),
    ])
    
    # Riferimenti (uno dei due sarà valorizzato)
    athlete = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='season_archives')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True, related_name='season_archives')
    
    # Dati archiviati (JSON)
    stats_data = models.JSONField(help_text="Statistiche complete della stagione")
    
    archived_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        entity = self.athlete or self.team
        return f"{entity} - Stagione {self.season}"
    
    class Meta:
        ordering = ['-season']
        unique_together = ['season', 'entity_type', 'athlete', 'team']
