"""Crash recovery system: detecting game crashes and recovering to a known state.

Covers S-32: Crash detection, state recovery, and session resumption.
Monitors for crash indicators, saves checkpoint state, and orchestrates
recovery to minimize lost progress.

Integrates with:
- core/state_bus.py for state management
- core/events.py for interrupt handling
- planning/quest_state_machine.py for quest state
- perception/genshin_screen_classifier.py for state detection
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Crash types
# ---------------------------------------------------------------------------

class CrashType(str, Enum):
    PROCESS_CRASH = "process_crash"        # Game process terminated
    GRAPHICS_CRASH = "graphics_crash"      # GPU driver failure
    NETWORK_DISCONNECT = "network_disconnect"  # Server connection lost
    STUCK_STATE = "stuck_state"            # UI stuck, no response
    UNKNOWN = "unknown"


class RecoveryPhase(str, Enum):
    DETECT = "detect"          # Detecting crash
    ASSESS = "assess"          # Assessing damage
    LAUNCH = "launch"          # Re-launching game
    RECONNECT = "reconnect"    # Reconnecting to game
    RESTORE = "restore"        # Restoring state
    RESUME = "resume"          # Resuming operations


@dataclass(slots=True)
class CrashCheckpoint:
    """Saved checkpoint state for recovery."""
    timestamp: float = 0.0
    quest_id: str = ""
    quest_phase: str = ""
    location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    character_states: dict[str, int] = field(default_factory=dict)
    inventory_snapshot: dict[str, int] = field(default_factory=dict)
    resin_state: int = 0
    mora_state: int = 0
    last_screen_state: str = ""
    pending_resin_tasks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CrashReport:
    """Detailed crash report."""
    crash_type: CrashType
    detected_at: float
    last_checkpoint: CrashCheckpoint | None = None
    session_start_time: float = 0.0
    progress_lost_pct: float = 0.0
    recovery_action: str = ""
    restart_required: bool = False


# ---------------------------------------------------------------------------
# Crash detector
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CrashIndicator:
    """Indicators of a crash condition."""
    indicator_type: str
    confidence: float = 0.0
    severity: str = "medium"
    description: str = ""


class CrashDetector:
    """Detects various types of game crashes."""

    # Crash indicator patterns
    STUCK_THRESHOLD_SEC = 30.0     # No state change for 30 sec
    BLACK_SCREEN_THRESHOLD_SEC = 10.0
    NO_INPUT_RESPONSE_SEC = 5.0

    def __init__(self) -> None:
        self._last_state_change: float = 0.0
        self._last_input_response: float = 0.0
        self._consecutive_same_states: int = 0

    def detect(
        self,
        current_state: str,
        last_state_change: float,
        last_input_response: float,
        process_alive: bool = True,
    ) -> CrashIndicator | None:
        """Detect if a crash has occurred.

        Returns CrashIndicator if crash detected, None otherwise.
        """
        now = time.perf_counter()

        # Process check
        if not process_alive:
            return CrashIndicator(
                indicator_type="process_terminated",
                confidence=1.0,
                severity="critical",
                description="Game process has terminated",
            )

        # Stuck state check
        state_change_gap = now - last_state_change
        if state_change_gap > self.STUCK_THRESHOLD_SEC:
            return CrashIndicator(
                indicator_type="stuck_state",
                confidence=min(1.0, state_change_gap / 60.0),
                severity="high",
                description=f"No state change for {state_change_gap:.0f}s",
            )

        # Black screen detection (handled by screen classifier)
        if current_state in ("black_screen", "loading_screen"):
            if state_change_gap > self.BLACK_SCREEN_THRESHOLD_SEC:
                return CrashIndicator(
                    indicator_type="black_screen_timeout",
                    confidence=0.8,
                    severity="high",
                    description="Black screen for too long",
                )

        # Input response check
        input_gap = now - last_input_response
        if input_gap > self.NO_INPUT_RESPONSE_SEC:
            return CrashIndicator(
                indicator_type="no_input_response",
                confidence=min(0.9, input_gap / 10.0),
                severity="medium",
                description=f"No input response for {input_gap:.0f}s",
            )

        return None

    def update_state_change(self, now: float) -> None:
        """Update last state change timestamp."""
        self._last_state_change = now

    def update_input_response(self, now: float) -> None:
        """Update last input response timestamp."""
        self._last_input_response = now


# ---------------------------------------------------------------------------
# Recovery orchestrator
# ---------------------------------------------------------------------------

class CrashRecoveryOrchestrator:
    """Orchestrates crash recovery process.

    State machine:
    1. DETECT -> 2. ASSESS -> 3. LAUNCH/RECONNECT -> 4. RESTORE -> 5. RESUME
    """

    # Recovery time estimates
    RESTART_TIME_SEC = 60.0       # Time to restart game
    RECONNECT_TIME_SEC = 30.0    # Time to reconnect
    RESTORE_TIME_SEC = 15.0      # Time to restore state

    def __init__(self) -> None:
        self._detector = CrashDetector()
        self._current_phase: RecoveryPhase = RecoveryPhase.DETECT
        self._recovery_start: float = 0.0
        self._checkpoint: CrashCheckpoint | None = None
        self._recovery_history: list[CrashReport] = []

    @property
    def current_phase(self) -> RecoveryPhase:
        return self._current_phase

    def start_recovery(self, checkpoint: CrashCheckpoint | None = None) -> None:
        """Start recovery process."""
        self._checkpoint = checkpoint
        self._current_phase = RecoveryPhase.DETECT
        self._recovery_start = time.perf_counter()
        log.info("[CrashRecovery] starting recovery, checkpoint=%s",
                 "present" if checkpoint else "none")

    def step_recovery(self) -> tuple[RecoveryPhase, str]:
        """Execute one step of recovery.

        Returns (next_phase, action_description).
        """
        now = time.perf_counter()
        elapsed = now - self._recovery_start

        if self._current_phase == RecoveryPhase.DETECT:
            self._current_phase = RecoveryPhase.ASSESS
            return RecoveryPhase.ASSESS, "Crash detected, assessing damage"

        if self._current_phase == RecoveryPhase.ASSESS:
            self._current_phase = RecoveryPhase.LAUNCH
            return RecoveryPhase.LAUNCH, "Assessment complete, launching recovery"

        if self._current_phase == RecoveryPhase.LAUNCH:
            if elapsed < self.RESTART_TIME_SEC:
                return RecoveryPhase.LAUNCH, "Waiting for game to launch..."
            self._current_phase = RecoveryPhase.RECONNECT
            return RecoveryPhase.RECONNECT, "Game launched, reconnecting"

        if self._current_phase == RecoveryPhase.RECONNECT:
            if elapsed < self.RESTART_TIME_SEC + self.RECONNECT_TIME_SEC:
                return RecoveryPhase.RECONNECT, "Reconnecting to game server..."
            self._current_phase = RecoveryPhase.RESTORE
            return RecoveryPhase.RESTORE, "Reconnected, restoring state"

        if self._current_phase == RecoveryPhase.RESTORE:
            self._current_phase = RecoveryPhase.RESUME
            return RecoveryPhase.RESUME, "State restored, resuming operations"

        if self._current_phase == RecoveryPhase.RESUME:
            return RecoveryPhase.RESUME, "Recovery complete, resuming normal operations"

        return self._current_phase, "Unknown phase"

    def execute_recovery_loop(
        self,
        max_wait_sec: float = 180.0,
    ) -> dict[str, Any]:
        """Execute full recovery loop.

        Returns recovery result dictionary.
        """
        self.start_recovery(self._checkpoint)
        result: dict[str, Any] = {"success": False, "phases_completed": []}

        while True:
            phase, action = self.step_recovery()
            result["phases_completed"].append({"phase": phase.value, "action": action})
            log.info("[CrashRecovery] phase=%s action=%s", phase.value, action)

            if phase == RecoveryPhase.RESUME:
                result["success"] = True
                break

            # Check timeout
            if time.perf_counter() - self._recovery_start > max_wait_sec:
                result["success"] = False
                result["error"] = "Recovery timeout"
                log.warning("[CrashRecovery] recovery timeout after %.0fs", max_wait_sec)
                break

        result["total_time_sec"] = time.perf_counter() - self._recovery_start
        return result

    def get_checkpoint(self) -> CrashCheckpoint | None:
        """Get current checkpoint for saving state."""
        return self._checkpoint

    def set_checkpoint(self, checkpoint: CrashCheckpoint) -> None:
        """Set/checkpoint for recovery."""
        self._checkpoint = checkpoint
        log.info("[CrashRecovery] checkpoint saved at t=%.1f", checkpoint.timestamp)


# ---------------------------------------------------------------------------
# Session state manager
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SessionState:
    """Current session state for crash recovery."""
    session_id: str
    start_time: float
    current_quest: str = ""
    quest_progress: float = 0.0
    checkpoint: CrashCheckpoint | None = None
    last_checkpoint_time: float = 0.0
    checkpoint_interval_sec: float = 60.0  # Save checkpoint every 60 sec


class SessionStateManager:
    """Manages session state for crash recovery.

    Periodically saves checkpoints and maintains recovery state.
    Optionally persists checkpoints via runtime.session_checkpoint.CheckpointStore.
    """

    def __init__(self, checkpoint_store: Any | None = None) -> None:
        self._current_session: SessionState | None = None
        self._recovery_orchestrator = CrashRecoveryOrchestrator()
        self._checkpoint_store = checkpoint_store

    def start_session(self, session_id: str) -> SessionState:
        """Start a new session."""
        self._current_session = SessionState(
            session_id=session_id,
            start_time=time.perf_counter(),
        )
        log.info("[SessionMgr] started session %s", session_id)
        return self._current_session

    def update_quest_progress(self, quest_id: str, progress: float) -> None:
        """Update current quest progress."""
        if self._current_session:
            self._current_session.current_quest = quest_id
            self._current_session.quest_progress = progress

    def save_checkpoint(
        self,
        quest_id: str,
        quest_phase: str,
        location: tuple[float, float, float],
        character_states: dict[str, int],
        inventory: dict[str, int],
        resin: int,
        mora: int,
        screen_state: str,
    ) -> None:
        """Save a recovery checkpoint."""
        if self._current_session is None:
            return

        now = time.perf_counter()
        checkpoint = CrashCheckpoint(
            timestamp=now,
            quest_id=quest_id,
            quest_phase=quest_phase,
            location=location,
            character_states=character_states,
            inventory_snapshot=inventory,
            resin_state=resin,
            mora_state=mora,
            last_screen_state=screen_state,
        )

        self._current_session.checkpoint = checkpoint
        self._current_session.last_checkpoint_time = now
        self._recovery_orchestrator.set_checkpoint(checkpoint)

        # Persist to CheckpointStore if available
        if self._checkpoint_store is not None:
            try:
                session_id = self._current_session.session_id
                cp = self._checkpoint_store.create_checkpoint(
                    session_id=session_id,
                    triggered_by="auto_checkpoint",
                    account_snapshot={"resin": resin, "mora": mora},
                    task_state={"quest_id": quest_id, "quest_phase": quest_phase},
                    location_snapshot={"x": location[0], "y": location[1], "z": location[2]},
                )
                self._checkpoint_store.save(cp)
            except Exception as exc:
                log.debug("[SessionMgr] checkpoint store save failed: %s", exc)

        log.info("[SessionMgr] checkpoint saved for quest=%s", quest_id)

    def auto_checkpoint(
        self,
        quest_id: str,
        quest_phase: str,
        location: tuple[float, float, float],
        character_states: dict[str, int],
        inventory: dict[str, int],
        resin: int,
        mora: int,
        screen_state: str,
    ) -> bool:
        """Auto-save checkpoint if interval has passed.

        Returns True if checkpoint was saved.
        """
        if self._current_session is None:
            return False

        now = time.perf_counter()
        elapsed = now - self._current_session.last_checkpoint_time

        if elapsed >= self._current_session.checkpoint_interval_sec:
            self.save_checkpoint(
                quest_id, quest_phase, location,
                character_states, inventory, resin, mora, screen_state,
            )
            return True
        return False

    def recover_session(self) -> dict[str, Any]:
        """Recover session from checkpoint."""
        if self._current_session is None:
            return {"success": False, "error": "No active session"}

        checkpoint = self._current_session.checkpoint
        self._recovery_orchestrator.start_recovery(checkpoint)
        result = self._recovery_orchestrator.execute_recovery_loop()

        if result["success"]:
            log.info("[SessionMgr] session %s recovered successfully",
                     self._current_session.session_id)
        return result

    def end_session(self) -> None:
        """End current session."""
        if self._current_session:
            log.info("[SessionMgr] ended session %s",
                     self._current_session.session_id)
        self._current_session = None

    def get_session_state(self) -> SessionState | None:
        """Get current session state."""
        return self._current_session