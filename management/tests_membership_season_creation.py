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

Dal flip NOT NULL (2d-7) il ramo difensivo (season non derivabile) non produce
piu' righe season=NULL: i creation-site falliscono in modo esplicito
(errore utente sul redeem/approve, RuntimeError sul signal).
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
            name="Serie A1", sport=self.sport, season=season_fk.label, season_fk=season_fk, slug=slug,
        )

    def test_primary_via_team_league_season_fk(self):
        season = self._season('2025/2026', is_current=True)
        league = self._league(season, slug='a1-2526')
        team = Team.objects.create(
            society=self.society, slug='t1', league=league
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
            society=self.society, slug='t2', league=league
        )

        resolved = resolve_membership_season(
            self.user, self.society, team, 'PLAYER'
        )

        self.assertEqual(resolved, league_season)

    def test_fallback_current_season_for_sport(self):
        # Team senza lega -> fallback su Season is_current per society.sport.
        current = self._season('2025/2026', is_current=True)
        team = Team.objects.create(
            society=self.society, slug='t3', league=None
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
            society=self.society, slug='t4', league=None
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
            name="Serie A1", sport=self.sport, season='2025/2026', season_fk=self.season, slug='a1-2526',
        )
        self.team = Team.objects.create(
            society=self.society, slug='team-a',
            league=self.league,
        )
        # Team senza lega: forza il ramo fallback (is_current per sport).
        self.team_no_league = Team.objects.create(
            society=self.society, slug='team-b', league=None
        )
        self.user = User.objects.create_user(username='athlete1', role='athlete')

    # ── signal path (_open_or_reopen_membership) ─────────────────────────────

    def test_signal_path_sets_season_via_league(self):
        profile = self.user.athlete_profile
        profile.current_team = self.team
        profile.save()

        m = Membership.objects.get(user=self.user, role='PLAYER')
        self.assertEqual(m.season, self.season)

    def test_president_managed_society_does_not_open_membership(self):
        # §10.10 — Presidente de-vincolato dalla stagione: assegnare managed_society
        # NON apre piu' una Membership PRESIDENT e NON solleva, nemmeno quando lo
        # sport della societa' non ha una Season corrente (era l'origine del
        # RuntimeError "no season derivable" che faceva fallire create_society).
        # Il ruolo PRESIDENT e' ora derivato a runtime in permissions.get_roles.
        seasonless_sport = Sport.objects.create(
            name='Sport Senza Stagione', slug='zz-noseason-sport',
        )
        seasonless_society = Society.objects.create(
            name='No Season FC', slug='zz-no-season-fc',
            sport=seasonless_sport, city='Roma',
        )
        prez = User.objects.create_user(username='prez', role='president')
        profile = prez.president_profile

        profile.managed_society = seasonless_society
        profile.save()  # non deve sollevare RuntimeError

        self.assertFalse(
            Membership.objects.filter(user=prez, role='PRESIDENT').exists()
        )

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
            identity_status='VERIFIED', onboarding_payment_done=True,
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

    def test_existing_membership_same_season_not_overwritten(self):
        # Membership preesistente con la *stessa* season che il sito deriverebbe
        # (self.season, via team.league). Con il lookup season-aware (2d-4b) il
        # get_or_create la ritrova (created=False) e i defaults — season inclusa
        # — sono ignorati: la riga non viene toccata.
        existing = Membership.objects.create(
            user=self.user, society=self.society, team=self.team,
            role='PLAYER', season=self.season,
        )
        ActivationCode.objects.create(
            code='IDEM-1', society=self.society, team=self.team,
            role='PLAYER', max_uses=5, current_uses=0, is_active=True,
        )

        ok, membership, err = redeem_activation_code(self.user, 'IDEM-1')

        self.assertTrue(ok)
        self.assertEqual(membership.pk, existing.pk)
        existing.refresh_from_db()
        self.assertEqual(existing.season, self.season)  # invariata
        self.assertEqual(
            Membership.objects.filter(
                user=self.user, society=self.society, team=self.team,
                role='PLAYER',
            ).count(),
            1,
        )


