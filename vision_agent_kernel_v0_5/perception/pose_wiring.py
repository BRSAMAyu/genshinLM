"""One-call wiring of pose estimation into a perception pipeline.

Keeps the integration point tiny and testable so the live factory only needs::

    from perception.pose_wiring import attach_pose_estimation
    pose_proc = attach_pose_estimation(pipeline, provider, command_source=executor_motion)

rather than hand-assembling the processor inline. Returns the
:class:`~perception.pose_estimation_processor.PoseEstimationProcessor` so the
caller can later call ``pose_proc.reset_pose(...)`` after a teleport (a known
absolute fix) and read ``pose_proc.current_pose()``.
"""
from __future__ import annotations

from typing import Any, Callable

from core.types import MotionCommand
from perception.pose_estimation_processor import (
    LocalizationProvider,
    PoseEstimationProcessor,
)
from perception.pose_fusion import PoseFusion, PoseFusionConfig


def attach_pose_estimation(
    pipeline: Any,
    provider: LocalizationProvider,
    *,
    command_source: Callable[[], MotionCommand | None] | None = None,
    fusion: PoseFusion | None = None,
    fusion_config: PoseFusionConfig | None = None,
) -> PoseEstimationProcessor:
    """Build a :class:`PoseEstimationProcessor` and register it on ``pipeline``.

    ``pipeline`` must expose ``add_post_processor(FramePostProcessor)`` (the
    standard perception-pipeline seam). ``command_source`` lets the executor feed
    the last commanded :class:`MotionCommand` for dead-reckoning.
    """
    processor = PoseEstimationProcessor(
        provider,
        fusion=fusion or PoseFusion(fusion_config),
        command_source=command_source,
    )
    pipeline.add_post_processor(processor)
    return processor
