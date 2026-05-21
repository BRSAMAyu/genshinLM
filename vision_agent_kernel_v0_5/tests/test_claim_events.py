from __future__ import annotations

from core.state_bus import StateBus
from runtime.claim_events import ClaimEvent, ClaimEventPublisher, ClaimGraphState
from runtime.claim_runtime import ClaimGraph, StateDeltaClaim
from runtime.claim_worker import ClaimGraphCommand, ClaimGraphWorker


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


def test_worker_without_publisher_submits_successfully_without_events() -> None:
    """Worker with no publisher should process commands but emit zero events."""
    bus = StateBus()
    received: list[ClaimEvent] = []
    bus.subscribe("claim_event", received.append)

    worker = ClaimGraphWorker(mission_id="m1", graph_id="g1")
    worker.start()
    try:
        result = worker.submit(ClaimGraphCommand(
            "add_claim",
            claim=StateDeltaClaim(
                claim_id="c2",
                mission_id="m1",
                node_id="n1",
                skill_id="s1",
                claim_type="inventory_delta",
                claimed_delta={"item": "qingxin", "delta": 1},
                status="asserted",
            ),
        ))
        assert result.ok
        assert result.snapshot["claim_count"] == 1
        assert received == []
    finally:
        worker.stop()


def test_from_snapshot_handles_empty_and_malformed_snapshots() -> None:
    state = ClaimGraphState.from_snapshot(
        mission_id="m1",
        graph_id="g1",
        snapshot={},
    )
    assert state.active_claim_count == 0
    assert state.latest_claim_id == ""
    assert state.suspect_clusters == []
    assert state.unresolved_uncertain_count == 0

    state2 = ClaimGraphState.from_snapshot(
        mission_id="m1",
        graph_id="g1",
        snapshot={"claims": {"c1": "verified", "c2": "suspect", "c3": "uncertain"}},
        blocked_nodes=["n1"],
    )
    assert state2.active_claim_count == 3
    assert state2.suspect_clusters == ["c2"]
    assert state2.unresolved_uncertain_count == 1
    assert state2.blocked_nodes == ["n1"]


def test_multiple_subscribers_each_receive_events() -> None:
    bus = StateBus()
    sub_a: list[ClaimEvent] = []
    sub_b: list[ClaimEvent] = []
    bus.subscribe("claim_event", sub_a.append)
    bus.subscribe("claim_event", sub_b.append)

    publisher = ClaimEventPublisher(bus)
    event = ClaimEvent("claim_adjudicated", mission_id="m1", graph_id="g1", claim_id="c1", status="verified")
    publisher.publish_event(event)

    assert len(sub_a) == 1
    assert len(sub_b) == 1
    assert sub_a[0] == event
    assert sub_b[0] == event


def test_publish_event_dual_delivery_for_specific_types() -> None:
    """Non-generic event types should be published under both 'claim_event' and their specific type."""
    bus = StateBus()
    generic: list[ClaimEvent] = []
    specific: list[ClaimEvent] = []
    bus.subscribe("claim_event", generic.append)
    bus.subscribe("claim_cascade", specific.append)

    publisher = ClaimEventPublisher(bus)
    cascade_event = ClaimEvent("claim_cascade", mission_id="m1", graph_id="g1", claim_id="c1", status="demoted")
    publisher.publish_event(cascade_event)

    assert len(generic) == 1
    assert len(specific) == 1
    assert generic[0] is cascade_event
    assert specific[0] is cascade_event
