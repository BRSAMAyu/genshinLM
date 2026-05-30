"""Tests for DailyRoutineSkillAdapter: 3-layer daily routine loop."""
from __future__ import annotations

from typing import Any

from orchestration.daily_routine_skill_adapter import (
    DailyRoutineConfig,
    DailyRoutineResult,
    DailyRoutineSkillAdapter,
)


class _FakeSkillExecutor:
    """Records execute_semantic calls for verification."""

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


def test_layer1_executes_phases():
    executor = _FakeSkillExecutor()
    adapter = DailyRoutineSkillAdapter(skill_executor=executor)
    result = adapter.execute_layer1()

    assert isinstance(result, DailyRoutineResult)
    assert result.layer == 1
    assert result.commissions_done == 4
    assert result.katheryne_claimed is True
    assert result.resin_spent >= 20
    # Verify key actions were called
    actions = [c[0] for c in executor.calls]
    assert "open_menu" in actions
    assert "close_menu" in actions
    assert "teleport" in actions
    assert "domain_enter_and_claim" in actions


def test_layer2_includes_layer1_plus_domains():
    executor = _FakeSkillExecutor()
    adapter = DailyRoutineSkillAdapter(skill_executor=executor)
    result = adapter.execute_layer2()

    assert result.layer == 2
    assert result.commissions_done == 4
    assert result.domains_done == 2  # default domain_runs
    assert result.bosses_done == 1  # default boss_runs
    assert result.resin_spent >= 80  # 20 (layer1) + 40 (domains) + 20 (boss)


def test_layer3_includes_layer2_plus_shop():
    executor = _FakeSkillExecutor()
    adapter = DailyRoutineSkillAdapter(skill_executor=executor)
    result = adapter.execute_layer3()

    assert result.layer == 3
    assert result.commissions_done == 4
    actions = [c[0] for c in executor.calls]
    assert "shop_open_paimon_bargains" in actions
    assert "shop_buy_monthly_fates" in actions
    assert "artifact_enhance_full" in actions


def test_layer1_with_custom_context():
    executor = _FakeSkillExecutor()
    adapter = DailyRoutineSkillAdapter(skill_executor=executor)
    result = adapter.execute_layer1(context={
        "commission_0_type": "dialog",
        "commission_1_type": "collect",
        "commission_2_type": "combat",
        "commission_3_type": "combat",
    })

    assert result.commissions_done == 4
    # Dialog commission calls interact_npc and advance_dialog
    assert result.success is True


def test_config_affects_commissions():
    executor = _FakeSkillExecutor()
    config = DailyRoutineConfig(max_commissions=2)
    adapter = DailyRoutineSkillAdapter(skill_executor=executor, config=config)
    result = adapter.execute_layer1()

    assert result.commissions_done == 2


def test_layer2_custom_domain_boss_counts():
    executor = _FakeSkillExecutor()
    adapter = DailyRoutineSkillAdapter(skill_executor=executor)
    result = adapter.execute_layer2(context={"domain_runs": 3, "boss_runs": 2})

    assert result.domains_done == 3
    assert result.bosses_done == 2


def test_result_errors_captured():
    class _FailingExecutor:
        def execute_semantic(self, action: str, target: str = "", context: Any = None) -> bool:
            if action == "domain_enter_and_claim":
                raise RuntimeError("domain error")
            return True

    adapter = DailyRoutineSkillAdapter(skill_executor=_FailingExecutor())
    result = adapter.execute_layer1()

    # Should have errors from domain and possibly Katherine
    assert len(result.errors) > 0
