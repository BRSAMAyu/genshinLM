from __future__ import annotations

from pathlib import Path

from persistence.mission_checkpoint import MissionCheckpoint
from persistence.sqlite_store import SQLiteStore


class HotResume:
    def __init__(self, root: Path) -> None:
        self._store = SQLiteStore(root / "data" / "mission_state.sqlite")

    def save(self, checkpoint: MissionCheckpoint) -> None:
        self._store.put(f"mission:{checkpoint.mission_id}", checkpoint.to_dict())
        self._store.put("mission:latest", checkpoint.to_dict())

    def latest(self) -> dict | None:
        return self._store.get("mission:latest")

    def can_resume(self, expected_profile: str) -> dict[str, object]:
        checkpoint = self.latest()
        if checkpoint is None:
            return {"ok": False, "reason": "no checkpoint"}
        if checkpoint.get("profile_id") != expected_profile:
            return {"ok": False, "reason": "profile changed; recalibration required", "checkpoint": checkpoint}
        return {"ok": True, "requires_user_confirmation": True, "checkpoint": checkpoint}
