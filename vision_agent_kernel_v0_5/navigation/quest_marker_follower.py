from __future__ import annotations

import logging
import math
import threading
import time
from typing import TYPE_CHECKING

from navigation.minimap_quest_reader import MinimapQuestReader

if TYPE_CHECKING:
    from execution.safe_window_backend import SafeWindowInputBackend

log = logging.getLogger(__name__)


class QuestMarkerFollower:
    """Real-time WASD navigation following quest marker direction."""

    _ANGLE_THRESHOLD = math.pi / 8  # 22.5 degrees tolerance for forward

    def __init__(self, backend: SafeWindowInputBackend, reader: MinimapQuestReader) -> None:
        self._backend = backend
        self._reader = reader

    def navigate_to_marker(
        self,
        frame_source,  # callable returning np.ndarray | None
        max_steps: int = 300,
        shutdown_event: threading.Event | None = None,
        step_interval: float = 0.3,
    ) -> bool:
        """Follow quest marker until arriving or max_steps exhausted."""
        for step in range(max_steps):
            if shutdown_event and shutdown_event.is_set():
                log.info("[QuestFollower] interrupted at step %d", step)
                return False

            frame = frame_source()
            if frame is None:
                time.sleep(0.1)
                continue

            if self._reader.is_at_destination(frame):
                log.info("[QuestFollower] arrived at destination after %d steps", step)
                return True

            angle = self._reader.read_quest_direction(frame)
            if angle is None:
                log.debug("[QuestFollower] no quest marker at step %d", step)
                time.sleep(0.5)
                continue

            keys = self._angle_to_keys(angle)
            self._hold_keys_briefly(keys, step_interval)

        log.warning("[QuestFollower] max_steps (%d) exhausted", max_steps)
        return False

    def _angle_to_keys(self, angle: float) -> list[str]:
        """Convert angle to WASD keys. 0=up(W), pi/2=right(D), pi=down(S), -pi/2=left(A)."""
        keys: list[str] = []
        # Normalize angle to [-pi, pi]
        angle = math.atan2(math.sin(angle), math.cos(angle))

        # Forward component (W)
        if abs(angle) < self._ANGLE_THRESHOLD * 3:  # within ~67 degrees of forward
            keys.append("w")
        elif abs(angle) > math.pi - self._ANGLE_THRESHOLD:  # roughly backward
            keys.append("s")

        # Side component
        if angle > self._ANGLE_THRESHOLD:
            keys.append("d")
        elif angle < -self._ANGLE_THRESHOLD:
            keys.append("a")

        # Default: at least go forward
        if not keys:
            keys.append("w")

        return keys

    def _hold_keys_briefly(self, keys: list[str], duration: float) -> None:
        """Press keys for a brief duration."""
        for key in keys:
            try:
                self._backend.key_down(key, reason="quest_follow")
            except Exception:
                pass
        time.sleep(duration)
        for key in keys:
            try:
                self._backend.key_up(key, reason="quest_follow_done")
            except Exception:
                pass