class MembershipLookupSeasonAwareTests(TestCase):
    """Fetta 2d-4b (rivista in 2d-7): season nel *lookup* del get_or_create.

    Copre i tre comportamenti chiave:
      - idempotenza stessa-season: due chiamate, stessa season derivata -> 1 riga;
      - rollover: stessa (user,society,team,role) ma season diversa -> 2 righe
        distinte (la chiave 5-field 2d-4a le separa);
      - season non derivabile: fail-fast esplicito (niente righe NULL, vietate
        dal NOT NULL di 2d-7).
    """

    def setUp(self):
        self.sport = Sport.objects.create(name="Pallanuoto", slug="pn")
        self.society = Society.objects.create(
            name="Pro Recco", slug="pro-recco", sport=self.sport, city="Recco"
        )
        self.user = User.objects.create_user(username='athlete1', role='athlete')

    # ── idempotenza: stessa season derivata -> una sola riga ─────────────────

    def test_redeem_twice_same_season_single_row(self):
        # Team senza lega + unica Season is_current -> fallback deterministico:
        # entrambi i redeem derivano la stessa season, quindi il lookup
        # season-aware ritrova la riga (created=False) e non duplica.
        Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )
        team = Team.objects.create(
            society=self.society, slug='t-idem', league=None
        )
        ActivationCode.objects.create(
            code='IDEM-2', society=self.society, team=team,
            role='PLAYER', max_uses=5, current_uses=0, is_active=True,
        )

        ok1, m1, _ = redeem_activation_code(self.user, 'IDEM-2')
        ok2, m2, _ = redeem_activation_code(self.user, 'IDEM-2')

        self.assertTrue(ok1 and ok2)
        self.assertEqual(m1.pk, m2.pk)
        self.assertEqual(
            Membership.objects.filter(
                user=self.user, society=self.society, team=team, role='PLAYER',
            ).count(),
            1,
        )

    # ── rollover: season diversa -> riga distinta ────────────────────────────

    def test_rollover_different_season_two_rows(self):
        # Primo redeem deriva la season corrente A; poi A smette di essere
        # corrente e diventa corrente B. Un secondo redeem sullo stesso
        # (user,society,team,role) deriva B: il lookup 5-field non trova la riga
        # con season=A e ne crea una nuova (comportamento voluto della chiave).
        season_a = Season.objects.create(
            sport=self.sport, label='2024/2025', is_current=True
        )
        team = Team.objects.create(
            society=self.society, slug='t-roll', league=None
        )
        ActivationCode.objects.create(
            code='ROLL-1', society=self.society, team=team,
            role='PLAYER', max_uses=5, current_uses=0, is_active=True,
        )

        ok1, m1, _ = redeem_activation_code(self.user, 'ROLL-1')
        self.assertTrue(ok1)
        self.assertEqual(m1.season, season_a)

        # rollover di stagione
        season_a.is_current = False
        season_a.save(update_fields=['is_current'])
        season_b = Season.objects.create(
            sport=self.sport, label='2025/2026', is_current=True
        )

        ok2, m2, _ = redeem_activation_code(self.user, 'ROLL-1')
        self.assertTrue(ok2)
        self.assertEqual(m2.season, season_b)

        self.assertNotEqual(m1.pk, m2.pk)
        self.assertEqual(
            Membership.objects.filter(
                user=self.user, society=self.society, team=team, role='PLAYER',
            ).count(),
            2,
        )

    # ── season non derivabile: fail-fast esplicito (2d-7) ────────────────────

    def test_season_not_derivable_redeem_fails_cleanly(self):
        # Nessuna Season is_current per lo sport e team senza lega -> resolve
        # ritorna None. Dal flip NOT NULL il redeem NON crea righe season=NULL:
        # fallisce con messaggio utente e nessuna Membership viene creata.
        team = Team.objects.create(
            society=self.society, slug='t-none', league=None
        )
        self.assertIsNone(
            resolve_membership_season(self.user, self.society, team, 'PLAYER')
        )
        code = ActivationCode.objects.create(
            code='NONE-1', society=self.society, team=team,
            role='PLAYER', max_uses=5, current_uses=0, is_active=True,
        )

        ok, membership, err = redeem_activation_code(self.user, 'NONE-1')

        self.assertFalse(ok)
        self.assertIsNone(membership)
        self.assertIn("Stagione corrente non configurata", err)
        self.assertFalse(Membership.objects.filter(user=self.user).exists())
        code.refresh_from_db()
        self.assertEqual(code.current_uses, 0)  # uso non consumato

    def test_season_not_derivable_signal_raises(self):
        # Il path signal (save del profilo) e' fail-fast: misconfigurazione
        # da sanare, non un flusso utente — RuntimeError esplicito.
        team = Team.objects.create(
            society=self.society, slug='t-none-2', league=None
        )
        profile = self.user.athlete_profile
        profile.current_team = team

        with self.assertRaises(RuntimeError):
            profile.save()
