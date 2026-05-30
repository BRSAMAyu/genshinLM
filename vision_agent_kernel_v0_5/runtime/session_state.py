"""Session lifecycle model: state transitions, startup protocol, incremental saves.

Implements the session lifecycle from GENSHIN_SESSION_PERSISTENCE_MODEL.md:
- SessionState enum (INITIALIZING → RUNNING → PAUSED/CHECKPOINTING/RECOVERING → SHUTTING_DOWN)
- SessionLifecycle manager with startup phases and incremental save triggers
- JSONL session logging
"""
from __future__ import annotations

import enum
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class SessionState(enum.Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    CHECKPOINTING = "checkpointing"
    RECOVERING = "recovering"
    SHUTTING_DOWN = "shutting_down"
    CRASHED = "crashed"


class SaveTrigger(enum.Enum):
    QUEST_STEP_COMPLETE = "quest_step_complete"
    REGION_CHANGE = "region_change"
    RESIN_CHANGE = "resin_change"
    CHARACTER_LEVEL_UP = "character_level_up"
    TEAM_CHANGE = "team_change"
    TIMED_INTERVAL = "timed_interval"
    PRE_TELEPORT = "pre_teleport"
    PRE_DIALOGUE = "pre_dialogue"
    PRE_DOMAIN = "pre_domain"
    HEARTBEAT_LOSS = "heartbeat_loss"
    WINDOW_DEFOCUS = "window_defocus"
    EMERGENCY = "emergency"


class LogLevel(enum.Enum):
    SESSION_START = "session_start"
    NODE_START = "node_start"
    OBSERVATION = "observation"
    ACTION = "action"
    NODE_COMPLETE = "node_complete"
    ERROR = "error"
    CHECKPOINT = "checkpoint"
    SESSION_END = "session_end"
    SAVE = "save"


# ---------------------------------------------------------------------------
# Session log entry
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SessionLogEntry:
    entry_type: str
    timestamp: float
    session_id: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "type": self.entry_type,
            "ts": self.timestamp,
            "sid": self.session_id,
            "data": self.data,
        }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[tuple[SessionState, SessionState], bool] = {
    (SessionState.INITIALIZING, SessionState.RUNNING): True,
    (SessionState.INITIALIZING, SessionState.CRASHED): True,
    (SessionState.RUNNING, SessionState.PAUSED): True,
    (SessionState.RUNNING, SessionState.CHECKPOINTING): True,
    (SessionState.RUNNING, SessionState.RECOVERING): True,
    (SessionState.RUNNING, SessionState.SHUTTING_DOWN): True,
    (SessionState.RUNNING, SessionState.CRASHED): True,
    (SessionState.PAUSED, SessionState.RUNNING): True,
    (SessionState.PAUSED, SessionState.SHUTTING_DOWN): True,
    (SessionState.PAUSED, SessionState.CRASHED): True,
    (SessionState.CHECKPOINTING, SessionState.RUNNING): True,
    (SessionState.CHECKPOINTING, SessionState.CRASHED): True,
    (SessionState.RECOVERING, SessionState.RUNNING): True,
    (SessionState.RECOVERING, SessionState.CRASHED): True,
    (SessionState.SHUTTING_DOWN, SessionState.CRASHED): True,
}


