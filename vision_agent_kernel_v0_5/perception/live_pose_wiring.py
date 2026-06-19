"""Self-contained live wiring for the pose-estimation substrate.

The fast perception pipeline (``PoseEstimationProcessor`` +
``attach_pose_estimation``) assumes a ``FramePostProcessor`` seam. The live
runtime (``agent_kernel.loop.AgentLoop`` driving a ``VLMPerceptionProvider``)
has no such pipeline — it calls ``perception.observe(frame, frame_id)`` once per
tick and never runs post-processors. So the built-in wiring helper does not fit
the live path.

This module bridges that gap *without* editing ``live_factory`` or ``loop``.
:func:`wire_genshin_pose` returns a :class:`PoseTickFn` — a small callable the
integrator drops into the live loop right after a frame is captured::

    pose_tick = wire_genshin_pose(state_bus, profile="genshin_1920x1080")
    ...
    frame = self._capture_frame()
    pose_tick(frame, frame_id)          # publishes StateBus.latest_pose

and an optional ``feed_motion`` hook so the executor's issued movement feeds
dead-reckoning. Everything is game-agnostic except the provider, which stays in
``capsules/genshin``. The minimap ROI is read from the resolution profile
(``configs/profiles/<profile>.json``) — no magic numbers in core.

Conventions are inherited from ``core.types`` (world frame x=east, y=north;
heading clockwise from north) and ``perception.pose_fusion``.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

from core.state_bus import StateBus
from core.types import LocalizationReading, MotionCommand, MovementIntent, PoseEstimate
from perception.pose_estimation_processor import LocalizationProvider, PoseEstimationProcessor
from perception.pose_fusion import PoseFusion, PoseFusionConfig

_PROFILE_DIR = Path(__file__).resolve().parent.parent / "configs" / "profiles"

# Fallback minimap ROI (normalized x, y, w, h) when no profile resolves — kept in
# sync with GenshinMinimapLocalizationProvider's documented default.
_DEFAULT_MINIMAP_ROI: tuple[float, float, float, float] = (0.0, 0.0, 0.10, 0.17)


class PoseTickFn(Protocol):
    """The per-frame callable returned by :func:`wire_genshin_pose`.

    Calling it reads one frame, fuses it into the pose belief, publishes the
    result on ``StateBus.latest_pose`` (and ``observation.extensions['pose']``
    when an observation is supplied), and returns the fresh snapshot.
    """

    def __call__(
        self, frame: np.ndarray, frame_id: int, *, observation: Any = None
    ) -> PoseEstimate:
        ...


def load_minimap_roi(profile: str | None) -> tuple[float, float, float, float]:
    """Resolve the minimap ROI as normalized ``(x, y, w, h)`` from a profile.

    Reads ``configs/profiles/<profile>.json``, where the minimap is stored as
    pixel offsets in ``rois.minimap`` against ``source_resolution``. Only the
    ``top-left`` anchor (Genshin's minimap) is normalized here; anything else or
    a missing/unreadable profile falls back to :data:`_DEFAULT_MINIMAP_ROI`.
    """
    if not profile:
        return _DEFAULT_MINIMAP_ROI
    path = profile if profile.endswith(".json") else f"{profile}.json"
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = _PROFILE_DIR / candidate
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _DEFAULT_MINIMAP_ROI

    res = data.get("source_resolution") or [1920, 1080]
    try:
        src_w, src_h = float(res[0]), float(res[1])
    except (TypeError, ValueError, IndexError):
        return _DEFAULT_MINIMAP_ROI
    if src_w <= 0 or src_h <= 0:
        return _DEFAULT_MINIMAP_ROI

    mm = ((data.get("rois") or {}).get("minimap")) or {}
    # Only the simple top-left anchored pixel box maps cleanly to a corner ROI.
    if mm.get("mode") != "anchor" or mm.get("anchor") != "top-left":
        return _DEFAULT_MINIMAP_ROI
    try:
        off_x = float(mm.get("offset_x_px", 0.0))
        off_y = float(mm.get("offset_y_px", 0.0))
        w_px = float(mm.get("width_px", 0.0))
        h_px = float(mm.get("height_px", 0.0))
    except (TypeError, ValueError):
        return _DEFAULT_MINIMAP_ROI
    if w_px <= 0 or h_px <= 0:
        return _DEFAULT_MINIMAP_ROI

    return (off_x / src_w, off_y / src_h, w_px / src_w, h_px / src_h)


@dataclass(slots=True)
class _MotionLatch:
    """Thread-safe-enough latch for the most recent commanded motion.

    The live loop is single-threaded for the executive cycle; this latch only
    needs to survive the executor handing a command in and the pose tick reading
    it out. A plain attribute write/read is atomic in CPython, so no lock.
    """

    speed_world_units_per_sec: float
    yaw_rate_deg_per_sec: float
    _last: MotionCommand | None = field(default=None)

    def feed_motion(self, command: MotionCommand) -> None:
        self._last = command

    def feed_movement_intent(self, intent: MovementIntent, *, now: float | None = None) -> None:
        """Adapt a control-plane :class:`MovementIntent` into a MotionCommand.

        Convenience for integrators whose executor emits ``MovementIntent``
        (the kernel's native movement type) rather than ``MotionCommand``. The
        nominal walking speed / yaw rate come from the latch's calibration.
        """
        ts = time.perf_counter() if now is None else now
        moving = abs(intent.move_forward) > 0.1 or abs(intent.move_right) > 0.1
        self._last = MotionCommand(
            timestamp=ts,
            forward=intent.move_forward,
            right=intent.move_right,
            speed_world_units_per_sec=self.speed_world_units_per_sec if moving else 0.0,
            yaw_rate_deg_per_sec=self.yaw_rate_deg_per_sec,
            is_moving=moving,
        )

    def take(self) -> MotionCommand | None:
        return self._last


@dataclass(slots=True)
class GenshinPoseWiring:
    """Bundle returned by :func:`wire_genshin_pose`.

    ``tick`` is the per-frame callable; the remaining members let the integrator
    feed motion, snap the belief after a teleport, and read the current pose.
    """

    tick: PoseTickFn
    feed_motion: Callable[[MotionCommand], None]
    feed_movement_intent: Callable[[MovementIntent], None]
    reset_pose: Callable[..., PoseEstimate]
    current_pose: Callable[[], PoseEstimate]
    processor: PoseEstimationProcessor
    minimap_roi: tuple[float, float, float, float]


def wire_genshin_pose(
    state_bus: StateBus,
    *,
    profile: str | None = "genshin_1920x1080",
    minimap_roi: tuple[float, float, float, float] | None = None,
    flow_world_scale: float = 1.0,
    walk_speed_world_units_per_sec: float = 5.0,
    yaw_rate_deg_per_sec: float = 0.0,
    provider: LocalizationProvider | None = None,
    fusion_config: PoseFusionConfig | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> GenshinPoseWiring:
    """Build a self-contained per-frame pose tick for the live Genshin loop.

    Parameters:
        state_bus: where the fused :class:`PoseEstimate` is published each tick.
        profile: resolution-profile id (file under ``configs/profiles/``) the
            minimap ROI is read from. Ignored if ``minimap_roi`` is given.
        minimap_roi: explicit normalized ``(x, y, w, h)`` override.
        flow_world_scale: minimap-pixel → world-unit scale (RESIDUAL — needs
            real-minimap calibration; defaults to 1.0 = pixels as units).
        walk_speed_world_units_per_sec: nominal speed used by the
            ``feed_movement_intent`` adapter for dead-reckoning.
        yaw_rate_deg_per_sec: nominal yaw rate likewise (0 = caller supplies it
            on the MotionCommand directly).
        provider: inject a custom :class:`LocalizationProvider` (tests). Defaults
            to a :class:`GenshinMinimapLocalizationProvider` on the resolved ROI.
        fusion_config: override :class:`PoseFusionConfig`.
        clock: monotonic time source (``perf_counter``).

    Returns a :class:`GenshinPoseWiring`. Drop ``wiring.tick`` into the live loop
    and ``wiring.feed_motion`` / ``wiring.feed_movement_intent`` into the
    executor path.
    """
    roi = minimap_roi if minimap_roi is not None else load_minimap_roi(profile)

    if provider is None:
        # Imported lazily so the game-agnostic wiring never hard-depends on the
        # capsule at module import time.
        from capsules.genshin.minimap_localization import GenshinMinimapLocalizationProvider

        provider = GenshinMinimapLocalizationProvider(
            minimap_roi=roi,
            flow_world_scale=flow_world_scale,
        )

    latch = _MotionLatch(
        speed_world_units_per_sec=walk_speed_world_units_per_sec,
        yaw_rate_deg_per_sec=yaw_rate_deg_per_sec,
    )
    processor = PoseEstimationProcessor(
        provider,
        fusion=PoseFusion(fusion_config),
        command_source=latch.take,
        clock=clock,
    )

    def tick(frame: np.ndarray, frame_id: int, *, observation: Any = None) -> PoseEstimate:
        now = clock()
        reading: LocalizationReading | None
        try:
            reading = provider.read(frame, frame_id, now)
        except Exception:
            reading = None
        command = latch.take()
        pose = processor.fusion.update(reading=reading, command=command, now=now)
        if observation is not None:
            try:
                observation.extensions["pose"] = pose
            except AttributeError:
                pass
        state_bus.publish_pose(pose)
        return pose

    return GenshinPoseWiring(
        tick=tick,
        feed_motion=latch.feed_motion,
        feed_movement_intent=latch.feed_movement_intent,
        reset_pose=processor.reset_pose,
        current_pose=processor.current_pose,
        processor=processor,
        minimap_roi=roi,
    )
