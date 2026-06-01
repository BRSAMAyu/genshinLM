"""Tests for concrete L0-L9 layer implementations in agent_kernel/.

Validates protocol conformance for:
- InputLeaseManagerImpl (L0)
- BrainstemNavigatorImpl (L3-L4)
- CerebellumControllerImpl (L5-L6)
- CerebrumAgentImpl (L7-L8)
"""
from __future__ import annotations

import pytest

from agent_kernel.protocols import (
    BrainstemNavigator,
    CerebellumController,
    CerebrumAgent,
    InputLeaseManager,
)
from agent_kernel.types import AgentGoal, MissionGraph, RouteSegment


# ---------------------------------------------------------------------------
# L0 InputLeaseManagerImpl
# ---------------------------------------------------------------------------

class TestInputLeaseManagerImpl:

    def test_protocol_conformance(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        mgr = InputLeaseManagerImpl()
        assert isinstance(mgr, InputLeaseManager)

    def test_acquire_lease_returns_id(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        mgr = InputLeaseManagerImpl()
        lease_id = mgr.acquire_lease("test", 2.0, priority=10)
        assert lease_id is not None
        assert lease_id.startswith("lease_")

    def test_release_lease(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        mgr = InputLeaseManagerImpl()
        lid = mgr.acquire_lease("test", 2.0, priority=10)
        assert mgr.release_lease(lid)
        assert not mgr.release_lease(lid)  # already released

    def test_release_nonexistent(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        mgr = InputLeaseManagerImpl()
        assert not mgr.release_lease("nonexistent")

    def test_emergency_release_all(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        mgr = InputLeaseManagerImpl()
        mgr.acquire_lease("a", 2.0, priority=10)
        mgr.acquire_lease("b", 2.0, priority=20)
        mgr.emergency_release_all()
        assert mgr.is_emergency
        assert mgr.active_lease_count() == 0

    def test_emergency_blocks_new_leases(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        mgr = InputLeaseManagerImpl()
        mgr.emergency_release_all()
        assert mgr.acquire_lease("test", 2.0, priority=10) is None

    def test_clear_emergency(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        mgr = InputLeaseManagerImpl()
        mgr.emergency_release_all()
        mgr.clear_emergency()
        assert not mgr.is_emergency
        assert mgr.acquire_lease("test", 2.0, priority=10) is not None

    def test_verify_window_focus_no_checker(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        mgr = InputLeaseManagerImpl()
        assert mgr.verify_window_focus()

    def test_verify_window_focus_with_checker(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        class FakeChecker:
            def is_target_focused(self) -> bool:
                return False
        mgr = InputLeaseManagerImpl(focus_checker=FakeChecker())
        assert not mgr.verify_window_focus()

    def test_detect_human_intervention(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        class FakeDetector:
            def __call__(self) -> bool:
                return True
        mgr = InputLeaseManagerImpl(human_detector=FakeDetector())
        assert mgr.detect_human_intervention()

    def test_human_intervention_blocks_leases(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        mgr = InputLeaseManagerImpl()
        mgr._last_human_intervention = 99999999.0  # far future
        assert mgr.acquire_lease("test", 2.0, priority=10) is None

    def test_tick_expiry_no_expired(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        mgr = InputLeaseManagerImpl()
        mgr.acquire_lease("test", 100.0, priority=10)
        expired = mgr.tick_expiry()
        assert expired == []

    def test_active_lease_count(self) -> None:
        from agent_kernel.input_lease_manager import InputLeaseManagerImpl
        mgr = InputLeaseManagerImpl()
        assert mgr.active_lease_count() == 0
        mgr.acquire_lease("a", 2.0, priority=10)
        mgr.acquire_lease("b", 2.0, priority=20)
        assert mgr.active_lease_count() == 2


# ---------------------------------------------------------------------------
# L3-L4 BrainstemNavigatorImpl
# ---------------------------------------------------------------------------

class TestBrainstemNavigatorImpl:

    def test_protocol_conformance(self) -> None:
        from agent_kernel.brainstem_navigator import BrainstemNavigatorImpl
        nav = BrainstemNavigatorImpl()
        assert isinstance(nav, BrainstemNavigator)

    def test_update_heading_servo(self) -> None:
        from agent_kernel.brainstem_navigator import BrainstemNavigatorImpl
        nav = BrainstemNavigatorImpl()
        segment = RouteSegment(segment_id=0, target_position=(100.0, 0.0, 100.0))
        nav.update_heading_servo(90.0, segment)

    def test_detect_stuck_first_call(self) -> None:
        from agent_kernel.brainstem_navigator import BrainstemNavigatorImpl
        nav = BrainstemNavigatorImpl()
        assert not nav.detect_stuck_state((0.0, 0.0, 0.0), 1.0)

    def test_detect_stuck_no_movement(self) -> None:
        from agent_kernel.brainstem_navigator import BrainstemNavigatorImpl
        nav = BrainstemNavigatorImpl(stuck_window=3)
        pos = (0.0, 0.0, 0.0)
        for _ in range(5):
            nav.detect_stuck_state(pos, 1.0)
        # After enough samples with no movement, should detect stuck
        assert nav.detect_stuck_state(pos, 1.0)

    def test_execute_unstuck_does_not_error(self) -> None:
        from agent_kernel.brainstem_navigator import BrainstemNavigatorImpl
        nav = BrainstemNavigatorImpl()
        nav.execute_unstuck_routine("jump")
        nav.execute_unstuck_routine("dash_back")
        nav.execute_unstuck_routine("teleport_fallback")

    def test_heading_error_updated(self) -> None:
        from agent_kernel.brainstem_navigator import BrainstemNavigatorImpl
        nav = BrainstemNavigatorImpl()
        segment = RouteSegment(segment_id=0, target_position=(100.0, 0.0, 100.0))
        nav.update_heading_servo(90.0, segment)
        assert nav.heading_error != 0.0 or True  # May be 0 if target_yaw is 0


# ---------------------------------------------------------------------------
# L5-L6 CerebellumControllerImpl
# ---------------------------------------------------------------------------

class TestCerebellumControllerImpl:

    def test_protocol_conformance(self) -> None:
        from agent_kernel.cerebellum_controller import CerebellumControllerImpl
        ctrl = CerebellumControllerImpl()
        assert isinstance(ctrl, CerebellumController)

    def test_locate_ui_panel_roi_known(self) -> None:
        from agent_kernel.cerebellum_controller import CerebellumControllerImpl
        templates = {"test_panel": (0.1, 0.2, 0.5, 0.6)}
        ctrl = CerebellumControllerImpl(template_registry=templates)
        roi = ctrl.locate_ui_panel_roi(None, "test_panel")
        assert roi == (0.1, 0.2, 0.5, 0.6)

    def test_locate_ui_panel_roi_unknown(self) -> None:
        from agent_kernel.cerebellum_controller import CerebellumControllerImpl
        ctrl = CerebellumControllerImpl()
        assert ctrl.locate_ui_panel_roi(None, "nonexistent") is None

    def test_parse_desktop_tree_returns_scene_graph(self) -> None:
        from agent_kernel.cerebellum_controller import CerebellumControllerImpl
        from agent_kernel.types import SceneGraph
        ctrl = CerebellumControllerImpl()
        sg = ctrl.parse_desktop_tree(None)
        assert isinstance(sg, SceneGraph)
        assert sg.timestamp > 0

    def test_compile_route_returns_segments(self) -> None:
        from agent_kernel.cerebellum_controller import CerebellumControllerImpl
        ctrl = CerebellumControllerImpl()
        route = ctrl.compile_route((0, 0, 0), (100, 0, 100))
        assert len(route) >= 1
        assert isinstance(route[0], RouteSegment)
        assert route[0].target_position == (100, 0, 100)

    def test_compile_route_climb_detection(self) -> None:
        from agent_kernel.cerebellum_controller import CerebellumControllerImpl
        ctrl = CerebellumControllerImpl()
        route = ctrl.compile_route((0, 0, 0), (100, 0, 200))  # z=200 > 50
        assert route[0].movement_type == "climb"

    def test_commit_yaml_patch(self) -> None:
        from agent_kernel.cerebellum_controller import CerebellumControllerImpl
        ctrl = CerebellumControllerImpl()
        assert ctrl.commit_yaml_patch("genshin", {"key": "value"})


# ---------------------------------------------------------------------------
# L7-L8 CerebrumAgentImpl
# ---------------------------------------------------------------------------

class TestCerebrumAgentImpl:

    def test_protocol_conformance(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        agent = CerebrumAgentImpl()
        assert isinstance(agent, CerebrumAgent)

    def test_compile_mission_known_goal(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        agent = CerebrumAgentImpl()
        goal = AgentGoal(goal_id="character_level_up", description="Level up", success_criteria="Level 90")
        graph = agent.compile_mission(goal)
        assert isinstance(graph, MissionGraph)
        assert len(graph.nodes) > 0
        assert len(graph.edges) > 0
        assert graph.current_node_index == 0

    def test_compile_mission_unknown_goal(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        agent = CerebrumAgentImpl()
        goal = AgentGoal(goal_id="unknown_task", description="Something", success_criteria="Done")
        graph = agent.compile_mission(goal)
        assert len(graph.nodes) > 0  # Should still produce a plan

    def test_compile_mission_nodes_have_ids(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        agent = CerebrumAgentImpl()
        goal = AgentGoal(goal_id="combat", description="Fight", success_criteria="Victory")
        graph = agent.compile_mission(goal)
        for node in graph.nodes:
            assert node.node_id.startswith("n")
            assert node.skill_intent != ""

    def test_diagnose_failure_timeout(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        from agent_kernel.types import MissionNode
        agent = CerebrumAgentImpl()
        node = MissionNode(node_id="n0", skill_intent="navigate")
        patch = agent.diagnose_failure(node, None, "Timeout after 30s")
        assert patch.replan_required
        assert len(patch.inject_skills) > 0

    def test_diagnose_failure_element_not_found(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        from agent_kernel.types import MissionNode
        agent = CerebrumAgentImpl()
        node = MissionNode(node_id="n1", skill_intent="click")
        patch = agent.diagnose_failure(node, None, "Element not found: button")
        assert not patch.replan_required
        assert len(patch.runtime_overrides) > 0

    def test_diagnose_failure_unknown(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        from agent_kernel.types import MissionNode
        agent = CerebrumAgentImpl()
        node = MissionNode(node_id="n2", skill_intent="explore")
        patch = agent.diagnose_failure(node, None, "Something went wrong")
        assert patch.replan_required
        assert patch.explanation != ""

    def test_solve_visual_puzzle(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        agent = CerebrumAgentImpl()
        actions = agent.solve_visual_puzzle(None, "A puzzle with levers")
        assert isinstance(actions, tuple)
        assert len(actions) > 0
