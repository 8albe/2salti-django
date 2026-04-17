import logging
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

class NotificationService:
    @staticmethod
    def notify_integrity_mismatch(league, issues):
        """
        Invia una notifica (email + log) per discrepanze di integrità.
        """
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
        subject = f"[2salti OPS] - Discrepanza Integrità: {league.name}"
        
        issue_details = ""
        for issue in issues:
            issue_details += f"- [{issue['type']}] {issue['message']}\n"
            
        message = (
            f"Rilevata incoerenza dati per la lega: {league.name}\n"
            f"Data/Ora: {timestamp}\n\n"
            f"Dettaglio errori:\n"
            f"{issue_details}\n"
            f"---\n"
            f"Azione consigliata: Eseguire 'python3 manage.py rebuild_standings --league-id {league.id} --verify'\n"
        )
        
        # Logging sempre
        logger.warning(f"INTEGRITY_ALERT: {league.name} - {len(issues)} issues found.")
        
        # Email se configurata
        recipients = getattr(settings, 'OPS_EMAIL_RECIPIENTS', [])
        if recipients:
            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    recipients,
                    fail_silently=False,
                )
            except Exception as e:
                logger.error(f"Failed to send integrity email: {str(e)}")

        # Telegram notification
        NotificationService._send_telegram_message(f"🚨 {subject}\n\n{issue_details}")
        
        return True

    @staticmethod
    def notify_report_needs_review(report):
        """
        Invia una notifica quando un referto entra in NEEDS_REVIEW.
        """
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
        match = report.match
        subject = f"[2salti OPS] - REVISIONE NECESSARIA: {match.home_team} vs {match.away_team}"
        
        # Estrai motivazione dai validation_notes (spesso JSON)
        import json
        reason = report.validation_notes
        try:
            val_data = json.loads(report.validation_notes)
            if isinstance(val_data, dict) and 'blocking' in val_data:
                reason = "\n".join([f"- {b}" for b in val_data['blocking']])
        except (json.JSONDecodeError, TypeError):
            pass

        admin_url = f"https://2salti.com/matches/reports/{report.id}/review/" # Link ipotetico, allineare a URL reali
        
        message = (
            f"Un referto è stato bloccato e richiede revisione tecnica manuale.\n"
            f"Partita: {match}\n"
            f"Stato: {report.get_status_display()}\n"
            f"Data/Ora: {timestamp}\n\n"
            f"Motivazione Blocco:\n"
            f"{reason}\n\n"
            f"Revisiona qui: {admin_url}\n"
        )
        
        logger.warning(f"NEEDS_REVIEW_ALERT: Report {report.id} for {match}")

        # Email
        recipients = getattr(settings, 'OPS_EMAIL_RECIPIENTS', [])
        if recipients:
            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    recipients,
                    fail_silently=False,
                )
            except Exception as e:
                logger.error(f"Failed to send NEEDS_REVIEW email for report {report.id}: {str(e)}")

        # Telegram
        telegram_msg = f"🔍 *REVISIONE NECESSARIA*\nMatch: {match}\n\nMotivo:\n{reason}\n\n[Apri Cockpit]({admin_url})"
        NotificationService._send_telegram_message(telegram_msg)

    @staticmethod
    def _send_telegram_message(message):
        """
        Invia un messaggio Telegram via Bot API.
        """
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)
        
        if not token or not chat_id:
            logger.info("Telegram notification skipped: credentials missing.")
            return False
            
        import httpx
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        try:
            with httpx.Client() as client:
                response = client.post(url, json=payload, timeout=5)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {str(e)}")
            return False
