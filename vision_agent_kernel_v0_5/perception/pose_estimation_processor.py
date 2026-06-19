"""Pose estimation as a perception post-processor.

Game-agnostic glue that turns a :class:`LocalizationProvider`'s per-frame
readings (plus optional dead-reckoning from the executor) into a fused
:class:`~core.types.PoseEstimate`, published on ``StateBus.latest_pose`` and
stashed in ``observation.extensions["pose"]`` so every plane can read one shared
belief.

It plugs into the fast perception pipeline via the ``FramePostProcessor``
protocol (``process(frame, observation, state_bus)``), running once per frame
before the observation is published. The provider is the only game-specific
part; this processor and :class:`~perception.pose_fusion.PoseFusion` are reused
across capsules.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Protocol

import numpy as np

from core.state_bus import StateBus
from core.types import LocalizationReading, MotionCommand, Observation, PoseEstimate
from perception.pose_fusion import PoseFusion


class LocalizationProvider(Protocol):
    """Per-frame localization reader (see capsules.domain_protocols)."""

    def read(self, frame: np.ndarray, frame_id: int, timestamp: float) -> LocalizationReading:
        ...


class PoseEstimationProcessor:
    """FramePostProcessor that maintains and publishes the fused pose belief.

    Parameters:
        provider: game-specific :class:`LocalizationProvider`.
        fusion: the estimator (defaults to a fresh :class:`PoseFusion`).
        command_source: optional callable returning the most recently commanded
            :class:`MotionCommand` for dead-reckoning; ``None`` → correct from
            sensors only. Decoupled so the executor can feed it without the
            perception plane importing control/execution.
        clock: monotonic time source, used only when an observation carries no
            capture timestamp.
    """

    def __init__(
        self,
        provider: LocalizationProvider,
        *,
        fusion: PoseFusion | None = None,
        command_source: Callable[[], MotionCommand | None] | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._provider = provider
        self._fusion = fusion or PoseFusion()
        self._command_source = command_source
        self._clock = clock

    @property
    def fusion(self) -> PoseFusion:
        return self._fusion

    def process(self, frame: np.ndarray, observation: Observation, state_bus: StateBus) -> None:
        now = observation.t_capture or self._clock()

        reading: LocalizationReading | None
        try:
            reading = self._provider.read(frame, observation.frame_id, now)
        except Exception:
            reading = None

        command: MotionCommand | None = None
        if self._command_source is not None:
            try:
                command = self._command_source()
            except Exception:
                command = None

        pose = self._fusion.update(reading=reading, command=command, now=now)
        observation.extensions["pose"] = pose
        state_bus.publish_pose(pose)

    def reset_pose(
        self,
        position: tuple[float, float],
        heading_deg: float,
        *,
        timestamp: float | None = None,
        confidence: float = 1.0,
    ) -> PoseEstimate:
        """Snap the belief to a known pose — call after a teleport/absolute fix."""
        self._fusion.reset(
            position,
            heading_deg,
            timestamp=timestamp if timestamp is not None else self._clock(),
            confidence=confidence,
        )
        pose = self._fusion.current()
        return pose

    def current_pose(self) -> PoseEstimate:
        return self._fusion.current()
