"""Resource management: resin tracking, mora budget, material inventory, food stock.

Tracks game resources and makes spending decisions based on current game state
and strategic priorities. Covers M-01 through M-05, M-06, M-11 through M-13.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from knowledge.genshin_character_progression import (
    RESIN_MAX,
    RESIN_RECOVERY_MINUTES,
    RESIN_COSTS,
    BUILD_INVESTMENT_PRIORITY,
)
from knowledge.genshin_f2p_builds import BUILD_PRIORITY

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Multi-character resin planner (R-42)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CharacterResinQuota:
    """Resin allocation for a single character."""
    character_id: str
    target_level: int
    current_level: int
    talent_targets: dict[str, int]
    talent_current: dict[str, int]
    estimated_resin: int = 0
    priority: int = 100


class MultiCharacterResinPlanner:
    """Plans resin spending across multiple characters simultaneously (R-42)."""

    def __init__(self, daily_resin_budget: int = 180) -> None:
        self._daily_budget = daily_resin_budget
        self._remaining = daily_resin_budget

    def plan_allocation(
        self,
        character_states: list[Any],
        current_ar: int,
        fragile_resin_count: int = 0,
    ) -> dict[str, CharacterResinQuota]:
        """Plan resin allocation across multiple characters.

        Args:
            character_states: List of character states to plan for
            current_ar: Current adventure rank (affects domain access)
            fragile_resin_count: Number of fragile resins available

        Returns:
            Dict of character_id -> CharacterResinQuota with allocation plan
        """
        allocations: dict[str, CharacterResinQuota] = {}
        total_resin = self._daily_budget + (fragile_resin_count * 60)

        # Sort characters by priority (BUILD_PRIORITY order)
        priority_map: dict[str, int] = {}
        for i, char_id in enumerate(BUILD_PRIORITY):
            priority_map[char_id] = i

        sorted_chars = sorted(
            character_states,
            key=lambda c: priority_map.get(c.character_id, 999),
        )

        remaining = total_resin
        for state in sorted_chars:
            if remaining < 20:
                break

            quota = self._estimate_character_needs(state, remaining, current_ar)
            allocations[state.character_id] = quota
            remaining -= min(quota.estimated_resin, remaining)

        return allocations

    def _estimate_character_needs(
        self,
        state: Any,
        budget: int,
        ar: int,
    ) -> CharacterResinQuota:
        """Estimate resin needs for a single character."""
        # Level gap estimation (20 resin per ascension level on average)
        target_level = getattr(state, 'target_level', state.level + 20)
        level_gap = max(0, target_level - state.level)
        level_resin = level_gap * 20 // 10

        # Talent estimation (20 resin per talent domain run)
        talent_gap = 0
        target = getattr(state, 'target_talent_levels', {"burst": 6, "skill": 6})
        current = state.talent_levels
        for talent, target_lv in target.items():
            current_lv = current.get(talent, 1)
            if current_lv < target_lv:
                talent_gap += (target_lv - current_lv) * 20

        total = min(level_resin + talent_gap, budget)

        priority_map: dict[str, int] = {}
        for i, char_id in enumerate(BUILD_PRIORITY):
            priority_map[char_id] = i

        return CharacterResinQuota(
            character_id=state.character_id,
            target_level=target_level,
            current_level=state.level,
            talent_targets=target,
            talent_current=current,
            estimated_resin=total,
            priority=priority_map.get(state.character_id, 999),
        )

    def adjust_for_budget(
        self,
        allocations: dict[str, CharacterResinQuota],
        max_resin: int,
    ) -> dict[str, CharacterResinQuota]:
        """Adjust allocations to fit within budget constraint."""
        total = sum(a.estimated_resin for a in allocations.values())
        if total <= max_resin:
            return allocations

        # Scale down proportionally
        scale = max_resin / total
        adjusted: dict[str, CharacterResinQuota] = {}
        for char_id, quota in allocations.items():
            adjusted_quota = CharacterResinQuota(
                character_id=char_id,
                target_level=quota.target_level,
                current_level=quota.current_level,
                talent_targets=quota.talent_targets,
                talent_current=quota.talent_current,
                estimated_resin=int(quota.estimated_resin * scale),
                priority=quota.priority,
            )
            adjusted[char_id] = adjusted_quota
        return adjusted


# ---------------------------------------------------------------------------
# Mora budget with large expense warnings (M-22)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class LargeExpenseWarning:
    """Warning about a large mora expense."""
    amount: int
    reason: str
    percent_of_available: float
    severity: str = "caution"  # "caution", "warning", "critical"


def check_large_expense(mora_budget: MoraBudget, amount: int, reason: str) -> LargeExpenseWarning | None:
    """Check if a planned expense is large relative to available mora (M-22)."""
    available = mora_budget.available
    if available <= 0:
        return LargeExpenseWarning(
            amount=amount,
            reason=reason,
            percent_of_available=999.0,
            severity="critical",
        )

    percent = (amount / available) * 100

    if percent >= 50:
        severity = "critical"
    elif percent >= 25:
        severity = "warning"
    elif percent >= 10:
        severity = "caution"
    else:
        return None

    return LargeExpenseWarning(
        amount=amount,
        reason=reason,
        percent_of_available=percent,
        severity=severity,
    )


# ---------------------------------------------------------------------------
# Condensed resin decision maker (M-18)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CondensedDecision:
    """Decision on whether to craft condensed resin."""
    should_craft: bool
    reason: str
    efficiency_gain: float = 0.0  # 0.0-1.0


class CondensedDecisionMaker:
    """Decides between condensed vs original resin (M-18).

    Efficiency vs interaction tradeoff:
    - Condensed: 2 runs for 40 resin (1 interaction), saves 1 interaction
    - Original: 2 runs for 40 resin (2 interactions), better for low resin
    """

    def decide(
        self,
        current_resin: int,
        time_available_minutes: float,
        session_length_minutes: float,
        condensed_available: int,
    ) -> CondensedDecision:
        """Decide whether to craft condensed resin.

        Args:
            current_resin: Current resin amount
            time_available_minutes: Time until next play session
            session_length_minutes: Expected play session length
            condensed_available: Condensed resins currently available

        Returns:
            CondensedDecision with recommendation
        """
        # If we already have condensed, use them
        if condensed_available > 0:
            return CondensedDecision(
                should_craft=False,
                reason=f"Already have {condensed_available} condensed resin",
                efficiency_gain=0.0,
            )

        # Need at least 40 resin + 1 crystal core
        if current_resin < 40:
            return CondensedDecision(
                should_craft=False,
                reason="Not enough resin (need 40)",
                efficiency_gain=0.0,
            )

        # Check if time is constrained
        if time_available_minutes < 60:
            # Short session: condensed saves interaction time
            if current_resin >= 80:
                return CondensedDecision(
                    should_craft=True,
                    reason="Short session: condensed saves interaction",
                    efficiency_gain=0.3,
                )

        # Check session length vs domain efficiency
        # Each domain run takes ~3 min, condensed saves 1 interaction
        runs_possible = int(session_length_minutes / 3)
        if runs_possible >= 2 and current_resin >= 40:
            # Craft condensed for efficiency
            return CondensedDecision(
                should_craft=True,
                reason=f"Long session: craft for {runs_possible} runs efficiency",
                efficiency_gain=0.5,
            )

        return CondensedDecision(
            should_craft=False,
            reason="Original resin preferred for flexibility",
            efficiency_gain=0.0,
        )


# ---------------------------------------------------------------------------
# Resin spending executor with AR-phase domain priority (R-50)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DomainPriority:
    """Priority ranking for a domain."""
    domain_name: str
    domain_type: str  # "artifact", "talent", "weapon", "ley_line", "boss"
    priority: int     # Lower = higher priority
    ar_requirement: int
    reason: str = ""


class ResinSpendingExecutor:
    """Executes prioritized resin spending based on AR phase (R-50)."""

    def get_domain_priority(
        self,
        ar: int,
        target_set: str | None = None,
        target_slot: str | None = None,
    ) -> list[DomainPriority]:
        """Get prioritized domain list for current AR phase.

        Priority order by AR:
        - AR < 30: Boss > Talent > Weapon > Ley Line
        - AR 30-44: Talent > Weapon > Boss > Artifact
        - AR 45+: Artifact > Talent > Weapon > Boss
        """
        priorities: list[DomainPriority] = []

        if ar < 30:
            # Early phase: focus on ascension materials
            priorities.extend([
                DomainPriority("World Boss", "boss", 10, 1, "Character ascension materials"),
                DomainPriority("Talent Domain", "talent", 20, 20, "Talent book upgrades"),
                DomainPriority("Ley Line", "ley_line", 30, 1, "EXP/Mora filler"),
            ])
        elif ar < 45:
            # Mid phase: talent/weapon focus
            priorities.extend([
                DomainPriority("Talent Domain", "talent", 10, 30, "Talent upgrades priority"),
                DomainPriority("Weapon Domain", "weapon", 15, 35, "Weapon material upgrades"),
                DomainPriority("World Boss", "boss", 20, 1, "Ascension material backup"),
                DomainPriority("Artifact Domain", "artifact", 25, 45, "Pre-AR45 4-star focus"),
            ])
        else:
            # Late phase: artifact focus
            priorities.extend([
                DomainPriority("Artifact Domain", "artifact", 5, 45, "5-star artifact farming"),
                DomainPriority("Talent Domain", "talent", 10, 30, "Talent book upgrades"),
                DomainPriority("Weapon Domain", "weapon", 15, 35, "Weapon refinement materials"),
                DomainPriority("World Boss", "boss", 20, 1, "Ascension material backup"),
            ])

        return sorted(priorities, key=lambda p: p.priority)

    def recommend_spending(
        self,
        available_resin: int,
        ar: int,
        fragile_count: int = 0,
    ) -> list[tuple[str, int, str]]:
        """Recommend how to spend resin optimally.

        Returns list of (domain_type, resin_amount, reason).
        """
        recommendations: list[tuple[str, int, str]] = []
        remaining = available_resin + (fragile_count * 60)
        priorities = self.get_domain_priority(ar)

        for domain in priorities:
            if remaining < 20:
                break

            if domain.domain_type == "artifact":
                # Use fragile resin for artifact domains (AR45+)
                if ar >= 45 and fragile_count > 0:
                    uses = min(remaining // 20, fragile_count)
                    recommendations.append((domain.domain_type, uses * 20, domain.reason))
                    remaining -= uses * 20
            elif domain.domain_type in ("talent", "weapon"):
                # Use regular resin for talent/weapon
                uses = remaining // 20
                if uses > 0:
                    recommendations.append((domain.domain_type, uses * 20, domain.reason))
                    remaining -= uses * 20
            elif domain.domain_type == "boss":
                # Boss costs 40
                if remaining >= 40:
                    uses = remaining // 40
                    recommendations.append((domain.domain_type, uses * 40, domain.reason))
                    remaining -= uses * 40

        return recommendations


# ---------------------------------------------------------------------------
# Fragile resin management (M-19, M-32, M-34)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FragileResinAlert:
    """Alert about fragile resin usage or expiration."""
    alert_type: str            # "artifact_priority", "expiration_risk", "breakthrough_pending"
    priority: int              # Alert priority
    recommendation: str
    details: str = ""


class FragileResinManager:
    """Manages fragile resin decisions (M-19, M-32, M-34).

    - M-19: Prioritize fragile resin for artifact domains at AR45+
    - M-32: Warn about fragile resin expiration risk
    - M-34: Detect breakthrough nodes (70->80, 80->90)
    """

    # Breakthrough milestone levels
    BREAKTHROUGH_LEVELS: tuple[int, ...] = (20, 40, 50, 60, 70, 80, 90)

    # Expires at AR45 (when artifact domains unlock)
    FRAGILE_RESIN_EXPIRES_AT_AR = 45
    FRAGILE_RESIN_SHELF_LIFE_DAYS = 30  # Approximate

    def __init__(self) -> None:
        self._fragile_resin_count = 0
        self._fragile_resin_acquired_date: str = ""

    @property
    def fragile_count(self) -> int:
        return self._fragile_resin_count

    def set_fragile_count(self, count: int) -> None:
        self._fragile_resin_count = count

    def should_use_fragile_for_artifacts(self, ar: int, artifact_gap: int = 0) -> bool:
        """M-19: Should fragile resin be used for artifact domains (AR45+)?."""
        if ar < self.FRAGILE_RESIN_EXPIRES_AT_AR:
            return False
        # Use fragile for artifacts if significant gap exists
        return artifact_gap > 5 or self._fragile_resin_count >= 3

    def check_expiration_risk(
        self,
        current_ar: int,
        current_level: int,
        days_since_acquired: int = 0,
    ) -> FragileResinAlert | None:
        """M-32: Check if fragile resin is at risk of expiration.

        Fragile resin should be used before:
        1. AR reaches 45 (artifact farming becomes priority)
        2. Shelf life expires
        """
        # Risk if we have fragile resin and haven't reached AR45
        if self._fragile_resin_count > 0 and current_ar < self.FRAGILE_RESIN_EXPIRES_AT_AR:
            # Check if we're approaching AR45
            ar_gap = self.FRAGILE_RESIN_EXPIRES_AT_AR - current_ar
            if ar_gap <= 5:
                return FragileResinAlert(
                    alert_type="expiration_risk",
                    priority=15,
                    recommendation="Use fragile resin soon - approaching AR45",
                    details=f"AR45 in ~{ar_gap} levels. Artifact priority will increase.",
                )

        # Shelf life warning
        if days_since_acquired >= self.FRAGILE_RESIN_SHELF_LIFE_DAYS - 5:
            return FragileResinAlert(
                alert_type="expiration_risk",
                priority=20,
                recommendation="Fragile resin shelf life expiring soon",
                details=f"Acquired {days_since_acquired} days ago",
            )

        return None

    def check_breakthrough_pending(
        self,
        current_level: int,
        target_levels: dict[str, int],
    ) -> FragileResinAlert | None:
        """M-34: Check if character is near breakthrough levels (70->80, 80->90).

        These are critical nodes where ascension materials become more expensive.
        """
        # Check character levels
        for level in (70, 80):
            if level - 5 <= current_level <= level:
                return FragileResinAlert(
                    alert_type="breakthrough_pending",
                    priority=10,
                    recommendation=f"Breakthrough node approaching: level {level}",
                    details=f"Current: {current_level}, Target: {level}. Stock ascension materials.",
                )

        return None

    def recommend_fragile_usage(
        self,
        ar: int,
        current_level: int,
        pending_resin: int,
    ) -> list[str]:
        """Generate recommendations for fragile resin usage."""
        recommendations: list[str] = []

        if ar < 45:
            recommendations.append("Save fragile resin for AR45+ artifact farming")
        else:
            recommendations.append("Use fragile resin for artifact domains (AR45+)")

        if self.check_breakthrough_pending(current_level, {}):
            recommendations.append("Prioritize ascension material domains for breakthrough")

        # Check if regular resin is sufficient
        if pending_resin >= 120:
            recommendations.append("Consider using 1 fragile resin to clear excess regular")
        else:
            recommendations.append("Wait until you accumulate more regular resin")

        return recommendations


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ResinPriority(Enum):
    WEEKLY_BOSS = 0      # 30 resin, best ROI
    TALENT_DOMAIN = 1    # time-gated by day
    WEAPON_DOMAIN = 2
    ARTIFACT_DOMAIN = 3  # AR45+ only
    BOSS_MATERIAL = 4    # 40 resin, character ascension
    LEY_LINE = 5         # mora/exp, filler


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ResinState:
    """Tracks resin recovery and spending."""
    current: int = 0
    max_resin: int = RESIN_MAX
    last_updated: float = 0.0  # timestamp of last known value
    condensed_available: int = 0

    def estimate_current(self, now: float) -> int:
        """Estimate current resin based on recovery since last update."""
        if self.last_updated <= 0:
            return min(self.current, self.max_resin)
        elapsed_min = (now - self.last_updated) / 60.0
        recovered = int(elapsed_min / RESIN_RECOVERY_MINUTES)
        return min(self.current + recovered, self.max_resin)

    def minutes_until_full(self, now: float) -> float:
        """Minutes until resin reaches max."""
        current = self.estimate_current(now)
        deficit = self.max_resin - current
        return max(0.0, deficit * RESIN_RECOVERY_MINUTES)

    def update(self, amount: int, timestamp: float) -> None:
        self.current = amount
        self.last_updated = timestamp

    def spend(self, amount: int, now: float) -> bool:
        current = self.estimate_current(now)
        if current < amount:
            return False
        self.current = current - amount
        self.last_updated = now
        return True


@dataclass(slots=True)
class MoraBudget:
    """Tracks mora income and spending."""
    current: int = 0
    reserved: int = 0  # reserved for planned upgrades
    daily_income: int = 0

    @property
    def available(self) -> int:
        return max(0, self.current - self.reserved)

    def reserve(self, amount: int, reason: str = "") -> bool:
        if self.available >= amount:
            self.reserved += amount
            log.info("[MoraBudget] reserved %d for %s", amount, reason)
            return True
        return False

    def spend(self, amount: int, reason: str = "") -> bool:
        if self.current >= amount:
            self.current -= amount
            if self.reserved > 0:
                self.reserved = max(0, self.reserved - amount)
            log.info("[MoraBudget] spent %d on %s (remaining: %d)", amount, reason, self.current)
            return True
        return False

    def add_income(self, amount: int, source: str = "") -> None:
        self.current += amount
        log.info("[MoraBudget] +%d from %s (total: %d)", amount, source, self.current)


@dataclass(slots=True, frozen=True)
class FoodItem:
    item_id: str
    name: str
    effect: str          # "heal", "revive", "atk_buff", "def_buff", "crit_buff"
    potency: str         # "minor", "moderate", "major"
    craft_materials: dict[str, int] = field(default_factory=dict)


# Key foods for autonomous play
CRITICAL_FOODS: dict[str, FoodItem] = {
    "sweet_madame": FoodItem("sweet_madame", "Sweet Madame", "heal", "moderate",
                             {"fowl": 2, "sweet_flower": 1}),
    "mushroom_pizza": FoodItem("mushroom_pizza", "Mushroom Pizza", "heal", "major",
                               {"mushroom": 4, "flour": 3, "cabbage": 2, "cheese": 1}),
    "mondstadt_hash_brown": FoodItem("mondstadt_hash_brown", "Mondstadt Hash Brown", "heal", "major",
                                     {"pinecone": 2, "potato": 1, "jam": 1}),
    "sticky_honey_roast": FoodItem("sticky_honey_roast", "Sticky Honey Roast", "atk_buff", "moderate",
                                   {"carrot": 2, "raw_meat": 2, "sugar": 1}),
    "tea_break_pancake": FoodItem("tea_break_pancake", "Tea Break Pancake", "revive", "minor",
                                  {"berry": 3, "flour": 2, "bird_egg": 1}),
    "tianshu_meat": FoodItem("tianshu_meat", "Tianshu Meat", "atk_buff", "major",
                             {"raw_meat": 4, "sugar": 2, "matsutake": 1, "jueyun_chili": 1}),
}


@dataclass(slots=True)
class FoodStock:
    """Tracks food inventory with thresholds."""
    items: dict[str, int] = field(default_factory=dict)
    thresholds: dict[str, int] = field(default_factory=lambda: {
        "heal": 10,
        "revive": 5,
        "atk_buff": 5,
        "def_buff": 3,
        "crit_buff": 3,
    })

    def count(self, effect: str) -> int:
        total = 0
        for item_id, qty in self.items.items():
            food = CRITICAL_FOODS.get(item_id)
            if food and food.effect == effect:
                total += qty
        return total

    def is_below_threshold(self, effect: str) -> bool:
        return self.count(effect) < self.thresholds.get(effect, 5)

    def lowest_effect(self) -> str | None:
        """Return the effect category most in need of restocking."""
        worst: str | None = None
        worst_ratio = 999.0
        for effect, threshold in self.thresholds.items():
            current = self.count(effect)
            if threshold > 0:
                ratio = current / threshold
                if ratio < worst_ratio:
                    worst_ratio = ratio
                    worst = effect
        return worst

    def needs_cooking(self) -> list[tuple[str, int]]:
        """Return list of (food_id, count_to_cook) for foods below threshold."""
        result: list[tuple[str, int]] = []
        for item_id, food in CRITICAL_FOODS.items():
            current = self.items.get(item_id, 0)
            threshold = self.thresholds.get(food.effect, 5)
            if current < threshold:
                result.append((item_id, threshold - current))
        return result


# ---------------------------------------------------------------------------
# Primogem budget (W-08: wish strategy)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PrimogemBudget:
    """Tracks primogem income and wish strategy."""
    current: int = 0
    pity_4star: int = 0    # pulls since last 4-star
    pity_5star: int = 0    # pulls since last 5-star
    guaranteed: bool = False  # guaranteed featured 5-star
    intertwined_fates: int = 0
    acquaint_fates: int = 0

    @property
    def total_wishes_available(self) -> int:
        return self.intertwined_fates + (self.current // 160)

    @property
    def pulls_until_hard_pity(self) -> int:
        return max(0, 90 - self.pity_5star)

    def is_near_pity(self, threshold: int = 20) -> bool:
        return self.pity_5star >= (90 - threshold)

    def should_pull(self) -> bool:
        """F2P strategy: only pull when near pity or have enough for guarantee."""
        return self.total_wishes_available >= 60 or self.is_near_pity(30)


# ---------------------------------------------------------------------------
# ResourceManager: unified resource tracking
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ResourceSnapshot:
    """Complete snapshot of all game resources."""
    mora: MoraBudget
    resin: ResinState
    primogems: PrimogemBudget
    food: FoodStock
    materials: dict[str, int] = field(default_factory=dict)  # material_id -> count
    timestamp: float = 0.0


class ResourceManager:
    """Central resource tracking and decision engine.

    Integrates with:
    - StateBus for observation-driven updates
    - StrategicDecisionEngine for priority-based spending
    - CharacterBuildPlanner for material gap analysis
    """

    def __init__(self) -> None:
        self._resin = ResinState()
        self._mora = MoraBudget()
        self._primogems = PrimogemBudget()
        self._food = FoodStock()
        self._materials: dict[str, int] = {}

    @property
    def resin(self) -> ResinState:
        return self._resin

    @property
    def mora(self) -> MoraBudget:
        return self._mora

    @property
    def primogems(self) -> PrimogemBudget:
        return self._primogems

    @property
    def food(self) -> FoodStock:
        return self._food

    def snapshot(self, now: float) -> ResourceSnapshot:
        return ResourceSnapshot(
            mora=self._mora,
            resin=self._resin,
            primogems=self._primogems,
            food=self._food,
            materials=dict(self._materials),
            timestamp=now,
        )

    def update_material(self, material_id: str, count: int) -> None:
        self._materials[material_id] = count

    def get_material(self, material_id: str) -> int:
        return self._materials.get(material_id, 0)

    def resin_spending_priority(self, ar: int) -> list[ResinPriority]:
        """Return ordered resin spending priorities based on AR."""
        if ar < 30:
            return [
                ResinPriority.WEEKLY_BOSS,
                ResinPriority.BOSS_MATERIAL,
                ResinPriority.TALENT_DOMAIN,
                ResinPriority.LEY_LINE,
            ]
        elif ar < 45:
            return [
                ResinPriority.WEEKLY_BOSS,
                ResinPriority.TALENT_DOMAIN,
                ResinPriority.WEAPON_DOMAIN,
                ResinPriority.BOSS_MATERIAL,
                ResinPriority.LEY_LINE,
            ]
        else:
            return [
                ResinPriority.WEEKLY_BOSS,
                ResinPriority.ARTIFACT_DOMAIN,
                ResinPriority.TALENT_DOMAIN,
                ResinPriority.WEAPON_DOMAIN,
                ResinPriority.BOSS_MATERIAL,
                ResinPriority.LEY_LINE,
            ]

    def should_craft_condensed(self, now: float) -> bool:
        """Check if we should craft condensed resin (requires 40 resin + crystal core)."""
        current = self._resin.estimate_current(now)
        return current >= 40 and self._resin.condensed_available < 5

    def food_preparation_plan(self) -> list[tuple[str, int]]:
        """Generate a cooking plan based on current food stock."""
        return self._food.needs_cooking()

    def material_synthesis_plan(self, target_materials: dict[str, int]) -> list[tuple[str, int]]:
        """Plan 3:1 material synthesis from lower-tier to higher-tier.

        Returns list of (lower_tier_material, count_needed).
        """
        plan: list[tuple[str, int]] = []
        for mat_id, needed in target_materials.items():
            owned = self._materials.get(mat_id, 0)
            deficit = needed - owned
            if deficit <= 0:
                continue
            # Check if we can synthesize from lower tier
            lower_tier = mat_id + "_lower"  # convention: append _lower
            lower_owned = self._materials.get(lower_tier, 0)
            synthesize_count = min(deficit, lower_owned // 3)
            if synthesize_count > 0:
                plan.append((lower_tier, synthesize_count * 3))
        return plan


# ---------------------------------------------------------------------------
# Monthly shop purchases (M-05, W-05, W-06)
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class MonthlyPurchase:
    item_id: str
    name: str
    cost_currency: str    # "stardust", "starglitter"
    cost_amount: int
    available_count: int  # monthly stock
    priority: int         # lower = higher priority


MONTHLY_SHOP_PURCHASES: tuple[MonthlyPurchase, ...] = (
    MonthlyPurchase("intertwined_fate_dust", "Intertwined Fate", "stardust", 75, 5, 0),
    MonthlyPurchase("acquaint_fate_dust", "Acquaint Fate", "stardust", 75, 5, 1),
    MonthlyPurchase("intertwined_fate_glitter", "Intertwined Fate", "starglitter", 5, 2, 2),
)


def get_monthly_purchases(stardust: int, starglitter: int) -> list[MonthlyPurchase]:
    """Return affordable monthly purchases sorted by priority."""
    result: list[MonthlyPurchase] = []
    for item in MONTHLY_SHOP_PURCHASES:
        if item.cost_currency == "stardust" and stardust >= item.cost_amount:
            result.append(item)
        elif item.cost_currency == "starglitter" and starglitter >= item.cost_amount:
            result.append(item)
    return sorted(result, key=lambda x: x.priority)


# ---------------------------------------------------------------------------
# M-33: Domain efficiency data table
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class DomainEfficiency:
    """Efficiency metrics for a domain."""
    domain_name: str
    domain_type: str             # "artifact", "talent", "weapon", "ley_line", "boss"
    region: str
    resin_cost: int
    # Mora efficiency
    mora_per_resin: float = 0.0
    # EXP efficiency
    exp_per_resin: float = 0.0
    # Material drop rate
    material_drop_rate: float = 0.0  # Expected drops per run
    # Overall score (higher = more efficient for F2P)
    efficiency_score: float = 0.0
    notes: str = ""


# Domain efficiency data (empirical from community tests)
DOMAIN_EFFICIENCY_TABLE: dict[str, DomainEfficiency] = {
    # Artifact domains (AR45+)
    "momiji_duty": DomainEfficiency(
        domain_name="Momiji-Duty",
        domain_type="artifact",
        region="Inazuma",
        resin_cost=20,
        mora_per_resin=12000.0,
        exp_per_resin=5000.0,
        material_drop_rate=0.0,  # No material drops
        efficiency_score=8.5,
        notes="Emblem + Shimenawa - best DPS artifact set",
    ),
    "slumbering_court": DomainEfficiency(
        domain_name="Slumbering Court",
        domain_type="artifact",
        region="Inazuma",
        resin_cost=20,
        mora_per_resin=10000.0,
        exp_per_resin=4800.0,
        material_drop_rate=0.0,
        efficiency_score=7.5,
        notes="Clarity + Tenacity - support sets",
    ),
    "ridge_war": DomainEfficiency(
        domain_name="Ridge Watch",
        domain_type="artifact",
        region="Liyue",
        resin_cost=20,
        mora_per_resin=11000.0,
        exp_per_resin=4500.0,
        material_drop_rate=0.0,
        efficiency_score=7.0,
        notes="Marechaussee + Heroic - niche sets",
    ),
    # Talent domains
    "cecilia_garden": DomainEfficiency(
        domain_name="Cecilia Garden",
        domain_type="talent",
        region="Mondstadt",
        resin_cost=20,
        mora_per_resin=8000.0,
        exp_per_resin=3000.0,
        material_drop_rate=0.5,  # Talent book drops
        efficiency_score=8.0,
        notes="Freedom/Resistance/Ballad - F2P accessible",
    ),
    "violet_court": DomainEfficiency(
        domain_name="Violet Court",
        domain_type="talent",
        region="Inazuma",
        resin_cost=20,
        mora_per_resin=9000.0,
        exp_per_resin=3500.0,
        material_drop_rate=0.5,
        efficiency_score=7.5,
        notes="Elegance/Transience/Light - Inazuma talents",
    ),
    # Weapon domains
    "hidden_palace": DomainEfficiency(
        domain_name="Hidden Palace of Zhou Formula",
        domain_type="weapon",
        region="Liyue",
        resin_cost=20,
        mora_per_resin=7000.0,
        exp_per_resin=2500.0,
        material_drop_rate=0.6,  # Weapon ascension materials
        efficiency_score=7.5,
        notes="Best F2P weapon domain",
    ),
    # Ley Line domains
    "ley_line_blossom": DomainEfficiency(
        domain_name="Ley Line Blossom - Experience",
        domain_type="ley_line",
        region="Any",
        resin_cost=20,
        mora_per_resin=5000.0,
        exp_per_resin=20000.0,  # Huge EXP
        material_drop_rate=0.0,
        efficiency_score=6.0,
        notes="Best for character leveling - use when overleveled",
    ),
    "ley_line_blossom_wealth": DomainEfficiency(
        domain_name="Ley Line Blossom - Wealth",
        domain_type="ley_line",
        region="Any",
        resin_cost=20,
        mora_per_resin=30000.0,  # Huge Mora
        exp_per_resin=3000.0,
        material_drop_rate=0.0,
        efficiency_score=7.0,
        notes="Best Mora farming - use when broke",
    ),
    # World bosses
    "ocean_hibrid": DomainEfficiency(
        domain_name="Oceanid",
        domain_type="boss",
        region="Mondstadt",
        resin_cost=30,
        mora_per_resin=6000.0,
        exp_per_resin=4000.0,
        material_drop_rate=1.0,  # Guaranteed ascension material
        efficiency_score=7.0,
        notes="Hydro ascension - Barbara/Fischerl",
    ),
    " Primo_Geovishap": DomainEfficiency(
        domain_name="Primo Geovishap",
        domain_type="boss",
        region="Liyue",
        resin_cost=40,
        mora_per_resin=8000.0,
        exp_per_resin=6000.0,
        material_drop_rate=1.0,
        efficiency_score=8.0,
        notes="Elemental gems - essential for ascension",
    ),
}


class DomainEfficiencyCalculator:
    """Calculates and compares domain efficiency (M-33)."""

    def get_efficiency(
        self,
        domain_name: str,
    ) -> DomainEfficiency | None:
        """Get efficiency data for a domain."""
        return DOMAIN_EFFICIENCY_TABLE.get(domain_name)

    def recommend_domain(
        self,
        goal: str,  # "mora", "exp", "materials", "mixed"
        current_ar: int,
        current_level: int,
    ) -> list[DomainEfficiency]:
        """Recommend domains based on goal and current state."""
        candidates = list(DOMAIN_EFFICIENCY_TABLE.values())

        if goal == "mora":
            candidates.sort(key=lambda x: x.mora_per_resin, reverse=True)
        elif goal == "exp":
            candidates.sort(key=lambda x: x.exp_per_resin, reverse=True)
        elif goal == "materials":
            candidates.sort(key=lambda x: x.material_drop_rate, reverse=True)
        else:
            candidates.sort(key=lambda x: x.efficiency_score, reverse=True)

        # Filter by AR requirements
        if current_ar < 45:
            candidates = [c for c in candidates if c.domain_type != "artifact"]

        return candidates[:5]

    def compare_domains(
        self,
        domain_a: str,
        domain_b: str,
    ) -> dict[str, Any]:
        """Compare two domains by efficiency metrics."""
        eff_a = DOMAIN_EFFICIENCY_TABLE.get(domain_a)
        eff_b = DOMAIN_EFFICIENCY_TABLE.get(domain_b)

        if eff_a is None or eff_b is None:
            return {"error": "Domain not found in table"}

        return {
            "domain_a": domain_a,
            "domain_b": domain_b,
            "mora_comparison": {
                domain_a: eff_a.mora_per_resin,
                domain_b: eff_b.mora_per_resin,
                "winner": domain_a if eff_a.mora_per_resin > eff_b.mora_per_resin else domain_b,
            },
            "exp_comparison": {
                domain_a: eff_a.exp_per_resin,
                domain_b: eff_b.exp_per_resin,
                "winner": domain_a if eff_a.exp_per_resin > eff_b.exp_per_resin else domain_b,
            },
            "overall_score": {
                domain_a: eff_a.efficiency_score,
                domain_b: eff_b.efficiency_score,
                "winner": domain_a if eff_a.efficiency_score > eff_b.efficiency_score else domain_b,
            },
        }


# ---------------------------------------------------------------------------
# M-20: Boss vs domain mora/EXP efficiency comparison
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EfficiencyComparison:
    """Comparison of different farming methods."""
    method_a: str
    method_b: str
    comparison_type: str  # "mora" or "exp"
    ratio: float
    recommendation: str
    reasoning: str


class BossDomainEfficiencyAnalyzer:
    """Compares boss vs domain efficiency for mora/EXP (M-20)."""

    def compare_boss_vs_domain(
        self,
        current_ar: int,
        boss_resin_cost: int = 40,
        domain_resin_cost: int = 20,
    ) -> EfficiencyComparison:
        """Compare boss vs ley line domain efficiency.

        Returns comparison with recommendation.
        """
        # Boss gives ~8k Mora per 40 resin = 200 Mora/resin
        # Domain gives ~30k Mora per 20 resin = 1500 Mora/resin

        boss_mora_per_resin = 8000 / boss_resin_cost
        domain_mora_per_resin = 30000 / domain_resin_cost

        ratio = domain_mora_per_resin / boss_mora_per_resin

        if ratio > 1.0:
            return EfficiencyComparison(
                method_a="Ley Line (Domain)",
                method_b="World Boss",
                comparison_type="mora",
                ratio=ratio,
                recommendation="Ley Line",
                reasoning=f"Ley Line gives {ratio:.1f}x more Mora per resin",
            )

        return EfficiencyComparison(
            method_a="World Boss",
            method_b="Ley Line (Domain)",
            comparison_type="mora",
            ratio=1.0 / ratio,
            recommendation="Boss",
            reasoning="Boss gives better value when Mora is not primary goal",
        )

    def recommend_resin_spending(
        self,
        current_ar: int,
        resource_need: str,  # "mora", "exp", "materials"
    ) -> list[tuple[str, int, str]]:
        """Recommend optimal resin spending for current need."""
        recommendations: list[tuple[str, int, str]] = []

        if resource_need == "mora":
            recommendations.extend([
                ("Ley Line Blossom - Wealth", 40, "Best Mora efficiency"),
                ("Artifact Domain (sell 5-star)", 40, "Secondary Mora source"),
            ])
        elif resource_need == "exp":
            recommendations.extend([
                ("Ley Line Blossom - Experience", 40, "Best EXP per resin"),
                ("Artifact Domain", 20, "Moderate EXP + artifacts"),
            ])
        elif resource_need == "materials":
            recommendations.extend([
                ("Weekly Boss (discounted)", 30, "Best material ROI"),
                ("World Boss", 40, "Character ascension materials"),
            ])

        return recommendations


# ---------------------------------------------------------------------------
# M-21: Three half-price weekly boss value evaluation
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class WeeklyBossValue:
    """Value analysis for a weekly boss."""
    boss_name: str
    material_name: str
    character: str
    primogem_value: float
    material_utility: float
    total_value_score: float


class WeeklyBossValueAnalyzer:
    """Evaluates value of 3 weekly boss runs at half price (M-21)."""

    # Weekly bosses and their value
    WEEKLY_BOSS_VALUES: dict[str, WeeklyBossValue] = {
        "andrius": WeeklyBossValue(
            boss_name="Anemo Hypostasis",
            material_name="Tail of Boreas",
            character="Xiao (Anemo)",
            primogem_value=30.0,
            material_utility=0.8,
            total_value_score=35.0,
        ),
        "childe": WeeklyBossValue(
            boss_name="Liyue Harbinger Childe",
            material_name="Tusk of Monoceros Caeli",
            character="Childe",
            primogem_value=30.0,
            material_utility=0.6,
            total_value_score=30.0,
        ),
        "azhdaha": WeeklyBossValue(
            boss_name="Liyue Dragon Azhdaha",
            material_name="Dvalin's Sorrow",
            character="Multiple (Zhongli, etc.)",
            primogem_value=30.0,
            material_utility=0.9,
            total_value_score=40.0,
        ),
        "signora": WeeklyBossValue(
            boss_name="Liyue Harbinger Signora",
            material_name="Bloodtained Liquid",
            character="Razor (Electro)",
            primogem_value=30.0,
            material_utility=0.7,
            total_value_score=35.0,
        ),
    }

    def evaluate_three_runs(self) -> dict[str, Any]:
        """Evaluate value of doing 3 weekly boss runs.

        Returns analysis of total value.
        """
        bosses = list(self.WEEKLY_BOSS_VALUES.values())
        bosses.sort(key=lambda x: x.total_value_score, reverse=True)

        # Take top 3
        top_three = bosses[:3]
        total_primogem = sum(b.material_primogem_value for b in top_three)
        total_material_value = sum(b.material_utility for b in top_three)
        total_score = sum(b.total_value_score for b in top_three)

        return {
            "recommended_bosses": [b.boss_name for b in top_three],
            "total_primogem_value": total_primogem,
            "total_material_utility": total_material_value,
            "total_value_score": total_score,
            "is_worth_discounted_resin": total_score >= 90.0,
            "reasoning": f"3 boss runs give {total_primogem} primogems + {total_material_value:.1f} material utility",
        }

    def recommend_weekly_boss_order(self) -> list[str]:
        """Recommend order to do weekly bosses."""
        sorted_bosses = sorted(
            self.WEEKLY_BOSS_VALUES.items(),
            key=lambda x: x[1].total_value_score,
            reverse=True,
        )
        return [boss_name for boss_name, _ in sorted_bosses]
