"""Tests for Paimon menu navigation flows (U-06 through U-12)."""
from __future__ import annotations

import pytest

from interaction.menu_flows import (
    ALL_MENU_FLOWS,
    MenuPage,
    build_battle_pass_claim_flow,
    build_battle_pass_open_flow,
    build_coop_enter_flow,
    build_coop_exit_flow,
    build_coop_open_flow,
    build_events_claim_reward_flow,
    build_events_navigate_flow,
    build_events_open_flow,
    build_handbook_open_flow,
    build_handbook_tab_flow,
    build_handbook_track_enemy_flow,
    build_party_config_flow,
    build_party_config_via_menu_flow,
    build_party_save_flow,
    build_return_to_world_flow,
    build_settings_audio_flow,
    build_settings_controls_flow,
    build_settings_graphics_flow,
    build_settings_open_flow,
    build_wish_open_flow,
    build_wish_select_banner_flow,
    build_wish_ten_pull_flow,
    get_menu_flow,
)
from interaction.ui_flow_engine import UIFlow


# ---------------------------------------------------------------------------
# U-06: Party Configuration
# ---------------------------------------------------------------------------
class TestPartyConfigFlows:
    def test_party_config_flow(self) -> None:
        flow = build_party_config_flow()
        assert flow.name == "MENU_PARTY_CONFIG"
        assert flow.precondition_state == "world_hud"
        assert any(s.key == "l" for s in flow.steps)

    def test_party_config_via_menu(self) -> None:
        flow = build_party_config_via_menu_flow()
        assert flow.name == "MENU_PARTY_VIA_MENU"
        assert any(s.key == "escape" for s in flow.steps)

    def test_party_save_flow(self) -> None:
        flow = build_party_save_flow()
        assert flow.name == "MENU_PARTY_SAVE"
        assert flow.precondition_state == "party_setup"

    def test_party_save_with_name(self) -> None:
        flow = build_party_save_flow(slot_name="test")
        assert len(flow.steps) == 3

    def test_party_save_no_name(self) -> None:
        flow = build_party_save_flow()
        assert len(flow.steps) == 2


# ---------------------------------------------------------------------------
# U-07: Wish System
# ---------------------------------------------------------------------------
class TestWishFlows:
    def test_wish_open(self) -> None:
        flow = build_wish_open_flow()
        assert flow.name == "MENU_WISH_OPEN"
        assert any(s.key == "f3" for s in flow.steps)

    def test_wish_ten_pull(self) -> None:
        flow = build_wish_ten_pull_flow()
        assert flow.name == "MENU_WISH_TEN_PULL"
        assert flow.precondition_state == "wish_screen"
        assert len(flow.steps) >= 4

    def test_wish_select_banner(self) -> None:
        flow = build_wish_select_banner_flow(0)
        assert flow.precondition_state == "wish_screen"
        assert len(flow.steps) == 1

    def test_wish_select_banner_invalid(self) -> None:
        with pytest.raises(ValueError):
            build_wish_select_banner_flow(5)
        with pytest.raises(ValueError):
            build_wish_select_banner_flow(-1)


# ---------------------------------------------------------------------------
# U-08: Adventurer's Handbook
# ---------------------------------------------------------------------------
class TestHandbookFlows:
    def test_handbook_open(self) -> None:
        flow = build_handbook_open_flow()
        assert flow.name == "MENU_HANDBOOK_OPEN"
        assert any(s.key == "f1" for s in flow.steps)

    def test_handbook_tabs(self) -> None:
        for i in range(6):
            flow = build_handbook_tab_flow(i)
            assert f"TAB_{i}" in flow.name
            assert flow.precondition_state == "adventurer_handbook"

    def test_handbook_tab_invalid(self) -> None:
        with pytest.raises(ValueError):
            build_handbook_tab_flow(6)
        with pytest.raises(ValueError):
            build_handbook_tab_flow(-1)

    def test_handbook_track_enemy(self) -> None:
        flow = build_handbook_track_enemy_flow()
        assert flow.precondition_state == "adventurer_handbook"
        assert len(flow.steps) == 2


