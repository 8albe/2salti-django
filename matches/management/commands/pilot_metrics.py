from django.core.management.base import BaseCommand
from matches.models import MatchReport, MatchReportAuditLog
from django.utils import timezone
import json

class Command(BaseCommand):
    help = 'Visualizza le metriche operative del pilot 2salti'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('--- REPORT METRICHE PILOT 2SALTI ---'))
        self.stdout.write("")

        reports = MatchReport.objects.exclude(status=MatchReport.Status.EXTRACTED).order_by('id')
        
        table_fmt = "{:<5} {:<15} {:<10} {:<15} {:<12} {:<10}"
        self.stdout.write(table_fmt.format("ID", "STATUS", "DURATA", "AUTO-MATCH%", "MANUAL FIX", "FORCED"))
        self.stdout.write("-" * 80)

        for report in reports:
            # Recupera log di apertura
            first_open = MatchReportAuditLog.objects.filter(report=report, action='review_opened').order_by('created_at').first()
            
            # Recupera log di pubblicazione
            publish_log = MatchReportAuditLog.objects.filter(report=report, action__in=['publish_now', 'publish_force']).order_by('-created_at').first()
            
            duration = "N/A"
            auto_pct = "N/A"
            manual_fixes = 0
            is_forced = "No"

            if publish_log and publish_log.after and '_metrics' in publish_log.after:
                m = publish_log.after['_metrics']
                duration_sec = m.get('duration_seconds', 0)
                duration = f"{int(duration_sec // 60)}m {int(duration_sec % 60)}s"
                
                total = m.get('total_players', 0)
                auto = m.get('auto_matched_at_start', 0)
                if total > 0:
                    auto_pct = f"{round((auto/total)*100)}%"
                else:
                    auto_pct = "100%"
                
                manual_fixes = m.get('manual_fixes', 0)
                is_forced = "SÌ" if m.get('is_forced') else "No"
            
            elif first_open:
                duration = "In corso..."
                m_start = first_open.after or {}
                total = m_start.get('total_players', 0)
                auto = m_start.get('auto_matched', 0)
                if total > 0:
                    auto_pct = f"{round((auto/total)*100)}%"
                else:
                    auto_pct = "100%"

            self.stdout.write(table_fmt.format(
                report.id, 
                report.get_status_display(), 
                duration, 
                auto_pct, 
                manual_fixes,
                is_forced
            ))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS('--- FINE REPORT ---'))
