from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
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
    
    # Risultato per tempi (JSON: {"1": [2,0], "2": [1,1] ...})
    quarter_scores = models.JSONField(default=dict, blank=True, help_text="Risultato per tempi: {tempo: [home, away]}")
    
    # Arbitri (many-to-many perché possono essere 2-3)
    referees = models.ManyToManyField(User, blank=True, limit_choices_to={'role': 'referee'}, related_name='officiated_matches')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Status flags (migrated from OCR-specific)
    has_report = models.BooleanField(default=False, help_text="La partita ha un referto associato (File o Digitale)")
    is_data_verified = models.BooleanField(default=False, help_text="I dati sono stati verificati e approvati")
    
    @property
    def is_public(self):
        """A match is public if it has at least one PUBLISHED report."""
        return self.reports.filter(status='PUBLISHED').exists()

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
        verbose_name = "Partita"
        verbose_name_plural = "Partite"


class SportEventConfig(models.Model):
    """Configurazione eventi validi per uno sport specifico."""
    sport = models.ForeignKey('core.Sport', on_delete=models.CASCADE, related_name='event_configs')
    event_code = models.CharField(max_length=50, help_text="Codice interno (es: GOAL, YELLOW_CARD)")
    label = models.CharField(max_length=100, help_text="Etichetta visualizzata (es: 'Gol', 'Cartellino Giallo')")
    is_score = models.BooleanField(default=False, help_text="Se l'evento incrementa il punteggio della squadra")
    
    def __str__(self):
        return f"{self.sport} - {self.label} ({self.event_code})"
    
    class Meta:
        unique_together = ['sport', 'event_code']

class MatchEvent(models.Model):
    """Evento durante una partita (gol, espulsione, timeout)"""
    # Legacy choices for retro-compatibility if needed, but we should use SportEventConfig
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=50, help_text="Codice dell'evento (mappato su SportEventConfig)")
    
    # Flags per statistiche avanzate
    is_superiority = models.BooleanField(default=False, help_text="Evento avvenuto in superiorità/inferiorità")
    is_penalty = models.BooleanField(default=False, help_text="Evento legato a un tiro di rigore")
    
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
        return f"{self.display_label} - {player_name} ({self.minute}')"

    @property
    def display_label(self):
        """
        Returns the label for the event.
        Priority: 
        1. SportEventConfig (DB)
        2. Centralized defaults
        """
        if self.match.league and self.match.league.sport:
            conf = SportEventConfig.objects.filter(
                sport=self.match.league.sport, 
                event_code=self.event_type
            ).first()
            if conf:
                return conf.label
        
        # Spring-loaded from a local dictionary if available, or just the type
        return self.event_type
    
    class Meta:
        ordering = ['match', 'quarter', 'minute']


class InboundEmail(models.Model):
    """
    Traccia le email ricevute per evitare processi duplicati (Idempotenza).
    """
    message_id = models.CharField(max_length=255, unique=True, help_text="RFC822 Message-ID")
    sender = models.EmailField()
    subject = models.CharField(max_length=255)
    received_at = models.DateTimeField()
    processed_at = models.DateTimeField(auto_now_add=True)
    
    uid = models.UUIDField(default=None, null=True, blank=True, help_text="Optional UUID from external provider")

    def __str__(self):
        return f"Email from {self.sender}: {self.subject[:30]}..."

    class Meta:
        verbose_name = "Email Inbound"
        verbose_name_plural = "Emails Inbound"


