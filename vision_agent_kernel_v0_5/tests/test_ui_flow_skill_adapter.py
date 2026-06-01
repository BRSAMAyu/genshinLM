from __future__ import annotations

from typing import Any

from core.types import InputLease
from execution.ui_flow_skill_adapter import UIFlowSkillAdapter


class _Rect:
    left = 0
    top = 0
    width = 1920
    height = 1080


class _Backend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def client_rect(self) -> _Rect:
        return _Rect()

    def click_at(self, x: int, y: int, reason: str = "") -> None:
        self.calls.append(("click_at", x, y, reason))

    def key_down(self, key: str, reason: str = "") -> None:
        self.calls.append(("key_down", key, reason))

    def key_up(self, key: str, reason: str = "") -> None:
        self.calls.append(("key_up", key, reason))

    def mouse_scroll(self, delta: int = -1, reason: str = "") -> None:
        self.calls.append(("mouse_scroll", delta, reason))

    def action_intent(self, intent: str, reason: str = "") -> None:
        self.calls.append(("action_intent", intent, reason))

    def is_target_focused(self) -> bool:
        return True


class _Worker:
    def __init__(self, backend: _Backend) -> None:
        self.backend = backend
        self.leases: list[InputLease] = []

    def submit_lease(self, lease: InputLease) -> bool:
        self.leases.append(lease)
        for key, state in lease.key_states.items():
            if state == "DOWN":
                self.backend.key_down(key, reason=lease.reason)
            elif state == "UP":
                self.backend.key_up(key, reason=lease.reason)
        return True


def test_adapter_routes_known_flow_name() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("character_level_up")
    assert adapter.execute_semantic("character_level_up", "", {})

    assert any(call[0] == "click_at" for call in backend.calls)


def test_adapter_routes_semantic_alias_to_flow() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("level_up_character")
    assert adapter.execute_semantic("level_up_character", "", {})

    assert any(call[0] == "click_at" for call in backend.calls)


def test_adapter_handles_primitive_action_without_real_input() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.execute_semantic("navigate_walk", "north", {})

    assert ("action_intent", "navigate_walk:north", "semantic_action_intent") in backend.calls


def test_adapter_rejects_unknown_semantic_action() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert not adapter.can_handle("not_a_real_action")
    assert not adapter.execute_semantic("not_a_real_action", "", {})


def test_character_slot_parsing() -> None:
    adapter = UIFlowSkillAdapter()
    assert adapter._parse_character_slot("slot_1") == 1
    assert adapter._parse_character_slot("slot:2") == 2
    assert adapter._parse_character_slot("slot3") == 3
    assert adapter._parse_character_slot("4") == 4
    assert adapter._parse_character_slot("hu_tao") is None
    assert adapter._parse_character_slot("") is None
    assert adapter._parse_character_slot("slot_5") is None


def test_adapter_character_select_with_slot_target() -> None:
    """When target='slot_2' and action is character-scoped, pre-select slot."""
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    ok = adapter.execute_semantic("character_level_up_full", "slot_2", {})
    assert ok

    # Should have at least 2 click_at calls: one for slot selection, rest for level up
    click_calls = [c for c in backend.calls if c[0] == "click_at"]
    assert len(click_calls) >= 2, f"expected >=2 clicks, got {len(click_calls)}"


def test_adapter_explore_waypoint_sends_f_key() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("explore_waypoint")
    assert adapter.execute_semantic("explore_waypoint", "", {})

    keys = [c for c in backend.calls if c[0] in ("key_down", "key_up")]
    assert any("f" in c for c in keys), "expected F-key interact for waypoint"


def test_adapter_explore_chest_sends_f_key() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("explore_chest")
    assert adapter.execute_semantic("explore_chest", "", {})

    keys = [c for c in backend.calls if c[0] in ("key_down", "key_up")]
    assert any("f" in c for c in keys), "expected F-key interact for chest"


def test_adapter_explore_oculus_sends_f_key() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("explore_oculus")
    assert adapter.execute_semantic("explore_oculus", "", {})

    keys = [c for c in backend.calls if c[0] in ("key_down", "key_up")]
    assert any("f" in c for c in keys), "expected F-key interact for oculus"


def test_adapter_explore_puzzle_uses_action_intent() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("explore_puzzle")
    assert adapter.execute_semantic("explore_puzzle", "", {})

    assert any(c[0] == "action_intent" and "explore" in c[1] for c in backend.calls)


def test_adapter_explore_statue_sends_f_key() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("explore_statue")
    assert adapter.execute_semantic("explore_statue", "", {})

    keys = [c for c in backend.calls if c[0] in ("key_down", "key_up")]
    assert any("f" in c for c in keys), "expected F-key interact for statue"


def test_adapter_explore_underwater_uses_action_intent() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("explore_underwater")
    assert adapter.execute_semantic("explore_underwater", "", {})

    assert any(c[0] == "action_intent" and "explore" in c[1] for c in backend.calls)


def test_adapter_explore_skill_id_routes_to_handler() -> None:
    """Verify skill_ids from ClosedLoopRunner route correctly via alias fallback."""
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    # These are the skill_ids that ClosedLoopRunner passes
    assert adapter.execute_semantic("explore_activate_waypoint", "", {})
    assert adapter.execute_semantic("explore_open_chest", "", {})
    assert adapter.execute_semantic("explore_collect_oculus", "", {})
    assert adapter.execute_semantic("explore_underwater", "", {})


