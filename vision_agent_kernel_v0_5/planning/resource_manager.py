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
    MonthlyPurchase("intertwined_fate_dust", "Intertwined Fate", "stardust", 150, 5, 0),
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
