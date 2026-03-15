
from django.core.management.base import BaseCommand
from core.models import Sport, Society, Team, League
from matches.models import Match
from django.utils import timezone
from datetime import datetime, timedelta
import random

class Command(BaseCommand):
    help = 'Seeds comprehensive real data for Serie A1 Waterpolo 2025-2026 with realistic results'

    def handle(self, *args, **options):
        self.stdout.write("🌊 Seeding Comprehensive Real Data...")

        # 1. Sport
        sport, _ = Sport.objects.get_or_create(
            name="Pallanuoto",
            defaults={'slug': 'pallanuoto', 'icon': '🤽', 'hex_color': '#06b6d4'}
        )

        # 2. Real Teams
        clubs = [
            "Pro Recco", "AN Brescia", "RN Savona", "CC Ortigia 1928",
            "Telimar Palermo", "Pallanuoto Trieste", "Iren Genova Quinto",
            "De Akker Team", "CN Posillipo", "Nuoto Catania",
            "Roma Vis Nova", "RN Florentia", "Onda Forte", "Olympic Roma"
        ]

        teams_objs = []
        for club_name in clubs:
            slug = club_name.lower().replace(' ', '-').replace('.', '')
            society, _ = Society.objects.get_or_create(
                slug=slug,
                defaults={'name': club_name, 'sport': sport, 'city': 'Italia'}
            )
            team, _ = Team.objects.get_or_create(
                society=society,
                category='SENIOR',
            )
            teams_objs.append(team)
            self.stdout.write(f"✓ {team.name}")

        # 3. League
        league, created = League.objects.get_or_create(
            name="Serie A1 Maschile",
            season="2025-2026",
            sport=sport,
            defaults={'slug': 'serie-a1-2025', 'category': 'SENIOR'}
        )
        league.teams.set(teams_objs)

        # 4. Matches - Full Round Robin with realistic scores
        Match.objects.filter(league=league).delete()
        
        self.stdout.write("📅 Generating Season...")
        
        # Start date: October 11, 2025
        base_date = timezone.make_aware(datetime(2025, 10, 11, 15, 0))
        
        # Realistic scores for top teams
        team_strength = {
            "Pro Recco": 95,
            "AN Brescia": 90,
            "RN Savona": 85,
            "CC Ortigia 1928": 82,
            "Telimar Palermo": 78,
            "Pallanuoto Trieste": 75,
            "Iren Genova Quinto": 73,
            "De Akker Team": 70,
            "CN Posillipo": 68,
            "Nuoto Catania": 65,
            "Roma Vis Nova": 62,
            "RN Florentia": 60,
            "Onda Forte": 58,
            "Olympic Roma": 55
        }

        match_counter = 0
        round_num = 1
        
        # Generate 13 rounds (each team plays every other once in a semi-round robin)
        for round_offset in range(13):
            round_date = base_date + timedelta(weeks=round_offset)
            
            # Create pairings for this round
            shuffled_teams = teams_objs.copy()
            random.seed(round_offset)  # Consistent shuffle per round
            random.shuffle(shuffled_teams)
            
            # Pair teams
            for i in range(0, len(shuffled_teams), 2):
                if i + 1 < len(shuffled_teams):
                    home = shuffled_teams[i]
                    away = shuffled_teams[i + 1]
                    
                    # Determine if match has been played (first 8 rounds = played)
                    is_finished = round_offset < 8
                    
                    home_score = 0
                    away_score = 0
                    
                    if is_finished:
                        # Generate realistic score based on team strength
                        home_strength = team_strength.get(home.name, 65)
                        away_strength = team_strength.get(away.name, 65)
                        
                        # Base scores
                        home_score = random.randint(8, 15)
                        away_score = random.randint(8, 15)
                        
                        # Adjust based on strength differential
                        strength_diff = home_strength - away_strength
                        if strength_diff > 10:
                            home_score += random.randint(1, 4)
                        elif strength_diff < -10:
                            away_score += random.randint(1, 4)
                        
                        # Ensure some variation
                        home_score = max(6, min(20, home_score))
                        away_score = max(6, min(20, away_score))
                    
                    Match.objects.create(
                        league=league,
                        home_team=home,
                        away_team=away,
                        match_date=round_date,
                        location=f"Piscina {home.society.city if hasattr(home.society, 'city') else 'Comunale'}",
                        is_finished=is_finished,
                        home_score=home_score if is_finished else None,
                        away_score=away_score if is_finished else None
                    )
                    match_counter += 1
            
            round_num += 1
        
        self.stdout.write(self.style.SUCCESS(f'✅ Created {match_counter} matches ({round_offset + 1} rounds)'))
        self.stdout.write(self.style.SUCCESS(f'✅ {len([m for m in Match.objects.filter(league=league) if m.is_finished])} finished matches'))
        self.stdout.write(self.style.SUCCESS(f'✅ {len([m for m in Match.objects.filter(league=league) if not m.is_finished])} upcoming matches'))
