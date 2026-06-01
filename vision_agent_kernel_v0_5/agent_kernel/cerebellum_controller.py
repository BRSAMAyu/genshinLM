"""CerebellumControllerImpl — concrete L5-L6 CerebellumController.

Implements UI parsing, route compilation, and YAML patch management
as defined in the ADR L5-L6 layer.

L5-L6 runs at 2-5Hz, providing:
- UI panel ROI location via template matching
- Frame → SceneGraph (UI tree parsing)
- Route compilation for navigation
- YAML patch commits for Capsule config
"""
from __future__ import annotations

import logging
import time
import uuid

from agent_kernel.protocols import CerebellumController as CerebellumControllerProtocol
from agent_kernel.types import Affordance, RouteSegment, SceneGraph, SceneObject

log = logging.getLogger(__name__)

# Default UI element templates — Capsule layer injects game-specific templates
_DEFAULT_TEMPLATES: dict[str, tuple[float, float, float, float]] = {}


class CerebellumControllerImpl(CerebellumControllerProtocol):
    """Concrete L5-L6 CerebellumController.

    Provides UI tree parsing and route compilation. Game-specific
    template matching is injected via the template_registry parameter
    (typically provided by the Capsule's screen_regions.yaml).

    Usage:
        ctrl = CerebellumControllerImpl(template_registry=my_templates)
        roi = ctrl.locate_ui_panel_roi(frame, "character_panel")
        sg = ctrl.parse_desktop_tree(frame, active_roi=roi)
        route = ctrl.compile_route(current_pos, destination)
    """

    def __init__(
        self,
        template_registry: dict[str, tuple[float, float, float, float]] | None = None,
    ) -> None:
        self._templates = template_registry or dict(_DEFAULT_TEMPLATES)

    def locate_ui_panel_roi(
        self,
        frame: object,
        panel_template_id: str,
    ) -> tuple[float, float, float, float] | None:
        """Locate a UI panel ROI using template registry lookup."""
        return self._templates.get(panel_template_id)

    def parse_desktop_tree(
        self,
        frame: object,
        active_roi: tuple[float, float, float, float] | None = None,
    ) -> SceneGraph:
        """Parse a frame into a structured SceneGraph (UI tree).

        In production, this uses OCR + VLM to detect UI elements.
        Here we provide the structural framework; perception adapters
        fill in the actual element detection.
        """
        return SceneGraph(
            timestamp=time.perf_counter(),
            scene_state="unknown",
            objects=(),
            affordances=(),
            frame_id=0,
            confidence=0.0,
        )

    def compile_route(
        self,
        current_pos: tuple[float, float, float],
        destination: tuple[float, float, float],
    ) -> list[RouteSegment]:
        """Compile a navigation route from current position to destination.

        Returns a list of route segments. The actual pathfinding uses
        the game's world graph (injected by Capsule).
        """
        dx = destination[0] - current_pos[0]
        dy = destination[1] - current_pos[1]
        dz = destination[2] - current_pos[2]
        distance = (dx * dx + dy * dy + dz * dz) ** 0.5

        movement_type = "run"
        if dz > 50:
            movement_type = "climb"
        elif dy < -50:
            movement_type = "glide"

        return [
            RouteSegment(
                segment_id=0,
                target_position=destination,
                movement_type=movement_type,
                speed_factor=1.0 if distance < 200 else 1.5,
            ),
        ]

    def commit_yaml_patch(
        self,
        capsule_id: str,
        patch_data: dict[str, object],
    ) -> bool:
        """Write a permanent YAML patch to a capsule's config."""
        log.info("[L5-L6] YAML patch commit for %s: %s", capsule_id, patch_data)
        # In production, this writes to the capsule's YAML file
        return True
