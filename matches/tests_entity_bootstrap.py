from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model

from matches.models import Match, MatchReport
from matches.services.entity_bootstrap import EntityBootstrapService
from core.models import Team, League, Sport, Society

User = get_user_model()


class EntityBootstrapServiceTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pallanuoto")
        self.soc_a = Society.objects.create(name="PlaceholderA", slug="placeholder-a", sport=self.sport, city="X")
        self.soc_b = Society.objects.create(name="PlaceholderB", slug="placeholder-b", sport=self.sport, city="X")
        self.league = League.objects.create(name="TestLeague", sport=self.sport)
        self.team_a = Team.objects.create(society=self.soc_a, name="PlaceholderA")
        self.team_b = Team.objects.create(society=self.soc_b, name="PlaceholderB")
        self.match = Match.objects.create(
            league=self.league, home_team=self.team_a, away_team=self.team_b,
            match_date=timezone.now()
        )
        self.admin_user = User.objects.create_superuser(
            username='admin_boot', password='password', email='admin@test.com'
        )

    def _make_data(self, home="Pro Recco", away="AN Brescia"):
        return {
            "metadata": {"confidence": 0.9},
            "match_info": {"home_team": home, "away_team": away},
            "scores": {"final_score": "3-2"},
            "teams": {"home": {"players": []}, "away": {"players": []}},
            "events": [],
        }

    def test_both_teams_missing(self):
        """Both OCR team names don't exist in DB → preview shows will_create for both."""
        data = self._make_data("NewTeamAlpha", "NewTeamBeta")
        preview = EntityBootstrapService.preview_creation(data, self.match)

        self.assertTrue(preview["detection"]["has_issues"])
        self.assertFalse(preview["blocked"])
        self.assertEqual(len(preview["will_create_teams"]), 2)
        names = {t["name"] for t in preview["will_create_teams"]}
        self.assertIn("NewTeamAlpha", names)
        self.assertIn("NewTeamBeta", names)

    def test_one_team_missing(self):
        """One OCR team exists, other doesn't → one reuse, one create."""
        # Create one matching team
        soc = Society.objects.create(name="ExistingClub", slug="existingclub", sport=self.sport, city="Y")
        Team.objects.create(society=soc, name="ExistingClub")

        data = self._make_data("ExistingClub", "BrandNewClub")
        preview = EntityBootstrapService.preview_creation(data, self.match)

        self.assertTrue(preview["detection"]["has_issues"])
        self.assertFalse(preview["blocked"])
        self.assertEqual(len(preview["will_reuse_teams"]), 1)
        self.assertEqual(len(preview["will_create_teams"]), 1)
        self.assertEqual(preview["will_reuse_teams"][0]["name"], "ExistingClub")
        self.assertEqual(preview["will_create_teams"][0]["name"], "BrandNewClub")

    def test_no_issues_when_teams_match(self):
        """OCR team names match match's current teams → no issues."""
        data = self._make_data("PlaceholderA", "PlaceholderB")
        preview = EntityBootstrapService.preview_creation(data, self.match)

        self.assertFalse(preview["detection"]["has_issues"])
        self.assertEqual(len(preview["will_create_teams"]), 0)
        self.assertEqual(len(preview["will_reuse_teams"]), 0)

    def test_ambiguous_names_block(self):
        """Multiple teams with same name → blocked with warning."""
        # Create two teams with same name (different societies)
        soc1 = Society.objects.create(name="AmbigTeam", slug="ambig-1", sport=self.sport, city="A")
        soc2 = Society.objects.create(name="AmbigTeam2", slug="ambig-2", sport=self.sport, city="B")
        Team.objects.create(society=soc1, name="AmbigTeam")
        Team.objects.create(society=soc2, name="AmbigTeam")

        data = self._make_data("AmbigTeam", "PlaceholderB")
        preview = EntityBootstrapService.preview_creation(data, self.match)

        self.assertTrue(preview["blocked"])
        self.assertTrue(len(preview["warnings"]) > 0)
        self.assertIn("Risolvi manualmente", preview["warnings"][0])

    def test_execute_creates_teams(self):
        """Execute bootstrap creates Society+Team and updates match."""
        data = self._make_data("CreatedHome", "CreatedAway")

        success, msg, warnings = EntityBootstrapService.execute_bootstrap(data, self.match)

        self.assertTrue(success)
        self.assertIn("Creati", msg)

        # Verify teams created
        self.assertTrue(Team.objects.filter(name="CreatedHome").exists())
        self.assertTrue(Team.objects.filter(name="CreatedAway").exists())

        # Verify match updated
        self.match.refresh_from_db()
        self.assertEqual(self.match.home_team.name, "CreatedHome")
        self.assertEqual(self.match.away_team.name, "CreatedAway")

    def test_execute_no_duplicates(self):
        """Running bootstrap twice doesn't create duplicate teams."""
        data = self._make_data("UniqueTeamX", "UniqueTeamY")

        EntityBootstrapService.execute_bootstrap(data, self.match)
        initial_count = Team.objects.count()

        # Run again — should reuse, not duplicate
        success, msg, _ = EntityBootstrapService.execute_bootstrap(data, self.match)
        self.assertTrue(success)
        self.assertEqual(Team.objects.count(), initial_count)

    def test_execute_blocked_on_ambiguity(self):
        """Execute returns failure when ambiguity exists."""
        soc1 = Society.objects.create(name="DupName", slug="dup-1", sport=self.sport, city="A")
        soc2 = Society.objects.create(name="DupName2", slug="dup-2", sport=self.sport, city="B")
        Team.objects.create(society=soc1, name="DupName")
        Team.objects.create(society=soc2, name="DupName")

        data = self._make_data("DupName", "PlaceholderB")
        success, msg, warnings = EntityBootstrapService.execute_bootstrap(data, self.match)

        self.assertFalse(success)
        self.assertIn("bloccato", msg.lower())


