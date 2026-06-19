"""Genshin minimap localization provider.

Reads the player's world-frame motion from the Genshin minimap and exposes it as
a game-agnostic :class:`~core.types.LocalizationReading` for the pose substrate.

Genshin's minimap is north-up: the player chevron stays centred while the map
scrolls underneath. Frame-to-frame optical flow of the minimap ROI (computed by
the existing :class:`~perception.minimap_flow_tracker.MinimapFlowTracker`) is
therefore the player's world-frame displacement. We convert it into the
:class:`~core.types.PoseEstimate` world frame (x=east, y=north) and, while
moving, derive a low-trust heading from the motion bearing.

CALIBRATION: the map scrolls *opposite* to player motion and the pixel→world
scale depends on the minimap zoom, so the sign flips and ``flow_world_scale``
must be tuned against the real game. The defaults are a documented best-guess
starting point, not ground truth — see ``ROADMAP.md`` Phase 0.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from capsules.domain_protocols import ProviderHealth
from core.types import LocalizationReading
from perception.minimap_flow_tracker import MinimapFlowTracker
from perception.pose_fusion import wrap360


class GenshinMinimapLocalizationProvider:
    """LocalizationProvider backed by minimap optical flow."""

    def __init__(
        self,
        *,
        minimap_roi: tuple[float, float, float, float] = (0.0, 0.0, 0.10, 0.17),
        flow_world_scale: float = 1.0,
        invert_x: bool = True,
        invert_y: bool = True,
        emit_heading_from_flow: bool = True,
        heading_flow_min_px: float = 3.0,
        heading_trust: float = 0.3,
        tracker: Any | None = None,
    ) -> None:
        self._tracker = tracker if tracker is not None else MinimapFlowTracker(minimap_roi=minimap_roi)
        self._scale = flow_world_scale
        self._sx = -1.0 if invert_x else 1.0
        self._sy = -1.0 if invert_y else 1.0
        self._emit_heading = emit_heading_from_flow
        self._heading_min_px = heading_flow_min_px
        self._heading_trust = heading_trust

    def read(self, frame: np.ndarray, frame_id: int, timestamp: float) -> LocalizationReading:
        flow = self._tracker.update(frame)
        if flow is None:
            # First frame / unreadable minimap — no measurement this tick.
            return LocalizationReading(
                timestamp=timestamp,
                frame_id=frame_id,
                minimap_visible=True,
                source="genshin_minimap",
            )

        # minimap image coords: +x right (east), +y down. World: +x east, +y north.
        world_dx = self._scale * self._sx * flow.dx
        world_dy = self._scale * self._sy * flow.dy

        heading: float | None = None
        heading_conf = 0.0
        if self._emit_heading and flow.magnitude >= self._heading_min_px:
            # Motion bearing as heading — valid only while moving forward, hence low trust.
            heading = wrap360(math.degrees(math.atan2(world_dx, world_dy)))
            heading_conf = self._heading_trust * flow.confidence

        return LocalizationReading(
            timestamp=timestamp,
            frame_id=frame_id,
            heading_deg=heading,
            heading_confidence=heading_conf,
            flow_dx=world_dx,
            flow_dy=world_dy,
            flow_confidence=flow.confidence,
            minimap_visible=True,
            source="genshin_minimap",
            metadata={"flow_px": (flow.dx, flow.dy), "flow_mag_px": flow.magnitude},
        )

    def set_walking(self, walking: bool) -> None:
        """Forward WASD state to the flow tracker (improves its stuck assessment)."""
        setter = getattr(self._tracker, "set_walking", None)
        if callable(setter):
            setter(walking)

    def health(self) -> ProviderHealth:
        return ProviderHealth("ok", "GenshinMinimapLocalizationProvider ready")
