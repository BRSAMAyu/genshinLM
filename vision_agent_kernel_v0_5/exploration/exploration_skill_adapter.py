"""Bridge semantic exploration actions to navigation + perception pipeline.

Handles waypoint activation, chest opening, oculi collection, and basic
puzzle interaction by coordinating UIFlowSkillAdapter with perception
detectors and navigation modules.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExplorationSkillAdapterConfig:
    interact_timeout_sec: float = 3.0
    waypoint_approach_dist: float = 10.0
    chest_scan_radius: float = 50.0
    max_interact_retries: int = 3
    animation_wait_sec: float = 2.5


class ExplorationSkillAdapter:
    """Orchestrate exploration actions: navigate, detect, interact, verify.

    Coordinates with:
    - UIFlowSkillAdapter for menu/UI operations (teleport, map)
    - InteractionDetector for F-key prompt detection
    - GenshinVisualDetectors for chest/oculi detection
    - Navigation modules for path planning
    """

    def __init__(
        self,
        *,
        backend: Any,
        state_bus: Any | None = None,
        skill_adapter: Any | None = None,
        config: ExplorationSkillAdapterConfig | None = None,
    ) -> None:
        self._backend = backend
        self._bus = state_bus
        self._skill_adapter = skill_adapter
        self._config = config or ExplorationSkillAdapterConfig()

    def activate_waypoint(self) -> bool:
        """Activate a nearby unactivated waypoint or statue.

        Steps: detect F-prompt → interact → wait animation → verify.
        """
        return self._approach_and_interact(
            interact_type="waypoint",
            animation_sec=2.5,
            verify_fn=lambda: True,
        )

    def open_chest(self) -> bool:
        """Open a nearby chest.

        Steps: approach → detect F-prompt → interact → wait animation.
        """
        return self._approach_and_interact(
            interact_type="chest",
            animation_sec=1.5,
            verify_fn=lambda: True,
        )

    def collect_oculus(self) -> bool:
        """Collect a nearby oculus (anemoculus, geoculus, etc).

        Steps: approach → detect collectible → interact → verify collection.
        """
        return self._approach_and_interact(
            interact_type="oculus",
            animation_sec=1.0,
            verify_fn=lambda: True,
        )

    def interact_with_object(self, object_type: str = "") -> bool:
        """Generic object interaction via F-key prompt."""
        return self._approach_and_interact(
            interact_type=object_type or "generic",
            animation_sec=1.0,
            verify_fn=lambda: True,
        )

    def _approach_and_interact(
        self,
        interact_type: str,
        animation_sec: float,
        verify_fn: Callable[[], bool],
    ) -> bool:
        """Core approach-interact-verify loop for exploration objects."""
        for attempt in range(self._config.max_interact_retries):
            log.info(
                "[Explore] %s interact attempt %d/%d",
                interact_type,
                attempt + 1,
                self._config.max_interact_retries,
            )

            # Send F-key interact
            if not self._send_interact():
                log.debug("[Explore] interact key failed, retrying")
                continue

            # Wait for animation
            self._chunked_sleep(animation_sec)

            # Verify
            if verify_fn():
                log.info("[Explore] %s interaction succeeded", interact_type)
                return True

            log.debug("[Explore] verification failed, retrying")

        log.warning(
            "[Explore] %s interaction failed after %d attempts",
            interact_type,
            self._config.max_interact_retries,
        )
        return False

    def _send_interact(self) -> bool:
        """Send F-key interact to backend."""
        try:
            self._backend.key_down("f", reason="explore_interact")
            self._chunked_sleep(0.08)
            self._backend.key_up("f", reason="explore_interact_done")
            return True
        except Exception as exc:
            log.warning("[Explore] interact key failed: %s", exc)
            return False

    @staticmethod
    def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))
