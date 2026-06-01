import pytest
import numpy as np
from typing import Any

from navigation.genshin_navigator import GenshinNavigator
from combat.cooldown_manager import CooldownManager, SkillCooldownConfig
from combat.reflex_evasion import ReflexEvasion
from interaction.puzzle_handler import PuzzleHandler, PuzzleType


class MockInputBackend:
    def __init__(self) -> None:
        self.moves: list[tuple[int, int, str]] = []
        self.clicks: list[str] = []
        self.keys: list[tuple[str, str]] = []
        self.mouse_pos: list[tuple[int, int, str]] = []

    def mouse_move(self, dx: int, dy: int, reason: str = "") -> None:
        self.moves.append((dx, dy, reason))

    def mouse_move_to(self, x: int, y: int, reason: str = "") -> None:
        self.mouse_pos.append((x, y, reason))

    def left_click(self, reason: str = "") -> None:
        self.clicks.append(f"left_click:{reason}")

    def right_click(self, reason: str = "") -> None:
        self.clicks.append(f"right_click:{reason}")

    def key_press(self, key: str, reason: str = "") -> None:
        self.keys.append((key, reason))


def test_genshin_navigator_3d_sweep() -> None:
    backend = MockInputBackend()
    nav = GenshinNavigator(input_backend=backend)
    
    nav.execute_3d_sweep(sweep_angle_deg=360.0, duration_sec=0.1)
    
    assert len(backend.moves) == 20
    assert all(m[2] == "3d_environment_sweep" for m in backend.moves)
    # 360 * 4.5 = 1620 total delta. 1620 / 20 = 81 delta per step
    assert backend.moves[0][0] == 81
    assert backend.moves[0][1] == 0


def test_genshin_navigator_minimap_steering() -> None:
    backend = MockInputBackend()
    nav = GenshinNavigator(input_backend=backend)
    
    # Target is to the right (angle 45 degrees) -> should steer right
    applied = nav.steer_towards_minimap_target(45.0)
    assert applied == 45.0 * 3.5
    assert len(backend.moves) == 1
    assert backend.moves[0][0] == int(45.0 * 3.5)
    assert backend.moves[0][2] == "minimap_chevron_steering"

    backend.moves.clear()
    # Target is to the left (angle 315 degrees -> -45 degrees) -> should steer left
    applied2 = nav.steer_towards_minimap_target(315.0)
    assert applied2 == -45.0 * 3.5
    assert backend.moves[0][0] == int(-45.0 * 3.5)
    
    backend.moves.clear()
    # Target is very close to heading (angle 5 degrees) -> should not steer (under 10 deg threshold)
    applied3 = nav.steer_towards_minimap_target(5.0)
    assert applied3 == 0.0
    assert len(backend.moves) == 0


def test_cooldown_manager_hp_tracking_and_food_healing() -> None:
    backend = MockInputBackend()
    mgr = CooldownManager(input_backend=backend)
    
    # Initial status is 1.0 (Full HP)
    assert mgr.char_hp[1] == 1.0
    
    # Drop HP to 50% -> no food recovery should be triggered
    mgr.update_character_hp(slot_id=2, hp_pct=0.5)
    assert mgr.char_hp[2] == 0.5
    assert len(backend.keys) == 0
    
    # Drop HP to 15% (Critical < 20%) -> triggers emergency food sequence for slot 2
    mgr.update_character_hp(slot_id=2, hp_pct=0.15)
    assert mgr.char_hp[2] == 0.15
    
    # Check backpack DirectInput sequence:
    # 1. 'b' key_press to open backpack
    assert backend.keys[0] == ("b", "open_backpack_emergency")
    # 2. mouse_move_to and left_click on food tab
    assert backend.mouse_pos[0][:2] == (450, 80)
    assert backend.clicks[0] == "left_click:backpack_food_tab"
    # 3. mouse_move_to and click on Sweet Madame coordinates
    assert backend.mouse_pos[1][:2] == (200, 250)
    assert backend.clicks[1] == "left_click:select_premium_recovery_food"
    assert backend.clicks[2] == "left_click:use_recovery_food"
    # 4. select slot "2" and space to confirm
    assert backend.keys[1] == ("2", "select_low_hp_character")
    assert backend.keys[2] == ("space", "confirm_eat_food")
    # 5. exit backpack
    assert backend.keys[3] == ("escape", "close_backpack_resume")


def test_reflex_evasion_check_and_dodge() -> None:
    backend = MockInputBackend()
    evasion = ReflexEvasion()
    
    # 1. Create a safe mock frame (yellow image representing full stamina) -> no threat
    safe_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    safe_frame[:, :] = (0, 255, 255) # BGR Yellow (H=60, S=1.0, V=1.0) to prevent stamina_critical drop dodge
    
    triggered = evasion.check_and_dodge(frame=safe_frame, input_backend=backend)
    assert triggered is False
    assert len(backend.clicks) == 0
    
    # 2. Create a danger mock frame (full red image representing warning zone overlay)
    danger_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    danger_frame[:, :, 2] = 255 # Fill red channel (BGR red is in channel 2)
    
    # We mock GenshinDangerSignalExtractor should_dodge checking by injecting a custom method or testing extraction directly
    triggered_danger = evasion.check_and_dodge(frame=danger_frame, input_backend=backend)
    assert triggered_danger is True
    # Verify the immediate physically injected dodge click
    assert "right_click:50hz_combat_reflex_dodge" in backend.clicks


