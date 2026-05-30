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
