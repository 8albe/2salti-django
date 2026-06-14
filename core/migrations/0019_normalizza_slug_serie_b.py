# Bonifica slug disallineati (debito §10.x): le due leghe "serie B Maschile"
# (Girone C / Girone D, scaffolding di test) hanno slug non coerenti con il
# group_name e in quasi-collisione case-insensitive:
#   - Girone C  -> slug "...-girone-d"  (lettera del girone SBAGLIATA)
#   - Girone D  -> slug "...-girone-D"  (D maiuscola: slug non normalizzato)
# League.save() genera lo slug solo se vuoto (core/models.py), quindi NON
# auto-ripara gli slug esistenti: serve una data-migration esplicita.
#
# Selezione per ATTRIBUTI (mai pk): name iexact "serie B Maschile" + type "B".
# Lo slug finale e' ricalcolato con la STESSA logica di save():
#   slugify(f"{name}-{season_slug}-{group_name}"), season_slug = season con "/"->"-".
# Idempotente: scrive solo se il nuovo slug differisce da quello attuale.
#
# Ordine non commutativo: lo slug canonico di Girone D ("...-girone-d") e'
# attualmente occupato dal record Girone C. Si usa quindi un APPROCCIO A DUE
# PASSATE con slug temporaneo univoco ("{new}-tmp-{pk}") per azzerare ogni
# dipendenza dall'ordine ed evitare collisioni transitorie sul vincolo unique.
# Guard anti-collisione (come core/0017): se lo slug finale e' occupato da un
# record ESTRANEO al set, si salta quel record, si RIPRISTINA il suo slug
# originale (per non lasciarlo sul temporaneo) e si logga un warning.
#
# Reverse: no-op documentato (come core/0017). Il reverse non deve ripristinare
# slug malformati; il rollback reale e' il restore da backup.
import logging

from django.db import migrations
from django.utils.text import slugify

logger = logging.getLogger(__name__)

TARGET_NAME = "serie B Maschile"
TARGET_TYPE = "B"


def _canonical_slug(league):
    season_slug = (league.season or "").replace("/", "-")
    return slugify(f"{league.name}-{season_slug}-{league.group_name}")


def normalizza_slug_serie_b(apps, schema_editor):
    League = apps.get_model("core", "League")

    targets = League.objects.filter(name__iexact=TARGET_NAME, league_type=TARGET_TYPE)

    # (league, old_slug, new_slug) solo per i record che cambiano davvero.
    to_fix = []
    for league in targets:
        new_slug = _canonical_slug(league)
        if new_slug != league.slug:
            to_fix.append((league, league.slug, new_slug))

    if not to_fix:
        logger.info(
            "[normalizza_slug_serie_b] nessuno slug da normalizzare: no-op"
        )
        return

    target_pks = {league.pk for league, _, _ in to_fix}

    # Passata 1: slug temporaneo univoco -> libera gli slug "vecchi"/canonici
    # all'interno del set, eliminando la dipendenza dall'ordine.
    for league, old_slug, new_slug in to_fix:
        league.slug = f"{new_slug}-tmp-{league.pk}"
        league.save(update_fields=["slug"])
        logger.info(
            "[normalizza_slug_serie_b] pass1 pk=%s group=%r %r -> temp %r",
            league.pk, league.group_name, old_slug, league.slug,
        )

    # Passata 2: slug finale, con guard anti-collisione su record estranei.
    for league, old_slug, new_slug in to_fix:
        clash = (
            League.objects.exclude(pk=league.pk)
            .exclude(pk__in=target_pks)
            .filter(slug=new_slug)
            .exists()
        )
        if clash:
            league.slug = old_slug
            league.save(update_fields=["slug"])
            logger.warning(
                "[normalizza_slug_serie_b] pk=%s group=%r: slug finale %r gia' "
                "occupato da record estraneo -> SKIP, ripristino %r",
                league.pk, league.group_name, new_slug, old_slug,
            )
            continue
        league.slug = new_slug
        league.save(update_fields=["slug"])
        logger.info(
            "[normalizza_slug_serie_b] pass2 pk=%s group=%r -> slug %r",
            league.pk, league.group_name, new_slug,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_remove_category_fields"),
    ]

    operations = [
        migrations.RunPython(
            normalizza_slug_serie_b, migrations.RunPython.noop
        ),
    ]
