"""Gap-fill integration tests (G1-G9) for the Genshin agent system.

Verifies the 9 execution gaps filled in commit be8e370:
  G1: OCR fail-safe
  G2: Mail system
  G3: Quest tracking real coords
  G4: DailyCommissionExecutor
  G5: 9 exploration UIFlows
  G6: Real combat key execution
  G7: WorldBoss + WaveDefense UIFlows
  G8: NpcShopInteractor
  G9: AbyssChamberExecutor
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pytest

from core.state_bus import StateBus
from execution.ui_flow_skill_adapter import UIFlowSkillAdapter
from interaction.npc_shop_interactor import NpcShopInteractor
from interaction.ui_flow_engine import (
    UIFlow,
    UIFlowExecutor,
    UIFlowTimeout,
    UIStep,
    verify_ocr_number,
    verify_screen_contains,
)
from interaction.ui_flows import ALL_FLOWS


# ---------------------------------------------------------------------------
# Shared mock infrastructure
# ---------------------------------------------------------------------------


class _Rect:
    left = 0
    top = 0
    width = 1920
    height = 1080


class _MockBackend:
    """Mock input backend that records all calls for assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def client_rect(self) -> _Rect:
        return _Rect()

    def click_at(self, x: int, y: int, reason: str = "") -> None:
        self.calls.append(("click_at", str(x), str(y), reason))

    def key_down(self, key: str, reason: str = "") -> None:
        self.calls.append(("key_down", key, reason))

    def key_up(self, key: str, reason: str = "") -> None:
        self.calls.append(("key_up", key, reason))

    def key_press(self, key: str, reason: str = "") -> None:
        self.calls.append(("key_press", key, reason))

    def left_click_down(self, reason: str = "") -> None:
        self.calls.append(("left_click_down", reason))

    def left_click_up(self, reason: str = "") -> None:
        self.calls.append(("left_click_up", reason))

    def mouse_scroll(self, delta: int = -1, reason: str = "") -> None:
        self.calls.append(("mouse_scroll", str(delta), reason))

    def action_intent(self, intent: str, reason: str = "") -> None:
        self.calls.append(("action_intent", intent, reason))

    def is_target_focused(self) -> bool:
        return True


class _MockWorker:
    """Mock InputWorker that delegates to _MockBackend."""

    def __init__(self, backend: _MockBackend) -> None:
        self.backend = backend
        self.is_alive = False

    def submit_lease(self, lease: Any) -> bool:
        for key, state in lease.key_states.items():
            if state == "DOWN":
                self.backend.key_down(key, reason=lease.reason)
            elif state == "UP":
                self.backend.key_up(key, reason=lease.reason)
        return True

    def start(self) -> None:
        self.is_alive = True


class _MockObjective:
    """Minimal mock for DailyCommissionObjective."""

    def __init__(
        self,
        objective_id: str = "test_obj_1",
        objective_type: str = "combat",
        target_label: str = "enemy_hilichurl",
        waypoint_id: str = "mondstadt_guild",
        puzzle_hint: str = "",
    ) -> None:
        self.objective_id = objective_id
        self.objective_type = objective_type
        self.target_label = target_label
        self.waypoint_id = waypoint_id
        self.puzzle_hint = puzzle_hint


