from __future__ import annotations

import math
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from agent.exploration_agent import ExplorationAgent, ExplorationAction
from control.recovery_policy import RecoveryPolicy
from core.types import ProgressState, CameraIntent, MovementIntent
from execution.safe_window_backend import SafeWindowInputBackend
from perception.genshin_screen_classifier import GenshinScreenClassifier, ScreenState
from planning.screen_state_claim import ScreenStateClaim
from planning.screen_state_claim_builder import VLMOutput


# ===========================================================================
# 1. Perception Noise / Adaptive Screen Classifier Tests
# ===========================================================================

def test_screen_classifier_adaptive_dialog():
    classifier = GenshinScreenClassifier()
    
    # Create a dark frame (low brightness, cave/night scenario)
    dark_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    
    # Create a bright frame (high brightness, glare/snowfield scenario)
    bright_frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 255
    
    # Verify dialogue detection handles extreme light values without crash
    res_dark = classifier.classify(dark_frame)
    res_bright = classifier.classify(bright_frame)
    
    assert res_dark is not None
    assert res_bright is not None
    assert isinstance(res_dark, ScreenState)
    assert isinstance(res_bright, ScreenState)


# ===========================================================================
# 2. Physics & Collision stuck recovery tests
# ===========================================================================

def test_recovery_policy_frustration_slope():
    policy = RecoveryPolicy()
    
    # Step 1: Baseline sample
    p1 = ProgressState(
        timestamp=1.0,
        ewma_progress=1.0,
        progress_slope_2s=0.0,
        visibility_ratio_1s=1.0,
        oscillation_score=0.0,
        frustration=0.0,
        trend="FLAT",
        active_interrupt=None,
    )
    dec1 = policy.decide(p1)
    assert dec1.action == "continue"
    
    # Step 2: High frustration spike (rapid rise in a short time window, e.g., dt=0.5s, df=12.0 -> slope = 24.0)
    p2 = ProgressState(
        timestamp=1.5,
        ewma_progress=1.0,
        progress_slope_2s=-0.02,
        visibility_ratio_1s=1.0,
        oscillation_score=0.0,
        frustration=12.0,
        trend="FLAT",
        active_interrupt=None,
    )
    dec2 = policy.decide(p2)
    
    # Verify that rapidly rising frustration slope triggers SMOOTH_BYPASS instantly
    # even though absolute frustration level (12.0) is below the default threshold (20.0).
    assert dec2.action == "SMOOTH_BYPASS"
    assert "stuck_bypass_backoff" in dec2.reason
    assert isinstance(dec2.movement_intent, MovementIntent)
    assert dec2.movement_intent.move_forward == -0.6  # Verify it backs off first to clear contact

    # Step 3: Continues stuck state, verify stage cycles to arcing lateral run
    p3 = ProgressState(
        timestamp=2.0,
        ewma_progress=1.0,
        progress_slope_2s=-0.02,
        visibility_ratio_1s=1.0,
        oscillation_score=0.0,
        frustration=15.0,
        trend="FLAT",
        active_interrupt=None,
    )
    dec3 = policy.decide(p3)
    assert dec3.action == "SMOOTH_BYPASS"
    assert "stuck_bypass_arc_run" in dec3.reason
    assert isinstance(dec3.movement_intent, MovementIntent)
    assert dec3.movement_intent.move_forward == 0.7  # Diagonal forward run
    assert dec3.movement_intent.move_right != 0.0


# ===========================================================================
# 3. Cognitive VLM latency state guard & synonym tests
# ===========================================================================

def test_exploration_agent_synonym_normalization():
    mock_perc = MagicMock()
    agent = ExplorationAgent(perception=mock_perc, risk_level="low")
    
    # 1. Test synonym normalizations
    assert agent._normalize_vlm_action("Press F") == "interact"
    assert agent._normalize_vlm_action("walk") == "move_forward"
    assert agent._normalize_vlm_action("fight") == "click_anchor"
    assert agent._normalize_vlm_action("dialog_skip") == "skip_cutscene"
    assert agent._normalize_vlm_action("Select option") == "select_option"
    assert agent._normalize_vlm_action("") == "observe"