# ---------------------------------------------------------------------------
# U-09: Battle Pass
# ---------------------------------------------------------------------------
class TestBattlePassFlows:
    def test_battle_pass_open(self) -> None:
        flow = build_battle_pass_open_flow()
        assert any(s.key == "f4" for s in flow.steps)

    def test_battle_pass_claim(self) -> None:
        flow = build_battle_pass_claim_flow()
        assert flow.precondition_state == "battle_pass"
        assert len(flow.steps) >= 2


# ---------------------------------------------------------------------------
# U-10: Events Panel
# ---------------------------------------------------------------------------
class TestEventsFlows:
    def test_events_open(self) -> None:
        flow = build_events_open_flow()
        assert any(s.key == "f5" for s in flow.steps)

    def test_events_navigate(self) -> None:
        flow = build_events_navigate_flow(0)
        assert flow.precondition_state == "events_panel"

    def test_events_navigate_clamped(self) -> None:
        flow = build_events_navigate_flow(10)
        assert flow.steps[0].ny is not None
        assert flow.steps[0].ny <= 0.80

    def test_events_navigate_negative(self) -> None:
        with pytest.raises(ValueError):
            build_events_navigate_flow(-1)

    def test_events_claim(self) -> None:
        flow = build_events_claim_reward_flow()
        assert flow.precondition_state == "events_panel"


# ---------------------------------------------------------------------------
# U-11: Co-op
# ---------------------------------------------------------------------------
class TestCoopFlows:
    def test_coop_open(self) -> None:
        flow = build_coop_open_flow()
        assert any(s.key == "f2" for s in flow.steps)

    def test_coop_enter(self) -> None:
        flow = build_coop_enter_flow()
        assert flow.precondition_state == "coop_screen"

    def test_coop_exit(self) -> None:
        flow = build_coop_exit_flow()
        assert flow.precondition_state == "coop_screen"


# ---------------------------------------------------------------------------
# U-12: Settings
# ---------------------------------------------------------------------------
class TestSettingsFlows:
    def test_settings_open(self) -> None:
        flow = build_settings_open_flow()
        assert any(s.key == "escape" for s in flow.steps)

    def test_settings_graphics(self) -> None:
        flow = build_settings_graphics_flow()
        assert flow.precondition_state == "settings_menu"

    def test_settings_controls(self) -> None:
        flow = build_settings_controls_flow()
        assert flow.precondition_state == "settings_menu"

    def test_settings_audio(self) -> None:
        flow = build_settings_audio_flow()
        assert flow.precondition_state == "settings_menu"


# ---------------------------------------------------------------------------
# Return to world
# ---------------------------------------------------------------------------
class TestReturnToWorld:
    def test_return_flow(self) -> None:
        flow = build_return_to_world_flow()
        assert flow.name == "MENU_RETURN_TO_WORLD"
        esc_count = sum(1 for s in flow.steps if s.key == "escape")
        assert esc_count == 3

    def test_custom_escape_count(self) -> None:
        flow = build_return_to_world_flow(max_escapes=5)
        esc_count = sum(1 for s in flow.steps if s.key == "escape")
        assert esc_count == 5


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
class TestFlowRegistry:
    def test_all_flows_populated(self) -> None:
        assert len(ALL_MENU_FLOWS) >= 20

    def test_get_menu_flow_found(self) -> None:
        flow = get_menu_flow("party_config")
        assert flow is not None
        assert isinstance(flow, UIFlow)

    def test_get_menu_flow_not_found(self) -> None:
        assert get_menu_flow("nonexistent") is None

    def test_all_flows_have_name(self) -> None:
        for name, flow in ALL_MENU_FLOWS.items():
            assert flow.name, f"Flow '{name}' has no name"

    def test_all_flows_have_steps(self) -> None:
        for name, flow in ALL_MENU_FLOWS.items():
            assert len(flow.steps) > 0, f"Flow '{name}' has no steps"
