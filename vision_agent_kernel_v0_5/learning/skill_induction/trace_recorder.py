"""TraceRecorder — records exploration events for skill induction.

Captures semantic action events with anchors, screen state, and timing.
Produces TraceSession objects suitable for episode segmentation.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RecordedAction:
    """A single recorded semantic action."""
    action_id: str
    action_type: str  # click_anchor, click_text, press_key, etc.
    target: str  # anchor_id or text target
    screen_state: str
    timestamp: float
    payload: dict[str, Any] = field(default_factory=dict)
    anchor_id: str = ""
    x: float = 0.0
    y: float = 0.0


@dataclass(slots=True)
class TraceSession:
    """A recording session containing a sequence of actions."""
    session_id: str
    goal: str
    started_at: float
    actions: list[RecordedAction] = field(default_factory=list)
    ended_at: float = 0.0
    success: bool = False
    screen_state: str = ""
    viewport: tuple[int, int] = (1920, 1080)

    @property
    def duration(self) -> float:
        end = self.ended_at or time.perf_counter()
        return end - self.started_at

    @property
    def has_semantic_anchors(self) -> bool:
        return any(a.anchor_id for a in self.actions)

    @property
    def action_types(self) -> set[str]:
        return {a.action_type for a in self.actions}


class TraceRecorder:
    """Records exploration actions into trace sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, TraceSession] = {}

    def start_session(self, goal: str, screen_state: str = "",
                      viewport: tuple[int, int] = (1920, 1080)) -> TraceSession:
        session = TraceSession(
            session_id=f"trace_{uuid.uuid4().hex[:8]}",
            goal=goal,
            started_at=time.perf_counter(),
            screen_state=screen_state,
            viewport=viewport,
        )
        self._sessions[session.session_id] = session
        return session

    def record_action(
        self,
        session: TraceSession,
        action_type: str,
        target: str,
        screen_state: str = "",
        anchor_id: str = "",
        x: float = 0.0,
        y: float = 0.0,
        payload: dict[str, Any] | None = None,
    ) -> RecordedAction:
        action = RecordedAction(
            action_id=f"act_{uuid.uuid4().hex[:6]}",
            action_type=action_type,
            target=target,
            screen_state=screen_state or session.screen_state,
            timestamp=time.perf_counter(),
            payload=payload or {},
            anchor_id=anchor_id,
            x=x,
            y=y,
        )
        session.actions.append(action)
        return action

    def end_session(self, session: TraceSession, success: bool = True) -> TraceSession:
        session.success = success
        session.ended_at = time.perf_counter()
        return session

    def get_session(self, session_id: str) -> TraceSession | None:
        return self._sessions.get(session_id)

    def completed_sessions(self) -> list[TraceSession]:
        return [s for s in self._sessions.values() if s.ended_at > 0 and s.success]
