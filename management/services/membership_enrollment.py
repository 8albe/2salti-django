"""
Service condiviso per l'enrollment di membership.

Centralizza la logica di:
- redenzione di un ActivationCode (riscatto codice → Membership)
- richiesta manuale di accesso a una squadra (MembershipRequest)

Usato sia dal flusso di onboarding (`accounts.views`) sia dal flusso
post-onboarding "team_access" (`management.views`).
"""
from django.db import transaction
from django.utils import timezone

from core.models import Team
from management.models import ActivationCode, Membership, MembershipRequest
from management.services.membership_season import resolve_membership_season
from management.utils import log_action


def _resolve_role(user) -> str:
    """Mappa user.role → ruolo Membership. Default PLAYER."""
    if getattr(user, 'role', None) == 'coach':
        return 'HEAD_COACH'
    return 'PLAYER'


def _sync_profile_denorm(user, role, team, society):
    """
    Aggiorna il campo denormalizzato sul profilo (current_team / managed_society)
    coerente con la Membership appena creata.

    Usa .update() per bypassare i signal post_save del profilo: evitiamo di
    rievocare sync_*_membership che ri-eseguirebbe chiusure/aperture inutili
    sulla Membership appena creata. La Membership è la fonte di verità.
    """
    from accounts.models import AthleteProfile, CoachProfile, PresidentProfile

    if role == 'PLAYER':
        AthleteProfile.objects.filter(user=user).update(current_team=team)
    elif role in ('HEAD_COACH', 'ASSISTANT_COACH'):
        CoachProfile.objects.filter(user=user).update(current_team=team)
    elif role == 'PRESIDENT':
        PresidentProfile.objects.filter(user=user).update(managed_society=society)


def redeem_activation_code(user, code_string, request=None):
    """
    Riscatta un ActivationCode per l'utente.

    Returns:
        (success: bool, membership: Membership|None, error: str|None)
    """
    if not code_string:
        return False, None, "Codice mancante."

    try:
        code_obj = ActivationCode.objects.get(code=code_string, is_active=True)
    except ActivationCode.DoesNotExist:
        return False, None, "Codice non valido."

    if code_obj.expires_at and code_obj.expires_at < timezone.now():
        return False, None, "Codice scaduto."

    if code_obj.current_uses >= code_obj.max_uses:
        return False, None, "Codice esaurito."

    role = _resolve_role(user)

    # Dal flip NOT NULL (2d-7): senza stagione derivabile il tesseramento non
    # puo' nascere — errore pulito all'utente invece di IntegrityError.
    season = resolve_membership_season(
        user, code_obj.society, code_obj.team, role)
    if season is None:
        return False, None, (
            "Stagione corrente non configurata per questo sport: "
            "contatta l'amministratore."
        )

    with transaction.atomic():
        # DEBT-004: lock della riga ActivationCode per serializzare riscatti
        # concorrenti — la verifica esaurimento + l'incremento di current_uses
        # devono essere atomici (altrimenti lost-update / over-redemption oltre
        # max_uses). Su SQLite è un no-op (write serializzati a livello DB),
        # difensivo per PostgreSQL in produzione.
        code_obj = ActivationCode.objects.select_for_update().get(pk=code_obj.pk)
        if code_obj.current_uses >= code_obj.max_uses:
            return False, None, "Codice esaurito."

        membership, created = Membership.objects.get_or_create(
            user=user, society=code_obj.society, team=code_obj.team,
            role=role, season=season,
        )
        if created:
            code_obj.current_uses += 1
            code_obj.save(update_fields=['current_uses'])

        _sync_profile_denorm(user, role, code_obj.team, code_obj.society)

        log_action(
            user,
            code_obj.society,
            "MEMBERSHIP_CODE_REDEEMED",
            target=code_obj,
            details={
                'code': code_obj.code,
                'team_id': code_obj.team_id,
                'role': role,
                'created': created,
            },
            request=request,
        )

    return True, membership, None


def request_manual_membership(user, team_id, request=None):
    """
    Crea (idempotente) una MembershipRequest per la squadra indicata.

    Returns:
        (success: bool, request: MembershipRequest|None, error: str|None)
    """
    try:
        team = Team.objects.select_related('society').get(id=team_id)
    except Team.DoesNotExist:
        return False, None, "Squadra non trovata."

    role = _resolve_role(user)

    with transaction.atomic():
        membership_request, created = MembershipRequest.objects.get_or_create(
            user=user,
            society=team.society,
            team=team,
            role=role,
            defaults={'status': 'PENDING'},
        )

        log_action(
            user,
            team.society,
            "MEMBERSHIP_REQUESTED",
            target=team,
            details={
                'team_id': team.id,
                'role': role,
                'created': created,
                'status': membership_request.status,
            },
            request=request,
        )

    return True, membership_request, None
