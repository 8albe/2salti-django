from django.core.management.base import BaseCommand
from management.pilot_services import check_and_send_urgent_alerts


class Command(BaseCommand):
    help = 'Check for urgent pilot alert conditions and send email if triggered.'

    def handle(self, *args, **options):
        self.stdout.write('Checking pilot alert triggers...\n')

        alerts = check_and_send_urgent_alerts()

        if alerts:
            self.stdout.write(self.style.WARNING(f'{len(alerts)} alert trigger(s) detected:'))
            for alert in alerts:
                self.stdout.write(f"  [{alert['trigger']}] {alert['message']}")
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('Alert processing complete.'))
        else:
            self.stdout.write(self.style.SUCCESS('No alert triggers detected. All clear.'))
