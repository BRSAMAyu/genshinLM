"""Realm manager v2: Serenitea Pot (Realm) system optimization.

Covers S-39: Managing Serenitea Pot realm currency, trust rank,
furnishing placement, and expedition optimization.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Realm types
# ---------------------------------------------------------------------------

class RealmType(str, Enum):
    NATIVE_PLATEAU = "native_plateau"      # Initial realm
    GOLDEN_NARCHESS = "golden_narchess"     # Unlocked with housing system


# ---------------------------------------------------------------------------
# Realm data
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RealmCurrency:
    """Current realm currency state."""
    realm_currency: int = 0
    max_currency: int = 2400
    hours_to_full: float = 72.0

    @property
    def should_collect(self) -> bool:
        return self.realm_currency >= self.max_currency * 0.8

    @property
    def fill_pct(self) -> float:
        return (self.realm_currency / max(self.max_currency, 1)) * 100.0


@dataclass(slots=True)
class RealmState:
    """Complete realm state."""
    realm_type: RealmType
    trust_rank: int = 0
    max_trust_rank: int = 10
    currency: RealmCurrency
    active_expeditions: int = 0
    max_expeditions: int = 4
    furnishings_placed: int = 0
    load_limit: float = 0.0


# ---------------------------------------------------------------------------
# Realm manager
# ---------------------------------------------------------------------------

class RealmManagerV2:
    """Manages Serenitea Pot realm system.

    Handles:
    1. Currency collection scheduling
    2. Trust rank progression
    3. Furnishing optimization
    4. Expedition management
    """

    # Currency collection intervals
    COLLECT_INTERVAL_HOURS = 8.0  # Collect every 8 hours
    OPTIMAL_COLLECT_THRESHOLD = 2000  # Collect when > 2000

    def __init__(self) -> None:
        self._state = RealmState(
            realm_type=RealmType.NATIVE_PLATEAU,
            currency=RealmCurrency(),
        )

    @property
    def state(self) -> RealmState:
        return self._state

    def should_collect_currency(self, current_time: float) -> bool:
        """Check if realm currency should be collected."""
        currency = self._state.currency
        if currency.realm_currency >= self.OPTIMAL_COLLECT_THRESHOLD:
            return True
        if currency.realm_currency >= currency.max_currency * 0.9:
            return True
        return False

    def collect_currency(self) -> dict[str, Any]:
        """Collect realm currency.

        Returns:
            Result dict with currency collected
        """
        currency = self._state.currency
        collected = currency.realm_currency
        currency.realm_currency = 0

        log.info("[RealmV2] collected %d realm currency", collected)
        return {
            "collected": collected,
            "new_balance": 0,
        }

    def get_expedition_recommendations(
        self,
        available_characters: list[str],
    ) -> list[dict[str, Any]]:
        """Get optimal expedition assignments.

        Returns list of recommended character -> expedition mappings.
        """
        recommendations = []
        slots = self._state.max_expeditions - self._state.active_expeditions

        for i, char_id in enumerate(available_characters[:slots]):
            recommendations.append({
                "character": char_id,
                "expedition_id": f"expedition_{i + 1}",
                "expected_reward": 300 + (i * 50),
                "duration_hours": 4.0 + (i * 2),
            })

        return recommendations

    def get_trust_rank_progress(self) -> dict[str, Any]:
        """Get trust rank progress and recommendations."""
        current = self._state.trust_rank
        max_rank = self._state.max_trust_rank

        # Trust rank thresholds
        trust_thresholds = [0, 600, 1800, 3600, 6000, 9000, 12000, 18000, 24000, 30000]

        current_threshold = trust_thresholds[current] if current < len(trust_thresholds) else 0
        next_threshold = trust_thresholds[current + 1] if current + 1 < len(trust_thresholds) else 0

        return {
            "current_rank": current,
            "max_rank": max_rank,
            "current_trust": current_threshold,
            "next_rank_trust": next_threshold,
            "progress_pct": ((current_threshold / max(next_threshold, 1)) * 100.0) if next_threshold > 0 else 100.0,
        }


# ---------------------------------------------------------------------------
# Realm flow
# ---------------------------------------------------------------------------

class RealmFlow:
    """Predefined flows for realm operations."""

    COLLECT_CURRENCY_FLOW = (
        "interact_statue",
        "wait_state:realm_menu",
        "click:0.30,0.30",  # Click realm tab
        "click:0.50,0.50",  # Collect
        "wait:1000",
        "press:escape",
    )

    START_EXPEDITION_FLOW = (
        "interact_statue",
        "wait_state:realm_menu",
        "click:0.30,0.70",  # Click expedition
        "click:0.50,0.50",  # Select slot
        "select_character",
        "confirm",
    )