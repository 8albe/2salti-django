"""Macro 16 Fase 2 (fetta 2d-1): i 3 creation-site di Membership nascono
season-aware.

Verifica che una Membership *nuova* creata da ciascuno dei tre path
(signal onboarding, redeem activation code, approvazione MembershipRequest)
riceva `season` derivata come il backfill 2b:
  - primaria: team.league.season_fk
  - fallback: unica Season is_current per society.sport
  - difensivo (team=None / niente lega / niente current): season=None
E che una Membership *esistente* (get_or_create created=False) non venga
toccata: i defaults sono ignorati per definizione (idempotenza).

La FK season e' ancora nullable (nessuna migration in 2d-1): il ramo difensivo
e' lecito e non deve sollevare.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import League, Season, Society, Sport, Team
from management.models import ActivationCode, Membership, MembershipRequest
from management.services.membership_enrollment import redeem_activation_code
from management.services.membership_season import resolve_membership_season

User = get_user_model()


class ResolveMembershipSeasonHelperTests(TestCase):
    """Unit test della derivazione pura, indipendente dai creation-site."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.user = User.objects.create_user(username='u1', role='athlete')

    def _season(self, label, is_current=False, sport=None):
        return Season.objects.create(
            sport=sport or self.sport, label=label, is_current=is_current
        )

    def _league(self, season_fk, slug):
        return League.objects.create(
            name="Serie A1", sport=self.sport, category='SENIOR',
            season=season_fk.label, season_fk=season_fk, slug=slug,
        )

    def test_primary_via_team_league_season_fk(self):
        season = self._season('2025/2026', is_current=True)
        league = self._league(season, slug='a1-2526')
        team = Team.objects.create(
            society=self.society, category='SENIOR', slug='t1', league=league
        )

        resolved = resolve_membership_season(
            self.user, self.society, team, 'PLAYER'
        )

        self.assertEqual(resolved, season)

    def test_primary_wins_over_fallback(self):
        # La lega punta a una stagione diversa da quella is_current: vince la
        # derivazione primaria (deterministica), non il fallback.
        current = self._season('2025/2026', is_current=True)
        league_season = self._season('2024/2025', is_current=False)
        league = self._league(league_season, slug='a1-2425')
        team = Team.objects.create(
            society=self.society, category='SENIOR', slug='t2', league=league
        )

        resolved = resolve_membership_season(
            self.user, self.society, team, 'PLAYER'
        )

        self.assertEqual(resolved, league_season)

    def test_fallback_current_season_for_sport(self):
        # Team senza lega -> fallback su Season is_current per society.sport.
        current = self._season('2025/2026', is_current=True)
        team = Team.objects.create(
            society=self.society, category='SENIOR', slug='t3', league=None
        )

        resolved = resolve_membership_season(
            self.user, self.society, team, 'PLAYER'
        )

        self.assertEqual(resolved, current)

    def test_fallback_when_team_none(self):
        # PRESIDENT / codice senza team -> direttamente al fallback.
        current = self._season('2025/2026', is_current=True)

        resolved = resolve_membership_season(
            self.user, self.society, None, 'PRESIDENT'
        )

        self.assertEqual(resolved, current)

    def test_defensive_branch_returns_none(self):
        # Nessuna lega e nessuna Season is_current per lo sport -> None.
        team = Team.objects.create(
            society=self.society, category='SENIOR', slug='t4', league=None
        )

        resolved = resolve_membership_season(
            self.user, self.society, team, 'PLAYER'
        )

        self.assertIsNone(resolved)


class MembershipCreationSeasonAwareTests(TestCase):
    """I 3 creation-site popolano season alla nascita della Membership."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.season = Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )
        self.league = League.objects.create(
            name="Serie A1", sport=self.sport, category='SENIOR',
            season='2025/2026', season_fk=self.season, slug='a1-2526',
        )
        self.team = Team.objects.create(
            society=self.society, category='SENIOR', slug='team-a',
            league=self.league,
        )
        # Team senza lega: forza il ramo fallback (is_current per sport).
        self.team_no_league = Team.objects.create(
            society=self.society, category='U20', slug='team-b', league=None
        )
        self.user = User.objects.create_user(username='athlete1', role='athlete')

    # ── signal path (_open_or_reopen_membership) ─────────────────────────────

    def test_signal_path_sets_season_via_league(self):
        profile = self.user.athlete_profile
        profile.current_team = self.team
        profile.save()

        m = Membership.objects.get(user=self.user, role='PLAYER')
        self.assertEqual(m.season, self.season)

    def test_signal_path_president_team_none_uses_fallback(self):
        prez = User.objects.create_user(username='prez', role='president')
        profile = prez.president_profile
        profile.managed_society = self.society
        profile.save()

        m = Membership.objects.get(user=prez, role='PRESIDENT')
        self.assertIsNone(m.team)
        self.assertEqual(m.season, self.season)  # fallback is_current

    # ── redeem activation code ───────────────────────────────────────────────

    def test_enrollment_path_sets_season_via_league(self):
        ActivationCode.objects.create(
            code='ABC-123', society=self.society, team=self.team,
            role='PLAYER', max_uses=5, current_uses=0, is_active=True,
        )

        ok, membership, err = redeem_activation_code(self.user, 'ABC-123')

        self.assertTrue(ok)
        self.assertEqual(membership.season, self.season)

    def test_enrollment_path_sets_season_via_fallback(self):
        # Codice su team senza lega -> derivazione via fallback is_current.
        ActivationCode.objects.create(
            code='NOLG-1', society=self.society, team=self.team_no_league,
            role='PLAYER', max_uses=5, current_uses=0, is_active=True,
        )

        ok, membership, err = redeem_activation_code(self.user, 'NOLG-1')

        self.assertTrue(ok)
        self.assertEqual(membership.season, self.season)

    # ── approvazione MembershipRequest (view) ────────────────────────────────

    def test_approve_request_path_sets_season(self):
        president_user = User.objects.create_user(
            username='prez2', password='pwd', role='president',
            identity_status='VERIFIED', subscription_status='ACTIVE',
            setup_completed=True,
        )
        president_user.president_profile.managed_society = self.society
        president_user.president_profile.save()
        req = MembershipRequest.objects.create(
            user=self.user, society=self.society, team=self.team,
            role='PLAYER', status='PENDING',
        )
        self.client.login(username='prez2', password='pwd')

        resp = self.client.post(
            reverse('approve_membership', args=[req.id]), {'action': 'approve'}
        )

        self.assertEqual(resp.status_code, 302)
        m = Membership.objects.get(
            user=self.user, society=self.society, team=self.team, role='PLAYER'
        )
        self.assertEqual(m.season, self.season)

    # ── idempotenza: created=False non sovrascrive season ────────────────────

    def test_existing_membership_season_not_overwritten(self):
        # Membership preesistente con una season "altra" (non corrente). Un
        # redeem sullo stesso lookup non deve toccarla (defaults ignorati).
        other_season = Season.objects.create(
            sport=self.sport, label='2024/2025', is_current=False
        )
        existing = Membership.objects.create(
            user=self.user, society=self.society, team=self.team,
            role='PLAYER', season=other_season,
        )
        ActivationCode.objects.create(
            code='IDEM-1', society=self.society, team=self.team,
            role='PLAYER', max_uses=5, current_uses=0, is_active=True,
        )

        ok, membership, err = redeem_activation_code(self.user, 'IDEM-1')

        self.assertTrue(ok)
        self.assertEqual(membership.pk, existing.pk)
        existing.refresh_from_db()
        self.assertEqual(existing.season, other_season)  # invariata
