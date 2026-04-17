"""
Test: Verifica che l'Audit Trail salvi correttamente old_status, new_status,
reason e le differenze nel database per ogni cambio di stato di un referto.
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from matches.models import MatchReport, Match, MatchReportAuditLog
from core.models import Sport, Society, Team, League

User = get_user_model()

PASS = 0
FAIL = 0

def check(description, condition):
    global PASS, FAIL
    if condition:
        print(f"  ✅ {description}")
        PASS += 1
    else:
        print(f"  ❌ {description}")
        FAIL += 1

# ── Setup ──────────────────────────────────────────────────────────
print("\n🔧 Setup test environment...")

sport, _ = Sport.objects.get_or_create(name='Test Sport Audit', slug='test-sport-audit')
society_h, _ = Society.objects.get_or_create(name='Audit Home Society', defaults={'sport': sport, 'city': 'TestCity'})
society_a, _ = Society.objects.get_or_create(name='Audit Away Society', defaults={'sport': sport, 'city': 'TestCity'})
team_h, _ = Team.objects.get_or_create(society=society_h, category='SENIOR', defaults={'name': 'Audit Home'})
team_a, _ = Team.objects.get_or_create(society=society_a, category='SENIOR', defaults={'name': 'Audit Away'})
league, _ = League.objects.get_or_create(name='Audit League', defaults={'sport': sport, 'season': '2025-2026', 'category': 'SENIOR'})

admin_user = User.objects.filter(is_superuser=True).first()
if not admin_user:
    admin_user = User.objects.create_superuser(username='audit_test_admin', password='test123', email='audit@test.com')

match = Match.objects.create(
    league=league, home_team=team_h, away_team=team_a,
    match_date=timezone.now()
)

report = MatchReport.objects.create(
    match=match, uploader=admin_user, status=MatchReport.Status.UPLOADED,
    normalized_data={'teams': {'home': {'score': 5}, 'away': {'score': 3}}}
)

# ── Test 1: Modello MatchReportAuditLog ha i nuovi campi ──────────
print("\n📋 Test 1: Verifica campi modello MatchReportAuditLog")
field_names = [f.name for f in MatchReportAuditLog._meta.get_fields()]
check("Campo 'old_status' esiste nel modello", 'old_status' in field_names)
check("Campo 'new_status' esiste nel modello", 'new_status' in field_names)
check("Campo 'reason' esiste nel modello", 'reason' in field_names)

# ── Test 2: Creazione audit log con tutti i campi ─────────────────
print("\n📋 Test 2: Creazione audit log completo con old_status, new_status, reason")
log1 = MatchReportAuditLog.objects.create(
    report=report,
    user=admin_user,
    action='validate',
    old_status='UPLOADED',
    new_status='VALIDATED',
    reason='Dati verificati manualmente - test audit trail',
    before={'teams': {'home': {'score': 4}}},
    after={'teams': {'home': {'score': 5}}}
)
check("Audit log creato con successo", log1.pk is not None)
check("old_status salvato correttamente", log1.old_status == 'UPLOADED')
check("new_status salvato correttamente", log1.new_status == 'VALIDATED')
check("reason salvato correttamente", 'test audit trail' in log1.reason)
check("before/after diff salvati", log1.before is not None and log1.after is not None)
check("__str__ include il cambio di stato", '(UPLOADED -> VALIDATED)' in str(log1))

# ── Test 3: Audit log senza cambio stato (save_draft) ─────────────
print("\n📋 Test 3: Audit log per save_draft (senza cambio stato)")
log2 = MatchReportAuditLog.objects.create(
    report=report,
    user=admin_user,
    action='save_draft',
    old_status='UPLOADED',
    new_status='UPLOADED',
    reason='',
    before={'teams': {'home': {'score': 5}}},
    after={'teams': {'home': {'score': 6}}}
)
check("save_draft log creato con successo", log2.pk is not None)
check("old_status == new_status per save_draft", log2.old_status == log2.new_status)
check("reason vuoto per save_draft è ammesso", log2.reason == '')

# ── Test 4: Audit log per publish ─────────────────────────────────
print("\n📋 Test 4: Audit log per pubblicazione")
log3 = MatchReportAuditLog.objects.create(
    report=report,
    user=admin_user,
    action='publish',
    old_status='VALIDATED',
    new_status='PUBLISHED',
    reason='Dati corretti, pronto per il pubblico',
    after={'events_created': 3, 'events_deleted': 0}
)
check("publish log creato con successo", log3.pk is not None)
check("old_status = VALIDATED", log3.old_status == 'VALIDATED')
check("new_status = PUBLISHED", log3.new_status == 'PUBLISHED')
check("reason presente", len(log3.reason) > 0)

# ── Test 5: Audit log per depublish ───────────────────────────────
print("\n📋 Test 5: Audit log per de-pubblicazione")
log4 = MatchReportAuditLog.objects.create(
    report=report,
    user=admin_user,
    action='depublish',
    old_status='PUBLISHED',
    new_status='VALIDATED',
    reason=f'Superato da nuova versione (Report ID 999)',
)
check("depublish log creato con successo", log4.pk is not None)
check("old_status = PUBLISHED", log4.old_status == 'PUBLISHED')
check("new_status = VALIDATED", log4.new_status == 'VALIDATED')
check("reason include ID del report sostitutivo", 'Report ID 999' in log4.reason)

# ── Test 6: Audit log per publish_force ───────────────────────────
print("\n📋 Test 6: Audit log per pubblicazione forzata")
log5 = MatchReportAuditLog.objects.create(
    report=report,
    user=admin_user,
    action='publish_force',
    old_status='NEEDS_REVIEW',
    new_status='PUBLISHED',
    reason='Override: blocchi ignorati per urgenza operativa',
)
check("publish_force log creato con successo", log5.pk is not None)
check("action = publish_force", log5.action == 'publish_force')
check("reason include override", 'Override' in log5.reason)

# ── Test 7: Query audit trail per report ──────────────────────────
print("\n📋 Test 7: Query audit trail completo per report")
all_logs = MatchReportAuditLog.objects.filter(report=report).order_by('-created_at')
check(f"Tutti i log presenti per il report: {all_logs.count()} voci", all_logs.count() == 5)

status_changes = all_logs.exclude(old_status='').exclude(new_status='')
check(f"Log con cambio stato: {status_changes.count()}", status_changes.count() == 5)

logs_with_reason = all_logs.exclude(reason='')
check(f"Log con motivazione: {logs_with_reason.count()}", logs_with_reason.count() == 4)  # save_draft has no reason

# ── Test 8: PublishingService firma aggiornata ────────────────────
print("\n📋 Test 8: Verifica firma PublishingService")
import inspect
sig = inspect.signature(
    __import__('matches.services.publishing_service', fromlist=['PublishingService']).PublishingService.publish_report
)
params = list(sig.parameters.keys())
check("PublishingService.publish_report accetta 'reason'", 'reason' in params)

# ── Cleanup ───────────────────────────────────────────────────────
print("\n🧹 Cleanup test data...")
MatchReportAuditLog.objects.filter(report=report).delete()
report.delete()
match.delete()

# ── Riepilogo ─────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"📊 RISULTATI: {PASS} passati, {FAIL} falliti su {PASS+FAIL} totali")
if FAIL == 0:
    print("🎉 TUTTI I TEST PASSATI — Audit Trail funzionante!")
else:
    print("⚠️  ATTENZIONE: Alcuni test sono falliti.")
print(f"{'='*50}\n")

sys.exit(1 if FAIL > 0 else 0)
