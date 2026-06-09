# Generated for Macro 16 Fase 1b: backfill League.season_fk dallo storico.
"""Data-migration: popola League.season_fk collegando ogni lega alla Season con
stessa coppia (sport, label = stringa League.season).

Difensiva e idempotente:
- per ogni League cerca la Season con (sport_id, label == league.season);
- se la trova, setta season_fk (re-run: sovrascrive con lo stesso valore, no-op);
- se NON la trova (non deve accadere post-0012), lascia season_fk = NULL e
  registra un warning, SENZA crashare. La stringa League.season resta la fonte
  di verita' in questa fase, quindi un NULL e' recuperabile rieseguendo il
  forward dopo aver sistemato i dati.

Reverse: rimette season_fk = NULL su tutte le leghe. Con PROTECT, l'ordinamento
delle migration garantisce che il reverse di 0014 azzeri le FK prima che il
reverse di 0012 cancelli le Season, quindi quel delete resta sicuro (NON va
toccato il reverse di 0012).

Usa apps.get_model: modelli storici, niente dipendenza dal codice applicativo.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def backfill_season_fk(apps, schema_editor):
    Season = apps.get_model('core', 'Season')
    League = apps.get_model('core', 'League')

    # Indice (sport_id, label) -> season_id per evitare una query per lega.
    season_index = {
        (sport_id, label): season_id
        for season_id, sport_id, label in Season.objects.values_list('id', 'sport_id', 'label')
    }

    unmatched = 0
    for league in League.objects.all():
        season_id = season_index.get((league.sport_id, league.season))
        if season_id is None:
            unmatched += 1
            logger.warning(
                "backfill_season_fk: nessuna Season per League id=%s "
                "(sport_id=%s, season=%r); season_fk lasciata NULL.",
                league.id, league.sport_id, league.season,
            )
            continue
        # Idempotente: re-run riscrive lo stesso valore.
        if league.season_fk_id != season_id:
            league.season_fk_id = season_id
            league.save(update_fields=['season_fk'])

    if unmatched:
        logger.warning(
            "backfill_season_fk: %s leghe senza Season corrispondente "
            "(season_fk = NULL).", unmatched,
        )


def clear_season_fk(apps, schema_editor):
    # Reverse: azzera tutte le FK. Necessario perche' con PROTECT una Season
    # con leghe collegate non sarebbe cancellabile dal reverse di 0012.
    League = apps.get_model('core', 'League')
    League.objects.update(season_fk=None)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_link_league_to_season'),
    ]

    operations = [
        migrations.RunPython(backfill_season_fk, clear_season_fk),
    ]
