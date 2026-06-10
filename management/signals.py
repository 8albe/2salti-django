from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from accounts.models import PresidentProfile, AthleteProfile, CoachProfile
from .models import Membership
from .services.membership_season import resolve_membership_season


def _close_other_team_memberships(user, role, new_team):
    """
    Chiude le Membership attive di (user, role) con team diverso da new_team,
    indipendentemente dalla società (cross-society cleanup).

    Una Membership è considerata attiva se is_active=True (2d-5: predicato
    disaccoppiato dalle date). Chiusura: end_date = oggi (TZ locale),
    is_active = False.

    La Membership con team = new_team (se esiste) viene preservata.

    Nota: per il ruolo PRESIDENT (team sempre None) usare la logica scopata
    a society direttamente nel receiver — non chiamare questa helper.
    """
    today = timezone.localdate()
    Membership.objects.filter(
        user=user,
        role=role,
        is_active=True,
    ).exclude(team=new_team).update(end_date=today, is_active=False)


def _close_stale_president_memberships(user, society):
    """
    Chiude le Membership PRESIDENT attive dell'utente in società diverse
    da quella nuova. PRESIDENT ha sempre team=None, quindi la chiusura
    è scopata per (society != new_society).
    """
    today = timezone.localdate()
    Membership.objects.filter(
        user=user,
        role='PRESIDENT',
        is_active=True,
    ).exclude(society=society).update(end_date=today, is_active=False)


def _close_all_role_memberships(user, role):
    """
    Chiude tutte le Membership attive (is_active=True) di (user, role)
    su qualunque society. Usato quando il profilo perde l'appartenenza
    (current_team / managed_society = None).
    """
    today = timezone.localdate()
    Membership.objects.filter(
        user=user, role=role, is_active=True,
    ).update(end_date=today, is_active=False)


def _open_or_reopen_membership(user, society, team, role):
    """
    Apre (o riapre) la Membership target.
    - Se non esiste: crea con start_date=oggi, end_date=None, is_active=True.
    - Se esiste ed è già attiva (is_active=True): no-op (preserva start_date
      originale, evita reset su save innocuo del profilo). 2d-5: la decisione
      dipende solo da is_active, non più dalle date.
    - Se esiste ma è inattiva (is_active=False): riapri (start_date=oggi,
      end_date=None, is_active=True).
    """
    today = timezone.localdate()
    # Fetta 2d-4b: lookup season-aware. season entra nella chiave del
    # get_or_create solo se derivabile; se resolve ritorna None (ramo
    # difensivo) resta fuori dal lookup — la chiave ricade su 4-field (2d-1) e
    # non si creano duplicati-NULL spuri (il UniqueConstraint 5-field non
    # vincola i NULL, nulls_distinct). season resta anche nei defaults per il
    # caso created=True.
    season = resolve_membership_season(user, society, team, role)
    lookup = dict(user=user, society=society, team=team, role=role)
    if season is not None:
        lookup['season'] = season
    membership, created = Membership.objects.get_or_create(
        **lookup,
        defaults={
            'is_active': True,
            'start_date': today,
            'end_date': None,
            'season': season,
        },
    )
    if created:
        return membership
    if not membership.is_active:
        membership.start_date = today
        membership.end_date = None
        membership.is_active = True
        membership.save(update_fields=['start_date', 'end_date', 'is_active'])
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


@receiver(post_save, sender=CoachProfile)
def sync_coach_membership(sender, instance, **kwargs):
    if instance.current_team:
        society = instance.current_team.society
        with transaction.atomic():
            _close_other_team_memberships(
                instance.user, 'HEAD_COACH', new_team=instance.current_team,
            )
            _open_or_reopen_membership(
                instance.user, society, instance.current_team, 'HEAD_COACH',
            )
    else:
        _close_all_role_memberships(instance.user, 'HEAD_COACH')
