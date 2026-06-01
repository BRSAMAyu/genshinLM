from __future__ import annotations

import logging
import math
import threading
import time
from typing import TYPE_CHECKING, Any, Callable

from navigation.minimap_quest_reader import MinimapQuestReader
from control.camera_servo import CameraServo, genshin_camera_servo_config
from core.types import CameraControlError

if TYPE_CHECKING:
    from execution.safe_window_backend import SafeWindowInputBackend
    import numpy

log = logging.getLogger(__name__)


def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))


class QuestMarkerFollower:
    """Real-time WASD navigation following quest marker direction."""

    _ANGLE_THRESHOLD = math.pi / 8  # 22.5 degrees tolerance for forward

    def __init__(
        self,
        backend: SafeWindowInputBackend,
        reader: MinimapQuestReader,
        servo: CameraServo | None = None,
        state_bus: Any | None = None,
    ) -> None:
        self._backend = backend
        self._reader = reader
        self._servo = servo or CameraServo(genshin_camera_servo_config())
        self._bus = state_bus

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
                _chunked_sleep(0.1)
                continue

            if self._reader.is_at_destination(frame):
                log.info("[QuestFollower] arrived at destination after %d steps", step)
                self._publish_nav_state("arrived", step)
                return True

            angle = self._reader.read_quest_direction(frame)
            if angle is None:
                log.debug("[QuestFollower] no quest marker at step %d", step)
                _chunked_sleep(0.5)
                continue

            # Convert angle to camera error
            error = CameraControlError(
                yaw_error_deg=math.degrees(angle),
                pitch_error_deg=0.0,
                angular_distance_deg=abs(math.degrees(angle)),
                target_confidence=1.0,
                stale=False,
            )

            # Determine keys based on the quest marker angle
            keys = self._angle_to_keys(angle)

            # Press keys
            for key in keys:
                try:
                    self._backend.key_down(key, reason="quest_follow")
                except Exception as exc:
                    log.warning("key_down %s failed: %s", key, exc)

            # Rotate camera smoothly during the step_interval
            intents = self._servo.step_multi(error, dt=step_interval)
            total_duration = 0.0
            for intent in intents:
                if abs(intent.yaw_delta) > 1e-5 or abs(intent.pitch_delta) > 1e-5:
                    try:
                        self._backend.mouse_move(intent.yaw_delta, intent.pitch_delta, reason="quest_camera_servo")
                    except Exception as exc:
                        log.warning("camera servo mouse_move failed: %s", exc)
                sleep_time = intent.duration_ms / 1000.0
                _chunked_sleep(sleep_time)
                total_duration += sleep_time

            # If the camera servo didn't consume the full step_interval, sleep the remainder
            remaining = step_interval - total_duration
            if remaining > 0:
                _chunked_sleep(remaining)

            # Release keys
            for key in keys:
                try:
                    self._backend.key_up(key, reason="quest_follow_done")
                except Exception as exc:
                    log.warning("key_up %s failed: %s", key, exc)

        log.warning("[QuestFollower] max_steps (%d) exhausted", max_steps)
        self._publish_nav_state("exhausted", max_steps)
        return False

    def _publish_nav_state(self, status: str, step: int) -> None:
        """Publish navigation progress to StateBus."""
        if self._bus is None:
            return
        try:
            if hasattr(self._bus, "navigation_signal"):
                nav = self._bus.navigation_signal.get()
                if nav is not None:
                    nav_dict = {
                        "status": status,
                        "step": step,
                        "timestamp": time.perf_counter(),
                    }
                    self._bus.navigation_signal.put(type(nav)(**{
                        k: getattr(nav, k) for k in nav.__dataclass_fields__
                    }))
        except Exception:
            pass

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