class MatchReport(models.Model):
    """
    MVP Workflow per Referti e OCR.
    Traccia l'intero ciclo di vita di un referto caricato.
    """
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Bozza (Digitale)'
        UPLOADED = 'UPLOADED', 'Caricato (In attesa)'
        QUEUED = 'QUEUED', 'In Coda OCR'
        PROCESSING = 'PROCESSING', 'In Elaborazione OCR'
        EXTRACTED = 'EXTRACTED', 'Dati Estratti (Da Revisionare)'
        VALIDATED = 'VALIDATED', 'Validato (Approvato Admin)'
        PUBLISHED = 'PUBLISHED', 'Pubblicato (Statistiche Aggiornate)'
        NEEDS_REVIEW = 'NEEDS_REVIEW', 'Revisione Tecnica Necessaria'
        REJECTED = 'REJECTED', 'Rifiutato/Errore'

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='reports', null=True, blank=True)
    uploader = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_reports')
    
    # File originale (opzionale per referti digitali nativi)
    file = models.FileField(upload_to='match_reports/', null=True, blank=True, help_text="Referto in PDF o Immagine")
    
    # Canale di acquisizione
    SOURCE_CHANNEL_CHOICES = [
        ('FILE', 'Caricamento File / OCR'),
        ('DIGITAL', 'Referto Digitale Nativo'),
    ]
    source_channel = models.CharField(max_length=10, choices=SOURCE_CHANNEL_CHOICES, default='FILE')
    
    # Stato
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    
    # Dati estratti
    raw_extracted_data = models.JSONField(default=dict, blank=True, help_text="Payload JSON grezzo restituito dall'engine OCR")
    raw_api_response = models.TextField(blank=True, help_text="The exact, untouched JSON string from the OCR provider")
    normalized_data = models.JSONField(default=dict, blank=True, help_text="Dati normalizzati/corretti pronti per l'inserimento")
    
    # Source tracking
    source_type = models.CharField(
        max_length=10, 
        choices=[('MANUAL', 'Manuale'), ('EMAIL', 'Email')], 
        default='MANUAL'
    )
    source_metadata = models.JSONField(default=dict, blank=True, help_text="Metadata aggiuntivi (es: subject email, sender)")
    inbound_email = models.ForeignKey(InboundEmail, on_delete=models.SET_NULL, null=True, blank=True, related_name='reports')
    
    # Deduplication
    file_hash = models.CharField(max_length=64, blank=True, db_index=True, help_text="SHA256 hash del file per evitare duplicati")

    # Firma arbitro (canale digitale): nome e cognome digitati alla chiusura del
    # referto. Sostituisce il PIN personale (decaduto nel modello no-account,
    # Macro 14). Valorizzato solo al close del canale DIGITAL.
    referee_signature = models.CharField(
        max_length=200, blank=True,
        help_text="Firma arbitro (nome e cognome) digitata alla chiusura del referto digitale"
    )

    # Coda OCR asincrona (Macro 22). Campi di lavorazione del worker: inerti
    # per il canale DIGITAL, che non passa dalla coda.
    ocr_attempts = models.PositiveSmallIntegerField(
        default=0, help_text="Tentativi di elaborazione OCR (incrementato al claim del worker)"
    )
    ocr_queued_at = models.DateTimeField(null=True, blank=True, help_text="Istante di accodamento (ordinamento FIFO)")
    ocr_next_attempt_at = models.DateTimeField(
        null=True, blank=True, help_text="Non eleggibile al claim prima di questo istante (backoff retry)"
    )
    ocr_started_at = models.DateTimeField(null=True, blank=True, help_text="Istante del claim (base per lo stale detection)")
    ocr_error = models.TextField(blank=True, help_text="Ultimo errore tecnico OCR (diagnostica worker)")

    # Review / Audit
    validation_notes = models.TextField(blank=True, help_text="Note di validazione (visibili se necessario)")
    internal_notes = models.TextField(blank=True, help_text="Note interne per lo staff (non visibili all'uploader)")
    
    validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='validated_reports')
    validated_at = models.DateTimeField(null=True, blank=True)
    
    published_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='published_reports')
    published_at = models.DateTimeField(null=True, blank=True)

    # Soft lock / "Presa in carico" per il pilot
    in_review_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='currently_reviewing')
    in_review_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Referto {self.match} [{self.get_status_display()}]"
    
    def realign_data(self):
        """
        Riconcilia i dati derivati (standings, stats atleti) basandosi sul match corrente.
        Idempotente e centralizzato.
        """
        from .services.standings_service import StandingsService
        from accounts.models import User
        
        # 1. Standings
        if self.match.league:
            StandingsService.rebuild_for_league(self.match.league)
            
        # 2. Stats Atleti (tutti quelli coinvolti nel match)
        athletes = User.objects.filter(
            models.Q(match_events__match=self.match) |
            models.Q(athlete_profile__current_team=self.match.home_team) |
            models.Q(athlete_profile__current_team=self.match.away_team)
        ).distinct()
        
        for user in athletes:
            if hasattr(user, 'athlete_profile'):
                user.athlete_profile.update_stats()

    @property
    def file_exists(self):
        """Check if the physical file exists on disk."""
        if not self.file:
            return False
        return self.file.storage.exists(self.file.name)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Referto"
        verbose_name_plural = "📄 Referti Match"


