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
    def __init__(
        self,
        *,
        frustration_escalate_threshold: float = 80.0,
        frustration_local_reroute_threshold: float = 30.0,
        frustration_micro_recovery_threshold: float = 10.0,
    ) -> None:
        self._prev_timestamp: float | None = None
        self._prev_frustration: float | None = None
        self._ewma_frustration_slope: float = 0.0
        self._alpha: float = 0.35
        self._stuck_count: int = 0
        self._frustration_escalate = frustration_escalate_threshold
        self._frustration_local_reroute = frustration_local_reroute_threshold
        self._frustration_micro_recovery = frustration_micro_recovery_threshold

    def decide(self, progress: ProgressState) -> RecoveryDecision:
        now = progress.timestamp
        current_frustration = progress.frustration
        
        # Calculate instant frustration slope
        inst_slope = 0.0
        if self._prev_timestamp is not None and self._prev_frustration is not None:
            dt = now - self._prev_timestamp
            if dt > 1e-5:
                inst_slope = (current_frustration - self._prev_frustration) / dt
        
        # Update EWMA frustration slope
        self._ewma_frustration_slope = (
            self._alpha * inst_slope + (1.0 - self._alpha) * self._ewma_frustration_slope
        )
        
        self._prev_timestamp = now
        self._prev_frustration = current_frustration

        active = progress.active_interrupt
        if active is not None:
            return RecoveryDecision(
                action="interrupt_recovery",
                reason=f"active_interrupt:{active.code}",
                interrupt=active,
            )
        if progress.frustration >= self._frustration_escalate:
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

        # Trigger smooth bypass rapidly if frustration is rising quickly (high slope) and progress is flat,
        # or if frustration level is high and progress is flat.
        is_stuck_by_slope = (self._ewma_frustration_slope > 5.0) and (progress.progress_slope_2s <= 0.01)
        is_stuck_by_level = (progress.frustration >= 20.0) and (progress.progress_slope_2s <= 0.01)

        if is_stuck_by_slope or is_stuck_by_level:
            self._stuck_count += 1
            # Alternate bypass direction based on stuck count to explore both left and right bypass arcs
            side_direction = 1.0 if self._stuck_count % 2 == 0 else -1.0
            
            # Formulate a dynamic arc maneuver: back off first, then turn and run sidesteps
            if self._stuck_count % 3 == 1:
                # Stage 1: Active disengagement. Back away from the convex collider to clear contact
                action_reason = "stuck_bypass_backoff"
                cam_intent = CameraIntent(
                    yaw_delta=5.0 * side_direction,
                    pitch_delta=0.0,
                    duration_ms=150,
                    confidence=0.8,
                    reason="stuck_backoff_camera_clear",
                )
                move_intent = MovementIntent(
                    move_forward=-0.6,
                    move_right=0.2 * side_direction,
                    duration_ms=250,
                    reason="stuck_backoff_arc",
                )
            else:
                # Stage 2 & 3: Smooth lateral arc bypass (diagonal forward + camera rotation)
                action_reason = "stuck_bypass_arc_run"
                cam_intent = CameraIntent(
                    yaw_delta=25.0 * side_direction,
                    pitch_delta=0.0,
                    duration_ms=250,
                    confidence=0.85,
                    reason="stuck_sweep_arc_yaw",
                )
                move_intent = MovementIntent(
                    move_forward=0.7,
                    move_right=0.5 * side_direction,
                    duration_ms=350,
                    reason="stuck_smooth_bypass_arc_run",
                )

            return RecoveryDecision(
                action="SMOOTH_BYPASS",
                reason=f"{action_reason}_slope_{self._ewma_frustration_slope:.2f}",
                camera_intent=cam_intent,
                movement_intent=move_intent,
            )

        if progress.frustration >= self._frustration_local_reroute:
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
        if progress.frustration >= self._frustration_micro_recovery:
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
