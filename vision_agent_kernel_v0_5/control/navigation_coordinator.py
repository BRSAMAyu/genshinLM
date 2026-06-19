"""Navigation coordinator — ties pose nav, visual reacquire, and recovery together.

:class:`~control.pose_navigation.PoseNavigationController` decides *coarse* steering
from the fused pose. When it returns ``reacquire`` (near the target but pose too
uncertain to place us precisely), control hands off to
:class:`~control.visual_reacquire.VisualReacquireController`; when it returns
``lost`` / ``stuck`` it hands off to a pluggable recovery strategy. This module is
the small state machine that owns those handoffs so callers (the loop / a mission
runner) see one ``step`` and one decision type.

It is game-agnostic: recovery is injected via the :class:`RecoveryStrategy`
protocol, so a capsule can wrap its own ``LostRecovery`` without this module
importing it. Mode is sticky (once in ``reacquire`` it stays there until the
target is reached or the search comes up empty) to avoid flapping between the
two controllers frame to frame.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from control.pose_navigation import PoseNavDecision, PoseNavigationController, PoseNavTarget
from control.visual_reacquire import VisualReacquireController
from core.types import CameraIntent, MovementIntent, PoseEstimate, TargetTrack

CoordMode = Literal["navigate", "reacquire", "recover", "arrived"]


@dataclass(frozen=True, slots=True)
class RecoveryOutput:
    """What a recovery strategy suggests doing for one tick."""

    movement: MovementIntent | None = None
    camera: CameraIntent | None = None
    resolved: bool = False  # True → recovery believes the situation is cleared
    reason: str = ""


class RecoveryStrategy(Protocol):
    """Pluggable recovery (e.g. a capsule adapter over LostRecovery)."""

    def recover(self, reason: str, pose: PoseEstimate, target: PoseNavTarget) -> RecoveryOutput:
        ...


@dataclass(frozen=True, slots=True)
class CoordinatedDecision:
    mode: CoordMode
    status: str            # underlying controller status
    reason: str
    movement: MovementIntent | None = None
    camera: CameraIntent | None = None
    distance: float = 0.0


class NavigationCoordinator:
    def __init__(
        self,
        nav: PoseNavigationController | None = None,
        reacquire: VisualReacquireController | None = None,
        recovery: RecoveryStrategy | None = None,
    ) -> None:
        self._nav = nav or PoseNavigationController()
        self._reacquire = reacquire or VisualReacquireController()
        self._recovery = recovery
        self._mode: CoordMode = "navigate"

    @property
    def mode(self) -> CoordMode:
        return self._mode

    def reset(self) -> None:
        self._nav.reset()
        self._reacquire.reset()
        self._mode = "navigate"

    def step(
        self,
        pose: PoseEstimate,
        target: PoseNavTarget,
        now: float,
        track: TargetTrack | None = None,
    ) -> CoordinatedDecision:
        if self._mode == "arrived":
            return CoordinatedDecision("arrived", "arrived", "already arrived")

        if self._mode == "reacquire":
            return self._run_reacquire(pose, target, track)

        if self._mode == "recover":
            # Try one recovery tick; if resolved, resume navigation next call.
            return self._run_recovery("recover_continue", pose, target)

        # mode == "navigate"
        decision = self._nav.step(pose, target, now)
        if decision.status == "arrived":
            self._mode = "arrived"
            return CoordinatedDecision("arrived", "arrived", decision.reason, distance=decision.distance)
        if decision.status == "reacquire":
            self._mode = "reacquire"
            self._reacquire.reset()
            return self._run_reacquire(pose, target, track)
        if decision.status in ("lost", "stuck"):
            self._mode = "recover"
            return self._run_recovery(decision.status, pose, target)
        # steer
        return self._passthrough_nav(decision)

    # -- internals ----------------------------------------------------------

    def _run_reacquire(
        self, pose: PoseEstimate, target: PoseNavTarget, track: TargetTrack | None,
    ) -> CoordinatedDecision:
        rd = self._reacquire.step(track)
        if rd.status == "arrived":
            self._mode = "arrived"
            return CoordinatedDecision("arrived", "arrived", "visual reacquire arrived")
        if rd.status == "not_found":
            self._mode = "recover"
            return self._run_recovery("reacquire_not_found", pose, target)
        return CoordinatedDecision(
            "reacquire", rd.status, rd.reason, movement=rd.movement, camera=rd.camera,
        )

    def _run_recovery(
        self, reason: str, pose: PoseEstimate, target: PoseNavTarget,
    ) -> CoordinatedDecision:
        if self._recovery is None:
            # No strategy wired — surface the condition; caller decides.
            return CoordinatedDecision("recover", reason, f"recovery needed: {reason} (no strategy wired)")
        out = self._recovery.recover(reason, pose, target)
        if out.resolved:
            self._mode = "navigate"
        return CoordinatedDecision(
            "recover", reason, out.reason or f"recovering: {reason}",
            movement=out.movement, camera=out.camera,
        )

    @staticmethod
    def _passthrough_nav(decision: PoseNavDecision) -> CoordinatedDecision:
        return CoordinatedDecision(
            "navigate", decision.status, decision.reason,
            movement=decision.movement, camera=decision.camera, distance=decision.distance,
        )
