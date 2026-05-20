from __future__ import annotations

import time

from core.timebase import Timebase
from core.types import InputLease
from execution.console_backend import ConsoleInputBackend
from execution.input_lease import DOWN, UP, InputLeaseStore
from execution.input_worker import InputWorker


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
