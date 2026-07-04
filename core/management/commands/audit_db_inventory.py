"""
Read-only DB inventory before cleanup.

Stampa (testo o JSON) un inventario completo del database di sviluppo per
distinguere dati di test, pilot reali e seed legittimi PRIMA di toccare
qualsiasi cosa. Nessuna scrittura.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Min
from django.utils import timezone

from accounts.models import (
    AccountProfileLink,
    AthleteProfile,
    CoachProfile,
    PresidentProfile,
    RefereeProfile,
)
from core.models import League, Society, Sport, Team
from management.models import (
    ActivationCode,
    AuditLog,
    ChatMessage,
    Comment,
    Convocation,
    ConvocationNominee,
    Membership,
    MembershipRequest,
    PilotBug,
    PilotDailyLog,
    PilotFeedback,
    PilotReview,
    Post,
    Training,
    TrainingAttendance,
    TrainingOccurrence,
)
from matches.models import (
    AIQueryLog,
    InboundEmail,
    Match,
    MatchEvent,
    MatchReport,
    MatchReportAuditLog,
    OCRRawResponse,
)

try:
    from seasons.models import SeasonArchive
except Exception:
    SeasonArchive = None  # type: ignore


User = get_user_model()


# ---------------------------------------------------------------- patterns
TEST_NAME_PATTERN = re.compile(
    r"\b(test|prova|demo|fake|esempio|pippo|pluto|paperino|sample)\b",
    re.IGNORECASE,
)
TEST_EMAIL_DOMAINS = ("@test.com", "@example.com", "@localhost", "@2salti.local")
SEP = "=" * 78
SUBSEP = "-" * 78


def is_test_name(name: str | None) -> bool:
    if not name:
        return False
    return bool(TEST_NAME_PATTERN.search(name))


def is_test_email(email: str | None) -> bool:
    if not email:
        return False
    e = email.lower().strip()
    return any(e.endswith(d) for d in TEST_EMAIL_DOMAINS)


def trunc(s: str | None, n: int = 80) -> str:
    if s is None:
        return ""
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


class Command(BaseCommand):
    help = "Audit read-only completo del DB per pianificare la pulizia (test vs pilot vs seed)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output JSON strutturato invece che testo.",
        )

    # ==================================================================
    # Collectors per sezione (ritornano dict serializzabili)
    # ==================================================================

    def collect_sports(self) -> dict:
        rows = []
        for s in Sport.objects.all().order_by("id"):
            rows.append({
                "id": s.id,
                "name": s.name,
                "slug": s.slug,
                "period_label": s.period_label,
                "point_system": s.point_system,
                "leagues_count": s.leagues.count(),
            })
        return {"total": Sport.objects.count(), "items": rows}

    def collect_societies(self) -> dict:
        rows = []
        for soc in Society.objects.all().order_by("id"):
            rows.append({
                "id": soc.id,
                "name": soc.name,
                "sport": soc.sport.name if soc.sport_id else None,
                "setup_completed": soc.setup_completed,
                "sponsors_truncated": trunc(json.dumps(soc.sponsors, ensure_ascii=False), 60),
                "teams_count": soc.teams.count(),
                "active_memberships_count": Membership.objects.filter(
                    society=soc, is_active=True
                ).count(),
                "users_linked_count": User.objects.filter(
                    memberships__society=soc, memberships__is_active=True
                ).distinct().count(),
                "is_test_name": is_test_name(soc.name),
            })
        return {"total": Society.objects.count(), "items": rows}

    def collect_teams(self) -> dict:
        rows = []
        for t in Team.objects.select_related("society", "league").all().order_by("id"):
            rows.append({
                "id": t.id,
                "name": t.name,
                "society": t.society.name if t.society_id else None,
                "league": t.league.name if t.league_id else None,
                "category": t.league.league_type if t.league_id else None,
                "active_memberships_count": t.memberships.filter(is_active=True).count(),
                "matches_as_home": t.home_matches.count(),
                "matches_as_away": t.away_matches.count(),
                "is_test_name": is_test_name(t.name) or is_test_name(t.society.name if t.society_id else None),
            })
        return {"total": Team.objects.count(), "items": rows}

    def collect_leagues(self) -> dict:
        rows = []
        for lg in League.objects.select_related("sport").all().order_by("id"):
            rows.append({
                "id": lg.id,
                "name": lg.name,
                "sport": lg.sport.name if lg.sport_id else None,
                "season": lg.season,
                "level": lg.level,
                "teams_count": lg.teams.count(),
                "matches_count": lg.matches.count(),
                "league_standings_count": lg.persisted_standings.count(),
                "is_test_name": is_test_name(lg.name),
            })
        return {"total": League.objects.count(), "items": rows}

    def collect_users(self) -> dict:
        rows = []
        recent_cutoff = timezone.now() - timedelta(days=30)
        for u in User.objects.all().order_by("id"):
            flags = []
            if is_test_name(u.username) or is_test_email(u.email):
                flags.append("TEST?")
            if u.is_superuser:
                flags.append("SUPERUSER")
            if u.is_staff and not u.is_superuser:
                flags.append("STAFF")
            if u.last_login is None:
                flags.append("NEVER_LOGGED_IN")
            elif u.last_login >= recent_cutoff:
                flags.append("RECENT_LOGIN_30D")

            rows.append({
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "staff_role": u.staff_role,
                "is_active": u.is_active,
                "is_staff": u.is_staff,
                "is_superuser": u.is_superuser,
                "date_joined": u.date_joined.isoformat() if u.date_joined else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "identity_status": u.identity_status,
                "onboarding_payment_done": u.onboarding_payment_done,
                "plan": u.plan,
                "setup_completed": u.setup_completed,
                "onboarding_state": u.onboarding_state,
                "active_memberships_count": u.memberships.filter(is_active=True).count(),
                "profile_links_count": u.profile_links.count(),
                "flags": flags,
            })
        return {"total": User.objects.count(), "items": rows}

    def collect_profiles(self) -> dict:
        def _flag_user(user):
            if not user:
                return False
            return is_test_name(user.username) or is_test_email(user.email)

        athletes = []
        for p in AthleteProfile.objects.select_related("user", "current_team").all().order_by("id"):
            athletes.append({
                "id": p.id,
                "user": p.user.username if p.user_id else None,
                "current_team": p.current_team.name if p.current_team_id else None,
                "total_goals": p.total_goals,
                "total_matches": p.total_matches,
                "total_expulsions": p.total_expulsions,
                "is_test_name": _flag_user(p.user) if p.user_id else False,
            })
        coaches = []
        for p in CoachProfile.objects.select_related("user", "current_team").all().order_by("id"):
            coaches.append({
                "id": p.id,
                "user": p.user.username if p.user_id else None,
                "current_team": p.current_team.name if p.current_team_id else None,
                "specialization": p.specialization,
                "is_test_name": _flag_user(p.user) if p.user_id else False,
            })
        referees = []
        for p in RefereeProfile.objects.select_related("user").all().order_by("id"):
            referees.append({
                "id": p.id,
                "user": p.user.username if p.user_id else None,
                "license_level": p.license_level,
                "total_matches_officiated": p.total_matches_officiated,
                "is_test_name": _flag_user(p.user) if p.user_id else False,
            })
        presidents = []
        for p in PresidentProfile.objects.select_related("user", "managed_society").all().order_by("id"):
            presidents.append({
                "id": p.id,
                "user": p.user.username if p.user_id else None,
                "managed_society": p.managed_society.name if p.managed_society_id else None,
                "is_test_name": _flag_user(p.user) if p.user_id else False,
            })
        return {
            "athletes": {"total": AthleteProfile.objects.count(), "items": athletes},
            "coaches": {"total": CoachProfile.objects.count(), "items": coaches},
            "referees": {"total": RefereeProfile.objects.count(), "items": referees},
            "presidents": {"total": PresidentProfile.objects.count(), "items": presidents},
        }

    def collect_matches(self) -> dict:
        rows = []
        for m in Match.objects.select_related("home_team", "away_team", "league").all().order_by("id"):
            reports = list(m.reports.all().values("id", "status"))
            rows.append({
                "id": m.id,
                "date": m.match_date.isoformat() if m.match_date else None,
                "home_team": m.home_team.name if m.home_team_id else None,
                "away_team": m.away_team.name if m.away_team_id else None,
                "league": m.league.name if m.league_id else None,
                "home_score": m.home_score,
                "away_score": m.away_score,
                "is_finished": m.is_finished,
                "has_report": m.has_report,
                "is_public": m.is_public,
                "reports_count": len(reports),
                "reports": reports,
                "events_count": m.events.count(),
            })
        return {"total": Match.objects.count(), "items": rows}

    def collect_match_reports(self) -> dict:
        by_status = dict(
            MatchReport.objects.values_list("status").annotate(c=Count("id")).values_list("status", "c")
        )
        non_final_statuses = ["DRAFT", "UPLOADED", "PROCESSING", "EXTRACTED", "NEEDS_REVIEW"]
        non_final_items = []
        for r in MatchReport.objects.filter(status__in=non_final_statuses).select_related("uploader").order_by("id"):
            non_final_items.append({
                "id": r.id,
                "match_id": r.match_id,
                "status": r.status,
                "source_channel": r.source_channel,
                "source_type": r.source_type,
                "uploader": r.uploader.username if r.uploader_id else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        published_total = by_status.get("PUBLISHED", 0)
        published_recent = []
        for r in MatchReport.objects.filter(status="PUBLISHED").order_by("-published_at", "-id")[:5]:
            published_recent.append({
                "id": r.id,
                "match_id": r.match_id,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "uploader": r.uploader.username if r.uploader_id else None,
            })
        rejected_items = []
        for r in MatchReport.objects.filter(status="REJECTED").select_related("uploader").order_by("id"):
            rejected_items.append({
                "id": r.id,
                "match_id": r.match_id,
                "source_channel": r.source_channel,
                "uploader": r.uploader.username if r.uploader_id else None,
                "internal_notes": trunc(r.internal_notes, 120),
                "validation_notes": trunc(r.validation_notes, 120),
            })
        return {
            "total": MatchReport.objects.count(),
            "by_status": by_status,
            "non_final": non_final_items,
            "published_recent_5": published_recent,
            "published_total": published_total,
            "rejected": rejected_items,
        }

    def collect_memberships(self) -> dict:
        active_qs = Membership.objects.filter(is_active=True).select_related("user", "society", "team")
        active_items = []
        for mb in active_qs.order_by("id"):
            active_items.append({
                "id": mb.id,
                "user": mb.user.username if mb.user_id else None,
                "society": mb.society.name if mb.society_id else None,
                "team": mb.team.name if mb.team_id else None,
                "role": mb.role,
                "created_at": mb.created_at.isoformat() if mb.created_at else None,
                "is_test_name": (
                    is_test_name(mb.user.username if mb.user_id else None)
                    or is_test_name(mb.society.name if mb.society_id else None)
                ),
            })
        return {
            "total": Membership.objects.count(),
            "active_total": active_qs.count(),
            "active_items": active_items,
        }

    def collect_activation_codes(self) -> dict:
        rows = []
        now = timezone.now()
        for ac in ActivationCode.objects.select_related("society").all().order_by("id"):
            expired = bool(ac.expires_at and ac.expires_at < now)
            rows.append({
                "id": ac.id,
                "code": ac.code,
                "society": ac.society.name if ac.society_id else None,
                "role": ac.role,
                "max_uses": ac.max_uses,
                "current_uses": ac.current_uses,
                "expires_at": ac.expires_at.isoformat() if ac.expires_at else None,
                "is_active": ac.is_active,
                "expired": expired,
                "never_used": ac.current_uses == 0,
            })
        return {"total": ActivationCode.objects.count(), "items": rows}

    def collect_membership_requests(self) -> dict:
        by_status = dict(
            MembershipRequest.objects.values_list("status").annotate(c=Count("id")).values_list("status", "c")
        )
        pending = []
        for mr in MembershipRequest.objects.filter(status="PENDING").select_related(
            "user", "society", "team"
        ).order_by("id"):
            pending.append({
                "id": mr.id,
                "user": mr.user.username if mr.user_id else None,
                "society": mr.society.name if mr.society_id else None,
                "team": mr.team.name if mr.team_id else None,
                "role": mr.role,
                "created_at": mr.created_at.isoformat() if mr.created_at else None,
            })
        cutoff = timezone.now() - timedelta(days=30)
        approved_recent = []
        for mr in MembershipRequest.objects.filter(
            status="APPROVED", updated_at__gte=cutoff
        ).select_related("user", "society", "team").order_by("-updated_at"):
            approved_recent.append({
                "id": mr.id,
                "user": mr.user.username if mr.user_id else None,
                "society": mr.society.name if mr.society_id else None,
                "team": mr.team.name if mr.team_id else None,
                "updated_at": mr.updated_at.isoformat() if mr.updated_at else None,
            })
        return {
            "total": MembershipRequest.objects.count(),
            "by_status": by_status,
            "pending": pending,
            "approved_last_30d": approved_recent,
        }

    def collect_account_profile_links(self) -> dict:
        by_status = dict(
            AccountProfileLink.objects.values_list("status").annotate(c=Count("id")).values_list("status", "c")
        )
        rows = []
        for lk in AccountProfileLink.objects.select_related(
            "user", "athlete_profile__user", "coach_profile__user", "referee_profile__user"
        ).all().order_by("id"):
            target = None
            if lk.athlete_profile_id:
                target = f"athlete:{lk.athlete_profile.user.username}"
            elif lk.coach_profile_id:
                target = f"coach:{lk.coach_profile.user.username}"
            elif lk.referee_profile_id:
                target = f"referee:{lk.referee_profile.user.username}"
            rows.append({
                "id": lk.id,
                "user": lk.user.username if lk.user_id else None,
                "target_profile": target,
                "status": lk.status,
                "created_at": lk.created_at.isoformat() if lk.created_at else None,
            })
        return {
            "total": AccountProfileLink.objects.count(),
            "by_status": by_status,
            "items": rows,
        }

    def collect_pilot(self) -> dict:
        # Pilot daily log
        pdl_by_status = dict(
            PilotDailyLog.objects.values_list("status").annotate(c=Count("id")).values_list("status", "c")
        )
        agg = PilotDailyLog.objects.aggregate(oldest=Min("date"), newest=Max("date"))
        pilot_daily_log = {
            "total": PilotDailyLog.objects.count(),
            "by_status": pdl_by_status,
            "oldest_date": agg["oldest"].isoformat() if agg["oldest"] else None,
            "newest_date": agg["newest"].isoformat() if agg["newest"] else None,
        }

        bug_by_status = dict(
            PilotBug.objects.values_list("status").annotate(c=Count("id")).values_list("status", "c")
        )
        bug_by_severity = dict(
            PilotBug.objects.values_list("severity").annotate(c=Count("id")).values_list("severity", "c")
        )
        pilot_bug = {
            "total": PilotBug.objects.count(),
            "by_status": bug_by_status,
            "by_severity": bug_by_severity,
        }

        fb_by_status = dict(
            PilotFeedback.objects.values_list("status").annotate(c=Count("id")).values_list("status", "c")
        )
        pilot_feedback = {
            "total": PilotFeedback.objects.count(),
            "by_status": fb_by_status,
        }

        pr_items = []
        for pr in PilotReview.objects.order_by("-review_date")[:3]:
            pr_items.append({
                "id": pr.id,
                "review_date": pr.review_date.isoformat() if pr.review_date else None,
                "review_type": pr.review_type,
                "recommendation": pr.recommendation,
            })
        pilot_review = {
            "total": PilotReview.objects.count(),
            "last_3": pr_items,
        }

        return {
            "pilot_daily_log": pilot_daily_log,
            "pilot_bug": pilot_bug,
            "pilot_feedback": pilot_feedback,
            "pilot_review": pilot_review,
        }

    def collect_audit_entities(self) -> dict:
        # AuditLog: top 10 actions
        top_actions = list(
            AuditLog.objects.values("action").annotate(c=Count("id")).order_by("-c")[:10]
        )
        match_audit_actions = dict(
            MatchReportAuditLog.objects.values_list("action")
            .annotate(c=Count("id"))
            .values_list("action", "c")
        )
        return {
            "audit_log": {
                "total": AuditLog.objects.count(),
                "top_actions": top_actions,
            },
            "match_report_audit_log": {
                "total": MatchReportAuditLog.objects.count(),
                "by_action": match_audit_actions,
            },
        }

    def collect_other(self) -> dict:
        ocr_total = OCRRawResponse.objects.count()
        # JSON size approx: sum char lengths of raw_response (cast to text)
        ocr_size_mb = None
        try:
            # Pull a sample sum to estimate. For sqlite we can iterate; for large DB
            # this can be slow, but DB di sviluppo è piccolo.
            total_chars = 0
            for r in OCRRawResponse.objects.all().iterator():
                try:
                    total_chars += len(json.dumps(r.raw_response, default=str))
                except Exception:
                    pass
            ocr_size_mb = round(total_chars / (1024 * 1024), 3)
        except Exception:
            ocr_size_mb = None

        inbound_total = InboundEmail.objects.count()

        season_archive_total = SeasonArchive.objects.count() if SeasonArchive else 0

        return {
            "inbound_email": {
                "total": inbound_total,
                "processed_with_success": inbound_total,  # tutti i record qui significano "elaborato"
            },
            "ocr_raw_response": {
                "total": ocr_total,
                "estimated_size_mb": ocr_size_mb,
            },
            "ai_query_log": {"total": AIQueryLog.objects.count()},
            "training": {"total": Training.objects.count()},
            "training_occurrence": {"total": TrainingOccurrence.objects.count()},
            "training_attendance": {"total": TrainingAttendance.objects.count()},
            "convocation": {"total": Convocation.objects.count()},
            "convocation_nominee": {"total": ConvocationNominee.objects.count()},
            "post": {"total": Post.objects.count()},
            "comment": {"total": Comment.objects.count()},
            "chat_message": {"total": ChatMessage.objects.count()},
            "season_archive": {"total": season_archive_total},
        }

    # ==================================================================
    # Cleanup candidates (riepilogo finale)
    # ==================================================================

    def build_cleanup_candidates(self, sections: dict) -> dict:
        """Costruisce le tre liste A/B/C sulla base dei dati già raccolti."""
        # Map id -> info per User
        users_by_id = {u["id"]: u for u in sections["users"]["items"]}
        societies_by_id = {s["id"]: s for s in sections["societies"]["items"]}
        teams_by_id = {t["id"]: t for t in sections["teams"]["items"]}
        leagues_by_id = {lg["id"]: lg for lg in sections["leagues"]["items"]}
        matches_by_id = {m["id"]: m for m in sections["matches"]["items"]}

        # quale Society/Team/League ospita almeno un match PUBLISHED?
        societies_with_published: set[int] = set()
        teams_with_published: set[int] = set()
        leagues_with_published: set[int] = set()
        for m in matches_by_id.values():
            has_published = any(r["status"] == "PUBLISHED" for r in m["reports"])
            if not has_published:
                continue
            if m.get("league"):
                # serve risalire via id: lo facciamo direttamente sul DB
                pass
        # Più semplice: rifacciamo via DB
        published_match_ids = list(
            MatchReport.objects.filter(status="PUBLISHED").values_list("match_id", flat=True).distinct()
        )
        published_matches = Match.objects.filter(id__in=published_match_ids).values(
            "league_id", "home_team_id", "away_team_id"
        )
        team_to_society: dict[int, int] = dict(Team.objects.values_list("id", "society_id"))
        for pm in published_matches:
            leagues_with_published.add(pm["league_id"])
            for tid in (pm["home_team_id"], pm["away_team_id"]):
                if tid:
                    teams_with_published.add(tid)
                    sid = team_to_society.get(tid)
                    if sid:
                        societies_with_published.add(sid)

        # A. CERTAMENTE TEST
        a_users = [
            u for u in users_by_id.values()
            if ("TEST?" in u["flags"]) and ("NEVER_LOGGED_IN" in u["flags"]) and (not u["is_superuser"])
        ]
        a_societies = [
            s for s in societies_by_id.values()
            if s["is_test_name"] and s["active_memberships_count"] == 0
            and s["id"] not in societies_with_published
        ]
        a_teams = [
            t for t in teams_by_id.values()
            if t["is_test_name"] and t["active_memberships_count"] == 0
            and t["id"] not in teams_with_published
        ]
        a_leagues = [
            lg for lg in leagues_by_id.values()
            if lg["is_test_name"] and lg["id"] not in leagues_with_published
        ]
        a_matches = []
        for m in matches_by_id.values():
            statuses = {r["status"] for r in m["reports"]}
            if not statuses:
                a_matches.append(m)
            elif statuses and statuses.issubset({"REJECTED"}):
                a_matches.append(m)

        # B. PROBABILMENTE TEST
        b_users = [
            u for u in users_by_id.values()
            if ("TEST?" in u["flags"]) and ("NEVER_LOGGED_IN" not in u["flags"])
            and (not u["is_superuser"])
        ]
        b_societies = [
            s for s in societies_by_id.values()
            if s["is_test_name"] and (
                s["active_memberships_count"] > 0 or s["id"] in societies_with_published
            )
        ]
        b_teams = [
            t for t in teams_by_id.values()
            if t["is_test_name"] and (
                t["active_memberships_count"] > 0 or t["id"] in teams_with_published
            )
        ]
        b_leagues = [
            lg for lg in leagues_by_id.values()
            if lg["is_test_name"] and lg["id"] in leagues_with_published
        ]
        non_final_statuses = {"PROCESSING", "EXTRACTED", "NEEDS_REVIEW", "UPLOADED", "DRAFT"}
        b_matches = []
        for m in matches_by_id.values():
            statuses = {r["status"] for r in m["reports"]}
            if statuses & non_final_statuses:
                b_matches.append(m)

        # C. NON TOCCARE
        c_superusers = [u for u in users_by_id.values() if u["is_superuser"]]
        c_recent_login = [u for u in users_by_id.values() if "RECENT_LOGIN_30D" in u["flags"]]
        c_matches_published = [
            m for m in matches_by_id.values()
            if any(r["status"] == "PUBLISHED" for r in m["reports"])
        ]
        c_societies = [societies_by_id[i] for i in societies_with_published if i in societies_by_id]
        c_teams = [teams_by_id[i] for i in teams_with_published if i in teams_by_id]
        c_leagues = [leagues_by_id[i] for i in leagues_with_published if i in leagues_by_id]

        def slim_user(u):
            return {"id": u["id"], "username": u["username"], "email": u["email"],
                    "role": u["role"], "flags": u["flags"]}

        def slim_entity(e, keys=("id", "name")):
            return {k: e.get(k) for k in keys}

        def slim_match(m):
            return {
                "id": m["id"], "date": m["date"],
                "home": m["home_team"], "away": m["away_team"],
                "league": m["league"], "reports": m["reports"],
            }

        return {
            "A_certamente_test": {
                "users": [slim_user(u) for u in a_users],
                "societies": [slim_entity(s) for s in a_societies],
                "teams": [slim_entity(t) for t in a_teams],
                "leagues": [slim_entity(lg) for lg in a_leagues],
                "matches": [slim_match(m) for m in a_matches],
            },
            "B_probabilmente_test": {
                "users": [slim_user(u) for u in b_users],
                "societies": [slim_entity(s) for s in b_societies],
                "teams": [slim_entity(t) for t in b_teams],
                "leagues": [slim_entity(lg) for lg in b_leagues],
                "matches_non_final_reports": [slim_match(m) for m in b_matches],
            },
            "C_non_toccare": {
                "superusers": [slim_user(u) for u in c_superusers],
                "users_logged_in_last_30d": [slim_user(u) for u in c_recent_login],
                "matches_with_published_report": [slim_match(m) for m in c_matches_published],
                "societies_with_published_match": [slim_entity(s) for s in c_societies],
                "teams_with_published_match": [slim_entity(t) for t in c_teams],
                "leagues_with_published_match": [slim_entity(lg) for lg in c_leagues],
                "pilot_logs_are_protected": True,
            },
        }

    # ==================================================================
    # Renderer testuale
    # ==================================================================

    def render_text(self, data: dict) -> str:
        L: list[str] = []

        def H(title):
            L.append("")
            L.append(SEP)
            L.append(title)
            L.append(SEP)

        def sub(title):
            L.append(SUBSEP)
            L.append(title)

        H("DB INVENTORY — READ ONLY")

        # 1 SPORT
        H(f"1. SPORT  (total={data['sports']['total']})")
        for s in data["sports"]["items"]:
            L.append(f"  #{s['id']}  {s['name']}  slug={s['slug']}  "
                     f"period_label={s['period_label']}  point_system={s['point_system']}  "
                     f"leagues={s['leagues_count']}")

        # 2 SOCIETY
        H(f"2. SOCIETY  (total={data['societies']['total']})")
        for s in data["societies"]["items"]:
            tag = " [TEST?]" if s["is_test_name"] else ""
            L.append(f"  #{s['id']}{tag}  {s['name']}  sport={s['sport']}  "
                     f"setup_completed={s['setup_completed']}  teams={s['teams_count']}  "
                     f"active_memberships={s['active_memberships_count']}  "
                     f"users_linked={s['users_linked_count']}")
            if s["sponsors_truncated"] and s["sponsors_truncated"] not in ("[]", "null"):
                L.append(f"      sponsors: {s['sponsors_truncated']}")

        # 3 TEAM
        H(f"3. TEAM  (total={data['teams']['total']})")
        for t in data["teams"]["items"]:
            tag = " [TEST?]" if t["is_test_name"] else ""
            L.append(f"  #{t['id']}{tag}  {t['name']}  society={t['society']}  "
                     f"league={t['league']}  category={t['category']}  "
                     f"memb_active={t['active_memberships_count']}  "
                     f"home_matches={t['matches_as_home']}  away_matches={t['matches_as_away']}")

        # 4 LEAGUE
        H(f"4. LEAGUE  (total={data['leagues']['total']})")
        for lg in data["leagues"]["items"]:
            tag = " [TEST?]" if lg["is_test_name"] else ""
            L.append(f"  #{lg['id']}{tag}  {lg['name']}  sport={lg['sport']}  "
                     f"season={lg['season']}  level={lg['level']}  "
                     f"teams={lg['teams_count']}  matches={lg['matches_count']}  "
                     f"standings_rows={lg['league_standings_count']}")

        # 5 USER
        H(f"5. USER  (total={data['users']['total']})")
        for u in data["users"]["items"]:
            tag = " [" + ",".join(u["flags"]) + "]" if u["flags"] else ""
            L.append(f"  #{u['id']}{tag}  {u['username']}  email={u['email']}  "
                     f"role={u['role']}  staff_role={u['staff_role']}  "
                     f"is_active={u['is_active']}  is_staff={u['is_staff']}  "
                     f"super={u['is_superuser']}")
            L.append(f"      joined={u['date_joined']}  last_login={u['last_login']}  "
                     f"identity={u['identity_status']}  payment_done={u['onboarding_payment_done']}  "
                     f"plan={u['plan']}  setup={u['setup_completed']}  onboarding_state={u['onboarding_state']}")
            L.append(f"      memberships_active={u['active_memberships_count']}  "
                     f"profile_links={u['profile_links_count']}")

        # 6 PROFILES
        H("6. PROFILI (athlete/coach/referee/president)")
        prof = data["profiles"]
        sub(f"AthleteProfile  total={prof['athletes']['total']}")
        for p in prof["athletes"]["items"]:
            tag = " [TEST?]" if p["is_test_name"] else ""
            L.append(f"  #{p['id']}{tag}  user={p['user']}  team={p['current_team']}  "
                     f"goals={p['total_goals']} matches={p['total_matches']} excl={p['total_expulsions']}")
        sub(f"CoachProfile  total={prof['coaches']['total']}")
        for p in prof["coaches"]["items"]:
            tag = " [TEST?]" if p["is_test_name"] else ""
            L.append(f"  #{p['id']}{tag}  user={p['user']}  team={p['current_team']}  "
                     f"spec={p['specialization']}")
        sub(f"RefereeProfile  total={prof['referees']['total']}")
        for p in prof["referees"]["items"]:
            tag = " [TEST?]" if p["is_test_name"] else ""
            L.append(f"  #{p['id']}{tag}  user={p['user']}  level={p['license_level']}  "
                     f"officiated={p['total_matches_officiated']}")
        sub(f"PresidentProfile  total={prof['presidents']['total']}")
        for p in prof["presidents"]["items"]:
            tag = " [TEST?]" if p["is_test_name"] else ""
            L.append(f"  #{p['id']}{tag}  user={p['user']}  managed_society={p['managed_society']}")

        # 7 MATCH
        H(f"7. MATCH  (total={data['matches']['total']})")
        for m in data["matches"]["items"]:
            L.append(f"  #{m['id']}  {m['date']}  {m['home_team']} {m['home_score']}-"
                     f"{m['away_score']} {m['away_team']}  league={m['league']}  "
                     f"is_finished={m['is_finished']}  has_report={m['has_report']}  "
                     f"is_public={m['is_public']}  events={m['events_count']}")
            for r in m["reports"]:
                L.append(f"      report id={r['id']} status={r['status']}")

        # 8 MATCHREPORT
        H(f"8. MATCHREPORT  (total={data['match_reports']['total']})")
        L.append(f"  by_status: {data['match_reports']['by_status']}")
        sub(f"Non-final ({len(data['match_reports']['non_final'])})")
        for r in data["match_reports"]["non_final"]:
            L.append(f"  #{r['id']} match={r['match_id']} status={r['status']} "
                     f"channel={r['source_channel']} type={r['source_type']} "
                     f"uploader={r['uploader']} created={r['created_at']}")
        sub(f"PUBLISHED — total={data['match_reports']['published_total']}, ultimi 5:")
        for r in data["match_reports"]["published_recent_5"]:
            L.append(f"  #{r['id']} match={r['match_id']} published_at={r['published_at']} "
                     f"uploader={r['uploader']}")
        sub(f"REJECTED ({len(data['match_reports']['rejected'])})")
        for r in data["match_reports"]["rejected"]:
            L.append(f"  #{r['id']} match={r['match_id']} channel={r['source_channel']} "
                     f"uploader={r['uploader']}  notes={r['internal_notes']!r}")

        # 9 MEMBERSHIP
        H(f"9. MEMBERSHIP  (total={data['memberships']['total']}, "
          f"active={data['memberships']['active_total']})")
        for mb in data["memberships"]["active_items"]:
            tag = " [TEST?]" if mb["is_test_name"] else ""
            L.append(f"  #{mb['id']}{tag}  user={mb['user']}  society={mb['society']}  "
                     f"team={mb['team']}  role={mb['role']}  joined={mb['created_at']}")

        # 10 ACTIVATION CODE
        H(f"10. ACTIVATION CODE  (total={data['activation_codes']['total']})")
        for ac in data["activation_codes"]["items"]:
            flags = []
            if ac["expired"]:
                flags.append("EXPIRED")
            if ac["never_used"]:
                flags.append("NEVER_USED")
            tag = " [" + ",".join(flags) + "]" if flags else ""
            L.append(f"  #{ac['id']}{tag}  code={ac['code']}  society={ac['society']}  "
                     f"role={ac['role']}  uses={ac['current_uses']}/{ac['max_uses']}  "
                     f"expires={ac['expires_at']}  is_active={ac['is_active']}")

        # 11 MEMBERSHIP REQUEST
        H(f"11. MEMBERSHIP REQUEST  (total={data['membership_requests']['total']})")
        L.append(f"  by_status: {data['membership_requests']['by_status']}")
        sub(f"PENDING ({len(data['membership_requests']['pending'])})")
        for mr in data["membership_requests"]["pending"]:
            L.append(f"  #{mr['id']}  user={mr['user']}  society={mr['society']}  "
                     f"team={mr['team']}  role={mr['role']}  created={mr['created_at']}")
        sub(f"APPROVED ultimi 30gg ({len(data['membership_requests']['approved_last_30d'])})")
        for mr in data["membership_requests"]["approved_last_30d"]:
            L.append(f"  #{mr['id']}  user={mr['user']}  society={mr['society']}  "
                     f"team={mr['team']}  updated_at={mr['updated_at']}")

        # 12 ACCOUNTPROFILELINK
        H(f"12. ACCOUNTPROFILELINK  (total={data['account_profile_links']['total']})")
        L.append(f"  by_status: {data['account_profile_links']['by_status']}")
        for lk in data["account_profile_links"]["items"]:
            L.append(f"  #{lk['id']}  user={lk['user']}  target={lk['target_profile']}  "
                     f"status={lk['status']}  created={lk['created_at']}")

        # 13 PILOT
        H("13. PILOT ENTITIES")
        p = data["pilot"]
        L.append(f"  PilotDailyLog: total={p['pilot_daily_log']['total']}  "
                 f"by_status={p['pilot_daily_log']['by_status']}  "
                 f"oldest={p['pilot_daily_log']['oldest_date']}  "
                 f"newest={p['pilot_daily_log']['newest_date']}")
        L.append(f"  PilotBug:      total={p['pilot_bug']['total']}  "
                 f"by_status={p['pilot_bug']['by_status']}  by_severity={p['pilot_bug']['by_severity']}")
        L.append(f"  PilotFeedback: total={p['pilot_feedback']['total']}  "
                 f"by_status={p['pilot_feedback']['by_status']}")
        L.append(f"  PilotReview:   total={p['pilot_review']['total']}")
        for pr in p["pilot_review"]["last_3"]:
            L.append(f"      #{pr['id']} {pr['review_date']} {pr['review_type']} "
                     f"→ {pr['recommendation']}")

        # 14 AUDIT
        H("14. AUDIT ENTITIES")
        a = data["audit"]
        L.append(f"  AuditLog: total={a['audit_log']['total']}")
        L.append(f"  Top 10 actions:")
        for row in a["audit_log"]["top_actions"]:
            L.append(f"    - {row['action']}: {row['c']}")
        L.append(f"  MatchReportAuditLog: total={a['match_report_audit_log']['total']}  "
                 f"by_action={a['match_report_audit_log']['by_action']}")

        # 15 OTHER
        H("15. ALTRE TABELLE")
        o = data["other"]
        L.append(f"  InboundEmail:        {o['inbound_email']['total']}")
        L.append(f"  OCRRawResponse:      {o['ocr_raw_response']['total']}  "
                 f"(~{o['ocr_raw_response']['estimated_size_mb']} MB)")
        L.append(f"  AIQueryLog:          {o['ai_query_log']['total']}")
        L.append(f"  Training:            {o['training']['total']}")
        L.append(f"  TrainingOccurrence:  {o['training_occurrence']['total']}")
        L.append(f"  TrainingAttendance:  {o['training_attendance']['total']}")
        L.append(f"  Convocation:         {o['convocation']['total']}")
        L.append(f"  ConvocationNominee:  {o['convocation_nominee']['total']}")
        L.append(f"  Post:                {o['post']['total']}")
        L.append(f"  Comment:             {o['comment']['total']}")
        L.append(f"  ChatMessage:         {o['chat_message']['total']}")
        L.append(f"  SeasonArchive:       {o['season_archive']['total']}")

        # 16 CLEANUP SUMMARY
        H("16. SUMMARY CANDIDATI PER PULIZIA")
        c = data["cleanup_candidates"]

        sub("A. CERTAMENTE TEST (sicuri da eliminare)")
        L.append(f"  Users        ({len(c['A_certamente_test']['users'])}):")
        for u in c["A_certamente_test"]["users"]:
            L.append(f"    - #{u['id']} {u['username']} email={u['email']} flags={u['flags']}")
        L.append(f"  Societies    ({len(c['A_certamente_test']['societies'])}):")
        for s in c["A_certamente_test"]["societies"]:
            L.append(f"    - #{s['id']} {s['name']}")
        L.append(f"  Teams        ({len(c['A_certamente_test']['teams'])}):")
        for t in c["A_certamente_test"]["teams"]:
            L.append(f"    - #{t['id']} {t['name']}")
        L.append(f"  Leagues      ({len(c['A_certamente_test']['leagues'])}):")
        for lg in c["A_certamente_test"]["leagues"]:
            L.append(f"    - #{lg['id']} {lg['name']}")
        L.append(f"  Matches (no report or only REJECTED)  "
                 f"({len(c['A_certamente_test']['matches'])}):")
        for m in c["A_certamente_test"]["matches"]:
            L.append(f"    - #{m['id']} {m['home']} vs {m['away']} league={m['league']} "
                     f"reports={m['reports']}")

        sub("B. PROBABILMENTE TEST (da revisionare)")
        L.append(f"  Users        ({len(c['B_probabilmente_test']['users'])}):")
        for u in c["B_probabilmente_test"]["users"]:
            L.append(f"    - #{u['id']} {u['username']} email={u['email']} flags={u['flags']}")
        L.append(f"  Societies    ({len(c['B_probabilmente_test']['societies'])}):")
        for s in c["B_probabilmente_test"]["societies"]:
            L.append(f"    - #{s['id']} {s['name']}")
        L.append(f"  Teams        ({len(c['B_probabilmente_test']['teams'])}):")
        for t in c["B_probabilmente_test"]["teams"]:
            L.append(f"    - #{t['id']} {t['name']}")
        L.append(f"  Leagues      ({len(c['B_probabilmente_test']['leagues'])}):")
        for lg in c["B_probabilmente_test"]["leagues"]:
            L.append(f"    - #{lg['id']} {lg['name']}")
        L.append(f"  Matches con report non-finale  "
                 f"({len(c['B_probabilmente_test']['matches_non_final_reports'])}):")
        for m in c["B_probabilmente_test"]["matches_non_final_reports"]:
            L.append(f"    - #{m['id']} reports={m['reports']}")

        sub("C. NON TOCCARE")
        L.append(f"  Superusers                       ({len(c['C_non_toccare']['superusers'])})")
        for u in c["C_non_toccare"]["superusers"]:
            L.append(f"    - #{u['id']} {u['username']}")
        L.append(f"  Users loggati ultimi 30gg        "
                 f"({len(c['C_non_toccare']['users_logged_in_last_30d'])})")
        for u in c["C_non_toccare"]["users_logged_in_last_30d"]:
            L.append(f"    - #{u['id']} {u['username']}")
        L.append(f"  Match con report PUBLISHED       "
                 f"({len(c['C_non_toccare']['matches_with_published_report'])})")
        L.append(f"  Society con match PUBLISHED      "
                 f"({len(c['C_non_toccare']['societies_with_published_match'])})")
        L.append(f"  Team con match PUBLISHED         "
                 f"({len(c['C_non_toccare']['teams_with_published_match'])})")
        L.append(f"  League con match PUBLISHED       "
                 f"({len(c['C_non_toccare']['leagues_with_published_match'])})")
        L.append(f"  Pilot logs (DailyLog, Bug, Feedback, Review): SEMPRE preservati")

        return "\n".join(L)

    # ==================================================================
    # Entry
    # ==================================================================
    def handle(self, *args, **opts):
        sections = {
            "generated_at": timezone.now().isoformat(),
            "sports": self.collect_sports(),
            "societies": self.collect_societies(),
            "teams": self.collect_teams(),
            "leagues": self.collect_leagues(),
            "users": self.collect_users(),
            "profiles": self.collect_profiles(),
            "matches": self.collect_matches(),
            "match_reports": self.collect_match_reports(),
            "memberships": self.collect_memberships(),
            "activation_codes": self.collect_activation_codes(),
            "membership_requests": self.collect_membership_requests(),
            "account_profile_links": self.collect_account_profile_links(),
            "pilot": self.collect_pilot(),
            "audit": self.collect_audit_entities(),
            "other": self.collect_other(),
        }
        sections["cleanup_candidates"] = self.build_cleanup_candidates(sections)

        if opts["json"]:
            self.stdout.write(json.dumps(sections, indent=2, default=str, ensure_ascii=False))
        else:
            self.stdout.write(self.render_text(sections))
