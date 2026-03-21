from django.db import migrations

def seed_sports(apps, schema_editor):
    Sport = apps.get_model('core', 'Sport')
    sports = [
        {'name': 'Calcio a 11', 'slug': 'calcio-11', 'hex_color': '#10B981'},
        {'name': 'Calcio a 7', 'slug': 'calcio-7', 'hex_color': '#34D399'},
        {'name': 'Calcio a 5', 'slug': 'calcio-5', 'hex_color': '#059669'},
        {'name': 'Basket', 'slug': 'basket', 'hex_color': '#F59E0B'},
        {'name': 'Pallavolo', 'slug': 'pallavolo', 'hex_color': '#3B82F6'},
    ]
    for s_data in sports:
        # get_or_create is idempotent: if it exists, it won't crash or duplicate
        Sport.objects.get_or_create(slug=s_data['slug'], defaults=s_data)

def reverse_sports(apps, schema_editor):
    Sport = apps.get_model('core', 'Sport')
    Sport.objects.filter(slug__in=['calcio-11', 'calcio-7', 'calcio-5', 'basket', 'pallavolo']).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_league_slug'),
    ]

    operations = [
        migrations.RunPython(seed_sports, reverse_sports),
    ]
