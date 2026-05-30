"""World Level transition planning and intensity jump handling.

S-17: WorldLevelTransitionPlanner - Pre-ascension preparation checklist
S-17: IntensityJumpHandler - Response when world level increases

This module provides strategic planning for world level transitions
and handles the difficulty spikes when WL increases.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WLTransitionPhase(str, Enum):
    """Phase of world level transition preparation."""
    ASSESSMENT = "assessment"        # Evaluate readiness
    PREPARATION = "preparation"      # Build characters before transition
    TRANSITION = "transition"       # Execute WL ascension
    STABILIZATION = "stabilization"  # Handle increased difficulty


class IntensityLevel(int, Enum):
    """Relative intensity compared to current state."""
    SAME = 0      # No change
    MILD = 1      # Slight increase (WL+1)
    MODERATE = 2  # Significant increase (WL+2)
    SEVERE = 3   # Major spike


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WLReadinessScore:
    """Assessment of readiness for world level transition."""
    overall_score: float           # 0.0-1.0, higher is more ready
    dps_readiness: float          # 0.0-1.0
    support_readiness: float      # 0.0-1.0
    artifact_readiness: float     # 0.0-1.0
    resource_sufficiency: float  # 0.0-1.0
    recommended_wl: int           # Safe WL for current gear
    risk_factors: tuple[str, ...] = field(default_factory=())
    missing_items: tuple[str, ...] = field(default_factory=())


@dataclass(frozen=True, slots=True)
class PreparationItem:
    """A single item on the pre-WL-transition checklist."""
    item_id: str
    category: str                 # "character", "artifact", "resource", "team"
    description: str
    priority: int                 # Lower = more urgent
    estimated_cost_resin: int = 0
    estimated_cost_mora: int = 0
    is_complete: bool = False


@dataclass(frozen=True, slots=True)
class WLTransitionPlan:
    """Complete plan for world level transition."""
    current_wl: int
    target_wl: int
    intensity_jump: IntensityLevel
    readiness: WLReadinessScore
    preparation_checklist: tuple[PreparationItem, ...]
    estimated_preparation_time_min: float
    transition_recommended: bool
    stabilization_notes: str = ""


# ---------------------------------------------------------------------------
# WL Transition thresholds
# ---------------------------------------------------------------------------

# WL to required character level mapping
WL_CHARACTER_REQUIREMENTS: dict[int, int] = {
    0: 20,
    1: 25,
    2: 30,
    3: 35,
    4: 40,
    5: 50,
    6: 60,
    7: 70,
    8: 80,
}

# WL to required team count (built characters)
WL_TEAM_REQUIREMENTS: dict[int, int] = {
    0: 1,
    1: 2,
    2: 2,
    3: 4,
    4: 4,
    5: 6,
    6: 6,
    7: 8,
    8: 8,
}


# ---------------------------------------------------------------------------
# WorldLevelTransitionPlanner
# ---------------------------------------------------------------------------

class WorldLevelTransitionPlanner:
    """Plans world level transitions with pre-ascension preparation checklists.

    S-17: Evaluates readiness, generates preparation checklists, and handles
    the intensity jump when WL increases.
    """

    def assess_readiness(
        self,
        current_wl: int,
        main_dps_level: int,
        main_dps_weapon_level: int,
        team_count: int,
        avg_artifact_level: int = 0,
        mora_millions: float = 0.0,
        resin_current: int = 0,
    ) -> WLReadinessScore:
        """Assess readiness for the next world level."""
        target_wl = min(current_wl + 1, 8)
        required_level = WL_CHARACTER_REQUIREMENTS.get(target_wl, 80)
        required_team = WL_TEAM_REQUIREMENTS.get(target_wl, 4)

        # DPS readiness (character level vs required)
        dps_score = min(1.0, main_dps_level / required_level)
        if main_dps_weapon_level < main_dps_level - 10:
            dps_score *= 0.7  # Penalize weapon underlevel

        # Support readiness (team count)
        support_score = min(1.0, team_count / required_team)

        # Artifact readiness
        artifact_score = min(1.0, avg_artifact_level / 16) if avg_artifact_level > 0 else 0.5

        # Resource sufficiency (mora + resin for immediate upgrades)
        resource_score = 0.5  # Base
        if mora_millions >= 1.0:
            resource_score += 0.2
        if mora_millions >= 5.0:
            resource_score += 0.2
        if resin_current >= 40:
            resource_score += 0.1

        # Overall weighted score
        overall = (
            dps_score * 0.35 +
            support_score * 0.25 +
            artifact_score * 0.20 +
            resource_score * 0.20
        )

        # Risk factors
        risks: list[str] = []
        if dps_score < 0.8:
            risks.append("DPS character underleveled")
        if support_score < 0.5:
            risks.append("Insufficient team depth")
        if artifact_score < 0.6:
            risks.append("Artifacts need upgrading")
        if resource_score < 0.6:
            risks.append("Insufficient resources")

        # Missing items
        missing: list[str] = []
        if main_dps_weapon_level < main_dps_level - 5:
            missing.append("Upgrade weapon")
        if team_count < 2:
            missing.append("Build secondary character")
        if avg_artifact_level < 12:
            missing.append("Enhance artifacts")

        # Recommended safe WL
        recommended_wl = current_wl
        if dps_score >= 0.9 and support_score >= 0.8:
            recommended_wl = min(target_wl, current_wl + 1)

        return WLReadinessScore(
            overall_score=overall,
            dps_readiness=dps_score,
            support_readiness=support_score,
            artifact_readiness=artifact_score,
            resource_sufficiency=resource_score,
            recommended_wl=recommended_wl,
            risk_factors=tuple(risks),
            missing_items=tuple(missing),
        )

    def generate_preparation_checklist(
        self,
        current_wl: int,
        readiness: WLReadinessScore,
    ) -> tuple[PreparationItem, ...]:
        """Generate checklist of items to prepare before WL transition."""
        items: list[PreparationItem] = []
        target_wl = min(current_wl + 1, 8)
        required_level = WL_CHARACTER_REQUIREMENTS.get(target_wl, 80)

        # High priority items
        if readiness.dps_readiness < 0.9:
            items.append(PreparationItem(
                item_id="dps_level",
                category="character",
                description=f"Level main DPS to {required_level}",
                priority=1,
                estimated_cost_resin=0,
                estimated_cost_mora=required_level * 10000,
            ))

        if "Upgrade weapon" in readiness.missing_items:
            items.append(PreparationItem(
                item_id="weapon_upgrade",
                category="weapon",
                description="Upgrade weapon to match character level",
                priority=2,
                estimated_cost_resin=20,
                estimated_cost_mora=50000,
            ))

        if readiness.support_readiness < 0.8:
            items.append(PreparationItem(
                item_id="team_build",
                category="team",
                description="Build additional characters for team coverage",
                priority=3,
                estimated_cost_resin=80,
                estimated_cost_mora=100000,
            ))

        if readiness.artifact_readiness < 0.7:
            items.append(PreparationItem(
                item_id="artifact_upgrade",
                category="artifact",
                description="Level up key artifacts to +12 or higher",
                priority=4,
                estimated_cost_resin=40,
                estimated_cost_mora=50000,
            ))

        # Medium priority
        items.append(PreparationItem(
            item_id="food_stock",
            category="resource",
            description="Stock up on attack/food buffs for combat",
            priority=5,
            estimated_cost_resin=0,
            estimated_cost_mora=10000,
        ))

        items.append(PreparationItem(
            item_id="resin_stock",
            category="resource",
            description="Accumulate fragile resin for post-transition domains",
            priority=6,
            estimated_cost_resin=0,
            estimated_cost_mora=0,
        ))

        return tuple(sorted(items, key=lambda x: x.priority))

    def create_transition_plan(
        self,
        current_wl: int,
        main_dps_level: int,
        main_dps_weapon_level: int,
        team_count: int,
        avg_artifact_level: int = 0,
        mora_millions: float = 0.0,
        resin_current: int = 0,
    ) -> WLTransitionPlan:
        """Create a complete world level transition plan."""
        target_wl = min(current_wl + 1, 8)
        intensity = IntensityLevel(target_wl - current_wl)

        readiness = self.assess_readiness(
            current_wl=current_wl,
            main_dps_level=main_dps_level,
            main_dps_weapon_level=main_dps_weapon_level,
            team_count=team_count,
            avg_artifact_level=avg_artifact_level,
            mora_millions=mora_millions,
            resin_current=resin_current,
        )

        checklist = self.generate_preparation_checklist(current_wl, readiness)

        # Calculate preparation time
        prep_time = 0.0
        for item in checklist:
            if not item.is_complete:
                prep_time += item.estimated_cost_resin * 0.125  # ~8 min per 40 resin

        # Transition recommended if readiness is good
        transition_ok = (
            readiness.overall_score >= 0.75 and
            len(readiness.risk_factors) <= 2
        )

        # Stabilization notes based on intensity
        stabilization = ""
        if intensity == IntensityLevel.MILD:
            stabilization = "Minor difficulty increase. Focus on dodging and timing."
        elif intensity == IntensityLevel.MODERATE:
            stabilization = "Significant jump. Use food buffs and prioritize survival."
        elif intensity == IntensityLevel.SEVERE:
            stabilization = "Major spike expected. Retreat and re-prepare if struggling."

        return WLTransitionPlan(
            current_wl=current_wl,
            target_wl=target_wl,
            intensity_jump=intensity,
            readiness=readiness,
            preparation_checklist=checklist,
            estimated_preparation_time_min=prep_time,
            transition_recommended=transition_ok,
            stabilization_notes=stabilization,
        )


# ---------------------------------------------------------------------------
# IntensityJumpHandler
# ---------------------------------------------------------------------------

class IntensityJumpHandler:
    """Handles difficulty spikes when world level increases.

    S-17: Responds to WL increases by adjusting strategy and providing
    immediate stabilization guidance.
    """

    def __init__(self) -> None:
        self._planner = WorldLevelTransitionPlanner()

    def detect_intensity_spike(
        self,
        previous_wl: int,
        current_wl: int,
        recent_death_rate: float = 0.0,
        avg_clear_time_multiplier: float = 1.0,
    ) -> IntensityLevel | None:
        """Detect if there was a significant intensity spike."""
        if current_wl <= previous_wl:
            return None

        jump = current_wl - previous_wl

        # Check if clear times increased significantly
        if avg_clear_time_multiplier > 1.5:
            return IntensityLevel.MODERATE

        # Check if deaths increased
        if recent_death_rate > 0.3:
            return IntensityLevel.MODERATE if jump == 1 else IntensityLevel.SEVERE

        return IntensityLevel(jump) if jump <= 3 else IntensityLevel.SEVERE

    def get_stabilization_actions(
        self,
        intensity: IntensityLevel,
        current_team_count: int,
        has_shield_character: bool = False,
        has healer: bool = False,
    ) -> tuple[str, ...]:
        """Get immediate actions to stabilize after intensity spike."""
        actions: list[str] = []

        if intensity >= IntensityLevel.MODERATE:
            actions.append("Switch to defensive team composition")
            if not has_shield_character:
                actions.append("Add shield character to team")

        if intensity >= IntensityLevel.SEVERE:
            actions.append("Retreat and use resources to boost character power")
            actions.append("Farm easier content until stabilized")

        # Universal stabilization actions
        actions.append("Use food buffs during combat")
        actions.append("Focus on dodging rather than damage")
        actions.append("Prioritize survival over clear speed")

        return tuple(actions)

    def should_temporarily_lower_wl(
        self,
        readiness: WLReadinessScore,
        recent_attempt_success: float = 0.0,
        frustration_level: float = 0.0,
    ) -> bool:
        """Determine if player should temporarily lower world level."""
        # Lower if readiness is very poor
        if readiness.overall_score < 0.5:
            return True

        # Lower if attempts keep failing
        if recent_attempt_success < 0.3 and frustration_level > 0.7:
            return True

        # Lower if multiple risk factors
        if len(readiness.risk_factors) >= 3:
            return True

        return False