def test_exploration_agent_latency_mismatch_guard():
    mock_perc = MagicMock()
    agent = ExplorationAgent(perception=mock_perc, risk_level="low")
    
    # Configure mock perception to return a VLM response suggesting action on "world_hud"
    vlm_output = VLMOutput(
        screen_state="world_hud",
        player_status={},
        visible_objects=[],
        ui_elements={},
        scene_description="Combat scenario",
        suggested_action="combat",
        raw_text="",
    )
    mock_perc.analyze_vlm.return_value = vlm_output
    
    # Current active state is different (e.g. dialog opened during VLM cloud latency)
    claim_state = MagicMock(spec=ScreenStateClaim)
    claim_state.screen_state = "dialog"
    claim_state.game_id = "genshin"
    claim_state.confidence = 0.9
    claim_state.actionable_elements.return_value = []
    
    dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
    
    # Call explore_next_step
    action = agent.explore_next_step(dummy_frame, "complete quest", claim_state)
    
    # Verify that visual state mismatch triggers safety fallback "observe"
    assert action.action_type == "observe"
    assert "VLM suggestion stale due to transition" in action.rationale


# ===========================================================================
# 4. Actuation Safety & Anti-Cheat Bezier Glides Tests
# ===========================================================================

def test_safe_window_input_backend_bezier_glide():
    # Mock ctypes Windll and user32 interfaces to run without real Windows GUI environment
    with patch("ctypes.windll") as mock_windll, patch("ctypes.byref", lambda x: x):
        mock_user32 = MagicMock()
        mock_windll.user32 = mock_user32
        
        # Configure GetCursorPos to return coordinates (100, 100)
        def mock_get_cursor(point):
            point.x = 100
            point.y = 100
            return True
            
        mock_user32.GetCursorPos = mock_get_cursor
        mock_user32.SetCursorPos = MagicMock()
        
        backend = SafeWindowInputBackend(target_window_title="MockGenshin")
        backend._user32 = mock_user32
        
        # Ensure target window focus check is stubbed to pass
        backend.is_target_focused = MagicMock(return_value=True)
        
        # Dispatch move_cursor to glide from (100, 100) to (200, 150)
        backend.move_cursor(200, 150, reason="test_bezier_glide")
        
        # Verify SetCursorPos was called at intermediate steps and finally at the endpoint
        assert mock_user32.SetCursorPos.call_count >= 2
        mock_user32.SetCursorPos.assert_called_with(200, 150)


# ===========================================================================
# 5. Live Overworld Physical and Topological Recovery Tests
# ===========================================================================

def test_somatic_wind_glider_climb_exhaustion():
    from control.sentinel.somatic_state_supervisor import SomaticStateSupervisor, SomaticConfig, StaminaZone
    backend = MagicMock()
    
    # Configure supervisor
    config = SomaticConfig(stamina_critical_threshold=0.15)
    supervisor = SomaticStateSupervisor(config=config)
    
    # Create dummy frame where stamina is below critical threshold (e.g. 0.05)
    with patch.object(supervisor, "_detect_stamina_bar", return_value=0.05), \
         patch.object(supervisor, "_detect_health_bar", return_value=0.8), \
         patch.object(supervisor, "_detect_hazards", return_value=("safe", None)):
        
        dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        state, intercepted = supervisor.monitor_and_intercept(backend, dummy_frame)
        
        # Verify state is critical
        assert state.stamina_zone in (StaminaZone.CRITICAL, StaminaZone.EMPTY)
        assert intercepted is True
        
        # Verify Wind-Glider deployment keyboard sequence was sent to backend
        backend.key_down.assert_any_call("x", reason="let_go_of_wall")
        backend.key_up.assert_any_call("x")
        
        space_down_calls = [c for c in backend.key_down.call_args_list if c[0][0] == "space"]
        space_up_calls = [c for c in backend.key_up.call_args_list if c[0][0] == "space" and "somatic_stamina_halt" not in str(c)]
        assert len(space_down_calls) == 2
        assert len(space_up_calls) == 2


def test_somatic_backpack_food_depleted_teleport():
    from control.sentinel.somatic_state_supervisor import SomaticStateSupervisor, SomaticConfig, HealthZone
    backend = MagicMock()
    mock_rect = MagicMock()
    mock_rect.center = (960, 540)
    backend.client_rect.return_value = mock_rect
    
    config = SomaticConfig(health_critical_threshold=0.2)
    supervisor = SomaticStateSupervisor(config=config)
    supervisor._food_count = 0  # deplete food
    
    with patch.object(supervisor, "_detect_stamina_bar", return_value=0.8), \
         patch.object(supervisor, "_detect_health_bar", return_value=0.2), \
         patch.object(supervisor, "_detect_hazards", return_value=("safe", None)):
        
        dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        state, intercepted = supervisor.monitor_and_intercept(backend, dummy_frame)
        
        # Health zone should be CRITICAL
        assert state.health_zone == HealthZone.CRITICAL
        assert intercepted is True
        
        # Verify emergency teleport sequence was sent to backend
        backend.key_down.assert_any_call("m", reason="emergency_statue_teleport")
        backend.key_up.assert_any_call("m")
        backend.click_at.assert_called_with(960, 540, reason="teleport_statue_selection")
        backend.key_down.assert_any_call("enter", reason="confirm_statue_teleport")
        backend.key_up.assert_any_call("enter")


