from django.db import transaction
from django.db.models import F
from core.models import League, LeagueStanding, Team
from matches.models import Match

class StandingsService:
    @staticmethod
    def rebuild_for_league(league):
        """Ricalcola e persiste la classifica per un intero campionato/stagione."""
        with transaction.atomic():
            expected_data = StandingsService._calculate_expected_standings(league)
            
            # Eliminiamo le vecchie standings per questa lega
            LeagueStanding.objects.filter(league=league).delete()
            
            new_standings = []
            for team_id, data in expected_data.items():
                new_standings.append(LeagueStanding(
                    league=league,
                    team=data['team'],
                    season=league.season,
                    played=data['played'],
                    won=data['won'],
                    drawn=data['drawn'],
                    lost=data['lost'],
                    goals_for=data['goals_for'],
                    goals_against=data['goals_against'],
                    goal_diff=data['goal_diff'],
                    points=data['points']
                ))
            
            # Ordinamento e Ranking (Points -> Goal Diff -> Goals For)
            new_standings.sort(key=lambda x: (x.points, x.goal_diff, x.goals_for), reverse=True)
            for idx, s in enumerate(new_standings):
                s.rank = idx + 1
            
            # Bulk create
            LeagueStanding.objects.bulk_create(new_standings)
            
        return len(new_standings)

    @staticmethod
    def _calculate_expected_standings(league):
        """Calcola i dati della classifica 'attesi' basandosi sui match pubblicati."""
        teams = league.teams.all()
        expected = {}
        
        # Recupera il sistema punti dallo sport (default WP: 3-1-0)
        ps = league.sport.point_system or {'win': 3, 'draw': 1, 'loss': 0}
        p_win = ps.get('win', 3)
        p_draw = ps.get('draw', 1)
        p_loss = ps.get('loss', 0)

        matches_base = Match.objects.filter(
            league=league, 
            is_finished=True, 
            reports__status='PUBLISHED'
        ).distinct()

        for team in teams:
            m_home = matches_base.filter(home_team=team)
            m_away = matches_base.filter(away_team=team)
            
            played = m_home.count() + m_away.count()
            
            wins = m_home.filter(home_score__gt=F('away_score')).count() + \
                   m_away.filter(away_score__gt=F('home_score')).count()
            
            draws = m_home.filter(home_score=F('away_score')).count() + \
                    m_away.filter(away_score=F('home_score')).count()
            
            losses = played - wins - draws
            
            gf = 0
            ga = 0
            for m in m_home:
                gf += m.home_score
                ga += m.away_score
            for m in m_away:
                gf += m.away_score
                ga += m.home_score
            
            expected[team.id] = {
                'team': team,
                'played': played,
                'won': wins,
                'drawn': draws,
                'lost': losses,
                'goals_for': gf,
                'goals_against': ga,
                'goal_diff': gf - ga,
                'points': (wins * p_win) + (draws * p_draw) + (losses * p_loss)
            }
        return expected

    @staticmethod
    def rebuild_all():
        """Aggiorna tutto"""
        leagues = League.objects.all()
        count = 0
        for l in leagues:
            StandingsService.rebuild_for_league(l)
            count += 1
        return count
