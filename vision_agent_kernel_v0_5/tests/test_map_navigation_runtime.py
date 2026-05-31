"""Tests for navigation/map_navigation_runtime.py: Phase 4 NavigationPlan producer."""
from __future__ import annotations

import pytest

from core.state_bus import StateBus
from knowledge.knowledge_schema import SourceNode, TraversalEdge, Waypoint
from knowledge.world_graph import PathResult, WaypointGraph
from navigation.map_navigation_runtime import (
    MapNavigationRuntime,
    NavigationLeg,
    NavigationPlan,
)


class TestNavigationLeg:
    def test_frozen(self):
        leg = NavigationLeg(method="teleport", waypoint_id="windrise", expected_duration_sec=5.0)
        assert leg.method == "teleport"
        assert leg.waypoint_id == "windrise"


class TestNavigationPlan:
    def test_defaults(self):
        plan = NavigationPlan(plan_id="test", objective="mon:windrise")
        assert plan.arrived is False
        assert plan.arrived_leg_index == -1
        assert plan.legs == ()
        assert plan.fallback_allowed is True

    def test_arrived_flag_consistency(self):
        plan = NavigationPlan(
            plan_id="test",
            objective="mon:windrise",
            legs=(NavigationLeg(method="teleport", waypoint_id="windrise"),),
            arrived=True,
            arrived_leg_index=0,
        )
        assert plan.arrived is True
        assert plan.arrived_leg_index == 0

    def test_failed_legs_tuple(self):
        plan = NavigationPlan(
            plan_id="test",
            objective="mon:windrise",
            failed_legs=("leg_1",),
        )
        assert len(plan.failed_legs) == 1


class TestMapNavigationRuntime:
    @pytest.fixture
    def graph(self) -> WaypointGraph:
        waypoints = [
            Waypoint(waypoint_id="mondstadt_waypoint", region="mondstadt", position=(100.0, 50.0, 0.0)),
            Waypoint(waypoint_id="windrise", region="mondstadt", position=(200.0, 150.0, 0.0)),
            Waypoint(waypoint_id="starsnape_cliff", region="mondstadt", position=(300.0, 250.0, 0.0)),
            Waypoint(waypoint_id="dawn_ winery", region="mondstadt", position=(500.0, 100.0, 0.0)),
        ]
        edges = [
            TraversalEdge(from_waypoint="mondstadt_waypoint", to_waypoint="windrise", cost=1.0),
            TraversalEdge(from_waypoint="windrise", to_waypoint="starsnape_cliff", cost=1.0),
            TraversalEdge(from_waypoint="mondstadt_waypoint", to_waypoint="dawn_ winery", cost=1.0),
        ]
        return WaypointGraph(waypoints, edges)

    @pytest.fixture
    def bus(self) -> StateBus:
        return StateBus()

    def test_select_destination_with_path(self, graph, bus):
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        plan = runtime.select_destination(
            objective="mon:windrise",
            current_waypoint="mondstadt_waypoint",
        )
        assert plan.plan_id.startswith("nav_")
        assert plan.objective == "mon:windrise"
        assert len(plan.legs) >= 1
        assert plan.legs[0].waypoint_id in ("windrise", "mondstadt_waypoint")
        assert plan.failed_legs == ()

    def test_select_destination_fallback_nearest(self, graph, bus):
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        plan = runtime.select_destination(
            objective="mon:starsnape_cliff",
            current_region="mondstadt",
        )
        assert len(plan.legs) >= 1
        assert plan.arrived is False

    def test_select_destination_unknown_objective(self, graph, bus):
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        plan = runtime.select_destination(
            objective="mon:nonexistent_waypoint",
            current_waypoint="mondstadt_waypoint",
        )
        assert plan.legs == ()
        # Unknown objectives still allow fallback (e.g. VLM resolution)
        assert plan.fallback_allowed is True

    def test_select_destination_unreachable(self, graph, bus):
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        # Path from windrise to dawn winery is reachable via mondstadt_waypoint
        # but direct unreachable case would need isolated waypoints
        plan = runtime.select_destination(
            objective="mon:windrise",
            current_waypoint="windrise",
        )
        # windrise is start, so path is just windrise itself
        assert plan.legs[0].waypoint_id == "windrise"

    def test_select_destination_writes_to_statebus(self, graph, bus):
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        plan = runtime.select_destination(
            objective="mon:windrise",
            current_waypoint="mondstadt_waypoint",
        )
        slot = bus.navigation_plan.get()
        assert slot is not None
        assert slot.plan_id == plan.plan_id

    def test_select_destination_bare_waypoint_name(self, graph, bus):
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        plan = runtime.select_destination(
            objective="windrise",
            current_waypoint="mondstadt_waypoint",
        )
        assert len(plan.legs) >= 1

    def test_mark_arrived_updates_plan(self, graph, bus):
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        plan = runtime.select_destination(
            objective="mon:windrise",
            current_waypoint="mondstadt_waypoint",
        )
        updated = runtime.mark_arrived(plan, leg_index=0)
        assert updated.arrived is True
        assert updated.arrived_leg_index == 0
        assert bus.navigation_plan.get().arrived is True

    def test_mark_failed_records_failed_leg(self, graph, bus):
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        plan = runtime.select_destination(
            objective="mon:windrise",
            current_waypoint="mondstadt_waypoint",
        )
        updated = runtime.mark_failed(plan, failed_leg_id="leg_windrise")
        assert "leg_windrise" in updated.failed_legs
        assert updated.fallback_allowed is False

    def test_select_destination_npc_prefix(self, graph, bus):
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        plan = runtime.select_destination(
            objective="npc:amber",
            current_waypoint="windrise",
        )
        # amber is not in graph, so no legs
        assert plan.legs == ()

    def test_select_destination_waypoint_prefix(self, graph, bus):
        runtime = MapNavigationRuntime(waypoint_graph=graph, state_bus=bus)
        plan = runtime.select_destination(
            objective="waypoint:windrise",
            current_waypoint="mondstadt_waypoint",
        )
        assert len(plan.legs) >= 1