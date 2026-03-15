from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import PresidentProfile, AthleteProfile, CoachProfile
from .models import Membership

@receiver(post_save, sender=PresidentProfile)
def sync_president_membership(sender, instance, **kwargs):
    if instance.managed_society:
        Membership.objects.update_or_create(
            user=instance.user,
            society=instance.managed_society,
            team=None,
            role='PRESIDENT',
            defaults={'is_active': True}
        )

@receiver(post_save, sender=AthleteProfile)
def sync_athlete_membership(sender, instance, **kwargs):
    if instance.current_team:
        Membership.objects.update_or_create(
            user=instance.user,
            society=instance.current_team.society,
            team=instance.current_team,
            role='PLAYER',
            defaults={'is_active': True}
        )

@receiver(post_save, sender=CoachProfile)
def sync_coach_membership(sender, instance, **kwargs):
    if instance.current_team:
        # Per ora defaultiamo a HEAD_COACH se viene dal profilo legacy
        Membership.objects.update_or_create(
            user=instance.user,
            society=instance.current_team.society,
            team=instance.current_team,
            role='HEAD_COACH',
            defaults={'is_active': True}
        )
