from django.core.management.base import BaseCommand
from core.models import League
from matches.services.integrity_service import DataIntegrityService

class Command(BaseCommand):
    help = 'Controlla la coerenza tra i match pubblicati e le classifiche persistite.'

    def add_arguments(self, parser):
        parser.add_argument('--league-id', type=int, help='ID della lega specifica da controllare')

    def handle(self, *args, **options):
        league_id = options.get('league_id')
        
        if league_id:
            leagues = League.objects.filter(id=league_id)
        else:
            leagues = League.objects.all()

        total_issues = 0
        leagues_with_issues = 0

        for league in leagues:
            self.stdout.write(f"Controllo integrità per: {league}...")
            discrepancies = DataIntegrityService.check_league_standings(league)
            
            if discrepancies:
                leagues_with_issues += 1
                total_issues += len(discrepancies)
                self.stdout.write(self.style.WARNING(f" TROVATE {len(discrepancies)} DISCREPANZE:"))
                for d in discrepancies:
                    self.stdout.write(f"  - [{d['type']}] {d['message']}")
            else:
                self.stdout.write(self.style.SUCCESS(" OK - Nessuna discrepanza."))

        if total_issues > 0:
            self.stdout.write(self.style.ERROR(f"\nTOTALE: {total_issues} problemi in {leagues_with_issues} leghe."))
        else:
            self.stdout.write(self.style.SUCCESS("\nCORE INTEGRITY CHECK PASSED: Tutti i dati sono coerenti."))
