from __future__ import annotations

import threading
from typing import Callable

from control.camera_servo import CameraServo
from control.progress_supervisor import ProgressSupervisor
from control.recovery_policy import RecoveryPolicy
from core.state_bus import StateBus
from core.types import CameraIntent, MovementIntent, Observation


class ControllerLoop:
    def __init__(
        self,
        state_bus: StateBus,
        progress_supervisor: ProgressSupervisor | None = None,
        recovery_policy: RecoveryPolicy | None = None,
        camera_servo: CameraServo | None = None,
        danger_callback: Callable[[Observation], None] | None = None,
        tick_seconds: float = 1.0 / 30.0,
    ) -> None:
        self._state_bus = state_bus
        self._progress = progress_supervisor or ProgressSupervisor(state_bus)
        self._recovery = recovery_policy or RecoveryPolicy()
        self._camera_servo = camera_servo
        self._danger_callback = danger_callback
        self._tick_seconds = tick_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_observation_version = -1

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        print("[ControllerLoop] starting controller loop", flush=True)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="controller-loop", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 2.0) -> None:
        print("[ControllerLoop] stop requested", flush=True)
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run_loop(self) -> None:
        print("[ControllerLoop] loop entered", flush=True)
        try:
            while not self._stop_event.is_set():
                snapshot = self._state_bus.latest_observation_snapshot()
                if snapshot.value is not None and snapshot.version != self._last_observation_version:
                    self._last_observation_version = snapshot.version
                    observation = snapshot.value
                    progress = self._progress.update(observation)
                    decision = self._recovery.decide(progress)
                    self._execute_decision(decision, observation)
                    print(
                        "[ControllerLoop] "
                        f"progress_trend={progress.trend} recovery_action={decision.action}",
                        flush=True,
                    )
                self._stop_event.wait(self._tick_seconds)
        finally:
            print("[ControllerLoop] loop exited", flush=True)

    def _execute_decision(self, decision: object, observation: Observation) -> None:
        if self._danger_callback is not None:
            self._danger_callback(observation)
        if self._camera_servo is not None and observation.target_track is not None:
            camera = getattr(self, "_camera_model", None)
            if camera is not None:
                error = self._camera_servo.compute_error(observation.target_track, camera)
                intent = self._camera_servo.step(error, dt=self._tick_seconds)
                camera_slot = self._state_bus.get_slot("camera_intent")
                if camera_slot is not None:
                    camera_slot.put(intent)
        camera_intent = getattr(decision, "camera_intent", None)
        if isinstance(camera_intent, CameraIntent):
            camera_slot = self._state_bus.get_slot("camera_intent")
            if camera_slot is not None:
                camera_slot.put(camera_intent)
        movement_intent = getattr(decision, "movement_intent", None)
        if isinstance(movement_intent, MovementIntent):
            movement_slot = self._state_bus.get_slot("movement_intent")
            if movement_slot is not None:
                movement_slot.put(movement_intent)
        interrupt = getattr(decision, "interrupt", None)
        if interrupt is not None:
            self._state_bus.publish_interrupt(interrupt)
