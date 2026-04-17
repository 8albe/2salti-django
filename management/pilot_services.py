"""
Pilot operations services — daily report generation and urgent alert logic.
"""
import logging
from datetime import date, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from .models import PilotDailyLog, PilotBug, PilotFeedback, AuditLog

logger = logging.getLogger('management')


def get_pilot_email_recipients():
    """Return list of pilot email recipients from settings."""
    return getattr(settings, 'PILOT_EMAIL_RECIPIENTS', ['albegalbi@gmail.com'])


def generate_daily_report_data(report_date=None):
    """
    Compile daily pilot report data from models.
    Returns a dict suitable for template rendering.
    """
    if report_date is None:
        report_date = date.today()

    yesterday = report_date - timedelta(days=1)

    # Latest daily log
    daily_log = PilotDailyLog.objects.filter(date=report_date).first()
    yesterday_log = PilotDailyLog.objects.filter(date=yesterday).first()

    # Bug stats
    open_bugs = PilotBug.objects.exclude(status__in=['CLOSED', 'VERIFIED'])
    open_blockers = open_bugs.filter(severity='S1')
    new_bugs_today = PilotBug.objects.filter(created_at__date=report_date)
    closed_bugs_today = PilotBug.objects.filter(
        status__in=['CLOSED', 'VERIFIED'],
        updated_at__date=report_date
    )

    # Recurring issues — bugs seen more than once (reported multiple times or sometimes/always repro)
    recurring_bugs = open_bugs.filter(reproducibility__in=['ALWAYS', 'SOMETIMES'])

    # Feedback stats
    new_feedback_today = PilotFeedback.objects.filter(created_at__date=report_date)
    feedback_by_category = {}
    for fb in PilotFeedback.objects.exclude(status='DONE').values_list('category', flat=True):
        feedback_by_category[fb] = feedback_by_category.get(fb, 0) + 1

    # KPIs
    kpis = {
        'open_blockers_eod': open_blockers.count(),
        'new_bugs_count': new_bugs_today.count(),
        'closed_bugs_count': closed_bugs_today.count(),
        'recurring_issues_count': recurring_bugs.count(),
        'total_open_bugs': open_bugs.count(),
        'total_open_feedback': PilotFeedback.objects.exclude(status__in=['DONE', 'WONT_FIX']).count(),
    }

    return {
        'report_date': report_date,
        'daily_log': daily_log,
        'yesterday_log': yesterday_log,
        'overall_status': daily_log.status if daily_log else 'NO_LOG',
        'open_blockers': open_blockers,
        'open_blockers_count': open_blockers.count(),
        'new_bugs_today': new_bugs_today,
        'new_bugs_count': new_bugs_today.count(),
        'closed_bugs_today': closed_bugs_today,
        'closed_bugs_count': closed_bugs_today.count(),
        'recurring_issues': recurring_bugs,
        'recurring_issues_count': recurring_bugs.count(),
        'feedback_by_category': feedback_by_category,
        'new_feedback_today': new_feedback_today,
        'next_day_decision': daily_log.next_day_decision if daily_log else 'No log filed',
        'kpis': kpis,
    }


def send_daily_report_email(report_date=None, dry_run=False):
    """
    Generate and send the daily pilot report email.
    Returns the report data dict and the rendered HTML.
    """
    data = generate_daily_report_data(report_date)

    html_content = render_to_string('management/emails/pilot_report_email.html', data)

    status_label = data['overall_status']
    subject = f"[2salti Pilot] Daily Report — {data['report_date']} — {status_label}"

    recipients = get_pilot_email_recipients()

    if dry_run:
        logger.info(f"[DRY-RUN] Would send pilot report to {recipients}")
        return data, html_content

    send_mail(
        subject=subject,
        message='',  # plain text fallback empty — HTML only
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
        html_message=html_content,
        fail_silently=False,
    )

    logger.info(f"Pilot daily report sent to {recipients} for {data['report_date']}")
    return data, html_content


def check_and_send_urgent_alerts():
    """
    Check for red/blocking conditions and send urgent alert email.
    Uses AuditLog to deduplicate — won't re-alert for the same condition
    within the same calendar day.

    Triggers:
    1. Latest PilotDailyLog status == RED
    2. Any S1 bug with no workaround
    3. 3+ open blockers (S1)

    Returns list of triggered alert reasons, or empty list if no alerts fired.
    """
    today = date.today()
    alerts = []

    # 1. Red daily log
    latest_log = PilotDailyLog.objects.order_by('-date').first()
    if latest_log and latest_log.status == 'RED':
        alerts.append({
            'trigger': 'PILOT_STATUS_RED',
            'message': f"Pilot status set to RED on {latest_log.date}",
            'detail': latest_log.blockers or 'No blockers specified',
        })

    # 2. S1 bugs without workaround
    s1_no_workaround = PilotBug.objects.filter(
        severity='S1',
        workaround='',
    ).exclude(status__in=['CLOSED', 'VERIFIED'])

    for bug in s1_no_workaround:
        alerts.append({
            'trigger': 'S1_BUG_NO_WORKAROUND',
            'message': f"S1 bug without workaround: {bug.title}",
            'detail': bug.observed_behavior[:200],
        })

    # 3. 3+ open S1 blockers
    s1_open_count = PilotBug.objects.filter(severity='S1').exclude(
        status__in=['CLOSED', 'VERIFIED']
    ).count()

    if s1_open_count >= 3:
        alerts.append({
            'trigger': 'BLOCKER_ACCUMULATION',
            'message': f"{s1_open_count} open S1 blockers accumulated",
            'detail': 'Abnormal blocker count — immediate attention needed',
        })

    if not alerts:
        logger.info("Pilot alert check: no triggers fired.")
        return []

    # Dedup: check if we already sent alerts today
    already_alerted_today = AuditLog.objects.filter(
        action='PILOT_URGENT_ALERT',
        timestamp__date=today,
    ).exists()

    if already_alerted_today:
        logger.info("Pilot alert check: triggers found but alert already sent today.")
        return alerts  # Return alerts but don't re-send

    # Send alert email
    html_content = render_to_string('management/emails/pilot_alert_email.html', {
        'alerts': alerts,
        'alert_date': today,
        'alert_count': len(alerts),
    })

    subject = f"🚨 [2salti Pilot] URGENT ALERT — {len(alerts)} issue(s) detected"
    recipients = get_pilot_email_recipients()

    send_mail(
        subject=subject,
        message='',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
        html_message=html_content,
        fail_silently=False,
    )

    # Log to AuditLog for dedup
    AuditLog.objects.create(
        user=None,
        society=None,
        action='PILOT_URGENT_ALERT',
        details={'alerts': [a['trigger'] for a in alerts], 'count': len(alerts)},
    )

    logger.info(f"Pilot urgent alert sent to {recipients}: {len(alerts)} triggers")
    return alerts
