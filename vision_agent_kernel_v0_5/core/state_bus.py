from __future__ import annotations

import heapq
import threading
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Generic, TypeVar, Any, Callable, TYPE_CHECKING

from core.events import Interrupt, ModeRequest
from core.types import Observation, ProgressState
from planning.screen_state_claim import ScreenStateClaim

if TYPE_CHECKING:
    from perception.fusion_runtime import FrameQuality


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SlotSnapshot(Generic[T]):
    value: T | None
    version: int


class LatestSlot(Generic[T]):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._value: T | None = None
        self._version = 0

    def put(self, value: T) -> int:
        with self._lock:
            self._value = value
            self._version += 1
            return self._version

    def get(self) -> T | None:
        with self._lock:
            return self._value

    def snapshot(self) -> SlotSnapshot[T]:
        with self._lock:
            return SlotSnapshot(value=self._value, version=self._version)

    @property
    def version(self) -> int:
        with self._lock:
            return self._version


class RingBuffer(Generic[T]):
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._lock = threading.RLock()
        self._items: deque[T] = deque(maxlen=capacity)

    def append(self, value: T) -> None:
        with self._lock:
            self._items.append(value)

    def snapshot(self) -> list[T]:
        with self._lock:
            return list(self._items)

    def latest(self) -> T | None:
        with self._lock:
            if not self._items:
                return None
            return self._items[-1]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


@dataclass(order=True, slots=True)
class _QueuedItem(Generic[T]):
    priority: int
    sequence: int
    item: T = field(compare=False)


class PriorityEventQueue(Generic[T]):
    def __init__(self, capacity: int = 1024) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._lock = threading.RLock()
        self._not_empty = threading.Condition(self._lock)
        self._heap: list[_QueuedItem[T]] = []
        self._sequence = 0

    def put(self, item: T, priority: int) -> bool:
        with self._not_empty:
            if len(self._heap) >= self._capacity and not self._drop_lowest_priority_locked(priority):
                return False
            self._sequence += 1
            heapq.heappush(self._heap, _QueuedItem(priority=priority, sequence=self._sequence, item=item))
            self._not_empty.notify()
            return True

    def get_nowait(self) -> T | None:
        with self._lock:
            if not self._heap:
                return None
            return heapq.heappop(self._heap).item

    def get(self, timeout: float | None = None) -> T | None:
        with self._not_empty:
            if not self._heap:
                self._not_empty.wait(timeout=timeout)
            if not self._heap:
                return None
            return heapq.heappop(self._heap).item

    def snapshot(self) -> list[T]:
        with self._lock:
            return [queued.item for queued in sorted(self._heap)]

    def clear(self) -> None:
        with self._lock:
            self._heap.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._heap)

    def _drop_lowest_priority_locked(self, new_priority: int) -> bool:
        worst_index = max(range(len(self._heap)), key=lambda index: self._heap[index].priority)
        if self._heap[worst_index].priority <= new_priority:
            return False
        self._heap[worst_index] = self._heap[-1]
        self._heap.pop()
        if worst_index < len(self._heap):
            heapq.heapify(self._heap)
        return True


@dataclass(slots=True)
class RuntimeHealth:
    healthy: bool = True
    last_error: str | None = None
    last_update: float = 0.0


