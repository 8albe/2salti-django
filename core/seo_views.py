from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from .models import Sport, Team, League, Society
from matches.models import Match
from django.contrib.auth import get_user_model

User = get_user_model()

from django.conf import settings

def robots_txt(request):
    """Serves robots.txt based on host/environment."""
    env = getattr(settings, 'ENVIRONMENT_NAME', 'development')
    
    if env != 'production':
        # Prevent indexing in dev/staging/any non-prod env
        content = "User-agent: *\nDisallow: /\n"
    else:
        # Production rules
        content = "User-agent: *\nDisallow: /admin/\nDisallow: /management/\n"
        content += f"Sitemap: {request.build_absolute_uri(reverse('sitemap_xml'))}\n"
    
    return HttpResponse(content, content_type="text/plain")

def sitemap_xml(request):
    """Simple XML sitemap generator for MVP."""
    base_url = f"{request.scheme}://{request.get_host()}"
    urls = []
    
    # 1. Static/Home
    urls.append(reverse('home'))
    
    # 2. Sports
    for sport in Sport.objects.all():
        urls.append(reverse('sport_detail', args=[sport.slug]))
        urls.append(reverse('sport_matches', args=[sport.slug]))
    
    # 3. Leagues/Standings
    for league in League.objects.all():
        urls.append(reverse('league_standings', args=[league.id]))
        # Fix league_stats if it exists (check name or slug)
        try:
            urls.append(reverse('league_stats', args=[league.slug]))
        except:
            pass
        
    # 4. Societies & Teams
    for society in Society.objects.all():
        urls.append(reverse('society_detail', args=[society.slug]))
    for team in Team.objects.all():
        urls.append(reverse('team_detail', args=[team.slug]))
        
    # 5. Matches (recently finished or upcoming)
    for match in Match.objects.all().order_by('-match_date')[:500]: 
        urls.append(reverse('match_detail', args=[match.id]))
        
    # 6. Athletes (public profiles)
    for athlete in User.objects.filter(role='athlete', setup_completed=True)[:500]:
        urls.append(reverse('profile', args=[athlete.username]))

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url in urls:
        xml += f'  <url><loc>{base_url}{url}</loc><changefreq>daily</changefreq></url>\n'
    xml += '</urlset>'
    
    return HttpResponse(xml, content_type="application/xml")
