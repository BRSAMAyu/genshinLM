from __future__ import annotations

from dataclasses import dataclass

from core.events import Interrupt
from core.types import MovementIntent, ObstacleField, ProgressState


@dataclass(frozen=True, slots=True)
class ObstacleDecision:
    action: str
    movement_intent: MovementIntent | None
    interrupt: Interrupt | None
    reason: str


class ObstaclePolicy:
    def __init__(self, front_threshold: float = 0.55, no_progress_threshold: float = 80.0) -> None:
        self._front_threshold = front_threshold
        self._no_progress_threshold = no_progress_threshold

    def decide(
        self,
        obstacle_field: ObstacleField | None,
        progress: ProgressState | None = None,
    ) -> ObstacleDecision:
        if obstacle_field is None:
            return ObstacleDecision("continue", None, None, "no_obstacle_field")
        sectors = obstacle_field.sectors
        front = sectors.get("front", 0.0)
        if progress is not None and progress.frustration >= self._no_progress_threshold:
            interrupt = Interrupt(
                priority=2,
                timestamp=progress.timestamp,
                code="NO_TASK_PROGRESS",
                source="obstacle_policy",
                payload={"frustration": progress.frustration, "front_pressure": front},
            )
            return ObstacleDecision("ESCALATE", None, interrupt, "frustration_exhausted")
        if front < self._front_threshold:
            return ObstacleDecision("continue", None, None, "front_clear")
        left_pressure = sectors.get("front_left", 0.0) + sectors.get("left", 0.0)
        right_pressure = sectors.get("front_right", 0.0) + sectors.get("right", 0.0)
        move_right = 1.0 if left_pressure <= right_pressure else -1.0
        return ObstacleDecision(
            "LOCAL_REROUTE",
            MovementIntent(
                move_forward=0.0,
                move_right=move_right,
                duration_ms=250,
                reason=f"obstacle_front_pressure={front:.2f}",
            ),
            None,
            "front_blocked_choose_side",
        )
