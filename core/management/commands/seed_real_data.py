
from django.core.management.base import BaseCommand
from core.models import Sport, Society, Team, League
from matches.models import Match
from django.utils import timezone
from datetime import datetime, timedelta
import random

class Command(BaseCommand):
    help = 'Seeds the database with Real Data for Serie A1 Waterpolo 2024-2025'

    def handle(self, *args, **options):
        self.stdout.write("🌊 Seeding Real Data...")

        # 1. Ensure Sport
        sport, _ = Sport.objects.get_or_create(
            name="Pallanuoto",
            defaults={'slug': 'pallanuoto', 'icon': '🤽', 'hex_color': '#06b6d4'}
        )

        # 2. Real Teams (Serie A1 2024-25)
        # Source (Approximate for Demo): Pro Recco, Savona, Brescia, Ortigia, Telimar, Trieste, Quinto, De Akker, Posillipo, Catania, Vis Nova, Florentia, Onda Forte, Olympic Roma
        clubs = [
            ("Pro Recco", "pro-recco"),
            ("RN Savona", "rn-savona"),
            ("AN Brescia", "an-brescia"),
            ("CC Ortigia 1928", "cc-ortigia"),
            ("Telimar Palermo", "telimar-palermo"),
            ("Pallanuoto Trieste", "pallanuoto-trieste"),
            ("Iren Genova Quinto", "iren-quinto"),
            ("De Akker Team", "de-akker"),
            ("CN Posillipo", "cn-posillipo"),
            ("Nuoto Catania", "nuoto-catania"),
            ("Roma Vis Nova", "roma-vis-nova"),
            ("RN Florentia", "rn-florentia"),
            ("Onda Forte", "onda-forte"),
            ("Olympic Roma", "olympic-roma"),
        ]

        teams_objs = []
        for name, slug in clubs:
            society, _ = Society.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'sport': sport}
            )
            # Create Senior Team
            team, _ = Team.objects.get_or_create(
                society=society,
                # correct code
                defaults={'name': name}
            )
            teams_objs.append(team)
            self.stdout.write(f"Confirmed Team: {name}")

        # 3. Create League
        league, created = League.objects.get_or_create(
            name="Serie A1 Maschile",
            season="2025-2026",
            sport=sport,
            defaults={'slug': 'serie-a1-2025'}
        )
        # Add teams to league
        league.teams.set(teams_objs)
        
        if not created and Match.objects.filter(league=league).exists():
             self.stdout.write("League and matches already exist. Skipping match generation.")
        else:
            self.stdout.write("📅 Generating Calendar...")
            # Simple Round Robin Generation for demo
            # Start Date: Oct 2025
            start_date = timezone.now().replace(year=2025, month=10, day=11, hour=15, minute=0)
            
            # Shuffle teams to randomize pairs
            # random.shuffle(teams_objs) 
            # OR define generic pairs (Round 1)
            pairs = []
            # Split list in two
            half = len(teams_objs) // 2
            group_a = teams_objs[:half]
            group_b = teams_objs[half:]
            
            # Create 3 rounds
            for round_num in range(1, 4):
                round_date = start_date + timedelta(weeks=round_num-1)
                
                for i in range(half):
                    home = group_a[i]
                    away = group_b[i]
                    
                    # Swap home/away for next round variety
                    if round_num % 2 == 0:
                        home, away = away, home

                    Match.objects.create(
                        league=league,
                        home_team=home,
                        away_team=away,
                        match_date=round_date,
                        location="Piscina Comunale",
                        is_finished=False
                    )
                
                # Rotate for next round (simple algo)
                # Keep first of group_a fixed, rotate others
                rotated_pool = [group_a[0]] + [group_b[-1]] + group_a[1:] + group_b[:-1]
                # Re-split? No, standard circle method is:
                # Fixed: A[0]
                # Rotate: A[1]...A[n] + B[...]
                
                # Simplified: Just shuffle simply for demo
                last = group_a.pop()
                group_b.insert(0, last)
                first_b = group_b.pop()
                group_a.insert(1, first_b)

        self.stdout.write(self.style.SUCCESS('✅ Real Data Seeded Successfully'))
