"""Entitlement service — unico seam per cambiare gli entitlement premium.

Tutte le mutazioni di ``User.plan`` e ``Society.tier`` / ``Society.is_comped``
passano da qui: così l'audit log è garantito e il webhook di pagamento futuro
si aggancia in un punto solo (oggi lo chiamano l'admin e — per il solo lato
società/pilota — i seed). Ortogonale all'RBAC (``management/permissions.py``):
non lo tocca.

Ogni funzione è idempotente (no-op silenzioso se il valore non cambia) e, quando
cambia, scrive una riga ``AuditLog`` con ``details={'from', 'to', 'source'}``.
``source`` identifica il chiamante (es. ``'admin'``, ``'mock_payment'``,
``'seed_zero9'``, domani ``'stripe_webhook'``).
"""
from accounts.models import User
from core.models import Society  # noqa: F401 — documenta il dominio del seam
from management.utils import log_action


def grant_premium(user, *, source, actor=None, request=None):
    """Porta l'utente a PREMIUM. Idempotente. Logga ENTITLEMENT_PLAN_GRANTED."""
    old = user.plan
    if old == User.Plan.PREMIUM:
        return
    user.plan = User.Plan.PREMIUM
    user.save(update_fields=['plan'])
    log_action(
        actor or user, None, 'ENTITLEMENT_PLAN_GRANTED', target=user,
        details={'from': old, 'to': user.plan, 'source': source}, request=request,
    )


def revoke_premium(user, *, source, actor=None, request=None):
    """Riporta l'utente a FREEMIUM. Idempotente. Logga ENTITLEMENT_PLAN_REVOKED."""
    old = user.plan
    if old == User.Plan.FREEMIUM:
        return
    user.plan = User.Plan.FREEMIUM
    user.save(update_fields=['plan'])
    log_action(
        actor or user, None, 'ENTITLEMENT_PLAN_REVOKED', target=user,
        details={'from': old, 'to': user.plan, 'source': source}, request=request,
    )


def set_society_tier(society, tier, *, source, actor=None, request=None):
    """Imposta il tier società. Idempotente. Logga ENTITLEMENT_SOCIETY_TIER_CHANGED."""
    old = society.tier
    if old == tier:
        return
    society.tier = tier
    society.save(update_fields=['tier'])
    log_action(
        actor, society, 'ENTITLEMENT_SOCIETY_TIER_CHANGED', target=society,
        details={'from': old, 'to': tier, 'source': source}, request=request,
    )


def set_society_comped(society, comped, *, source, actor=None, request=None):
    """Imposta il flag comped. Idempotente. Logga ENTITLEMENT_SOCIETY_COMPED_CHANGED."""
    old = society.is_comped
    if old == comped:
        return
    society.is_comped = comped
    society.save(update_fields=['is_comped'])
    log_action(
        actor, society, 'ENTITLEMENT_SOCIETY_COMPED_CHANGED', target=society,
        details={'from': old, 'to': comped, 'source': source}, request=request,
    )
