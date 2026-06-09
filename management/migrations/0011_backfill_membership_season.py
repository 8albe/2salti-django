# Generated for Macro 16 Fase 2 (fetta 2b): backfill Membership.season.
#
# Data-migration che popola la FK transitoria Membership.season (aggiunta NULL
# in 0010). Derivazione: team -> team.league -> league.season_fk -> core.Season.
# Fallback per record senza team/lega/season_fk: la Season corrente dello sport
# del contesto (membership.society.sport), se univoca. Ramo difensivo: se nulla
# e' derivabile, si lascia season=NULL e si logga un warning (no crash).
#
# Idempotente: rieseguendo la funzione lo stato non cambia (si scrive solo dove
# la stagione derivata differisce da quella gia' presente). Reverse: azzera il
# campo (UPDATE season=NULL) -- rollback-safe, la colonna resta nullable fino
# alla fetta 2c.
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def _derive_season(membership, Season):
    """Stagione da assegnare alla membership, o None se non derivabile.

    1) team -> league -> league.season_fk (derivazione primaria, deterministica)
    2) fallback: unica Season is_current per lo sport del contesto (society.sport)
    """
    team = membership.team
    if team is not None and team.league_id is not None:
        league = team.league
        if league.season_fk_id is not None:
            return league.season_fk

    # Fallback: stagione corrente dello sport del contesto. Si esige unicita'
    # (il constraint unique_current_season_per_sport la garantisce, ma il filtro
    # difensivo evita assunzioni se il dato fosse incoerente).
    sport_id = membership.society.sport_id
    current = list(Season.objects.filter(is_current=True, sport_id=sport_id)[:2])
    if len(current) == 1:
        return current[0]
    return None


def backfill_membership_season(apps, schema_editor):
    Membership = apps.get_model("management", "Membership")
    Season = apps.get_model("core", "Season")

    qs = Membership.objects.select_related("team__league__season_fk", "society")
    updated = unchanged = defended = 0
    for membership in qs:
        season = _derive_season(membership, Season)
        if season is None:
            defended += 1
            logger.warning(
                "[backfill_membership_season] Membership pk=%s: stagione non "
                "derivabile (team/lega/season_fk assenti e fallback is_current "
                "non univoco) -> resta NULL",
                membership.pk,
            )
            continue
        if membership.season_id == season.pk:
            unchanged += 1
            continue
        membership.season_id = season.pk
        membership.save(update_fields=["season"])
        updated += 1
        logger.info(
            "[backfill_membership_season] Membership pk=%s season -> pk=%s (%s)",
            membership.pk, season.pk, season.label,
        )

    logger.info(
        "[backfill_membership_season] done: updated=%s unchanged=%s defended(NULL)=%s",
        updated, unchanged, defended,
    )


def reverse_backfill(apps, schema_editor):
    Membership = apps.get_model("management", "Membership")
    n = Membership.objects.update(season=None)
    logger.info("[backfill_membership_season] reverse: %s Membership -> season=NULL", n)


class Migration(migrations.Migration):

    dependencies = [
        ("management", "0010_membership_season"),
    ]

    operations = [
        migrations.RunPython(backfill_membership_season, reverse_backfill),
    ]
