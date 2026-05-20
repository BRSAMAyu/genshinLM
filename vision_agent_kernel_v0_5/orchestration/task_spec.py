from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_id: str
    target_profile: dict[str, Any]
    success_criteria: dict[str, Any]
    max_duration_sec: float
    max_retries: int
    failure_policy: dict[str, Any] = field(default_factory=dict)


def load_task_spec(path: str | Path) -> TaskSpec:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return TaskSpec(
        task_id=str(data["task_id"]),
        target_profile=dict(data.get("target_profile", {})),
        success_criteria=dict(data.get("success_criteria", {})),
        max_duration_sec=float(data.get("max_duration_sec", 60.0)),
        max_retries=int(data.get("max_retries", 1)),
        failure_policy=dict(data.get("failure_policy", {})),
    )
