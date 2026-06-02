from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from accounts.models import PresidentProfile, AthleteProfile, CoachProfile
from .models import Membership


def _close_other_team_memberships(user, role, new_team):
    """
    Chiude le Membership attive di (user, role) con team diverso da new_team,
    indipendentemente dalla società (cross-society cleanup).

    Una Membership è considerata attiva se end_date IS NULL.
    Chiusura: end_date = oggi (TZ locale), is_active = False.

    La Membership con team = new_team (se esiste) viene preservata.

    Nota: per il ruolo PRESIDENT (team sempre None) usare la logica scopata
    a society direttamente nel receiver — non chiamare questa helper.
    """
    today = timezone.localdate()
    Membership.objects.filter(
        user=user,
        role=role,
        end_date__isnull=True,
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
        end_date__isnull=True,
    ).exclude(society=society).update(end_date=today, is_active=False)


def _close_all_role_memberships(user, role):
    """
    Chiude tutte le Membership attive (end_date IS NULL) di (user, role)
    su qualunque society. Usato quando il profilo perde l'appartenenza
    (current_team / managed_society = None).
    """
    today = timezone.localdate()
    Membership.objects.filter(
        user=user, role=role, end_date__isnull=True,
    ).update(end_date=today, is_active=False)


def _open_or_reopen_membership(user, society, team, role):
    """
    Apre (o riapre) la Membership target.
    - Se non esiste: crea con start_date=oggi, end_date=None, is_active=True.
    - Se esiste ed è già attiva (end_date IS NULL, is_active=True): no-op
      (preserva start_date originale, evita reset su save innocuo del profilo).
    - Se esiste ma è chiusa o inattiva: riapri (start_date=oggi, end_date=None,
      is_active=True).
    """
    today = timezone.localdate()
    membership, created = Membership.objects.get_or_create(
        user=user,
        society=society,
        team=team,
        role=role,
        defaults={
            'is_active': True,
            'start_date': today,
            'end_date': None,
        },
    )
    if created:
        return membership
    if membership.end_date is not None or not membership.is_active or membership.start_date is None:
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
