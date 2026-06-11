# Macro 16 Fase 3: classificazione del tipo lega per PATTERN DI NOME.
#
# Riclassifica le leghe esistenti sul campo league_type (lista chiusa A1-D /
# U10-U20) derivando il tipo dal nome — MAI da pk (la migration girera' anche
# su prod, dove le leghe possono differire dal dev). Ordine di derivazione:
#   1) marcatore Under esplicito nel nome ("U16", "U 18", "U18A", ...)
#   2) etichetta tradizionale giovanile (pulcini/esordienti/ragazzi/allievi/
#      juniores) — mappa 1:1 sull'Under canonico
#   3) "serie <tipo>" per i tipi dei grandi (A1, A2, B, C, D)
# Nomi non riconosciuti: league_type resta NULL e si logga un warning
# ("Null invece di invenzione" — si classifica a mano, non si indovina).
#
# Idempotente: ricalcola e scrive solo se il valore differisce. Reverse:
# azzera league_type (la colonna resta, aggiunta in 0015).
import logging
import re

from django.db import migrations

logger = logging.getLogger(__name__)

_UNDER_RE = re.compile(r"\bU\s?(10|12|14|16|18|20)", re.IGNORECASE)
_TRADITIONAL = {
    "pulcini": "U10",
    "esordienti": "U12",
    "ragazzi": "U14",
    "allievi": "U16",
    "juniores": "U18",
}
_SENIOR_RE = re.compile(r"\bserie\s+(A1|A2|B|C|D)\b", re.IGNORECASE)


def _classify(name):
    """Tipo lega derivato dal nome, o None se non riconoscibile."""
    m = _UNDER_RE.search(name)
    if m:
        return f"U{m.group(1)}"
    lowered = name.lower()
    for keyword, under in _TRADITIONAL.items():
        if keyword in lowered:
            return under
    m = _SENIOR_RE.search(name)
    if m:
        return m.group(1).upper()
    return None


def classify_league_type(apps, schema_editor):
    League = apps.get_model("core", "League")

    updated = unchanged = unrecognized = 0
    for league in League.objects.all():
        derived = _classify(league.name)
        if derived is None:
            unrecognized += 1
            logger.warning(
                "[classify_league_type] League pk=%s name=%r: tipo non "
                "riconoscibile dal nome -> league_type resta NULL "
                "(classificare a mano)",
                league.pk, league.name,
            )
            continue
        if league.league_type == derived:
            unchanged += 1
            continue
        league.league_type = derived
        league.save(update_fields=["league_type"])
        updated += 1
        logger.info(
            "[classify_league_type] League pk=%s name=%r -> league_type=%s",
            league.pk, league.name, derived,
        )

    logger.info(
        "[classify_league_type] done: updated=%s unchanged=%s unrecognized=%s",
        updated, unchanged, unrecognized,
    )


def reverse_classify(apps, schema_editor):
    League = apps.get_model("core", "League")
    n = League.objects.update(league_type=None)
    logger.info("[classify_league_type] reverse: %s League -> league_type=NULL", n)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_league_type"),
    ]

    operations = [
        migrations.RunPython(classify_league_type, reverse_classify),
    ]