def test_adapter_quest_dialog_sends_f_key() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("quest_dialog")
    assert adapter.execute_semantic("quest_dialog", "", {})

    keys = [c for c in backend.calls if c[0] in ("key_down", "key_up")]
    assert any("f" in c for c in keys), "expected F-key for quest dialog"


def test_adapter_quest_skip_cutscene_sends_escape() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("quest_skip_cutscene")
    assert adapter.execute_semantic("quest_skip_cutscene", "", {})

    keys = [c for c in backend.calls if c[0] in ("key_down", "key_up")]
    assert any("escape" in c for c in keys), "expected Escape for cutscene skip"


def test_adapter_quest_track_uses_action_intent() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("quest_track")
    assert adapter.execute_semantic("quest_track", "", {})

    assert any(c[0] == "action_intent" and "quest" in c[1] for c in backend.calls)


def test_adapter_quest_archon_uses_action_intent() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("quest_archon")
    assert adapter.execute_semantic("quest_archon", "", {})

    assert any(c[0] == "action_intent" and "quest" in c[1] for c in backend.calls)


def test_adapter_quest_daily_uses_action_intent() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("quest_daily")
    assert adapter.execute_semantic("quest_daily", "", {})

    assert any(c[0] == "action_intent" and "quest" in c[1] for c in backend.calls)


def test_adapter_daily_domain_uses_action_intent() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("daily_domain")
    assert adapter.execute_semantic("daily_domain", "", {})

    assert any(c[0] == "action_intent" and "daily" in c[1] for c in backend.calls)


def test_adapter_daily_resin_uses_action_intent() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("daily_resin")
    assert adapter.execute_semantic("daily_resin", "", {})

    assert any(c[0] == "action_intent" and "daily" in c[1] for c in backend.calls)


def test_adapter_progression_chain_executes_all_stages() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("progression_chain")
    assert adapter.execute_semantic("progression_chain", "", {})

    # Chain runs 6 stages, each executing a UIFlow with clicks
    click_calls = [c for c in backend.calls if c[0] == "click_at"]
    assert len(click_calls) >= 6, f"expected >=6 clicks for 6 stages, got {len(click_calls)}"


def test_adapter_progression_stage_routes_to_flow() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("progression_level_up")
    assert adapter.execute_semantic("progression_level_up", "", {})

    assert any(call[0] == "click_at" for call in backend.calls)


def test_adapter_progression_stage_with_slot_target() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.execute_semantic("progression_weapon", "slot_2", {})

    # Should have character slot selection clicks + weapon enhance flow clicks
    click_calls = [c for c in backend.calls if c[0] == "click_at"]
    assert len(click_calls) >= 2


def test_adapter_progression_stage_unknown_fails() -> None:
    adapter = UIFlowSkillAdapter()
    # Directly call the handler with an unknown stage
    result = adapter._handle_progression_stage("", {"semantic_action": "progression_unknown"})
    assert not result


def test_adapter_boss_combat_routes_boss_id() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("combat_boss_dvalin")
    assert adapter.execute_semantic("combat_boss_dvalin", "", {})

    assert any(c[0] == "action_intent" and "dvalin" in c[1] for c in backend.calls)


def test_adapter_boss_combat_all_bosses() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    for action in (
        "combat_boss_dvalin", "combat_boss_childe", "combat_boss_signora",
        "combat_boss_raiden", "combat_boss_shouki", "combat_boss_narwhal",
    ):
        assert adapter.can_handle(action)
        assert adapter.execute_semantic(action, "", {})

    combat_calls = [c for c in backend.calls if c[0] == "action_intent" and "combat:boss" in c[1]]
    assert len(combat_calls) >= 6


def test_adapter_env_combat_routes_environment() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("combat_env_dragonspine")
    assert adapter.execute_semantic("combat_env_dragonspine", "", {})
    assert any(c[0] == "action_intent" and "dragonspine" in c[1] for c in backend.calls)

    assert adapter.can_handle("combat_env_inazuma")
    assert adapter.execute_semantic("combat_env_inazuma", "", {})
    assert any(c[0] == "action_intent" and "inazuma" in c[1] for c in backend.calls)


def test_adapter_abyss_and_multiwave_route_to_combat() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    for action in ("combat_abyss", "combat_multi_wave", "combat_weekly_rotation", "combat_world_farming"):
        assert adapter.can_handle(action)
        assert adapter.execute_semantic(action, "", {})

    combat_calls = [c for c in backend.calls if c[0] == "action_intent" and "combat" in c[1]]
    assert len(combat_calls) >= 4


def test_adapter_chain_scenario_routes() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    for action in ("chain_tutorial", "chain_daily_session", "chain_boss_gauntlet",
                   "chain_weekly_gauntlet", "chain_exploration_sweep"):
        assert adapter.can_handle(action)
        assert adapter.execute_semantic(action, "", {})

    chain_calls = [c for c in backend.calls if c[0] == "action_intent" and "chain" in c[1]]
    assert len(chain_calls) >= 5


def test_adapter_mainline_quest_routes() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    for action in ("mainline_progress", "mainline_prologue",
                   "mainline_ch1", "mainline_ch2", "mainline_ch3",
                   "mainline_ch4", "mainline_ch5"):
        assert adapter.can_handle(action)
        assert adapter.execute_semantic(action, "", {})

    mainline_calls = [c for c in backend.calls if c[0] == "action_intent" and "mainline" in c[1]]
    assert len(mainline_calls) >= 7
