"""Tests for the live-perception control adapters.

Drives each adapter with a synthetic ``Observation`` + screen-state, asserts a
well-formed View, feeds it through the real controller, and asserts the resulting
Action maps to a valid ``SemanticAction`` whose key comes from the capsule keymap.
"""
from __future__ import annotations

import time

from agent_kernel.types import SemanticAction
from capsules.genshin.control_adapters import (
    COMBAT_RESIDUALS,
    DEFAULT_GENSHIN_KEYMAP,
    INTERACTION_RESIDUALS,
    PUZZLE_RESIDUALS,
    build_combat_view,
    build_interaction_view,
    build_puzzle_view,
    combat_action_to_semantic,
    interaction_action_to_semantic,
    puzzle_action_to_semantic,
)
from combat.reactive_combat_controller import (
    CombatCharView,
    CombatView,
    ReactiveCombatController,
)
from core.types import FocusState, Observation, TargetTrack
from interaction.interaction_controller import InteractionController, InteractionView
from puzzle.puzzle_controller import PuzzleController, PuzzleView


def _obs(
    *,
    target_track: TargetTrack | None = None,
    extensions: dict[str, object] | None = None,
) -> Observation:
    t = time.perf_counter()
    return Observation(
        frame_id=1,
        t_capture=t,
        t_processed=t,
        latency_ms=0.0,
        viewport_size=(1280, 720),
        target_track=target_track,
        obstacle_field=None,
        ui_state=None,
        visual_triggers={},
        os_focus=FocusState(focused=True),
        extensions=extensions or {},
    )


def _enemy_track() -> TargetTrack:
    return TargetTrack(
        track_id="t1",
        class_id="hilichurl",
        state="tracked",
        bbox_xyxy=(100.0, 100.0, 200.0, 200.0),
        smoothed_center_px=(150.0, 150.0),
        velocity_px_s=(0.0, 0.0),
        confidence=0.9,
        identity_confidence=0.9,
        missing_duration_ms=0.0,
        bearing_deg=0.0,
        pitch_deg=0.0,
        estimated_range=5.0,
        last_seen_frame_id=1,
    )


_KEYS = set(DEFAULT_GENSHIN_KEYMAP.values())


# --- combat ----------------------------------------------------------------


def test_build_combat_view_safe_defaults_no_party() -> None:
    view = build_combat_view(_obs(target_track=_enemy_track()), "combat")
    assert isinstance(view, CombatView)
    # safe defaults: full enemy HP, no telegraph, single conservative DPS.
    assert view.enemy_hp_ratio == 1.0
    assert view.incoming_attack is False
    assert len(view.chars) == 1
    assert view.chars[0].skill_ready is False and view.chars[0].burst_ready is False


def test_combat_view_default_falls_through_to_attack() -> None:
    view = build_combat_view(_obs(target_track=_enemy_track()), "combat")
    action = ReactiveCombatController().decide(view)
    # nothing ready, no telegraph -> normal attack.
    assert action.kind == "attack"
    sem = combat_action_to_semantic(action)
    assert isinstance(sem, SemanticAction)
    assert sem.kind == "combat"
    assert sem.requires_physical_input is True
    params = dict(sem.parameters)
    assert params["key"] == DEFAULT_GENSHIN_KEYMAP["normal_attack"]
    assert params["key"] in _KEYS


def test_combat_dodge_maps_to_sprint_key() -> None:
    # extensions can supply richer signals when a provider populates them.
    chars = (
        CombatCharView(0, "dps", "pyro", 1.0, 0.0, False, False, "dps"),
    )
    view = build_combat_view(
        _obs(extensions={"incoming_attack": True, "can_dodge": True}),
        "combat",
        chars=chars,
    )
    action = ReactiveCombatController().decide(view)
    assert action.kind == "dodge"
    sem = combat_action_to_semantic(action)
    params = dict(sem.parameters)
    assert params["key"] == DEFAULT_GENSHIN_KEYMAP["sprint"]


