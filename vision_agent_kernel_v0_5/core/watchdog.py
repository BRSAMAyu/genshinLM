from __future__ import annotations

import threading
from dataclasses import dataclass

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from execution.input_worker import InputWorker


@dataclass(frozen=True, slots=True)
class WatchdogConfig:
    check_interval_sec: float = 0.2
    heartbeat_timeout_sec: float = 1.0


class Watchdog:
    def __init__(
        self,
        state_bus: StateBus,
        input_worker: InputWorker,
        timebase: Timebase | None = None,
        config: WatchdogConfig | None = None,
    ) -> None:
        self._state_bus = state_bus
        self._input_worker = input_worker
        self._timebase = timebase or Timebase()
        self._config = config or WatchdogConfig()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._fired_sources: set[str] = set()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            print("[Watchdog] start ignored; already running", flush=True)
            return
        print("[Watchdog] starting watchdog loop", flush=True)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="watchdog", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 2.0) -> None:
        print("[Watchdog] stop requested", flush=True)
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def check_once(self) -> list[Interrupt]:
        now = self._timebase.now()
        interrupts: list[Interrupt] = []
        for owner, heartbeat_at in self._state_bus.heartbeat_snapshot().items():
            age = now - heartbeat_at
            if age <= self._config.heartbeat_timeout_sec or owner in self._fired_sources:
                continue
            interrupt = Interrupt(
                priority=0,
                timestamp=now,
                code="WATCHDOG_TIMEOUT",
                source="watchdog",
                payload={"owner": owner, "heartbeat_age_sec": age},
                recoverable=False,
                requires_input_release=True,
            )
            self._fired_sources.add(owner)
            print(
                "[Watchdog] "
                f"{now:.6f} timeout owner={owner} age={age:.3f}s -> release_all",
                flush=True,
            )
            self._state_bus.publish_interrupt(interrupt)
            self._input_worker.submit_interrupt(interrupt)
            interrupts.append(interrupt)
        return interrupts

    def _run_loop(self) -> None:
        print("[Watchdog] loop entered", flush=True)
        try:
            while not self._stop_event.wait(self._config.check_interval_sec):
                self.check_once()
        finally:
            print("[Watchdog] loop exited", flush=True)

    def __enter__(self) -> Watchdog:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop()
