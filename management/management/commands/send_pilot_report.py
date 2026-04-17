from django.core.management.base import BaseCommand
from management.pilot_services import send_daily_report_email


class Command(BaseCommand):
    help = 'Generate and send the daily pilot report email to configured recipients.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview report data without sending email.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN mode — email will NOT be sent.\n'))

        data, html = send_daily_report_email(dry_run=dry_run)

        self.stdout.write(f"\n=== Pilot Daily Report — {data['report_date']} ===")
        self.stdout.write(f"Overall Status: {data['overall_status']}")
        self.stdout.write(f"Open Blockers:  {data['open_blockers_count']}")
        self.stdout.write(f"New Bugs:       {data['new_bugs_count']}")
        self.stdout.write(f"Closed Bugs:    {data['closed_bugs_count']}")
        self.stdout.write(f"Recurring:      {data['recurring_issues_count']}")
        self.stdout.write(f"Next-Day:       {data['next_day_decision']}")
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('Email NOT sent (dry-run).'))
        else:
            self.stdout.write(self.style.SUCCESS('Daily report email sent successfully.'))
