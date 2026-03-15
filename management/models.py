from django.db import models
from django.conf import settings
from core.models import Society, Team

class Membership(models.Model):
    """
    Gestisce i ruoli degli utenti all'interno di Società e Squadre.
    Un utente può avere più ruoli in squadre diverse.
    """
    ROLE_CHOICES = [
        ('PRESIDENT', 'Presidente (Società)'),
        ('HEAD_COACH', 'Allenatore Capo (Squadra)'),
        ('ASSISTANT_COACH', 'Vice Allenatore (Squadra)'),
        ('PLAYER', 'Giocatore (Squadra)'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name='memberships')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'society', 'team', 'role']
        verbose_name = "Appartenenza"
        verbose_name_plural = "Appartenenze"

    def __str__(self):
        scope = self.team.name if self.team else self.society.name
        return f"{self.user.username} - {self.get_role_display()} ({scope})"

class AuditLog(models.Model):
    """
    Tracciamento delle azioni critiche nel sistema.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=255)  # Es: "CREATE_CONVOCATION", "UPDATE_TRAINING"
    target_id = models.CharField(max_length=100, blank=True, null=True)
    target_type = models.CharField(max_length=100, blank=True, null=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} - {self.user} - {self.action}"

class Training(models.Model):
    """
    Definisce un piano di allenamento (singolo o ricorrente).
    """
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='trainings')
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name='trainings')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=255, blank=True)
    
    # Orari (per il singolo evento o come base per la ricorrenza)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    # Ricorrenza
    is_recurring = models.BooleanField(default=False)
    recurrence_rule = models.JSONField(null=True, blank=True, help_text="Es: {'freq': 'WEEKLY', 'days': [0, 2, 4], 'until': '2026-06-30'}")
    
    # Allegati
    attachment = models.FileField(upload_to='trainings/', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.title} - {self.team.name}"

class TrainingOccurrence(models.Model):
    """
    Singola istanza di un allenamento (generata dalla ricorrenza o singola).
    """
    training = models.ForeignKey(Training, on_delete=models.CASCADE, related_name='occurrences')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    is_cancelled = models.BooleanField(default=False)
    notes = models.TextField(blank=True, help_text="Note specifiche per questa sessione")
    
    class Meta:
        ordering = ['start_time']

    def __str__(self):
        return f"{self.training.title} ({self.start_time.strftime('%d/%m/%Y %H:%M')})"

class TrainingAttendance(models.Model):
    """
    Presenza e RSVP con Geofencing.
    """
    STATUS_CHOICES = [
        ('PENDING', 'In attesa'),
        ('PRESENT', 'Presente'),
        ('ABSENT', 'Assente'),
        ('JUSTIFIED', 'Assente Giustificato'),
    ]

    occurrence = models.ForeignKey(TrainingOccurrence, on_delete=models.CASCADE, related_name='attendances')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Geofence Data
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True)
    checkin_time = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['occurrence', 'user']

    def __str__(self):
        return f"{self.user.username} - {self.occurrence} - {self.status}"

class Convocation(models.Model):
    """
    Gestione delle convocazioni ufficiali per una partita.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Bozza'),
        ('SENT_PRIVATE', 'Inviata Privata'),
        ('PUBLISHED', 'Pubblicata Ufficiale'),
        ('LOCKED', 'Bloccata (Gara iniziata)'),
    ]

    match = models.OneToOneField('matches.Match', on_delete=models.CASCADE, related_name='convocation')
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_convocations')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    # Ruoli speciali
    capitano = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='as_captain')
    vicecapitano = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='as_vice_captain')
    
    notes = models.TextField(blank=True)
    attachment = models.FileField(upload_to='convocations/', null=True, blank=True)
    ai_check_result = models.JSONField(default=dict, blank=True)
    reminders_sent = models.JSONField(default=list, blank=True)  # Es: ['T-24', 'T-2']
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def current_effective_status(self):
        """
        Calcola lo stato effettivo in base al tempo rimanente alla partita.
        PRD 4.5/4.6 logic.
        """
        now = timezone.now()
        diff = self.match.match_date - now
        
        if diff.total_seconds() <= 0:
            return 'LOCKED'
        
        if diff.total_seconds() <= 1800: # 30 minuti (T-30)
            return 'PUBLISHED'
            
        return self.status

    def perform_ai_cross_check(self):
        """
        PRD 4.4: AI confronta allegato con dati del form.
        Placeholder for real AI integration.
        """
        if not self.attachment:
            return
            
        # Simulazione: L'AI segnala se mancano giocatori importanti o se i nomi non coincidono
        # In produzione qui chiameremmo un servizio OCR/Vision.
        self.ai_check_result = {
            "status": "warning",
            "message": "AI: Nome 'Mario Rossi' nel PDF non trovato nei convocati del form.",
            "timestamp": timezone.now().isoformat()
        }
        self.save()

    def __str__(self):
        return f"Convocazione {self.match}"

class ConvocationNominee(models.Model):
    """
    Giocatore convocato per una specifica partita.
    """
    convocation = models.ForeignKey(Convocation, on_delete=models.CASCADE, related_name='nominees')
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='convocation_entries')
    is_starter = models.BooleanField(default=False, help_text="Se fa parte dei 7 titolari")

    class Meta:
        unique_together = ['convocation', 'player']

    def __str__(self):
        role = " (T)" if self.is_starter else ""
        return f"{self.player.get_full_name()}{role}"

class Post(models.Model):
    """
    Messaggi in bacheca di squadra o broadcast societari.
    """
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name='posts')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True, related_name='posts')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    title = models.CharField(max_length=200, blank=True)
    content = models.TextField()
    
    is_pinned = models.BooleanField(default=False)
    is_broadcast = models.BooleanField(default=False, help_text="Visibile a tutte le squadre della società")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"{self.title or self.content[:30]}..."

class Comment(models.Model):
    """
    Commenti ai post della bacheca.
    """
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

class ChatMessage(models.Model):
    """
    Messaggi di chat istantanea di squadra.
    """
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='chat_messages')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
