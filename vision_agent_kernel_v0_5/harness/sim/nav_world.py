"""2D navigation world — a deterministic dogfood environment.

Ground-truth player moves per the issued action; the agent only ever sees *noisy*
world-frame flow + a noisy compass (and a synthetic target track when close),
feeds them to the real :class:`~perception.pose_fusion.PoseFusion`, and steers
with the real :class:`~control.navigation_coordinator.NavigationCoordinator`.

So a batch over many seeds yields a genuine *offline* arrival-success rate for the
Phase 0 navigation stack — closing the trial-and-error loop without the real game.
"""
from __future__ import annotations

import math
import random
from typing import Any

from control.navigation_coordinator import (
    NavigationCoordinator,
    RecoveryOutput,
)
from control.pose_navigation import PoseNavConfig, PoseNavigationController, PoseNavTarget
from control.visual_reacquire import VisualReacquireController
from core.types import LocalizationReading, MotionCommand, MovementIntent, TargetTrack
from harness.core import JsonDict, Scenario
from perception.pose_fusion import PoseFusion, PoseFusionConfig, bearing_to, shortest_arc_deg


def _wrap360(d: float) -> float:
    return d % 360.0


class NavWorldEnv:
    """Ground-truth 2D world with noisy sensing. Implements the Environment protocol."""

    def __init__(self) -> None:
        self._x = 0.0
        self._y = 0.0
        self._heading = 0.0
        self._t = 0.0
        self._rng = random.Random(0)
        self._setup: JsonDict = {}
        self._initial_distance = 1.0

    def reset(self, scenario: Scenario) -> JsonDict:
        s = scenario.setup
        self._setup = s
        self._x, self._y = float(s["start"][0]), float(s["start"][1])
        self._heading = float(s.get("heading", 0.0))
        self._t = 0.0
        self._rng = random.Random(int(s.get("seed", 0)))
        tx, ty = s["target"]
        self._initial_distance = math.hypot(tx - self._x, ty - self._y) or 1.0
        return self._observe(flow_dx=None, flow_dy=None, flow_conf=0.0, moving=False)

    def step(self, action: JsonDict) -> tuple[JsonDict, bool, JsonDict]:
        s = self._setup
        speed = float(s.get("speed", 5.0))
        flow_noise = float(s.get("flow_noise", 0.05))
        heading_noise = float(s.get("heading_noise", 4.0))
        arrival_radius = float(s.get("arrival_radius", 1.5))
        bounds = float(s.get("bounds", 200.0))
        obstacle = s.get("obstacle")  # {"c":[x,y],"r":float} | None

        dt = max(0.0, min(float(action.get("duration_ms", 200)) / 1000.0, 1.0))
        self._heading = _wrap360(self._heading + float(action.get("yaw_delta", 0.0)))
        f = max(-1.0, min(1.0, float(action.get("forward", 0.0))))
        r = max(-1.0, min(1.0, float(action.get("right", 0.0))))

        dist = speed * dt
        h = math.radians(self._heading)
        dx = f * dist * math.sin(h) + r * dist * math.cos(h)
        dy = f * dist * math.cos(h) - r * dist * math.sin(h)

        nx, ny = self._x + dx, self._y + dy
        blocked = False
        if obstacle is not None:
            ox, oy = obstacle["c"]
            if math.hypot(nx - ox, ny - oy) < float(obstacle["r"]):
                blocked = True
                nx, ny = self._x, self._y
        actual_dx = nx - self._x
        actual_dy = ny - self._y
        self._x, self._y = nx, ny
        self._t += dt

        moving = (f != 0.0 or r != 0.0)
        flow_dx = actual_dx + self._rng.gauss(0.0, flow_noise)
        flow_dy = actual_dy + self._rng.gauss(0.0, flow_noise)
        flow_mag = math.hypot(actual_dx, actual_dy)
        flow_conf = 0.9 if flow_mag > 1e-3 else (0.2 if moving else 0.0)

        tx, ty = s["target"]
        dist_to_target = math.hypot(tx - self._x, ty - self._y)
        success = dist_to_target <= arrival_radius
        out_of_bounds = abs(self._x) > bounds or abs(self._y) > bounds
        done = success or out_of_bounds
        failure_code = "out_of_bounds" if out_of_bounds else None
        progress = max(0.0, min(1.0, 1.0 - dist_to_target / self._initial_distance))

        obs = self._observe(flow_dx=flow_dx, flow_dy=flow_dy, flow_conf=flow_conf,
                            moving=moving, heading_noise=heading_noise)
        info: JsonDict = {
            "success": success,
            "failure_code": failure_code,
            "reason": "arrived" if success else (failure_code or "in_progress"),
            "progress": progress,
            "metrics": {"final_distance": dist_to_target, "blocked": blocked},
            "true_distance": dist_to_target,
        }
        return obs, done, info

    # -- helpers ------------------------------------------------------------

    def _observe(
        self, *, flow_dx, flow_dy, flow_conf, moving, heading_noise: float = 4.0,
    ) -> JsonDict:
        s = self._setup
        heading_meas = _wrap360(self._heading + self._rng.gauss(0.0, heading_noise)) if s else self._heading
        visual_range = float(s.get("visual_range", 6.0)) if s else 6.0
        arrival_radius = float(s.get("arrival_radius", 1.5)) if s else 1.5
        track = None
        if s:
            tx, ty = s["target"]
            dist_to_target = math.hypot(tx - self._x, ty - self._y)
            if dist_to_target <= visual_range:
                track = self._synth_track(dist_to_target, arrival_radius)
        return {
            "t": self._t,
            "flow_dx": flow_dx,
            "flow_dy": flow_dy,
            "flow_conf": flow_conf,
            "heading_meas": heading_meas,
            "heading_conf": 0.6,
            "is_moving": moving,
            "target_track": track,
        }

    def _synth_track(self, dist: float, arrival_radius: float) -> JsonDict:
        # Where the target appears given true heading (FOV ~78°, viewport 1280x720).
        tx, ty = self._setup["target"]
        bearing = bearing_to((self._x, self._y), (tx, ty))
        err = shortest_arc_deg(self._heading, bearing)
        cx = 640.0 + (err / 39.0) * 640.0
        cx = max(0.0, min(1280.0, cx))
        area_ratio = min(0.3, 0.13 * (arrival_radius / max(dist, 1e-3)) ** 2)
        half = math.sqrt(area_ratio * 1280.0 * 720.0) / 2.0
        return {
            "center_px": (cx, 360.0),
            "bbox_xyxy": (cx - half, 360.0 - half, cx + half, 360.0 + half),
            "state": "visible",
            "confidence": 0.85,
        }


