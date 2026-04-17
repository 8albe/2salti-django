from django.core.management.base import BaseCommand
from core.models import League
from matches.services.integrity_service import DataIntegrityService
from core.services.notification_service import NotificationService
from matches.services.standings_service import StandingsService

class Command(BaseCommand):
    help = 'Esegue il controllo periodico dell\'integrità e segnala eventuali errori.'

    def add_arguments(self, parser):
        parser.add_argument('--auto-rebuild', action='store_true', help='Esegue automaticamente il rebuild in caso di errore')

    def handle(self, *args, **options):
        auto_rebuild = options.get('auto_rebuild')
        leagues = League.objects.all()
        
        total_issues = 0
        leagues_impacted = 0
        
        self.stdout.write("Avvio Monitoraggio Integrità Dati...")
        
        for league in leagues:
            issues = DataIntegrityService.check_league_standings(league)
            if issues:
                leagues_impacted += 1
                total_issues += len(issues)
                
                self.stdout.write(self.style.WARNING(f"Mismatch rilevato in {league}: {len(issues)} errori."))
                
                # Invia Alert
                NotificationService.notify_integrity_mismatch(league, issues)
                
                # Eventuale Auto-Fix
                if auto_rebuild:
                    self.stdout.write(f"  Auto-rebuild in corso per {league}...")
                    StandingsService.rebuild_for_league(league)
                    self.stdout.write(self.style.SUCCESS(f"  {league} riallineato."))
            else:
                self.stdout.write(f"Lega {league}: OK")

        if total_issues > 0:
            status_msg = f"Monitoraggio completato: {total_issues} problemi in {leagues_impacted} leghe."
            self.stdout.write(self.style.ERROR(status_msg))
            # Exit code 1 for automation tools to detect failure
            import sys
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("Monitoraggio completato: Sistema in salute."))
