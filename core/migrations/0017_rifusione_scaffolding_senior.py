# Macro 16 Fase 3 (decisione prodotto D4-A, 2026-06-11): rifusione dello
# scaffolding leghe pre-lancio.
#
# La lega "Senior" non e' una lega reale: e' un'etichetta-ombrello messa a mano
# per raggruppare i campionati dei grandi, e non mappa su NESSUN valore della
# lista chiusa dei tipi (per questo core/0016 la lascia league_type=NULL).
# Poiche' i dati sono scaffolding di test (sito non live), si RIFONDE invece di
# trascinarsela dietro: la lega viene convertita in place in "serie C Maschile"
# (tipo C), cosi' il set d'esempio copre due tipi dei grandi (B con due gironi,
# C) e due giovanili (U16, U18) — rappresentativo del modello reale.
#
# Conversione IN PLACE (stesso pk): team, standings, match e Membership restano
# agganciati senza riscritture FK. Lo slug viene rigenerato (deroga alla regola
# "gli slug esistenti non si rigenerano" di Fase 0: dati finti, nessun URL
# reale da preservare). Selezione per PATTERN DI NOME (mai pk): name iexact
# "senior" e league_type NULL. Idempotente: al secondo giro il filtro non
# trova nulla. Reverse: noop documentato — ripristino da backup.
import logging

from django.db import migrations
from django.utils.text import slugify

logger = logging.getLogger(__name__)

NEW_NAME = "serie C Maschile"
NEW_TYPE = "C"


def rifusione_scaffolding_senior(apps, schema_editor):
    League = apps.get_model("core", "League")

    umbrellas = League.objects.filter(name__iexact="senior", league_type__isnull=True)
    if not umbrellas.exists():
        logger.info(
            "[rifusione_scaffolding_senior] nessuna lega-ombrello 'Senior' "
            "da rifondere: no-op"
        )
        return

    for league in umbrellas:
        old_name, old_slug = league.name, league.slug
        season_slug = (league.season or "").replace("/", "-")
        new_slug = slugify(f"{NEW_NAME}-{season_slug}-{league.group_name}")
        if League.objects.exclude(pk=league.pk).filter(slug=new_slug).exists():
            raise RuntimeError(
                "[rifusione_scaffolding_senior] slug collision for League "
                "pk=%s: %r already exists — resolve manually" % (league.pk, new_slug)
            )
        league.name = NEW_NAME
        league.league_type = NEW_TYPE
        league.slug = new_slug
        league.save(update_fields=["name", "league_type", "slug"])
        logger.info(
            "[rifusione_scaffolding_senior] League pk=%s %r (slug=%r) -> %r "
            "(league_type=%s, slug=%r); team agganciati=%s, standing=%s, "
            "membership (via team)=%s",
            league.pk, old_name, old_slug, NEW_NAME, NEW_TYPE, new_slug,
            league.teams.count(),
            league.persisted_standings.count() if hasattr(league, "persisted_standings") else "n/d",
            sum(t.memberships.count() for t in league.teams.all()),
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_classify_league_type"),
        # I conteggi di log leggono Membership via team (related_name).
        ("management", "0015_membership_season_notnull"),
    ]

    operations = [
        migrations.RunPython(
            rifusione_scaffolding_senior, migrations.RunPython.noop
        ),
    ]
