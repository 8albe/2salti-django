from django.db import models
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
from core.models import Society, Team


class MembershipQuerySet(models.QuerySet):
    def active_at(self, date=None):
        """
        Filtra le Membership attive alla data indicata (default: oggi in TZ locale).

        Regola di attività:
        - start_date NOT NULL (record senza start_date sono anomali, esclusi)
        - start_date <= date
        - end_date IS NULL OR end_date >= date
        """
        if date is None:
            date = timezone.localdate()
        return self.filter(
            start_date__isnull=False,
            start_date__lte=date,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=date))


class MembershipManager(models.Manager.from_queryset(MembershipQuerySet)):
    pass


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
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MembershipManager()

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
    society = models.ForeignKey(Society, on_delete=models.CASCADE, null=True, blank=True, related_name='audit_logs')
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

# Temporary dummy models to satisfy imports until real models are restored
class ActivationCode(models.Model):
    """
    PRD 7.0: Codici di attivazione generati dal Club Admin per invitare membri.
    """
    code = models.CharField(max_length=50, unique=True, help_text="Es: RECC-X12-Y34")
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name='activation_codes')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True, related_name='activation_codes')
    role = models.CharField(max_length=20, choices=Membership.ROLE_CHOICES, default='PLAYER')
    
    max_uses = models.IntegerField(default=50)
    current_uses = models.IntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_activation_codes')

    def __str__(self):
        scope = self.team.name if self.team else self.society.name
        return f"{self.code} - {self.get_role_display()} ({scope})"

class MembershipRequest(models.Model):
    """
    PRD 7.0: Richieste di accesso manuale quando l'utente non ha il codice.
    """
    STATUS_CHOICES = [
        ('PENDING', 'In attesa'),
        ('APPROVED', 'Approvata'),
        ('REJECTED', 'Respinta'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='membership_requests')
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name='membership_requests')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True, related_name='membership_requests')
    role = models.CharField(max_length=20, choices=Membership.ROLE_CHOICES, default='PLAYER')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    admin_note = models.TextField(blank=True, help_text="Note del Club Admin in fase di approvazione/rifiuto")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Richiesta Membership"
        verbose_name_plural = "Richieste Membership"

    def __str__(self):
        scope = self.team.name if self.team else self.society.name
        return f"{self.user.username} -> {scope} ({self.status})"


# ──────────────────────────────────────────────────────────────
# PILOT OPERATIONS MODELS
# ──────────────────────────────────────────────────────────────

class PilotDailyLog(models.Model):
    """
    One record per pilot day — captures daily operational status.
    Staff-only. Used for daily tracking and email report generation.
    """
    STATUS_CHOICES = [
        ('GREEN', '🟢 Green — nominal'),
        ('YELLOW', '🟡 Yellow — issues present'),
        ('RED', '🔴 Red — blocked / critical'),
    ]

    date = models.DateField(unique=True, help_text="Pilot day date")
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='pilot_daily_logs',
        help_text="Staff member responsible for this day"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='GREEN')
    blockers = models.TextField(blank=True, help_text="Active blockers")
    workarounds = models.TextField(blank=True, help_text="Active workarounds in place")
    notes = models.TextField(blank=True, help_text="Key observations for the day")
    next_day_decision = models.TextField(blank=True, help_text="Operational decision for the next day")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "Pilot Daily Log"
        verbose_name_plural = "Pilot Daily Logs"

    def __str__(self):
        return f"{self.date} — {self.get_status_display()}"


