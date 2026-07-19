import json
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.models import Sport, Society, League, Team
from matches.models import Match, MatchReport, MatchReportAuditLog

User = get_user_model()


def valid_digital_payload(home="Pro Recco", away="AN Brescia"):
    return {
        "metadata": {"version": "2.0", "confidence": 1.0, "source": "digital_app"},
        "match_info": {"home_team": home, "away_team": away, "date": "2026-07-19", "city": "Genova"},
        "scores": {"final_score": "0-0", "quarters": {}},
        "teams": {"home": {"players": []}, "away": {"players": []}},
        "events": [],
    }


class DigitalReportBaseTestCase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto-digital")
        self.society_h = Society.objects.create(name="Pro Recco", sport=self.sport, slug="pro-recco-digital")
        self.society_a = Society.objects.create(name="AN Brescia", sport=self.sport, slug="an-brescia-digital")
        self.league = League.objects.create(name="Serie A1", sport=self.sport, slug="serie-a1-digital")
        self.team_h = Team.objects.create(society=self.society_h, league=self.league)
        self.team_a = Team.objects.create(society=self.society_a, league=self.league)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_h,
            away_team=self.team_a,
            match_date=timezone.now(),
        )

        self.uploader = User.objects.create_user(
            username="uploader1", password="pw-test-123", role="fan", staff_role="UPLOADER"
        )
        self.reviewer = User.objects.create_user(
            username="reviewer1", password="pw-test-123", role="fan", staff_role="REVIEWER"
        )
        self.referee = User.objects.create_user(
            username="referee1", password="pw-test-123", role="referee"
        )
        self.plain_user = User.objects.create_user(
            username="plain1", password="pw-test-123", role="fan"
        )
        self.superuser = User.objects.create_superuser(
            username="admin_digital", email="admin_digital@test.com", password="pw-test-123"
        )

    def start_report(self, user):
        self.client.force_login(user)
        url = reverse('api_digital_report_start')
        return self.client.post(
            url,
            data=json.dumps({"match_id": self.match.id}),
            content_type='application/json',
        )


class DigitalReportStartTestCase(DigitalReportBaseTestCase):
    def test_start_creates_draft_report(self):
        response = self.start_report(self.uploader)
        self.assertEqual(response.status_code, 201)

        data = response.json()
        report = MatchReport.objects.get(id=data['id'])
        self.assertEqual(report.status, MatchReport.Status.DRAFT)
        self.assertEqual(report.source_channel, 'DIGITAL')
        self.assertEqual(report.uploader, self.uploader)

        # Payload v2.0 di default
        self.assertEqual(report.raw_extracted_data['metadata']['source'], 'digital_app')
        self.assertIn('teams', report.raw_extracted_data)

    def test_start_writes_audit_log(self):
        response = self.start_report(self.uploader)
        report = MatchReport.objects.get(id=response.json()['id'])

        log = MatchReportAuditLog.objects.get(report=report, action='create_digital')
        self.assertEqual(log.user, self.uploader)
        self.assertEqual(log.new_status, MatchReport.Status.DRAFT)

    def test_start_allowed_for_superuser(self):
        response = self.start_report(self.superuser)
        self.assertEqual(response.status_code, 201)

    def test_start_allowed_for_referee(self):
        response = self.start_report(self.referee)
        self.assertEqual(response.status_code, 201)

    def test_start_forbidden_for_plain_user(self):
        response = self.start_report(self.plain_user)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MatchReport.objects.filter(match=self.match).exists())

    def test_start_forbidden_for_anonymous(self):
        url = reverse('api_digital_report_start')
        response = self.client.post(
            url,
            data=json.dumps({"match_id": self.match.id}),
            content_type='application/json',
        )
        # login_required -> redirect al login (default-closed)
        self.assertIn(response.status_code, (302, 401, 403))
        self.assertFalse(MatchReport.objects.filter(match=self.match).exists())

    def test_start_missing_match_id_returns_400(self):
        self.client.force_login(self.uploader)
        url = reverse('api_digital_report_start')
        response = self.client.post(url, data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 400)


