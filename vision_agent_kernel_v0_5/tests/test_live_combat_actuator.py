from __future__ import annotations

import time
from unittest.mock import MagicMock, call

import pytest

from combat.live_combat_actuator import LiveCombatActuator


def test_live_combat_actuator_initialization() -> None:
    backend = MagicMock()
    actuator = LiveCombatActuator(backend)
    assert actuator._backend is backend
    assert actuator._active_character == 1


def test_live_combat_actuator_normal_loop() -> None:
    backend = MagicMock()
    actuator = LiveCombatActuator(backend)

    playbook_steps = [
        {"type": "attack", "duration": 0.2},
        {"type": "skill_e"},
        {"type": "switch", "character": 2},
        {"type": "burst_q"},
    ]

    obs_stream = lambda: {"hp_ratio": 0.9, "signals": {}}

    res = actuator.execute_combat_loop(playbook_steps, obs_stream)
    assert res is True

    # Validate that correct key sequences were pressed
    # 1. Attack should call left_click
    backend.left_click.assert_called()

    # 2. skill_e should press "e"
    backend.key_down.assert_any_call("e", reason="cast_skill_e")
    backend.key_up.assert_any_call("e", reason="cast_skill_e_done")

    # 3. Switch to 2 should press "2"
    backend.key_down.assert_any_call("2", reason="character_switch")
    backend.key_up.assert_any_call("2", reason="character_switch_done")

    # 4. burst_q should press "q"
    backend.key_down.assert_any_call("q", reason="cast_burst_q")
    backend.key_up.assert_any_call("q", reason="cast_burst_q_done")


def test_live_combat_actuator_stiffness_escape() -> None:
    backend = MagicMock()
    actuator = LiveCombatActuator(backend)

    playbook_steps = [{"type": "attack", "duration": 0.1}]

    # Interruption signal is active (hitstun)
    obs_stream = lambda: {"hp_ratio": 0.8, "signals": {"hitstun": 1.0}}

    res = actuator.execute_combat_loop(playbook_steps, obs_stream)
    assert res is True

    # Should execute escape sequence: double press "shift"
    shift_down_calls = [c for c in backend.key_down.call_args_list if c[0][0] == "shift"]
    shift_up_calls = [c for c in backend.key_up.call_args_list if c[0][0] == "shift"]

    assert len(shift_down_calls) == 2
    assert len(shift_up_calls) == 2


def test_live_combat_actuator_emergency_heal() -> None:
    backend = MagicMock()
    actuator = LiveCombatActuator(backend)

    playbook_steps = [{"type": "attack", "duration": 0.1}]

    # HP ratio is below 20%
    obs_stream = lambda: {"hp_ratio": 0.15, "signals": {}}

    res = actuator.execute_combat_loop(playbook_steps, obs_stream)
    # Loop should abort and return False
    assert res is False

    # Should press "esc" for emergency menu/healing
    backend.key_down.assert_called_with("esc", reason="emergency_heal")
    backend.key_up.assert_called_with("esc")


def test_live_combat_actuator_switch_cooldown() -> None:
    backend = MagicMock()
    actuator = LiveCombatActuator(backend)

    # First switch: to 2 (instant)
    # Second switch: back to 1 (instantly after 2, should be delayed because of the 1s cooldown)
    playbook_steps = [
        {"type": "switch", "character": 2},
        {"type": "switch", "character": 1},
    ]

    obs_stream = lambda: {"hp_ratio": 0.9, "signals": {}}

    start = time.perf_counter()
    res = actuator.execute_combat_loop(playbook_steps, obs_stream)
    end = time.perf_counter()

    assert res is True
    # The second switch should have been delayed by 1.0s minus the small execution time.
    # So the total time elapsed should be at least 0.9s.
    assert (end - start) >= 0.9
