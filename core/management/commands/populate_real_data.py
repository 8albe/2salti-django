from django.core.management.base import BaseCommand
from core.models import Sport, Society, Team, League
from matches.models import Match
from datetime import datetime, timedelta
import random

class Command(BaseCommand):
    help = 'Popola database con squadre reali Serie A1 2025-2026 e calendario'

    def handle(self, *args, **options):
        self.stdout.write('🚀 Inizio popolamento dati reali...')

        # 1. SPORT
        sport, _ = Sport.objects.get_or_create(
            name='Pallanuoto',
            slug='pallanuoto',
            defaults={'hex_color': '#00ffff', 'icon': '🤽'}
        )

        # 2. CAMPIONATO
        league, _ = League.objects.get_or_create(
            name='Serie A1 Maschile',
            season='2025-2026',
            sport=sport,
            defaults={
                'category': 'SENIOR', 
                'level': 1,
                'group_name': '' # Girone unico
            }
        )
        self.stdout.write(f'✅ Campionato: {league}')

        # 3. SOCIETÀ E SQUADRE REALI
        teams_data = [
            ("Pro Recco", "Recco"),
            ("AN Brescia", "Brescia"),
            ("RN Savona", "Savona"),
            ("CC Ortigia 1928", "Siracusa"),
            ("Telimar Palermo", "Palermo"),
            ("Pallanuoto Trieste", "Trieste"),
            ("Iren Genova Quinto", "Genova"),
            ("CN Posillipo", "Napoli"),
            ("Roma Vis Nova", "Roma"),
            ("Nuoto Catania", "Catania"),
            ("De Akker Team", "Bologna"),
            ("RN Florentia", "Firenze"),
            ("Olympic Roma", "Roma"),
            ("Onda Forte", "Roma"), 
        ]

        teams_objs = []

        for name, city in teams_data:
            # Crea Società
            society, _ = Society.objects.get_or_create(
                name=name,
                sport=sport,
                defaults={'city': city, 'setup_completed': True}
            )
            
            # Crea Squadra Senior
            team, _ = Team.objects.get_or_create(
                society=society,
                category='SENIOR',
                defaults={'league': league}
            )
            
            # Assicura che la squadra sia iscritta al campionato corretto
            if team.league != league:
                team.league = league
                team.save()
                
            teams_objs.append(team)
            self.stdout.write(f'   - {team.name} ({city})')

        self.stdout.write(f'✅ {len(teams_objs)} Squadre verificate/create')

        # 4. GENERAZIONE CALENDARIO (ALGORITMO BERGER)
        # Se ci sono già partite per questo campionato, non duplicare tutto alla cieca
        existing_matches = Match.objects.filter(league=league).count()
        if existing_matches > 0:
            self.stdout.write(self.style.WARNING(f'⚠️ Trovate già {existing_matches} partite. Salto generazione calendario.'))
            return

        self.stdout.write('📅 Generazione Calendario (Algoritmo di Berger)...')
        
        n = len(teams_objs)
        if n % 2 != 0:
             # Aggiungi squadra "riposo" se dispari (ma qui sono 14, quindi ok)
             teams_objs.append(None)
             n += 1
        
        # Copia lista per manipolazione
        teams = list(teams_objs)
        
        # Giorni partita (Sabati)
        start_date = datetime(2025, 10, 11, 15, 0) # 11 Ottobre 2025, ore 15:00
        matches_to_create = []

        # Giornate = n - 1
        days = n - 1
        
        # ANDATA
        for day in range(days):
            match_date = start_date + timedelta(weeks=day)
            
            self.stdout.write(f'   Giornata {day+1} - {match_date.strftime("%d/%m/%Y")}')
            
            # Accoppiamenti
            for i in range(n // 2):
                t1 = teams[i]
                t2 = teams[n - 1 - i]
                
                if t1 is not None and t2 is not None:
                    # Alternanza casa/trasferta
                    if day % 2 == 0:
                        home, away = t1, t2
                    else:
                        home, away = t2, t1
                    
                    matches_to_create.append(Match(
                        league=league,
                        home_team=home,
                        away_team=away,
                        match_date=match_date,
                        location=f"Piscina {home.society.city}"
                    ))
            
            # Rotazione squadre (l'elemento 1 rimane fisso, gli altri ruotano)
            # teams[0] è fisso
            # muovi l'ultimo elemento in seconda posizione
            teams.insert(1, teams.pop())

        # RITORNO (stesso ordine, campi invertiti, + 13 settimane circa + pausa natalizia?)
        # Semplifichiamo: ritorno inizia dopo la fine dell'andata + 2 settimane
        return_start_date = start_date + timedelta(weeks=days + 2)
        
        # Reimposta ordine squadre originale per ricalcolare ritorno correttamente o usa la lista ruotata?
        # L'algoritmo di Berger genera le giornate. Per il ritorno basta invertire casa/trasferta della giornata X
        
        # Ricostruiamo le coppie dell'andata per il ritorno
        # Metodo più semplice: iterare matches_to_create dell'andata e crearne speculari
        
        matches_andata_count = len(matches_to_create)
        self.stdout.write(f'   Generati {matches_andata_count} match di Andata')
        
        matches_ritorno = []
        for match in matches_to_create:
            # Calcola data ritorno: data andata + (num_giornate + pausa) settimane
            # Approssimazione: + 15 settimane
            date_ritorno = match.match_date + timedelta(weeks=15)
            
            matches_ritorno.append(Match(
                league=league,
                home_team=match.away_team, # Invertito
                away_team=match.home_team, # Invertito
                match_date=date_ritorno,
                location=f"Piscina {match.away_team.society.city}"
            ))

        all_matches = matches_to_create + matches_ritorno
        Match.objects.bulk_create(all_matches)
        
        self.stdout.write(self.style.SUCCESS(f'✨ Completato! Inserite {len(all_matches)} partite totali.'))
