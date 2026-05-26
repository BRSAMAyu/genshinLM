from __future__ import annotations

from typing import Any

from planning.mission_queue import MissionQueue
from planning.skill_capability_catalog import SkillCapabilityCatalog


FORBIDDEN_NODE_TYPES = {"raw_key_input", "raw_mouse_input", "direct_click", "direct_press_key", "bypass_safety"}


class PlanValidator:
    def validate(
        self,
        queue: MissionQueue,
        available_skills: set[str] | None = None,
        strict_mode: bool = False,
        catalog: SkillCapabilityCatalog | None = None,
    ) -> dict[str, Any]:
        errors: list[str] = []
        missing_skills: list[str] = []
        available = available_skills or set()
        
        for node in queue.nodes:
            if node.type in FORBIDDEN_NODE_TYPES:
                errors.append(f"{node.id}: raw input node type is forbidden")
            if not node.verifier:
                errors.append(f"{node.id}: verifier is required")
            if node.skill_binding and available and node.skill_binding not in available:
                missing_skills.append(node.skill_binding)

            # Strict mode check on skill risk & verifier
            if strict_mode and catalog and node.skill_binding:
                # Find entry in catalog
                entry = next((e for e in catalog.entries() if e.skill_id == node.skill_binding), None)
                if entry:
                    is_high_risk = entry.risk_level in ("high", "human_confirm")
                    if is_high_risk:
                        if not entry.verifiers and not node.verifier:
                            errors.append(f"{node.id}: high-risk skill '{node.skill_binding}' requires a verifier in strict mode")
                        if entry.risk_level == "human_confirm" and not queue.requires_user_confirmation:
                            errors.append(f"{node.id}: skill '{node.skill_binding}' requires user confirmation")

        if queue.loop and queue.loop.max_iterations <= 0:
            errors.append("loop.max_iterations must be positive")
        if strict_mode and not queue.requires_user_confirmation:
            # In strict mode, mission must require user confirmation before execution
            errors.append("mission must require user confirmation before execution")
            
        return {"ok": not errors and not missing_skills, "errors": errors, "missing_skills": sorted(set(missing_skills))}

