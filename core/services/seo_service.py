import json
from django.urls import reverse
from django.conf import settings

class SEOService:
    @staticmethod
    def get_website_schema(request):
        return {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "2salti",
            "url": request.build_absolute_uri('/'),
            "description": "La piattaforma per il volley e la pallanuoto. Risultati, classifiche e statistiche."
        }

    @staticmethod
    def get_organization_schema(request):
        return {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "2salti",
            "url": request.build_absolute_uri('/'),
            "logo": request.build_absolute_uri('/static/img/logo.png'), # Fallback
            "sameAs": [
                "https://www.facebook.com/2salti",
                "https://www.instagram.com/2salti"
            ]
        }

    @staticmethod
    def get_match_schema(request, match):
        schema = {
            "@context": "https://schema.org",
            "@type": "SportsEvent",
            "name": f"{match.home_team.society.name} vs {match.away_team.society.name}",
            "startDate": match.match_date.isoformat(),
            "homeTeam": {
                "@type": "SportsOrganization",
                "name": match.home_team.society.name,
                "url": request.build_absolute_uri(reverse('team_detail', args=[match.home_team.slug]))
            },
            "awayTeam": {
                "@type": "SportsOrganization",
                "name": match.away_team.society.name,
                "url": request.build_absolute_uri(reverse('team_detail', args=[match.away_team.slug]))
            },
            "sport": match.league.sport.name if match.league and match.league.sport else "Sport"
        }
        
        # Aggiungi location se disponibile (es. campo della squadra di casa)
        if hasattr(match.home_team.society, 'venue_name') and match.home_team.society.venue_name:
            schema["location"] = {
                "@type": "Place",
                "name": match.home_team.society.venue_name
            }
            
        return schema

    @staticmethod
    def get_team_schema(request, team):
        return {
            "@context": "https://schema.org",
            "@type": "SportsOrganization",
            "name": team.society.name,
            "url": request.build_absolute_uri(reverse('team_detail', args=[team.slug])),
            "memberOf": {
                "@type": "SportsLeague",
                "name": team.league.name if team.league else "Campionato"
            }
        }

    @staticmethod
    def get_user_schema(request, user):
        schema = {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": user.get_full_name() or user.username,
            "url": request.build_absolute_uri(reverse('profile', args=[user.username])),
        }
        
        # Determine Organization (MemberOf)
        org_name = None
        if user.role == 'athlete' and hasattr(user, 'athlete_profile') and user.athlete_profile.current_team:
            org_name = user.athlete_profile.current_team.society.name
        elif user.role == 'coach' and hasattr(user, 'coach_profile') and user.coach_profile.current_team:
            org_name = user.coach_profile.current_team.society.name
        elif user.role == 'referee':
            org_name = "Associazione Arbitri" # Generic fallback or specific if available
            schema["jobTitle"] = "Referee"
            
        if org_name:
            schema["memberOf"] = {
                "@type": "SportsOrganization",
                "name": org_name
            }
            
        return schema

    @staticmethod
    def get_breadcrumb_schema(request, items):
        """
        items: list of (name, url) tuples
        """
        breadcrumb_list = []
        for i, (name, url) in enumerate(items, 1):
            breadcrumb_list.append({
                "@type": "ListItem",
                "position": i,
                "name": name,
                "item": request.build_absolute_uri(url)
            })
            
        return {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": breadcrumb_list
        }
