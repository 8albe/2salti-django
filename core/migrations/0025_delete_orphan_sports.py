# Data migration only — no schema changes. Deletes orphan Sport seed rows
# (zero references on ALL four FKs), never the 'pallanuoto' row.
from django.db import migrations


def delete_orphan_sports(apps, schema_editor):
    """Delete Sport rows that are empty seeds: slug != 'pallanuoto' AND zero
    references across all four FKs pointing at Sport (core.Society, core.League,
    core.Season, matches.SportEventConfig).

    Double guard: the exclude(slug='pallanuoto') makes the pallanuoto row never
    a candidate, even if it hypothetically had zero references; the zero-ref
    check makes the delete cascade-free by construction (only rows nothing
    points at are deleted). Guard is by slug, not pk: pallanuoto's pk is not
    guaranteed identical across environments.
    """
    Sport = apps.get_model('core', 'Sport')
    Society = apps.get_model('core', 'Society')
    League = apps.get_model('core', 'League')
    Season = apps.get_model('core', 'Season')
    SportEventConfig = apps.get_model('matches', 'SportEventConfig')

    for sport in Sport.objects.exclude(slug='pallanuoto').order_by('pk'):
        refs = {
            'societies': Society.objects.filter(sport=sport).count(),
            'leagues': League.objects.filter(sport=sport).count(),
            'seasons': Season.objects.filter(sport=sport).count(),
            'event_configs': SportEventConfig.objects.filter(sport=sport).count(),
        }
        label = f"Sport pk={sport.pk} name={sport.name!r} slug={sport.slug!r}"
        if all(count == 0 for count in refs.values()):
            sport.delete()
            print(f"  [0025] DELETED orphan {label}")
        else:
            print(f"  [0025] PRESERVED {label} — references: {refs}")


class Migration(migrations.Migration):
    """Reverse is a documented noop: the deleted rows are empty seed data with
    no informational content (created by the old multi-sport bootstrap_sports
    command), their pks are not guaranteed to match across environments, and
    restoring them would only re-introduce garbage. The forward pass logs
    pk/name/slug of every deleted row, so the inventory is preserved in the
    migrate output. Noop keeps the migration reversible without errors for
    historical-state test runs.
    """

    dependencies = [
        ('core', '0024_society_tier_comped_db_default'),
        ('matches', '0016_alter_matchreport_match'),
    ]

    operations = [
        migrations.RunPython(delete_orphan_sports, migrations.RunPython.noop),
    ]
