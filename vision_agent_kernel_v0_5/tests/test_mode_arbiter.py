from __future__ import annotations

from core.events import ModeRequest
from core.mode_arbiter import (
    EMERGENCY_STOPPED,
    IDLE,
    P0_EMERGENCY,
    P4_RECOVERY,
    P5_TRACKING,
    RECOVERING,
    TRACKING_TARGET,
    ModeArbiter,
)
from core.state_bus import StateBus


def _request(mode: str, priority: int, timestamp: float = 1.0) -> ModeRequest:
    return ModeRequest(
        requested_mode=mode,
        owner="test",
        priority=priority,
        reason="unit test",
        timestamp=timestamp,
    )


def test_mode_request_priority_arbitration() -> None:
    arbiter = ModeArbiter(initial_mode=IDLE)

    tracking = arbiter.submit(_request(TRACKING_TARGET, P5_TRACKING, timestamp=1.0))
    assert tracking.accepted
    assert tracking.current_mode == TRACKING_TARGET

    lower = arbiter.submit(_request(IDLE, priority=100, timestamp=2.0))
    assert not lower.accepted
    assert lower.current_mode == TRACKING_TARGET

    recovery = arbiter.submit(_request(RECOVERING, P4_RECOVERY, timestamp=3.0))
    assert recovery.accepted
    assert recovery.current_mode == RECOVERING

    emergency = arbiter.submit(_request(EMERGENCY_STOPPED, P0_EMERGENCY, timestamp=4.0))
    assert emergency.accepted
    assert emergency.current_mode == EMERGENCY_STOPPED


def test_mode_arbiter_drains_state_bus_request() -> None:
    bus = StateBus()
    arbiter = ModeArbiter()
    bus.submit_mode_request(_request(TRACKING_TARGET, P5_TRACKING))

    decision = arbiter.drain_once(bus)

    assert decision is not None
    assert decision.accepted
    assert bus.current_mode.get() == TRACKING_TARGET