class PilotBug(models.Model):
    """
    Staff-only bug tracker, separate from user feedback.
    Tracks technical issues found during the pilot.
    """
    SEVERITY_CHOICES = [
        ('S1', 'S1 — Blocker'),
        ('S2', 'S2 — Critical'),
        ('S3', 'S3 — Major'),
        ('S4', 'S4 — Minor'),
    ]
    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('TRIAGED', 'Triaged'),
        ('IN_PROGRESS', 'In Progress'),
        ('MITIGATED', 'Mitigated'),
        ('CLOSED', 'Closed'),
        ('VERIFIED', 'Verified'),
    ]
    REPRODUCIBILITY_CHOICES = [
        ('ALWAYS', 'Always'),
        ('SOMETIMES', 'Sometimes'),
        ('RARE', 'Rare'),
        ('ONCE', 'Once'),
    ]

    title = models.CharField(max_length=255)
    severity = models.CharField(max_length=2, choices=SEVERITY_CHOICES, default='S3')
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='pilot_bugs_reported'
    )
    role_context = models.CharField(max_length=100, blank=True, help_text="Role/context when bug was found")
    observed_behavior = models.TextField(help_text="What actually happened")
    expected_behavior = models.TextField(help_text="What should have happened")
    reproducibility = models.CharField(max_length=10, choices=REPRODUCIBILITY_CHOICES, default='ALWAYS')
    workaround = models.TextField(blank=True, help_text="Known workaround if any")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pilot_bugs_owned',
        help_text="Assigned developer/staff"
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='NEW')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['severity', '-created_at']
        verbose_name = "Pilot Bug"
        verbose_name_plural = "Pilot Bugs"

    def __str__(self):
        return f"[{self.severity}] {self.title} ({self.status})"


class PilotFeedback(models.Model):
    """
    Staff-only feedback tracker, separate from bugs.
    Captures UX/operational feedback from pilot users and staff.
    """
    CATEGORY_CHOICES = [
        ('UX_COPY', 'UX / Copy'),
        ('ONBOARDING', 'Onboarding'),
        ('VISIBILITY_STATE', 'Visibility / State'),
        ('OPERATIONAL_PROCESS', 'Operational Process'),
        ('FUTURE_REQUEST', 'Future Request'),
    ]
    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('ACKNOWLEDGED', 'Acknowledged'),
        ('PLANNED', 'Planned'),
        ('DONE', 'Done'),
        ('WONT_FIX', "Won't Fix"),
    ]

    source = models.CharField(max_length=100, help_text="Who provided this feedback")
    flow_step = models.CharField(max_length=100, blank=True, help_text="Which flow/step this relates to")
    summary = models.TextField(help_text="Feedback summary")
    impact = models.TextField(blank=True, help_text="Impact on user experience or operations")
    category = models.CharField(max_length=25, choices=CATEGORY_CHOICES, default='UX_COPY')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pilot_feedback_owned'
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='NEW')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Pilot Feedback"
        verbose_name_plural = "Pilot Feedback"

    def __str__(self):
        return f"[{self.category}] {self.summary[:60]}"


class PilotReview(models.Model):
    """
    Day-7 / Day-14 pilot review — compiles evidence-based summary
    for go/no-go decisions.
    """
    REVIEW_TYPE_CHOICES = [
        ('DAY_7', 'Day 7 Review'),
        ('DAY_14', 'Day 14 Review'),
    ]
    RECOMMENDATION_CHOICES = [
        ('CONTINUE', 'Continue'),
        ('REDUCED_SCOPE', 'Continue with Reduced Scope'),
        ('EXTEND', 'Extend to Day 14'),
        ('SUSPEND', 'Suspend Part of Flow'),
    ]

    review_date = models.DateField()
    review_type = models.CharField(max_length=10, choices=REVIEW_TYPE_CHOICES)
    what_worked = models.TextField(help_text="What went well during this period")
    blockers_summary = models.TextField(blank=True, help_text="Summary of blockers encountered")
    recurring_issues = models.TextField(blank=True, help_text="Issues that kept coming back")
    staff_load = models.TextField(blank=True, help_text="Assessment of staff workload")
    recommendation = models.CharField(max_length=15, choices=RECOMMENDATION_CHOICES)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='pilot_reviews_created'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-review_date']
        verbose_name = "Pilot Review"
        verbose_name_plural = "Pilot Reviews"

    def __str__(self):
        return f"{self.get_review_type_display()} — {self.review_date} ({self.recommendation})"
