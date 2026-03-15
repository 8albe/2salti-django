from django.db import models
from django.utils.text import slugify
from django.contrib.auth import get_user_model

User = get_user_model()


class Sport(models.Model):
    """Sport disponibili sulla piattaforma"""
    name = models.CharField(max_length=100, unique=True)  # "Pallanuoto", "Basket", "Volley"
    slug = models.SlugField(unique=True)
    hex_color = models.CharField(max_length=7, default='#00ffff', help_text="Colore tema (es: #00ffff)")
    icon = models.CharField(max_length=50, blank=True, help_text="Nome icona Heroicons")
    description = models.TextField(blank=True)
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class Society(models.Model):
    """Società sportiva (es: Pro Recco) - CREATA DAL PRESIDENTE"""
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name='societies')
    
    # Dati compilati dal presidente nel wizard
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True)
    founded_year = models.IntegerField(null=True, blank=True)
    logo = models.ImageField(upload_to='societies/', null=True, blank=True)
    history = models.TextField(blank=True, help_text="Storia della società")
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    
    # Sponsor (lista JSON: [{"name": "Nike", "logo_url": "..."}])
    sponsors = models.JSONField(default=list, blank=True)
    
    # Setup
    setup_completed = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def get_staff(self):
        """Ritorna tutti gli allenatori che si sono auto-dichiarati di questa società"""
        from accounts.models import CoachProfile
        team_ids = self.teams.values_list('id', flat=True)
        return CoachProfile.objects.filter(current_team__in=team_ids).select_related('user')
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Societies"
        ordering = ['name']


class Team(models.Model):
    """Squadra specifica di una società (es: Pro Recco Under 16)"""
    CATEGORY_CHOICES = [
        ('U10', 'Under 10'),
        ('U12', 'Under 12'),
        ('U14', 'Under 14'),
        ('U16', 'Under 16'),
        ('U18', 'Under 18'),
        ('U20', 'Under 20'),
        ('SENIOR', 'Prima Squadra'),
    ]
    
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name='teams')
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    league = models.ForeignKey('League', on_delete=models.SET_NULL, null=True, blank=True, related_name='teams')
    
    # Auto-generated
    name = models.CharField(max_length=200, blank=True, help_text="Auto-generato: Society + Category")
    slug = models.SlugField(unique=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.name:
            if self.category == 'SENIOR':
                self.name = self.society.name
            else:
                self.name = f"{self.society.name} {self.get_category_display()}"
        if not self.slug:
            self.slug = slugify(f"{self.society.slug}-{self.category}")
        super().save(*args, **kwargs)
    
    def get_roster(self):
        """Ritorna rosa giocatori"""
        from accounts.models import AthleteProfile
        return AthleteProfile.objects.filter(current_team=self).select_related('user')
    
    def __str__(self):
        return self.name
    
    class Meta:
        unique_together = ['society', 'category']
        ordering = ['society', 'category']


class League(models.Model):
    """Campionato (es: Serie A1 Maschile - Girone A)"""
    name = models.CharField(max_length=100, help_text="Es: Serie A1 Maschile")
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name='leagues')
    category = models.CharField(max_length=10, choices=Team.CATEGORY_CHOICES)
    season = models.CharField(max_length=9, default='2024-2025', help_text="Es: 2024-2025")
    group_name = models.CharField(max_length=50, blank=True, help_text="Es: Girone A, Girone B")
    
    # Metadati
    level = models.IntegerField(default=1, help_text="1=A1, 2=A2, 3=B, ecc.")
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.name}-{self.season}-{self.group_name}")
        super().save(*args, **kwargs)
    
    def __str__(self):
        base = f"{self.name} {self.season}"
        if self.group_name:
            base += f" - {self.group_name}"
        return base
    
    def get_standings(self):
        """Calcola classifica ordinata per punti"""
        from matches.models import Match
        standings_list = []
        
        for team in self.teams.all():
            matches_home = Match.objects.filter(league=self, is_finished=True, home_team=team)
            matches_away = Match.objects.filter(league=self, is_finished=True, away_team=team)
            
            played = matches_home.count() + matches_away.count()
            
            wins = matches_home.filter(home_score__gt=models.F('away_score')).count() + \
                   matches_away.filter(away_score__gt=models.F('home_score')).count()
            
            draws = matches_home.filter(home_score=models.F('away_score')).count() + \
                    matches_away.filter(away_score=models.F('home_score')).count()
            
            losses = matches_home.filter(home_score__lt=models.F('away_score')).count() + \
                     matches_away.filter(away_score__lt=models.F('home_score')).count()
            
            # Calcolo Gol (Naive implementation - optimize with aggregation in future)
            gf = 0
            ga = 0
            for m in matches_home:
                gf += m.home_score
                ga += m.away_score
            for m in matches_away:
                gf += m.away_score
                ga += m.home_score
                
            gd = gf - ga
            points = wins * 3 + draws
            
            standings_list.append({
                'team': team,
                'played': played,
                'won': wins,
                'drawn': draws,
                'lost': losses,
                'goals_for': gf,
                'goals_against': ga,
                'goal_diff': gd,
                'points': points,
            })
        
        # Sort by Points (desc), then Goal Diff (desc), then Goals For (desc)
        return sorted(standings_list, key=lambda x: (x['points'], x['goal_diff'], x['goals_for']), reverse=True)
    
    class Meta:
        unique_together = ['name', 'season', 'group_name']
        ordering = ['sport', 'level', 'group_name']
