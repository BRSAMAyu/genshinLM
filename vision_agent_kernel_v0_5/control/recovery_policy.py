from __future__ import annotations

from dataclasses import dataclass

from core.events import Interrupt
from core.types import CameraIntent, ProgressState


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    action: str
    reason: str
    camera_intent: CameraIntent | None = None
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
            return RecoveryDecision(action="escalate", reason="frustration_escalate")
        if progress.frustration >= 30.0:
            return RecoveryDecision(
                action="wide_search",
                reason="no_task_progress",
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
                action="micro_recovery",
                reason="micro_recovery",
                camera_intent=CameraIntent(
                    yaw_delta=4.0,
                    pitch_delta=0.0,
                    duration_ms=120,
                    confidence=0.6,
                    reason="recovery_micro_sweep",
                ),
            )
        return RecoveryDecision(action="continue", reason="progress_acceptable")
