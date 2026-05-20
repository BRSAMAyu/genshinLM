from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SkillBindingResult:
    node_id: str
    candidate_skills: list[str]
    selected_skill: str | None
    confidence: float
    reason: str
    fallback: list[str] = field(default_factory=list)


class SkillBinder:
    def bind(self, plan_node: Any, available_skills: list[dict[str, Any]], environment_profile: str = "default_1920x1080") -> SkillBindingResult:
        requested = _field(plan_node, "skill_binding")
        node_id = _field(plan_node, "id")
        node_type = _field(plan_node, "type")
        candidates = [skill for skill in available_skills if skill.get("environment_profile", environment_profile) == environment_profile]
        exact = [skill for skill in candidates if skill.get("skill_id") == requested]
        typed = [skill for skill in candidates if skill.get("type") == node_type]
        if exact:
            return SkillBindingResult(node_id, [skill["skill_id"] for skill in exact + typed], exact[0]["skill_id"], 0.92, "exact skill binding found", [skill["skill_id"] for skill in typed[:2]])
        if typed:
            return SkillBindingResult(node_id, [skill["skill_id"] for skill in typed], typed[0]["skill_id"], 0.68, "matched by node type", [skill["skill_id"] for skill in typed[1:3]])
        return SkillBindingResult(node_id, [], None, 0.0, "missing skill; request user demonstration", ["request_user_demo"])


def _field(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
