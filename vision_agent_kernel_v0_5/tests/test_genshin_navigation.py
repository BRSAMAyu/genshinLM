from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from configs.profiles.genshin_profile_generator import (
    ResolutionScale,
    SUPPORTED_RESOLUTIONS,
    generate_all_profiles,
    generate_profile,
)
from navigation.genshin_dialog_handler import DialogState, GenshinDialogHandler
from navigation.genshin_navigator import GenshinNavigator


# ---------------------------------------------------------------------------
# Navigator fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def navigator() -> GenshinNavigator:
    return GenshinNavigator(knowledge_dir=Path("knowledge"))


@pytest.fixture
def dialog_handler() -> GenshinDialogHandler:
    return GenshinDialogHandler()


# ---------------------------------------------------------------------------
# Route planning
# ---------------------------------------------------------------------------

class TestPlanRoute:
    def test_plan_route_same_region(self, navigator: GenshinNavigator) -> None:
        """Walk route within same region (Mondstadt)."""
        route = navigator.plan_route("monstadt_city", "mondstadt_windrise")
        assert len(route) >= 2
        assert route[0] == "monstadt_city"
        assert route[-1] == "mondstadt_windrise"

    def test_plan_route_cross_region(self, navigator: GenshinNavigator) -> None:
        """Teleport + walk for different regions (Mondstadt -> Liyue)."""
        route = navigator.plan_route("monstadt_city", "liyue_harbor")
        assert len(route) >= 2
        assert route[0] == "monstadt_city"
        assert route[-1] == "liyue_harbor"

    def test_plan_route_same_waypoint(self, navigator: GenshinNavigator) -> None:
        """Same start and end returns single-element list."""
        route = navigator.plan_route("monstadt_city", "monstadt_city")
        assert route == ["monstadt_city"]

    def test_plan_route_long_cross_region(self, navigator: GenshinNavigator) -> None:
        """Long cross-region route: Mondstadt -> Natlan."""
        route = navigator.plan_route("monstadt_city", "natlan_stadium")
        assert len(route) >= 2
        assert route[0] == "monstadt_city"
        assert route[-1] == "natlan_stadium"


# ---------------------------------------------------------------------------
# Movement computation
# ---------------------------------------------------------------------------

class TestComputeMovement:
    def test_compute_movement_forward(self, navigator: GenshinNavigator) -> None:
        """0 degrees -> forward 'w'."""
        keys, duration = navigator.compute_movement(0.0)
        assert keys == "w"
        assert duration > 0

    def test_compute_movement_right(self, navigator: GenshinNavigator) -> None:
        """90 degrees -> right 'd'."""
        keys, duration = navigator.compute_movement(90.0)
        assert keys == "d"

    def test_compute_movement_diagonal(self, navigator: GenshinNavigator) -> None:
        """45 degrees -> diagonal 'wd'."""
        keys, duration = navigator.compute_movement(45.0)
        assert keys == "wd"

    def test_compute_movement_backward(self, navigator: GenshinNavigator) -> None:
        """180 degrees -> backward 's'."""
        keys, _ = navigator.compute_movement(180.0)
        assert keys == "s"

    def test_compute_movement_left(self, navigator: GenshinNavigator) -> None:
        """270 degrees -> left 'a'."""
        keys, _ = navigator.compute_movement(270.0)
        assert keys == "a"


# ---------------------------------------------------------------------------
# Teleport sequence
# ---------------------------------------------------------------------------

class TestTeleportSequence:
    def test_teleport_sequence_steps(self, navigator: GenshinNavigator) -> None:
        """Teleport sequence has correct step count (5 actions)."""
        steps = navigator.execute_teleport_sequence()
        assert len(steps) == 5
        assert steps[0]["input"] == "press_key"
        assert steps[0]["key"] == "m"

    def test_teleport_sequence_has_wait(self, navigator: GenshinNavigator) -> None:
        """Teleport sequence ends with a wait for world_hud."""
        steps = navigator.execute_teleport_sequence()
        last = steps[-1]
        assert "wait_screen" in last["input"]
        assert last["screen"] == "world_hud"


class TestTeleportSequenceUIFlow:
    """Tests for TeleportSequence UIFlow-based execution."""

    def test_instantiate_with_ui_flow_executor(self) -> None:
        from navigation.teleport_sequence import TeleportSequence
        from interaction.ui_flow_engine import UIFlowExecutor
        from core.state_bus import StateBus
        from execution.console_backend import ConsoleInputBackend
        from execution.input_worker import InputWorker

        bus = StateBus()
        backend = ConsoleInputBackend()
        worker = InputWorker(backend=backend, state_bus=bus)
        executor = UIFlowExecutor(state_bus=bus, input_worker=worker)

        seq = TeleportSequence(ui_flow_executor=executor)
        assert seq._ui_flow_executor is executor
        assert seq._executor is None

    def test_instantiate_with_raw_executor(self) -> None:
        from navigation.teleport_sequence import TeleportSequence

        seq = TeleportSequence(executor=None, classifier=None)
        assert seq._ui_flow_executor is None
        assert seq._executor is None

    def test_teleport_no_executor_returns_false(self) -> None:
        from navigation.teleport_sequence import TeleportSequence

        seq = TeleportSequence()
        result = seq.teleport_to_waypoint("mondstadt")
        assert result is False


