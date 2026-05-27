"""SentinelRuntime — persistent watchdog that monitors and recovers.

The sentinel:
1. Receives SomaticState snapshots periodically
2. Detects anomalies (stuck, lost, low HP, etc.)
3. Selects and executes appropriate recovery recipe
4. Verifies restabilization
5. Writes claims and BAGEL feedback
6. Enforces budget to prevent infinite recovery loops
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from control.sentinel.recovery_recipe import RecoveryRecipe, RecoveryResult
from control.sentinel.recipes import default_recipes
from control.sentinel.somatic_state import SomaticState

log = logging.getLogger(__name__)


@dataclass(slots=True)
class SentinelEvent:
    """Record of a sentinel intervention."""
    event_id: str
    recipe_id: str
    snapshot: SomaticState
    result: RecoveryResult | None = None
    timestamp: float = 0.0
    budget_used: int = 0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            object.__setattr__(self, "timestamp", time.perf_counter())


class SentinelRuntime:
    """Persistent watchdog for anomaly detection and recovery.

    Thread-safe. Monitors somatic state and triggers recovery recipes
    when anomalies are detected.
    """

    def __init__(
        self,
        recipes: list[RecoveryRecipe] | None = None,
        max_global_budget: int = 10,
    ) -> None:
        self._recipes = recipes or default_recipes()
        self._max_global_budget = max_global_budget
        self._global_budget_used = 0
        self._history: list[SentinelEvent] = []
        self._lock = threading.Lock()
        self._last_snapshot: SomaticState | None = None

    @property
    def budget_remaining(self) -> int:
        return self._max_global_budget - self._global_budget_used

    @property
    def interventions(self) -> list[SentinelEvent]:
        return list(self._history)

    def update_snapshot(self, snapshot: SomaticState) -> None:
        """Update the current somatic state snapshot."""
        with self._lock:
            self._last_snapshot = snapshot

    def detect_anomaly(self, snapshot: SomaticState) -> RecoveryRecipe | None:
        """Check if any recovery recipe's precondition is met."""
        for recipe in self._recipes:
            if recipe.check_precondition(snapshot):
                return recipe
        return None

    def intervene(self, snapshot: SomaticState) -> SentinelEvent | None:
        """Detect anomaly and execute recovery if needed.

        Returns a SentinelEvent if intervention occurred, None if healthy.
        Thread-safe: anomaly detection and budget check are atomic.
        """
        with self._lock:
            recipe = self.detect_anomaly(snapshot)
            if recipe is None:
                return None

            if self._global_budget_used >= self._max_global_budget:
                log.warning("[Sentinel] Global budget exhausted (%d)", self._max_global_budget)
                event = SentinelEvent(
                    event_id=f"sentinel_{int(time.perf_counter())}",
                    recipe_id="BUDGET_EXHAUSTED",
                    snapshot=snapshot,
                    result=RecoveryResult("BUDGET_EXHAUSTED", "budget_exhausted"),
                    budget_used=self._global_budget_used,
                )
                self._history.append(event)
                return event

            event = SentinelEvent(
                event_id=f"sentinel_{int(time.perf_counter())}",
                recipe_id=recipe.recipe_id,
                snapshot=snapshot,
            )

            result = recipe.execute_recovery()
            event.result = result

            if result.status == "success":
                recipe.verify_restabilized()

            self._global_budget_used += 1
            event.budget_used = self._global_budget_used
            self._history.append(event)

            return event

    def reset_budget(self) -> None:
        """Reset global budget (e.g., after successful mission completion)."""
        with self._lock:
            self._global_budget_used = 0

    def reset(self) -> None:
        """Full reset for new session."""
        with self._lock:
            self._global_budget_used = 0
            self._history.clear()
            self._last_snapshot = None
