from __future__ import annotations

from pathlib import Path
from typing import Any

from app_service.skill_manager import SkillStore
from llm.tool_schema import FORBIDDEN_TOOLS, tool_allowed


class SandboxValidator:
    def __init__(self, root: Path, skill_store: SkillStore) -> None:
        self._root = root
        self._skill_store = skill_store

    def validate_task_spec(self, task_spec: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        if not task_spec.get("requires_user_confirmation", False):
            errors.append("TaskSpec requires user confirmation before execution")
        if task_spec.get("input_mode") not in {"dry-run", "safe-window", "analysis-only"}:
            errors.append("TaskSpec input_mode must be dry-run, safe-window, or analysis-only")
        if "max_retries" not in task_spec:
            errors.append("TaskSpec max_retries is required")
        if int(task_spec.get("max_duration_sec", 0)) <= 0:
            errors.append("TaskSpec max_duration_sec is required")
        for tool in task_spec.get("tools", []):
            if tool in FORBIDDEN_TOOLS or not tool_allowed(str(tool)):
                errors.append(f"unsafe or unknown tool: {tool}")
        available = {item["skill_id"] for item in self._skill_store.list_skills().get("skills", [])}
        for skill_id in task_spec.get("skill_chain", []):
            if skill_id not in available:
                errors.append(f"missing skill id: {skill_id}")
        profile_id = task_spec.get("environment_profile")
        if profile_id and not (self._root / "configs" / "profiles" / f"{profile_id}.json").exists():
            errors.append(f"missing profile: {profile_id}")
        graph = task_spec.get("graph", {})
        nodes = graph.get("nodes", [])
        if nodes and "COMPLETE" not in nodes:
            errors.append("dry-run graph simulation requires COMPLETE node")
        return {"ok": not errors, "errors": errors, "simulation": "PASS" if not errors else "BLOCKED"}
