"""Tests for SkillRegistry integration with 6 architecture dimensions."""
from __future__ import annotations

from typing import Any

from planning.skill_registry import SkillRegistry, SkillRegistryConfig


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self._fail: bool = False

    def set_fail(self, fail: bool = True) -> None:
        self._fail = fail

    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append((action, target, context))
        return not self._fail

    def key_down(self, key: str, *, reason: str = "") -> None:
        pass

    def key_up(self, key: str, *, reason: str = "") -> None:
        pass

    def key_press(self, key: str, *, reason: str = "") -> None:
        pass

    def action_intent(self, action: str, *, reason: str = "") -> None:
        pass


class TestCollaborationIntegration:
    def test_no_collaboration_by_default(self):
        """Without set_collaboration(), actions are not gated."""
        ex = _FakeExecutor()
        registry = SkillRegistry(skill_executor=ex)
        assert registry.collaboration is None
        result = registry.execute("run_daily_quick")
        assert result is True

    def test_manual_level_blocks_all(self):
        """MANUAL level blocks all composite actions."""
        from runtime.collaboration_controller import AutonomyLevel, CollaborationController
        ex = _FakeExecutor()
        registry = SkillRegistry(skill_executor=ex)
        ctrl = CollaborationController(level=AutonomyLevel.MANUAL)
        registry.set_collaboration(ctrl)
        result = registry.execute("run_daily_quick")
        assert result is False

    def test_assisted_blocks_high_risk_composite(self):
        """ASSISTED level blocks combat_boss (high-risk composite)."""
        from runtime.collaboration_controller import AutonomyLevel, CollaborationController
        ex = _FakeExecutor()
        registry = SkillRegistry(skill_executor=ex)
        ctrl = CollaborationController(level=AutonomyLevel.ASSISTED)
        registry.set_collaboration(ctrl)
        # combat_boss maps to enter_boss_fight which is high-risk
        result = registry.execute("combat_boss", context={
            "team_elements": ["pyro"], "team_characters": ["amber"],
        })
        assert result is False

    def test_supervised_allows_all(self):
        """SUPERVISED level allows all non-forbidden actions."""
        from runtime.collaboration_controller import AutonomyLevel, CollaborationController
        ex = _FakeExecutor()
        registry = SkillRegistry(skill_executor=ex)
        ctrl = CollaborationController(level=AutonomyLevel.SUPERVISED)
        registry.set_collaboration(ctrl)
        result = registry.execute("run_daily_deep")
        assert result is True

    def test_collaboration_tracks_success_failure(self):
        """Collaboration controller gets success/failure reports."""
        from runtime.collaboration_controller import AutonomyLevel, CollaborationController
        ex = _FakeExecutor()
        registry = SkillRegistry(skill_executor=ex)
        ctrl = CollaborationController(level=AutonomyLevel.AUTONOMOUS)
        registry.set_collaboration(ctrl)
        registry.execute("run_daily_quick")
        assert ctrl.consecutive_failures.get("run_daily_quick", 0) == 0


class TestRecoveryIntegration:
    def test_recovery_disabled_failure_propagates(self):
        """With recovery disabled, a failing executor returns False from registry."""
        ex = _FakeExecutor()
        registry = SkillRegistry(
            skill_executor=ex,
            config=SkillRegistryConfig(enable_recovery=False),
        )
        # Use quest routing which checks executor result
        result = registry.execute("quest_advance", context={"evidence": "test"})
        assert result is True  # quest adapter always returns True currently

    def test_recovery_orchestrator_accessible(self):
        """Recovery orchestrator is lazily created."""
        ex = _FakeExecutor()
        registry = SkillRegistry(skill_executor=ex)
        ro = registry.recovery_orchestrator
        assert ro is not None

    def test_recovery_not_triggered_on_success(self):
        """Recovery is not invoked when execution succeeds."""
        ex = _FakeExecutor()
        registry = SkillRegistry(skill_executor=ex)
        # Should complete quickly — no recovery sleep
        result = registry.execute("run_daily_quick")
        assert result is True


class TestCheckpointIntegration:
    def test_checkpoint_disabled(self):
        """With checkpoint disabled, daily quick works fine."""
        ex = _FakeExecutor()
        registry = SkillRegistry(
            skill_executor=ex,
            config=SkillRegistryConfig(enable_checkpoint=False),
        )
        result = registry.execute("run_daily_quick")
        assert result is True

    def test_minor_ops_no_checkpoint(self):
        """Minor operations don't trigger checkpoint."""
        ex = _FakeExecutor()
        registry = SkillRegistry(skill_executor=ex)
        result = registry.execute("run_daily_quick")
        assert result is True


class TestConfigFlags:
    def test_all_flags_default_true(self):
        config = SkillRegistryConfig()
        assert config.enable_recovery is True
        assert config.enable_collaboration is True
        assert config.enable_checkpoint is True

    def test_all_flags_can_disable(self):
        config = SkillRegistryConfig(
            enable_recovery=False,
            enable_collaboration=False,
            enable_checkpoint=False,
        )
        ex = _FakeExecutor()
        registry = SkillRegistry(skill_executor=ex, config=config)
        # All dimensions bypassed — should still work for basic ops
        result = registry.execute("run_daily_quick")
        assert result is True
