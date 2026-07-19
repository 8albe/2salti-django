"""
Emissione, revoca e risoluzione dei link giuria monouso (Macro 14).

Un solo link ACTIVE per match: garantito dal partial unique index sul modello e
rinforzato qui (issue revoca in transazione l'eventuale ACTIVE precedente).
Scadenza valutata a lettura (nessun cron in questo giro): `resolve` degrada a
EXPIRED i link ACTIVE oltre `expires_at` e li tratta come invalidi.
"""
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from matches.models import MatchJuryLink

# >=32 byte di entropia -> token_urlsafe(32) produce ~43 char URL-safe.
_TOKEN_NBYTES = 32


class JuryLinkService:

    @staticmethod
    @transaction.atomic
    def issue(match, created_by=None):
        """
        Emette un nuovo link ACTIVE per il match, revocando l'eventuale ACTIVE
        precedente (monouso = un ciclo di vita per match).
        """
        now = timezone.now()
        MatchJuryLink.objects.filter(
            match=match, status=MatchJuryLink.Status.ACTIVE
        ).update(status=MatchJuryLink.Status.REVOKED, revoked_at=now)

        return MatchJuryLink.objects.create(
            match=match,
            token=secrets.token_urlsafe(_TOKEN_NBYTES),
            status=MatchJuryLink.Status.ACTIVE,
            created_by=created_by,
            expires_at=now + timedelta(days=MatchJuryLink.EXPIRY_DAYS),
        )

    @staticmethod
    @transaction.atomic
    def revoke(match):
        """Revoca l'eventuale link ACTIVE del match. Ritorna il n. di link revocati."""
        return MatchJuryLink.objects.filter(
            match=match, status=MatchJuryLink.Status.ACTIVE
        ).update(status=MatchJuryLink.Status.REVOKED, revoked_at=timezone.now())

    @staticmethod
    def resolve(token, match=None):
        """
        Ritorna il MatchJuryLink valido (ACTIVE + non scaduto) per il token, o
        None. Se `match` e' passato, il link deve appartenere a quel match.
        Degrada a EXPIRED (lazy) i link ACTIVE oltre la scadenza.
        """
        if not token:
            return None
        try:
            link = MatchJuryLink.objects.select_related('match').get(token=token)
        except MatchJuryLink.DoesNotExist:
            return None

        if link.status != MatchJuryLink.Status.ACTIVE:
            return None
        if link.is_expired_by_time:
            link.status = MatchJuryLink.Status.EXPIRED
            link.save(update_fields=['status'])
            return None
        if match is not None and link.match_id != match.id:
            return None
        return link

    @staticmethod
    @transaction.atomic
    def consume(link, report=None):
        """
        Porta il link a CONSUMED (chiamato dentro il close riuscito, atomico col
        cambio stato del referto). Nessuna transizione di ritorno.
        """
        link.status = MatchJuryLink.Status.CONSUMED
        link.consumed_at = timezone.now()
        if report is not None:
            link.report = report
        link.save(update_fields=['status', 'consumed_at', 'report'])
        return link

    @staticmethod
    def active_for_match(match):
        """L'eventuale link ACTIVE del match (senza valutare la scadenza per tempo)."""
        return MatchJuryLink.objects.filter(
            match=match, status=MatchJuryLink.Status.ACTIVE
        ).first()
