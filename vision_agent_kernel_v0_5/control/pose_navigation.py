"""Pose-closed-loop navigation controller.

Steers toward a world-coordinate target using the fused
:class:`~core.types.PoseEstimate` instead of reacting to a minimap marker's
on-screen pixel angle. This is the closed-loop replacement for the open-loop
``control.navigation_runtime`` path:

* heading error = ``shortest_arc_deg(pose.heading, bearing_to(pose, target))``
* arrival = within ``arrival_radius`` *and* pose confident enough to trust
* stuck = commanded forward but pose displacement ≈ 0 over a window
* lost = pose confidence collapsed → hand back for relocalization
* reacquire = close to target but pose too uncertain for precision → hand off
  to last-mile visual servoing (:mod:`control.visual_reacquire`)

It is game-agnostic: it consumes a pose and a target and emits
:class:`~core.types.MovementIntent` / :class:`~core.types.CameraIntent`. The
caller turns those into input leases.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from core.types import CameraIntent, MovementIntent, PoseEstimate
from perception.pose_fusion import bearing_to, shortest_arc_deg

NavStatus = Literal["steer", "arrived", "lost", "stuck", "reacquire"]


@dataclass(frozen=True, slots=True)
class PoseNavTarget:
    position: tuple[float, float]
    arrival_radius: float = 2.0
    reacquire_radius: float = 6.0
    name: str = ""


@dataclass(frozen=True, slots=True)
class PoseNavConfig:
    heading_dead_zone_deg: float = 5.0
    yaw_gain: float = 0.5
    max_yaw_delta_deg: float = 30.0
    min_confidence: float = 0.25
    move_duration_ms: int = 200
    camera_duration_ms: int = 80
    stuck_window_sec: float = 1.5
    stuck_min_displacement: float = 0.5
    # Near the target, if position uncertainty is large relative to the remaining
    # distance, dead-reckoned pose can't place us precisely — switch to vision.
    reacquire_uncertainty_ratio: float = 0.5


@dataclass(frozen=True, slots=True)
class PoseNavDecision:
    status: NavStatus
    reason: str
    movement: MovementIntent | None = None
    camera: CameraIntent | None = None
    heading_error_deg: float = 0.0
    distance: float = 0.0


class PoseNavigationController:
    def __init__(self, config: PoseNavConfig | None = None) -> None:
        self._cfg = config or PoseNavConfig()
        self._history: deque[tuple[float, tuple[float, float]]] = deque()
        self._last_forward = 0.0

    def reset(self) -> None:
        self._history.clear()
        self._last_forward = 0.0

    def step(self, pose: PoseEstimate, target: PoseNavTarget, now: float) -> PoseNavDecision:
        cfg = self._cfg
        dx = target.position[0] - pose.position[0]
        dy = target.position[1] - pose.position[1]
        distance = math.hypot(dx, dy)

        # Lost — confidence collapsed; caller should relocalize (map fix / recovery).
        if pose.confidence < cfg.min_confidence:
            self._last_forward = 0.0
            return PoseNavDecision(
                "lost", f"confidence {pose.confidence:.2f} < {cfg.min_confidence}",
                distance=distance,
            )

        # Arrived.
        if distance <= target.arrival_radius:
            self._last_forward = 0.0
            return PoseNavDecision("arrived", "within arrival radius", distance=distance)

        # Last-mile: close but pose too uncertain to place us precisely → vision.
        if (
            distance <= target.reacquire_radius
            and pose.position_uncertainty > cfg.reacquire_uncertainty_ratio * max(distance, 1e-6)
        ):
            self._last_forward = 0.0
            return PoseNavDecision(
                "reacquire", "near target but pose uncertain — hand to visual servo",
                distance=distance,
            )

        # Stuck detection: commanded forward yet pose barely moved over the window.
        self._history.append((now, pose.position))
        while self._history and now - self._history[0][0] > cfg.stuck_window_sec:
            self._history.popleft()
        if (
            self._last_forward > 0.05
            and len(self._history) >= 2
            and (now - self._history[0][0]) >= cfg.stuck_window_sec * 0.8
            and self._window_displacement() < cfg.stuck_min_displacement
        ):
            return PoseNavDecision(
                "stuck", "commanded forward but pose not advancing", distance=distance,
            )

        # Steer: rotate camera toward bearing, walk forward scaled by alignment.
        bearing = bearing_to(pose.position, target.position)
        heading_error = shortest_arc_deg(pose.heading_deg, bearing)

        camera: CameraIntent | None = None
        if abs(heading_error) > cfg.heading_dead_zone_deg:
            yaw = _clamp(heading_error * cfg.yaw_gain, -cfg.max_yaw_delta_deg, cfg.max_yaw_delta_deg)
            camera = CameraIntent(
                yaw_delta=yaw, pitch_delta=0.0, duration_ms=cfg.camera_duration_ms,
                confidence=pose.confidence, reason="pose_steer",
            )

        align = max(0.0, math.cos(math.radians(heading_error)))
        move_forward = align if align > 0.05 else 0.0
        self._last_forward = move_forward
        movement = MovementIntent(
            move_forward=move_forward, move_right=0.0,
            duration_ms=cfg.move_duration_ms, reason="pose_steer",
        )
        return PoseNavDecision(
            "steer", "steering toward target", movement=movement, camera=camera,
            heading_error_deg=heading_error, distance=distance,
        )

    def _window_displacement(self) -> float:
        if len(self._history) < 2:
            return math.inf
        (_, first), (_, last) = self._history[0], self._history[-1]
        return math.hypot(last[0] - first[0], last[1] - first[1])


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value
