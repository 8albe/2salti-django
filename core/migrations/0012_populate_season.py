# Generated for Macro 16 Fase 1a-ii: popolamento storico Season.
"""Data-migration: popola core.Season dallo storico delle stringhe League.season.

Per ogni coppia distinta (sport, label) presente su League crea una riga Season
(idempotente via get_or_create). Dopo aver creato le righe di uno sport, elegge
is_current=True sulla label MAX lessicografico di quello sport — stesso criterio
di ordinamento usato finora dalla view (order_by('-season')), cosi' la corrente
coincide bit-per-bit con quella che la view eleggerebbe oggi.

Lo schema (CreateModel + constraint) e' introdotto da 0011 e resta; questa
migration tocca solo i dati.

Reverse: cancella TUTTE le righe Season (Season.objects.all().delete()). E' lossy
ma interamente rigenerabile rieseguendo il forward di questa stessa migration
dai dati di League, che restano la fonte di verita' in questa fase (nessuna FK
League->Season ancora).
"""
from django.db import migrations


def populate_seasons(apps, schema_editor):
    Season = apps.get_model('core', 'Season')
    League = apps.get_model('core', 'League')

    # Coppie (sport, label) distinte presenti sullo storico delle leghe.
    labels_per_sport = {}
    for sport_id, label in League.objects.values_list('sport_id', 'season').distinct():
        if not label:
            continue
        labels_per_sport.setdefault(sport_id, set()).add(label)

    for sport_id, labels in labels_per_sport.items():
        # 1. Crea tutte le righe dello sport (idempotente: re-run non duplica).
        for label in labels:
            Season.objects.get_or_create(sport_id=sport_id, label=label)

        # 2. Elezione corrente = MAX lessicografico sulle label dello sport.
        #    Setta prima TUTTE a False, poi UNA a True: cosi' il constraint
        #    parziale unique_current_season_per_sport non viene mai violato.
        current_label = max(labels)
        Season.objects.filter(sport_id=sport_id).update(is_current=False)
        Season.objects.filter(sport_id=sport_id, label=current_label).update(is_current=True)


def delete_seasons(apps, schema_editor):
    # Lossy ma rigenerabile dal forward di questa stessa migration.
    Season = apps.get_model('core', 'Season')
    Season.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_season_season_unique_season_per_sport_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_seasons, delete_seasons),
    ]
