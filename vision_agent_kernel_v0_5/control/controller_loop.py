from __future__ import annotations

import threading

from control.progress_supervisor import ProgressSupervisor
from control.recovery_policy import RecoveryPolicy
from core.state_bus import StateBus


class ControllerLoop:
    def __init__(
        self,
        state_bus: StateBus,
        progress_supervisor: ProgressSupervisor | None = None,
        recovery_policy: RecoveryPolicy | None = None,
        tick_seconds: float = 1.0 / 30.0,
    ) -> None:
        self._state_bus = state_bus
        self._progress = progress_supervisor or ProgressSupervisor(state_bus)
        self._recovery = recovery_policy or RecoveryPolicy()
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
                    progress = self._progress.update(snapshot.value)
                    decision = self._recovery.decide(progress)
                    print(
                        "[ControllerLoop] "
                        f"progress_trend={progress.trend} recovery_action={decision.action}",
                        flush=True,
                    )
                self._stop_event.wait(self._tick_seconds)
        finally:
            print("[ControllerLoop] loop exited", flush=True)
