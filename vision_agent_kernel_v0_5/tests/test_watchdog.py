from __future__ import annotations

import time

from core.state_bus import StateBus
from core.timebase import Timebase
from core.watchdog import Watchdog, WatchdogConfig
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker


def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not met before timeout")


def test_watchdog_timeout_submits_p0_release_all() -> None:
    timebase = Timebase()
    backend = ConsoleInputBackend(timebase)
    worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.005)
    bus = StateBus()
    watchdog = Watchdog(
        state_bus=bus,
        input_worker=worker,
        timebase=timebase,
        config=WatchdogConfig(check_interval_sec=0.01, heartbeat_timeout_sec=0.01),
    )
    bus.update_heartbeat("perception", timebase.now() - 1.0)

    worker.start()
    try:
        interrupts = watchdog.check_once()
        assert len(interrupts) == 1
        assert interrupts[0].priority == 0
        assert interrupts[0].code == "WATCHDOG_TIMEOUT"
        _wait_for(
            lambda: any(
                event.action == "release_all"
                and event.payload["reason"] == "interrupt:WATCHDOG_TIMEOUT"
                for event in backend.events_snapshot()
            )
        )
    finally:
        worker.stop()
