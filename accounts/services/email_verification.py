"""Verifica identità via email a click (onboarding reale, sostituisce il mock SPID).

Token stateless firmato con django.core.signing — nessuna migration: il link
lega uid+email, così un cambio email invalida automaticamente i vecchi link.
Pattern di invio email calcato su management.services.certification_service
(_safe_send): un fallimento SMTP non deve propagare né bloccare la richiesta.
"""
import logging

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.urls import reverse

logger = logging.getLogger(__name__)

EMAIL_VERIFICATION_SALT = 'accounts.email-verification'
EMAIL_VERIFICATION_MAX_AGE_DAYS = 7
EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS = 60


def make_token(user):
    """Genera il token firmato per il link di verifica di questo utente."""
    return signing.dumps({'uid': user.pk, 'email': user.email}, salt=EMAIL_VERIFICATION_SALT)


def verify_token(token, max_age=None):
    """Valida il token. Ritorna (ok, user | None, error), error in
    {'expired', 'invalid', None}."""
    from accounts.models import User

    max_age_seconds = (
        max_age if max_age is not None else EMAIL_VERIFICATION_MAX_AGE_DAYS * 86400
    )
    try:
        data = signing.loads(token, salt=EMAIL_VERIFICATION_SALT, max_age=max_age_seconds)
    except signing.SignatureExpired:
        return False, None, 'expired'
    except signing.BadSignature:
        return False, None, 'invalid'

    try:
        user = User.objects.get(pk=data['uid'], email=data['email'])
    except (User.DoesNotExist, KeyError):
        return False, None, 'invalid'

    return True, user, None


def _safe_send(*, subject, message, recipient_list, log_ref):
    """Invio email best-effort. Nessuna PII nei log: solo il riferimento tecnico."""
    if not recipient_list:
        return False
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipient_list, fail_silently=False)
        return True
    except Exception:
        logger.warning(
            "[email_verification] invio fallito (%s): notifica non recapitata",
            log_ref, exc_info=True,
        )
        return False


def send_verification_email(user, request=None):
    """Invia (o reinvia) l'email di verifica identità. Best-effort: ritorna
    True se l'email è partita, False altrimenti."""
    if not user.email:
        logger.warning("[email_verification] user pk=%s senza email: link non inviato", user.pk)
        return False

    token = make_token(user)
    link_path = reverse('verify_email', args=[token])
    link = request.build_absolute_uri(link_path) if request is not None else link_path

    return _safe_send(
        subject="[2salti] Conferma il tuo indirizzo email",
        message=(
            f"Ciao {user.get_full_name() or user.username},\n\n"
            f"per completare la registrazione su 2salti conferma il tuo indirizzo "
            f"email cliccando sul link entro {EMAIL_VERIFICATION_MAX_AGE_DAYS} giorni:\n\n"
            f"{link}\n\n"
            f"Se non hai richiesto tu questa registrazione, ignora questa email.\n"
        ),
        recipient_list=[user.email],
        log_ref=f"user pk={user.pk} verify-email",
    )