class EntityBootstrapAdminIntegrationTest(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="WP", slug="wp-boot")
        self.soc_a = Society.objects.create(name="TempA", slug="temp-a", sport=self.sport, city="X")
        self.soc_b = Society.objects.create(name="TempB", slug="temp-b", sport=self.sport, city="X")
        self.league = League.objects.create(name="BootLeague", sport=self.sport)
        self.team_a = Team.objects.create(society=self.soc_a, name="TempA")
        self.team_b = Team.objects.create(society=self.soc_b, name="TempB")
        self.match = Match.objects.create(
            league=self.league, home_team=self.team_a, away_team=self.team_b,
            match_date=timezone.now()
        )
        self.report = MatchReport.objects.create(
            match=self.match,
            status=MatchReport.Status.EXTRACTED,
            normalized_data={
                "metadata": {"confidence": 0.9},
                "match_info": {"home_team": "NewHome", "away_team": "NewAway"},
                "scores": {"final_score": "5-3"},
                "teams": {"home": {"players": []}, "away": {"players": []}},
                "events": [],
            },
            raw_extracted_data={"metadata": {"confidence": 0.9}},
        )
        self.admin_user = User.objects.create_superuser(
            username='admin_boot2', password='password', email='admin@test.com'
        )
        self.client.login(username='admin_boot2', password='password')

    def test_review_page_shows_bootstrap(self):
        """Review page shows the bootstrap section when teams don't match."""
        url = reverse('op_admin:matches_matchreport_review', args=[self.report.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Check bootstrap context is passed and has_issues is True
        self.assertTrue(response.context['bootstrap']['detection']['has_issues'])
        self.assertContains(response, "NewHome")
        self.assertContains(response, "NewAway")
        self.assertContains(response, "bootstrap_entities")

    def test_bootstrap_action_creates_entities(self):
        """POST bootstrap action creates teams and updates match."""
        url = reverse('op_admin:matches_matchreport_review', args=[self.report.pk])
        response = self.client.post(url, {'_action': 'bootstrap_entities'})

        self.assertEqual(response.status_code, 302)  # redirect

        self.match.refresh_from_db()
        self.assertEqual(self.match.home_team.name, "NewHome")
        self.assertEqual(self.match.away_team.name, "NewAway")
        self.assertTrue(Team.objects.filter(name="NewHome").exists())
        self.assertTrue(Team.objects.filter(name="NewAway").exists())

    def test_review_hides_bootstrap_when_matched(self):
        """Review page hides bootstrap section when teams already match."""
        self.report.normalized_data["match_info"]["home_team"] = "TempA"
        self.report.normalized_data["match_info"]["away_team"] = "TempB"
        self.report.save()

        url = reverse('op_admin:matches_matchreport_review', args=[self.report.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Entità Mancanti")
