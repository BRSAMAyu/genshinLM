from __future__ import annotations

import threading
from dataclasses import dataclass

from core.timebase import Timebase


@dataclass(frozen=True, slots=True)
class ConsoleInputEvent:
    timestamp: float
    action: str
    payload: dict[str, object]


class ConsoleInputBackend:
    """Dry-run backend: print every requested action and never touch OS input."""

    def __init__(self, timebase: Timebase | None = None) -> None:
        self._timebase = timebase or Timebase()
        self._lock = threading.RLock()
        self._events: list[ConsoleInputEvent] = []
        self._down_keys: set[str] = set()
        self._max_events = 10000

    def key_down(self, key: str, reason: str = "") -> None:
        with self._lock:
            self._down_keys.add(key)
            self._record("key_down", {"key": key, "reason": reason})

    def key_up(self, key: str, reason: str = "") -> None:
        with self._lock:
            self._down_keys.discard(key)
            self._record("key_up", {"key": key, "reason": reason})

    def mouse_move(self, dx: float, dy: float, reason: str = "") -> None:
        with self._lock:
            self._record("mouse_move", {"dx": dx, "dy": dy, "reason": reason})

    def action_intent(self, intent: str, reason: str = "") -> None:
        with self._lock:
            self._record("action_intent", {"intent": intent, "reason": reason})

    def release_all(self, reason: str = "") -> None:
        with self._lock:
            released = sorted(self._down_keys)
            self._down_keys.clear()
            self._record("release_all", {"keys": released, "reason": reason})

    def events_snapshot(self) -> list[ConsoleInputEvent]:
        with self._lock:
            return list(self._events)

    def down_keys_snapshot(self) -> set[str]:
        with self._lock:
            return set(self._down_keys)

    def is_target_focused(self) -> bool:
        return True

    def _record(self, action: str, payload: dict[str, object]) -> None:
        event = ConsoleInputEvent(
            timestamp=self._timebase.now(),
            action=action,
            payload=payload,
        )
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
        print(f"[ConsoleInputBackend] {event.timestamp:.6f} {action} {payload}", flush=True)
