from __future__ import annotations

import time

from core.timebase import Timebase
from core.types import InputLease
from execution.console_backend import ConsoleInputBackend
from execution.input_lease import DOWN, UP, InputLeaseStore
from execution.input_worker import InputWorker
from core.events import Interrupt


def _lease(lease_id: str, key: str, expires_at: float, state: str = DOWN) -> InputLease:
    return InputLease(
        lease_id=lease_id,
        owner="test",
        priority=10,
        key_states={key: state},
        mouse_delta=None,
        created_at=time.perf_counter(),
        expires_at=expires_at,
        reason="unit test",
    )


def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not met before timeout")


def test_input_lease_rejects_expired_down_key() -> None:
    timebase = Timebase()
    store = InputLeaseStore()
    now = timebase.now()

    result = store.validate(_lease("expired", "W", expires_at=now - 0.1), now=now)

    assert not result.valid
    assert "expired" in result.reason


def test_input_worker_applies_up_without_registering_deadman_lease() -> None:
    timebase = Timebase()
    backend = ConsoleInputBackend(timebase)
    worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.005)
    now = timebase.now()

    worker.start()
    try:
        assert worker.submit_lease(_lease("up", "W", expires_at=now + 1.0, state=UP))
        _wait_for(lambda: any(event.action == "key_up" for event in backend.events_snapshot()))
        assert worker.active_keys_snapshot() == set()
    finally:
        worker.stop()


def test_input_worker_atomic_actions_execute() -> None:
    timebase = Timebase()
    backend = ConsoleInputBackend(timebase)
    worker = InputWorker(backend=backend, timebase=timebase, tick_seconds=0.005)
    now = timebase.now()

    worker.start()
    try:
        lease = InputLease(
            lease_id="atomic-actions",
            owner="test",
            priority=10,
            key_states={},
            mouse_delta=None,
            created_at=time.perf_counter(),
            expires_at=now + 1.0,
            reason="atomic actions",
            actions=[
                {"type": "left_click"},
                {"type": "mouse_scroll", "delta": -1},
                {"type": "type_text", "text": "abc", "delay_between_keys_ms": 1},
                {"type": "execute_combo", "keys": ["ctrl", "c"], "hold_time_ms": 1},
            ],
        )
        assert worker.submit_lease(lease)
        _wait_for(
            lambda: {"left_click", "mouse_scroll", "type_text", "execute_combo"}.issubset(
                {e.action for e in backend.events_snapshot()}
            )
        )
    finally:
        worker.stop()


def test_input_worker_critical_interrupt_not_dropped_when_queue_full() -> None:
    timebase = Timebase()
    backend = ConsoleInputBackend(timebase)
    worker = InputWorker(
        backend=backend,
        timebase=timebase,
        tick_seconds=0.05,
        command_queue_size=1,
    )
    now = timebase.now()

    # Fill queue with a lease first, then ensure interrupt still accepted.
    assert worker.submit_lease(_lease("queued-lease", "W", expires_at=now + 1.0))
    accepted = worker.submit_interrupt(
        Interrupt(
            priority=0,
            timestamp=now,
            code="QUEUE_PRESSURE_INTERRUPT",
            source="unit_test",
            requires_input_release=True,
        )
    )
    assert accepted is True
