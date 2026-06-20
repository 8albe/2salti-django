"""Orchestrazione della certificazione genitore (Macro 7b, BLUEPRINT §7.7).

Coordina invio email + transizioni di stato di ParentCertification. Le
transizioni vivono come metodi sul modello (validano lo stato di partenza); qui
si aggiungono i side effect (email) e le regole di dominio (chi è il figlio,
quale società, deduplica richieste aperte).

Email: usa il backend Django configurato (in dev tipicamente console/file). Non
configura SMTP. Nessuna PII nei log: si loggano solo pk e stato.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse

from accounts.models import User
from management.models import ParentCertification

logger = logging.getLogger(__name__)


def _society_recipients(society):
    """Indirizzi a cui notificare la società. Preferisce society.email; in
    fallback l'email del presidente. Lista vuota se nessuno è disponibile."""
    if society.email:
        return [society.email]
    president = getattr(society, 'president', None)
    if president and president.user and president.user.email:
        return [president.user.email]
    return []


def _safe_send(*, subject, message, recipient_list, log_ref):
    """Invio email best-effort. Un fallimento (SMTP irraggiungibile, indirizzo
    vuoto) viene loggato ma NON propagato: la notifica è un side effect non
    critico e non deve rompere la transizione di stato né produrre un 500.

    Si usa try/except mirato invece di fail_silently=True per lasciare una
    traccia ops (warning) del mancato invio — coerente col fallback già usato
    quando non esistono destinatari. Niente PII nei log: solo il riferimento
    tecnico (cert pk). Ritorna True se l'email è partita, False altrimenti.
    """
    if not recipient_list:
        return False
    try:
        send_mail(
            subject, message, settings.DEFAULT_FROM_EMAIL,
            recipient_list, fail_silently=False,
        )
        return True
    except Exception:
        logger.warning(
            "[certification] invio email fallito (%s): notifica non recapitata",
            log_ref, exc_info=True,
        )
        return False


def _resolve_society_for_child(child):
    """Società destinataria = quella in cui il figlio è tesserato come PLAYER
    nella stagione corrente. None se non esiste un tesseramento attivo valido."""
    from management.models import Membership

    membership = (
        Membership.objects
        .filter(user=child, role='PLAYER', is_active=True, season__is_current=True)
        .select_related('society')
        .first()
    )
    return membership.society if membership else None


def request_certification(parent, child):
    """Il genitore dichiara il figlio. Crea la ParentCertification, invia la
    mail di vouching alla società e porta lo stato a IN_ATTESA_SOCIETA.

    Returns: (ok: bool, cert: ParentCertification | None, error: str | None).
    """
    if child is None or child.role != 'athlete':
        return False, None, "Puoi richiedere la certificazione solo per un atleta presente nel sistema."

    if child == parent:
        return False, None, "Non puoi certificarti come genitore di te stesso."

    # Deduplica: una richiesta aperta (non finale) per la stessa coppia basta.
    existing = ParentCertification.objects.filter(parent=parent, child=child).exclude(
        status__in=ParentCertification.FINAL_STATUSES).first()
    if existing:
        return False, existing, "Esiste già una richiesta di certificazione in corso per questo atleta."

    society = _resolve_society_for_child(child)
    if society is None:
        return False, None, (
            "L'atleta non risulta tesserato in alcuna società per la stagione "
            "corrente: impossibile inoltrare la richiesta."
        )

    # Creazione + transizione RICHIESTA_INVIATA -> IN_ATTESA_SOCIETA atomiche
    # (disciplina DEBT-004). L'email di vouching alla società è side effect non
    # critico e va FUORI dal blocco: un SMTP irraggiungibile non deve lasciare
    # la cert appena creata bloccata a RICHIESTA_INVIATA né produrre un 500.
    with transaction.atomic():
        cert = ParentCertification.objects.create(
            parent=parent, child=child, society=society,
            status=ParentCertification.Status.RICHIESTA_INVIATA,
        )
        cert.mark_in_attesa_societa()

    recipients = _society_recipients(society)
    if recipients:
        parent_name = parent.get_full_name() or parent.username
        child_name = child.get_full_name() or child.username
        _safe_send(
            subject=f"[2salti] Richiesta certificazione genitore — {society.name}",
            message=(
                f"La società {society.name} ha ricevuto una richiesta di "
                f"certificazione genitore.\n\n"
                f"Genitore dichiarante: {parent_name} ({parent.email or 'email non indicata'})\n"
                f"Atleta dichiarato: {child_name}\n\n"
                f"Verifica nome ed email del genitore sul tuo gestionale. Se "
                f"corrispondono, conferma la richiesta dal pannello società; "
                f"in caso contrario, rifiutala.\n"
            ),
            recipient_list=recipients,
            log_ref=f"cert pk={cert.pk} request-vouching",
        )
    else:
        logger.warning(
            "[certification] nessun destinatario email per society pk=%s "
            "(cert pk=%s): richiesta registrata ma non notificata",
            society.pk, cert.pk,
        )

    logger.info("[certification] cert pk=%s -> IN_ATTESA_SOCIETA", cert.pk)
    return True, cert, None