def test_combat_switch_maps_to_party_slot_key() -> None:
    chars = (
        CombatCharView(0, "dps", "pyro", 1.0, 0.0, False, False, "dps"),
        CombatCharView(1, "sub", "hydro", 1.0, 0.0, True, False, "sub"),
    )
    view = build_combat_view(
        _obs(extensions={"enemy_aura": "pyro"}),
        "combat",
        chars=chars,
        active_index=0,
    )
    action = ReactiveCombatController().decide(view)
    assert action.kind == "switch" and action.switch_to == 1
    sem = combat_action_to_semantic(action)
    params = dict(sem.parameters)
    assert params["key"] == "2"  # party slot for index 1


# --- interaction -----------------------------------------------------------


def test_build_interaction_view_dialog_advances() -> None:
    view = build_interaction_view(_obs(), "dialog", objective_hint="accept commission")
    assert isinstance(view, InteractionView)
    assert view.screen == "dialogue" and view.dialogue_active is True
    action = InteractionController().decide(view)
    assert action.kind == "advance"
    sem = interaction_action_to_semantic(action)
    assert isinstance(sem, SemanticAction)
    assert sem.kind == "ui" and sem.requires_physical_input is True
    params = dict(sem.parameters)
    assert params["key"] == DEFAULT_GENSHIN_KEYMAP["interact"]


def test_interaction_reward_claims() -> None:
    view = build_interaction_view(_obs(), "notification")
    assert view.screen == "reward"
    action = InteractionController().decide(view)
    assert action.kind == "claim"
    sem = interaction_action_to_semantic(action)
    assert dict(sem.parameters)["key"] in _KEYS


def test_interaction_choice_passes_index_not_pixels() -> None:
    view = build_interaction_view(
        _obs(extensions={"dialogue_choices": ("Accept the commission", "Decline")}),
        "menu",
        objective_hint="accept the commission",
    )
    assert view.screen == "choice"
    action = InteractionController().decide(view)
    assert action.kind == "choose" and action.choice_index == 0
    sem = interaction_action_to_semantic(action)
    assert sem.intent == "select_dialog_choice"
    params = dict(sem.parameters)
    assert params["choice_index"] == "0"
    # no raw x/y fabricated.
    assert "x" not in params and "y" not in params


def test_interaction_none_is_idle_noop() -> None:
    view = build_interaction_view(_obs(), "world_hud")
    assert view.screen == "none"
    action = InteractionController().decide(view)
    assert action.kind == "idle"
    sem = interaction_action_to_semantic(action)
    assert sem.kind == "system" and sem.requires_physical_input is False


# --- puzzle ----------------------------------------------------------------


def test_build_puzzle_view_no_target_proposes() -> None:
    view = build_puzzle_view(_obs(target_track=_enemy_track()), "overworld")
    assert isinstance(view, PuzzleView)
    assert view.target is None
    # current seeded from tracked pixel centre.
    assert view.current == (150.0, 150.0)
    action = PuzzleController().decide(view)
    assert action.kind == "propose"
    sem = puzzle_action_to_semantic(action)
    assert sem.kind == "system" and sem.requires_physical_input is False


def test_puzzle_with_target_no_error_refines() -> None:
    view = build_puzzle_view(_obs(), "overworld", target=(10.0, 10.0))
    assert view.target == (10.0, 10.0) and view.error is None
    action = PuzzleController().decide(view)
    assert action.kind == "refine"


def test_puzzle_act_carries_metric_delta() -> None:
    view = build_puzzle_view(
        _obs(),
        "overworld",
        current=(0.0, 0.0),
        target=(10.0, 0.0),
        error=(10.0, 0.0),
        tolerance=1.0,
    )
    action = PuzzleController().decide(view)
    assert action.kind == "act"
    sem = puzzle_action_to_semantic(action)
    assert sem.intent == "puzzle_step" and sem.requires_physical_input is True
    params = dict(sem.parameters)
    assert "delta_x" in params and "delta_y" in params
    assert float(params["delta_x"]) > 0.0


# --- residuals are exported and non-empty ----------------------------------


def test_residuals_documented() -> None:
    assert COMBAT_RESIDUALS and INTERACTION_RESIDUALS and PUZZLE_RESIDUALS
    assert all(isinstance(s, str) for s in COMBAT_RESIDUALS)
