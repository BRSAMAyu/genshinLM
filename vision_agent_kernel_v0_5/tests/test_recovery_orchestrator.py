"""Tests for planning/recovery_orchestrator.py: unified recovery chain."""
from __future__ import annotations

from typing import Any

from planning.recovery_orchestrator import (
    EscalationLevel,
    RecoveryAction,
    RecoveryCategory,
    RecoveryEvent,
    RecoveryOrchestrator,
    RecoveryOrchestratorConfig,
    RecoveryResult,
    RecoverySeverity,
)


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self._fail_actions: set[str] = set()

    def set_fail_on(self, actions: set[str]) -> None:
        self._fail_actions = actions

    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append((action, target, context))
        return action not in self._fail_actions


class TestRecoveryOrchestrator:
    def test_combat_death_recovery(self):
        ex = _FakeExecutor()
        orch = RecoveryOrchestrator(executor=ex)
        event = RecoveryEvent(
            RecoveryCategory.COMBAT, RecoverySeverity.MODERATE,
            "character_death", context={"failure_type": "character_death"},
        )
        result = orch.recover(event)
        assert result.success
        assert result.category == RecoveryCategory.COMBAT
        assert result.escalation == EscalationLevel.AUTO
        assert any("statue" in c[1] for c in ex.calls)

    def test_navigation_stuck_recovery(self):
        ex = _FakeExecutor()
        orch = RecoveryOrchestrator(executor=ex)
        event = RecoveryEvent(
            RecoveryCategory.NAVIGATION, RecoverySeverity.MINOR,
            "stuck", context={"failure_type": "stuck"},
        )
        result = orch.recover(event)
        assert result.success
        assert any("waypoint" in c[1] for c in ex.calls)

    def test_ui_stuck_menu_recovery(self):
        ex = _FakeExecutor()
        orch = RecoveryOrchestrator(executor=ex)
        event = RecoveryEvent(
            RecoveryCategory.UI, RecoverySeverity.TRIVIAL,
            "stuck_menu", context={"failure_type": "stuck_menu"},
        )
        result = orch.recover(event)
        assert result.success
        assert any("escape" in c[0] for c in ex.calls)

    def test_environment_cold_recovery(self):
        ex = _FakeExecutor()
        orch = RecoveryOrchestrator(executor=ex)
        event = RecoveryEvent(
            RecoveryCategory.ENVIRONMENT, RecoverySeverity.MODERATE,
            "sheer_cold", context={"failure_type": "sheer_cold"},
        )
        result = orch.recover(event)
        assert result.success
        assert any("warmth" in c[1] for c in ex.calls)

    def test_quest_marker_gone_recovery(self):
        ex = _FakeExecutor()
        orch = RecoveryOrchestrator(executor=ex)
        event = RecoveryEvent(
            RecoveryCategory.QUEST, RecoverySeverity.MINOR,
            "marker_gone", context={"failure_type": "marker_gone"},
        )
        result = orch.recover(event)
        assert result.success

    def test_system_crash_recovery(self):
        ex = _FakeExecutor()
        orch = RecoveryOrchestrator(executor=ex)
        event = RecoveryEvent(
            RecoveryCategory.SYSTEM, RecoverySeverity.CRITICAL,
            "crash", context={"failure_type": "crash"},
        )
        result = orch.recover(event)
        # System recovery starts at MANUAL escalation
        assert result.escalation >= EscalationLevel.MANUAL

    def test_resource_no_food_recovery(self):
        ex = _FakeExecutor()
        orch = RecoveryOrchestrator(executor=ex)
        event = RecoveryEvent(
            RecoveryCategory.RESOURCE, RecoverySeverity.MODERATE,
            "no_food", context={"failure_type": "no_food"},
        )
        result = orch.recover(event)
        assert result.success
        assert any("craft" in c[0] or "sweet_madame" in c[1] for c in ex.calls)

    def test_consecutive_failures_escalate(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"press_escape"})
        orch = RecoveryOrchestrator(
            executor=ex,
            config=RecoveryOrchestratorConfig(max_auto_retries=2),
        )
        # Fail multiple times to trigger escalation
        event = RecoveryEvent(
            RecoveryCategory.UI, RecoverySeverity.MINOR,
            "stuck_menu", context={"failure_type": "stuck_menu"},
        )
        r1 = orch.recover(event)
        assert r1.escalation == EscalationLevel.ASSISTED
        r2 = orch.recover(event)
        assert r2.escalation >= EscalationLevel.ASSISTED

    def test_reset_consecutive_clears_counter(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"press_escape"})
        orch = RecoveryOrchestrator(executor=ex)
        event = RecoveryEvent(
            RecoveryCategory.UI, RecoverySeverity.MINOR,
            "stuck_menu", context={"failure_type": "stuck_menu"},
        )
        orch.recover(event)
        assert orch._consecutive_failures.get(RecoveryCategory.UI, 0) > 0
        orch.reset_consecutive(RecoveryCategory.UI)
        assert RecoveryCategory.UI not in orch._consecutive_failures

    def test_get_status(self):
        ex = _FakeExecutor()
        orch = RecoveryOrchestrator(executor=ex)
        event = RecoveryEvent(
            RecoveryCategory.COMBAT, RecoverySeverity.MINOR,
            "low_hp", context={"failure_type": "low_hp"},
        )
        orch.recover(event)
        status = orch.get_status()
        assert status["total_recoveries"] == 1
        assert status["successful"] == 1
        assert status["success_rate"] == 1.0

    def test_recovery_history_bounded(self):
        ex = _FakeExecutor()
        orch = RecoveryOrchestrator(executor=ex)
        event = RecoveryEvent(
            RecoveryCategory.COMBAT, RecoverySeverity.MINOR,
            "low_hp", context={"failure_type": "low_hp"},
        )
        for _ in range(110):
            orch.recover(event)
        assert len(orch.recovery_history) <= 100

    def test_unknown_failure_uses_category_fallback(self):
        ex = _FakeExecutor()
        orch = RecoveryOrchestrator(executor=ex)
        event = RecoveryEvent(
            RecoveryCategory.COMBAT, RecoverySeverity.MODERATE,
            "unknown_combat_thing",
        )
        result = orch.recover(event)
        # Should fall back to first combat action
        assert result.category == RecoveryCategory.COMBAT

    def test_no_action_for_unknown_category(self):
        """Edge case: no action registered for a weird category."""
        ex = _FakeExecutor()
        orch = RecoveryOrchestrator(executor=ex)
        # All categories have actions, but let's test with empty context
        event = RecoveryEvent(
            RecoveryCategory.QUEST, RecoverySeverity.MINOR,
            "completely_unknown",
        )
        result = orch.recover(event)
        # Category-level fallback should find an action
        assert result.category == RecoveryCategory.QUEST

    def test_severity_to_escalation_mapping(self):
        assert RecoveryOrchestrator._severity_to_escalation(RecoverySeverity.TRIVIAL) == EscalationLevel.AUTO
        assert RecoveryOrchestrator._severity_to_escalation(RecoverySeverity.MINOR) == EscalationLevel.AUTO
        assert RecoveryOrchestrator._severity_to_escalation(RecoverySeverity.MODERATE) == EscalationLevel.AUTO
        assert RecoveryOrchestrator._severity_to_escalation(RecoverySeverity.MAJOR) == EscalationLevel.ASSISTED
        assert RecoveryOrchestrator._severity_to_escalation(RecoverySeverity.CRITICAL) == EscalationLevel.MANUAL
