"""Sensor-agnostic pose fusion — the agent's state estimator.

This is the layer the kernel was missing: a small predict/correct complementary
filter that turns scattered localization cues into a single coherent
:class:`~core.types.PoseEstimate` with a confidence and a growing/shrinking
uncertainty. It is deliberately *not* a heavy EKF — it is debuggable, allocation
free in the hot path, and follows the project's "EWMA + slopes, never a single
frame" philosophy.

Design contract (see ``core.types`` spatial substrate section):

* **predict** — integrate the body-frame :class:`~core.types.MotionCommand` the
  executor actually issued (dead-reckoning). Position uncertainty grows with the
  distance travelled; heading uncertainty grows while turning without a compass.
* **correct** — fold in a :class:`~core.types.LocalizationReading`:
    - compass heading (strong, shrinks heading uncertainty),
    - incremental flow displacement (measured, low-noise),
    - an absolute position fix (e.g. map readout / teleport landing) which pulls
      the estimate back and collapses position uncertainty.
* **confidence** decays with time when no measurement arrives, so a stale pose
  advertises its own staleness instead of lying.

The engine is game-agnostic. A minimap is just one source of readings. All clock
values are passed in explicitly (monotonic ``perf_counter`` seconds) so the
filter is fully deterministic under test.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from core.types import LocalizationReading, MotionCommand, PoseEstimate


def wrap360(deg: float) -> float:
    """Normalize an angle into ``[0, 360)``."""
    return deg % 360.0


def shortest_arc_deg(frm: float, to: float) -> float:
    """Signed shortest rotation (degrees) from ``frm`` to ``to`` in ``(-180, 180]``."""
    diff = (to - frm + 180.0) % 360.0 - 180.0
    return diff + 360.0 if diff <= -180.0 else diff


def blend_heading(current: float, measured: float, gain: float) -> float:
    """Move ``current`` toward ``measured`` by ``gain`` along the shortest arc."""
    return wrap360(current + gain * shortest_arc_deg(current, measured))


def bearing_to(origin: tuple[float, float], target: tuple[float, float]) -> float:
    """Clockwise-from-north bearing (deg) from ``origin`` to ``target``.

    Matches the :class:`~core.types.PoseEstimate` heading convention
    (0=+Y/north, 90=+X/east), so ``shortest_arc_deg(pose.heading_deg,
    bearing_to(pose.position, target))`` is directly a steering error.
    """
    dx = target[0] - origin[0]
    dy = target[1] - origin[1]
    return wrap360(math.degrees(math.atan2(dx, dy)))


@dataclass(slots=True)
class PoseFusionConfig:
    """Tunables for :class:`PoseFusion`. Units are world units / seconds / degrees."""

    # Uncertainty (world units) added per world unit travelled, by displacement source.
    process_noise_per_unit: float = 0.15   # dead-reckoning is noisy
    flow_noise_per_unit: float = 0.04      # measured flow is much better
    # Heading uncertainty (deg) added per second of dead-reckoned turning.
    yaw_drift_deg_per_sec: float = 8.0
    # How hard a compass / absolute fix pulls the estimate (0..1, scaled by reading confidence).
    compass_trust: float = 0.85
    absolute_fix_gain: float = 0.8
    # Confidence decay per second with no measurement.
    confidence_decay_per_sec: float = 0.25
    # Velocity EWMA smoothing (0..1, higher = snappier).
    velocity_alpha: float = 0.5
    # Safety clamps.
    max_position_uncertainty: float = 1.0e6
    max_heading_uncertainty_deg: float = 180.0
    max_dt_sec: float = 1.0  # ignore absurd gaps (e.g. after a pause)


class PoseFusion:
    """Predict/correct pose estimator producing :class:`PoseEstimate` snapshots."""

    def __init__(
        self,
        config: PoseFusionConfig | None = None,
        *,
        initial_position: tuple[float, float] = (0.0, 0.0),
        initial_heading_deg: float = 0.0,
    ) -> None:
        self._cfg = config or PoseFusionConfig()
        self._x, self._y = float(initial_position[0]), float(initial_position[1])
        self._heading = wrap360(initial_heading_deg)
        self._vx = 0.0
        self._vy = 0.0
        self._confidence = 0.0
        self._pos_unc = self._cfg.max_position_uncertainty  # unknown until a fix
        self._head_unc = self._cfg.max_heading_uncertainty_deg
        self._has_abs_fix = False
        self._source = "init"
        self._last_t: float | None = None
        self._last_frame_id = 0

    # -- public API ---------------------------------------------------------

    def reset(
        self,
        position: tuple[float, float],
        heading_deg: float,
        *,
        timestamp: float,
        confidence: float = 1.0,
    ) -> None:
        """Snap to a known pose — use after teleport / a trusted absolute fix."""
        self._x, self._y = float(position[0]), float(position[1])
        self._heading = wrap360(heading_deg)
        self._vx = self._vy = 0.0
        self._confidence = _clamp01(confidence)
        self._pos_unc = 0.0
        self._head_unc = 0.0
        self._has_abs_fix = True
        self._source = "reset"
        self._last_t = timestamp

    def predict(self, command: MotionCommand, now: float) -> PoseEstimate:
        """Advance the estimate using only dead-reckoning."""
        return self.update(reading=None, command=command, now=now)

    def correct(self, reading: LocalizationReading, now: float) -> PoseEstimate:
        """Fold in a measurement with no accompanying motion command."""
        return self.update(reading=reading, command=None, now=now)

    def update(
        self,
        reading: LocalizationReading | None,
        command: MotionCommand | None,
        now: float,
    ) -> PoseEstimate:
        """Single fused step. Either argument may be ``None``.

        Order: time-decay confidence → integrate heading (compass beats
        dead-reckoning) → integrate displacement (flow beats dead-reckoning) →
        apply absolute fix → recompute confidence. Returns the new snapshot.
        """
        cfg = self._cfg
        dt = 0.0 if self._last_t is None else max(0.0, min(now - self._last_t, cfg.max_dt_sec))
        self._last_t = now
        if reading is not None and reading.frame_id:
            self._last_frame_id = reading.frame_id

        sources: list[str] = []

        # 1. Confidence decays purely with time; measurements below restore it.
        self._confidence = max(0.0, self._confidence - cfg.confidence_decay_per_sec * dt)

        # 2. Heading: prefer a compass measurement, else integrate yaw rate.
        compass = reading.heading_deg if reading is not None else None
        compass_conf = reading.heading_confidence if reading is not None else 0.0
        if compass is not None and compass_conf > 0.0:
            gain = cfg.compass_trust * _clamp01(compass_conf)
            self._heading = blend_heading(self._heading, wrap360(compass), gain)
            self._head_unc *= (1.0 - gain)
            sources.append("compass")
        elif command is not None and command.yaw_rate_deg_per_sec:
            self._heading = wrap360(self._heading + command.yaw_rate_deg_per_sec * dt)
            self._head_unc = min(
                cfg.max_heading_uncertainty_deg,
                self._head_unc + cfg.yaw_drift_deg_per_sec * dt,
            )

        # 3. Displacement: measured flow beats dead-reckoning; otherwise integrate
        #    the commanded body-frame motion rotated into world frame.
        dx = dy = 0.0
        used_flow = False
        if (
            reading is not None
            and reading.flow_dx is not None
            and reading.flow_dy is not None
            and reading.flow_confidence > 0.0
        ):
            dx, dy = float(reading.flow_dx), float(reading.flow_dy)
            used_flow = True
            sources.append("flow")
        elif command is not None and command.is_moving and dt > 0.0:
            move = command.speed_world_units_per_sec * dt
            disp_f = command.forward * move
            disp_r = command.right * move
            h = math.radians(self._heading)
            # forward = (sin h, cos h); right = (cos h, -sin h)
            dx = disp_f * math.sin(h) + disp_r * math.cos(h)
            dy = disp_f * math.cos(h) - disp_r * math.sin(h)
            if move != 0.0:
                sources.append("deadreckon")

        if dx or dy:
            self._x += dx
            self._y += dy
            dist = math.hypot(dx, dy)
            noise = cfg.flow_noise_per_unit if used_flow else cfg.process_noise_per_unit
            self._pos_unc = min(cfg.max_position_uncertainty, self._pos_unc + dist * noise)
            if dt > 0.0:
                self._vx = _ewma(self._vx, dx / dt, cfg.velocity_alpha)
                self._vy = _ewma(self._vy, dy / dt, cfg.velocity_alpha)
            if used_flow and reading is not None:
                self._confidence = max(self._confidence, _clamp01(reading.flow_confidence) * 0.9)
        elif dt > 0.0:
            # Standing still — bleed velocity toward zero.
            self._vx = _ewma(self._vx, 0.0, cfg.velocity_alpha)
            self._vy = _ewma(self._vy, 0.0, cfg.velocity_alpha)

        # 4. Absolute fix: pull position back and collapse uncertainty.
        if (
            reading is not None
            and reading.absolute_position is not None
            and reading.absolute_confidence > 0.0
        ):
            gain = cfg.absolute_fix_gain * _clamp01(reading.absolute_confidence)
            ax, ay = reading.absolute_position
            self._x += gain * (ax - self._x)
            self._y += gain * (ay - self._y)
            self._pos_unc *= (1.0 - gain)
            self._has_abs_fix = True
            self._confidence = max(self._confidence, _clamp01(reading.absolute_confidence))
            sources.append("absolute")

        if compass is not None and compass_conf > 0.0:
            self._confidence = max(self._confidence, _clamp01(compass_conf) * 0.8)

        if sources:
            self._source = "+".join(sources)
        return self.current()

    def current(self) -> PoseEstimate:
        """Snapshot the current belief without advancing it."""
        return PoseEstimate(
            frame_id=self._last_frame_id,
            timestamp=self._last_t or 0.0,
            position=(self._x, self._y),
            heading_deg=self._heading,
            velocity=(self._vx, self._vy),
            confidence=_clamp01(self._confidence),
            position_uncertainty=self._pos_unc,
            heading_uncertainty_deg=self._head_unc,
            has_absolute_fix=self._has_abs_fix,
            source=self._source,
        )


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _ewma(prev: float, new: float, alpha: float) -> float:
    return alpha * new + (1.0 - alpha) * prev
