import os
import sys
import django

# Setup Django environment
sys.path.append('/opt/2salti/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Sport, Society, Team, League
from accounts.models import User, AthleteProfile
from django.utils.text import slugify

# Dataset from 1x2pallanuoto.it
data = [
  {"first_name": "R.", "last_name": "Valle", "team": "De Akker"},
  {"first_name": "M.", "last_name": "Martini", "team": "De Akker"},
  {"first_name": "G.", "last_name": "Bardulla", "team": "De Akker"},
  {"first_name": "M.", "last_name": "Bragantini", "team": "De Akker"},
  {"first_name": "D.", "last_name": "Mcfarland", "team": "De Akker"},
  {"first_name": "E.", "last_name": "Campopiano", "team": "De Akker"},
  {"first_name": "J.", "last_name": "Painter", "team": "De Akker"},
  {"first_name": "K.", "last_name": "Milakovic", "team": "De Akker"},
  {"first_name": "B.", "last_name": "Erdelyi", "team": "De Akker"},
  {"first_name": "N.", "last_name": "Di Murro", "team": "De Akker"},
  {"first_name": "F.", "last_name": "Lucci", "team": "De Akker"},
  {"first_name": "A.", "last_name": "Urbinati", "team": "De Akker"},
  {"first_name": "S.", "last_name": "Santini", "team": "De Akker"},
  {"first_name": "L.", "last_name": "Barovic", "team": "De Akker"},
  {"first_name": "A.", "last_name": "Renzi", "team": "De Akker"},
  {"first_name": "G.", "last_name": "Nicosia", "team": "Pro Recco Waterpolo"},
  {"first_name": "F.", "last_name": "Di Fulvio", "team": "Pro Recco Waterpolo"},
  {"first_name": "A.", "last_name": "Granados Ortega", "team": "Pro Recco Waterpolo"},
  {"first_name": "G.", "last_name": "Cannella", "team": "Pro Recco Waterpolo"},
  {"first_name": "A.", "last_name": "Patchaliev", "team": "Pro Recco Waterpolo"},
  {"first_name": "L.", "last_name": "Durik", "team": "Pro Recco Waterpolo"},
  {"first_name": "N.", "last_name": "Presciutti", "team": "Pro Recco Waterpolo"},
  {"first_name": "L.", "last_name": "Pavillard", "team": "Pro Recco Waterpolo"},
  {"first_name": "M.", "last_name": "Iocchi Gratta", "team": "Pro Recco Waterpolo"},
  {"first_name": "R.", "last_name": "Buric", "team": "Pro Recco Waterpolo"},
  {"first_name": "F.", "last_name": "Condemi", "team": "Pro Recco Waterpolo"},
  {"first_name": "M.", "last_name": "Irving", "team": "Pro Recco Waterpolo"},
  {"first_name": "L.", "last_name": "Perrone", "team": "Pro Recco Waterpolo"},
  {"first_name": "A.", "last_name": "Mladossich", "team": "Pro Recco Waterpolo"},
  {"first_name": "L.", "last_name": "Demarchi", "team": "Pro Recco Waterpolo"},
  {"first_name": "F.", "last_name": "Piccionetti", "team": "Onda Forte"},
  {"first_name": "D.", "last_name": "Barilla’", "team": "Onda Forte"},
  {"first_name": "F.", "last_name": "Barchiesi", "team": "Onda Forte"},
  {"first_name": "M.", "last_name": "Voncina", "team": "Onda Forte"},
  {"first_name": "A.", "last_name": "Pisu", "team": "Onda Forte"},
  {"first_name": "D.", "last_name": "Boezi", "team": "Onda Forte"},
  {"first_name": "T.", "last_name": "Fabrucci", "team": "Onda Forte"},
  {"first_name": "M.", "last_name": "Serta", "team": "Onda Forte"},
  {"first_name": "S.", "last_name": "Boezi", "team": "Onda Forte"},
  {"first_name": "P.", "last_name": "Fabbri", "team": "Onda Forte"},
  {"first_name": "N.", "last_name": "Gatto", "team": "Onda Forte"},
  {"first_name": "L.", "last_name": "Vita", "team": "Onda Forte"},
  {"first_name": "J.", "last_name": "Marella", "team": "Onda Forte"},
  {"first_name": "G.", "last_name": "Rumolo", "team": "Onda Forte"},
  {"first_name": "A.", "last_name": "Giannotti", "team": "S.S. Lazio Nuoto"},
  {"first_name": "G.", "last_name": "Alessandrini", "team": "S.S. Lazio Nuoto"},
  {"first_name": "F.", "last_name": "Dominici", "team": "S.S. Lazio Nuoto"},
  {"first_name": "G.", "last_name": "Silvestri", "team": "S.S. Lazio Nuoto"},
  {"first_name": "L.", "last_name": "Checchini", "team": "S.S. Lazio Nuoto"},
  {"first_name": "A.", "last_name": "Costanzo", "team": "S.S. Lazio Nuoto"},
  {"first_name": "A.", "last_name": "Olivi", "team": "S.S. Lazio Nuoto"},
  {"first_name": "M.", "last_name": "Jankovic", "team": "S.S. Lazio Nuoto"},
  {"first_name": "G.", "last_name": "Cardoni", "team": "S.S. Lazio Nuoto"},
  {"first_name": "N.", "last_name": "Troiani", "team": "S.S. Lazio Nuoto"},
  {"first_name": "G.", "last_name": "Giacomone", "team": "S.S. Lazio Nuoto"},
  {"first_name": "G.", "last_name": "Moroni", "team": "S.S. Lazio Nuoto"},
  {"first_name": "M.", "last_name": "Marchetti", "team": "S.S. Lazio Nuoto"},
  {"first_name": "D.", "last_name": "Piccinini", "team": "S.S. Lazio Nuoto"}
]

def seed():
    # 1. Sport
    sport, _ = Sport.objects.get_or_create(name="Pallanuoto")
    if not sport.slug:
        sport.slug = "pallanuoto"
        sport.save()

    # 2. League
    league, _ = League.objects.get_or_create(
        name="Senior", 
        sport=sport, 
        category="SENIOR", 
        slug="senior"
    )

    teams_map = {}

    for entry in data:
        team_name = entry['team']
        if team_name not in teams_map:
            # 3. Society & Team
            society_slug = slugify(team_name)
            soc, _ = Society.objects.get_or_create(
                name=team_name, 
                sport=sport, 
                slug=society_slug
            )
            team, _ = Team.objects.get_or_create(
                society=soc, 
                league=league, 
                category="SENIOR"
            )
            teams_map[team_name] = team
            print(f"Ensured Team: {team_name}")

        # 4. User (Athlete)
        first_name = entry['first_name']
        last_name = entry['last_name']
        username = slugify(f"{first_name}-{last_name}")
        
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'role': 'athlete'
            }
        )
        if created:
            user.set_unusable_password()
            user.save()
            print(f"Created Athlete: {first_name} {last_name}")

        # 5. AthleteProfile
        profile = user.athlete_profile
        profile.current_team = teams_map[team_name]
        profile.save()

    print("Seed completed successfully.")

if __name__ == "__main__":
    seed()
