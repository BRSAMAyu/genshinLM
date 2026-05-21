from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from recording.record_schema import RecordEvent, RecordSessionMeta

logger = logging.getLogger("record_session")


class RecordSession:
    """Manages low-frequency serialization of events to disk under data/recordings/{session_id}/."""

    def __init__(
        self,
        session_id: str,
        capsule_id: str,
        root_dir: str | Path | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        self.session_id = session_id
        self.capsule_id = capsule_id
        
        # Resolve output directory
        base = Path(root_dir) if root_dir else Path(__file__).resolve().parents[1]
        self.output_dir = base / "data" / "recordings" / session_id
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.session_json_path = self.output_dir / "session.json"
        self.events_jsonl_path = self.output_dir / "events.jsonl"
        self.frame_refs_jsonl_path = self.output_dir / "frame_refs.jsonl"

        self.meta = RecordSessionMeta(
            session_id=session_id,
            capsule_id=capsule_id,
            start_timestamp=time.time(),
            metadata=metadata or {},
        )
        self._write_meta()
        logger.info("Initialized RecordSession '%s' for capsule '%s'", session_id, capsule_id)

    def add_event(self, event: RecordEvent) -> None:
        """Append a structured RecordEvent to the events log."""
        # Convert event dataclass to dict
        event_dict = {
            "timestamp": event.timestamp,
            "event_type": event.event_type,
            "frame_id": event.frame_id,
            "frame_hash": event.frame_hash,
            "screen_state": event.screen_state,
            "active_skill": event.active_skill,
            "physical_input_event": event.physical_input_event,
            "state_bus_snapshot": event.state_bus_snapshot,
            "verifier_results": event.verifier_results,
            "interrupts": event.interrupts,
            "user_marker": event.user_marker,
            "metadata": event.metadata,
        }
        
        # Append to events.jsonl
        with open(self.events_jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_dict, ensure_ascii=False) + "\n")

        # If it's a frame event, also append a reference entry to frame_refs.jsonl
        if event.event_type == "frame" or event.frame_id is not None:
            ref_dict = {
                "timestamp": event.timestamp,
                "frame_id": event.frame_id,
                "frame_hash": event.frame_hash,
            }
            with open(self.frame_refs_jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ref_dict, ensure_ascii=False) + "\n")

    def close(self) -> None:
        """Mark session end and save updated metadata."""
        # Update metadata with end timestamp
        self.meta = RecordSessionMeta(
            session_id=self.meta.session_id,
            capsule_id=self.meta.capsule_id,
            start_timestamp=self.meta.start_timestamp,
            end_timestamp=time.time(),
            metadata=self.meta.metadata,
        )
        self._write_meta()
        logger.info("Closed RecordSession '%s'", self.session_id)

    def _write_meta(self) -> None:
        meta_dict = {
            "session_id": self.meta.session_id,
            "capsule_id": self.meta.capsule_id,
            "start_timestamp": self.meta.start_timestamp,
            "end_timestamp": self.meta.end_timestamp,
            "metadata": self.meta.metadata,
        }
        with open(self.session_json_path, "w", encoding="utf-8") as f:
            json.dump(meta_dict, f, indent=2, ensure_ascii=False)
