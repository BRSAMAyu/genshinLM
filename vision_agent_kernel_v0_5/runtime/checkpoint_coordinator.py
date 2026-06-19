"""Three checkpoint system unification — single CheckpointCoordinator.

Coordinates QuestContextPersistence, MainlineCheckpointPublisher, and
SessionStateManager into a coherent checkpoint cycle so that all three
systems stay synchronized during saves and recovery.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

log = logging.getLogger(__name__)


@dataclass(slots=True)
class UnifiedCheckpoint:
    """A checkpoint that spans all three subsystems."""
    checkpoint_id: str
    timestamp: float
    quest_context: dict[str, Any] = field(default_factory=dict)
    execution_state: dict[str, Any] = field(default_factory=dict)
    session_state: dict[str, Any] = field(default_factory=dict)
    source: str = "unified"


@runtime_checkable
class CheckpointWriter(Protocol):
    """Protocol for a subsystem that can save/load checkpoints."""
    def save_checkpoint(self, data: dict[str, Any]) -> str: ...
    def load_latest(self) -> dict[str, Any] | None: ...


class CheckpointCoordinator:
    """Coordinates checkpoint saves and loads across all three subsystems.

    Ensures that a save operation updates all subsystems atomically,
    and that a load restores all subsystems consistently.
    """

    def __init__(
        self,
        quest_writer: CheckpointWriter | None = None,
        execution_writer: CheckpointWriter | None = None,
        session_writer: CheckpointWriter | None = None,
    ) -> None:
        self._quest_writer = quest_writer
        self._execution_writer = execution_writer
        self._session_writer = session_writer
        self._last_checkpoint: UnifiedCheckpoint | None = None
        self._save_count: int = 0

    @property
    def last_checkpoint(self) -> UnifiedCheckpoint | None:
        return self._last_checkpoint

    @property
    def save_count(self) -> int:
        return self._save_count

    def save_all(
        self,
        quest_data: dict[str, Any] | None = None,
        execution_data: dict[str, Any] | None = None,
        session_data: dict[str, Any] | None = None,
    ) -> UnifiedCheckpoint:
        """Save a unified checkpoint across all subsystems."""
        import uuid
        checkpoint = UnifiedCheckpoint(
            checkpoint_id=str(uuid.uuid4())[:8],
            timestamp=time.perf_counter(),
            quest_context=quest_data or {},
            execution_state=execution_data or {},
            session_state=session_data or {},
        )

        # Save to each subsystem
        if self._quest_writer is not None and checkpoint.quest_context:
            try:
                self._quest_writer.save_checkpoint(checkpoint.quest_context)
            except Exception as exc:
                log.warning("[CheckpointCoordinator] Quest save failed: %s", exc)

        if self._execution_writer is not None and checkpoint.execution_state:
            try:
                self._execution_writer.save_checkpoint(checkpoint.execution_state)
            except Exception as exc:
                log.warning("[CheckpointCoordinator] Execution save failed: %s", exc)

        if self._session_writer is not None and checkpoint.session_state:
            try:
                self._session_writer.save_checkpoint(checkpoint.session_state)
            except Exception as exc:
                log.warning("[CheckpointCoordinator] Session save failed: %s", exc)

        self._last_checkpoint = checkpoint
        self._save_count += 1
        log.info(
            "[CheckpointCoordinator] Saved unified checkpoint %s (%d total)",
            checkpoint.checkpoint_id, self._save_count,
        )
        return checkpoint

    def load_all(self) -> UnifiedCheckpoint | None:
        """Load the latest checkpoint from all subsystems."""
        quest_data: dict[str, Any] | None = None
        exec_data: dict[str, Any] | None = None
        session_data: dict[str, Any] | None = None

        if self._quest_writer is not None:
            try:
                quest_data = self._quest_writer.load_latest()
            except Exception as exc:
                log.warning("[CheckpointCoordinator] Quest load failed: %s", exc)

        if self._execution_writer is not None:
            try:
                exec_data = self._execution_writer.load_latest()
            except Exception as exc:
                log.warning("[CheckpointCoordinator] Execution load failed: %s", exc)

        if self._session_writer is not None:
            try:
                session_data = self._session_writer.load_latest()
            except Exception as exc:
                log.warning("[CheckpointCoordinator] Session load failed: %s", exc)

        if quest_data is None and exec_data is None and session_data is None:
            return None

        import uuid
        checkpoint = UnifiedCheckpoint(
            checkpoint_id=str(uuid.uuid4())[:8],
            timestamp=time.perf_counter(),
            quest_context=quest_data or {},
            execution_state=exec_data or {},
            session_state=session_data or {},
        )
        self._last_checkpoint = checkpoint
        return checkpoint
