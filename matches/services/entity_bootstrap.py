"""
Entity Bootstrap Service
Guided, explicit creation of missing Team/Match entities for the review flow.
No silent automation — everything is preview-first, admin-triggered.
"""
import logging
from typing import Dict, List, Tuple, Optional
from django.utils.text import slugify
from core.models import Team, League, Sport, Society
from matches.models import Match

logger = logging.getLogger(__name__)


class EntityBootstrapService:
    """
    Detects missing entities required for a MatchReport review/publish cycle.
    Provides preview (what WILL be created) and explicit creation (admin-triggered).
    """

    @staticmethod
    def detect_missing(normalized_data: dict, match: Match) -> Dict:
        """
        Analyze normalized_data.match_info and compare with current Match.
        Returns a structured dict describing what's missing or mismatched.
        """
        match_info = normalized_data.get("match_info", {})
        ocr_home = (match_info.get("home_team") or "").strip()
        ocr_away = (match_info.get("away_team") or "").strip()

        result = {
            "ocr_home_name": ocr_home,
            "ocr_away_name": ocr_away,
            "current_home": match.home_team,
            "current_away": match.away_team,
            "home_needs_update": False,
            "away_needs_update": False,
            "home_candidates": [],
            "away_candidates": [],
            "home_ambiguous": False,
            "away_ambiguous": False,
            "has_issues": False,
        }

        if not ocr_home and not ocr_away:
            return result

        # Check home team
        if ocr_home:
            result["home_candidates"] = list(
                Team.objects.filter(name__iexact=ocr_home)
            )
            if match.home_team.name.lower() != ocr_home.lower():
                result["home_needs_update"] = True
                result["has_issues"] = True
                if len(result["home_candidates"]) > 1:
                    result["home_ambiguous"] = True

        # Check away team
        if ocr_away:
            result["away_candidates"] = list(
                Team.objects.filter(name__iexact=ocr_away)
            )
            if match.away_team.name.lower() != ocr_away.lower():
                result["away_needs_update"] = True
                result["has_issues"] = True
                if len(result["away_candidates"]) > 1:
                    result["away_ambiguous"] = True

        return result

    @staticmethod
    def preview_creation(normalized_data: dict, match: Match) -> Dict:
        """
        Returns a preview of what will be created/updated.
        No side effects — purely informational.
        """
        detection = EntityBootstrapService.detect_missing(normalized_data, match)
        preview = {
            "detection": detection,
            "has_issues": detection["has_issues"],
            "will_create_teams": [],
            "will_reuse_teams": [],
            "will_update_match": False,
            "warnings": [],
            "blocked": False,
        }

        if not detection["has_issues"]:
            return preview

        sport = match.league.sport if match.league else None
        if not sport:
            preview["warnings"].append(
                "Nessuno Sport associato al campionato. Impossibile creare team."
            )
            preview["blocked"] = True
            return preview

        for side in ["home", "away"]:
            ocr_name = detection[f"ocr_{side}_name"]
            needs_update = detection[f"{side}_needs_update"]
            candidates = detection[f"{side}_candidates"]
            ambiguous = detection[f"{side}_ambiguous"]

            if not needs_update or not ocr_name:
                continue

            if ambiguous:
                preview["warnings"].append(
                    f"Squadra '{ocr_name}' ({side.upper()}): "
                    f"trovati {len(candidates)} team con lo stesso nome. "
                    f"Risolvi manualmente."
                )
                preview["blocked"] = True
            elif len(candidates) == 1:
                preview["will_reuse_teams"].append({
                    "side": side,
                    "name": ocr_name,
                    "existing_team": candidates[0],
                })
                preview["will_update_match"] = True
            else:
                # No existing team — will create Society + Team
                preview["will_create_teams"].append({
                    "side": side,
                    "name": ocr_name,
                    "sport": sport.name,
                })
                preview["will_update_match"] = True

        return preview

    @staticmethod
    def execute_bootstrap(
        normalized_data: dict, match: Match, user=None
    ) -> Tuple[bool, str, List[str]]:
        """
        Execute the bootstrap: create missing teams, update match.
        Returns: (success, message, warnings)
        """
        preview = EntityBootstrapService.preview_creation(normalized_data, match)

        if preview["blocked"]:
            return False, "Bootstrap bloccato per ambiguità.", preview["warnings"]

        if not preview["will_create_teams"] and not preview["will_reuse_teams"]:
            return True, "Nessuna entità da creare.", []

        sport = match.league.sport
        created_names = []
        reused_names = []
        warnings = []

        for item in preview["will_create_teams"]:
            side = item["side"]
            name = item["name"]

            # Double-check: still doesn't exist? (guard against race)
            existing = Team.objects.filter(name__iexact=name)
            if existing.count() == 1:
                # Race: appeared between preview and execute
                team = existing.first()
                reused_names.append(f"{name} ({side})")
            elif existing.count() > 1:
                warnings.append(
                    f"Ambiguità per '{name}': più team trovati. Saltato."
                )
                continue
            else:
                # Create minimal Society + Team
                base_slug = slugify(name)
                # Ensure unique slug
                slug = base_slug
                counter = 1
                while Society.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1

                society = Society.objects.create(
                    name=name,
                    slug=slug,
                    sport=sport,
                    city="(da completare)",
                    setup_completed=False,
                )
                team = Team.objects.create(
                    society=society,
                    name=name,
                    league=match.league,
                )
                created_names.append(f"{name} ({side})")
                logger.info(
                    f"Bootstrap: created Society '{society.name}' + "
                    f"Team '{team.name}' for {side}"
                )

            # Update match
            if side == "home":
                match.home_team = team
            else:
                match.away_team = team

        for item in preview["will_reuse_teams"]:
            side = item["side"]
            team = item["existing_team"]
            reused_names.append(f"{team.name} ({side})")
            if side == "home":
                match.home_team = team
            else:
                match.away_team = team

        match.save(update_fields=["home_team", "away_team"])

        parts = []
        if created_names:
            parts.append(f"Creati: {', '.join(created_names)}")
        if reused_names:
            parts.append(f"Riutilizzati: {', '.join(reused_names)}")

        msg = ". ".join(parts) + ". Match aggiornato."
        return True, msg, warnings
