# Macro 16 Fase 2 (fetta 2d-7): flip Membership.season a NOT NULL.
#
# Ultimo gradino della Fase 2: i 3 creation-site sono season-aware (2d-1/2d-4b)
# e lo storico e' backfillato (0011). Prima del flip, una RunPython consolida
# gli eventuali NULL residui (legacy/difensivi) con la stessa derivazione del
# backfill: team -> league -> season_fk, fallback Season is_current per sport.
#
# Fail-fast: se dopo la derivazione restano NULL non risolvibili, la migration
# SOLLEVA (elenco pk nel messaggio) e l'AlterField non viene applicato (la
# migration e' atomica): su un DB reale si decide caso per caso invece di
# inventare una stagione. Reverse: la colonna torna nullable (i valori
# consolidati restano).
import logging

from django.db import migrations, models
import django.db.models.deletion

logger = logging.getLogger(__name__)


def _derive_season(membership, Season):
    """Identica al backfill 0011: primaria team->league->season_fk, fallback
    unica Season is_current per society.sport, altrimenti None."""
    team = membership.team
    if team is not None and team.league_id is not None:
        league = team.league
        if league.season_fk_id is not None:
            return league.season_fk

    sport_id = membership.society.sport_id
    current = list(Season.objects.filter(is_current=True, sport_id=sport_id)[:2])
    if len(current) == 1:
        return current[0]
    return None


def consolidate_null_seasons(apps, schema_editor):
    Membership = apps.get_model("management", "Membership")
    Season = apps.get_model("core", "Season")

    qs = Membership.objects.filter(season__isnull=True).select_related(
        "team__league__season_fk", "society"
    )
    consolidated = 0
    unresolved = []
    for membership in qs:
        season = _derive_season(membership, Season)
        if season is None:
            unresolved.append(membership.pk)
            continue
        membership.season_id = season.pk
        membership.save(update_fields=["season"])
        consolidated += 1
        logger.info(
            "[membership_season_notnull] Membership pk=%s season NULL -> pk=%s (%s)",
            membership.pk, season.pk, season.label,
        )

    if unresolved:
        raise RuntimeError(
            "[membership_season_notnull] %d Membership with season=NULL not "
            "derivable (pks=%s): resolve manually before flipping NOT NULL"
            % (len(unresolved), unresolved)
        )
    logger.info(
        "[membership_season_notnull] consolidated=%s, no NULL left", consolidated
    )


class Migration(migrations.Migration):

    dependencies = [
        ("management", "0014_remove_membership_dates"),
        # La derivazione legge core.Season e League.season_fk: serve il backfill
        # core gia' applicato.
        ("core", "0014_backfill_league_season_fk"),
    ]

    operations = [
        migrations.RunPython(consolidate_null_seasons, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="membership",
            name="season",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="memberships",
                to="core.season",
            ),
        ),
    ]
