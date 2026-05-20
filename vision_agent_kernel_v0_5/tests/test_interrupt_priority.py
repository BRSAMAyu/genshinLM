from __future__ import annotations

from core.events import Interrupt
from core.state_bus import PriorityEventQueue


def test_interrupt_priority_order() -> None:
    queue: PriorityEventQueue[Interrupt] = PriorityEventQueue()
    queue.put(Interrupt(priority=2, timestamp=1.0, code="TARGET_LOST", source="test"), priority=2)
    queue.put(Interrupt(priority=0, timestamp=2.0, code="EMERGENCY_STOP", source="test"), priority=0)
    queue.put(Interrupt(priority=1, timestamp=3.0, code="CONTROL_LOST", source="test"), priority=1)

    assert queue.get_nowait().code == "EMERGENCY_STOP"
    assert queue.get_nowait().code == "CONTROL_LOST"
    assert queue.get_nowait().code == "TARGET_LOST"


def test_priority_queue_drops_lower_value_when_full() -> None:
    queue: PriorityEventQueue[Interrupt] = PriorityEventQueue(capacity=2)
    assert queue.put(Interrupt(priority=2, timestamp=1.0, code="P2", source="test"), priority=2)
    assert queue.put(Interrupt(priority=3, timestamp=2.0, code="P3", source="test"), priority=3)
    assert queue.put(Interrupt(priority=0, timestamp=3.0, code="P0", source="test"), priority=0)

    codes = {queue.get_nowait().code, queue.get_nowait().code}
    assert codes == {"P0", "P2"}
