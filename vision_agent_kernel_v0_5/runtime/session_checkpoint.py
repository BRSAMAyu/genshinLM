"""Session checkpoint system: incremental/full checkpoints with rolling window.

Implements the checkpoint system from GENSHIN_SESSION_PERSISTENCE_MODEL.md:
- CheckpointType (incremental vs full)
- Rolling window: keep last 20 checkpoints, compress old ones
- Atomic write-rename for safe persistence
- Checkpoint validation with checksum
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class CheckpointType(enum.Enum if False else type("", (), {})):
    """Checkpoint type marker."""
    pass


@dataclass(frozen=True, slots=True)
class _CheckpointType:
    INCREMENTAL = "incremental"
    FULL = "full"


CheckpointType = _CheckpointType


@dataclass(frozen=True, slots=True)
class CheckpointMetadata:
    checkpoint_id: str
    checkpoint_type: str  # "incremental" or "full"
    session_id: str
    triggered_by: str
    agent_version: str = "v0.5"
    game_version: str = ""
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_type": self.checkpoint_type,
            "session_id": self.session_id,
            "triggered_by": self.triggered_by,
            "agent_version": self.agent_version,
            "game_version": self.game_version,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """A session checkpoint with metadata and account state snapshot."""
    metadata: CheckpointMetadata
    account_snapshot: dict[str, Any] = field(default_factory=dict)
    task_state: dict[str, Any] = field(default_factory=dict)
    location_snapshot: dict[str, Any] = field(default_factory=dict)
    resource_snapshot: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "account_snapshot": self.account_snapshot,
            "task_state": self.task_state,
            "location_snapshot": self.location_snapshot,
            "resource_snapshot": self.resource_snapshot,
            "checksum": self.checksum,
        }

    def compute_checksum(self) -> str:
        """Compute SHA256 checksum of checkpoint content (excluding checksum field)."""
        content = json.dumps({
            "metadata": self.metadata.to_dict(),
            "account_snapshot": self.account_snapshot,
            "task_state": self.task_state,
            "location_snapshot": self.location_snapshot,
            "resource_snapshot": self.resource_snapshot,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()

    def verify(self) -> bool:
        """Verify checksum integrity."""
        return self.compute_checksum() == self.checksum


@dataclass(slots=True)
class CheckpointStore:
    """Manage checkpoint persistence with rolling window.

    Usage::

        store = CheckpointStore(checkpoint_dir=Path("checkpoints"))
        cp = store.create_checkpoint(
            session_id="abc123",
            triggered_by="quest_step_complete",
            account_snapshot={"ar": 35},
        )
        store.save(cp)
        latest = store.load_latest()
    """

    checkpoint_dir: Path = field(default_factory=lambda: Path("checkpoints"))
    max_checkpoints: int = 20
    max_full_checkpoints: int = 5
    max_age_days: int = 7

    def __post_init__(self) -> None:
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Create checkpoints
    # ------------------------------------------------------------------

    def create_checkpoint(
        self,
        session_id: str,
        triggered_by: str,
        account_snapshot: dict[str, Any] | None = None,
        task_state: dict[str, Any] | None = None,
        location_snapshot: dict[str, Any] | None = None,
        resource_snapshot: dict[str, Any] | None = None,
        checkpoint_type: str = "incremental",
        agent_version: str = "v0.5",
        game_version: str = "",
    ) -> Checkpoint:
        now = time.perf_counter()
        ts = time.strftime("%Y%m%d_%H%M%S")
        seq = len(list(self.checkpoint_dir.glob("checkpoint_*.json")))
        cp_id = f"ck_{ts}_{seq:03d}"

        metadata = CheckpointMetadata(
            checkpoint_id=cp_id,
            checkpoint_type=checkpoint_type,
            session_id=session_id,
            triggered_by=triggered_by,
            agent_version=agent_version,
            game_version=game_version,
            created_at=now,
        )
        cp = Checkpoint(
            metadata=metadata,
            account_snapshot=account_snapshot or {},
            task_state=task_state or {},
            location_snapshot=location_snapshot or {},
            resource_snapshot=resource_snapshot or {},
        )
        # Compute and set checksum
        return Checkpoint(
            metadata=metadata,
            account_snapshot=cp.account_snapshot,
            task_state=cp.task_state,
            location_snapshot=cp.location_snapshot,
            resource_snapshot=cp.resource_snapshot,
            checksum=cp.compute_checksum(),
        )

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def save(self, cp: Checkpoint) -> Path:
        """Save checkpoint to disk with atomic write-rename."""
        filename = f"checkpoint_{cp.metadata.checkpoint_id}.json"
        target = self.checkpoint_dir / filename

        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.checkpoint_dir), prefix=".checkpoint_", suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cp.to_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(target))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        # Update latest pointer
        latest_link = self.checkpoint_dir / "latest_checkpoint.json"
        try:
            # Write latest as a copy (Windows doesn't support symlinks easily)
            fd2, tmp2 = tempfile.mkstemp(
                dir=str(self.checkpoint_dir), prefix=".latest_", suffix=".tmp",
            )
            with os.fdopen(fd2, "w", encoding="utf-8") as f:
                json.dump(cp.to_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp2, str(latest_link))
        except Exception:
            pass

        self._prune_old_checkpoints()
        log.info("[CheckpointStore] saved %s (%s)", cp.metadata.checkpoint_id, cp.metadata.checkpoint_type)
        return target

    def load_latest(self) -> Checkpoint | None:
        """Load the latest checkpoint."""
        latest_path = self.checkpoint_dir / "latest_checkpoint.json"
        if not latest_path.exists():
            return None
        return self._load_from_path(latest_path)

    def load(self, checkpoint_id: str) -> Checkpoint | None:
        """Load a specific checkpoint by ID."""
        pattern = f"checkpoint_{checkpoint_id}.json"
        path = self.checkpoint_dir / pattern
        if not path.exists():
            return None
        return self._load_from_path(path)

    def list_checkpoints(self) -> list[str]:
        """List all checkpoint IDs, newest first."""
        files = sorted(self.checkpoint_dir.glob("checkpoint_*.json"), reverse=True)
        return [f.stem.replace("checkpoint_", "", 1) for f in files]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_old_checkpoints(self) -> None:
        """Remove checkpoints exceeding the rolling window."""
        all_cps = sorted(self.checkpoint_dir.glob("checkpoint_ck_*.json"), reverse=True)
        if len(all_cps) <= self.max_checkpoints:
            return

        to_delete = all_cps[self.max_checkpoints:]
        for path in to_delete:
            try:
                path.unlink()
                log.debug("[CheckpointStore] pruned %s", path.name)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _load_from_path(path: Path) -> Checkpoint | None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        meta_data = data.get("metadata", {})
        metadata = CheckpointMetadata(
            checkpoint_id=meta_data.get("checkpoint_id", ""),
            checkpoint_type=meta_data.get("checkpoint_type", "incremental"),
            session_id=meta_data.get("session_id", ""),
            triggered_by=meta_data.get("triggered_by", ""),
            agent_version=meta_data.get("agent_version", "v0.5"),
            game_version=meta_data.get("game_version", ""),
            created_at=meta_data.get("created_at", 0.0),
        )
        return Checkpoint(
            metadata=metadata,
            account_snapshot=data.get("account_snapshot", {}),
            task_state=data.get("task_state", {}),
            location_snapshot=data.get("location_snapshot", {}),
            resource_snapshot=data.get("resource_snapshot", {}),
            checksum=data.get("checksum", ""),
        )
