"""Tests for SkillRegistry: composite action routing to specialized adapters."""
from __future__ import annotations

from typing import Any

from planning.skill_registry import SkillRegistry, SkillRegistryConfig


class _FakeExecutor:
    """Records execute_semantic calls and doubles as a backend."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def execute_semantic(
        self,
        action: str,
        target: str = "",
        context: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append((action, target, context))
        return True

    # Backend protocol methods for adapters that need a backend
    def key_down(self, key: str, *, reason: str = "") -> None:
        pass

    def key_up(self, key: str, *, reason: str = "") -> None:
        pass

    def key_press(self, key: str, *, reason: str = "") -> None:
        pass

    def action_intent(self, action: str, *, reason: str = "") -> None:
        pass


def _make_registry(**kwargs: Any) -> SkillRegistry:
    executor = _FakeExecutor()
    return SkillRegistry(skill_executor=executor, **kwargs)


def test_composite_actions_listed():
    registry = _make_registry()
    actions = registry.composite_actions
    assert "run_daily_deep" in actions
    assert "combat_encounter" in actions
    assert "explore_open_chest" in actions
    assert "quest_drive_dialog" in actions
    assert "character_progression_full" in actions


def test_can_handle_composite():
    registry = _make_registry()
    assert registry.can_handle("run_daily_deep") is True
    assert registry.can_handle("combat_encounter") is True
    assert registry.can_handle("unknown_action") is False


def test_daily_routine_routing():
    registry = _make_registry()
    result = registry.execute("run_daily_quick")
    # DailyRoutineSkillAdapter is lazily created and calls executor
    assert result is True


def test_progression_routing():
    registry = _make_registry()
    result = registry.execute("character_progression_full", target="hutao")
    assert result is True


def test_progression_individual_stage():
    registry = _make_registry()
    result = registry.execute("character_progression_level_up", target="amber")
    assert result is True


def test_exploration_routing():
    registry = _make_registry()
    result = registry.execute("explore_open_chest")
    assert result is True


def test_quest_routing():
    registry = _make_registry()
    result = registry.execute("quest_advance", context={"evidence": "npc_spoken"})
    assert result is True


def test_unknown_action_returns_false():
    registry = _make_registry()
    result = registry.execute("totally_unknown")
    assert result is False


def test_config_propagated():
    config = SkillRegistryConfig(
        combat_max_retries=5,
        daily_max_commissions=2,
        progression_max_level=80,
    )
    registry = _make_registry(config=config)
    # The config should be stored and used when creating adapters
    result = registry.execute("run_daily_quick")
    assert result is True


def test_adapter_cached():
    registry = _make_registry()
    # First call creates adapter
    registry.execute("run_daily_quick")
    # Second call reuses cached adapter
    registry.execute("run_daily_standard")
    # Should have cached the daily_routine adapter
    assert "daily_routine" in registry._adapters


def test_progression_chain_result():
    """run_full_chain returns list[ProgressionResult], registry should convert to bool."""
    registry = _make_registry()
    result = registry.execute("character_progression_full", target="hutao")
    assert result is True


def test_combat_routing_with_context():
    registry = _make_registry()
    result = registry.execute(
        "combat_encounter",
        context={
            "team_elements": ["pyro", "hydro"],
            "team_characters": ["hutao", "xingqiu"],
        },
    )
    assert result is True
