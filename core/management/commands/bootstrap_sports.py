from django.core.management.base import BaseCommand
from core.models import Sport

class Command(BaseCommand):
    help = 'Initialize or update the list of supported sports in the platform'

    def handle(self, *args, **options):
        # Pallanuoto-only (scope decision 2026-07, FUTURE_IDEAS.md §2): seeding
        # other sports would resurrect the orphan rows deleted by core.0025
        # and re-show the home sport navigator ({% if sports|length > 1 %}).
        sports_data = [
            {'name': 'Pallanuoto', 'slug': 'pallanuoto', 'hex_color': '#2563eb', 'icon': '🤽'},
        ]

        self.stdout.write('🚀 Bootstrapping sports...')
        
        count_created = 0
        count_updated = 0
        
        for data in sports_data:
            sport, created = Sport.objects.update_or_create(
                slug=data['slug'],
                defaults=data
            )
            if created:
                count_created += 1
                self.stdout.write(f"   [NEW] {sport.name}")
            else:
                count_updated += 1
                self.stdout.write(f"   [UPD] {sport.name}")
        
        self.stdout.write(self.style.SUCCESS(f'✨ Done! Created {count_created}, Updated {count_updated} sports.'))
