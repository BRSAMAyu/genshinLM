"""Strategic decision engine extensions for resource management.

S-18: OverInvestmentDetector - Identifies over-invested characters
S-19: DynamicTimeBudget - Daily available time evaluation

This module extends StrategicDecisionEngine with resource efficiency
and time management capabilities.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# S-18: Over-Investment Detection
# ---------------------------------------------------------------------------

class InvestmentLevel(str, Enum):
    """Level of investment in a character."""
    UNBUILT = "unbuilt"      # Level 1-20
    BUILDING = "building"    # Level 20-50, ascending
    VIABLE = "viable"        # Level 50-70, usable but not invested
    WELL_BUILT = "well_built"  # Level 70-80, solid contribution
    OVERINVESTED = "overinvested"  # Level 80+, high investment
    DIMINISHING_RETURNS = "diminishing_returns"  # 90+, marginal gains


@dataclass(frozen=True, slots=True)
class InvestmentAssessment:
    """Assessment of character investment level."""
    character_name: str
    current_level: int
    investment_level: InvestmentLevel
    is_over_invested: bool
    marginal_gain_score: float  # 0.0-1.0, how much benefit per resource
    recommendation: str
    cost_efficiency_grade: str  # "A", "B", "C", "D"


@dataclass(frozen=True, slots=True)
class OverInvestedCharacter:
    """A character that exceeds 'good enough' threshold."""
    name: str
    current_level: int
    wasted_levels: int        # Levels beyond what was needed
    wasted_resin: int        # Resin spent beyond necessity
    wasted_mora: int         # Mora spent beyond necessity
    alternative_suggestion: str


class OverInvestmentDetector:
    """Detects over-investment in characters.

    S-18: Implements "good enough" dynamic standard - determines when
    additional investment provides diminishing returns vs opportunity cost.
    """

    # Level thresholds where investment provides meaningful gains
    VIABLE_THRESHOLD = 50     # Can participate in most content
    WELL_BUILT_THRESHOLD = 70  # Solid for endgame
    DIMINISHING_THRESHOLD = 85  # Gains become marginal

    # Context-dependent thresholds
    CONTEXT_THRESHOLDS: dict[str, int] = {
        "spiral_abyss_floor_9": 70,
        "spiral_abyss_floor_12": 80,
        "world_boss": 60,
        "weekly_boss": 70,
        "daily_commissions": 50,
        "exploration": 40,
    }

    def assess_character(
        self,
        character_name: str,
        current_level: int,
        current_weapon_level: int,
        current_talent_levels: tuple[int, int, int],
        target_content: str = "general",
    ) -> InvestmentAssessment:
        """Assess if a character is over-invested."""
        threshold = self.CONTEXT_THRESHOLDS.get(
            target_content, self.VIABLE_THRESHOLD
        )

        # Determine investment level
        if current_level < 20:
            inv_level = InvestmentLevel.UNBUILT
        elif current_level < 50:
            inv_level = InvestmentLevel.BUILDING
        elif current_level < threshold:
            inv_level = InvestmentLevel.VIABLE
        elif current_level < self.DIMINISHING_THRESHOLD:
            inv_level = InvestmentLevel.WELL_BUILT
        elif current_level < 90:
            inv_level = InvestmentLevel.OVERINVESTED
        else:
            inv_level = InvestmentLevel.DIMINISHING_RETURNS

        # Calculate marginal gain score (benefit per resource unit)
        # Higher threshold = lower marginal gain
        level_gap = current_level - threshold
        if level_gap <= 0:
            marginal_score = 1.0
        elif level_gap <= 10:
            marginal_score = 0.6
        elif level_gap <= 20:
            marginal_score = 0.3
        else:
            marginal_score = 0.1

        # Check weapon parity
        weapon_gap = current_level - current_weapon_level
        if weapon_gap > 10:
            marginal_score *= 0.5  # Weapon is bottleneck, level investment wasted

        # Check talent investment
        avg_talent = sum(current_talent_levels) / 3
        talent_gap = current_level - (avg_talent * 2)
        if talent_gap > 15:
            marginal_score *= 0.6  # Talent is bottleneck

        # Determine if over-invested
        is_over = (
            inv_level in (InvestmentLevel.OVERINVESTED, InvestmentLevel.DIMINISHING_RETURNS)
            and level_gap > 5
        )

        # Grade cost efficiency
        if marginal_score >= 0.8:
            grade = "A"
        elif marginal_score >= 0.6:
            grade = "B"
        elif marginal_score >= 0.4:
            grade = "C"
        else:
            grade = "D"

        # Recommendation
        if is_over:
            rec = f"Stop investing. Level {current_level} exceeds {target_content} needs."
        elif inv_level == InvestmentLevel.WELL_BUILT:
            rec = f"Target reached for {target_content}. Consider other investments."
        else:
            rec = f"Continue investing toward level {threshold}."

        return InvestmentAssessment(
            character_name=character_name,
            current_level=current_level,
            investment_level=inv_level,
            is_over_invested=is_over,
            marginal_gain_score=marginal_score,
            recommendation=rec,
            cost_efficiency_grade=grade,
        )

    def find_overinvested(
        self,
        characters: list[dict[str, object]],
        target_content: str = "general",
    ) -> tuple[OverInvestedCharacter, ...]:
        """Find all over-invested characters in a roster."""
        overinvested: list[OverInvestedCharacter] = []

        for char in characters:
            name = char.get("name", "unknown")
            level = int(char.get("level", 1))
            weapon = int(char.get("weapon_level", 1))
            talents = char.get("talent_levels", (1, 1, 1))

            assessment = self.assess_character(
                character_name=name,
                current_level=level,
                current_weapon_level=weapon,
                current_talent_levels=tuple(talents),  # type: ignore
                target_content=target_content,
            )

            if assessment.is_over_invested:
                threshold = self.CONTEXT_THRESHOLDS.get(
                    target_content, self.VIABLE_THRESHOLD
                )
                wasted_levels = level - threshold
                # Mora cost varies by level:
                # - Level 1-40: ~15,000 Mora per level
                # - Level 41-60: ~20,000 Mora per level
                # - Level 61-80: ~25,000 Mora per level
                # - Level 81-90: ~30,000 Mora per level
                wasted_mora = wasted_levels * 20000  # Average ~20,000 Mora per level

                # Suggest alternative
                alt = f"Invest resin in artifacts or other characters instead of {name}"

                overinvested.append(OverInvestedCharacter(
                    name=name,
                    current_level=level,
                    wasted_levels=wasted_levels,
                    wasted_resin=wasted_resin,
                    wasted_mora=wasted_mora,
                    alternative_suggestion=alt,
                ))

        return tuple(overinvested)


# ---------------------------------------------------------------------------
# S-19: Dynamic Time Budget
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TimeBudgetAllocation:
    """Allocation of available time across activity categories."""
    total_available_min: float
    allocations: dict[str, float] = field(default_factory=dict)  # category -> minutes
    priorities: tuple[str, ...] = field(default_factory=())
    warnings: tuple[str, ...] = field(default_factory=())


@dataclass(frozen=True, slots=True)
class DailyTimeBudget:
    """Daily time budget with context-aware allocation."""
    day_type: str                    # "weekday", "weekend", "event", "reset"
    base_available_min: float        # Base time available
    adjusted_available_min: float   # After adjustments
    allocations: TimeBudgetAllocation
    is_emergency_grind: bool = False  # True if time-constrained grind


class DynamicTimeBudget:
    """Evaluates daily available time and allocates it optimally.

    S-19: Provides dynamic time budget evaluation based on:
    - Day type (weekday vs weekend)
    - Event schedule
    - Resin state
    - Player urgency
    """

    # Time constants
    WEEKDAY_BASE_MIN = 60.0        # 1 hour on weekdays
    WEEKEND_BASE_MIN = 120.0      # 2 hours on weekends
    RESET_OVERHEAD_MIN = 15.0      # Time for daily reset tasks

    # Activity time costs
    ACTIVITY_COSTS: dict[str, float] = {
        "commissions": 10.0,
        "resin_spend": 5.0,         # Per 40 resin chunk
        "weekly_boss": 10.0,
        "exploration": 15.0,
        "quest": 30.0,              # Per major quest
        "spiral_abyss_half": 15.0,
        "spiral_abyss_full": 45.0,
        "event_daily": 15.0,
    }

    # Priority order
    PRIORITY_ORDER = (
        "commissions",
        "resin_spend",
        "weekly_boss",
        "event_daily",
        "spiral_abyss_half",
        "quest",
        "exploration",
    )

    def evaluate_day_type(self, day_of_week: int) -> str:
        """Determine day type from day of week (0=Monday)."""
        if day_of_week == 0:  # Monday
            return "reset"
        if day_of_week in (5, 6):  # Sat, Sun
            return "weekend"
        return "weekday"

    def calculate_base_budget(
        self,
        day_type: str,
        user_reported_available_hours: float = 0.0,
    ) -> float:
        """Calculate base time budget for the day."""
        # If user provided specific time, use it
        if user_reported_available_hours > 0:
            return user_reported_available_hours * 60.0

        # Otherwise use defaults
        if day_type == "weekend":
            base = self.WEEKEND_BASE_MIN
        elif day_type == "reset":
            base = self.WEEKDAY_BASE_MIN + self.RESET_OVERHEAD_MIN
        else:
            base = self.WEEKDAY_BASE_MIN

        return base

    def adjust_for_context(
        self,
        base_budget: float,
        resin_current: int = 0,
        resin_max: int = 200,
        has_pending_urgent: bool = False,
        is_event_active: bool = False,
        days_until_event_end: int = 0,
    ) -> tuple[float, list[str]]:
        """Adjust budget based on game context."""
        adjusted = base_budget
        warnings: list[str] = []

        # Resin pressure - if near full, consider time budget
        if resin_current >= resin_max * 0.9:
            adjusted += 10.0  # Add time for resin spending
            warnings.append("High resin detected - prioritize resin spend time")

        # Resin under pressure - if empty, reduce time expectation
        if resin_current < 40:
            adjusted -= 15.0
            warnings.append("Low resin - reducing non-resin time expectations")

        # Urgent content
        if has_pending_urgent:
            adjusted += 10.0
            warnings.append("Urgent content pending - added buffer")

        # Event urgency
        if is_event_active and days_until_event_end <= 3:
            adjusted += 15.0
            warnings.append(f"Event ending in {days_until_event_end} days - added event time")

        return max(30.0, adjusted), warnings  # Minimum 30 min

    def allocate_time(
        self,
        available_min: float,
        activity_requirements: dict[str, float],
        priorities: tuple[str, ...] | None = None,
    ) -> TimeBudgetAllocation:
        """Allocate available time across activities."""
        if priorities is None:
            priorities = self.PRIORITY_ORDER

        allocated: dict[str, float] = {}
        remaining = available_min
        included: list[str] = []
        warnings: list[str] = []

        for activity in priorities:
            cost = self.ACTIVITY_COSTS.get(activity, 10.0)
            required = activity_requirements.get(activity, 0.0)

            if required <= 0:
                continue

            if cost <= remaining:
                allocated[activity] = min(required, cost)
                remaining -= allocated[activity]
                included.append(activity)
            else:
                # Partial allocation
                if remaining >= cost * 0.5:
                    allocated[activity] = remaining
                    remaining = 0
                    included.append(activity)
                    warnings.append(f"Insufficient time for full {activity}")
                else:
                    warnings.append(f"No time allocated for {activity}")

        return TimeBudgetAllocation(
            total_available_min=available_min,
            allocations=allocated,
            priorities=tuple(included),
            warnings=tuple(warnings),
        )

    def evaluate_daily_budget(
        self,
        day_of_week: int,
        user_reported_hours: float = 0.0,
        resin_current: int = 0,
        resin_max: int = 200,
        has_pending_urgent: bool = False,
        is_event_active: bool = False,
        days_until_event_end: int = 0,
        activity_requirements: dict[str, float] | None = None,
    ) -> DailyTimeBudget:
        """Full daily time budget evaluation."""
        if activity_requirements is None:
            activity_requirements = {
                "commissions": 10.0,
                "resin_spend": min(resin_current, 200) / 40 * 5.0,
                "weekly_boss": 30.0 if day_of_week == 0 else 0.0,
                "event_daily": 15.0 if is_event_active else 0.0,
            }

        day_type = self.evaluate_day_type(day_of_week)
        base = self.calculate_base_budget(day_type, user_reported_hours)
        adjusted, context_warnings = self.adjust_for_context(
            base, resin_current, resin_max, has_pending_urgent,
            is_event_active, days_until_event_end,
        )

        allocations = self.allocate_time(adjusted, activity_requirements)

        # Check if emergency grind mode needed
        total_required = sum(activity_requirements.values())
        is_emergency = total_required > adjusted * 1.2

        all_warnings = list(allocations.warnings) + context_warnings
        if is_emergency:
            all_warnings.append("Emergency grind mode - prioritizing high-value activities")

        return DailyTimeBudget(
            day_type=day_type,
            base_available_min=base,
            adjusted_available_min=adjusted,
            allocations=allocations,
            is_emergency_grind=is_emergency,
        )


# ---------------------------------------------------------------------------
# S-18 Integration: StrategicDecisionEngine extensions
# ---------------------------------------------------------------------------

class InvestmentAwareDecisionMixin:
    """Mixin to add over-investment awareness to StrategicDecisionEngine."""

    def __init__(self) -> None:
        self._detector = OverInvestmentDetector()

    def check_investment_balance(
        self,
        characters: list[dict[str, object]],
        target_content: str = "spiral_abyss_floor_9",
    ) -> dict[str, object]:
        """Check roster for investment balance issues."""
        overinvested = self._detector.find_overinvested(
            characters, target_content
        )

        if overinvested:
            total_wasted = sum(
                (oi.wasted_resin, oi.wasted_mora) for oi in overinvested
            )
            return {
                "has_imbalance": True,
                "overinvested_count": len(overinvested),
                "overinvested": overinvested,
                "total_wasted_resin": sum(oi.wasted_resin for oi in overinvested),
                "suggestion": "Redirect resources from over-invested to under-invested characters",
            }

        return {"has_imbalance": False}