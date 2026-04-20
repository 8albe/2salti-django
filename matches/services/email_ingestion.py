import os
import hashlib
import logging
from email import message_from_bytes
from email.utils import parsedate_to_datetime
from django.core.files.base import ContentFile
from django.utils import timezone
from matches.models import MatchReport, InboundEmail, Match

logger = logging.getLogger(__name__)

class EmailIngestionService:
    """
    Servizio per l'ingestione di referti via email.
    Supporta il parsing di file .eml e la creazione di MatchReport.
    """
    
    ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png'}

    @classmethod
    def process_eml_file(cls, file_path: str):
        """Processa un file .eml su disco."""
        with open(file_path, 'rb') as f:
            return cls.process_raw_eml(f.read())

    @classmethod
    def process_raw_eml(cls, raw_content: bytes):
        """
        Parsa il contenuto raw di una email e crea i relativi MatchReport.
        Ritorna una lista di (MatchReport, creato_nuovo).
        """
        msg = message_from_bytes(raw_content)
        
        message_id = msg.get('Message-ID')
        sender = msg.get('From', '')
        subject = msg.get('Subject', '')
        date_str = msg.get('Date')
        
        try:
            received_at = parsedate_to_datetime(date_str) if date_str else timezone.now()
        except Exception:
            received_at = timezone.now()

        # 1. Verifica Idempotenza Email (Message-ID)
        inbound_email, created = InboundEmail.objects.get_or_create(
            message_id=message_id,
            defaults={
                'sender': sender,
                'subject': subject,
                'received_at': received_at,
            }
        )
        
        if not created:
            logger.info(f"Email {message_id} già processata in precedenza.")
            # Se l'email è già stata processata, ritorniamo i report ad essa collegati
            return [(r, False) for r in inbound_email.reports.all()]

        results = []
        
        # 2. Estrazione Allegati
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            
            filename = part.get_filename()
            if not filename:
                continue
                
            ext = os.path.splitext(filename)[1].lower()
            if ext not in cls.ALLOWED_EXTENSIONS:
                logger.debug(f"Allegato {filename} scartato (estensione non supportata).")
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            # 3. Deduplica per Hash del File
            file_hash = hashlib.sha256(payload).hexdigest()
            existing_report = MatchReport.objects.filter(file_hash=file_hash).first()
            
            if existing_report:
                logger.info(f"Allegato {filename} (hash {file_hash[:8]}) già presente nel sistema (ID {existing_report.id}).")
                # Colleghiamo l'email esistente se necessario? Per ora saltiamo o colleghiamo.
                if not existing_report.inbound_email:
                    existing_report.inbound_email = inbound_email
                    existing_report.save()
                results.append((existing_report, False))
                continue

            # 4. Creazione MatchReport
            # Per l'MVP, se non riusciamo a mappare il match, lasciamo un placeholder o chiediamo admin.
            # Qui cerchiamo di essere "smart": se il subject contiene "ID: <num>", proviamo a linkare.
            match = cls._guess_match(subject)
            
            report = MatchReport(
                match=match,
                status=MatchReport.Status.UPLOADED,
                source_type='EMAIL',
                source_metadata={
                    'email_subject': subject,
                    'email_sender': sender,
                    'message_id': message_id,
                    'filename': filename,
                },
                inbound_email=inbound_email,
                file_hash=file_hash
            )
            
            # Salvataggio file
            django_file = ContentFile(payload, name=filename)
            report.file.save(filename, django_file, save=False)
            report.save()
            
            logger.info(f"Creato MatchReport {report.id} dall'email {message_id} (file: {filename})")
            results.append((report, True))

        return results

    @staticmethod
    def _guess_match(subject: str):
        """
        Tenta di individuare il match dal subject dell'email.
        Esempio: "Referto Match ID: 14"
        In mancanza di match, ritorna il primo match disponibile o None (richiedendo intervento admin).
        """
        import re
        match_id_search = re.search(r'ID:\s*(\d+)', subject, re.IGNORECASE)
        if match_id_search:
            try:
                return Match.objects.get(id=int(match_id_search.group(1)))
            except Match.DoesNotExist:
                pass
        
        # Fallback: se non c'è match, prendiamo l'ultimo match creato o None.
        # Nelle reali implementazioni potremmo cercare per nomi squadre.
        return Match.objects.first() 