class StateBus:
    def __init__(
        self,
        observation_history_capacity: int = 300,
        progress_history_capacity: int = 300,
        event_queue_capacity: int = 1024,
        mode_queue_capacity: int = 128,
    ) -> None:
        self.latest_observation: LatestSlot[Observation] = LatestSlot()
        self.observation_ring: RingBuffer[Observation] = RingBuffer(observation_history_capacity)
        self.progress_ring: RingBuffer[ProgressState] = RingBuffer(progress_history_capacity)
        self.event_queue: PriorityEventQueue[Interrupt] = PriorityEventQueue(event_queue_capacity)
        self.mode_request_queue: PriorityEventQueue[ModeRequest] = PriorityEventQueue(mode_queue_capacity)
        self.runtime_health: LatestSlot[RuntimeHealth] = LatestSlot()
        self.current_goal: LatestSlot[str] = LatestSlot()
        self.current_mode: LatestSlot[str] = LatestSlot()
        # Phase 1 slots (AUTONOMY_RUNTIME_CONTRACT.md §3)
        self.screen_claim: LatestSlot[ScreenStateClaim] = LatestSlot()  # type: ignore[assignment]
        self.affordances: LatestSlot[list[Any]] = LatestSlot()  # type: ignore[assignment]
        self.frame_quality: LatestSlot[FrameQuality] = LatestSlot()  # type: ignore[assignment]
        self.navigation_signal: LatestSlot[Any] = LatestSlot()  # type: ignore[assignment]
        self.combat_signal: LatestSlot[Any] = LatestSlot()  # type: ignore[assignment]
        self.shutdown_flag = threading.Event()
        self.event_signal = threading.Event()
        self.mode_signal = threading.Event()
        self._heartbeat_lock = threading.RLock()
        self._heartbeat_table: dict[str, float] = {}
        self._dynamic_slots_lock = threading.RLock()
        self._dynamic_slots: dict[str, LatestSlot[object]] = {}
        self._listeners: dict[str, list[Callable[[Any], None]]] = defaultdict(list)
        self._listeners_lock = threading.RLock()
        self._sub_ids: dict[str, tuple[str, Callable[[Any], None]]] = {}
        self._sub_counter = 0

    def publish_observation(self, observation: Observation) -> int:
        version = self.latest_observation.put(observation)
        self.observation_ring.append(observation)
        return version

    def latest_observation_snapshot(self) -> SlotSnapshot[Observation]:
        return self.latest_observation.snapshot()

    def publish_progress(self, progress: ProgressState) -> None:
        self.progress_ring.append(progress)

    def publish_interrupt(self, interrupt: Interrupt) -> bool:
        accepted = self.event_queue.put(interrupt, priority=interrupt.priority)
        if accepted:
            self.event_signal.set()
            self.publish("interrupt", interrupt)
        return accepted

    def next_interrupt(self, timeout: float | None = None) -> Interrupt | None:
        interrupt = self.event_queue.get(timeout=timeout)
        if len(self.event_queue) == 0:
            self.event_signal.clear()
        return interrupt

    def submit_mode_request(self, request: ModeRequest) -> bool:
        accepted = self.mode_request_queue.put(request, priority=request.priority)
        if accepted:
            self.mode_signal.set()
        return accepted

    def next_mode_request(self, timeout: float | None = None) -> ModeRequest | None:
        request = self.mode_request_queue.get(timeout=timeout)
        if len(self.mode_request_queue) == 0:
            self.mode_signal.clear()
        return request

    def update_heartbeat(self, owner: str, timestamp: float) -> None:
        with self._heartbeat_lock:
            self._heartbeat_table[owner] = timestamp

    def heartbeat_snapshot(self) -> dict[str, float]:
        with self._heartbeat_lock:
            return dict(self._heartbeat_table)

    def request_shutdown(self) -> None:
        self.shutdown_flag.set()
        self.event_signal.set()
        self.mode_signal.set()

    def register_slot(self, name: str) -> LatestSlot[object]:
        with self._dynamic_slots_lock:
            if name in self._dynamic_slots:
                return self._dynamic_slots[name]
            slot: LatestSlot[object] = LatestSlot()
            self._dynamic_slots[name] = slot
            return slot

    def get_slot(self, name: str) -> LatestSlot[object] | None:
        with self._dynamic_slots_lock:
            return self._dynamic_slots.get(name)

    def unregister_slot(self, name: str) -> bool:
        with self._dynamic_slots_lock:
            return self._dynamic_slots.pop(name, None) is not None

    def registered_slot_names(self) -> list[str]:
        with self._dynamic_slots_lock:
            return list(self._dynamic_slots.keys())

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> str:
        """Subscribe to an event type. Returns a subscription_id for unsubscribe."""
        with self._listeners_lock:
            sub_id = f"{event_type}_{id(callback)}_{threading.get_ident()}_{self._sub_counter}"
            self._sub_counter += 1
            self._listeners[event_type].append(callback)
            self._sub_ids[sub_id] = (event_type, callback)
        return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription by its ID. Returns True if found and removed."""
        with self._listeners_lock:
            entry = self._sub_ids.pop(subscription_id, None)
            if entry is None:
                return False
            event_type, callback = entry
            listeners = self._listeners.get(event_type, [])
            try:
                listeners.remove(callback)
            except ValueError:
                pass
            return True

    def subscription_ids(self) -> list[str]:
        """Return a snapshot of active subscription IDs."""
        with self._listeners_lock:
            return list(self._sub_ids.keys())

    def publish(self, event_type: str, data: Any) -> None:
        with self._listeners_lock:
            listeners = list(self._listeners.get(event_type, []))
        for callback in listeners:
            try:
                callback(data)
            except Exception as e:
                import logging
                logging.getLogger("StateBus").error(
                    f"Error executing listener for {event_type}: {str(e)}"
                )
