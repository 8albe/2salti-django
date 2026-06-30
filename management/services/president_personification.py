"""Macro 18 — Personificazione società da parte del presidente.

Il presidente NON crea una società da zero: sceglie una società esistente (che
deriva dal caricamento campionati/partite), richiede l'accesso, e un admin
(staff) approva. All'approvazione il presidente viene agganciato alla società
via `PresidentProfile.managed_society` — NESSUNA Membership PRESIDENT viene
creata (coerente con `create_society` e con la bacheca del "presidente
de-vincolato", vedi management/tests_bacheca.py).

Macchina di autorizzazione riusata: `MembershipRequest` con `role='PRESIDENT'`
come discriminatore (no schema-change). Il ramo PRESIDENT è isolato dal
consumer president-gated (`club_admin_dashboard`/`approve_membership`): solo
l'admin può approvarlo, via op_admin_site.

Email: notifica best-effort FUORI dal blocco atomico (pattern certificazione).
Un invio fallito viene loggato ma non rompe la transizione di stato.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from core.models import Society
from management.models import MembershipRequest

logger = logging.getLogger(__name__)


def societies_for_personification():
    """Società personificabili: quelle con almeno una squadra, in qualsiasi
    stagione (#4 / Caso B: anche società di stagioni future, NON filtrare per
    is_current). `.distinct()` perché il join su teams duplica le righe."""
    return (
        Society.objects
        .filter(teams__isnull=False)
        .distinct()
        .order_by('name')
    )


def request_president_personification(user, society):
    """Crea (idempotente) una richiesta di personificazione PRESIDENT.

    Guard: se l'utente gestisce già una società o ha già una richiesta PENDING,
    non si duplica nulla — si ritorna lo stato corrente.

    Returns:
        (success: bool, request: MembershipRequest|None, error: str|None)
    """
    profile = getattr(user, 'president_profile', None)
    if profile is not None and profile.managed_society_id is not None:
        return False, None, "Gestisci già una società."

    existing = (
        MembershipRequest.objects
        .filter(user=user, role='PRESIDENT', status='PENDING')
        .first()
    )
    if existing is not None:
        # Richiesta già in attesa: non duplicare, mostra lo stato.
        return True, existing, None

    req, _created = MembershipRequest.objects.get_or_create(
        user=user,
        society=society,
        role='PRESIDENT',
        defaults={'status': 'PENDING'},
    )
    # Se una richiesta REJECTED/APPROVED esisteva su questa società la riapriamo
    # a PENDING solo se non è già attiva: get_or_create non riapre da solo.
    if req.status not in ('PENDING',):
        req.status = 'PENDING'
        req.save(update_fields=['status'])
    logger.info(
        "[personification] richiesta PRESIDENT pk=%s user=%s society=%s -> PENDING",
        req.pk, user.pk, society.pk,
    )
    return True, req, None


def approve_president_request(req):
    """Approva (admin-gated) una richiesta di personificazione PRESIDENT.

    Dentro `transaction.atomic()`:
      1. lock della richiesta (serializza approvazioni concorrenti);
      2. guard 1:1 applicativo: se la società ha già un presidente -> reject
         pulito (NIENTE IntegrityError grezzo sul OneToOne);
      3. set `managed_society` sul profilo del richiedente (NESSUNA Membership);
      4. status -> APPROVED.

    La notifica email al presidente è best-effort e resta FUORI dall'atomic.

    Returns:
        (success: bool, error: str|None)
    """
    from accounts.models import PresidentProfile

    with transaction.atomic():
        locked = (
            MembershipRequest.objects
            .select_for_update()
            .select_related('society', 'user')
            .get(pk=req.pk)
        )
        if locked.role != 'PRESIDENT':
            return False, "La richiesta non è una personificazione presidente."
        if locked.status != 'PENDING':
            return False, "La richiesta non è in attesa."

        # Guard 1:1 (4c): `managed_society` è OneToOne. Senza questo controllo,
        # agganciare un secondo presidente alla stessa società solleverebbe un
        # IntegrityError grezzo. Lo sostituiamo con un reject leggibile. Il check
        # è sul lato proprietario del OneToOne (PresidentProfile.managed_society):
        # il reverse `Society.president` non espone un attributo `_id`.
        already_managed = (
            PresidentProfile.objects
            .filter(managed_society=locked.society)
            .exists()
        )
        if already_managed:
            return False, "Questa società ha già un presidente assegnato."

        # Side-effect: solo managed_society, nessuna Membership PRESIDENT (#2).
        PresidentProfile.objects.filter(user=locked.user).update(
            managed_society=locked.society,
        )
        locked.status = 'APPROVED'
        locked.save(update_fields=['status', 'updated_at'])

    logger.info(
        "[personification] richiesta pk=%s APPROVED -> managed_society=%s (user=%s)",
        locked.pk, locked.society_id, locked.user_id,
    )
    _notify_president_approved(locked)
    return True, None


def _notify_president_approved(req):
    """Notifica best-effort al presidente dell'avvenuta approvazione. Un
    fallimento (SMTP, indirizzo vuoto) viene loggato ma non propagato: la
    notifica è side effect non critico e non deve rompere l'approvazione."""
    recipient = getattr(req.user, 'email', None)
    if not recipient:
        logger.warning(
            "[personification] nessuna email per user=%s (req pk=%s): "
            "approvazione registrata ma non notificata",
            req.user_id, req.pk,
        )
        return False
    try:
        send_mail(
            subject=f"[2salti] Sei ora presidente di {req.society.name}",
            message=(
                f"La tua richiesta di gestione della società {req.society.name} "
                f"è stata approvata.\n\n"
                f"Accedi a 2salti per completare il setup della società.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.warning(
            "[personification] invio email approvazione fallito (req pk=%s)",
            req.pk, exc_info=True,
        )
        return False
