"""Tests for dynamic low-frequency record sessions and event auditing."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest

from recording.record_schema import RecordEvent
from recording.record_session import RecordSession


@pytest.fixture
def temp_record_dir(tmp_path: Path) -> Path:
    """Provides a clean temporary directory for recording files."""
    return tmp_path / "recordings"


def test_record_session_writes_capsule_scoped_events(temp_record_dir: Path) -> None:
    """Verify that RecordSession initiates, logs capsule events, indexes frames, and saves JSONL metadata."""
    session_id = "test_session_123"
    capsule_id = "hsr"
    
    # 1. Initialize session
    session = RecordSession(
        session_id=session_id,
        capsule_id=capsule_id,
        root_dir=temp_record_dir,
        metadata={"user_intent": "grind_calyx"},
    )

    session_dir = temp_record_dir / "data" / "recordings" / session_id
    assert session_dir.exists()
    assert (session_dir / "session.json").exists()

    # 2. Add dynamic events
    # Event 1: State bus update
    evt_state = RecordEvent(
        timestamp=time.time(),
        event_type="state_bus",
        screen_state="dialog",
        active_skill="hsr_dialog_progression",
        state_bus_snapshot={"hsr.screen_state": "dialog"},
    )
    session.add_event(evt_state)

    # Event 2: Frame input trigger (frame reference)
    evt_frame = RecordEvent(
        timestamp=time.time(),
        event_type="frame",
        frame_id=42,
        frame_hash="abcde12345",
        physical_input_event={"key": "F", "action": "press"},
    )
    session.add_event(evt_frame)

    # 3. Close the session
    session.close()

    # 4. Read back and verify files
    # Check session.json meta
    with open(session_dir / "session.json", encoding="utf-8") as f:
        meta = json.load(f)
        assert meta["session_id"] == session_id
        assert meta["capsule_id"] == capsule_id
        assert meta["metadata"]["user_intent"] == "grind_calyx"
        assert meta["end_timestamp"] is not None
        assert meta["end_timestamp"] >= meta["start_timestamp"]

    # Check events.jsonl
    events = []
    with open(session_dir / "events.jsonl", encoding="utf-8") as f:
        for line in f:
            events.append(json.loads(line))
            
    assert len(events) == 2
    assert events[0]["event_type"] == "state_bus"
    assert events[0]["screen_state"] == "dialog"
    assert events[0]["state_bus_snapshot"] == {"hsr.screen_state": "dialog"}

    assert events[1]["event_type"] == "frame"
    assert events[1]["frame_id"] == 42
    assert events[1]["frame_hash"] == "abcde12345"
    assert events[1]["physical_input_event"] == {"key": "F", "action": "press"}

    # Check frame_refs.jsonl (only the frame event or events with non-None frame_id should be indexed)
    frame_refs = []
    with open(session_dir / "frame_refs.jsonl", encoding="utf-8") as f:
        for line in f:
            frame_refs.append(json.loads(line))

    assert len(frame_refs) == 1
    assert frame_refs[0]["frame_id"] == 42
    assert frame_refs[0]["frame_hash"] == "abcde12345"
