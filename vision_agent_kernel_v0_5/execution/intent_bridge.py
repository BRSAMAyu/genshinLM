"""Intent-to-Lease bridge: converts CameraIntent/MovementIntent from StateBus
into InputLease commands submitted to InputWorker.

This is the critical connection between the control plane (30Hz) and the
execution plane (100Hz). Without it, the controller publishes intents that
nobody consumes.
"""
from __future__ import annotations

import threading
import uuid

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import CameraIntent, InputLease, MovementIntent
from execution.input_worker import InputWorker


# Movement axis → key mapping
_FORWARD_KEY = "w"
_BACKWARD_KEY = "s"
_LEFT_KEY = "a"
_RIGHT_KEY = "d"
_JUMP_KEY = "space"
_DASH_KEY = "shift"


class IntentBridge:
    """Bridges StateBus intent slots → InputWorker lease submissions.

    Runs a background thread that polls "camera_intent" and "movement_intent"
    dynamic slots from StateBus and converts them to InputLease commands.
    """

    def __init__(
        self,
        state_bus: StateBus,
        input_worker: InputWorker,
        timebase: Timebase | None = None,
        pixels_per_degree: float = 8.0,
        default_lease_ms: int = 80,
        tick_seconds: float = 0.01,
    ) -> None:
        self._state_bus = state_bus
        self._input_worker = input_worker
        self._timebase = timebase or Timebase()
        self._pixels_per_degree = pixels_per_degree
        self._default_lease_ms = default_lease_ms
        self._tick_seconds = tick_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Ensure dynamic slots exist
        self._camera_slot = self._state_bus.register_slot("camera_intent")
        self._movement_slot = self._state_bus.register_slot("movement_intent")

        # Track held movement keys so we can release them
        self._active_movement_keys: set[str] = set()
        self._movement_lock = threading.Lock()

        # Version tracking to avoid reprocessing the same intent
        self._last_camera_version = -1
        self._last_movement_version = -1

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="intent-bridge", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 2.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                self._drain_camera_intent()
                self._drain_movement_intent()
                self._stop_event.wait(self._tick_seconds)
        finally:
            self._release_movement_keys()

    def _drain_camera_intent(self) -> None:
        snapshot = self._camera_slot.snapshot()
        if snapshot.value is None or snapshot.version == self._last_camera_version:
            return
        self._last_camera_version = snapshot.version
        intent = snapshot.value
        if not isinstance(intent, CameraIntent):
            return
        if abs(intent.yaw_delta) < 0.001 and abs(intent.pitch_delta) < 0.001:
            return
        now = self._timebase.now()
        # Pass raw degree deltas — the backend (SafeWindowInputBackend) does
        # the degree→pixel conversion itself via pixels_per_degree.
        lease = InputLease(
            lease_id=str(uuid.uuid4()),
            owner="intent_bridge:camera",
            priority=30,
            key_states={},
            mouse_delta=(intent.yaw_delta, intent.pitch_delta),
            created_at=now,
            expires_at=now + intent.duration_ms / 1000.0,
            reason=intent.reason,
        )
        self._input_worker.submit_lease(lease)

    def _drain_movement_intent(self) -> None:
        snapshot = self._movement_slot.snapshot()
        if snapshot.value is None or snapshot.version == self._last_movement_version:
            return
        self._last_movement_version = snapshot.version
        intent = snapshot.value
        if not isinstance(intent, MovementIntent):
            return

        now = self._timebase.now()
        duration_sec = intent.duration_ms / 1000.0
        key_states: dict[str, str] = {}
        desired_keys: set[str] = set()

        if intent.move_forward > 0.1:
            key_states[_FORWARD_KEY] = "DOWN"
            desired_keys.add(_FORWARD_KEY)
        elif intent.move_forward < -0.1:
            key_states[_BACKWARD_KEY] = "DOWN"
            desired_keys.add(_BACKWARD_KEY)

        if intent.move_right > 0.1:
            key_states[_RIGHT_KEY] = "DOWN"
            desired_keys.add(_RIGHT_KEY)
        elif intent.move_right < -0.1:
            key_states[_LEFT_KEY] = "DOWN"
            desired_keys.add(_LEFT_KEY)

        if intent.jump:
            key_states[_JUMP_KEY] = "DOWN"
            desired_keys.add(_JUMP_KEY)

        if intent.dash:
            key_states[_DASH_KEY] = "DOWN"
            desired_keys.add(_DASH_KEY)

        # Release keys no longer needed
        with self._movement_lock:
            to_release = self._active_movement_keys - desired_keys
            self._active_movement_keys = desired_keys

        for key in to_release:
            release_lease = InputLease(
                lease_id=str(uuid.uuid4()),
                owner="intent_bridge:movement:release",
                priority=30,
                key_states={key: "UP"},
                mouse_delta=None,
                created_at=now,
                expires_at=now + 0.05,
                reason=f"movement_release:{key}",
            )
            self._input_worker.submit_lease(release_lease)

        if not key_states:
            return

        lease = InputLease(
            lease_id=str(uuid.uuid4()),
            owner="intent_bridge:movement",
            priority=30,
            key_states=key_states,
            mouse_delta=None,
            created_at=now,
            expires_at=now + duration_sec,
            reason=intent.reason or "movement",
        )
        self._input_worker.submit_lease(lease)

    def _release_movement_keys(self) -> None:
        with self._movement_lock:
            keys = sorted(self._active_movement_keys)
            self._active_movement_keys.clear()
        now = self._timebase.now()
        for key in keys:
            release_lease = InputLease(
                lease_id=str(uuid.uuid4()),
                owner="intent_bridge:shutdown",
                priority=0,
                key_states={key: "UP"},
                mouse_delta=None,
                created_at=now,
                expires_at=now + 0.1,
                reason="intent_bridge_shutdown",
            )
            self._input_worker.submit_lease(release_lease)
