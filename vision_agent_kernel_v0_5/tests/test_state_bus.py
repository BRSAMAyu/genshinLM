from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from core.state_bus import StateBus
from core.types import FocusState, Observation


def _observation(frame_id: int) -> Observation:
    return Observation(
        frame_id=frame_id,
        t_capture=float(frame_id),
        t_processed=float(frame_id),
        latency_ms=1.0,
        viewport_size=(1280, 720),
        target_track=None,
        obstacle_field=None,
        ui_state=None,
        visual_triggers={},
        os_focus=FocusState(focused=True),
    )


def test_state_bus_concurrent_latest_observation() -> None:
    bus = StateBus(observation_history_capacity=20)

    def publish(frame_id: int) -> int:
        return bus.publish_observation(_observation(frame_id))

    with ThreadPoolExecutor(max_workers=8) as executor:
        versions = list(executor.map(publish, range(100)))

    snapshot = bus.latest_observation_snapshot()
    assert snapshot.value is not None
    assert snapshot.version == 100
    assert max(versions) == 100
    assert len(bus.observation_ring) == 20
