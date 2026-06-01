"""Tests for Phase 8: Navigation StateBus integration.

Verifies:
- MapNavigationRuntime writes NavigationPlan to StateBus.navigation_plan
- navigation_plan slot version increments on each plan
- Mark arrived/failed updates StateBus slot
"""
from __future__ import annotations

from core.state_bus import StateBus
from navigation.map_navigation_runtime import MapNavigationRuntime, NavigationPlan, NavigationLeg


class _FakeWaypoint:
    def __init__(self, wp_id: str, pos: tuple[float, float, float] = (0.0, 0.0, 0.0)):
        self.waypoint_id = wp_id
        self.position = pos
        self.region = "mondstadt"


class _FakeGraph:
    def __init__(self, waypoints: dict[str, _FakeWaypoint] | None = None):
        self._waypoints = {k: v for k, v in (waypoints or {}).items()}
        self._adj: dict[str, list[str]] = {k: [] for k in self._waypoints}

    def shortest_path(self, src: str, dst: str):
        if src in self._waypoints and dst in self._waypoints:
            return _PathResult(True, 1.0, [src, dst])
        return _PathResult(False, float("inf"), [])

    def nearest_waypoint(self, source):
        if self._waypoints:
            return next(iter(self._waypoints))
        return None


class _PathResult:
    def __init__(self, ok, cost, path):
        self.ok = ok
        self.cost = cost
        self.path = path


class TestNavigationStateBus:
    """Test MapNavigationRuntime writes to StateBus."""

    def test_select_destination_writes_to_statebus(self):
        bus = StateBus()
        wp1 = _FakeWaypoint("wp1", (100.0, 200.0, 0.0))
        wp2 = _FakeWaypoint("wp2", (300.0, 400.0, 0.0))
        graph = _FakeGraph({"wp1": wp1, "wp2": wp2})
        graph._adj = {"wp1": ["wp2"], "wp2": ["wp1"]}

        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        plan = runtime.select_destination("wp2", current_waypoint="wp1")

        slot_value = bus.navigation_plan.get()
        assert slot_value is not None
        assert slot_value.plan_id == plan.plan_id

    def test_navigation_plan_version_increments(self):
        bus = StateBus()
        wp1 = _FakeWaypoint("wp1", (0.0, 0.0, 0.0))
        wp2 = _FakeWaypoint("wp2", (1.0, 1.0, 0.0))
        graph = _FakeGraph({"wp1": wp1, "wp2": wp2})
        graph._adj = {"wp1": ["wp2"], "wp2": ["wp1"]}

        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        v0 = bus.navigation_plan.version
        runtime.select_destination("wp2", current_waypoint="wp1")
        v1 = bus.navigation_plan.version
        assert v1 > v0

    def test_mark_arrived_updates_statebus(self):
        bus = StateBus()
        graph = _FakeGraph({})
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)

        plan = NavigationPlan(plan_id="p1", objective="test", legs=())
        updated = runtime.mark_arrived(plan, 0)
        assert updated.arrived is True
        assert bus.navigation_plan.get().arrived is True

    def test_mark_failed_updates_statebus(self):
        bus = StateBus()
        graph = _FakeGraph({})
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)

        plan = NavigationPlan(plan_id="p1", objective="test", legs=())
        updated = runtime.mark_failed(plan, "leg_1")
        assert "leg_1" in updated.failed_legs
        assert bus.navigation_plan.get().fallback_allowed is False

    def test_no_statebus_does_not_crash(self):
        graph = _FakeGraph({})
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=None)
        plan = runtime.select_destination("wp1")
        assert plan is not None
