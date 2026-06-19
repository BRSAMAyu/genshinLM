from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.events import Interrupt
from persona.dialogue_generator import DialogueGenerator


@dataclass(frozen=True, slots=True)
class CompanionUtterance:
    """A single companion line surfaced from a live kernel event."""

    event_code: str
    message: str
    emotion: str
    overlay_state: str
    source: str
    persona_id: str
    timestamp: float
    sequence: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_code": self.event_code,
            "message": self.message,
            "emotion": self.emotion,
            "overlay_state": self.overlay_state,
            "source": self.source,
            "persona_id": self.persona_id,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
        }


@dataclass(slots=True)
class _FeedState:
    sequence: int = 0
    latest: CompanionUtterance | None = None
    history: deque[CompanionUtterance] = field(default_factory=deque)


class CompanionFeed:
    """Bridge that turns live kernel events into companion speech.

    The feed runs known event codes through :class:`DialogueGenerator` and keeps
    a *bounded* buffer of recent utterances plus the latest one, so it can be
    surfaced in the websocket ``AgentState`` payload without unbounded growth.

    Thread-safety: every public method is guarded by a single lock. Callbacks
    invoked from the StateBus listener thread (``ingest_interrupt``) and from API
    handler threads (``ingest_event``) share the same lock, so the latest slot
    and the ring never observe a torn write.
    """

    # Event codes the companion speaks for. Unknown codes are ignored so the
    # feed never spams the UI with raw, untranslated internals.
    _KNOWN_CODES: frozenset[str] = frozenset(
        {
            "TARGET_LOST",
            "NO_TASK_PROGRESS",
            "RECOVERY_STARTED",
            "SKILL_TIMEOUT",
            "TASK_COMPLETE",
            "FOCUS_LOST",
            "EMERGENCY_STOP",
            "DODGE_REFLEX",
            "HUMAN_OVERRIDE",
        }
    )

    def __init__(
        self,
        dialogue_generator: DialogueGenerator,
        *,
        persona_id: str = "default_companion",
        max_history: int = 32,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_history <= 0:
            raise ValueError("max_history must be positive")
        self._dialogue = dialogue_generator
        self._persona_id = persona_id
        self._max_history = max_history
        # Monotonic clock for logic; injectable for tests.
        self._clock: Callable[[], float] = clock or time.perf_counter
        self._lock = threading.RLock()
        self._state = _FeedState(history=deque(maxlen=max_history))

    def ingest_interrupt(self, interrupt: Interrupt) -> CompanionUtterance | None:
        """StateBus ``"interrupt"`` listener entry point.

        Registered directly as a StateBus ``"interrupt"`` subscriber. Returns the
        utterance when one was produced, ``None`` for unknown/empty codes.
        """
        code = getattr(interrupt, "code", None)
        if not code:
            return None
        source = getattr(interrupt, "source", "kernel") or "kernel"
        payload = getattr(interrupt, "payload", None)
        return self.ingest_event(str(code), source=str(source), payload=payload)

    def ingest_event(
        self,
        event_code: str,
        *,
        source: str = "kernel",
        payload: dict[str, Any] | None = None,
        persona_id: str | None = None,
    ) -> CompanionUtterance | None:
        """Translate an event code into a companion utterance and buffer it."""
        if not event_code or event_code not in self._KNOWN_CODES:
            return None
        persona = persona_id or self._persona_id
        line = self._dialogue.generate(event_code, payload=payload, persona_id=persona)
        with self._lock:
            self._state.sequence += 1
            utterance = CompanionUtterance(
                event_code=event_code,
                message=line.message,
                emotion=line.emotion,
                overlay_state=line.overlay_state,
                source=source,
                persona_id=persona,
                timestamp=self._clock(),
                sequence=self._state.sequence,
            )
            self._state.latest = utterance
            self._state.history.append(utterance)
            return utterance

    def latest(self) -> CompanionUtterance | None:
        with self._lock:
            return self._state.latest

    def latest_dict(self) -> dict[str, Any] | None:
        with self._lock:
            latest = self._state.latest
        return latest.to_dict() if latest is not None else None

    def history(self) -> list[CompanionUtterance]:
        with self._lock:
            return list(self._state.history)

    def clear(self) -> None:
        with self._lock:
            self._state.latest = None
            self._state.history.clear()
