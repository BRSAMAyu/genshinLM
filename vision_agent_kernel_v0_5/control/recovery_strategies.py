"""Reusable recovery strategies for the navigation coordinator.

These implement the :class:`~control.navigation_coordinator.RecoveryStrategy`
protocol so both the offline sim and (later) the live capsule can share the same
behaviour. Game-agnostic: a strategy sees only the fused pose, the target, and a
reason string.
"""
from __future__ import annotations

from typing import Any, Protocol

from control.navigation_coordinator import RecoveryOutput
from core.types import MovementIntent


class _KnowledgeStore(Protocol):
    """Structural subset of learning.game_knowledge_store.GameKnowledgeStore."""

    def get(self, category: str, subject: str, attribute: str, game_id: str = "") -> Any:
        ...


class ArcGoAroundRecovery:
    """Arc around a blockage instead of backing straight off.

    Commits to one side and strafes with a slight forward bias so the agent
    *arcs* past the obstacle while still making net progress toward the target.
    Flips side only after a sustained unsuccessful arc, so it doesn't cancel
    itself out by alternating every tick (the bug the Phase 1 dogfood surfaced:
    alternating tiny strafes left the agent oscillating until timeout).
    """

    def __init__(
        self,
        *,
        strafe: float = 0.9,
        forward_bias: float = 0.2,
        flip_after: int = 12,
        duration_ms: int = 200,
    ) -> None:
        self._strafe = strafe
        self._forward_bias = forward_bias
        self._flip_after = max(1, flip_after)
        self._duration_ms = duration_ms
        self._side = 1.0
        self._calls = 0

    def reset(self) -> None:
        self._side = 1.0
        self._calls = 0

    def recover(self, reason: str, pose: Any, target: Any) -> RecoveryOutput:
        self._calls += 1
        if self._calls % self._flip_after == 0:
            self._side *= -1.0
        return RecoveryOutput(
            movement=MovementIntent(
                move_forward=self._forward_bias,
                move_right=self._strafe * self._side,
                duration_ms=self._duration_ms,
                reason=f"arc_goaround_{reason}",
            ),
            resolved=False,
            reason=f"arc go-around ({reason})",
        )


# Mapping from a learned failure category to the maneuver that category's
# suggested_fix text implies. Keeps the read-side of the learning loop game-agnostic.
_CATEGORY_MANEUVER = {
    "navigation_failed": ("backstep_then_strafe", -0.4, 0.9),
    "stuck_state": ("backstep_then_strafe", -0.4, 0.9),
    "hp_depleted": ("retreat", -0.8, 0.0),
    "combat_timeout": ("reposition", -0.3, 0.6),
    "puzzle_failed": ("backstep_then_strafe", -0.3, 0.7),
}


class KnowledgeAwareRecovery:
    """Recovery strategy that CONSULTS learned failure knowledge.

    Closes the trial-and-error -> learning loop's read side: on a recovery event
    it queries the :class:`GameKnowledgeStore` for a ``failure_pattern`` fact
    matching the failure category, and if one exists, applies the maneuver that
    category's learned ``suggested_fix`` implies — otherwise falls back to a base
    strategy. Without this, the learning bridge is write-only (facts stored,
    never read), so the "self-improvement loop" never actually changes behavior.
    """

    def __init__(
        self,
        store: _KnowledgeStore,
        fallback: "ArcGoAroundRecovery | None" = None,
        *,
        game_id: str = "genshin",
        category_map: dict[str, tuple[str, float, float]] | None = None,
    ) -> None:
        self._store = store
        self._fallback = fallback or ArcGoAroundRecovery()
        self._game_id = game_id
        self._category_map = category_map or dict(_CATEGORY_MANEUVER)
        self._consulted = 0

    @property
    def consulted_count(self) -> int:
        """How many times a learned fact actually drove a maneuver (for tests)."""
        return self._consulted

    def recover(self, reason: str, pose: Any, target: Any) -> RecoveryOutput:
        category = self._category_for(reason)
        fact = None
        if category is not None:
            fact = self._store.get(
                category="failure_pattern", subject=category,
                attribute="suggested_fix", game_id=self._game_id,
            )
        if fact is not None and category in self._category_map:
            self._consulted += 1
            maneuver, forward, right = self._category_map[category]
            return RecoveryOutput(
                movement=MovementIntent(
                    move_forward=forward, move_right=right,
                    duration_ms=200, reason=f"learned:{maneuver}:{category}",
                ),
                resolved=False,
                reason=f"applied learned fix for {category}",
            )
        # No learned knowledge yet — use the base go-around.
        return self._fallback.recover(reason, pose, target)

    def _category_for(self, reason: str) -> str | None:
        reason_l = reason.lower()
        for cat in self._category_map:
            if cat.split("_")[0] in reason_l or cat in reason_l:
                return cat
        # Map coordinator reasons to categories.
        if "stuck" in reason_l:
            return "stuck_state"
        if "lost" in reason_l or "navigation" in reason_l:
            return "navigation_failed"
        return None
