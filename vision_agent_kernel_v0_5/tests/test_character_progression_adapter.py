"""Tests for CharacterProgressionAdapter: 6-stage progression chain."""
from __future__ import annotations

from typing import Any

from planning.character_progression_adapter import (
    CharacterProgressionAdapter,
    CharacterProgressionConfig,
    ProgressionResult,
)


class _FakeExecutor:
    def __init__(self, *, fail_at: str | None = None) -> None:
        self.calls: list[str] = []
        self._fail_at = fail_at

    def execute_semantic(
        self,
        action: str,
        target: str = "",
        context: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append(action)
        if self._fail_at and action == self._fail_at:
            return False
        return True


def test_full_chain_all_stages():
    executor = _FakeExecutor()
    adapter = CharacterProgressionAdapter(skill_executor=executor)
    results = adapter.run_full_chain(character="hutao")

    assert len(results) == 6
    assert all(r.success for r in results)
    assert results[0].stage_name == "level_up"
    assert results[5].stage_name == "team_config"


def test_full_chain_stops_on_failure():
    executor = _FakeExecutor(fail_at="character_ascend_full")
    adapter = CharacterProgressionAdapter(skill_executor=executor)
    results = adapter.run_full_chain()

    assert len(results) == 2  # stage 1 ok, stage 2 fails, stops
    assert results[0].success is True
    assert results[1].success is False


def test_stage1_level_up():
    executor = _FakeExecutor()
    adapter = CharacterProgressionAdapter(skill_executor=executor)
    result = adapter.stage1_level_up("amber")

    assert result.stage == 1
    assert result.stage_name == "level_up"
    assert result.success is True
    assert "character_level_up_full" in executor.calls


def test_stage3_weapon():
    executor = _FakeExecutor()
    adapter = CharacterProgressionAdapter(skill_executor=executor)
    result = adapter.stage3_weapon("hutao")

    assert result.stage == 3
    assert result.success is True
    assert "weapon_equip_full" in executor.calls
    assert "weapon_enhance_full" in executor.calls


def test_stage5_talent_all_three():
    executor = _FakeExecutor()
    adapter = CharacterProgressionAdapter(skill_executor=executor)
    result = adapter.stage5_talent("ganyu")

    assert result.stage == 5
    assert result.success is True
    assert "character_talent_upgrade_full" in executor.calls
    assert "character_talent_upgrade_skill" in executor.calls
    assert "character_talent_upgrade_burst" in executor.calls


def test_individual_stage():
    executor = _FakeExecutor()
    adapter = CharacterProgressionAdapter(skill_executor=executor)
    result = adapter.stage4_artifact()

    assert result.stage == 4
    assert "artifact_equip_full" in executor.calls
    assert "artifact_enhance_full" in executor.calls