# ---------------------------------------------------------------------------
# Dialog handling
# ---------------------------------------------------------------------------

class TestDialogDetection:
    def test_dialog_detect_active(self, dialog_handler: GenshinDialogHandler) -> None:
        """Dialog state detected when screen_state is 'dialog'."""
        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        state = dialog_handler.detect_dialog(frame, "dialog")
        assert state.active is True

    def test_dialog_detect_not_active(self, dialog_handler: GenshinDialogHandler) -> None:
        """Dialog not active when screen_state is not 'dialog'."""
        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        state = dialog_handler.detect_dialog(frame, "world_hud")
        assert state.active is False
        assert state.choice_count == 0


class TestDialogActions:
    def test_dialog_advance_click(self, dialog_handler: GenshinDialogHandler) -> None:
        """Advance generates click action with cooldown."""
        action = dialog_handler.advance_dialog()
        assert action["input"] == "click_at"
        assert "cooldown_ms" in action
        assert action["cooldown_ms"] == 500

    def test_dialog_select_choice(self, dialog_handler: GenshinDialogHandler) -> None:
        """Choice selection generates correct input."""
        action = dialog_handler.select_choice(2)
        assert action["input"] == "click_at"
        assert action["choice_index"] == 2

    def test_dialog_select_choice_first(self, dialog_handler: GenshinDialogHandler) -> None:
        """Selecting choice 0 produces correct target."""
        action = dialog_handler.select_choice(0)
        assert action["target"] == "dialog_choice_0"


class TestDialogEnd:
    def test_detect_dialog_end_transition(self, dialog_handler: GenshinDialogHandler) -> None:
        """Dialog end detected when transitioning from dialog state."""
        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        assert dialog_handler.detect_dialog_end(frame, "dialog") is True

    def test_detect_dialog_not_ended(self, dialog_handler: GenshinDialogHandler) -> None:
        """No dialog end when not previously in dialog."""
        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        assert dialog_handler.detect_dialog_end(frame, "world_hud") is False


# ---------------------------------------------------------------------------
# Profile generator
# ---------------------------------------------------------------------------

class TestProfileGenerator:
    def test_profile_generator_1280x720(self) -> None:
        """ROI offsets scaled correctly for 720p."""
        res = ResolutionScale(1280, 720, 0.667)
        profile = generate_profile(res)

        assert profile["profile_id"] == "genshin_1280x720"
        assert profile["source_resolution"] == [1280, 720]

        minimap = profile["rois"]["minimap"]
        assert minimap["offset_x_px"] == 13  # 20 * 0.667 rounded
        assert minimap["offset_y_px"] == 13
        assert minimap["width_px"] == 133  # 200 * 0.667 rounded
        assert minimap["height_px"] == 133

    def test_profile_generator_2560x1440(self) -> None:
        """ROI offsets scaled correctly for 1440p."""
        res = ResolutionScale(2560, 1440, 1.333)
        profile = generate_profile(res)

        assert profile["profile_id"] == "genshin_2560x1440"
        assert profile["source_resolution"] == [2560, 1440]

        minimap = profile["rois"]["minimap"]
        assert minimap["offset_x_px"] == 27  # 20 * (2560/1920) rounded
        assert minimap["offset_y_px"] == 27
        assert minimap["width_px"] == 267  # 200 * 1.333 rounded
        assert minimap["height_px"] == 267

    def test_profile_generator_relative_rois_unchanged(self) -> None:
        """Relative ROIs (main_view) should not be scaled."""
        res = ResolutionScale(1280, 720, 0.667)
        profile = generate_profile(res)

        main_view = profile["rois"]["main_view"]
        assert main_view["mode"] == "relative"
        assert main_view["x"] == 0.08
        assert main_view["y"] == 0.06
        assert main_view["w"] == 0.84
        assert main_view["h"] == 0.76

    def test_profile_generator_range_offsets_scaled(self) -> None:
        """Range-based offset_x_px lists are scaled correctly."""
        res = ResolutionScale(1280, 720, 0.667)
        profile = generate_profile(res)

        enemy_hp = profile["rois"]["enemy_hp_bar"]
        assert enemy_hp["offset_x_px"] == [-133, 133]  # [-200, 200] * 0.667

    def test_generate_all_profiles_creates_files(self, tmp_path: Path) -> None:
        """generate_all_profiles creates JSON files for all non-reference resolutions."""
        paths = generate_all_profiles(tmp_path)
        assert len(paths) == len(SUPPORTED_RESOLUTIONS) - 1  # minus 1920x1080

        for p in paths:
            assert p.exists()
            data = json.loads(p.read_text(encoding="utf-8"))
            assert "profile_id" in data
            assert "rois" in data