class AIQueryLog(models.Model):
    """Log di sistema per tracciare le query AI v0 durante il pilot."""
    created_at = models.DateTimeField(auto_now_add=True)
    raw_query = models.TextField()
    
    # Metadata parsing
    response_type = models.CharField(max_length=50, help_text="answer, error, insufficient_data")
    response_text = models.TextField()
    success = models.BooleanField(default=False)
    
    # Analysis fields
    matched_athlete = models.ForeignKey(
        'accounts.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='ai_queries'
    )
    time_range = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=50, default='homepage')

    class Meta:
        ordering = ['-created_at']
        verbose_name = "AI Query Log"
        verbose_name_plural = "🤖 AI Query Logs"

    def __str__(self):
        return f"{self.created_at.strftime('%Y-%m-%d %H:%M')} - {self.raw_query[:30]}"


class MatchReportAuditLog(models.Model):
    """Log di sistema per tracciare le modifiche e le azioni sui referti."""
    report = models.ForeignKey(MatchReport, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50, help_text="es: edit, validate, publish")
    
    old_status = models.CharField(max_length=20, null=True, blank=True, help_text="Stato precedente")
    new_status = models.CharField(max_length=20, null=True, blank=True, help_text="Nuovo stato")
    reason = models.TextField(blank=True, help_text="Motivazione del cambio stato o modifica")
    
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Audit Log Referto"
        verbose_name_plural = "Audit Log Referti"

    def __str__(self):
        status_change = f" ({self.old_status} -> {self.new_status})" if self.old_status and self.new_status else ""
        return f"{self.created_at.strftime('%Y-%m-%d %H:%M')} - {self.action}{status_change} su {self.report}"


class MatchJuryLink(models.Model):
    """
    Link monouso per l'accesso della giuria alla compilazione del referto
    digitale di UNA partita, senza account (Macro 14).

    "Monouso" = un ciclo di vita, non un singolo click: il link resta valido per
    più sessioni/visite durante la compilazione e muore alla chiusura del
    referto (CONSUMED). Stati e transizioni in docs/STATE_MACHINES.md.

    Al più UN link ACTIVE per match è garantito a livello DB da un partial unique
    index (SQLite supporta indici parziali), rinforzato applicativamente:
    emettere un nuovo link revoca in transazione l'eventuale ACTIVE precedente.
    """
    EXPIRY_DAYS = 7

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Attivo'
        CONSUMED = 'CONSUMED', 'Consumato (referto chiuso)'
        REVOKED = 'REVOKED', 'Revocato'
        EXPIRED = 'EXPIRED', 'Scaduto (backstop 7 giorni)'

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='jury_links')
    token = models.CharField(
        max_length=64, unique=True, db_index=True,
        help_text="Token URL-safe ad alta entropia (secrets, >=32 byte)"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issued_jury_links',
        help_text="Staff/admin che ha emesso il link (null se sistema)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="Backstop = created_at + EXPIRY_DAYS")
    revoked_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    # Referto chiuso tramite questo link (valorizzato al consume).
    report = models.ForeignKey(
        MatchReport, on_delete=models.SET_NULL, null=True, blank=True, related_name='jury_links',
        help_text="Referto chiuso dal link (valorizzato al consume)"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Link Giuria Partita"
        verbose_name_plural = "Link Giuria Partite"
        constraints = [
            models.UniqueConstraint(
                fields=['match'],
                condition=models.Q(status='ACTIVE'),
                name='uniq_active_jury_link_per_match',
            ),
        ]

    @property
    def is_expired_by_time(self):
        """Scadenza valutata a lettura: nessun cron in questo giro."""
        return timezone.now() >= self.expires_at

    def is_valid(self):
        """ACTIVE e non ancora scaduto per tempo."""
        return self.status == self.Status.ACTIVE and not self.is_expired_by_time

    def __str__(self):
        return f"JuryLink {self.match_id} [{self.get_status_display()}]"
