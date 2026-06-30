from django.core.management.base import BaseCommand
from core.models import Sport

class Command(BaseCommand):
    help = 'Initialize or update the list of supported sports in the platform'

    def handle(self, *args, **options):
        sports_data = [
            {'name': 'Calcio a 11', 'slug': 'calcio-11', 'hex_color': '#10B981', 'icon': '⚽'},
            {'name': 'Calcio a 7', 'slug': 'calcio-7', 'hex_color': '#34D399', 'icon': '⚽'},
            {'name': 'Calcio a 5', 'slug': 'calcio-5', 'hex_color': '#059669', 'icon': '⚽'},
            {'name': 'Basket', 'slug': 'basket', 'hex_color': '#F59E0B', 'icon': '🏀'},
            {'name': 'Pallavolo', 'slug': 'pallavolo', 'hex_color': '#3B82F6', 'icon': '🏐'},
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
