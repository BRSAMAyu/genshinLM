"""Reusable recovery strategies for the navigation coordinator.

These implement the :class:`~control.navigation_coordinator.RecoveryStrategy`
protocol so both the offline sim and (later) the live capsule can share the same
behaviour. Game-agnostic: a strategy sees only the fused pose, the target, and a
reason string.
"""
from __future__ import annotations

from typing import Any

from control.navigation_coordinator import RecoveryOutput
from core.types import MovementIntent


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
