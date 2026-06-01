"""R-34: Artifact main stat validator — detect incorrect main stats.

Checks equipped artifact main stats against recommended builds.
Detects common mistakes like DPS with Healing Bonus circlet,
support without ER% sands, etc.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from knowledge.genshin_f2p_builds import F2P_BUILDS

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MainStatIssue:
    character_id: str
    slot: str  # "sands", "goblet", "circlet"
    detected_stat: str
    recommended_stat: str
    severity: str  # "error" | "warning"
    reason: str


# Role-based main stat heuristics for when build data is unavailable.
_ROLE_MAIN_STATS: dict[str, dict[str, tuple[str, ...]]] = {
    "dps": {
        "sands": ("ATK%", "EM", "ER%"),
        "goblet": ("DMG%",),
        "circlet": ("CRIT Rate", "CRIT DMG"),
    },
    "main_dps": {
        "sands": ("ATK%", "EM", "DEF%", "HP%"),
        "goblet": ("DMG%",),
        "circlet": ("CRIT Rate", "CRIT DMG"),
    },
    "off_field_dps": {
        "sands": ("ATK%", "EM", "ER%"),
        "goblet": ("DMG%",),
        "circlet": ("CRIT Rate", "CRIT DMG"),
    },
    "support": {
        "sands": ("ER%", "ATK%", "HP%"),
        "goblet": ("DMG%", "HP%"),
        "circlet": ("CRIT Rate", "CRIT DMG", "HB"),
    },
    "healer": {
        "sands": ("HP%", "ER%"),
        "goblet": ("HP%",),
        "circlet": ("HB", "HP%", "CRIT Rate"),
    },
    "shielder": {
        "sands": ("HP%", "DEF%", "ER%"),
        "goblet": ("HP%", "DEF%"),
        "circlet": ("HB", "HP%", "CRIT Rate"),
    },
}

# Stats that should never appear on certain role/slot combos.
_NEVER_STATS: dict[str, dict[str, tuple[str, ...]]] = {
    "dps": {"circlet": ("HB",), "sands": ("HB",)},
    "main_dps": {"circlet": ("HB",), "sands": ("HB",)},
    "off_field_dps": {"circlet": ("HB",), "sands": ("HB",)},
    "healer": {"sands": ("DMG%",), "circlet": ("DMG%",)},
    "shielder": {"sands": ("DMG%",), "circlet": ("DMG%",)},
}


def _parse_main_stats(spec: tuple[str, str, str]) -> dict[str, str]:
    """Parse (sands, goblet, circlet) spec into slot→stat dict."""
    slots = ("sands", "goblet", "circlet")
    result: dict[str, str] = {}
    for slot, stat_spec in zip(slots, spec):
        # Take the first recommended option (before "or")
        primary = stat_spec.split(" or ")[0].strip()
        result[slot] = primary
    return result


def _normalize_stat(stat: str) -> str:
    """Normalize stat name for comparison."""
    s = stat.upper().strip().replace("%", "")
    if s in ("CRIT RATE", "CRIT RATE/DMG"):
        return "CRIT RATE"
    if s in ("CRIT DMG",):
        return "CRIT DMG"
    if "HEALING" in s or s == "HB":
        return "HB"
    if s.startswith("PHYSICAL"):
        return "PHYSICAL DMG%"
    if "DMG" in s:
        return "DMG%"
    if s in ("ATK", "ATK%"):
        return "ATK%"
    if s in ("HP", "HP%"):
        return "HP%"
    if s in ("DEF", "DEF%"):
        return "DEF%"
    if s in ("ER", "ER%"):
        return "ER%"
    if "EM" in s or "ELEMENTAL MASTERY" in s:
        return "EM"
    return s


class ArtifactMainStatValidator:
    """Validate artifact main stats against recommended builds."""

    def validate(
        self,
        character_id: str,
        detected_stats: dict[str, str],
    ) -> list[MainStatIssue]:
        """Validate artifact main stats for a character.

        Args:
            character_id: Character identifier (e.g., "xiangling").
            detected_stats: Dict mapping slot names to detected main stats.
                           E.g. {"sands": "ATK%", "goblet": "Pyro DMG%", "circlet": "CRIT Rate"}

        Returns:
            List of MainStatIssue for any problems found.
        """
        issues: list[MainStatIssue] = []
        cid = character_id.lower().strip()

        build = F2P_BUILDS.get(cid)
        if build is not None:
            recommended = _parse_main_stats(build.artifact_main_stats)
            raw_stats = build.artifact_main_stats  # (sands, goblet, circlet) raw
            role = build.role
        else:
            recommended = {}
            raw_stats = ()
            role = "dps"

        slot_order = ("sands", "goblet", "circlet")

        for slot, detected in detected_stats.items():
            det_norm = _normalize_stat(detected)

            # Check if detected stat is in any of the "or" alternatives
            slot_idx = {"sands": 0, "goblet": 1, "circlet": 2}.get(slot)
            all_rec_options: list[str] = []
            if raw_stats and slot_idx is not None and slot_idx < len(raw_stats):
                all_rec_options = [opt.strip() for opt in raw_stats[slot_idx].split(" or ")]

            if any(_normalize_stat(opt) == det_norm for opt in all_rec_options):
                continue  # Detected stat matches one of the recommended options

            # Check against build-specific recommendation
            if slot in recommended:
                rec_norm = _normalize_stat(recommended[slot])
                if det_norm != rec_norm:
                    # Check if it's a valid alternative
                    valid_stats = self._get_valid_stats(role, slot)
                    if valid_stats and det_norm not in [_normalize_stat(s) for s in valid_stats]:
                        severity = "error"
                    else:
                        severity = "warning"

                    issues.append(MainStatIssue(
                        character_id=character_id,
                        slot=slot,
                        detected_stat=detected,
                        recommended_stat=recommended[slot],
                        severity=severity,
                        reason=f"{detected} is suboptimal — recommended: {recommended[slot]}",
                    ))

            # Check against never-stats
            never = _NEVER_STATS.get(role, {}).get(slot, ())
            for never_stat in never:
                if _normalize_stat(never_stat) == det_norm:
                    issues.append(MainStatIssue(
                        character_id=character_id,
                        slot=slot,
                        detected_stat=detected,
                        recommended_stat=never_stat,
                        severity="error",
                        reason=f"{detected} should never be on {role} {slot}",
                    ))

        return issues

    def _get_valid_stats(self, role: str, slot: str) -> tuple[str, ...]:
        """Get valid main stats for a role/slot combination."""
        # Try exact role match
        stats = _ROLE_MAIN_STATS.get(role, {}).get(slot)
        if stats:
            return stats
        # Fallback: try base role type
        base_role = role.split("_")[0] if "_" in role else role
        return _ROLE_MAIN_STATS.get(base_role, {}).get(slot, ())
