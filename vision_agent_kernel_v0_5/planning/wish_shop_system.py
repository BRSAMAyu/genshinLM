"""Wish (gacha) and shop system: pity tracking, monthly purchases, wish strategy.

Manages the gacha system for F2P progression, tracking pity counters,
recommending wish timing, and automating monthly shop purchases.
Covers W-01 through W-08.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pity system
# ---------------------------------------------------------------------------

HARD_PITY_5STAR = 90     # guaranteed 5-star at 90 pulls
SOFT_PITY_START = 74     # soft pity begins, rates increase
HARD_PITY_4STAR = 10     # guaranteed 4-star at 10 pulls
GOLDEN_RATIO = 0.006     # base 5-star rate (0.6%)
BASE_4STAR_RATE = 0.051  # base 4-star rate (5.1%)


class WishRarity(Enum):
    THREE_STAR = 3
    FOUR_STAR = 4
    FIVE_STAR = 5


@dataclass(slots=True)
class PityCounter:
    """Tracks pity for a single banner."""
    banner_name: str
    pulls_since_5star: int = 0
    pulls_since_4star: int = 0
    total_pulls: int = 0
    guaranteed_featured: bool = False  # 50/50 lost = guaranteed next
    history: list[WishRarity] = field(default_factory=list)

    @property
    def pulls_until_hard_pity(self) -> int:
        return max(0, HARD_PITY_5STAR - self.pulls_since_5star)

    @property
    def pulls_until_4star(self) -> int:
        return max(0, HARD_PITY_4STAR - self.pulls_since_4star)

    @property
    def is_soft_pity(self) -> bool:
        return self.pulls_since_5star >= SOFT_PITY_START

    @property
    def estimated_5star_rate(self) -> float:
        """Estimate current 5-star rate based on soft pity."""
        if self.pulls_since_5star < SOFT_PITY_START:
            return GOLDEN_RATIO
        # Soft pity increases rate ~6% per pull after 74
        extra = (self.pulls_since_5star - SOFT_PITY_START) * 0.06
        return min(1.0, GOLDEN_RATIO + extra)

    def record_pull(self, rarity: WishRarity) -> None:
        self.total_pulls += 1
        self.history.append(rarity)
        if len(self.history) > 200:
            self.history = self.history[-200:]
        if rarity == WishRarity.FIVE_STAR:
            self.pulls_since_5star = 0
            # 50/50 or guaranteed
        else:
            self.pulls_since_5star += 1
        if rarity == WishRarity.FOUR_STAR:
            self.pulls_since_4star = 0
        else:
            self.pulls_since_4star += 1

    def record_5050_won(self) -> None:
        self.guaranteed_featured = False

    def record_5050_lost(self) -> None:
        self.guaranteed_featured = True


# ---------------------------------------------------------------------------
# Wish strategy
# ---------------------------------------------------------------------------

class WishStrategy(Enum):
    SKIP = "skip"                   # Don't pull, save for future
    PULL_IF_NEAR_PITY = "near_pity" # Only pull if within 30 of pity
    PULL_ALWAYS = "always"          # Pull whenever possible
    PULL_VALUE_ONLY = "value"       # Only pull on banners with high F2P value


@dataclass(slots=True, frozen=True)
class BannerInfo:
    """Information about a current wish banner."""
    banner_id: str
    banner_type: str           # "character", "weapon", "standard", "chronicled"
    featured_5star: str = ""
    featured_4stars: tuple[str, ...] = ()
    phase: int = 1             # 1 or 2 for character banners
    end_date: str = ""


@dataclass(slots=True)
class WishDecisionEngine:
    """Decides when and what to wish for based on F2P strategy."""
    primogems: int = 0
    intertwined_fates: int = 0
    acquaint_fates: int = 0
    stardust: int = 0
    starglitter: int = 0
    character_banner_pity: PityCounter = field(default_factory=lambda: PityCounter("character"))
    weapon_banner_pity: PityCounter = field(default_factory=lambda: PityCounter("weapon"))

    @property
    def total_wishes_available(self) -> int:
        return self.intertwined_fates + (self.primogems // 160)

    def evaluate_banner(self, banner: BannerInfo) -> dict[str, Any]:
        """Evaluate whether to pull on a banner."""
        result: dict[str, Any] = {"banner": banner.banner_id}

        # F2P rule: skip weapon banners
        if banner.banner_type == "weapon":
            result["strategy"] = WishStrategy.SKIP
            result["reason"] = "F2P should skip weapon banners"
            return result

        if banner.banner_type == "standard":
            result["strategy"] = WishStrategy.SKIP
            result["reason"] = "Use acquaint fates, don't spend primogems"
            return result

        pity = self.character_banner_pity
        wishes = self.total_wishes_available

        # Near pity: pull
        if pity.pulls_until_hard_pity <= 30:
            result["strategy"] = WishStrategy.PULL_IF_NEAR_PITY
            result["reason"] = f"Near pity ({pity.pulls_since_5star}/{HARD_PITY_5STAR})"
            result["can_guarantee"] = wishes >= pity.pulls_until_hard_pity
            return result

        # Guaranteed featured: high value
        if pity.guaranteed_featured and wishes >= pity.pulls_until_hard_pity:
            result["strategy"] = WishStrategy.PULL_IF_NEAR_PITY
            result["reason"] = "Guaranteed featured 5-star"
            result["can_guarantee"] = True
            return result

        # Not enough for guarantee: skip unless near pity
        if wishes < 60:
            result["strategy"] = WishStrategy.SKIP
            result["reason"] = f"Only {wishes} wishes, need ~160 for guarantee"
            return result

        result["strategy"] = WishStrategy.SKIP
        result["reason"] = "Save for better banners"
        return result

    def monthly_shop_plan(self) -> list[dict[str, Any]]:
        """Generate monthly Paimon's Bargains purchase plan."""
        purchases: list[dict[str, Any]] = []

        # Intertwined Fates from stardust (75 each, 5 available)
        affordable_intertwined = min(5, self.stardust // 75)
        if affordable_intertwined > 0:
            purchases.append({
                "item": "Intertwined Fate",
                "count": affordable_intertwined,
                "currency": "stardust",
                "cost": affordable_intertwined * 75,
                "priority": 0,
            })

        # Acquaint Fates from stardust (75 each, 5 available)
        remaining_stardust = self.stardust - affordable_intertwined * 75
        affordable_acquaint = min(5, remaining_stardust // 75)
        if affordable_acquaint > 0:
            purchases.append({
                "item": "Acquaint Fate",
                "count": affordable_acquaint,
                "currency": "stardust",
                "cost": affordable_acquaint * 75,
                "priority": 1,
            })

        # Starglitter: intertwined fates (5 each, 2 available)
        affordable_glitter = min(2, self.starglitter // 5)
        if affordable_glitter > 0:
            purchases.append({
                "item": "Intertwined Fate (Starglitter)",
                "count": affordable_glitter,
                "currency": "starglitter",
                "cost": affordable_glitter * 5,
                "priority": 2,
            })

        return sorted(purchases, key=lambda p: p["priority"])

    def should_buy_monthly(self) -> bool:
        """Check if monthly purchases should be made."""
        return self.stardust >= 75  # at least one acquaint fate


# ---------------------------------------------------------------------------
# Wish decision tree (M-23)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class WishDecisionTree:
    """Decision tree for limited character vs weapon banners (M-23)."""
    should_pull: bool
    banner_type: str           # "character", "weapon"
    target: str                # Featured character/weapon name
    pull_count: int            # Recommended pull count
    reasoning: str = ""
    priority_score: float = 0.0  # 0.0-1.0


class WishDecisionTreeEngine:
    """Decides between limited character and weapon banners (M-23).

    Decision tree:
    1. F2P should NEVER pull on weapon banners
    2. Character banners: only pull if guaranteed or near pity
    3. Standard banners: only use acquaints, not primogems
    4. Chronicled: evaluate based on constellation needs
    """

    # Character importance tiers for decision making
    HIGH_VALUE_CHARACTERS: frozenset[str] = frozenset({
        "bennett", "xiangling", "xingqiu", "fischl", "xianyun",
    })
    MEDIUM_VALUE_CHARACTERS: frozenset[str] = frozenset({
        "kaeya", "barbara", "noelle", "collei", "diona", "rosaria",
    })

    def evaluate_banner(
        self,
        banner_type: str,
        featured_character: str,
        pity_counter: PityCounter,
        total_wishes: int,
        is_guaranteed: bool = False,
    ) -> WishDecisionTree:
        """Evaluate a banner using the decision tree."""
        # Node 1: Weapon banner = SKIP for F2P
        if banner_type == "weapon":
            return WishDecisionTree(
                should_pull=False,
                banner_type=banner_type,
                target=featured_character,
                pull_count=0,
                reasoning="F2P should NEVER pull on weapon banners",
                priority_score=0.0,
            )

        # Node 2: Character banner evaluation
        if banner_type == "character":
            return self._evaluate_character_banner(
                featured_character, pity_counter, total_wishes, is_guaranteed
            )

        # Node 3: Standard banner
        if banner_type == "standard":
            return WishDecisionTree(
                should_pull=False,
                banner_type=banner_type,
                target=featured_character,
                pull_count=0,
                reasoning="Standard banner: use acquaints only, not primogems",
                priority_score=0.1,
            )

        # Node 4: Chronicled banner
        if banner_type == "chronicled":
            return self._evaluate_chronicled_banner(
                featured_character, pity_counter, total_wishes
            )

        return WishDecisionTree(
            should_pull=False,
            banner_type=banner_type,
            target=featured_character,
            pull_count=0,
            reasoning="Unknown banner type",
            priority_score=0.0,
        )

    def _evaluate_character_banner(
        self,
        featured_character: str,
        pity: PityCounter,
        total_wishes: int,
        is_guaranteed: bool,
    ) -> WishDecisionTree:
        """Evaluate character banner using decision tree."""
        character_value = self._get_character_value(featured_character)

        # Decision branch: guaranteed featured
        if is_guaranteed:
            if total_wishes >= pity.pulls_until_hard_pity:
                return WishDecisionTree(
                    should_pull=True,
                    banner_type="character",
                    target=featured_character,
                    pull_count=pity.pulls_until_hard_pity,
                    reasoning=f"Guaranteed featured {featured_character} - pull now",
                    priority_score=0.9 + character_value * 0.1,
                )
            else:
                return WishDecisionTree(
                    should_pull=False,
                    banner_type="character",
                    target=featured_character,
                    pull_count=0,
                    reasoning=f"Not enough wishes ({total_wishes}) for guarantee on {featured_character}",
                    priority_score=0.5 + character_value * 0.3,
                )

        # Decision branch: near pity (within 30 pulls)
        if pity.pulls_until_hard_pity <= 30:
            # High value character: pull
            if character_value >= 0.8:
                return WishDecisionTree(
                    should_pull=True,
                    banner_type="character",
                    target=featured_character,
                    pull_count=min(total_wishes, pity.pulls_until_hard_pity),
                    reasoning=f"Near pity ({pity.pulls_since_5star}/{HARD_PITY_5STAR}), {featured_character} is high value",
                    priority_score=0.8 + character_value * 0.1,
                )
            # Medium value: evaluate
            if character_value >= 0.5 and total_wishes >= 60:
                return WishDecisionTree(
                    should_pull=True,
                    banner_type="character",
                    target=featured_character,
                    pull_count=min(60, total_wishes),
                    reasoning=f"{featured_character} has medium value, near pity",
                    priority_score=0.5 + character_value * 0.3,
                )
            # Low value: skip unless guaranteed
            return WishDecisionTree(
                should_pull=False,
                banner_type="character",
                target=featured_character,
                pull_count=0,
                reasoning=f"{featured_character} is low value - save for better banners",
                priority_score=character_value * 0.3,
            )

        # Not near pity: skip unless high value and lots of wishes
        if character_value >= 0.9 and total_wishes >= 120:
            return WishDecisionTree(
                should_pull=True,
                banner_type="character",
                target=featured_character,
                pull_count=min(120, total_wishes),
                reasoning=f"Very high value {featured_character}, enough wishes for guarantee",
                priority_score=0.9,
            )

        return WishDecisionTree(
            should_pull=False,
            banner_type="character",
            target=featured_character,
            pull_count=0,
            reasoning="Not near pity - save primogems for better opportunities",
            priority_score=0.2,
        )

    def _evaluate_chronicled_banner(
        self,
        featured_character: str,
        pity: PityCounter,
        total_wishes: int,
    ) -> WishDecisionTree:
        """Evaluate chronicled banner."""
        character_value = self._get_character_value(featured_character)

        # Chronicled has no soft pity - evaluate carefully
        if character_value >= 0.8 and total_wishes >= 90:
            return WishDecisionTree(
                should_pull=True,
                banner_type="chronicled",
                target=featured_character,
                pull_count=min(90, total_wishes),
                reasoning=f"High value {featured_character} in chronicled",
                priority_score=0.7,
            )

        return WishDecisionTree(
            should_pull=False,
            banner_type="chronicled",
            target=featured_character,
            pull_count=0,
            reasoning="Chronicled banner: evaluate constellations needs first",
            priority_score=0.3,
        )

    def _get_character_value(self, character_id: str) -> float:
        """Get character value score (0.0-1.0)."""
        char_lower = character_id.lower()
        if char_lower in self.HIGH_VALUE_CHARACTERS:
            return 0.9
        if char_lower in self.MEDIUM_VALUE_CHARACTERS:
            return 0.6
        return 0.4


# ---------------------------------------------------------------------------
# M-24: Stardust priority system (星辉优先级)
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class StardustPurchase:
    """A stardust purchase option."""
    item_id: str
    item_name: str
    stardust_cost: int
    starglitter_cost: int
    is_stardust_only: bool = True
    monthly_stock: int = 5
    value_score: float = 0.0


@dataclass(slots=True)
class StardustPriorityDecision:
    """Decision on stardust/shop purchases."""
    recommended_purchases: list[StardustPurchase]
    stardust_remaining: int
    priority_order: list[str]
    total_spent: int = 0


# Stardust shop items (M-24 priority system)
STARDUST_SHOP_PRIORITY: list[StardustPurchase] = [
    StardustPurchase(
        item_id="intertwined_fate_stardust",
        item_name="Intertwined Fate",
        stardust_cost=75,
        starglitter_cost=0,
        is_stardust_only=True,
        value_score=10.0,  # High value: wish currency
    ),
    StardustPurchase(
        item_id="acquaint_fate_stardust",
        item_name="Acquaint Fate",
        stardust_cost=75,
        starglitter_cost=0,
        is_stardust_only=True,
        value_score=8.0,  # Medium value
    ),
    StardustPurchase(
        item_id="hero_wit_stardust",
        item_name="Hero's Wit",
        stardust_cost=20,
        starglitter_cost=0,
        is_stardust_only=True,
        monthly_stock=10,
        value_score=5.0,  # Lower priority - use resin instead
    ),
]

# Starglitter shop priority (M-24)
STARGLITTER_SHOP_PRIORITY: list[StardustPurchase] = [
    StardustPurchase(
        item_id="intertwined_fate_glitter",
        item_name="Intertwined Fate",
        stardust_cost=0,
        starglitter_cost=5,
        is_stardust_only=False,
        monthly_stock=2,
        value_score=9.0,  # High priority: rare wishes
    ),
    StardustPurchase(
        item_id="refined_dishes",
        item_name="Refined Dishes",
        stardust_cost=0,
        starglitter_cost=3,
        is_stardust_only=False,
        monthly_stock=3,
        value_score=4.0,  # Convenience food
    ),
]


class StardustPriorityCalculator:
    """Calculates optimal stardust/shop purchase priority (M-24)."""

    def calculate_priority(
        self,
        stardust: int,
        starglitter: int,
        intertwined_fates: int = 0,
        character_banner_pity: int = 0,
    ) -> StardustPriorityDecision:
        """Calculate optimal stardust purchase priority.

        Args:
            stardust: Current stardust amount
            starglitter: Current starglitter amount
            intertwined_fates: Current intertwined fates
            character_banner_pity: Current pity count

        Returns:
            StardustPriorityDecision with recommended purchases
        """
        purchases: list[StardustPurchase] = []
        remaining_stardust = stardust
        remaining_glitter = starglitter

        # Priority 1: Intertwined Fates (for character wishes)
        for item in STARDUST_SHOP_PRIORITY:
            if item.item_id == "intertwined_fate_stardust":
                # Buy 5 intertwined fates max
                max_buy = min(5, item.monthly_stock)
                affordable = remaining_stardust // item.stardust_cost
                buy_count = min(max_buy, affordable)
                if buy_count > 0:
                    purchases.append(item)
                    remaining_stardust -= buy_count * item.stardust_cost

        # Priority 2: Acquaint Fates
        for item in STARDUST_SHOP_PRIORITY:
            if item.item_id == "acquaint_fate_stardust":
                max_buy = min(5, item.monthly_stock)
                affordable = remaining_stardust // item.stardust_cost
                buy_count = min(max_buy, affordable)
                if buy_count > 0:
                    purchases.append(item)
                    remaining_stardust -= buy_count * item.stardust_cost

        # Priority 3: Starglitter Intertwined Fates (if near pity)
        if character_banner_pity >= 60 or intertwined_fates >= 10:
            for item in STARGLITTER_SHOP_PRIORITY:
                if item.item_id == "intertwined_fate_glitter":
                    max_buy = min(item.monthly_stock, remaining_glitter // item.starglitter_cost)
                    if max_buy > 0:
                        purchases.append(item)
                        remaining_glitter -= max_buy * item.starglitter_cost

        total_spent = stardust - remaining_stardust + starglitter - remaining_glitter

        return StardustPriorityDecision(
            recommended_purchases=purchases,
            stardust_remaining=remaining_stardust,
            priority_order=[p.item_name for p in purchases],
            total_spent=total_spent,
        )


# ---------------------------------------------------------------------------
# U-65: Star glitter refresh detection
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ShopRefreshState:
    """Tracks shop refresh state."""
    last_refresh: str = ""  # ISO date
    stardust_count: int = 0
    starglitter_count: int = 0
    monthly_items_bought: dict[str, int] = field(default_factory=dict)


class ShopRefreshDetector:
    """Detects when the Paimon's Bargains shop has refreshed (U-65).

    Shop resets monthly on 1st day of each month.
    """

    MONTHLY_RESET_DAY = 1  # First day of month

    def check_refresh(self, current_day: int, last_known_day: int) -> bool:
        """Check if shop has refreshed.

        Returns True if refresh detected.
        """
        if current_day == self.MONTHLY_RESET_DAY and last_known_day != self.MONTHLY_RESET_DAY:
            return True
        return False

    def get_monthly_items_status(
        self,
        bought_counts: dict[str, int],
        max_stocks: dict[str, int],
    ) -> dict[str, Any]:
        """Get status of monthly shop items.

        Returns which items are still available.
        """
        available: list[str] = []
        sold_out: list[str] = []

        for item_id, bought in bought_counts.items():
            max_stock = max_stocks.get(item_id, 0)
            if bought < max_stock:
                available.append(item_id)
            else:
                sold_out.append(item_id)

        return {
            "available_items": available,
            "sold_out_items": sold_out,
            "needs_refresh": len(available) == 0,
        }
