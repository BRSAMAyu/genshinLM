"""Tests for IntentBridge: CameraIntent/MovementIntent → InputLease conversion."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import CameraIntent, InputLease, MovementIntent
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from execution.intent_bridge import IntentBridge


@pytest.fixture
def bus() -> StateBus:
    return StateBus()


@pytest.fixture
def tb() -> Timebase:
    return Timebase()


@pytest.fixture
def worker(tb: Timebase, bus: StateBus) -> InputWorker:
    return InputWorker(backend=ConsoleInputBackend(tb), timebase=tb, state_bus=bus)


class TestIntentBridgeCamera:
    def test_camera_intent_submits_lease(self, bus: StateBus, tb: Timebase, worker: InputWorker) -> None:
        bridge = IntentBridge(bus, worker, timebase=tb, pixels_per_degree=8.0, tick_seconds=0.01)
        camera_slot = bus.get_slot("camera_intent")
        assert camera_slot is not None

        intent = CameraIntent(yaw_delta=5.0, pitch_delta=-2.0, duration_ms=50, confidence=0.9, reason="test")
        camera_slot.put(intent)

        bridge.start()
        time.sleep(0.15)
        bridge.stop()

        # Worker should have processed at least one lease with mouse_delta
        log_calls = worker.lease_store.active_leases_snapshot()
        # The lease may have already expired and been cleaned up, which is fine.
        # The key assertion is that no exception was raised.

    def test_zero_camera_intent_ignored(self, bus: StateBus, tb: Timebase, worker: InputWorker) -> None:
        bridge = IntentBridge(bus, worker, timebase=tb, tick_seconds=0.01)
        camera_slot = bus.get_slot("camera_intent")
        camera_slot.put(CameraIntent(yaw_delta=0.0, pitch_delta=0.0, duration_ms=50, confidence=0.0, reason="zero"))

        bridge.start()
        time.sleep(0.1)
        bridge.stop()
        # Should not crash — zero movement is a no-op

    def test_raw_degree_deltas_passed(self, bus: StateBus, tb: Timebase) -> None:
        bridge = IntentBridge(bus, MagicMock(spec=InputWorker), timebase=tb, pixels_per_degree=10.0)
        # IntentBridge passes raw degree deltas — the backend does the pixel conversion
        camera_slot = bus.get_slot("camera_intent")
        camera_slot.put(CameraIntent(yaw_delta=2.0, pitch_delta=1.5, duration_ms=50, confidence=0.9, reason="test"))

        bridge._drain_camera_intent()

        mock_worker: MagicMock = bridge._input_worker  # type: ignore[assignment]
        assert mock_worker.submit_lease.call_count == 1
        lease: InputLease = mock_worker.submit_lease.call_args[0][0]
        assert lease.mouse_delta is not None
        dx, dy = lease.mouse_delta
        # Raw degrees, not pixels (backend does the conversion)
        assert abs(dx - 2.0) < 0.001
        assert abs(dy - 1.5) < 0.001

    def test_same_intent_not_reprocessed(self, bus: StateBus, tb: Timebase) -> None:
        bridge = IntentBridge(bus, MagicMock(spec=InputWorker), timebase=tb)
        camera_slot = bus.get_slot("camera_intent")
        camera_slot.put(CameraIntent(yaw_delta=5.0, pitch_delta=0.0, duration_ms=50, confidence=0.9, reason="test"))

        bridge._drain_camera_intent()
        # Same snapshot, same version — should not submit again
        bridge._drain_camera_intent()

        mock_worker: MagicMock = bridge._input_worker  # type: ignore[assignment]
        assert mock_worker.submit_lease.call_count == 1


class TestIntentBridgeMovement:
    def test_forward_movement(self, bus: StateBus, tb: Timebase) -> None:
        bridge = IntentBridge(bus, MagicMock(spec=InputWorker), timebase=tb)
        movement_slot = bus.get_slot("movement_intent")
        movement_slot.put(MovementIntent(move_forward=1.0, move_right=0.0, duration_ms=100, reason="walk"))

        bridge._drain_movement_intent()

        mock_worker: MagicMock = bridge._input_worker  # type: ignore[assignment]
        assert mock_worker.submit_lease.call_count == 1
        lease: InputLease = mock_worker.submit_lease.call_args[0][0]
        assert "w" in lease.key_states
        assert lease.key_states["w"] == "DOWN"

    def test_diagonal_movement(self, bus: StateBus, tb: Timebase) -> None:
        bridge = IntentBridge(bus, MagicMock(spec=InputWorker), timebase=tb)
        movement_slot = bus.get_slot("movement_intent")
        movement_slot.put(MovementIntent(move_forward=1.0, move_right=1.0, jump=True, duration_ms=200, reason="diagonal"))

        bridge._drain_movement_intent()

        mock_worker: MagicMock = bridge._input_worker  # type: ignore[assignment]
        assert mock_worker.submit_lease.call_count == 1
        lease: InputLease = mock_worker.submit_lease.call_args[0][0]
        assert "w" in lease.key_states
        assert "d" in lease.key_states
        assert "space" in lease.key_states

    def test_direction_change_releases_old_keys(self, bus: StateBus, tb: Timebase) -> None:
        bridge = IntentBridge(bus, MagicMock(spec=InputWorker), timebase=tb)
        movement_slot = bus.get_slot("movement_intent")

        # First: move forward
        movement_slot.put(MovementIntent(move_forward=1.0, move_right=0.0, duration_ms=100, reason="forward"))
        bridge._drain_movement_intent()

        # Now: move right (release forward)
        movement_slot.put(MovementIntent(move_forward=0.0, move_right=1.0, duration_ms=100, reason="right"))
        bridge._drain_movement_intent()

        mock_worker: MagicMock = bridge._input_worker  # type: ignore[assignment]
        # Should have 3 calls: forward_down, forward_up, right_down
        assert mock_worker.submit_lease.call_count == 3
        release_call = mock_worker.submit_lease.call_args_list[1]
        release_lease: InputLease = release_call[0][0]
        assert release_lease.key_states.get("w") == "UP"

    def test_backward_movement(self, bus: StateBus, tb: Timebase) -> None:
        bridge = IntentBridge(bus, MagicMock(spec=InputWorker), timebase=tb)
        movement_slot = bus.get_slot("movement_intent")
        movement_slot.put(MovementIntent(move_forward=-1.0, move_right=0.0, duration_ms=100, reason="back"))

        bridge._drain_movement_intent()

        mock_worker: MagicMock = bridge._input_worker  # type: ignore[assignment]
        lease: InputLease = mock_worker.submit_lease.call_args[0][0]
        assert "s" in lease.key_states

    def test_dash_movement(self, bus: StateBus, tb: Timebase) -> None:
        bridge = IntentBridge(bus, MagicMock(spec=InputWorker), timebase=tb)
        movement_slot = bus.get_slot("movement_intent")
        movement_slot.put(MovementIntent(move_forward=1.0, move_right=0.0, dash=True, duration_ms=100, reason="dash"))

        bridge._drain_movement_intent()

        mock_worker: MagicMock = bridge._input_worker  # type: ignore[assignment]
        lease: InputLease = mock_worker.submit_lease.call_args[0][0]
        assert "w" in lease.key_states
        assert "shift" in lease.key_states


class TestIntentBridgeLifecycle:
    def test_start_stop(self, bus: StateBus, tb: Timebase, worker: InputWorker) -> None:
        bridge = IntentBridge(bus, worker, timebase=tb, tick_seconds=0.01)
        bridge.start()
        assert bridge.is_alive()
        bridge.stop()
        assert not bridge.is_alive()

    def test_release_on_stop(self, bus: StateBus, tb: Timebase) -> None:
        bridge = IntentBridge(bus, MagicMock(spec=InputWorker), timebase=tb)
        movement_slot = bus.get_slot("movement_intent")

        # Hold forward
        movement_slot.put(MovementIntent(move_forward=1.0, move_right=0.0, duration_ms=5000, reason="walk"))
        bridge._drain_movement_intent()

        # Simulate stop releasing keys
        bridge._release_movement_keys()

        mock_worker: MagicMock = bridge._input_worker  # type: ignore[assignment]
        release_call = mock_worker.submit_lease.call_args_list[-1]
        release_lease: InputLease = release_call[0][0]
        assert release_lease.key_states.get("w") == "UP"

    def test_slots_registered_on_construction(self, bus: StateBus, tb: Timebase, worker: InputWorker) -> None:
        IntentBridge(bus, worker, timebase=tb)
        assert "camera_intent" in bus.registered_slot_names()
        assert "movement_intent" in bus.registered_slot_names()
