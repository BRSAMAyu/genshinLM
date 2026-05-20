from __future__ import annotations

from typing import Any

from planning.mission_queue import MissionQueue


FORBIDDEN_NODE_TYPES = {"raw_key_input", "raw_mouse_input", "direct_click", "direct_press_key", "bypass_safety"}


class PlanValidator:
    def validate(self, queue: MissionQueue, available_skills: set[str] | None = None) -> dict[str, Any]:
        errors: list[str] = []
        missing_skills: list[str] = []
        available = available_skills or set()
        for node in queue.nodes:
            if node.type in FORBIDDEN_NODE_TYPES:
                errors.append(f"{node.id}: raw input node type is forbidden")
            if not node.verifier:
                errors.append(f"{node.id}: verifier is required")
            if not node.failure_policy:
                errors.append(f"{node.id}: failure_policy is required")
            if node.skill_binding and available and node.skill_binding not in available:
                missing_skills.append(node.skill_binding)
        if queue.loop and queue.loop.max_iterations <= 0:
            errors.append("loop.max_iterations must be positive")
        if not queue.requires_user_confirmation:
            errors.append("mission must require user confirmation before execution")
        return {"ok": not errors and not missing_skills, "errors": errors, "missing_skills": sorted(set(missing_skills))}

