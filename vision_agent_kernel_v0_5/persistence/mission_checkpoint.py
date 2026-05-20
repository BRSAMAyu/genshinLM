from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MissionCheckpoint:
    mission_id: str
    current_node: str
    completed_nodes: list[str]
    failed_nodes: list[str]
    profile_id: str
    skill_id: str | None
    playbook_id: str | None
    resource_progress: dict[str, Any] = field(default_factory=dict)
    verifier_result: dict[str, Any] = field(default_factory=dict)
    failure_signature_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

