import re

from django.db import migrations

# Stagioni in formato dash AAAA-AAAA (incluso il typo, es. 2025-5026).
_DASH_RE = re.compile(r"^(\d{4})-(\d{4})$")
# Stagione "residua test" mal-datata: leghe orfane vanno cancellate, leghe con
# team/standing collegati sono in realta' la stagione corrente mal-datata.
_RESIDUO = ("2024", "2025")
_CURRENT = "2025/2026"


def _target_season(value):
    """Valore canonico AAAA/AAAA a partire da un dash. None se non dash."""
    match = _DASH_RE.match(value or "")
    if not match:
        return None
    year1 = match.group(1)
    if (match.group(1), match.group(2)) == _RESIDUO:
        # Lega corrente mal-datata: si forza alla stagione corrente (decisione C).
        return _CURRENT
    # Formato puro (2025-2026) e typo (2025-5026) -> primo anno / primo+1.
    return f"{year1}/{int(year1) + 1}"


def bonifica(apps, schema_editor):
    League = apps.get_model("core", "League")
    LeagueStanding = apps.get_model("core", "LeagueStanding")
    Team = apps.get_model("core", "Team")

    # --- Pre-check collisioni League (name, season, group_name) ---------------
    planned = {}  # pk -> new_season ('' = delete)
    for lg in League.objects.all():
        match = _DASH_RE.match(lg.season or "")
        if not match:
            continue  # gia' canonico o malformato: non si tocca
        is_residuo = (match.group(1), match.group(2)) == _RESIDUO
        has_links = (
            Team.objects.filter(league_id=lg.id).exists()
            or LeagueStanding.objects.filter(league_id=lg.id).exists()
        )
        if is_residuo and not has_links:
            planned[lg.id] = ""  # DELETE orfana
        else:
            planned[lg.id] = _target_season(lg.season)

    survivors = {}  # (name, season, group_name) -> pk
    for lg in League.objects.all():
        if lg.id in planned and planned[lg.id] == "":
            continue
        season = planned.get(lg.id, lg.season)
        key = (lg.name, season, lg.group_name)
        if key in survivors:
            raise RuntimeError(
                f"COLLISIONE League unique_together {key}: "
                f"pk={survivors[key]} e pk={lg.id}. Bonifica interrotta."
            )
        survivors[key] = lg.id

    # --- Pre-check collisioni LeagueStanding (league, team, season) -----------
    ls_seen = {}
    for ls in LeagueStanding.objects.all():
        new = _target_season(ls.season)
        season = new if new is not None else ls.season
        # Se appartiene a una lega convertita, segue il valore della lega.
        if ls.league_id in planned and planned[ls.league_id] not in ("", None):
            season = planned[ls.league_id]
        key = (ls.league_id, ls.team_id, season)
        if key in ls_seen:
            raise RuntimeError(
                f"COLLISIONE LeagueStanding unique_together {key}: "
                f"pk={ls_seen[key]} e pk={ls.id}. Bonifica interrotta."
            )
        ls_seen[key] = ls.id

    # --- Esecuzione -----------------------------------------------------------
    for lg in League.objects.all():
        action = planned.get(lg.id)
        if action is None:
            continue
        if action == "":
            print(f"[bonifica_season] DELETE League pk={lg.id} season={lg.season!r} (residuo orfano)")
            lg.delete()
            continue
        old = lg.season
        # Lockstep: standing della lega allineati allo stesso valore.
        stds = list(LeagueStanding.objects.filter(league_id=lg.id))
        for ls in stds:
            if ls.season != action:
                print(f"[bonifica_season] LeagueStanding pk={ls.id} season {ls.season!r}->{action!r} (lockstep league pk={lg.id})")
                ls.season = action
                ls.save(update_fields=["season"])
        lg.season = action
        lg.save(update_fields=["season"])
        print(f"[bonifica_season] League pk={lg.id} season {old!r}->{action!r}")

    # --- Sweep difensiva: standing dash rimasti (lega gia' canonica/assente) --
    for ls in LeagueStanding.objects.all():
        new = _target_season(ls.season)
        if new is not None:
            print(f"[bonifica_season] LeagueStanding pk={ls.id} season {ls.season!r}->{new!r} (sweep)")
            ls.season = new
            ls.save(update_fields=["season"])


def reverse(apps, schema_editor):
    # Non reversibile in modo fedele: la conversione e' lossy
    # (2025-2026 e 2025-5026 collassano entrambi su 2025/2026; le DELETE sono
    # irreversibili). Ripristinare dal backup db.sqlite3.bak.* se necessario.
    raise RuntimeError(
        "Migration di bonifica non reversibile: ripristinare dal backup DB."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_alter_league_options_alter_sport_options_and_more"),
    ]

    operations = [
        migrations.RunPython(bonifica, reverse),
    ]
