from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BlueprintValidation:
    ok: bool
    errors: list[str]


class SkillWorkshop:
    def validate_blueprint(self, blueprint: dict) -> BlueprintValidation:
        errors = []
        if blueprint.get("kind") not in {"skill", "profile", "playbook", "persona"}:
            errors.append("unsupported blueprint kind")
        if blueprint.get("dangerous_input", False):
            errors.append("dangerous input is not allowed")
        if not blueprint.get("id"):
            errors.append("blueprint id is required")
        return BlueprintValidation(not errors, errors)