@dataclass(slots=True)
class SessionLifecycle:
    """Manage session lifecycle state transitions and logging.

    Usage::

        lifecycle = SessionLifecycle(session_dir=Path("sessions/latest"))
        lifecycle.start()
        # ... agent runs ...
        lifecycle.pause()
        lifecycle.resume()
        lifecycle.shutdown(reason="user_request")
    """

    state: SessionState = SessionState.INITIALIZING
    session_id: str = ""
    session_dir: Path = field(default_factory=lambda: Path("sessions"))
    started_at: float = 0.0
    last_save_at: float = 0.0
    save_interval_sec: float = 30.0
    full_checkpoint_interval_sec: float = 300.0
    _log_file: Any = field(default=None, repr=False)
    _incremental_count: int = 0

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = uuid.uuid4().hex[:12]
        if self.started_at == 0.0:
            self.started_at = time.perf_counter()
        self.last_save_at = self.started_at

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Transition from INITIALIZING to RUNNING."""
        self._transition(SessionState.RUNNING)
        self._open_log()
        self._write_log(LogLevel.SESSION_START, {"session_id": self.session_id})

    def pause(self) -> None:
        self._transition(SessionState.PAUSED)

    def resume(self) -> None:
        self._transition(SessionState.RUNNING)

    def begin_checkpoint(self) -> None:
        self._transition(SessionState.CHECKPOINTING)

    def end_checkpoint(self) -> None:
        self._transition(SessionState.RUNNING)

    def begin_recovery(self) -> None:
        self._transition(SessionState.RECOVERING)

    def end_recovery(self) -> None:
        self._transition(SessionState.RUNNING)

    def shutdown(self, reason: str = "user_request") -> None:
        self._transition(SessionState.SHUTTING_DOWN)
        self._write_log(LogLevel.SESSION_END, {"reason": reason, "duration": self.duration_sec})
        self._close_log()

    def mark_crashed(self) -> None:
        self.state = SessionState.CRASHED
        self._close_log()

    def _transition(self, target: SessionState) -> None:
        key = (self.state, target)
        if key not in _VALID_TRANSITIONS:
            log.warning("[Session] invalid transition %s → %s", self.state.value, target.value)
            return
        log.info("[Session] %s → %s", self.state.value, target.value)
        self.state = target

    # ------------------------------------------------------------------
    # Incremental save triggers
    # ------------------------------------------------------------------

    def should_save(self, trigger: SaveTrigger) -> bool:
        """Check if a save should happen for the given trigger."""
        if trigger in (SaveTrigger.QUEST_STEP_COMPLETE, SaveTrigger.REGION_CHANGE,
                       SaveTrigger.CHARACTER_LEVEL_UP, SaveTrigger.HEARTBEAT_LOSS,
                       SaveTrigger.EMERGENCY, SaveTrigger.WINDOW_DEFOCUS):
            return True
        if trigger == SaveTrigger.TIMED_INTERVAL:
            return (time.perf_counter() - self.last_save_at) >= self.save_interval_sec
        if trigger in (SaveTrigger.PRE_TELEPORT, SaveTrigger.PRE_DIALOGUE, SaveTrigger.PRE_DOMAIN):
            return True
        if trigger in (SaveTrigger.RESIN_CHANGE, SaveTrigger.TEAM_CHANGE):
            return (time.perf_counter() - self.last_save_at) >= self.save_interval_sec * 0.5
        return False

    def mark_saved(self) -> None:
        self.last_save_at = time.perf_counter()
        self._incremental_count += 1

    @property
    def needs_full_checkpoint(self) -> bool:
        return self._incremental_count >= 10 or (
            time.perf_counter() - self.started_at >= self.full_checkpoint_interval_sec
        )

    def reset_checkpoint_counter(self) -> None:
        self._incremental_count = 0

    # ------------------------------------------------------------------
    # Session logging
    # ------------------------------------------------------------------

    def _open_log(self) -> None:
        log_dir = self.session_dir / "session_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"session_{self.session_id}.jsonl"
        self._log_file = open(log_path, "a", encoding="utf-8")

    def _close_log(self) -> None:
        if self._log_file is not None:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

    def _write_log(self, entry_type: LogLevel, data: dict[str, Any]) -> None:
        if self._log_file is None:
            return
        entry = SessionLogEntry(
            entry_type=entry_type.value,
            timestamp=time.perf_counter(),
            session_id=self.session_id,
            data=data,
        )
        try:
            self._log_file.write(entry.to_json() + "\n")
            self._log_file.flush()
        except Exception:
            pass

    def log_action(self, action: str, target: str = "", result: str = "") -> None:
        self._write_log(LogLevel.ACTION, {"action": action, "target": target, "result": result})

    def log_error(self, code: str, message: str = "") -> None:
        self._write_log(LogLevel.ERROR, {"code": code, "message": message})

    def log_checkpoint(self, checkpoint_id: str, checkpoint_type: str) -> None:
        self._write_log(LogLevel.CHECKPOINT, {"id": checkpoint_id, "type": checkpoint_type})

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def duration_sec(self) -> float:
        return time.perf_counter() - self.started_at

    @property
    def is_running(self) -> bool:
        return self.state == SessionState.RUNNING

    @property
    def can_operate(self) -> bool:
        return self.state in (SessionState.RUNNING, SessionState.PAUSED)

    def session_info(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "started_at": self.started_at,
            "duration_sec": self.duration_sec,
            "last_save_at": self.last_save_at,
            "incremental_count": self._incremental_count,
        }
