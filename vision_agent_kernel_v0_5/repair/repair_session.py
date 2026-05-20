"""Repair session: records user demonstration events for skill patch creation."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass(slots=True)
class RepairEvent:
    """A single event recorded during a repair session."""

    event_id: str
    session_id: str
    event_type: str  # "demonstration_start", "action_recorded", "checkpoint_proposed", "repair_complete"
    payload: dict[str, object]
    created_at: float


class RepairSession:
    """Manages a repair session that records user demonstration events."""

    def __init__(self, failure_signature_id: str, skill_id: str) -> None:
        self.session_id = str(uuid.uuid4())
        self.failure_signature_id = failure_signature_id
        self.skill_id = skill_id
        self._events: list[RepairEvent] = []
        self._demonstration_events: list[RepairEvent] = []
        self._current_demo_id: str | None = None

    def start_demonstration(self) -> str:
        """Start a new demonstration segment. Returns the demo event id."""
        event_id = str(uuid.uuid4())
        self._current_demo_id = event_id
        event = RepairEvent(
            event_id=event_id,
            session_id=self.session_id,
            event_type="demonstration_start",
            payload={"failure_signature_id": self.failure_signature_id, "skill_id": self.skill_id},
            created_at=time.perf_counter(),
        )
        self._events.append(event)
        self._demonstration_events.append(event)
        return event_id

    def record_action(self, action_type: str, params: dict[str, object]) -> str:
        """Record an action performed during demonstration. Returns the event id."""
        event_id = str(uuid.uuid4())
        event = RepairEvent(
            event_id=event_id,
            session_id=self.session_id,
            event_type="action_recorded",
            payload={"action_type": action_type, "params": params, "demo_id": self._current_demo_id},
            created_at=time.perf_counter(),
        )
        self._events.append(event)
        return event_id

    def propose_checkpoint(self, verifier_contract: dict[str, object]) -> str:
        """Propose a checkpoint with a verifier contract. Returns the event id."""
        event_id = str(uuid.uuid4())
        event = RepairEvent(
            event_id=event_id,
            session_id=self.session_id,
            event_type="checkpoint_proposed",
            payload={"verifier_contract": verifier_contract, "demo_id": self._current_demo_id},
            created_at=time.perf_counter(),
        )
        self._events.append(event)
        return event_id

    def complete_repair(self) -> RepairEvent:
        """Mark the repair session as complete. Returns the completion event."""
        event = RepairEvent(
            event_id=str(uuid.uuid4()),
            session_id=self.session_id,
            event_type="repair_complete",
            payload={
                "failure_signature_id": self.failure_signature_id,
                "skill_id": self.skill_id,
                "total_events": len(self._events),
                "demonstration_count": len(self._demonstration_events),
            },
            created_at=time.perf_counter(),
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> list[RepairEvent]:
        """Return a copy of all recorded events."""
        return list(self._events)

    @property
    def demonstration_ids(self) -> list[str]:
        """Return IDs of all demonstration_start events."""
        return [e.event_id for e in self._demonstration_events]
