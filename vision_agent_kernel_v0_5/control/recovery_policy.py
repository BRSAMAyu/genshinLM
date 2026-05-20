from __future__ import annotations

from dataclasses import dataclass

from core.events import Interrupt
from core.types import CameraIntent, MovementIntent, ProgressState


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    action: str
    reason: str
    camera_intent: CameraIntent | None = None
    movement_intent: MovementIntent | None = None
    interrupt: Interrupt | None = None


class RecoveryPolicy:
    def decide(self, progress: ProgressState) -> RecoveryDecision:
        active = progress.active_interrupt
        if active is not None:
            return RecoveryDecision(
                action="interrupt_recovery",
                reason=f"active_interrupt:{active.code}",
                interrupt=active,
            )
        if progress.frustration >= 80.0:
            return RecoveryDecision(
                action="ESCALATE",
                reason="frustration_escalate",
                interrupt=Interrupt(
                    priority=2,
                    timestamp=progress.timestamp,
                    code="NO_TASK_PROGRESS",
                    source="recovery_policy",
                    payload={"frustration": progress.frustration},
                ),
            )
        if progress.frustration >= 30.0:
            return RecoveryDecision(
                action="LOCAL_REROUTE",
                reason="no_task_progress_local_reroute",
                camera_intent=CameraIntent(
                    yaw_delta=12.0,
                    pitch_delta=0.0,
                    duration_ms=150,
                    confidence=0.5,
                    reason="recovery_wide_search",
                ),
            )
        if progress.frustration >= 10.0:
            return RecoveryDecision(
                action="MICRO_RECOVERY",
                reason="micro_recovery",
                camera_intent=CameraIntent(
                    yaw_delta=4.0,
                    pitch_delta=0.0,
                    duration_ms=120,
                    confidence=0.6,
                    reason="recovery_micro_sweep",
                ),
                movement_intent=MovementIntent(
                    move_forward=-0.25,
                    move_right=0.5,
                    duration_ms=180,
                    reason="micro_recovery_back_and_side",
                ),
            )
        return RecoveryDecision(action="continue", reason="progress_acceptable")