class _MockUIAdapter:
    """Minimal mock UIFlowSkillAdapter for DailyCommissionExecutor / AbyssChamberExecutor."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None
    ) -> bool:
        self.calls.append((action, target, context or {}))
        return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def backend() -> _MockBackend:
    return _MockBackend()


@pytest.fixture()
def worker(backend: _MockBackend) -> _MockWorker:
    return _MockWorker(backend)


@pytest.fixture()
def adapter(worker: _MockWorker) -> UIFlowSkillAdapter:
    return UIFlowSkillAdapter(input_worker=worker)  # type: ignore[arg-type]


@pytest.fixture()
def bus() -> StateBus:
    return StateBus()


@pytest.fixture()
def mock_adapter() -> _MockUIAdapter:
    return _MockUIAdapter()


# ===================================================================
# G1: OCR Fail-Safe
# ===================================================================


class TestG1OcrFailSafe:
    """Verify OCR verification steps fail-safe instead of fail-open."""

    def test_verify_ocr_number_raises_when_no_claim_with_min(
        self, bus: StateBus, worker: _MockWorker
    ) -> None:
        """When no screen claim exists and ocr_expected_min is set, must raise."""
        executor = UIFlowExecutor(state_bus=bus, input_worker=worker)  # type: ignore[arg-type]
        flow = UIFlow(
            name="test_ocr_min",
            steps=(verify_ocr_number(expected_min=10, reason="check_level"),),
        )
        result = executor.execute(flow)
        assert result.status == "TIMEOUT", "Expected TIMEOUT when OCR min set but no claim"

    def test_verify_ocr_number_raises_when_no_claim_with_max(
        self, bus: StateBus, worker: _MockWorker
    ) -> None:
        """When no screen claim exists and ocr_expected_max is set, must raise."""
        executor = UIFlowExecutor(state_bus=bus, input_worker=worker)  # type: ignore[arg-type]
        flow = UIFlow(
            name="test_ocr_max",
            steps=(verify_ocr_number(expected_max=90, reason="check_level_cap"),),
        )
        result = executor.execute(flow)
        assert result.status == "TIMEOUT"

    def test_verify_ocr_number_passes_when_no_range_no_claim(
        self, bus: StateBus, worker: _MockWorker
    ) -> None:
        """When no screen claim and no min/max, step should pass (lenient)."""
        executor = UIFlowExecutor(state_bus=bus, input_worker=worker)  # type: ignore[arg-type]
        flow = UIFlow(
            name="test_ocr_lenient",
            steps=(verify_ocr_number(reason="optional_check"),),
        )
        result = executor.execute(flow)
        assert result.status == "SUCCESS"

    def test_verify_screen_contains_raises_when_no_claim(
        self, bus: StateBus, worker: _MockWorker
    ) -> None:
        """When expected_text set but no screen claim, must raise."""
        executor = UIFlowExecutor(state_bus=bus, input_worker=worker)  # type: ignore[arg-type]
        flow = UIFlow(
            name="test_screen_verify",
            steps=(verify_screen_contains("Level Up", reason="check_button"),),
        )
        result = executor.execute(flow)
        assert result.status == "TIMEOUT"

    def test_verify_screen_contains_raises_when_text_not_found(
        self, bus: StateBus, worker: _MockWorker
    ) -> None:
        """When expected_text not in OCR results, must raise."""
        from planning.screen_state_claim import ScreenStateClaim

        claim = ScreenStateClaim(
            game_id="genshin",
            screen_state="menu",
            confidence=0.9,
            source="classifier",
            raw_ocr_texts=("Inventory", " backpack"),
        )
        bus.screen_claim.put(claim)

        executor = UIFlowExecutor(state_bus=bus, input_worker=worker)  # type: ignore[arg-type]
        flow = UIFlow(
            name="test_missing_text",
            steps=(verify_screen_contains("Level Up", reason="check_level_btn"),),
        )
        result = executor.execute(flow)
        assert result.status == "TIMEOUT"


# ===================================================================
# G2: Mail System
# ===================================================================


class TestG2MailSystem:
    """Verify mail UIFlows exist and adapter routes correctly."""

    def test_open_mail_flow_exists(self) -> None:
        assert "open_mail" in ALL_FLOWS
        flow = ALL_FLOWS["open_mail"]
        assert flow.name == "open_mail"
        assert len(flow.steps) > 0

    def test_mail_claim_all_flow_exists(self) -> None:
        assert "mail_claim_all" in ALL_FLOWS
        flow = ALL_FLOWS["mail_claim_all"]
        assert flow.name == "mail_claim_all"
        assert len(flow.steps) > 0

    def test_mail_claim_attachment_flow_exists(self) -> None:
        assert "mail_claim_attachment" in ALL_FLOWS

    def test_handle_mail_routes_open(self, adapter: UIFlowSkillAdapter, backend: _MockBackend) -> None:
        """_handle_mail with open_mail action routes to open_mail flow."""
        adapter._handle_mail("", {"semantic_action": "open_mail"})
        keys = [c for c in backend.calls if c[0] in ("key_down", "key_up")]
        assert len(keys) > 0, "Expected key presses for opening mail menu"

    def test_handle_mail_routes_claim_all(self, adapter: UIFlowSkillAdapter, backend: _MockBackend) -> None:
        """_handle_mail with mail_claim_all routes to mail_claim_all flow."""
        adapter._handle_mail("", {"semantic_action": "mail_claim_all"})
        # mail_claim_all should produce clicks for claim button
        clicks = [c for c in backend.calls if c[0] == "click_at"]
        assert len(clicks) > 0, "Expected click_at calls for claim all"

    def test_handle_mail_default_claims_attachment(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        """_handle_mail with unknown action falls through to attachment claim."""
        adapter._handle_mail("", {"semantic_action": "unknown_action"})
        # Should execute mail_claim_attachment flow (has click + escape)
        assert len(backend.calls) > 0

    def test_mail_aliases_in_default_aliases(self) -> None:
        """Mail aliases are registered in _DEFAULT_ALIASES."""
        aliases = UIFlowSkillAdapter._DEFAULT_ALIASES
        assert aliases.get("open_mail") == "open_mail"
        assert aliases.get("claim_mail") == "mail_claim_all"
        assert aliases.get("mail_claim_all") == "mail_claim_all"


# ===================================================================
# G3: Quest Tracking Real Coords
# ===================================================================


class TestG3QuestTracking:
    """Verify quest tracking uses real UIFlow, not action_intent stub."""

    def test_quest_select_and_track_flow_exists(self) -> None:
        assert "quest_select_and_track" in ALL_FLOWS
        flow = ALL_FLOWS["quest_select_and_track"]
        assert flow.name == "quest_select_and_track"
        # Must contain J key press + click + Esc
        step_types = [s.type for s in flow.steps]
        assert "press_key" in step_types, "Expected press_key for J key"

    def test_quest_select_and_track_has_clicks(self) -> None:
        flow = ALL_FLOWS["quest_select_and_track"]
        click_steps = [s for s in flow.steps if s.type == "click_at"]
        assert len(click_steps) >= 2, "Expected click_at for quest select + track button"

    def test_handle_quest_track_sends_j_key(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        """_handle_quest_track executes QUEST_SELECT_AND_TRACK which presses J."""
        adapter._handle_quest_track("", {"semantic_action": "quest_track"})
        keys = [c for c in backend.calls if c[0] in ("key_down", "key_up")]
        j_keys = [c for c in keys if c[1] == "j"]
        assert len(j_keys) > 0, "Expected J key for quest log"

    def test_handle_quest_track_has_clicks(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        """_handle_quest_track should produce click_at calls, not just action_intent."""
        adapter._handle_quest_track("", {"semantic_action": "quest_track"})
        clicks = [c for c in backend.calls if c[0] == "click_at"]
        assert len(clicks) > 0, "quest_track should click quest list + track button"

    def test_handle_quest_track_no_action_intent_stub(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        """_handle_quest_track should NOT use action_intent stub anymore."""
        adapter._handle_quest_track("", {"semantic_action": "quest_track"})
        quest_action_intent = [
            c for c in backend.calls if c[0] == "action_intent" and "quest:track" in c[1]
        ]
        assert len(quest_action_intent) == 0, "quest_track should use real UIFlow, not action_intent stub"


# ===================================================================
# G4: DailyCommissionExecutor
# ===================================================================


class TestG4DailyCommission:
    """Verify DailyCommissionExecutor instantiation and commission dispatch."""

    def test_instantiation(self, mock_adapter: _MockUIAdapter) -> None:
        from agent_kernel.daily_commission_executor import DailyCommissionExecutor

        executor = DailyCommissionExecutor(ui_adapter=mock_adapter)
        assert executor._ui is mock_adapter

    def test_accept_commissions_calls_interact(self, mock_adapter: _MockUIAdapter) -> None:
        from agent_kernel.daily_commission_executor import DailyCommissionExecutor

        executor = DailyCommissionExecutor(ui_adapter=mock_adapter)
        result = executor.accept_commissions()
        assert result is True
        # Should call interact + select_option + skip_cutscene
        actions = [c[0] for c in mock_adapter.calls]
        assert "interact" in actions
        assert "select_option" in actions

    def test_execute_commission_combat(self, mock_adapter: _MockUIAdapter) -> None:
        from agent_kernel.daily_commission_executor import DailyCommissionExecutor

        executor = DailyCommissionExecutor(ui_adapter=mock_adapter)
        obj = _MockObjective(objective_type="combat")
        result = executor.execute_commission(obj)
        assert result.success
        assert result.commission_type == "combat"

    def test_execute_commission_dialogue(self, mock_adapter: _MockUIAdapter) -> None:
        from agent_kernel.daily_commission_executor import DailyCommissionExecutor

        executor = DailyCommissionExecutor(ui_adapter=mock_adapter)
        obj = _MockObjective(objective_type="dialogue")
        result = executor.execute_commission(obj)
        assert result.success
        assert result.commission_type == "dialogue"
        # Dialogue commission should use quest_dialog semantic
        actions = [c[0] for c in mock_adapter.calls]
        assert "quest_dialog" in actions

    def test_execute_commission_puzzle(self, mock_adapter: _MockUIAdapter) -> None:
        from agent_kernel.daily_commission_executor import DailyCommissionExecutor

        executor = DailyCommissionExecutor(ui_adapter=mock_adapter)
        obj = _MockObjective(objective_type="puzzle", puzzle_hint="torch_sequence")
        result = executor.execute_commission(obj)
        assert result.success
        assert result.commission_type == "puzzle"

    def test_execute_commission_interaction(self, mock_adapter: _MockUIAdapter) -> None:
        from agent_kernel.daily_commission_executor import DailyCommissionExecutor

        executor = DailyCommissionExecutor(ui_adapter=mock_adapter)
        obj = _MockObjective(objective_type="interaction", target_label="npc_flora")
        result = executor.execute_commission(obj)
        assert result.success
        assert result.commission_type == "interaction"
        # Interaction commission should navigate + interact
        actions = [c[0] for c in mock_adapter.calls]
        assert "navigate_walk" in actions
        assert "interact" in actions

    def test_claim_rewards(self, mock_adapter: _MockUIAdapter) -> None:
        from agent_kernel.daily_commission_executor import DailyCommissionExecutor

        executor = DailyCommissionExecutor(ui_adapter=mock_adapter)
        result = executor.claim_rewards()
        assert result is True
        actions = [c[0] for c in mock_adapter.calls]
        assert "interact" in actions
        assert "confirm" in actions

    def test_commission_result_dataclass(self) -> None:
        from agent_kernel.daily_commission_executor import CommissionResult

        r = CommissionResult(
            objective_id="c1",
            commission_type="combat",
            success=True,
            duration_sec=12.5,
        )
        assert r.objective_id == "c1"
        assert r.success
        assert r.error == ""

    def test_commission_type_map(self) -> None:
        from agent_kernel.daily_commission_executor import _COMMISSION_TYPE_MAP

        assert _COMMISSION_TYPE_MAP["combat"] == "combat_basic"
        assert _COMMISSION_TYPE_MAP["dialogue"] == "quest_dialog"
        assert _COMMISSION_TYPE_MAP["puzzle"] == "explore_puzzle"
        assert _COMMISSION_TYPE_MAP["interaction"] == "interact"


# ===================================================================
# G5: Exploration UIFlows (9)
# ===================================================================

_EXPLORE_FLOW_NAMES = [
    "explore_statue_activate",
    "explore_open_chest",
    "explore_element_monument",
    "explore_torch_puzzle",
    "explore_pressure_plate",
    "explore_timed_challenge",
    "explore_oculus_collect",
    "explore_withering_zone",
    "explore_underwater",
]


class TestG5ExplorationFlows:
    """Verify all 9 exploration UIFlows exist and contain F-key interaction."""

    @pytest.mark.parametrize("flow_name", _EXPLORE_FLOW_NAMES)
    def test_explore_flow_exists(self, flow_name: str) -> None:
        assert flow_name in ALL_FLOWS, f"Flow {flow_name} missing from ALL_FLOWS"

    @pytest.mark.parametrize("flow_name", _EXPLORE_FLOW_NAMES)
    def test_explore_flow_has_steps(self, flow_name: str) -> None:
        flow = ALL_FLOWS[flow_name]
        assert len(flow.steps) > 0, f"{flow_name} has no steps"

    @pytest.mark.parametrize("flow_name", _EXPLORE_FLOW_NAMES)
    def test_explore_flow_starts_with_press_key(self, flow_name: str) -> None:
        """All explore flows should start with an F-key press (interact)."""
        flow = ALL_FLOWS[flow_name]
        assert flow.steps[0].type == "press_key", f"{flow_name} should start with press_key"
        assert flow.steps[0].key == "f", f"{flow_name} should start with F key press"

    def test_explore_handler_still_routes_interact_actions(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        """_handle_explore still routes interact-type actions with F key."""
        adapter.execute_semantic("explore_statue", "", {"semantic_action": "explore_statue"})
        keys = [c for c in backend.calls if c[0] in ("key_down", "key_up")]
        f_keys = [c for c in keys if c[1] == "f"]
        assert len(f_keys) > 0, "explore_statue should send F key"

    def test_explore_handler_routes_non_interact_via_action_intent(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        """Non-interact explore actions (puzzle, timed, withering, underwater) use action_intent."""
        adapter.execute_semantic("explore_puzzle", "", {"semantic_action": "explore_puzzle"})
        intents = [c for c in backend.calls if c[0] == "action_intent" and "explore" in c[1]]
        assert len(intents) > 0, "explore_puzzle should use action_intent"


# ===================================================================
# G6: Combat Real Keys
# ===================================================================


class TestG6CombatRealKeys:
    """Verify combat handler maps semantic actions to real key presses."""

    def test_combat_key_sends_down_up(self, adapter: UIFlowSkillAdapter, backend: _MockBackend) -> None:
        """_combat_key sends key_down then key_up."""
        result = adapter._combat_key("e", "test_skill")
        assert result is True
        assert ("key_down", "e", "test_skill") in backend.calls
        assert ("key_up", "e", "test_skill_done") in backend.calls

    def test_combat_skill_e_sends_e_key(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        adapter._handle_combat("", {"semantic_action": "cast_skill_e"})
        assert any(c[0] == "key_down" and c[1] == "e" for c in backend.calls)

    def test_combat_burst_sends_q_key(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        adapter._handle_combat("", {"semantic_action": "cast_burst_q"})
        assert any(c[0] == "key_down" and c[1] == "q" for c in backend.calls)

    def test_combat_use_burst_sends_q_key(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        adapter._handle_combat("", {"semantic_action": "use_burst"})
        assert any(c[0] == "key_down" and c[1] == "q" for c in backend.calls)

    def test_combat_jump_sends_space(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        adapter._handle_combat("", {"semantic_action": "jump"})
        assert any(c[0] == "key_down" and c[1] == "space" for c in backend.calls)

    def test_combat_lock_target_sends_tab(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        adapter._handle_combat("", {"semantic_action": "lock_target"})
        assert any(c[0] == "key_down" and c[1] == "tab" for c in backend.calls)

    def test_combat_switch_char_sends_number(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        adapter._handle_combat("slot_2", {"semantic_action": "switch_char"})
        assert any(c[0] == "key_down" and c[1] == "2" for c in backend.calls)

    def test_combat_fallback_uses_action_intent(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        """Unknown combat action falls back to action_intent."""
        adapter._handle_combat("", {"semantic_action": "combat_basic"})
        # ConsoleInputBackend lacks left_click_down, so attack path fails,
        # then falls through to action_intent at end of _handle_combat
        intents = [c for c in backend.calls if c[0] == "action_intent"]
        assert len(intents) > 0, "Unknown combat action should use action_intent fallback"

    def test_explore_interact_actions_frozenset(self) -> None:
        """_EXPLORE_INTERACT_ACTIONS contains the expected set."""
        expected = frozenset({
            "explore_waypoint", "explore_statue", "explore_chest", "explore_oculus",
            "explore_activate_waypoint", "explore_activate_statue",
            "explore_open_chest", "explore_collect_oculus",
        })
        assert UIFlowSkillAdapter._EXPLORE_INTERACT_ACTIONS == expected


# ===================================================================
# G7: WorldBoss + WaveDefense
# ===================================================================


class TestG7WorldBossWaveDefense:
    """Verify WORLD_BOSS_ROTATION_CLAIM and WAVE_DEFENSE_START flows."""

    def test_world_boss_rotation_claim_exists(self) -> None:
        assert "world_boss_rotation_claim" in ALL_FLOWS

    def test_wave_defense_start_exists(self) -> None:
        assert "wave_defense_start" in ALL_FLOWS

    def test_world_boss_claim_has_confirm_step(self) -> None:
        flow = ALL_FLOWS["world_boss_rotation_claim"]
        step_types = [s.type for s in flow.steps]
        assert "confirm" in step_types, "world_boss_rotation_claim should have confirm step"

    def test_wave_defense_has_wait_loading(self) -> None:
        flow = ALL_FLOWS["wave_defense_start"]
        step_types = [s.type for s in flow.steps]
        assert "wait_loading" in step_types, "wave_defense_start should wait for loading"

    def test_world_boss_claim_executes(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        adapter.execute_semantic("world_boss_rotation_claim", "", {})
        # Should have key_down/key_up for F + escape, and click_at for confirm
        keys = [c for c in backend.calls if c[0] in ("key_down", "key_up")]
        assert len(keys) > 0

    def test_wave_defense_executes(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        adapter.execute_semantic("wave_defense_start", "", {})
        # Should have F key and click_at for start button
        keys = [c for c in backend.calls if c[0] in ("key_down", "key_up")]
        assert len(keys) > 0


# ===================================================================
# G8: NpcShopInteractor
# ===================================================================


class TestG8NpcShop:
    """Verify NpcShopInteractor grid click and adapter buy-specific handler."""

    def test_select_item_by_index_clicks_correct_position(self, backend: _MockBackend) -> None:
        bus = StateBus()
        shop = NpcShopInteractor(backend=backend, state_bus=bus)
        shop.select_item_by_index(0)
        # Index 0 → (0.35, 0.35) → (672, 378)
        assert len(backend.calls) == 1
        assert backend.calls[0][0] == "click_at"
        assert backend.calls[0][1] == str(int(0.35 * 1920))
        assert backend.calls[0][2] == str(int(0.35 * 1080))

    def test_select_item_by_index_out_of_range(self, backend: _MockBackend) -> None:
        bus = StateBus()
        shop = NpcShopInteractor(backend=backend, state_bus=bus)
        assert shop.select_item_by_index(-1) is False
        assert shop.select_item_by_index(8) is False
        assert len(backend.calls) == 0

    def test_buy_item_by_index_selects_then_buys(self, backend: _MockBackend) -> None:
        bus = StateBus()
        shop = NpcShopInteractor(backend=backend, state_bus=bus)
        result = shop.buy_item_by_index(0)
        assert result is True
        # select_item clicks once, buy_item clicks twice (buy + confirm)
        clicks = [c for c in backend.calls if c[0] == "click_at"]
        assert len(clicks) >= 3

    def test_handle_npc_shop_buy_specific_parses_index(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        """_handle_npc_shop_buy_specific parses 'index:2' target correctly."""
        # Need shop_interactor initialized with a click_at capable backend
        bus = StateBus()
        adapter._shop_interactor = NpcShopInteractor(backend=backend, state_bus=bus)
        result = adapter._handle_npc_shop_buy_specific("index:2", {})
        assert result is True
        # Index 2 → (0.35, 0.50) → (672, 540)
        clicks = [c for c in backend.calls if c[0] == "click_at"]
        assert len(clicks) >= 1

    def test_handle_npc_shop_buy_specific_invalid_index(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        """Invalid index format returns False (logs warning)."""
        result = adapter._handle_npc_shop_buy_specific("index:abc", {})
        # ValueError in int() causes it to log warning and return False
        assert result is False

    def test_handle_npc_shop_buy_specific_non_index(
        self, adapter: UIFlowSkillAdapter, backend: _MockBackend
    ) -> None:
        """Non-index target falls back to npc_shop_buy_item flow."""
        result = adapter._handle_npc_shop_buy_specific("name:Weapon_Material", {})
        # Falls through to execute_flow_as_semantic("npc_shop_buy_item")
        assert result is True

    def test_grid_slots_count(self) -> None:
        """NpcShopInteractor has exactly 8 grid slots (4 rows x 2 cols)."""
        assert len(NpcShopInteractor._GRID_SLOTS) == 8


# ===================================================================
# G9: AbyssChamberExecutor
# ===================================================================


class TestG9AbyssChamber:
    """Verify AbyssChamberExecutor instantiation, chamber and floor execution."""

    def test_instantiation(self, mock_adapter: _MockUIAdapter) -> None:
        from agent_kernel.abyss_chamber_executor import AbyssChamberExecutor

        executor = AbyssChamberExecutor(ui_adapter=mock_adapter)
        assert executor._ui is mock_adapter
        assert executor._current_floor == 9

    def test_chamber_result_dataclass(self) -> None:
        from agent_kernel.abyss_chamber_executor import ChamberResult

        r = ChamberResult(floor=9, chamber=1, success=True, stars_earned=3, duration_sec=45.0)
        assert r.floor == 9
        assert r.chamber == 1
        assert r.success
        assert r.stars_earned == 3
        assert r.error == ""

    def test_execute_chamber_returns_chamber_result(self, mock_adapter: _MockUIAdapter) -> None:
        from agent_kernel.abyss_chamber_executor import AbyssChamberExecutor, ChamberResult

        executor = AbyssChamberExecutor(ui_adapter=mock_adapter)
        result = executor.execute_chamber(floor=9, chamber=1, max_duration_sec=2.0)
        assert isinstance(result, ChamberResult)
        assert result.floor == 9
        assert result.chamber == 1
        assert result.success
        assert result.stars_earned == 3

    def test_execute_floor_returns_3_tuple(self, mock_adapter: _MockUIAdapter) -> None:
        from agent_kernel.abyss_chamber_executor import AbyssChamberExecutor, ChamberResult

        executor = AbyssChamberExecutor(ui_adapter=mock_adapter)
        results = executor.execute_floor(floor=9)
        assert isinstance(results, tuple)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, ChamberResult)
            assert r.floor == 9

    def test_execute_chamber_calls_semantics(self, mock_adapter: _MockUIAdapter) -> None:
        from agent_kernel.abyss_chamber_executor import AbyssChamberExecutor

        executor = AbyssChamberExecutor(ui_adapter=mock_adapter)
        executor.execute_chamber(floor=11, chamber=2, max_duration_sec=1.0)
        actions = [c[0] for c in mock_adapter.calls]
        assert "combat_abyss" in actions
        assert "claim_reward" in actions

    def test_execute_chamber_on_exception_returns_failure(self) -> None:
        from agent_kernel.abyss_chamber_executor import AbyssChamberExecutor, ChamberResult

        failing_adapter = _MockUIAdapter()
        failing_adapter.execute_semantic = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[assignment]
        executor = AbyssChamberExecutor(ui_adapter=failing_adapter)
        result = executor.execute_chamber(floor=12, chamber=3, max_duration_sec=1.0)
        assert isinstance(result, ChamberResult)
        assert not result.success
        assert "boom" in result.error
