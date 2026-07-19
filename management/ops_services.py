import json
import logging
import subprocess
from datetime import date
from django.utils import timezone
import os
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from management.models import PilotDailyLog, PilotBug
from management.pilot_services import get_pilot_email_recipients

logger = logging.getLogger('management.ops')

# The path to persist out findings
OPS_LOG_DIR = os.path.join(settings.BASE_DIR, 'logs', 'ops')
os.makedirs(OPS_LOG_DIR, exist_ok=True)

class OpsCheckRunner:
    def __init__(self, mode):
        self.mode = mode
        self.findings = []
        self.overall_status = 'GREEN'
        self.check_time = timezone.localtime(timezone.now())

    def run_checks(self):
        self._check_systemd_timers()
        self._check_systemd_services()
        self._check_pilot_log()
        self._check_smtp_health()
        self._check_ocr_queue()
        if self.mode in ['afternoon', 'evening']:
            self._check_unresolved_issues()
            
    def _add_finding(self, title, severity, probable_cause, impact, remediation_attempted=False, remediation_succeeded=False, human_action_required=False, recommended_action="", outcome_category="Monitoring only — no action needed now", system_autofixed=False):
        self.findings.append({
            'title': title,
            'severity': severity,
            'detection_time': timezone.localtime(timezone.now()).isoformat(),
            'probable_cause': probable_cause,
            'impact': impact,
            'auto_remediation_attempted': remediation_attempted,
            'auto_remediation_succeeded': remediation_succeeded,
            'human_action_required': human_action_required,
            'recommended_action': recommended_action,
            'outcome_category': outcome_category,
            'system_autofixed': system_autofixed
        })
        if severity == 'RED':
            self.overall_status = 'RED'
        elif severity == 'YELLOW' and self.overall_status != 'RED':
            self.overall_status = 'YELLOW'

    def _check_systemd_timers(self):
        timers_to_check = ['2salti-pilot-report.timer', '2salti-pilot-alerts.timer']
        for timer in timers_to_check:
            res = subprocess.run(['systemctl', 'is-active', timer], capture_output=True, text=True)
            if res.returncode != 0:
                subprocess.run(['systemctl', 'start', timer])
                recheck = subprocess.run(['systemctl', 'is-active', timer], capture_output=True, text=True)
                if recheck.returncode == 0:
                    self._add_finding(
                        f"Timer {timer} was inactive", 
                        "YELLOW", 
                        "Timer failed or was stopped manually.",
                        "Scheduled jobs wouldn't run.",
                        remediation_attempted=True, 
                        remediation_succeeded=True,
                        system_autofixed=True,
                        recommended_action="The system restarted the timer successfully.",
                        outcome_category="Resolved automatically — no action needed"
                    )
                else:
                    self._add_finding(
                        f"Timer {timer} is DOWN", 
                        "RED", 
                        "Systemd failed to start the timer automatically.",
                        "Scheduled reports and alerts will not be sent.",
                        remediation_attempted=True, 
                        remediation_succeeded=False,
                        human_action_required=True,
                        recommended_action=f"Check `journalctl -u {timer}` on the server to see why it won't start.",
                        outcome_category="Urgent intervention required"
                    )

    def _check_systemd_services(self):
        services_to_check = ['2salti.service']
        for svc in services_to_check:
            res = subprocess.run(['systemctl', 'is-active', svc], capture_output=True, text=True)
            if res.returncode != 0:
                subprocess.run(['systemctl', 'restart', svc])
                recheck = subprocess.run(['systemctl', 'is-active', svc], capture_output=True, text=True)
                if recheck.returncode == 0:
                    self._add_finding(
                        f"Service {svc} was down", 
                        "YELLOW", 
                        "Service crashed or was stopped.",
                        "Platform was temporarily unavailable.",
                        remediation_attempted=True, 
                        remediation_succeeded=True,
                        system_autofixed=True,
                        recommended_action="The system restarted the service successfully.",
                        outcome_category="Resolved automatically — no action needed"
                    )
                else:
                    self._add_finding(
                        f"Service {svc} is DOWN", 
                        "RED", 
                        "Application crashed and failed to restart after automated attempt.",
                        "The main platform is entirely unavailable to pilot users.",
                        remediation_attempted=True, 
                        remediation_succeeded=False,
                        human_action_required=True,
                        recommended_action=f"Check `journalctl -u {svc}` immediately to debug application crash.",
                        outcome_category="Urgent intervention required"
                    )
                    
    def _check_pilot_log(self):
        if self.mode == 'morning':
            today = timezone.localdate()
            log = PilotDailyLog.objects.filter(date=today).first()
            if not log:
                # We also check if we are actually tracking any pilot behaviors yet.
                has_any_logs = PilotDailyLog.objects.exists()
                if has_any_logs:
                    self._add_finding(
                        "Missing Daily Pilot Log", 
                        "YELLOW", 
                        "No operational log was submitted yet for today.",
                        "Without the daily log, pilot metrics, blockers, and activities for the day are untracked.",
                        human_action_required=True,
                        recommended_action="Please login to the admin panel and file the Daily Pilot Log for today.",
                        outcome_category="Manual action required now"
                    )
                else:
                    # If there are no logs at all in the DB, the pilot probably hasn't officially started tracking days yet.
                    self._add_finding(
                        "No Pilot Logs Found (Pilot likely pending start)", 
                        "GREEN", 
                        "No daily pilot log was submitted, but this appears expected because the system has 0 total logs recorded.",
                        "Expected behavior until the first official pilot day log is submitted.",
                        human_action_required=False,
                        recommended_action="Remember to file the first Daily Pilot Log when the pilot officially begins.",
                        outcome_category="Monitoring only — no action needed now"
                    )

    def _check_smtp_health(self):
        pass

    # Profondita' della coda oltre la quale si segnala: con un solo worker e
    # ~80s per referto, 10 in attesa sono ~13 minuti di arretrato. Sotto questa
    # soglia la coda sta semplicemente lavorando.
    OCR_QUEUE_DEPTH_WARN = 10

    def _check_ocr_queue(self):
        """
        Salute della coda OCR (Macro 22, giro 2).

        Serve perche' il worker che si ferma non ha sintomi propri: i referti
        smettono di avanzare e basta: nessun errore, nessuna mail, nessuna
        pagina rotta. Chi guarda vede solo upload che restano "in elaborazione".
        Queste tre metriche rendono il silenzio visibile.
        """
        from datetime import timedelta

        from matches.models import MatchReport
        from matches.services.ocr_queue import OCRQueueService

        now = timezone.now()
        stale_cutoff = now - timedelta(minutes=OCRQueueService.STALE_MINUTES)

        queued = MatchReport.objects.filter(status=MatchReport.Status.QUEUED).count()
        stale_processing = MatchReport.objects.filter(
            status=MatchReport.Status.PROCESSING, ocr_started_at__lte=stale_cutoff,
        ).count()
        exhausted = MatchReport.objects.filter(
            status=MatchReport.Status.NEEDS_REVIEW,
            ocr_attempts__gte=OCRQueueService.MAX_ATTEMPTS,
        ).count()

        # (b) Referti piantati in PROCESSING: il sintomo piu' netto di worker
        # morto. Il backstop `recover_stale_reports` li riaccoda, ma se ne
        # trova di continuo vuol dire che nessuno li sta consumando.
        if stale_processing:
            self._add_finding(
                "Referti OCR piantati in PROCESSING",
                "RED",
                "Il worker `ocr_worker` e' fermo o muore a meta' job: i referti restano claimati senza avanzare.",
                f"{stale_processing} referti fermi da oltre {OCRQueueService.STALE_MINUTES} minuti: "
                "gli utenti vedono l'elaborazione bloccata a tempo indefinito.",
                human_action_required=True,
                recommended_action=(
                    "Verificare `systemctl status 2salti-ocrworker` e i log in journald; "
                    "il timer `2salti-recover-stale` li riaccoda ma non rimpiazza il worker."
                ),
                outcome_category="Urgent intervention required",
            )

        # (a) Profondita' della coda: alta anche senza referti stale significa
        # worker vivo ma troppo lento, o appena riavviato con arretrato.
        if queued > self.OCR_QUEUE_DEPTH_WARN:
            self._add_finding(
                "Coda OCR profonda",
                "YELLOW",
                "Arrivo di referti piu' rapido della capacita' del singolo worker, oppure worker riavviato con arretrato.",
                f"{queued} referti in attesa di elaborazione: i tempi di attesa percepiti crescono.",
                human_action_required=False,
                recommended_action="Monitorare: se non rientra da sola, valutare un secondo worker (Macro 22 giro 4).",
                outcome_category="Monitoring only — no action needed now",
            )

        # (c) Tentativi esauriti: gia' notificati uno a uno al momento del
        # fallimento, ma qui se ne vede l'accumulo — un picco indica un guasto
        # sistemico del provider, non sfortuna sul singolo referto.
        if exhausted:
            self._add_finding(
                "Referti OCR con tentativi esauriti",
                "YELLOW",
                f"Referti falliti {OCRQueueService.MAX_ATTEMPTS} volte di fila: provider OCR degradato o file illeggibili.",
                f"{exhausted} referti in NEEDS_REVIEW dopo aver esaurito i tentativi: richiedono lavorazione manuale.",
                human_action_required=True,
                recommended_action="Rivedere i referti in NEEDS_REVIEW nell'admin e riaccodarli con l'azione 'Elabora OCR'.",
                outcome_category="Urgent intervention required",
            )

    def _check_unresolved_issues(self):
        open_bugs = PilotBug.objects.filter(severity='S1').exclude(status__in=['CLOSED', 'VERIFIED'])
        if open_bugs.exists():
            self._add_finding(
                "Unresolved S1 Blockers persist", 
                "RED", 
                "There are S1 bugs not yet closed since the morning check.",
                "Pilot usage is at severe risk or totally blocked.",
                human_action_required=True,
                recommended_action="Look at active S1 bugs in PilotBug and resolve them or push updates to users.",
                outcome_category="Urgent intervention required"
            )

    def persist_results(self):
        log_name = f"ops_check_{self.check_time.strftime('%Y%m%d_%H%M%S')}_{self.mode}.json"
        log_path = os.path.join(OPS_LOG_DIR, log_name)
        data = {
            'mode': self.mode,
            'timestamp': self.check_time.isoformat(),
            'overall_status': self.overall_status,
            'findings': self.findings
        }
        with open(log_path, 'w') as f:
            json.dump(data, f, indent=2)
        return data

    def send_report(self, data):
        html_content = render_to_string('management/emails/ops_report_email.html', {
            'mode': self.mode,
            'check_time': self.check_time.strftime('%Y-%m-%d %H:%M'),
            'overall_status': self.overall_status,
            'findings': self.findings,
            'green_run': len(self.findings) == 0
        })

        subject = f"[{self.mode.upper()} OPS CHECK] {self.overall_status} - 2salti Pilot"
        recipients = get_pilot_email_recipients()
        
        send_mail(
            subject=subject,
            message='',  # HTML only
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            html_message=html_content,
            fail_silently=False,
        )

def run_ops_check(mode):
    runner = OpsCheckRunner(mode)
    runner.run_checks()
    data = runner.persist_results()
    runner.send_report(data)
    return data
