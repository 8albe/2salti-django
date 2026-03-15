from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Sport, Society, Team, League
from matches.models import Match, MatchEvent
from accounts.models import AthleteProfile
from datetime import datetime, timedelta
import random

User = get_user_model()

class Command(BaseCommand):
    help = 'Popola database con dati demo per Pallanuoto'
    
    def handle(self, *args, **options):
        self.stdout.write('🚀 Creazione dati demo...')
        
        # 1. SPORT
        sport, _ = Sport.objects.get_or_create(
            name='Pallanuoto',
            slug='pallanuoto',
            hex_color='#00ffff',
            defaults={'icon': '🤽'}
        )
        self.stdout.write('✅ Sport creato')
        
        # 2. SOCIETÀ
        pro_recco, _ = Society.objects.get_or_create(
            name='Pro Recco',
            slug='pro-recco',
            sport=sport,
            defaults={
                'city': 'Recco',
                'founded_year': 1913,
                'history': 'La Pro Recco è la squadra più titolata al mondo...',
                'setup_completed': True,
            }
        )
        
        brescia, _ = Society.objects.get_or_create(
            name='AN Brescia',
            slug='an-brescia',
            sport=sport,
            defaults={
                'city': 'Brescia',
                'founded_year': 1912,
                'setup_completed': True,
            }
        )
        self.stdout.write('✅ Società create')
        
        # 3. CAMPIONATO
        league, _ = League.objects.get_or_create(
            name='Serie A1 Maschile',
            sport=sport,
            category='SENIOR',
            season='2024-2025',
            level=1
        )
        self.stdout.write('✅ Campionato creato')
        
        # 4. SQUADRE
        pro_recco_senior, _ = Team.objects.get_or_create(
            society=pro_recco,
            category='SENIOR',
            defaults={'league': league}
        )
        
        brescia_senior, _ = Team.objects.get_or_create(
            society=brescia,
            category='SENIOR',
            defaults={'league': league}
        )
        self.stdout.write('✅ Squadre create')
        
        # 5. GIOCATORI PRO RECCO
        pro_recco_players = []
        for i in range(1, 14):
            user, created = User.objects.get_or_create(
                username=f'prorecco_{i}',
                defaults={
                    'first_name': f'Giocatore{i}',
                    'last_name': 'ProRecco',
                    'role': 'athlete',
                    'setup_completed': True,
                }
            )
            if created:
                profile = user.athlete_profile
                profile.current_team = pro_recco_senior
                profile.jersey_number = i
                profile.position = 'Portiere' if i == 1 else ('Centroboa' if i == 7 else 'Ala')
                profile.save()
            pro_recco_players.append(user)
        
        # 6. GIOCATORI BRESCIA
        brescia_players = []
        for i in range(1, 14):
            user, created = User.objects.get_or_create(
                username=f'brescia_{i}',
                defaults={
                    'first_name': f'Giocatore{i}',
                    'last_name': 'Brescia',
                    'role': 'athlete',
                    'setup_completed': True,
                }
            )
            if created:
                profile = user.athlete_profile
                profile.current_team = brescia_senior
                profile.jersey_number = i
                profile.position = 'Portiere' if i == 1 else ('Centroboa' if i == 7 else 'Ala')
                profile.save()
            brescia_players.append(user)
        
        self.stdout.write('✅ Giocatori creati')
        
        # 7. ARBITRO
        referee, created = User.objects.get_or_create(
            username='arbitro_rossi',
            defaults={
                'first_name': 'Mario',
                'last_name': 'Rossi',
                'role': 'referee',
                'setup_completed': True,
            }
        )
        self.stdout.write('✅ Arbitro creato')
        
        # 8. PARTITA FINITA: Pro Recco 12-10 Brescia
        match, created = Match.objects.get_or_create(
            league=league,
            home_team=pro_recco_senior,
            away_team=brescia_senior,
            match_date=datetime.now() - timedelta(days=2),
            defaults={
                'home_score': 12,
                'away_score': 10,
                'is_finished': True,
                'location': 'Piscina Recco',
            }
        )
        if created:
            match.referees.add(referee)
        
        self.stdout.write('✅ Partita creata')
        
        # 9. EVENTI PARTITA (22 GOL)
        if created:
            # 12 gol Pro Recco
            for i in range(12):
                scorer = random.choice(pro_recco_players)
                MatchEvent.objects.create(
                    match=match,
                    event_type='GOAL',
                    player=scorer,
                    team=pro_recco_senior,
                    minute=random.randint(1, 32),
                    quarter=random.randint(1, 4),
                )
            
            # 10 gol Brescia
            for i in range(10):
                scorer = random.choice(brescia_players)
                MatchEvent.objects.create(
                    match=match,
                    event_type='GOAL',
                    player=scorer,
                    team=brescia_senior,
                    minute=random.randint(1, 32),
                    quarter=random.randint(1, 4),
                )
            
            # 2 espulsioni
            MatchEvent.objects.create(
                match=match,
                event_type='EXPULSION',
                player=random.choice(brescia_players),
                team=brescia_senior,
                minute=15,
                quarter=2,
            )
            
            MatchEvent.objects.create(
                match=match,
                event_type='EXPULSION',
                player=random.choice(pro_recco_players),
                team=pro_recco_senior,
                minute=28,
                quarter=4,
            )
        
        self.stdout.write('✅ Eventi partita creati')
        
        # 10. AGGIORNA STATISTICHE GIOCATORI
        for player in pro_recco_players + brescia_players:
            player.athlete_profile.update_stats()
        
        referee.referee_profile.update_stats()
        
        self.stdout.write(self.style.SUCCESS('🎉 SETUP DEMO COMPLETATO!'))
        self.stdout.write(f'   Partita: {match}')
        self.stdout.write(f'   Eventi creati: {match.events.count()}')
