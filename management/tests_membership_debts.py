"""Regression test di chiusura debiti membership (giro batch 2026-06-19).

Copre i tre debiti chiusi in batch:

- DEBT-001 — rientro cross-stagione: dimostra che il rientro nella stessa
  society/team/role in stagione DIVERSA è una riga distinta permessa, mentre
  la stessa stagione resta bloccata. Chiuso PER COSTRUZIONE dalla
  UniqueConstraint(user, society, team, role, season) (Macro 16).
- DEBT-002 — dual-role coach: il signal su CoachProfile è role-differentiated;
  HEAD_COACH e ASSISTANT_COACH coesistono senza che la sincronizzazione di uno
  chiuda o duplichi l'altro.
- DEBT-004 — atomicità approve_membership: la transizione APPROVED e la
  creazione della Membership sono un'unica unità atomica (sub-bug "status
  persistito fuori dal blocco atomico"). La race redeem/approve in sé NON è
  falsificabile su SQLite (write serializzati, select_for_update no-op): qui si
  testa il sub-bug deterministico, il lock resta come fix difensivo per Postgres.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core.models import Season, Society, Sport, Team
from management.models import Membership, MembershipRequest

User = get_user_model()


class Debt001CrossSeasonReentryTests(TestCase):
    """DEBT-001: rientro cross-stagione assorbito dalla chiave season-aware."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.team = Team.objects.create(society=self.society, slug='team-a')
        self.season_prev = Season.objects.create(
            sport=self.sport, label='2024/2025', is_current=False
        )
        self.season_curr = Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )
        self.user = User.objects.create_user(username='athlete1', role='athlete')

    def _make(self, season):
        return Membership.objects.create(
            user=self.user, society=self.society, team=self.team,
            role='PLAYER', season=season,
        )

    def test_reentry_in_different_season_allowed(self):
        """Stesso (user, society, team, role) in stagione diversa = 2 righe."""
        m_prev = self._make(self.season_prev)
        m_curr = self._make(self.season_curr)

        self.assertNotEqual(m_prev.pk, m_curr.pk)
        self.assertEqual(
            Membership.objects.filter(
                user=self.user, society=self.society, team=self.team,
                role='PLAYER',
            ).count(),
            2,
        )

    def test_same_season_duplicate_blocked(self):
        """Stessa stagione: la UniqueConstraint blocca il duplicato."""
        self._make(self.season_curr)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._make(self.season_curr)


class Debt002DualRoleCoachTests(TestCase):
    """DEBT-002: il signal CoachProfile è role-aware (HEAD/ASSISTANT coesistono)."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.season = Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )
        self.team = Team.objects.create(society=self.society, slug='team-a')
        self.coach = User.objects.create_user(username='coach1', role='coach')

    def _coach_membership(self, role, **overrides):
        defaults = dict(
            user=self.coach, society=self.society, team=self.team,
            role=role, season=self.season, is_active=True,
        )
        defaults.update(overrides)
        return Membership.objects.create(**defaults)

    def test_dual_role_both_remain_active_after_profile_save(self):
        """Utente HEAD_COACH + ASSISTANT_COACH stesso team/stagione:
        il save del profilo non chiude né duplica l'altro ruolo."""
        head = self._coach_membership('HEAD_COACH')
        assistant = self._coach_membership('ASSISTANT_COACH')

        profile = self.coach.coach_profile
        profile.current_team = self.team
        profile.save()

        head.refresh_from_db()
        assistant.refresh_from_db()
        self.assertTrue(head.is_active)
        self.assertTrue(assistant.is_active)
        # Nessuna duplicazione: restano esattamente 2 membership coach.
        self.assertEqual(
            Membership.objects.filter(
                user=self.coach,
                role__in=['HEAD_COACH', 'ASSISTANT_COACH'],
            ).count(),
            2,
        )

    def test_assistant_only_does_not_spawn_spurious_head_coach(self):
        """Coach con SOLO ASSISTANT_COACH: il save del profilo non deve
        fabbricare una HEAD_COACH spuria (signal role-differentiated)."""
        assistant = self._coach_membership('ASSISTANT_COACH')

        profile = self.coach.coach_profile
        profile.current_team = self.team
        profile.save()

        assistant.refresh_from_db()
        self.assertTrue(assistant.is_active)
        self.assertFalse(
            Membership.objects.filter(
                user=self.coach, role='HEAD_COACH',
            ).exists(),
            "Il signal ha creato una HEAD_COACH spuria per un assistente.",
        )

    def test_new_coach_without_membership_defaults_to_head(self):
        """Backward-compat: un coach senza membership coach pregresse, al primo
        save con current_team, nasce HEAD_COACH (default di onboarding)."""
        profile = self.coach.coach_profile
        profile.current_team = self.team
        profile.save()

        self.assertTrue(
            Membership.objects.filter(
                user=self.coach, team=self.team, role='HEAD_COACH',
                is_active=True,
            ).exists()
        )


class Debt004ApproveAtomicityTests(TestCase):
    """DEBT-004: approve_membership — atomicità status+membership + lock difensivo."""

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.season = Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )
        self.team = Team.objects.create(society=self.society, slug='team-a')
        self.athlete = User.objects.create_user(username='ath', role='athlete')
        self.president = User.objects.create_user(
            username='prez', password='pwd', role='president',
            identity_status='VERIFIED', subscription_status='ACTIVE',
            setup_completed=True,
        )
        pp = self.president.president_profile
        pp.managed_society = self.society
        pp.save()
        self.req = MembershipRequest.objects.create(
            user=self.athlete, society=self.society, team=self.team,
            role='PLAYER', status='PENDING',
        )
        self.client.login(username='prez', password='pwd')

    def test_approve_happy_path_persists_status_and_membership(self):
        resp = self.client.post(
            reverse('approve_membership', args=[self.req.id]),
            {'action': 'approve'},
        )

        self.assertEqual(resp.status_code, 302)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'APPROVED')
        self.assertTrue(
            Membership.objects.filter(
                user=self.athlete, team=self.team, role='PLAYER',
                is_active=True,
            ).exists()
        )

    def test_approve_status_and_membership_atomic_on_save_failure(self):
        """Sub-bug DEBT-004: APPROVED e creazione Membership sono un'unica
        unità atomica. Se la persistenza dello stato fallisce, la Membership
        non deve restare orfana.

        NB: la race redeem/approve in sé NON è falsificabile su SQLite — i write
        sono serializzati a livello DB e select_for_update() è un no-op. Qui si
        testa il sub-bug di atomicità (deterministico); il select_for_update()
        resta come fix difensivo per PostgreSQL in produzione.
        """
        with patch.object(MembershipRequest, 'save', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse('approve_membership', args=[self.req.id]),
                    {'action': 'approve'},
                )

        self.assertFalse(
            Membership.objects.filter(
                user=self.athlete, team=self.team,
            ).exists(),
            "Membership orfana: creata ma status non persistito (non atomico).",
        )
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'PENDING')
