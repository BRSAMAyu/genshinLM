"""Tests for planning/session_chains.py: daily, progression, and mainline sessions."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from planning.session_chains import (
    CharacterProgressionSession,
    DailySessionChain,
    MainlineSession,
    SessionSnapshot,
)
from planning.newbie_tutorial_chain import NewbieTutorialChain


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


class TestDailySessionChain:
    def test_full_session_succeeds(self):
        ex = _FakeExecutor()
        chain = DailySessionChain(executor=ex)
        result = chain.run()
        assert result.success
        assert result.commissions_done == 4
        assert result.duration_sec > 0

    def test_steps_completed(self):
        ex = _FakeExecutor()
        chain = DailySessionChain(executor=ex)
        result = chain.run()
        assert result.steps_completed == 7

    def test_commissions_use_daily_quick(self):
        ex = _FakeExecutor()
        chain = DailySessionChain(executor=ex)
        chain.run()
        quick_calls = [c for c in ex.calls if c[0] == "run_daily_quick"]
        assert len(quick_calls) == 4

    def test_katheryne_interaction(self):
        ex = _FakeExecutor()
        chain = DailySessionChain(executor=ex)
        result = chain.run()
        assert result.katheryne_collected
        kath_calls = [c for c in ex.calls if "katheryne" in c[1]]
        assert len(kath_calls) >= 1

    def test_resin_spending(self):
        ex = _FakeExecutor()
        chain = DailySessionChain(executor=ex)
        snap = SessionSnapshot(resin=160)
        result = chain.run(initial_snapshot=snap)
        assert result.resin_spent == 160

    def test_return_to_start(self):
        ex = _FakeExecutor()
        chain = DailySessionChain(executor=ex)
        snap = SessionSnapshot(position_region="mondstadt")
        result = chain.run(initial_snapshot=snap)
        tp_calls = [c for c in ex.calls if c[0] == "teleport_to" and "return" in str(c[2])]
        assert len(tp_calls) >= 1

    def test_timeout_skips_remaining(self):
        ex = _FakeExecutor()
        chain = DailySessionChain(executor=ex, max_duration_sec=0.0)
        result = chain.run()
        # With 0 timeout, most steps should be skipped
        assert len(result.skipped_steps) > 0

    def test_commission_failure_marks_unsuccessful(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"run_daily_quick"})
        chain = DailySessionChain(executor=ex)
        result = chain.run()
        assert result.commissions_done == 0
        assert not result.success


class TestCharacterProgressionSession:
    def test_full_session_succeeds(self):
        ex = _FakeExecutor()
        session = CharacterProgressionSession(executor=ex)
        result = session.run(character="hu_tao")
        assert result.success
        assert result.character == "hu_tao"

    def test_all_stages_completed(self):
        ex = _FakeExecutor()
        session = CharacterProgressionSession(executor=ex)
        result = session.run(character="ganyu")
        assert result.level_done
        assert result.ascend_done
        assert result.weapon_done
        assert result.artifact_done
        assert result.talent_done
        assert result.team_done
        assert result.material_farmed

    def test_material_farming_step(self):
        ex = _FakeExecutor()
        session = CharacterProgressionSession(executor=ex)
        session.run(character="raiden")
        farm_calls = [c for c in ex.calls if c[0] == "combat_world_boss_farming"]
        assert len(farm_calls) >= 1

    def test_progression_uses_semantic_actions(self):
        ex = _FakeExecutor()
        session = CharacterProgressionSession(executor=ex)
        session.run(character="zhongli")
        prog_calls = [c for c in ex.calls if c[0].startswith("character_progression")]
        assert len(prog_calls) >= 6  # level, ascend, weapon, artifact, talent, team

    def test_timeout_limits_session(self):
        ex = _FakeExecutor()
        session = CharacterProgressionSession(executor=ex, max_duration_sec=0.0)
        result = session.run(character="nahida")
        assert result.steps_completed < 8


class TestMainlineSession:
    def test_full_session_succeeds(self):
        ex = _FakeExecutor()
        session = MainlineSession(executor=ex)
        result = session.run(current_ar=1)
        assert result.success

    def test_delegates_to_mainline_progression(self):
        ex = _FakeExecutor()
        session = MainlineSession(executor=ex)
        session.run()
        mainline_calls = [c for c in ex.calls if c[0] == "mainline_full_progression"]
        assert len(mainline_calls) >= 1

    def test_passes_current_ar(self):
        ex = _FakeExecutor()
        session = MainlineSession(executor=ex)
        session.run(current_ar=25)
        mainline_calls = [c for c in ex.calls if c[0] == "mainline_full_progression"]
        assert mainline_calls[0][2].get("current_ar") == 25

    def test_failure_returns_unsuccessful(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"mainline_full_progression"})
        session = MainlineSession(executor=ex)
        result = session.run()
        assert not result.success


class TestDailySessionChainRecovery:
    def test_recovery_on_step_failure(self):
        from planning.recovery_orchestrator import RecoveryOrchestrator, RecoveryResult
        from planning.recovery_orchestrator import (
            RecoveryCategory,
            EscalationLevel,
        )
        mock_recovery = MagicMock(spec=RecoveryOrchestrator)
        mock_recovery.recover.return_value = RecoveryResult(
            success=True, category=RecoveryCategory.COMBAT,
            escalation=EscalationLevel.AUTO,
        )
        ex = _FakeExecutor()
        ex.set_fail_on({"run_daily_quick"})
        chain = DailySessionChain(executor=ex, recovery_orchestrator=mock_recovery)
        result = chain.run()
        assert result.recovery_events >= 1
        mock_recovery.recover.assert_called()

    def test_no_recovery_when_none_provided(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"run_daily_quick"})
        chain = DailySessionChain(executor=ex)
        result = chain.run()
        assert result.recovery_events == 0

    def test_recovery_on_exception(self):
        class _ThrowExecutor:
            def execute_semantic(self, action: str = "", target: str = "",
                                context: Any = None) -> bool:
                if action == "run_daily_quick":
                    raise RuntimeError("boom")
                return True

        from planning.recovery_orchestrator import RecoveryOrchestrator, RecoveryResult
        from planning.recovery_orchestrator import (
            RecoveryCategory,
            EscalationLevel,
        )
        mock_recovery = MagicMock(spec=RecoveryOrchestrator)
        mock_recovery.recover.return_value = RecoveryResult(
            success=True, category=RecoveryCategory.COMBAT,
            escalation=EscalationLevel.AUTO,
        )
        chain = DailySessionChain(
            executor=_ThrowExecutor(), recovery_orchestrator=mock_recovery,
        )
        result = chain.run()
        assert result.recovery_events >= 1


class TestProgressionSessionRecovery:
    def test_recovery_on_step_failure(self):
        from planning.recovery_orchestrator import RecoveryOrchestrator, RecoveryResult
        from planning.recovery_orchestrator import (
            RecoveryCategory,
            EscalationLevel,
        )
        mock_recovery = MagicMock(spec=RecoveryOrchestrator)
        mock_recovery.recover.return_value = RecoveryResult(
            success=True, category=RecoveryCategory.COMBAT,
            escalation=EscalationLevel.AUTO,
        )
        ex = _FakeExecutor()
        ex.set_fail_on({"combat_world_boss_farming"})
        session = CharacterProgressionSession(
            executor=ex, recovery_orchestrator=mock_recovery,
        )
        result = session.run(character="hu_tao")
        assert result.recovery_events >= 1
        mock_recovery.recover.assert_called()

    def test_recovery_on_exception(self):
        class _ThrowOnFarm:
            def execute_semantic(self, action: str = "", target: str = "",
                                context: Any = None) -> bool:
                if action == "combat_world_boss_farming":
                    raise RuntimeError("boss_encounter_error")
                return True

        from planning.recovery_orchestrator import RecoveryOrchestrator, RecoveryResult
        from planning.recovery_orchestrator import (
            RecoveryCategory,
            EscalationLevel,
        )
        mock_recovery = MagicMock(spec=RecoveryOrchestrator)
        mock_recovery.recover.return_value = RecoveryResult(
            success=True, category=RecoveryCategory.COMBAT,
            escalation=EscalationLevel.AUTO,
        )
        session = CharacterProgressionSession(
            executor=_ThrowOnFarm(), recovery_orchestrator=mock_recovery,
        )
        result = session.run(character="raiden")
        assert result.recovery_events >= 1

    def test_no_recovery_when_none_provided(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"combat_world_boss_farming"})
        session = CharacterProgressionSession(executor=ex)
        result = session.run(character="nahida")
        assert result.recovery_events == 0


class TestNewbieTutorialCheckpoint:
    def test_checkpoint_saved_after_each_phase(self):
        from pathlib import Path
        import tempfile
        import shutil
        from runtime.session_checkpoint import CheckpointStore
        from planning.newbie_tutorial_chain import NewbieTutorialChain

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            store = CheckpointStore(checkpoint_dir=tmp_dir)
            ex = _FakeExecutor()
            chain = NewbieTutorialChain(executor=ex, checkpoint_store=store)
            results = chain.run()
            # All 21 phases completed
            assert chain.completed
            # Checkpoints saved for each phase
            files = list(tmp_dir.glob("checkpoint_*.json"))
            assert len(files) >= 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_resume_from_checkpoint(self):
        from pathlib import Path
        import tempfile
        import shutil
        from runtime.session_checkpoint import CheckpointStore
        from planning.newbie_tutorial_chain import NewbieTutorialChain

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            store = CheckpointStore(checkpoint_dir=tmp_dir)
            ex = _FakeExecutor()

            # Run first chain to create checkpoint
            chain1 = NewbieTutorialChain(executor=ex, checkpoint_store=store)
            chain1.run()
            assert chain1.completed

            # Create second chain and verify it loads checkpoint
            chain2 = NewbieTutorialChain(executor=ex, checkpoint_store=store)
            chain2._load_checkpoint()
            # Should resume at phase 21 (completed)
            assert chain2.current_phase_idx == 21
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_checkpoint_without_store(self):
        ex = _FakeExecutor()
        chain = NewbieTutorialChain(executor=ex)
        results = chain.run()
        assert chain.completed
        # No errors even without checkpoint store
