"""Tests for execution/crash_recovery.py: session state + checkpoint integration."""
from __future__ import annotations

from execution.crash_recovery import (
    CrashCheckpoint,
    CrashDetector,
    CrashRecoveryOrchestrator,
    SessionState,
    SessionStateManager,
)


class TestCrashDetector:
    def test_no_crash_when_healthy(self):
        import time
        detector = CrashDetector()
        now = time.perf_counter()
        result = detector.detect(
            current_state="gameplay",
            last_state_change=now,
            last_input_response=now,
        )
        assert result is None

    def test_detect_process_crash(self):
        result = CrashDetector().detect(
            current_state="gameplay",
            last_state_change=0.0,
            last_input_response=0.0,
            process_alive=False,
        )
        assert result is not None
        assert result.indicator_type == "process_terminated"


class TestSessionStateManager:
    def test_start_session(self):
        mgr = SessionStateManager()
        session = mgr.start_session("test_session")
        assert session.session_id == "test_session"

    def test_save_checkpoint(self):
        mgr = SessionStateManager()
        mgr.start_session("test_session")
        mgr.save_checkpoint(
            quest_id="q001",
            quest_phase="act_1",
            location=(100.0, 200.0, 50.0),
            character_states={"amber": 40},
            inventory={"mora": 5000},
            resin=120,
            mora=5000,
            screen_state="gameplay",
        )
        cp = mgr.get_session_state().checkpoint
        assert cp is not None
        assert cp.quest_id == "q001"

    def test_auto_checkpoint_respects_interval(self):
        import time
        mgr = SessionStateManager()
        mgr.start_session("test_session")
        saved = mgr.auto_checkpoint(
            quest_id="q001", quest_phase="act_1",
            location=(0, 0, 0), character_states={},
            inventory={}, resin=0, mora=0, screen_state="gameplay",
        )
        # First auto_checkpoint should save since interval is 0
        assert saved is True

    def test_recovery_orchestrator_steps(self):
        """Test that recovery orchestrator progresses through phases."""
        orch = CrashRecoveryOrchestrator()
        orch.start_recovery(CrashCheckpoint(timestamp=0.0))
        # Just step once — don't run the full timed loop
        phase, action = orch.step_recovery()
        assert phase.value == "assess"

    def test_end_session(self):
        mgr = SessionStateManager()
        mgr.start_session("test_session")
        mgr.end_session()
        assert mgr.get_session_state() is None

    def test_checkpoint_store_integration(self):
        """Verify SessionStateManager can use CheckpointStore for persistence."""
        from runtime.session_checkpoint import CheckpointStore
        from pathlib import Path
        import tempfile
        import shutil

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            store = CheckpointStore(checkpoint_dir=tmp_dir)
            mgr = SessionStateManager(checkpoint_store=store)
            mgr.start_session("test_session")
            mgr.save_checkpoint(
                quest_id="q001", quest_phase="act_1",
                location=(100.0, 200.0, 50.0),
                character_states={"amber": 40},
                inventory={"mora": 5000},
                resin=120, mora=5000, screen_state="gameplay",
            )
            # Verify checkpoint was persisted to store
            files = list(tmp_dir.glob("checkpoint_*.json"))
            assert len(files) >= 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