class _SimRecovery:
    """Minimal recovery: back off and turn to escape, let nav retry."""

    def recover(self, reason: str, pose: Any, target: Any) -> RecoveryOutput:
        return RecoveryOutput(
            movement=MovementIntent(move_forward=-0.6, move_right=0.0, reason=f"recover_{reason}"),
            resolved=False,
            reason=f"recovering:{reason}",
        )


class NavStackPolicy:
    """Drives the real pose+nav stack from NavWorldEnv observations."""

    def __init__(
        self,
        *,
        fusion_config: PoseFusionConfig | None = None,
        nav_config: PoseNavConfig | None = None,
    ) -> None:
        self._fusion_config = fusion_config
        self._nav_config = nav_config
        self._fusion: PoseFusion | None = None
        self._coord: NavigationCoordinator | None = None
        self._target: PoseNavTarget | None = None
        self._speed = 5.0
        self._last_cmd: MotionCommand | None = None

    def reset(self, scenario: Scenario) -> None:
        s = scenario.setup
        self._speed = float(s.get("speed", 5.0))
        start = (float(s["start"][0]), float(s["start"][1]))
        heading = float(s.get("heading", 0.0))
        self._fusion = PoseFusion(self._fusion_config)
        self._fusion.reset(start, heading, timestamp=0.0, confidence=1.0)
        arrival = float(s.get("arrival_radius", 1.5))
        self._target = PoseNavTarget(
            position=(float(s["target"][0]), float(s["target"][1])),
            arrival_radius=arrival,
            reacquire_radius=float(s.get("visual_range", 6.0)),
        )
        self._coord = NavigationCoordinator(
            PoseNavigationController(self._nav_config),
            VisualReacquireController(),
            recovery=_SimRecovery(),
        )
        self._last_cmd = None

    def act(self, obs: JsonDict) -> JsonDict:
        assert self._fusion is not None and self._coord is not None and self._target is not None
        reading = LocalizationReading(
            timestamp=obs["t"], frame_id=0,
            heading_deg=obs.get("heading_meas"), heading_confidence=obs.get("heading_conf", 0.0),
            flow_dx=obs.get("flow_dx"), flow_dy=obs.get("flow_dy"),
            flow_confidence=obs.get("flow_conf", 0.0),
        )
        pose = self._fusion.update(reading=reading, command=self._last_cmd, now=obs["t"])
        track = _to_track(obs.get("target_track"))
        decision = self._coord.step(pose, self._target, obs["t"], track=track)
        mv = decision.movement
        cam = decision.camera
        forward = mv.move_forward if mv else 0.0
        right = mv.move_right if mv else 0.0
        yaw = cam.yaw_delta if cam else 0.0
        dur = mv.duration_ms if mv else (cam.duration_ms if cam else 200)
        self._last_cmd = MotionCommand(
            timestamp=obs["t"], forward=forward, right=right,
            speed_world_units_per_sec=self._speed, yaw_rate_deg_per_sec=0.0,
            is_moving=(forward != 0.0 or right != 0.0),
        )
        return {"forward": forward, "right": right, "yaw_delta": yaw, "duration_ms": dur}


