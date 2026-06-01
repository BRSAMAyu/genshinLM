"""R-33: Team build validator — pre-combat safety checks.

Validates team composition before entering combat encounters:
- At least 1 healer or shielder present
- Elemental coverage for boss weaknesses
- No empty slots
- Warns (does not block) for suboptimal compositions
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from combat.boss_schema import BossProfile
from combat.team_capability import TeamProfile

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TeamValidationResult:
    valid: bool
    safety_score: float  # 0.0-1.0
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    @property
    def safe_to_proceed(self) -> bool:
        return len(self.blockers) == 0


@dataclass(frozen=True, slots=True)
class BossWeakness:
    element: str
    importance: str = "recommended"  # "required" | "recommended" | "optional"


_KNOWN_HEALERS: frozenset[str] = frozenset({
    "bennett", "jean", "kokomi", "kuki_shinobu", "barbara", "qiqi",
    "sayu", "diona", "noelle", "baizhu", "charlotte", "mika",
})

_KNOWN_SHIELDERS: frozenset[str] = frozenset({
    "zhongli", "layla", "diona", "kirara", "noelle", "thoma",
    "baizhong", "xiangling",  # Pyronado provides partial cover
})


class TeamBuildValidator:
    """Validate team composition before combat."""

    def validate(
        self,
        team: TeamProfile,
        boss: BossProfile | None = None,
        strict: bool = False,
    ) -> TeamValidationResult:
        """Validate a team composition.

        Args:
            team: Team profile with character capabilities.
            boss: Optional boss profile for weakness checking.
            strict: If True, warnings become blockers.

        Returns:
            TeamValidationResult with safety assessment.
        """
        warnings: list[str] = []
        blockers: list[str] = []

        # Check 1: Empty team
        if not team.characters:
            blockers.append("Team is empty — no characters selected")
            return TeamValidationResult(
                valid=False, safety_score=0.0,
                warnings=tuple(warnings), blockers=tuple(blockers),
            )

        # Check 2: Survival — healer or shielder
        has_healer = team.has_healer
        has_shielder = team.has_shielder
        if not has_healer and not has_shielder:
            msg = "No healer or shielder — team has no sustain"
            if strict:
                blockers.append(msg)
            else:
                warnings.append(msg)

        # Check 3: Empty slots
        slots_filled = {c.slot for c in team.characters}
        for slot in range(1, 5):
            if slot not in slots_filled:
                warnings.append(f"Slot {slot} is empty — fighting undermanned")

        # Check 4: Elemental coverage vs boss weakness
        if boss is not None:
            self._check_elemental_coverage(team, boss, warnings, blockers, strict)

        # Check 5: All unknown characters
        unknown_count = sum(1 for c in team.characters if not c.known)
        if unknown_count == len(team.characters):
            blockers.append("All characters are unknown — cannot plan combat")

        # Calculate safety score
        score = self._calculate_safety_score(team, has_healer, has_shielder, len(warnings), len(blockers))

        return TeamValidationResult(
            valid=len(blockers) == 0,
            safety_score=score,
            warnings=tuple(warnings),
            blockers=tuple(blockers),
        )

    def _check_elemental_coverage(
        self,
        team: TeamProfile,
        boss: BossProfile,
        warnings: list[str],
        blockers: list[str],
        strict: bool,
    ) -> None:
        elements = set(team.elements)
        # Check boss elemental immunity/resistance
        for element, resistance in boss.elemental_resistance.items():
            if float(resistance) >= 0.7 and element in elements:
                msg = f"Boss resists {element} ({float(resistance):.0%}) — team relies on this element"
                if strict:
                    blockers.append(msg)
                else:
                    warnings.append(msg)
        # Check for recommended reactions
        if boss.recommended_reactions:
            has_recommended = False
            for reaction in boss.recommended_reactions:
                reaction_lower = reaction.lower()
                if "vaporize" in reaction_lower and {"pyro", "hydro"} <= elements:
                    has_recommended = True
                elif "melt" in reaction_lower and ({"pyro", "cryo"} <= elements or {"cryo", "pyro"} <= elements):
                    has_recommended = True
                elif "freeze" in reaction_lower and {"cryo", "hydro"} <= elements:
                    has_recommended = True
                elif "quicken" in reaction_lower and {"dendro", "electro"} <= elements:
                    has_recommended = True
                elif "overloaded" in reaction_lower and {"pyro", "electro"} <= elements:
                    has_recommended = True
                elif "superconduct" in reaction_lower and {"cryo", "electro"} <= elements:
                    has_recommended = True
            if not has_recommended:
                warnings.append("Team lacks recommended elemental reactions for this boss")

    @staticmethod
    def _calculate_safety_score(
        team: TeamProfile,
        has_healer: bool,
        has_shielder: bool,
        warning_count: int,
        blocker_count: int,
    ) -> float:
        score = 0.5  # base
        if has_healer:
            score += 0.25
        if has_shielder:
            score += 0.15
        if len(team.characters) >= 4:
            score += 0.1
        elif len(team.characters) >= 3:
            score += 0.05
        # Penalties
        score -= warning_count * 0.05
        score -= blocker_count * 0.2
        return max(0.0, min(1.0, score))