def test_puzzle_handler_noise_filtering_and_state_extraction() -> None:
    handler = PuzzleHandler()
    
    # 1. Test empty frame
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    assert handler.filter_environment_noise(empty).size == 0
    assert handler.extract_puzzle_landmarks(empty) == []
    
    # 2. Test mock frame with Pyro Torch (Red/Orange cluster) and Electro Monument (Purple cluster)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    
    # BGR values:
    # Pyro: high Red (H ~ 0). Let's put B=0, G=0, R=255.
    frame[10:20, 10:20, 2] = 255
    # Electro: high Purple (H ~ 150). Let's put B=255, G=0, R=255.
    frame[70:80, 70:80, 0] = 255 # Blue
    frame[70:80, 70:80, 2] = 255 # Red
    
    # Filter noise
    filtered = handler.filter_environment_noise(frame)
    assert filtered.any()
    
    # Extract landmarks
    landmarks = handler.extract_puzzle_landmarks(frame)
    assert len(landmarks) == 2
    
    # Verify Pyro Torch is identified at approximate center of its cluster
    pyro = next(item for item in landmarks if item["element_type"] == "pyro_torch")
    assert pyro["id"] == "pyro_torch_1"
    assert pyro["x"] == pytest.approx(0.15, abs=0.05)
    assert pyro["y"] == pytest.approx(0.15, abs=0.05)
    assert pyro["active"] is True
    
    # Verify Electro Monument is identified at approximate center of its cluster
    electro = next(item for item in landmarks if item["element_type"] == "electro_monument")
    assert electro["id"] == "electro_monument_1"
    assert electro["x"] == pytest.approx(0.75, abs=0.05)
    assert electro["y"] == pytest.approx(0.75, abs=0.05)
    assert electro["active"] is False


def test_depth_anything_obstacle_avoidance() -> None:
    from perception.depth_anything_estimator import DepthAnythingEstimator
    
    estimator = DepthAnythingEstimator()
    backend = MockInputBackend()
    nav = GenshinNavigator(input_backend=backend)
    
    # 1. Test empty frame depth
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    assert estimator.estimate_depth(empty).size == 0
    assert estimator.detect_vertical_obstacle(np.zeros((0, 0))) is False
    assert estimator.get_terrain_slope(np.zeros((0, 0))) == 0.0
    
    # 2. Test safe frame (open road, no immediate obstacle in center region)
    safe_frame = np.ones((100, 100, 3), dtype=np.uint8) * 150 # bright horizon BGR
    depth_map = estimator.estimate_depth(safe_frame)
    assert depth_map.shape == (100, 100)
    
    # Center region should not trigger vertical obstacle avoidance
    assert estimator.detect_vertical_obstacle(depth_map) is False
    assert nav.update_3d_avoidance(safe_frame) == 0.0
    assert len(backend.moves) == 0
    
    # 3. Test obstacle frame (dark boulder/wall in central region)
    obstacle_frame = np.ones((100, 100, 3), dtype=np.uint8) * 150
    # Make center region dark representing obstacle
    obstacle_frame[40:70, 35:65] = 20
    
    obs_depth_map = estimator.estimate_depth(obstacle_frame)
    assert estimator.detect_vertical_obstacle(obs_depth_map) is True
    
    # Verify that the navigator executes the obstacle evasion 90-degree yaw steering turn
    applied = nav.update_3d_avoidance(obstacle_frame)
    assert applied == 315.0 # Evasion yaw delta
    assert len(backend.moves) == 1
    assert backend.moves[0][0] == 315
    assert backend.moves[0][2] == "3d_obstacle_evasion"


def test_genshin_dialog_handler_select_choice_by_text() -> None:
    from navigation.genshin_dialog_handler import GenshinDialogHandler
    
    handler = GenshinDialogHandler()
    backend = MockInputBackend()
    frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 200
    
    # 1. Test empty frame
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    assert handler.select_choice_by_text(empty, "Claim Rewards", backend) is False
    
    # 2. Test successful dialogue dynamic selection
    clicked = handler.select_choice_by_text(frame, "Claim Daily Commission Rewards", backend)
    assert clicked is True
    assert len(backend.mouse_pos) == 1
    # Bounding box should center on right half of 1920x1080 -> (1920 * 0.72 = 1382, 1080 * 0.55 = 594)
    assert backend.mouse_pos[0][:2] == (1382, 594)
    assert backend.clicks[0] == "left_click:select_dialogue_option:Claim Daily Commission Rewards"


def test_predictive_heading_servo() -> None:
    backend = MockInputBackend()
    nav = GenshinNavigator(input_backend=backend)
    
    # 1. Empty history
    assert nav.predict_and_steer_yaw([]) == 0.0
    
    # 2. Steer with trend prediction:
    # Chevron history shows a clockwise turning trend: [10, 20, 30] -> diff is +10.
    # Predicted is 30 + 10 * 1.5 = 45.0 degrees.
    applied = nav.predict_and_steer_yaw([10.0, 20.0, 30.0])
    assert applied == 45.0 * 3.5
    assert len(backend.moves) == 1
    assert backend.moves[0][0] == int(45.0 * 3.5)
    assert backend.moves[0][2] == "minimap_chevron_steering"