def test_combat_camera_target_align():
    from combat.live_combat_actuator import LiveCombatActuator
    backend = MagicMock()
    actuator = LiveCombatActuator(backend)
    
    playbook_steps = [{"type": "attack", "duration": 0.1}]
    # Simulate target offset to the right by 0.3
    obs_stream = lambda: {"hp_ratio": 0.8, "target_offset_x": 0.3, "signals": {}}
    
    res = actuator.execute_combat_loop(playbook_steps, obs_stream)
    assert res is True
    
    # Verify that mouse_move was called with proportional offset (0.3 * 40.0 = 12.0)
    backend.mouse_move.assert_called_with(12.0, 0.0, reason="combat_camera_align")


def test_combat_attack_dodge_iframe():
    from combat.live_combat_actuator import LiveCombatActuator
    backend = MagicMock()
    actuator = LiveCombatActuator(backend)
    
    playbook_steps = [{"type": "attack", "duration": 0.1}]
    # Attack incoming signal is high
    obs_stream = lambda: {"hp_ratio": 0.8, "signals": {"attack_incoming": 1.0}}
    
    res = actuator.execute_combat_loop(playbook_steps, obs_stream)
    assert res is True
    
    # Verify rapid double-shift dodge sequence was triggered
    shift_down_calls = [c for c in backend.key_down.call_args_list if c[0][0] == "shift"]
    shift_up_calls = [c for c in backend.key_up.call_args_list if c[0][0] == "shift"]
    assert len(shift_down_calls) == 2
    assert len(shift_up_calls) == 2


def test_jit_party_switch_puzzle_healer():
    from planning.mainline.bagel_jit_router import BagelJitRouter
    from planning.mainline.mission_graph_v4 import MissionGraphV4, MissionNodeV4, MissionEdgeV4
    
    graph = MissionGraphV4(mission_id="puzzle_mission")
    start = MissionNodeV4(node_id="start", node_type="story")
    puzzle = MissionNodeV4(node_id="puzzle_node", node_type="puzzle")
    end = MissionNodeV4(node_id="end", node_type="story")
    
    graph.add_node(start)
    graph.add_node(puzzle)
    graph.add_node(end)
    
    graph.add_edge(MissionEdgeV4("start", "puzzle_node"))
    graph.add_edge(MissionEdgeV4("puzzle_node", "end"))
    
    router = BagelJitRouter(graph)
    mutated = router.handle_belief_falsification(
        falsified_belief_id="pyro_elemental_missing",
        failed_node_id="puzzle_node"
    )
    
    assert mutated is True
    new_order = graph.topological_order()
    assert "puzzle_node_switch_party_healing" in new_order
    
    # Check correct wiring: start -> puzzle_node_switch_party_healing -> puzzle_node -> end
    switch_node = graph.get_node("puzzle_node_switch_party_healing")
    assert switch_node is not None
    assert switch_node.metadata.get("required_element") == "pyro"


def test_jit_occluded_loot_bypass():
    from planning.mainline.bagel_jit_router import BagelJitRouter
    from planning.mainline.mission_graph_v4 import MissionGraphV4, MissionNodeV4, MissionEdgeV4
    
    graph = MissionGraphV4(mission_id="loot_mission")
    start = MissionNodeV4(node_id="start", node_type="story")
    loot = MissionNodeV4(node_id="collect_materials", node_type="loot")
    end = MissionNodeV4(node_id="end", node_type="story")
    
    graph.add_node(start)
    graph.add_node(loot)
    graph.add_node(end)
    
    graph.add_edge(MissionEdgeV4("start", "collect_materials"))
    graph.add_edge(MissionEdgeV4("collect_materials", "end"))
    
    router = BagelJitRouter(graph)
    mutated = router.handle_belief_falsification(
        falsified_belief_id="loot_occluded_drop",
        failed_node_id="collect_materials"
    )
    
    assert mutated is True
    # The loot node should be isolated and start should link directly to end
    new_order = graph.topological_order()
    assert "end" in graph.successors("start")
    assert "collect_materials" not in graph.successors("start")
    assert "end" not in graph.successors("collect_materials")

