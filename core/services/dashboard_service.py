from django.utils import timezone
from django.db.models import Q, Count
from core.models import Team, LeagueStanding, Society
from matches.models import Match
from accounts.models import AccountProfileLink, AthleteProfile, CoachProfile, PresidentProfile

class DashboardService:
    @staticmethod
    def get_dashboard_data(user):
        """Metodo principale per generare il payload della dashboard basato sul ruolo."""
        
        # Struttura base del payload
        payload = {
            "user": {
                "username": user.username,
                "full_name": user.get_full_name(),
                "role": user.role,
                "is_verified": user.is_verified,
            },
            "modules": []
        }

        # Routing basato su ruolo e stato verifica
        if user.role == 'athlete' and user.is_verified:
            if hasattr(user, 'athlete_profile'):
                payload["modules"] = DashboardService._get_athlete_modules(user.athlete_profile)
        
        elif user.role == 'coach' and user.is_verified:
            if hasattr(user, 'coach_profile'):
                payload["modules"] = DashboardService._get_coach_modules(user.coach_profile)
        
        elif user.role == 'president':
            if hasattr(user, 'president_profile'):
                payload["modules"] = DashboardService._get_admin_modules(user.president_profile)
        
        # Se non ci sono moduli (o utente non verificato/senza claim), aggiungiamo il modulo guest
        if not payload["modules"]:
            payload["modules"] = DashboardService._get_guest_modules(user)
            
        return payload

    @staticmethod
    def _get_athlete_modules(profile):
        modules = []
        
        # 1. Stats Recap
        modules.append({
            "id": "athlete_stats",
            "type": "stats_recap",
            "title": "Recap Stagione",
            "data": {
                "total_goals": profile.total_goals,
                "total_matches": profile.total_matches,
                "total_expulsions": profile.total_expulsions
            }
        })
        
        # 2. Upcoming Matches
        if profile.current_team:
            upcoming = Match.objects.filter(
                Q(home_team=profile.current_team) | Q(away_team=profile.current_team),
                match_date__gte=timezone.now(),
                is_finished=False
            ).order_by('match_date')[:3]
            
            matches_data = []
            for m in upcoming:
                matches_data.append({
                    "id": m.id,
                    "date": m.match_date.isoformat(),
                    "opponent": m.away_team.name if m.home_team == profile.current_team else m.home_team.name,
                    "is_home": m.home_team == profile.current_team,
                    "location": m.location
                })
            
            modules.append({
                "id": "upcoming_matches",
                "type": "match_list",
                "title": "Prossimi Impegni",
                "data": matches_data
            })
            
        # 3. Quick Links
        modules.append({
            "id": "quick_links",
            "type": "link_list",
            "title": "Accesso Rapido",
            "data": [
                {"label": "Il Mio Profilo Pubblico", "url": f"/atleta/{profile.user.username}/", "icon": "user"},
                {"label": "Classifica Campionato", "url": f"/campionato/{profile.current_team.league.id}/" if profile.current_team and profile.current_team.league else "#", "icon": "trophy"}
            ]
        })
        
        return modules

    @staticmethod
    def _get_coach_modules(profile):
        modules = []
        
        # 1. Team Record
        if profile.current_team and profile.current_team.league:
            standing = LeagueStanding.objects.filter(
                league=profile.current_team.league,
                team=profile.current_team
            ).first()
            
            if standing:
                modules.append({
                    "id": "team_record",
                    "type": "record_card",
                    "title": f"Record {profile.current_team.name}",
                    "data": {
                        "won": standing.won,
                        "drawn": standing.drawn,
                        "lost": standing.lost,
                        "rank": standing.rank,
                        "points": standing.points
                    }
                })
        
        # 2. Upcoming Matches (simile ad atleta)
        if profile.current_team:
            upcoming = Match.objects.filter(
                Q(home_team=profile.current_team) | Q(away_team=profile.current_team),
                match_date__gte=timezone.now(),
                is_finished=False
            ).order_by('match_date')[:3]
            
            matches_data = []
            for m in upcoming:
                matches_data.append({
                    "id": m.id,
                    "date": m.match_date.isoformat(),
                    "home_team": m.home_team.name,
                    "away_team": m.away_team.name,
                    "location": m.location
                })
                
            modules.append({
                "id": "upcoming_matches",
                "type": "match_list",
                "title": "Calendario Squadra",
                "data": matches_data
            })

            # 3. Coach specific shortcuts
            modules.append({
                "id": "coach_actions",
                "type": "action_list",
                "title": "Gestione Squadra",
                "data": [
                    {"label": "Invia Referto Digitale", "url": "/api/referti/digital/", "variant": "primary"},
                    {"label": "Analisi Avversari", "url": "#", "variant": "secondary", "disabled": True}
                ]
            })

        return modules

    @staticmethod
    def _get_admin_modules(profile):
        modules = []
        society = profile.managed_society
        
        if not society:
            return modules
            
        # 1. Club KPIs
        team_count = society.teams.count()
        athlete_count = AthleteProfile.objects.filter(current_team__society=society).count()

        modules.append({
            "id": "club_kpis",
            "type": "kpi_grid",
            "title": f"Dashboard {society.name}",
            "data": {
                "total_teams": team_count,
                "total_athletes": athlete_count,
                "active_members": athlete_count # Placeholder for paid subs in future
            }
        })
        
        # 2. Action Items (Alerts)
        alerts = []
        
        # Pending Claims
        pending_claims = AccountProfileLink.objects.filter(
            status='PENDING',
            athlete_profile__current_team__society=society
        ).count()
        
        if pending_claims > 0:
            alerts.append({
                "id": "pending_claims",
                "severity": "warning",
                "label": f"Ci sono {pending_claims} richieste di claim profilo da approvare",
                "action_url": "/admin/accounts/accountprofilelink/?status__exact=PENDING"
            })
            
        # Missing Reports
        missing_reports = Match.objects.filter(
            Q(home_team__society=society) | Q(away_team__society=society),
            match_date__lt=timezone.now(),
            has_report=False
        ).count()
        
        if missing_reports > 0:
            alerts.append({
                "id": "missing_reports",
                "severity": "info",
                "label": f"{missing_reports} partite giocate sono senza referto caricato",
                "action_url": "#"
            })
            
        if alerts:
            modules.append({
                "id": "admin_alerts",
                "type": "alert_list",
                "title": "Azioni Richieste",
                "data": alerts
            })
            
        return modules

    @staticmethod
    def _get_guest_modules(user):
        """Modulo per utenti non verificati o Guest."""
        return [
            {
                "id": "onboarding_cta",
                "type": "hero_banner",
                "title": "Sblocca il tuo Spazio Sportivo",
                "data": {
                    "message": "Associa il tuo account a un profilo atleta o coach per vedere statistiche, classifiche e referti.",
                    "primary_action": {"label": "Esegui Claim Profilo", "url": "/onboarding/claim/"},
                    "secondary_action": {"label": "Verifica Identità", "url": "/onboarding/identity/"}
                }
            }
        ]
