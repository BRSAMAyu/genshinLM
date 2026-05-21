from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from planning.mission_queue import MissionQueue, mission_to_dict
from runtime.context_compactor import RunSummary


@dataclass(frozen=True, slots=True)
class RunCheckpoint:
    checkpoint_id: str
    mission_id: str
    node_id: str
    verified: bool
    created_at: float = field(default_factory=time.time)
    evidence_refs: list[str] = field(default_factory=list)
    profile_id: str = ""
    capsule_id: str = ""
    skill_versions: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class RunStateStore:
    """Small JSON-backed store for long-run checkpoints and context summaries."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_mission(self, mission: MissionQueue) -> Path:
        path = self.root / f"{mission.mission_id}.mission.json"
        path.write_text(json.dumps(mission_to_dict(mission), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def save_checkpoint(self, checkpoint: RunCheckpoint) -> Path:
        path = self.root / f"{checkpoint.mission_id}.{checkpoint.checkpoint_id}.checkpoint.json"
        path.write_text(json.dumps(asdict(checkpoint), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def save_summary(self, summary: RunSummary) -> Path:
        path = self.root / f"{summary.mission_id}.summary.json"
        path.write_text(json.dumps(asdict(summary), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def latest_verified_checkpoint(self, mission_id: str) -> dict[str, Any] | None:
        checkpoints: list[dict[str, Any]] = []
        for path in self.root.glob(f"{mission_id}.*.checkpoint.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("verified") is True:
                checkpoints.append(data)
        if not checkpoints:
            return None
        return sorted(checkpoints, key=lambda item: float(item.get("created_at", 0.0)), reverse=True)[0]

    def revalidation_errors(
        self,
        checkpoint: dict[str, Any],
        *,
        profile_id: str,
        capsule_id: str,
        skill_versions: dict[str, int] | None = None,
    ) -> list[str]:
        errors: list[str] = []
        if checkpoint.get("profile_id") and checkpoint.get("profile_id") != profile_id:
            errors.append("profile_mismatch")
        if checkpoint.get("capsule_id") and checkpoint.get("capsule_id") != capsule_id:
            errors.append("capsule_mismatch")
        expected_versions = dict(checkpoint.get("skill_versions") or {})
        current_versions = skill_versions or {}
        for skill_id, expected in expected_versions.items():
            if current_versions.get(skill_id) != expected:
                errors.append(f"skill_version_mismatch:{skill_id}")
        return errors
