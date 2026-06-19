from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import PresidentProfile, AthleteProfile, CoachProfile
from .models import Membership
from .services.membership_season import resolve_membership_season


def _close_other_team_memberships(user, role, new_team):
    """
    Chiude le Membership attive di (user, role) con team diverso da new_team,
    indipendentemente dalla società (cross-society cleanup).

    Una Membership è considerata attiva se is_active=True (2d-5: predicato
    disaccoppiato dalle date; Fase 2: le date non esistono più, la chiusura
    è il solo flip is_active=False — la riga storica resta).

    La Membership con team = new_team (se esiste) viene preservata.

    Nota: per il ruolo PRESIDENT (team sempre None) usare la logica scopata
    a society direttamente nel receiver — non chiamare questa helper.
    """
    Membership.objects.filter(
        user=user,
        role=role,
        is_active=True,
    ).exclude(team=new_team).update(is_active=False)


def _close_stale_president_memberships(user, society):
    """
    Chiude le Membership PRESIDENT attive dell'utente in società diverse
    da quella nuova. PRESIDENT ha sempre team=None, quindi la chiusura
    è scopata per (society != new_society).
    """
    Membership.objects.filter(
        user=user,
        role='PRESIDENT',
        is_active=True,
    ).exclude(society=society).update(is_active=False)


def _close_all_role_memberships(user, role):
    """
    Chiude tutte le Membership attive (is_active=True) di (user, role)
    su qualunque society. Usato quando il profilo perde l'appartenenza
    (current_team / managed_society = None).
    """
    Membership.objects.filter(
        user=user, role=role, is_active=True,
    ).update(is_active=False)


def _open_or_reopen_membership(user, society, team, role):
    """
    Apre (o riapre) la Membership target.
    - Se non esiste: crea con is_active=True e season derivata.
    - Se esiste ed è già attiva (is_active=True): no-op (evita scritture su
      save innocuo del profilo). 2d-5: la decisione dipende solo da is_active.
    - Se esiste ma è inattiva (is_active=False): riapri (is_active=True).
    """
    # Lookup season-aware (2d-4b). Dal flip NOT NULL (2d-7) una Membership
    # senza stagione non puo' esistere: se la stagione non e' derivabile
    # (nessuna lega con season_fk e nessuna Season is_current per lo sport)
    # si fallisce subito con un errore esplicito invece di lasciar esplodere
    # il NOT NULL a livello DB — e' una misconfigurazione da sanare in admin.
    season = resolve_membership_season(user, society, team, role)
    if season is None:
        raise RuntimeError(
            "Cannot open membership (user=%s society=%s team=%s role=%s): "
            "no season derivable — configure a current Season for the sport."
            % (user.pk, society.pk, getattr(team, 'pk', None), role)
        )
    membership, created = Membership.objects.get_or_create(
        user=user, society=society, team=team, role=role, season=season,
        defaults={'is_active': True},
    )
    if created:
        return membership
    if not membership.is_active:
        membership.is_active = True
        membership.save(update_fields=['is_active'])
    return membership


@receiver(post_save, sender=PresidentProfile)
def sync_president_membership(sender, instance, **kwargs):
    if instance.managed_society:
        with transaction.atomic():
            _close_stale_president_memberships(
                instance.user, instance.managed_society,
            )
            _open_or_reopen_membership(
                instance.user, instance.managed_society, None, 'PRESIDENT',
            )
    else:
        _close_all_role_memberships(instance.user, 'PRESIDENT')


@receiver(post_save, sender=AthleteProfile)
def sync_athlete_membership(sender, instance, **kwargs):
    if instance.current_team:
        society = instance.current_team.society
        with transaction.atomic():
            _close_other_team_memberships(
                instance.user, 'PLAYER', new_team=instance.current_team,
            )
            _open_or_reopen_membership(
                instance.user, society, instance.current_team, 'PLAYER',
            )
    else:
        _close_all_role_memberships(instance.user, 'PLAYER')


COACH_ROLES = ('HEAD_COACH', 'ASSISTANT_COACH')


@receiver(post_save, sender=CoachProfile)
def sync_coach_membership(sender, instance, **kwargs):
    """Sincronizza la/le Membership coach derivando il ruolo dai dati esistenti.

    DEBT-002: un CoachProfile può corrispondere a più ruoli coach
    (HEAD_COACH e/o ASSISTANT_COACH) sullo stesso utente — non esiste un campo
    di ruolo sul profilo (niente schema-change, niente 2-FK). Il signal è quindi
    *role-differentiated*: deriva i ruoli effettivi dalle Membership coach attive
    e sincronizza CIASCUNO in isolamento (le helper sono già role-scoped), così
    che la chiusura/apertura di un ruolo non azzeri né duplichi l'altro.

    Senza Membership coach pregresse il default è HEAD_COACH: un coach in
    onboarding nasce capo-allenatore (backward-compat con il flusso pre-DEBT-002).
    """
    user = instance.user
    roles = set(
        Membership.objects.filter(
            user=user, role__in=COACH_ROLES, is_active=True,
        ).values_list('role', flat=True)
    ) or {'HEAD_COACH'}

    if instance.current_team:
        society = instance.current_team.society
        with transaction.atomic():
            for role in roles:
                _close_other_team_memberships(
                    user, role, new_team=instance.current_team,
                )
                _open_or_reopen_membership(
                    user, society, instance.current_team, role,
                )
    else:
        with transaction.atomic():
            for role in roles:
                _close_all_role_memberships(user, role)