def _to_track(d: JsonDict | None) -> TargetTrack | None:
    if not d:
        return None
    return TargetTrack(
        track_id="sim", class_id="target", state=d.get("state", "visible"),
        bbox_xyxy=tuple(d["bbox_xyxy"]), smoothed_center_px=tuple(d["center_px"]),
        velocity_px_s=(0.0, 0.0), confidence=d.get("confidence", 0.8),
        identity_confidence=d.get("confidence", 0.8), missing_duration_ms=0.0,
        bearing_deg=None, pitch_deg=None, estimated_range=None, last_seen_frame_id=0,
    )


def make_nav_scenarios(
    n: int,
    *,
    seed: int = 0,
    bounds: float = 60.0,
    speed: float = 5.0,
    flow_noise: float = 0.05,
    with_obstacles: bool = False,
) -> list[Scenario]:
    """Generate ``n`` deterministic navigation scenarios."""
    rng = random.Random(seed)
    scenarios: list[Scenario] = []
    for i in range(n):
        sx, sy = rng.uniform(-bounds, bounds), rng.uniform(-bounds, bounds)
        # target at least 10 units away
        while True:
            tx, ty = rng.uniform(-bounds, bounds), rng.uniform(-bounds, bounds)
            if math.hypot(tx - sx, ty - sy) >= 10.0:
                break
        setup: JsonDict = {
            "start": [sx, sy], "heading": rng.uniform(0, 360),
            "target": [tx, ty], "arrival_radius": 1.5, "visual_range": 6.0,
            "speed": speed, "flow_noise": flow_noise, "heading_noise": 4.0,
            "bounds": bounds * 2.0, "seed": rng.randint(0, 1_000_000),
        }
        tags: tuple[str, ...] = ("nav",)
        if with_obstacles and i % 3 == 0:
            mx, my = (sx + tx) / 2.0, (sy + ty) / 2.0
            setup["obstacle"] = {"c": [mx, my], "r": 3.0}
            tags = ("nav", "obstacle")
        scenarios.append(Scenario(
            scenario_id=f"nav-{seed}-{i:03d}", objective="reach target",
            setup=setup, max_steps=400, timeout_sec=30.0, tags=tags,
        ))
    return scenarios
