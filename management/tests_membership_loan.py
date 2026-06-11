"""Prestito strutturato (Macro 16 Fase 4, §16.5).

Unica eccezione a "una società per stagione": membership marcata is_loan con
società d'origine del tesseramento e stato-etichetta (Attivo/Concluso, NON
macchina a stati). Vale solo verso leghe dei grandi (A1–D).

Copertura: gate "dei grandi", coerenza campi (clean + CheckConstraint DB),
vincolo una-società-per-stagione sulle ATTIVE (successione D2: le righe
chiuse non contano), rollover di stagione.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import League, Season, Society, Sport, Team
from management.models import Membership

User = get_user_model()


class MembershipLoanTestsBase(TestCase):
    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn-loan")
        self.season = Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )
        self.origin = Society.objects.create(
            name="Origine", slug="origine", sport=self.sport, city="Roma"
        )
        self.destination = Society.objects.create(
            name="Destinazione", slug="destinazione", sport=self.sport, city="Milano"
        )
        self.senior_league = League.objects.create(
            name="serie B Maschile", sport=self.sport, season="2025/2026",
            season_fk=self.season, slug="loan-b", league_type='B',
        )
        self.youth_league = League.objects.create(
            name="Juniores - U18", sport=self.sport, season="2025/2026",
            season_fk=self.season, slug="loan-u18", league_type='U18',
        )
        self.unclassified_league = League.objects.create(
            name="Campionato Master", sport=self.sport, season="2025/2026",
            season_fk=self.season, slug="loan-nc", league_type=None,
        )
        self.origin_team = Team.objects.create(
            society=self.origin, league=self.senior_league, slug="loan-orig-b"
        )
        self.dest_senior_team = Team.objects.create(
            society=self.destination, league=self.senior_league, slug="loan-dest-b"
        )
        self.dest_youth_team = Team.objects.create(
            society=self.destination, league=self.youth_league, slug="loan-dest-u18"
        )
        self.dest_unclassified_team = Team.objects.create(
            society=self.destination, league=self.unclassified_league, slug="loan-dest-nc"
        )
        self.user = User.objects.create_user(username='loan_player', role='athlete')
        # Tesseramento d'origine attivo.
        self.origin_membership = Membership.objects.create(
            user=self.user, society=self.origin, team=self.origin_team,
            role='PLAYER', season=self.season,
        )

    def _loan(self, team=None, **overrides):
        kwargs = dict(
            user=self.user,
            society=self.destination,
            team=team or self.dest_senior_team,
            role='PLAYER',
            season=self.season,
            is_loan=True,
            tesseramento_society=self.origin,
            loan_status=Membership.LoanStatus.ACTIVE,
        )
        kwargs.update(overrides)
        return Membership(**kwargs)


class MembershipLoanValidationTests(MembershipLoanTestsBase):
    def test_loan_to_senior_league_is_valid(self):
        loan = self._loan()
        loan.full_clean()
        loan.save()
        self.assertTrue(loan.is_loan)
        self.assertEqual(loan.loan_status, Membership.LoanStatus.ACTIVE)
        # Il tesseramento d'origine resta attivo: due membership attive,
        # due società, stessa stagione — l'eccezione prevista.
        self.assertEqual(
            Membership.objects.filter(
                user=self.user, season=self.season, is_active=True
            ).count(),
            2,
        )

    def test_loan_to_youth_league_rejected(self):
        loan = self._loan(team=self.dest_youth_team)
        with self.assertRaises(ValidationError):
            loan.full_clean()

    def test_loan_to_unclassified_league_rejected(self):
        # league_type NULL non passa il gate (Null invece di invenzione).
        loan = self._loan(team=self.dest_unclassified_team)
        with self.assertRaises(ValidationError):
            loan.full_clean()

    def test_loan_without_team_rejected(self):
        loan = self._loan(team=None)
        loan.team = None
        with self.assertRaises(ValidationError):
            loan.full_clean()

    def test_loan_requires_tesseramento_society(self):
        loan = self._loan(tesseramento_society=None)
        with self.assertRaises(ValidationError):
            loan.full_clean()

    def test_loan_tesseramento_society_must_differ_from_destination(self):
        loan = self._loan(tesseramento_society=self.destination)
        with self.assertRaises(ValidationError):
            loan.full_clean()

    def test_loan_status_normalized_to_active(self):
        loan = self._loan(loan_status='')
        loan.full_clean()
        self.assertEqual(loan.loan_status, Membership.LoanStatus.ACTIVE)

    def test_non_loan_with_loan_fields_rejected_by_clean(self):
        m = Membership(
            user=self.user, society=self.destination,
            team=self.dest_senior_team, role='PLAYER', season=self.season,
            is_loan=False, tesseramento_society=self.origin,
        )
        with self.assertRaises(ValidationError):
            m.full_clean()

    def test_db_constraint_rejects_incoherent_loan_fields(self):
        # CheckConstraint a livello DB: prestito senza società d'origine.
        m = self._loan(tesseramento_society=None)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                m.save()


class OneSocietyPerSeasonTests(MembershipLoanTestsBase):
    def test_second_active_society_without_loan_rejected(self):
        m = Membership(
            user=self.user, society=self.destination,
            team=self.dest_senior_team, role='PLAYER', season=self.season,
        )
        with self.assertRaises(ValidationError):
            m.full_clean()

    def test_succession_closed_origin_allows_new_society(self):
        # Trasferimento definitivo in-season (D2): si chiude l'origine
        # (is_active=False, riga storica conservata) e si apre la nuova.
        self.origin_membership.is_active = False
        self.origin_membership.save(update_fields=['is_active'])

        m = Membership(
            user=self.user, society=self.destination,
            team=self.dest_senior_team, role='PLAYER', season=self.season,
        )
        m.full_clean()
        m.save()
        self.assertEqual(
            Membership.objects.filter(user=self.user, season=self.season).count(), 2
        )
        self.assertEqual(
            Membership.objects.filter(
                user=self.user, season=self.season, is_active=True
            ).count(),
            1,
        )

    def test_same_society_second_team_allowed(self):
        # Stessa società, altra squadra (es. giovanile che gioca anche in
        # prima squadra): nessun conflitto di società.
        youth_origin_team = Team.objects.create(
            society=self.origin, league=self.youth_league, slug="loan-orig-u18"
        )
        m = Membership(
            user=self.user, society=self.origin, team=youth_origin_team,
            role='PLAYER', season=self.season,
        )
        m.full_clean()
        m.save()
        self.assertEqual(
            Membership.objects.filter(
                user=self.user, season=self.season, is_active=True
            ).count(),
            2,
        )

    def test_other_season_no_conflict(self):
        season_next = Season.objects.create(
            sport=self.sport, label='2026/2027', is_current=False
        )
        m = Membership(
            user=self.user, society=self.destination,
            team=self.dest_senior_team, role='PLAYER', season=season_next,
        )
        m.full_clean()
        m.save()

    def test_origin_membership_clean_still_valid_with_active_loan(self):
        # Con un prestito attivo in essere, la membership d'origine resta
        # valida (il conflitto si calcola sulle non-prestito).
        loan = self._loan()
        loan.full_clean()
        loan.save()
        self.origin_membership.full_clean()  # non solleva
