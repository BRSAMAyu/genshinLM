from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from core.state_bus import StateBus


ClaimEventType = Literal[
    "claim_event",
    "claim_adjudicated",
    "claim_cascade",
    "audit_scheduled",
    "audit_completed",
    "reliability_updated",
    "claim_adjudication_error",
]


@dataclass(frozen=True, slots=True)
class ClaimEvent:
    event_type: ClaimEventType
    mission_id: str
    graph_id: str
    claim_id: str = ""
    status: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class ClaimGraphState:
    mission_id: str
    graph_id: str
    active_claim_count: int
    latest_claim_id: str = ""
    latest_status: str = ""
    blocked_nodes: list[str] = field(default_factory=list)
    suspect_clusters: list[str] = field(default_factory=list)
    unresolved_uncertain_count: int = 0
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_snapshot(
        cls,
        *,
        mission_id: str,
        graph_id: str,
        snapshot: dict[str, Any],
        blocked_nodes: list[str] | None = None,
    ) -> "ClaimGraphState":
        claims = dict(snapshot.get("claims") or {})
        latest_claim_id = str(snapshot.get("latest_claim_id") or "")
        latest_status = str(claims.get(latest_claim_id, "")) if latest_claim_id else ""
        suspect_clusters = [claim_id for claim_id, status in claims.items() if status in {"suspect", "demoted", "disputed"}]
        unresolved = sum(1 for status in claims.values() if status in {"uncertain", "tentative", "disputed"})
        return cls(
            mission_id=mission_id,
            graph_id=graph_id,
            active_claim_count=int(snapshot.get("claim_count", len(claims))),
            latest_claim_id=latest_claim_id,
            latest_status=latest_status,
            blocked_nodes=blocked_nodes or [],
            suspect_clusters=suspect_clusters,
            unresolved_uncertain_count=unresolved,
        )


class ClaimEventPublisher:
    """Publish claim events through the existing StateBus boundary."""

    state_slot_name = "claim_graph_state"

    def __init__(self, state_bus: StateBus) -> None:
        self._state_bus = state_bus
        self._state_bus.register_slot(self.state_slot_name)

    def publish_event(self, event: ClaimEvent) -> None:
        self._state_bus.publish("claim_event", event)
        if event.event_type != "claim_event":
            self._state_bus.publish(event.event_type, event)

    def publish_state(self, state: ClaimGraphState) -> int:
        slot = self._state_bus.register_slot(self.state_slot_name)
        version = slot.put(state)
        self._state_bus.publish("claim_graph_state", state)
        return version
