from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from matches.models import Match
from management.models import Convocation
from management.utils import log_action

class Command(BaseCommand):
    help = 'Invia reminder agli allenatori e gestisce la pubblicazione automatica delle convocazioni.'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # 1. REMINDERS (T-24, T-2, T-1)
        # Cerchiamo i match imminenti (prossime 24 ore)
        upcoming_matches = Match.objects.filter(
            match_date__range=[now, now + timedelta(hours=24)]
        )
        
        for match in upcoming_matches:
            # Recupera o crea (in bozza) la convocazione per questo match
            conv, created = Convocation.objects.get_or_create(match=match)
            head_coach = match.home_team.memberships.filter(role='HEAD_COACH', is_active=True).first()
            
            if not head_coach:
                continue
                
            coach_user = head_coach.user
            diff = match.match_date - now
            hours_diff = diff.total_seconds() / 3600
            
            # T-24 Reminder
            if 23 <= hours_diff <= 24 and 'T-24' not in conv.reminders_sent:
                self._send_reminder(conv, coach_user, "T-24")
                
            # T-2 Reminder (se non ancora inviata)
            if 1.5 <= hours_diff <= 2 and conv.status == 'DRAFT' and 'T-2' not in conv.reminders_sent:
                self._send_reminder(conv, coach_user, "T-2")
                
            # T-1 Reminder (se non ancora inviata)
            if 0.5 <= hours_diff <= 1 and conv.status == 'DRAFT' and 'T-1' not in conv.reminders_sent:
                self._send_reminder(conv, coach_user, "T-1")

        self.stdout.write(self.style.SUCCESS('Scheduler completato con successo.'))

    def _send_reminder(self, conv, user, label):
        """Simulazione invio notifica con log audit"""
        log_action(
            user=user, 
            society=conv.match.home_team.society, 
            action=f"REMINDER_{label}", 
            target=conv,
            details={"message": f"Reminder {label} per la partita {conv.match}"}
        )
        conv.reminders_sent.append(label)
        conv.save()
        self.stdout.write(f"Inviato reminder {label} a {user.username} per {conv.match}")
