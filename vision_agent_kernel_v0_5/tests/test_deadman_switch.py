from __future__ import annotations

import time

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import InputLease
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker


def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not met before timeout")


def _lease(lease_id: str, key: str, expires_at: float) -> InputLease:
    return InputLease(
        lease_id=lease_id,
        owner="test",
        priority=10,
        key_states={key: "DOWN"},
        mouse_delta=None,
        created_at=time.perf_counter(),
        expires_at=expires_at,
        reason="unit test",
    )


def test_deadman_switch_releases_expired_key() -> None:
    timebase = Timebase()
    backend = ConsoleInputBackend(timebase)
    worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.005)
    expires_at = timebase.now() + 0.03

    worker.start()
    try:
        assert worker.submit_lease(_lease("lease-1", "W", expires_at))
        _wait_for(lambda: "W" in backend.down_keys_snapshot())
        _wait_for(
            lambda: any(
                event.action == "key_up" and event.payload["reason"] == "deadman_expired"
                for event in backend.events_snapshot()
            ),
            timeout=1.0,
        )
        assert "W" not in backend.down_keys_snapshot()
    finally:
        worker.stop()


def test_p0_interrupt_release_all() -> None:
    timebase = Timebase()
    backend = ConsoleInputBackend(timebase)
    worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.005)
    interrupt = Interrupt(
        priority=0,
        timestamp=timebase.now(),
        code="EMERGENCY_STOP",
        source="unit_test",
        requires_input_release=True,
    )

    worker.start()
    try:
        assert worker.submit_lease(_lease("lease-1", "W", timebase.now() + 1.0))
        _wait_for(lambda: "W" in backend.down_keys_snapshot())
        assert worker.submit_interrupt(interrupt)
        _wait_for(
            lambda: any(
                event.action == "release_all"
                and event.payload["reason"] == "interrupt:EMERGENCY_STOP"
                for event in backend.events_snapshot()
            )
        )
        assert backend.down_keys_snapshot() == set()
    finally:
        worker.stop()


def test_worker_stop_finally_release_all() -> None:
    timebase = Timebase()
    backend = ConsoleInputBackend(timebase)
    worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.005)

    worker.start()
    assert worker.submit_lease(_lease("lease-1", "W", timebase.now() + 1.0))
    _wait_for(lambda: "W" in backend.down_keys_snapshot())
    worker.stop()

    assert backend.down_keys_snapshot() == set()
    assert any(
        event.action == "release_all" and event.payload["reason"] == "input_worker_exit"
        for event in backend.events_snapshot()
    )


def test_focus_loss_releases_all_and_interrupts() -> None:
    timebase = Timebase()
    state_bus = StateBus()

    class MockBackend(ConsoleInputBackend):
        def __init__(self, timebase):
            super().__init__(timebase)
            self.focused = True

        def is_target_focused(self) -> bool:
            return self.focused

    backend = MockBackend(timebase)
    worker = InputWorker(
        backend=backend,
        timebase=timebase,
        tick_seconds=0.005,
        state_bus=state_bus,
    )

    interrupts = []
    state_bus.subscribe("interrupt", lambda intr: interrupts.append(intr))

    worker.start()
    try:
        assert worker.submit_lease(_lease("lease-1", "W", timebase.now() + 1.0))
        _wait_for(lambda: "W" in backend.down_keys_snapshot())

        backend.focused = False

        _wait_for(
            lambda: any(
                event.action == "release_all" and event.payload["reason"] == "focus_lost"
                for event in backend.events_snapshot()
            )
        )

        assert backend.down_keys_snapshot() == set()

        _wait_for(lambda: len(interrupts) > 0)
        assert interrupts[0].code == "FOCUS_LOST"
        assert interrupts[0].priority == 0
    finally:
        worker.stop()

