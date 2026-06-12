# Generated for Macro 16 Fase 1b: schema FK League.season_fk -> core.Season.
"""Schema-migration: aggiunge League.season_fk (FK transitoria a Season).

Nullable (null=True, blank=True) per consentire il backfill rollback-safe in 0014.
on_delete=PROTECT: una Season con leghe collegate non dev'essere cancellabile.
related_name='leagues' su Season (non collide con Sport.leagues: target diverso).

La stringa League.season RESTA intatta: nessun impatto sugli unique_together.
Reverse: drop column nativo (Django gestisce il RemoveField inverso).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_populate_season'),
    ]

    operations = [
        migrations.AddField(
            model_name='league',
            name='season_fk',
            field=models.ForeignKey(blank=True, help_text='Stagione (FK transitoria, Fase 1b)', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='leagues', to='core.season'),
        ),
    ]
