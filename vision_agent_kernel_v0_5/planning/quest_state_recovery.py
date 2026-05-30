"""Q-30: Quest state recovery from inconsistencies.

Detects and recovers from quest state inconsistencies that can
occur due to save corruption, crash recovery, or out-of-order
actions.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class InconsistencyType(str, Enum):
    MISSING_STEP = "missing_step"        # Expected step not found
    WRONG_ORDER = "wrong_order"          # Steps completed out of order
    NPC_MISSING = "npc_missing"           # Expected NPC not at location
    ITEM_MISSING = "item_missing"        # Required item not in inventory
    LOCATION_MISMATCH = "location_mismatch"  # Not at expected location
    STATE_CORRUPTED = "state_corrupted"  # General state corruption


@dataclass(frozen=True, slots=True)
class StateInconsistency:
    """Detected state inconsistency."""
    inconsistency_type: InconsistencyType
    expected_value: str
    actual_value: str | None
    severity: str  # "low", "medium", "high", "critical"
    recovery_suggestion: str


@dataclass(frozen=True, slots=True)
class RecoveryAction:
    """A recovery action to fix inconsistency."""
    action_type: str  # "teleport", "npc_talk", "item_use", "retry_step"
    target: str
    reason: str
    estimated_time_seconds: float


class QuestStateRecovery:
    """Recover from quest state inconsistencies."""

    def __init__(
        self,
        teleport_callback: Any = None,
        on_recovery_start: Any = None,
        on_recovery_complete: Any = None,
    ) -> None:
        self._teleport_callback = teleport_callback
        self._on_recovery_start = on_recovery_start
        self._on_recovery_complete = on_recovery_complete

        self._known_quests: dict[str, dict[str, Any]] = {}
        self._last_checkpoint: dict[str, Any] = {}
        self._inconsistency_history: list[StateInconsistency] = []

    def register_quest(
        self,
        quest_id: str,
        steps: list[dict[str, Any]],
        checkpoints: list[str] | None = None,
    ) -> None:
        """Register a quest for inconsistency tracking.

        Args:
            quest_id: Unique quest identifier
            steps: Ordered list of quest steps
            checkpoints: Step IDs that are checkpoints
        """
        self._known_quests[quest_id] = {
            "steps": steps,
            "checkpoints": checkpoints or [],
            "current_step": 0,
        }
        log.info("[QuestStateRecovery] Registered quest %s with %d steps", quest_id, len(steps))

    def set_checkpoint(self, quest_id: str, checkpoint_name: str, state: dict[str, Any]) -> None:
        """Save a checkpoint for recovery.

        Args:
            quest_id: Quest identifier
            checkpoint_name: Name of checkpoint
            state: State snapshot
        """
        key = f"{quest_id}:{checkpoint_name}"
        self._last_checkpoint[key] = {
            "state": state,
            "timestamp": time.perf_counter(),
        }
        log.debug("[QuestStateRecovery] Checkpoint saved: %s", key)

    def detect_inconsistency(
        self,
        quest_id: str,
        expected_step: int,
        actual_step: int | None,
        expected_location: str | None = None,
        actual_location: str | None = None,
        expected_npc: str | None = None,
        actual_npc_found: bool = True,
    ) -> StateInconsistency | None:
        """Detect inconsistency between expected and actual state.

        Args:
            quest_id: Quest identifier
            expected_step: Step that should be active
            actual_step: Step that appears active (None if unknown)
            expected_location: Expected location name
            actual_location: Actual location name
            expected_npc: Expected NPC name
            actual_npc_found: Whether the NPC was found

        Returns:
            StateInconsistency if found, None otherwise
        """
        if actual_step is not None and actual_step != expected_step:
            severity = "high" if abs(actual_step - expected_step) > 1 else "medium"
            return StateInconsistency(
                inconsistency_type=InconsistencyType.WRONG_ORDER,
                expected_value=f"step {expected_step}",
                actual_value=f"step {actual_step}",
                severity=severity,
                recovery_suggestion=f"Return to step {expected_step} via quest menu",
            )

        if expected_location and actual_location and expected_location != actual_location:
            return StateInconsistency(
                inconsistency_type=InconsistencyType.LOCATION_MISMATCH,
                expected_value=expected_location,
                actual_value=actual_location,
                severity="high",
                recovery_suggestion=f"Teleport to {expected_location}",
            )

        if expected_npc and not actual_npc_found:
            return StateInconsistency(
                inconsistency_type=InconsistencyType.NPC_MISSING,
                expected_value=expected_npc,
                actual_value=None,
                severity="medium",
                recovery_suggestion="Check if NPC is at different location or wait for respawn",
            )

        return None

    def generate_recovery_actions(
        self,
        quest_id: str,
        inconsistency: StateInconsistency,
    ) -> list[RecoveryAction]:
        """Generate recovery actions for an inconsistency.

        Args:
            quest_id: Quest identifier
            inconsistency: The inconsistency to recover from

        Returns:
            List of recovery actions to execute
        """
        actions: list[RecoveryAction] = []

        if inconsistency.inconsistency_type == InconsistencyType.LOCATION_MISMATCH:
            actions.append(RecoveryAction(
                action_type="teleport",
                target=inconsistency.expected_value,
                reason="Return to correct location",
                estimated_time_seconds=5.0,
            ))

        elif inconsistency.inconsistency_type == InconsistencyType.WRONG_ORDER:
            actions.append(RecoveryAction(
                action_type="retry_step",
                target=f"step {inconsistency.expected_value}",
                reason="Complete skipped step",
                estimated_time_seconds=30.0,
            ))

        elif inconsistency.inconsistency_type == InconsistencyType.NPC_MISSING:
            actions.append(RecoveryAction(
                action_type="npc_talk",
                target=inconsistency.expected_value,
                reason="Find required NPC",
                estimated_time_seconds=10.0,
            ))

        return actions

    def execute_recovery(
        self,
        actions: list[RecoveryAction],
    ) -> bool:
        """Execute recovery actions.

        Args:
            actions: Recovery actions to execute

        Returns:
            True if recovery successful
        """
        if self._on_recovery_start:
            try:
                self._on_recovery_start(len(actions))
            except Exception as exc:
                log.warning("[QuestStateRecovery] Recovery start callback failed: %s", exc)

        success = True

        for action in actions:
            log.info(
                "[QuestStateRecovery] Executing: %s -> %s (%s)",
                action.action_type, action.target, action.reason
            )

            if action.action_type == "teleport" and self._teleport_callback:
                try:
                    self._teleport_callback(action.target)
                except Exception as exc:
                    log.warning("[QuestStateRecovery] Teleport failed: %s", exc)
                    success = False

            # Add delay between actions
            time.sleep(min(action.estimated_time_seconds, 2.0))

        if self._on_recovery_complete:
            try:
                self._on_recovery_complete(success)
            except Exception as exc:
                log.warning("[QuestStateRecovery] Recovery complete callback failed: %s", exc)

        return success

    def restore_checkpoint(
        self,
        quest_id: str,
        checkpoint_name: str,
    ) -> dict[str, Any] | None:
        """Restore state from a checkpoint.

        Args:
            quest_id: Quest identifier
            checkpoint_name: Checkpoint to restore

        Returns:
            Saved state or None if checkpoint not found
        """
        key = f"{quest_id}:{checkpoint_name}"
        if key in self._last_checkpoint:
            state = self._last_checkpoint[key]["state"]
            log.info("[QuestStateRecovery] Restored checkpoint: %s", key)
            return state
        return None

    def record_inconsistency(self, inconsistency: StateInconsistency) -> None:
        """Record an inconsistency for history tracking."""
        self._inconsistency_history.append(inconsistency)
        # Keep only recent history
        if len(self._inconsistency_history) > 50:
            self._inconsistency_history.pop(0)
        log.warning(
            "[QuestStateRecovery] Inconsistency recorded: %s (%s)",
            inconsistency.inconsistency_type.value, inconsistency.severity
        )

    def get_recovery_stats(self) -> dict[str, Any]:
        """Get recovery statistics."""
        total = len(self._inconsistency_history)
        critical = sum(1 for i in self._inconsistency_history if i.severity == "critical")
        high = sum(1 for i in self._inconsistency_history if i.severity == "high")

        return {
            "total_inconsistencies": total,
            "critical_count": critical,
            "high_severity_count": high,
            "checkpoints_saved": len(self._last_checkpoint),
            "quests_tracked": len(self._known_quests),
        }

    def reset(self) -> None:
        """Reset recovery state."""
        self._inconsistency_history = []
        log.info("[QuestStateRecovery] Recovery state reset")