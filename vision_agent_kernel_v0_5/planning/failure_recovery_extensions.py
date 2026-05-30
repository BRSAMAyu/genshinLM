"""Failure analysis and recovery priority decision making.

S-22: RecoveryPriorityDecision - Temporary buff vs permanent upgrade decisions

This module extends FailureAnalyzer with strategic recovery prioritization.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# S-22: Recovery Priority Decisions
# ---------------------------------------------------------------------------

class RecoveryType(str, Enum):
    """Type of recovery action."""
    TEMPORARY_BUFF = "temporary_buff"      # Food, potions, blessings
    PERMANENT_UPGRADE = "permanent_upgrade"  # Level, talent, artifact
    TEAM_ADJUSTMENT = "team_adjustment"   # Swap characters, change comp
    STRATEGY_CHANGE = "strategy_change"    # Different approach/timing
    RETREAT_REASSESS = "retreat_reassess"  # Full retreat and reprepare


class RecoveryUrgency(str, Enum):
    """How urgent is the recovery need."""
    LOW = "low"         # Can wait, no immediate threat
    MEDIUM = "medium"   # Should address in current session
    HIGH = "high"       # Must address before continuing
    CRITICAL = "critical"  # Stop current activity


@dataclass(frozen=True, slots=True)
class ResourceRecoveryOption:
    """A single recovery option with cost-benefit analysis."""
    recovery_type: RecoveryType
    action: str                      # Concrete action description
    cost_resin: int = 0
    cost_mora: int = 0
    cost_time_min: float = 0.0
    benefit_score: float             # 0.0-1.0, immediate benefit
    permanent_value: float           # 0.0-1.0, long-term value
    time_to_effect: float            # Minutes until benefit realized
    urgency: RecoveryUrgency
    priority: int                    # Rank among options


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    """Complete recovery decision with prioritized options."""
    situation_summary: str
    primary_recovery: ResourceRecoveryOption
    alternatives: tuple[ResourceRecoveryOption, ...]
    immediate_action: str
    deferred_actions: tuple[str, ...]
    retreat_required: bool
    retreat_reason: str = ""


@dataclass(frozen=True, slots=True)
class TempVsPermanentAnalysis:
    """Analysis comparing temporary buffs vs permanent upgrades."""
    temp_buffs_available: tuple[str, ...]
    permanent_upgrades_needed: tuple[str, ...]
    recommended_mix: str            # "favor_temp", "favor_perm", "balanced"
    reasoning: str


class RecoveryPriorityDecision:
    """Decides between temporary buffs and permanent upgrades for recovery.

    S-22: Analyzes failure context and determines optimal recovery strategy:
    - When to use temporary buffs (food, potions)
    - When to invest in permanent upgrades (levels, talents)
    - How to balance short-term vs long-term gains
    """

    # Temporary buff sources and their effects
    TEMP_BUFF_EFFECTS: dict[str, dict[str, float]] = {
        "atk_food_small": {"atk_pct": 0.10, "duration_min": 5.0},
        "atk_food_large": {"atk_pct": 0.20, "duration_min": 5.0},
        "crit_rate_food": {"crit_rate": 0.10, "duration_min": 5.0},
        "def_food": {"def_pct": 0.15, "duration_min": 5.0},
        "healing_food": {"heal": 0.25, "duration_min": 0.0},
        "stamina_food": {"stamina_cost": -0.25, "duration_min": 5.0},
        "blessing_atk": {"atk_pct": 0.15, "duration_min": 10.0},
        "blessing_crit": {"crit_rate": 0.15, "duration_min": 10.0},
    }

    # Permanent upgrade thresholds (levels where upgrade is most efficient)
    UPGRADE_THRESHOLDS = {
        "character_level": [20, 40, 50, 60, 70, 80],
        "weapon_level": [20, 40, 50, 60, 70, 80],
        "talent_level": [2, 4, 6, 8, 10, 12],
    }

    def analyze_temp_vs_permanent(
        self,
        failure_context: str,
        current_character_level: int,
        current_weapon_level: int,
        current_talent_level: int,
        available_mora: int,
        available_resin: int,
        time_constraint_min: float,
    ) -> TempVsPermanentAnalysis:
        """Analyze whether to favor temporary or permanent solutions."""
        temp_buffs: list[str] = []
        permanent_upgrades: list[str] = []

        # Identify failure type
        is_survivability = "died" in failure_context.lower() or "health" in failure_context.lower()
        is_damage = "damage" in failure_context.lower() or "dps" in failure_context.lower()

        # Temporary options
        if is_damage:
            temp_buffs.extend(["atk_food_small", "atk_food_large", "blessing_atk"])
        if is_survivability:
            temp_buffs.extend(["def_food", "healing_food"])

        # Permanent options
        # Level upgrades
        for threshold in self.UPGRADE_THRESHOLDS["character_level"]:
            if current_character_level < threshold:
                permanent_upgrades.append(f"Level to {threshold}")
                break

        # Weapon upgrades
        weapon_gap = current_character_level - current_weapon_level
        if weapon_gap > 10:
            target = min(current_character_level, current_weapon_level + 20)
            permanent_upgrades.append(f"Weapon to level {target}")

        # Talent upgrades
        for threshold in self.UPGRADE_THRESHOLDS["talent_level"]:
            if current_talent_level < threshold:
                permanent_upgrades.append(f"Talent to level {threshold}")
                break

        # Determine recommended mix
        if time_constraint_min < 15:
            recommendation = "favor_temp"
            reasoning = "Limited time - use food buffs for immediate effect"
        elif available_resin >= 80 and available_mora >= 200000:
            recommendation = "favor_perm"
            reasoning = "Sufficient resources - invest in permanent upgrades"
        elif is_survivability:
            recommendation = "balanced"
            reasoning = "Need both survival buffs and permanent survivability"
        else:
            recommendation = "favor_temp"
            reasoning = "Prioritize temporary buffs until content is stable"

        return TempVsPermanentAnalysis(
            temp_buffs_available=tuple(temp_buffs),
            permanent_upgrades_needed=tuple(permanent_upgrades),
            recommended_mix=recommendation,
            reasoning=reasoning,
        )

    def evaluate_recovery_options(
        self,
        failure_context: str,
        attempts: int,
        current_resin: int,
        current_mora: int,
        main_dps_level: int,
        main_dps_weapon_level: int,
        is_time_critical: bool = False,
    ) -> RecoveryDecision:
        """Evaluate all recovery options and rank them."""
        options: list[ResourceRecoveryOption] = []

        # Analyze context
        analysis = self.analyze_temp_vs_permanent(
            failure_context=failure_context,
            current_character_level=main_dps_level,
            current_weapon_level=main_dps_weapon_level,
            current_talent_level=0,  # Would need actual talent data
            available_mora=current_mora,
            available_resin=current_resin,
            time_constraint_min=0.0,  # Would need actual time
        )

        # Temporary buff options
        for buff_name in analysis.temp_buffs_available:
            effect = self.TEMP_BUFF_EFFECTS.get(buff_name, {})
            benefit = max(
                effect.get("atk_pct", 0.0),
                effect.get("crit_rate", 0.0),
                effect.get("def_pct", 0.0),
            )

            options.append(ResourceRecoveryOption(
                recovery_type=RecoveryType.TEMPORARY_BUFF,
                action=f"Use {buff_name}",
                cost_mora=5000,
                benefit_score=min(1.0, benefit * 5),  # Scale to 0-1
                permanent_value=0.0,
                time_to_effect=0.0,  # Immediate
                urgency=RecoveryUrgency.HIGH if attempts >= 2 else RecoveryUrgency.MEDIUM,
                priority=0,
            ))

        # Permanent upgrade options
        if current_resin >= 40:
            options.append(ResourceRecoveryOption(
                recovery_type=RecoveryType.PERMANENT_UPGRADE,
                action="Level up main DPS character",
                cost_resin=40,
                cost_mora=20000,
                benefit_score=0.4,  # Takes time to see benefit
                permanent_value=0.8,
                time_to_effect=5.0,
                urgency=RecoveryUrgency.MEDIUM,
                priority=10,
            ))

        if main_dps_weapon_level < main_dps_level - 5:
            options.append(ResourceRecoveryOption(
                recovery_type=RecoveryType.PERMANENT_UPGRADE,
                action="Upgrade main DPS weapon",
                cost_resin=20,
                cost_mora=10000,
                benefit_score=0.5,
                permanent_value=0.7,
                time_to_effect=2.0,
                urgency=RecoveryUrgency.MEDIUM,
                priority=5,
            ))

        # Team adjustment
        options.append(ResourceRecoveryOption(
            recovery_type=RecoveryType.TEAM_ADJUSTMENT,
            action="Try different team composition",
            benefit_score=0.3,
            permanent_value=0.2,
            time_to_effect=0.0,
            urgency=RecoveryUrgency.LOW,
            priority=15,
        ))

        # Strategy change
        options.append(ResourceRecoveryOption(
            recovery_type=RecoveryType.STRATEGY_CHANGE,
            action="Learn boss patterns and adjust timing",
            benefit_score=0.4,
            permanent_value=0.5,  # Skill improvement
            time_to_effect=10.0,  # Practice time
            urgency=RecoveryUrgency.LOW,
            priority=12,
        ))

        # Sort by priority
        options.sort(key=lambda x: (x.urgency.value if hasattr(x.urgency, 'value') else 0, x.priority))

        # Assign priority ranks
        for i, opt in enumerate(options):
            options[i].priority = i  # type: ignore

        # Determine retreat requirement
        retreat_required = attempts >= 5 and options[0].recovery_type != RecoveryType.TEMPORARY_BUFF

        # Build decision
        primary = options[0] if options else ResourceRecoveryOption(
            recovery_type=RecoveryType.RETREAT_REASSESS,
            action="Retreat and reassess",
            urgency=RecoveryUrgency.HIGH,
            priority=0,
        )

        return RecoveryDecision(
            situation_summary=f"Failed {attempts} times - {failure_context}",
            primary_recovery=primary,
            alternatives=tuple(options[1:5]),
            immediate_action=primary.action,
            deferred_actions=tuple(opt.action for opt in options[5:]),
            retreat_required=retreat_required,
            retreat_reason="Multiple failures indicate fundamental issue" if retreat_required else "",
        )


# ---------------------------------------------------------------------------
# S-22 Integration: Extend FailureAnalyzer
# ---------------------------------------------------------------------------

def extended_failure_diagnosis(
    base_diagnosis: dict[str, object],
    recovery_decision: RecoveryDecision,
) -> dict[str, object]:
    """Extend base failure diagnosis with recovery prioritization."""
    return {
        **base_diagnosis,
        "recovery_priority": {
            "immediate": recovery_decision.immediate_action,
            "alternatives": [a.action for a in recovery_decision.alternatives],
            "retreat_required": recovery_decision.retreat_required,
        },
        "temp_vs_permanent": {
            "primary": recovery_decision.primary_recovery.recovery_type.value,
            "benefit": recovery_decision.primary_recovery.benefit_score,
            "permanent_value": recovery_decision.primary_recovery.permanent_value,
        },
    }