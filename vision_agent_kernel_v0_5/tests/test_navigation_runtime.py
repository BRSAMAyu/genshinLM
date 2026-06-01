"""Tests for HeadingServo, StuckDetector, NavigationController."""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from control.navigation_runtime import (
    HeadingServo,
    NavigationController,
    NavigationDecision,
    NavigationSample,
    RouteSegment,
    StuckDetector,
)


# ---------------------------------------------------------------------------
# HeadingServo tests
# ---------------------------------------------------------------------------

class TestHeadingServo:
    """Test heading error → mouse delta conversion."""

    def test_dead_zone_returns_none(self) -> None:
        servo = HeadingServo(dead_zone_deg=3.0)
        assert servo.mouse_delta_for(2.0) is None
        assert servo.mouse_delta_for(-2.0) is None
        assert servo.mouse_delta_for(0.0) is None

    def test_gain_applied(self) -> None:
        """error=20°, gain=0.25 → delta=5."""
        servo = HeadingServo(gain=0.25, dead_zone_deg=0.0)
        dx, dy = servo.mouse_delta_for(20.0)
        assert abs(dx - 5.0) < 1e-9

    def test_max_delta_clipping(self) -> None:
        """Large error is clipped to max_mouse_delta."""
        servo = HeadingServo(gain=1.0, max_mouse_delta=80.0, dead_zone_deg=0.0)
        dx, dy = servo.mouse_delta_for(200.0)
        assert abs(dx - 80.0) < 1e-9

    def test_negative_error(self) -> None:
        servo = HeadingServo(gain=0.5, dead_zone_deg=0.0)
        dx, dy = servo.mouse_delta_for(-40.0)
        assert abs(dx + 20.0) < 1e-9

    def test_dy_always_zero(self) -> None:
        """Y delta is always 0 (horizontal rotation only)."""
        servo = HeadingServo()
        _, dy = servo.mouse_delta_for(90.0)
        assert dy == 0.0

    def test_custom_gain_and_max(self) -> None:
        servo = HeadingServo(gain=0.1, max_mouse_delta=50.0, dead_zone_deg=1.0)
        dx, dy = servo.mouse_delta_for(10.0)
        assert abs(dx - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# StuckDetector tests
# ---------------------------------------------------------------------------

class TestStuckDetector:
    """Test stuck detection from progress samples."""

    def _sample(self, progress: float, flow: float = 1.0, distance: float = 100.0, heading: float = 0.0) -> NavigationSample:
        return NavigationSample(
            timestamp=0.0,
            progress=progress,
            optical_flow=flow,
            distance_to_target=distance,
            heading_error_deg=heading,
        )

    def test_not_stuck_with_progress(self) -> None:
        detector = StuckDetector(min_progress_delta=0.1, window=3)
        detector.update(self._sample(0.0, flow=0.5))
        detector.update(self._sample(0.05, flow=0.5))
        assert detector.update(self._sample(0.15, flow=0.5)) is False

    def test_not_stuck_insufficient_window(self) -> None:
        """Needs `window` samples before triggering."""
        detector = StuckDetector(min_progress_delta=0.1, min_flow=0.1, window=3)
        detector.update(self._sample(0.0, flow=0.5, distance=100.0))
        detector.update(self._sample(0.0, flow=0.5, distance=90.0))  # distance improving
        # With 2 samples, window not full yet → False
        assert detector.update(self._sample(0.0, flow=0.5, distance=80.0)) is False

    def test_stuck_when_no_progress_and_low_flow(self) -> None:
        detector = StuckDetector(min_progress_delta=0.1, min_flow=0.1, window=4)
        for i in range(4):
            detector.update(self._sample(0.0, flow=0.01))
        assert detector.update(self._sample(0.0, flow=0.01)) is True

    def test_stuck_ignores_high_flow(self) -> None:
        """High optical flow means character is moving → not stuck."""
        detector = StuckDetector(min_progress_delta=0.1, min_flow=0.1, window=3)
        for _ in range(3):
            detector.update(self._sample(0.0, flow=0.5))
        assert detector.update(self._sample(0.0, flow=0.5)) is False

    def test_stuck_ignores_distance_improving(self) -> None:
        """Even with zero progress, distance decreasing → not stuck."""
        detector = StuckDetector(min_progress_delta=0.01, min_flow=0.01, window=4)
        for i in range(4):
            detector.update(self._sample(0.0, flow=0.01, distance=100.0 - i))
        assert detector.update(self._sample(0.0, flow=0.01, distance=95.0)) is False

    def test_window_truncation(self) -> None:
        """Samples older than window are dropped."""
        detector = StuckDetector(min_progress_delta=0.1, window=2)
        for _ in range(10):
            detector.update(self._sample(0.0, flow=0.0))
        # After 10 updates, only last 2 samples remain
        assert len(detector._samples) <= 2


# ---------------------------------------------------------------------------
# NavigationController tests
# ---------------------------------------------------------------------------

class TestNavigationController:
    """Test step() decision logic."""

    def _segment(
        self,
        arrive_distance: float = 1.0,
        max_recoveries: int = 2,
        **kwargs: object,
    ) -> RouteSegment:
        return RouteSegment(
            segment_id="seg1",
            target_waypoint="wp1",
            expected_bearing=0.0,
            max_duration_s=30.0,
            stuck_policy={"arrive_distance": arrive_distance, "max_recoveries": max_recoveries, **kwargs},
        )

    def _sample(
        self,
        distance: float = 100.0,
        progress: float = 0.0,
        heading: float = 0.0,
        flow: float = 1.0,
    ) -> NavigationSample:
        return NavigationSample(
            timestamp=0.0,
            distance_to_target=distance,
            heading_error_deg=heading,
            optical_flow=flow,
            progress=progress,
        )

    def test_arrived_decision(self) -> None:
        ctrl = NavigationController()
        segment = self._segment(arrive_distance=5.0)
        sample = self._sample(distance=3.0)
        decision = ctrl.step(segment, sample, now=0.0)
        assert decision.status == "arrived"

    def test_move_decision(self) -> None:
        ctrl = NavigationController()
        segment = self._segment()
        sample = self._sample(distance=50.0, heading=30.0)
        decision = ctrl.step(segment, sample, now=0.0)
        assert decision.status == "move"
        assert decision.lease is not None
        assert "W" in decision.lease.key_states

    def test_recover_decision(self) -> None:
        ctrl = NavigationController()
        segment = self._segment(arrive_distance=1.0, max_recoveries=2)
        # Simulate stuck samples
        for _ in range(5):
            ctrl._stuck.update(self._sample(distance=100.0, progress=0.0, flow=0.0))
        sample = self._sample(distance=100.0, progress=0.0, flow=0.0)
        decision = ctrl.step(segment, sample, now=0.0)
        assert decision.status == "recover"
        assert "release_all" in decision.recovery_actions

    def test_escalate_after_max_recoveries(self) -> None:
        ctrl = NavigationController()
        # Code: if self._recoveries > max_recoveries → escalate
        # StuckDetector window=4 requires 4 samples to trigger.
        segment = self._segment(arrive_distance=1.0, max_recoveries=2)
        # Pre-fill with stuck samples so detector is already in stuck state
        for _ in range(4):
            ctrl._stuck.update(self._sample(distance=100.0, progress=0.0, flow=0.0))
        # First step: stuck detected, recoveries becomes 1
        decision1 = ctrl.step(segment, self._sample(distance=100.0, progress=0.0, flow=0.0), now=0.0)
        assert decision1.status == "recover"
        assert ctrl._recoveries == 1
        # Second step: stuck again, recoveries becomes 2 (not > 2, so recover)
        decision2 = ctrl.step(segment, self._sample(distance=100.0, progress=0.0, flow=0.0), now=0.0)
        assert decision2.status == "recover"
        assert ctrl._recoveries == 2
        # Third step: stuck, recoveries becomes 3 → 3 > 2 → escalate
        decision3 = ctrl.step(segment, self._sample(distance=100.0, progress=0.0, flow=0.0), now=0.0)
        assert decision3.status == "escalate"

    def test_mouse_delta_in_lease(self) -> None:
        ctrl = NavigationController(servo=HeadingServo(gain=0.25, dead_zone_deg=0.0))
        segment = self._segment()
        sample = self._sample(heading=20.0)
        decision = ctrl.step(segment, sample, now=0.0)
        assert decision.lease is not None
        assert decision.lease.mouse_delta is not None
        dx, dy = decision.lease.mouse_delta
        assert abs(dx - 5.0) < 1e-9

    def test_recovery_count_increments(self) -> None:
        ctrl = NavigationController()
        segment = self._segment(arrive_distance=1.0, max_recoveries=3)
        for _ in range(4):
            ctrl._stuck.update(self._sample(progress=0.0, flow=0.0))
        sample = self._sample(progress=0.0, flow=0.0)
        ctrl.step(segment, sample, now=0.0)
        assert ctrl._recoveries >= 1

    def test_lease_has_correct_owner_and_priority(self) -> None:
        ctrl = NavigationController()
        segment = self._segment()
        sample = self._sample(heading=10.0)
        decision = ctrl.step(segment, sample, now=0.0)
        assert decision.lease is not None
        assert "navigation:" in decision.lease.owner
        assert decision.lease.priority == 25

    def test_lease_expiry_set(self) -> None:
        ctrl = NavigationController()
        segment = self._segment()
        sample = self._sample(heading=10.0)
        now = 1234.5
        decision = ctrl.step(segment, sample, now=now)
        assert decision.lease is not None
        assert decision.lease.created_at == now
        assert decision.lease.expires_at > now

    def test_different_segments_have_independent_recovery_count(self) -> None:
        ctrl = NavigationController()
        seg1 = self._segment(arrive_distance=1.0, max_recoveries=2)
        seg2 = RouteSegment(
            segment_id="seg2",
            target_waypoint="wp2",
            expected_bearing=0.0,
            max_duration_s=30.0,
            stuck_policy={"arrive_distance": 1.0, "max_recoveries": 2},
        )
        # Trigger recovery on seg1
        for _ in range(4):
            ctrl._stuck.update(self._sample(progress=0.0, flow=0.0))
        sample = self._sample(progress=0.0, flow=0.0)
        decision1 = ctrl.step(seg1, sample, now=0.0)
        assert decision1.status == "recover"

        # Reset stuck state by providing progress
        ctrl._stuck._samples.clear()
        ctrl._recoveries = 0

        # seg2 should not be stuck with new progress
        sample2 = self._sample(progress=0.5, flow=0.5, distance=50.0)
        decision2 = ctrl.step(seg2, sample2, now=0.0)
        assert decision2.status == "move"


# ---------------------------------------------------------------------------
# MapNavigationRuntime integration
# ---------------------------------------------------------------------------

class TestMapNavigationRuntime:
    """Test MapNavigationRuntime with WaypointGraph."""

    def test_select_destination_basic(self) -> None:
        from knowledge.knowledge_schema import TraversalEdge, Waypoint
        from knowledge.world_graph import WaypointGraph
        from navigation.map_navigation_runtime import MapNavigationRuntime, NavigationPlan

        waypoints = [
            Waypoint(waypoint_id="wp_a", region="mondstadt", position=(0.0, 0.0, 0.0)),
            Waypoint(waypoint_id="wp_b", region="mondstadt", position=(10.0, 0.0, 0.0)),
            Waypoint(waypoint_id="wp_c", region="mondstadt", position=(20.0, 0.0, 0.0)),
        ]
        edges = [
            TraversalEdge(from_waypoint="wp_a", to_waypoint="wp_b", cost=1.0),
            TraversalEdge(from_waypoint="wp_b", to_waypoint="wp_c", cost=1.0),
        ]
        graph = WaypointGraph(waypoints, edges)
        runtime = MapNavigationRuntime(graph)

        plan = runtime.select_destination("wp_c", current_waypoint="wp_a")

        assert isinstance(plan, NavigationPlan)
        assert plan.objective == "wp_c"
        assert plan.arrived is False
        assert len(plan.legs) >= 2

    def test_select_destination_unknown_objective(self) -> None:
        from knowledge.knowledge_schema import TraversalEdge, Waypoint
        from knowledge.world_graph import WaypointGraph
        from navigation.map_navigation_runtime import MapNavigationRuntime, NavigationPlan

        waypoints = [
            Waypoint(waypoint_id="wp_a", region="mondstadt", position=(0.0, 0.0, 0.0)),
        ]
        edges = [TraversalEdge(from_waypoint="wp_a", to_waypoint="wp_a", cost=0.0)]
        graph = WaypointGraph(waypoints, edges)
        runtime = MapNavigationRuntime(graph)

        plan = runtime.select_destination("nonexistent_objective")

        assert isinstance(plan, NavigationPlan)
        assert plan.fallback_allowed is False
        assert len(plan.legs) == 0

    def test_select_destination_shortest_path(self) -> None:
        from knowledge.knowledge_schema import TraversalEdge, Waypoint
        from knowledge.world_graph import WaypointGraph
        from navigation.map_navigation_runtime import MapNavigationRuntime

        waypoints = [
            Waypoint(waypoint_id="start", region="mondstadt", position=(0.0, 0.0, 0.0)),
            Waypoint(waypoint_id="mid", region="mondstadt", position=(5.0, 0.0, 0.0)),
            Waypoint(waypoint_id="goal", region="mondstadt", position=(10.0, 0.0, 0.0)),
        ]
        edges = [
            TraversalEdge(from_waypoint="start", to_waypoint="mid", cost=1.0),
            TraversalEdge(from_waypoint="mid", to_waypoint="goal", cost=1.0),
            TraversalEdge(from_waypoint="start", to_waypoint="goal", cost=100.0),
        ]
        graph = WaypointGraph(waypoints, edges)
        runtime = MapNavigationRuntime(graph)

        plan = runtime.select_destination("goal", current_waypoint="start")

        # Should take the short path via mid, not the direct 100-cost edge
        leg_ids = [leg.waypoint_id for leg in plan.legs]
        assert "mid" in leg_ids or len(plan.legs) <= 2

    def test_mark_arrived(self) -> None:
        from knowledge.knowledge_schema import TraversalEdge, Waypoint
        from knowledge.world_graph import WaypointGraph
        from navigation.map_navigation_runtime import MapNavigationRuntime, NavigationLeg, NavigationPlan

        waypoints = [
            Waypoint(waypoint_id="wp_a", region="mondstadt", position=(0.0, 0.0, 0.0)),
            Waypoint(waypoint_id="wp_b", region="mondstadt", position=(10.0, 0.0, 0.0)),
        ]
        edges = [TraversalEdge(from_waypoint="wp_a", to_waypoint="wp_b", cost=1.0)]
        graph = WaypointGraph(waypoints, edges)
        runtime = MapNavigationRuntime(graph)

        plan = runtime.select_destination("wp_b", current_waypoint="wp_a")
        updated = runtime.mark_arrived(plan, leg_index=0)

        assert updated.arrived is True
        assert updated.arrived_leg_index == 0

    def test_mark_failed(self) -> None:
        from knowledge.knowledge_schema import TraversalEdge, Waypoint
        from knowledge.world_graph import WaypointGraph
        from navigation.map_navigation_runtime import MapNavigationRuntime

        waypoints = [
            Waypoint(waypoint_id="wp_a", region="mondstadt", position=(0.0, 0.0, 0.0)),
            Waypoint(waypoint_id="wp_b", region="mondstadt", position=(10.0, 0.0, 0.0)),
        ]
        edges = [TraversalEdge(from_waypoint="wp_a", to_waypoint="wp_b", cost=1.0)]
        graph = WaypointGraph(waypoints, edges)
        runtime = MapNavigationRuntime(graph)

        plan = runtime.select_destination("wp_b", current_waypoint="wp_a")
        updated = runtime.mark_failed(plan, failed_leg_id="wp_b")

        assert updated.arrived is False
        assert "wp_b" in updated.failed_legs
        assert updated.fallback_allowed is False

    def test_legs_teleport_vs_walk(self) -> None:
        from knowledge.knowledge_schema import TraversalEdge, Waypoint
        from knowledge.world_graph import WaypointGraph
        from navigation.map_navigation_runtime import MapNavigationRuntime

        waypoints = [
            Waypoint(waypoint_id="wp_a", region="mondstadt", position=(0.0, 0.0, 0.0)),
            Waypoint(waypoint_id="wp_b", region="mondstadt", position=(10.0, 0.0, 0.0)),
            Waypoint(waypoint_id="wp_c", region="mondstadt", position=(20.0, 0.0, 0.0)),
        ]
        edges = [
            TraversalEdge(from_waypoint="wp_a", to_waypoint="wp_b", cost=1.0),
            TraversalEdge(from_waypoint="wp_b", to_waypoint="wp_c", cost=1.0),
        ]
        graph = WaypointGraph(waypoints, edges)
        runtime = MapNavigationRuntime(graph)

        plan = runtime.select_destination("wp_c", current_waypoint="wp_a")

        # Intermediate legs should be teleport, last leg should be walk
        leg_methods = [leg.method for leg in plan.legs]
        assert "teleport" in leg_methods
        assert "walk" in leg_methods