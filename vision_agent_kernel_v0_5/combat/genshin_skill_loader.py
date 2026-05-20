from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class SkillStep:
    step_id: str
    type: str
    label: str
    params: dict[str, object]
    timeout_ms: int = 5000


@dataclass(frozen=True, slots=True)
class VisualTrigger:
    trigger_id: str
    type: str
    detection: str
    roi: str | None = None


@dataclass(frozen=True, slots=True)
class GenshinSkill:
    skill_id: str
    name: str
    type: str
    environment_profile: str
    steps: list[SkillStep]
    visual_triggers: dict[str, VisualTrigger]
    success_criteria: list[str]
    failure_policy: dict[str, object]
    safety: dict[str, object]


_REQUIRED_SKILL_FIELDS = (
    "skill_id",
    "name",
    "type",
    "environment_profile",
    "steps",
    "visual_triggers",
    "success_criteria",
    "failure_policy",
    "safety",
)

_REQUIRED_STEP_FIELDS = ("step_id", "type", "label")

_REQUIRED_TRIGGER_FIELDS = ("trigger_id", "type", "detection")


class GenshinSkillLoader:
    def __init__(self, skills_dir: Path | None = None) -> None:
        self._skills_dir = skills_dir or Path(__file__).resolve().parent.parent / "data" / "skills"
        self._cache: dict[str, GenshinSkill] = {}

    def load_skill(self, skill_id: str) -> GenshinSkill:
        if skill_id in self._cache:
            return self._cache[skill_id]

        for yaml_path in self._skills_dir.glob("genshin_*.yaml"):
            if yaml_path.name == "genshin_skill_index.yaml":
                continue
            with yaml_path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not data or "skills" not in data:
                continue
            for skill_key, skill_data in data["skills"].items():
                if skill_key != skill_id:
                    continue
                resolved = self._resolve_inheritance(skill_data, data["skills"])
                skill = self._build_skill(resolved)
                self._cache[skill_id] = skill
                return skill

        raise SkillNotFoundError(f"Skill not found: {skill_id}")

    def load_all(self) -> dict[str, GenshinSkill]:
        results: dict[str, GenshinSkill] = {}
        for yaml_path in sorted(self._skills_dir.glob("genshin_*.yaml")):
            if yaml_path.name == "genshin_skill_index.yaml":
                continue
            with yaml_path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not data or "skills" not in data:
                continue
            all_skills_data = data["skills"]
            for skill_key, skill_data in all_skills_data.items():
                if skill_key in results:
                    continue
                resolved = self._resolve_inheritance(skill_data, all_skills_data)
                results[skill_key] = self._build_skill(resolved)
        self._cache.update(results)
        return results

    def _resolve_inheritance(self, skill_data: dict[str, Any], all_skills: dict[str, Any]) -> dict[str, Any]:
        extends_id = skill_data.get("extends")
        if not extends_id:
            return skill_data

        parent_data = all_skills.get(extends_id)
        if parent_data is None:
            raise SkillInheritanceError(
                f"Skill '{skill_data.get('skill_id')}' extends '{extends_id}', but parent not found"
            )

        resolved_parent = self._resolve_inheritance(parent_data, all_skills)

        merged_steps: list[dict[str, Any]] = list(resolved_parent.get("steps", []))
        child_step_ids: set[str] = set()
        for step in skill_data.get("steps", []):
            child_step_ids.add(step["step_id"])
        merged_steps = [s for s in merged_steps if s["step_id"] not in child_step_ids]
        merged_steps.extend(skill_data.get("steps", []))

        merged_triggers: dict[str, Any] = dict(resolved_parent.get("visual_triggers", {}))
        merged_triggers.update(skill_data.get("visual_triggers", {}))

        merged: dict[str, Any] = {}
        merged.update(resolved_parent)
        merged.update(skill_data)
        merged["steps"] = merged_steps
        merged["visual_triggers"] = merged_triggers
        merged.pop("extends", None)

        return merged

    def _build_skill(self, data: dict[str, Any]) -> GenshinSkill:
        self._validate_required(data, _REQUIRED_SKILL_FIELDS, context="skill")
        steps = self._build_steps(data["steps"])
        triggers = self._build_triggers(data["visual_triggers"])
        return GenshinSkill(
            skill_id=data["skill_id"],
            name=data["name"],
            type=data["type"],
            environment_profile=data["environment_profile"],
            steps=steps,
            visual_triggers=triggers,
            success_criteria=list(data["success_criteria"]),
            failure_policy=dict(data["failure_policy"]),
            safety=dict(data["safety"]),
        )

    def _build_steps(self, raw_steps: list[dict[str, Any]]) -> list[SkillStep]:
        steps: list[SkillStep] = []
        for raw in raw_steps:
            self._validate_required(raw, _REQUIRED_STEP_FIELDS, context="step")
            steps.append(
                SkillStep(
                    step_id=raw["step_id"],
                    type=raw["type"],
                    label=raw["label"],
                    params=dict(raw.get("params", {})),
                    timeout_ms=int(raw.get("timeout_ms", 5000)),
                )
            )
        return steps

    def _build_triggers(self, raw_triggers: dict[str, Any]) -> dict[str, VisualTrigger]:
        triggers: dict[str, VisualTrigger] = {}
        for key, raw in raw_triggers.items():
            self._validate_required(raw, _REQUIRED_TRIGGER_FIELDS, context=f"trigger '{key}'")
            triggers[key] = VisualTrigger(
                trigger_id=raw["trigger_id"],
                type=raw["type"],
                detection=raw["detection"],
                roi=raw.get("roi"),
            )
        return triggers

    @staticmethod
    def _validate_required(data: dict[str, Any], fields: tuple[str, ...], context: str) -> None:
        missing = [f for f in fields if f not in data]
        if missing:
            raise SkillValidationError(f"Missing required fields in {context}: {missing}")


class SkillNotFoundError(Exception):
    pass


class SkillValidationError(Exception):
    pass


class SkillInheritanceError(Exception):
    pass
