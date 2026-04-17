from django.core.management.base import BaseCommand
from management.ops_services import run_ops_check

class Command(BaseCommand):
    help = 'Run automated ops checks (morning/afternoon/evening) for 2salti pilot operations.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            choices=['morning', 'afternoon', 'evening'],
            required=True,
            help="Which ops check to execute.",
        )

    def handle(self, *args, **options):
        mode = options['mode']
        self.stdout.write(f"Starting {mode} ops check...")
        
        result = run_ops_check(mode)
        
        self.stdout.write(f"Check finished: Overall status {result['overall_status']}")
        self.stdout.write(f"Findings: {len(result['findings'])}")
        
        if result['overall_status'] == 'GREEN':
            self.stdout.write(self.style.SUCCESS('Status: GREEN'))
        elif result['overall_status'] == 'YELLOW':
            self.stdout.write(self.style.WARNING('Status: YELLOW'))
        else:
            self.stdout.write(self.style.ERROR('Status: RED'))
