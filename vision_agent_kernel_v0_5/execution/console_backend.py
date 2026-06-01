"""Dry-run ConsoleInputBackend that prints and records all actions."""
from __future__ import annotations

import collections
import logging
import threading
from dataclasses import dataclass
from typing import Literal

from core.timebase import Timebase

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ConsoleInputEvent:
    timestamp: float
    action: str
    payload: dict[str, object]


class ConsoleInputBackend:
    """Dry-run backend: records every requested action and prints to terminal."""

    def __init__(self, timebase: Timebase | None = None) -> None:
        self._timebase = timebase or Timebase()
        self._lock = threading.RLock()
        self._max_events = 10000
        self._events: collections.deque[ConsoleInputEvent] = collections.deque(maxlen=self._max_events)
        self._down_keys: set[str] = set()

    def key_down(self, key: str, reason: str = "") -> bool:
        with self._lock:
            self._down_keys.add(key)
            self._record("key_down", {"key": key, "reason": reason})
        return True

    def key_up(self, key: str, reason: str = "") -> bool:
        with self._lock:
            self._down_keys.discard(key)
            self._record("key_up", {"key": key, "reason": reason})
        return True

    def release_all(self, reason: str = "") -> int:
        with self._lock:
            released = sorted(self._down_keys)
            self._down_keys.clear()
            self._record("release_all", {"keys": released, "reason": reason})
        return len(released)

    def is_target_focused(self) -> bool:
        return True

    # --- Mouse Actions ---

    def mouse_move(self, dx: float, dy: float, reason: str = "") -> bool:
        with self._lock:
            self._record("mouse_move", {"dx": dx, "dy": dy, "reason": reason})
        return True

    def mouse_move_to(self, x: int, y: int, reason: str = "") -> bool:
        with self._lock:
            self._record("mouse_move_to", {"x": x, "y": y, "reason": reason})
        return True

    def left_click(self, reason: str = "") -> bool:
        with self._lock:
            self._record("left_click", {"reason": reason})
        return True

    def right_click(self, reason: str = "") -> bool:
        with self._lock:
            self._record("right_click", {"reason": reason})
        return True

    def mouse_scroll(self, delta: int = -1, reason: str = "") -> bool:
        with self._lock:
            self._record("mouse_scroll", {"delta": delta, "reason": reason})
        return True

    def hold_click(self, duration_sec: float = 0.5, reason: str = "") -> bool:
        with self._lock:
            self._record("hold_click", {"duration_sec": duration_sec, "reason": reason})
        return True

    # --- Next-Gen Computer Use Advanced Actions ---

    def mouse_drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 300,
        button: Literal["left", "right"] = "left",
        reason: str = "",
    ) -> bool:
        with self._lock:
            self._record(
                "mouse_drag",
                {
                    "start_x": start_x,
                    "start_y": start_y,
                    "end_x": end_x,
                    "end_y": end_y,
                    "duration_ms": duration_ms,
                    "button": button,
                    "reason": reason,
                },
            )
        return True

    def mouse_relative_drag(
        self,
        dx: int,
        dy: int,
        duration_ms: int = 150,
        button: Literal["left", "right", "middle"] = "right",
        reason: str = "",
    ) -> bool:
        with self._lock:
            self._record(
                "mouse_relative_drag",
                {"dx": dx, "dy": dy, "duration_ms": duration_ms, "button": button, "reason": reason},
            )
        return True

    def mouse_double_click(
        self,
        x: int,
        y: int,
        button: Literal["left", "right"] = "left",
        reason: str = "",
    ) -> bool:
        with self._lock:
            self._record("mouse_double_click", {"x": x, "y": y, "button": button, "reason": reason})
        return True

    # --- Advanced Keyboard Additions ---

    def type_text(self, text: str, delay_between_keys_ms: int = 50, reason: str = "") -> bool:
        with self._lock:
            self._record("type_text", {"text": text, "delay_between_keys_ms": delay_between_keys_ms, "reason": reason})
        return True

    def execute_combo(self, keys: list[str], hold_time_ms: int = 100, reason: str = "") -> bool:
        with self._lock:
            self._record("execute_combo", {"keys": keys, "hold_time_ms": hold_time_ms, "reason": reason})
        return True

    # --- Core Helpers ---

    def action_intent(self, intent: str, reason: str = "") -> None:
        with self._lock:
            self._record("action_intent", {"intent": intent, "reason": reason})

    def events_snapshot(self) -> list[ConsoleInputEvent]:
        with self._lock:
            return list(self._events)

    def down_keys_snapshot(self) -> set[str]:
        with self._lock:
            return set(self._down_keys)

    def _record(self, action: str, payload: dict[str, object]) -> None:
        event = ConsoleInputEvent(
            timestamp=self._timebase.now(),
            action=action,
            payload=payload,
        )
        self._events.append(event)
        print(f"[ConsoleInputBackend] {event.timestamp:.6f} {action} {payload}", flush=True)