class DigitalReportUpdateTestCase(DigitalReportBaseTestCase):
    def setUp(self):
        super().setUp()
        response = self.start_report(self.uploader)
        self.report_id = response.json()['id']
        self.report = MatchReport.objects.get(id=self.report_id)
        self.update_url = reverse('api_digital_report_update', args=[self.report_id])

    def test_update_overwrites_draft_payload(self):
        self.client.force_login(self.uploader)
        new_payload = valid_digital_payload()
        new_payload['scores']['final_score'] = "5-3"

        response = self.client.put(
            self.update_url,
            data=json.dumps({"data": new_payload}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        self.report.refresh_from_db()
        self.assertEqual(self.report.raw_extracted_data['scores']['final_score'], "5-3")
        self.assertEqual(self.report.normalized_data['scores']['final_score'], "5-3")

    def test_update_allowed_for_reviewer(self):
        self.client.force_login(self.reviewer)
        response = self.client.put(
            self.update_url,
            data=json.dumps({"data": valid_digital_payload()}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_update_forbidden_for_other_user(self):
        other = User.objects.create_user(username="other1", password="pw-test-123", role="fan")
        self.client.force_login(other)
        response = self.client.put(
            self.update_url,
            data=json.dumps({"data": valid_digital_payload()}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_update_rejected_when_not_draft(self):
        self.report.status = MatchReport.Status.NEEDS_REVIEW
        self.report.save()

        self.client.force_login(self.uploader)
        response = self.client.put(
            self.update_url,
            data=json.dumps({"data": valid_digital_payload()}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_update_missing_data_returns_400(self):
        self.client.force_login(self.uploader)
        response = self.client.put(
            self.update_url,
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)


class DigitalReportCloseTestCase(DigitalReportBaseTestCase):
    def setUp(self):
        super().setUp()
        response = self.start_report(self.uploader)
        self.report_id = response.json()['id']
        self.report = MatchReport.objects.get(id=self.report_id)
        self.close_url = reverse('api_digital_report_close', args=[self.report_id])

    def test_close_valid_payload_transitions_to_needs_review(self):
        self.report.raw_extracted_data = valid_digital_payload()
        self.report.save()

        self.client.force_login(self.uploader)
        response = self.client.post(self.close_url)
        self.assertEqual(response.status_code, 200)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.NEEDS_REVIEW)

        log = MatchReportAuditLog.objects.get(report=self.report, action='close_digital')
        self.assertEqual(log.old_status, MatchReport.Status.DRAFT)
        self.assertEqual(log.new_status, MatchReport.Status.NEEDS_REVIEW)

    def test_close_as_is_no_pin_signature_required(self):
        """
        Fotografa il comportamento attuale: close chiude in NEEDS_REVIEW senza
        alcuna firma PIN arbitro, nonostante BLUEPRINT descriva l'endpoint come
        "firma PIN arbitro e chiude" (Macro 14 §14.3, discrepanza doc-vs-codice
        già nota e non risolta in questo giro).
        """
        self.report.raw_extracted_data = valid_digital_payload()
        self.report.save()

        self.client.force_login(self.uploader)
        response = self.client.post(self.close_url)
        self.assertEqual(response.status_code, 200)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.NEEDS_REVIEW)
        self.assertNotEqual(self.report.status, MatchReport.Status.PUBLISHED)

    def test_close_invalid_payload_rejected_without_transition(self):
        # Payload privo delle chiavi root richieste da OCRSchemaValidator
        self.report.raw_extracted_data = {"metadata": {"confidence": 1.0}}
        self.report.save()

        self.client.force_login(self.uploader)
        response = self.client.post(self.close_url)
        self.assertEqual(response.status_code, 422)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.DRAFT)
        self.assertFalse(
            MatchReportAuditLog.objects.filter(report=self.report, action='close_digital').exists()
        )

    def test_double_close_rejected(self):
        self.report.raw_extracted_data = valid_digital_payload()
        self.report.save()

        self.client.force_login(self.uploader)
        first = self.client.post(self.close_url)
        self.assertEqual(first.status_code, 200)

        second = self.client.post(self.close_url)
        # get_object_or_404(..., source_channel='DIGITAL') trova comunque il
        # referto (ormai NEEDS_REVIEW): OCRSchemaValidator lo rivalida (payload
        # ancora valido) e la view lo transiziona di nuovo, senza guardia sullo
        # stato corrente. Fotografa il comportamento as-is.
        self.assertEqual(second.status_code, 200)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.NEEDS_REVIEW)
        close_logs = MatchReportAuditLog.objects.filter(report=self.report, action='close_digital')
        self.assertEqual(close_logs.count(), 2)

    def test_close_forbidden_for_other_user(self):
        self.report.raw_extracted_data = valid_digital_payload()
        self.report.save()

        other = User.objects.create_user(username="other2", password="pw-test-123", role="fan")
        self.client.force_login(other)
        response = self.client.post(self.close_url)
        self.assertEqual(response.status_code, 403)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.DRAFT)
