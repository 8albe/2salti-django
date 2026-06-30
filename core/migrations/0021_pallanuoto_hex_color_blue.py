# Data migration — Macro 17 Fase 2 (code B)
# Allinea il colore tema della Pallanuoto al brand blue-600 (#2563eb).
# Difensiva: tocca SOLO lo sport reale slug='pallanuoto' e SOLO se ancora
# sul vecchio default ciano '#00ffff'. Non tocca a tappeto gli altri Sport
# (alcuni in dev hanno '#00ffff' ma sono artefatti di test, non la pallanuoto).
# Idempotente: rilanciata non fa nulla. Reversibile.

from django.db import migrations

OLD = '#00ffff'
NEW = '#2563eb'
SLUG = 'pallanuoto'


def set_pallanuoto_blue(apps, schema_editor):
    Sport = apps.get_model('core', 'Sport')
    updated = Sport.objects.filter(slug=SLUG, hex_color=OLD).update(hex_color=NEW)
    print(f"  [data-migration] Sport(slug={SLUG!r}) hex_color {OLD} -> {NEW}: {updated} row(s)")


def revert_pallanuoto_cyan(apps, schema_editor):
    Sport = apps.get_model('core', 'Sport')
    reverted = Sport.objects.filter(slug=SLUG, hex_color=NEW).update(hex_color=OLD)
    print(f"  [data-migration] revert Sport(slug={SLUG!r}) hex_color {NEW} -> {OLD}: {reverted} row(s)")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_alter_sport_hex_color_default'),
    ]

    operations = [
        migrations.RunPython(set_pallanuoto_blue, revert_pallanuoto_cyan),
    ]
