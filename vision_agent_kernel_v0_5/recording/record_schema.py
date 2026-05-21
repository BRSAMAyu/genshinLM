from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RecordSessionMeta:
    """Session metadata preserved in session.json."""
    session_id: str
    capsule_id: str
    start_timestamp: float
    end_timestamp: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecordEvent:
    """Event frame payload appended to events.jsonl."""
    timestamp: float
    event_type: str  # "state_bus", "skill", "input", "verifier", "interrupt", "marker", "frame"
    frame_id: Optional[int] = None
    frame_hash: Optional[str] = None
    screen_state: Optional[str] = None
    active_skill: Optional[str] = None
    physical_input_event: Optional[Dict[str, Any]] = None
    state_bus_snapshot: Optional[Dict[str, Any]] = None
    verifier_results: Optional[List[Dict[str, Any]]] = None
    interrupts: Optional[List[Dict[str, Any]]] = None
    user_marker: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