def confirm_certification(cert, request=None):
    """La società conferma il match: genera token, invia al genitore la mail con
    il link e porta lo stato a IN_ATTESA_CLICK_GENITORE.

    Returns: (ok, cert, error).
    """
    # Transizione atomica IN_ATTESA_SOCIETA -> IN_ATTESA_CLICK_GENITORE
    # (CONFERMATA_SOCIETA è uno stato intermedio transiente). Disciplina
    # DEBT-004: nessun save parziale fuori dal blocco. Su re-submit (stato non
    # più IN_ATTESA_SOCIETA) conferma_societa() alza ValueError: lo catturiamo e
    # restituiamo l'errore senza propagare né lasciare stato a metà.
    try:
        with transaction.atomic():
            cert.conferma_societa()
            cert.mark_in_attesa_click()
    except ValueError as exc:
        return False, cert, str(exc)

    # Email NON critica e FUORI dalla transizione: un SMTP irraggiungibile non
    # deve annullare la conferma né produrre un 500 (era la causa del bug).
    link_path = reverse('certify_parent', args=[cert.token])
    link = request.build_absolute_uri(link_path) if request is not None else link_path

    if cert.parent.email:
        child_name = cert.child.get_full_name() or cert.child.username
        _safe_send(
            subject="[2salti] Conferma la tua certificazione genitore",
            message=(
                f"La società {cert.society.name} ha confermato la tua richiesta "
                f"di certificazione come genitore di {child_name}.\n\n"
                f"Per attivare l'accesso ai dati e ai servizi di tuo figlio, "
                f"clicca sul link entro {cert_validity_days()} giorni:\n\n{link}\n\n"
                f"Se non hai richiesto tu questa certificazione, ignora questa email.\n"
            ),
            recipient_list=[cert.parent.email],
            log_ref=f"cert pk={cert.pk} confirm-link",
        )
    else:
        logger.warning(
            "[certification] parent pk=%s senza email (cert pk=%s): link non inviato",
            cert.parent_id, cert.pk,
        )

    logger.info("[certification] cert pk=%s -> IN_ATTESA_CLICK_GENITORE", cert.pk)
    return True, cert, None


def reject_certification(cert):
    """La società nega il match. Stato → RIFIUTATA, notifica il genitore."""
    # Transizione atomica; email best-effort fuori dal blocco. Un SMTP
    # irraggiungibile non deve trasformare il rifiuto in un 500 (era il bug):
    # lo stato passa comunque a RIFIUTATA e la notifica mancata viene loggata.
    try:
        with transaction.atomic():
            cert.rifiuta_societa()
    except ValueError as exc:
        return False, cert, str(exc)

    if cert.parent.email:
        child_name = cert.child.get_full_name() or cert.child.username
        _safe_send(
            subject="[2salti] Esito richiesta certificazione genitore",
            message=(
                f"La società {cert.society.name} non ha potuto confermare la tua "
                f"richiesta di certificazione come genitore di {child_name}. "
                f"L'accesso ai dati non è stato attivato. Per riprovare, invia una "
                f"nuova richiesta dopo aver verificato i dati con la società.\n"
            ),
            recipient_list=[cert.parent.email],
            log_ref=f"cert pk={cert.pk} reject-notice",
        )
    logger.info("[certification] cert pk=%s -> RIFIUTATA", cert.pk)
    return True, cert, None


def certify_by_token(token):
    """Click del genitore sul link. Se valido → CERTIFICATA; se la finestra è
    scaduta → SCADUTA. Stati non attesi → errore.

    Returns: (ok, cert | None, error).
    """
    cert = ParentCertification.objects.filter(token=token).first()
    if cert is None or not token:
        return False, None, "Link di certificazione non valido."

    if cert.status != ParentCertification.Status.IN_ATTESA_CLICK_GENITORE:
        if cert.status == ParentCertification.Status.CERTIFICATA:
            return True, cert, None  # già certificata: idempotente
        return False, cert, "Questo link non è più utilizzabile."

    if cert.is_link_expired:
        cert.scadi()
        logger.info("[certification] cert pk=%s -> SCADUTA (link scaduto)", cert.pk)
        return False, cert, "Il link è scaduto. Richiedi una nuova certificazione."

    cert.certifica_via_click()
    logger.info("[certification] cert pk=%s -> CERTIFICATA", cert.pk)
    return True, cert, None


def cert_validity_days():
    from management.models import CERTIFICATION_LINK_VALIDITY_DAYS
    return CERTIFICATION_LINK_VALIDITY_DAYS
