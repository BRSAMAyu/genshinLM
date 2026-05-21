from __future__ import annotations

from core.state_bus import StateBus
from runtime.claim_events import ClaimEvent, ClaimEventPublisher, ClaimGraphState
from runtime.claim_runtime import ClaimGraph, StateDeltaClaim


def test_claim_events_publish_through_state_bus_and_state_slot() -> None:
    bus = StateBus()
    received: list[ClaimEvent] = []
    states: list[ClaimGraphState] = []
    bus.subscribe("claim_event", received.append)
    bus.subscribe("claim_graph_state", states.append)
    publisher = ClaimEventPublisher(bus)

    graph = ClaimGraph()
    graph.add_claim(
        StateDeltaClaim(
            claim_id="c1",
            mission_id="m1",
            node_id="n1",
            skill_id="s1",
            claim_type="screen_state_transition",
            claimed_delta={"screen_state": "menu"},
            status="verified",
        )
    )

    event = ClaimEvent("claim_adjudicated", mission_id="m1", graph_id="g1", claim_id="c1", status="verified")
    publisher.publish_event(event)
    version = publisher.publish_state(ClaimGraphState.from_snapshot(mission_id="m1", graph_id="g1", snapshot=graph.snapshot()))

    assert received == [event]
    assert version == 1
    assert states[0].latest_claim_id == "c1"
    slot = bus.get_slot("claim_graph_state")
    assert slot is not None
    assert slot.snapshot().value == states[0]
