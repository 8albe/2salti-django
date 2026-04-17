from django.core.management.base import BaseCommand
from core.models import League
from django.utils import timezone
from matches.services.standings_service import StandingsService

class Command(BaseCommand):
    help = 'Ricalcola le classifiche persistite (LeagueStanding) partendo dai match pubblicati.'

    def add_arguments(self, parser):
        parser.add_argument('--league-id', type=int, help='ID del campionato specifico da ricalcolare')
        parser.add_argument('--verify', action='store_true', help='Esegue un check di integrità prima del ricalcolo')
        parser.add_argument('--force-all', action='store_true', help='Ricalcola tutte le leghe ignorando il flag needs_rebuild')

    def handle(self, *args, **options):
        league_id = options.get('league_id')
        verify = options.get('verify')
        force_all = options.get('force_all')
        
        if verify:
            from matches.services.integrity_service import DataIntegrityService
        
        if league_id:
            try:
                league = League.objects.get(id=league_id)
                self._process_league(league, verify, DataIntegrityService if verify else None)
            except League.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Lega con ID {league_id} non trovata."))
        elif force_all:
            self.stdout.write("Ricalcolando tutte le classifiche (Force All)...")
            count = 0
            for league in League.objects.all():
                self._process_league(league, verify, DataIntegrityService if verify else None)
                count += 1
            self.stdout.write(self.style.SUCCESS(f"Ricalcolate {count} classifiche."))
        else:
            # Comportamento predefinito: ricalcola solo le leghe 'dirty'
            leagues = League.objects.filter(needs_rebuild=True)
            if not leagues.exists():
                self.stdout.write(self.style.SUCCESS("Nessuna lega richiede il ricalcolo (needs_rebuild=False)."))
                return
                
            self.stdout.write(f"Trovate {leagues.count()} leghe con ricalcolo richiesto...")
            for league in leagues:
                self._process_league(league, verify, DataIntegrityService if verify else None)

    def _process_league(self, league, verify, integrity_service):
        if verify and integrity_service:
            self.stdout.write(f"Verificando {league} prima del rebuild...")
            issues = integrity_service.check_league_standings(league)
            if not issues:
                self.stdout.write(self.style.SUCCESS("  Dati già coerenti. Rebuild non strettamente necessario."))
            else:
                self.stdout.write(self.style.WARNING(f"  Trovate {len(issues)} discrepanze. Procedo al riallineamento."))
        
        try:
            self.stdout.write(f"Ricalcolando classifica per: {league}")
            count = StandingsService.rebuild_for_league(league)
            
            # Aggiornamento flag e timestamp
            league.needs_rebuild = False
            league.last_rebuild_at = timezone.now()
            league.save(update_fields=['needs_rebuild', 'last_rebuild_at'])
            
            self.stdout.write(self.style.SUCCESS(f"  OK: Classifica ricalcolata ({count} teams)."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ERRORE su {league}: {str(e)}"))
