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
    profile_version: str = ""
    capsule_id: str = ""
    capsule_version: str = ""
    window_id: str = ""
    screen_state: str = ""
    observation_graph_id: str = ""
    state_hash: str = ""
    semantic_action_id: str = ""
    controller_id: str = ""
    verifier_id: str = ""
    verifier_ok: bool | None = None
    allowed_next_actions: list[str] = field(default_factory=list)
    skill_versions: dict[str, int] = field(default_factory=dict)
    runtime_versions: dict[str, str] = field(default_factory=dict)
    claim_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResumeContext:
    profile_id: str = ""
    profile_version: str = ""
    capsule_id: str = ""
    capsule_version: str = ""
    window_id: str = ""
    screen_state: str = ""
    skill_versions: dict[str, int] = field(default_factory=dict)
    runtime_versions: dict[str, str] = field(default_factory=dict)


class CheckpointValidator:
    """Validate that a stored checkpoint is safe to resume from."""

    def validate(self, checkpoint: RunCheckpoint | dict[str, Any], current: ResumeContext) -> list[str]:
        data = asdict(checkpoint) if isinstance(checkpoint, RunCheckpoint) else dict(checkpoint)
        errors: list[str] = []
        if data.get("verified") is not True:
            errors.append("checkpoint_not_verified")
        if not data.get("evidence_refs"):
            errors.append("missing_checkpoint_evidence")
        if data.get("verifier_ok") is False:
            errors.append("verifier_not_ok")
        self._match(errors, data, "profile_id", current.profile_id, "profile_mismatch")
        self._match(errors, data, "profile_version", current.profile_version, "profile_version_mismatch")
        self._match(errors, data, "capsule_id", current.capsule_id, "capsule_mismatch")
        self._match(errors, data, "capsule_version", current.capsule_version, "capsule_version_mismatch")
        self._match(errors, data, "window_id", current.window_id, "window_mismatch")
        self._match(errors, data, "screen_state", current.screen_state, "screen_state_mismatch")

        for skill_id, expected in dict(data.get("skill_versions") or {}).items():
            if current.skill_versions.get(skill_id) != expected:
                errors.append(f"skill_version_mismatch:{skill_id}")
        for component, expected in dict(data.get("runtime_versions") or {}).items():
            if current.runtime_versions and current.runtime_versions.get(component) != expected:
                errors.append(f"runtime_version_mismatch:{component}")
        return errors

    @staticmethod
    def _match(errors: list[str], data: dict[str, Any], key: str, current: str, code: str) -> None:
        expected = str(data.get(key) or "")
        if expected and current and expected != current:
            errors.append(code)


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
        return CheckpointValidator().validate(
            checkpoint,
            ResumeContext(profile_id=profile_id, capsule_id=capsule_id, skill_versions=skill_versions or {}),
        )
