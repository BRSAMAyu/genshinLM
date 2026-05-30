"""Tests for Spiral Abyss floor handler integration in CombatSkillAdapter."""
from __future__ import annotations

from combat.combat_skill_adapter import CombatSkillAdapter, CombatSkillAdapterConfig
from execution.console_backend import ConsoleInputBackend


class TestAbyssFloorHandler:
    def test_execute_abyss_floor_default(self):
        adapter = CombatSkillAdapter(
            backend=ConsoleInputBackend(),
            config=CombatSkillAdapterConfig(default_combat_duration_sec=1.0),
        )
        result = adapter.execute_abyss_floor(floor_number=9, context={
            "characters": [
                {"name": "hutao", "element": "pyro", "level": 90, "role": "main_dps"},
                {"name": "xingqiu", "element": "hydro", "level": 90, "role": "sub_dps"},
                {"name": "zhongli", "element": "geo", "level": 90, "role": "shield"},
                {"name": "bennett", "element": "pyro", "level": 90, "role": "healer"},
                {"name": "raiden", "element": "electro", "level": 90, "role": "main_dps"},
                {"name": "nahida", "element": "dendro", "level": 90, "role": "sub_dps"},
                {"name": "kazuha", "element": "anemo", "level": 90, "role": "support"},
                {"name": "kokomi", "element": "hydro", "level": 90, "role": "healer"},
            ],
        })
        assert result is True

    def test_execute_abyss_floor_12(self):
        adapter = CombatSkillAdapter(
            backend=ConsoleInputBackend(),
            config=CombatSkillAdapterConfig(default_combat_duration_sec=1.0),
        )
        result = adapter.execute_abyss_floor(floor_number=12, context={
            "characters": [
                {"name": "hutao", "element": "pyro", "level": 90, "role": "main_dps"},
                {"name": "xingqiu", "element": "hydro", "level": 90, "role": "sub_dps"},
                {"name": "zhongli", "element": "geo", "level": 90, "role": "shield"},
                {"name": "bennett", "element": "pyro", "level": 90, "role": "healer"},
                {"name": "raiden", "element": "electro", "level": 90, "role": "main_dps"},
                {"name": "nahida", "element": "dendro", "level": 90, "role": "sub_dps"},
                {"name": "kazuha", "element": "anemo", "level": 90, "role": "support"},
                {"name": "kokomi", "element": "hydro", "level": 90, "role": "healer"},
            ],
        })
        assert result is True

    def test_execute_abyss_floor_with_context(self):
        adapter = CombatSkillAdapter(
            backend=ConsoleInputBackend(),
            config=CombatSkillAdapterConfig(default_combat_duration_sec=1.0),
        )
        result = adapter.execute_abyss_floor(
            floor_number=11,
            context={
                "characters": [
                    {"name": "hutao", "element": "pyro", "level": 90, "role": "main_dps"},
                    {"name": "xingqiu", "element": "hydro", "level": 90, "role": "sub_dps"},
                    {"name": "zhongli", "element": "geo", "level": 90, "role": "shield"},
                    {"name": "bennett", "element": "pyro", "level": 90, "role": "healer"},
                ],
            },
        )
        assert result is True

    def test_skill_registry_routes_abyss_floor(self):
        from planning.skill_registry import SkillRegistry
        registry = SkillRegistry(
            skill_executor=_FakeExecutor(),
        )
        assert registry.can_handle("combat_abyss_floor")


class _FakeExecutor:
    def execute_semantic(self, action: str, target: str = "", context=None) -> bool:
        return True

    def key_down(self, key: str, *, reason: str = "") -> None:
        pass

    def key_up(self, key: str, *, reason: str = "") -> None:
        pass

    def key_press(self, key: str, *, reason: str = "") -> None:
        pass

    def action_intent(self, action: str, *, reason: str = "") -> None:
        pass
