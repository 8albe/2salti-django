"""
Derivazione runtime della stagione (`core.Season`) per una Membership in
creazione.

Macro 16 Fase 2 (fetta 2d-1): i 3 creation-site di Membership devono nascere
season-aware mentre la FK e' ancora nullable, cosi' da non generare piu' record
`season=NULL` in attesa del flip NOT NULL (gradino 2d-7).

La logica replica *esattamente* quella della data-migration di backfill
`management/0011_backfill_membership_season._derive_season`:
  1) primaria, deterministica: team -> team.league -> league.season_fk
  2) fallback: unica Season is_current per lo sport del contesto (society.sport)
  3) ramo difensivo: nulla derivabile -> None + warning (nessun crash)

NON si importa dalla migration congelata (usa modelli storici via `apps`):
qui si lavora coi modelli reali. La logica e' duplicata di proposito.
"""
import logging

from core.models import Season

logger = logging.getLogger(__name__)


def resolve_membership_season(user, society, team, role):
    """Stagione da assegnare a una nuova Membership, o None se non derivabile.

    Args:
        user: l'utente della membership (non usato nella derivazione attuale,
            accettato per simmetria con la chiave della Membership e per
            estensioni future).
        society: la Society del contesto (obbligatoria; fonte dello sport per
            il fallback).
        team: la Team, oppure None (PRESIDENT, codice/richiesta senza team) ->
            si salta la derivazione primaria e si va diretti al fallback.
        role: il ruolo (non usato nella derivazione attuale; accettato per
            simmetria con la chiave della Membership).

    Returns:
        Una istanza `core.Season`, oppure None (ramo difensivo, loggato).
    """
    # 1) Derivazione primaria: team -> league -> league.season_fk.
    if team is not None and team.league_id is not None:
        league = team.league
        if league.season_fk_id is not None:
            return league.season_fk

    # 2) Fallback: unica Season corrente per lo sport del contesto. Si esige
    # unicita' (il constraint unique_current_season_per_sport la garantisce, ma
    # il filtro difensivo evita assunzioni se il dato fosse incoerente).
    sport_id = society.sport_id
    current = list(Season.objects.filter(is_current=True, sport_id=sport_id)[:2])
    if len(current) == 1:
        return current[0]

    # 3) Ramo difensivo: stagione non derivabile -> None + warning.
    logger.warning(
        "[resolve_membership_season] stagione non derivabile per membership in "
        "creazione (user=%s society=%s team=%s role=%s): team/lega/season_fk "
        "assenti e fallback is_current non univoco -> season=None",
        getattr(user, "pk", user), getattr(society, "pk", society),
        getattr(team, "pk", team), role,
    )
    return None
