"""Tests for runtime/session_state.py: session lifecycle, state transitions, logging."""
from __future__ import annotations

import time
from pathlib import Path
from runtime.session_state import (
    SaveTrigger,
    SessionLifecycle,
    SessionLogEntry,
    SessionState,
)


class TestSessionStateEnum:
    def test_has_7_states(self):
        assert len(SessionState) == 7
        names = {s.value for s in SessionState}
        assert "initializing" in names
        assert "running" in names
        assert "crashed" in names


class TestSessionLifecycle:
    def test_starts_initializing(self):
        lc = SessionLifecycle()
        assert lc.state == SessionState.INITIALIZING
        assert lc.session_id != ""

    def test_start_transitions_to_running(self):
        lc = SessionLifecycle(session_dir=Path("test_sessions"))
        lc.start()
        assert lc.state == SessionState.RUNNING
        assert lc.is_running
        lc.shutdown("test")
        # Cleanup
        import shutil
        if Path("test_sessions").exists():
            shutil.rmtree("test_sessions")

    def test_full_lifecycle(self):
        lc = SessionLifecycle(session_dir=Path("test_sessions"))
        lc.start()
        assert lc.state == SessionState.RUNNING
        lc.pause()
        assert lc.state == SessionState.PAUSED
        lc.resume()
        assert lc.state == SessionState.RUNNING
        lc.begin_checkpoint()
        assert lc.state == SessionState.CHECKPOINTING
        lc.end_checkpoint()
        assert lc.state == SessionState.RUNNING
        lc.begin_recovery()
        assert lc.state == SessionState.RECOVERING
        lc.end_recovery()
        assert lc.state == SessionState.RUNNING
        lc.shutdown("user_request")
        assert lc.state == SessionState.SHUTTING_DOWN

        import shutil
        if Path("test_sessions").exists():
            shutil.rmtree("test_sessions")

    def test_invalid_transition_ignored(self):
        lc = SessionLifecycle()
        # Cannot go directly from INITIALIZING to PAUSED
        lc.pause()
        assert lc.state == SessionState.INITIALIZING

    def test_mark_crashed(self):
        lc = SessionLifecycle()
        lc.mark_crashed()
        assert lc.state == SessionState.CRASHED

    def test_duration_sec(self):
        lc = SessionLifecycle()
        lc.started_at = time.perf_counter() - 5.0
        assert lc.duration_sec >= 4.9

    def test_can_operate(self):
        lc = SessionLifecycle()
        assert not lc.can_operate
        lc.state = SessionState.RUNNING
        assert lc.can_operate
        lc.state = SessionState.PAUSED
        assert lc.can_operate
        lc.state = SessionState.SHUTTING_DOWN
        assert not lc.can_operate

    def test_session_info(self):
        lc = SessionLifecycle(session_id="test123")
        info = lc.session_info()
        assert info["session_id"] == "test123"
        assert info["state"] == "initializing"


class TestSaveTrigger:
    def test_high_priority_triggers_always_save(self):
        lc = SessionLifecycle()
        for trigger in (SaveTrigger.QUEST_STEP_COMPLETE, SaveTrigger.REGION_CHANGE,
                        SaveTrigger.CHARACTER_LEVEL_UP, SaveTrigger.HEARTBEAT_LOSS,
                        SaveTrigger.EMERGENCY, SaveTrigger.WINDOW_DEFOCUS):
            assert lc.should_save(trigger) is True, f"{trigger} should always trigger save"

    def test_timed_interval_requires_elapsed(self):
        lc = SessionLifecycle()
        lc.last_save_at = time.perf_counter()  # just saved
        assert lc.should_save(SaveTrigger.TIMED_INTERVAL) is False
        lc.last_save_at = time.perf_counter() - 60.0  # saved 60s ago
        assert lc.should_save(SaveTrigger.TIMED_INTERVAL) is True

    def test_mark_saved_resets_timer(self):
        lc = SessionLifecycle()
        lc.last_save_at = time.perf_counter() - 60.0
        assert lc.should_save(SaveTrigger.TIMED_INTERVAL) is True
        lc.mark_saved()
        assert lc.should_save(SaveTrigger.TIMED_INTERVAL) is False

    def test_needs_full_checkpoint(self):
        lc = SessionLifecycle()
        assert not lc.needs_full_checkpoint
        for _ in range(10):
            lc.mark_saved()
        assert lc.needs_full_checkpoint
        lc.reset_checkpoint_counter()
        assert not lc.needs_full_checkpoint


class TestSessionLogging:
    def test_log_entry_serialization(self):
        entry = SessionLogEntry(
            entry_type="action",
            timestamp=1234.5,
            session_id="abc",
            data={"action": "click"},
        )
        j = entry.to_json()
        assert '"type": "action"' in j
        assert '"sid": "abc"' in j

    def test_session_log_file_created(self):
        import shutil
        lc = SessionLifecycle(session_dir=Path("test_sessions_log"))
        lc.start()
        lc.log_action("click", target="button", result="ok")
        lc.log_error("STUCK", message="nav failed")
        lc.shutdown("test")

        log_dir = Path("test_sessions_log") / "session_logs"
        assert log_dir.exists()
        log_files = list(log_dir.glob("session_*.jsonl"))
        assert len(log_files) == 1

        content = log_files[0].read_text()
        assert "session_start" in content
        assert "click" in content
        assert "STUCK" in content
        assert "session_end" in content

        shutil.rmtree("test_sessions_log")
