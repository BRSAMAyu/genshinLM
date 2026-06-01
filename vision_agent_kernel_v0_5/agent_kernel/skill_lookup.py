"""Concrete SkillRecipeLookup implementations for the generic kernel.

This module is intentionally game-agnostic. Game capsules can provide raw
dict/YAML skill libraries, and the lookup normalizes them into immutable
SkillRecipe objects that the L7-L8 planner can query without knowing the
source format.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from agent_kernel.protocols import SkillRecipeLookup as SkillRecipeLookupProtocol
from agent_kernel.types import SkillRecipe, SkillStep


class KernelSkillRecipeLookup(SkillRecipeLookupProtocol):
    """In-memory skill recipe repository with capsule-library ingestion."""

    def __init__(self, recipes: dict[str, SkillRecipe] | None = None) -> None:
        self._recipes: dict[str, SkillRecipe] = {}
        self._capability_index: dict[str, str] = {}
        for capability, recipe in (recipes or {}).items():
            self.register(capability, recipe)

    def register(self, capability: str, recipe: SkillRecipe) -> None:
        """Register a recipe under a capability or intent key."""
        key = capability.strip().lower()
        if not key:
            raise ValueError("capability must not be empty")
        self._recipes[recipe.skill_id] = recipe
        self._capability_index[key] = recipe.skill_id
        self._capability_index[recipe.skill_id.lower()] = recipe.skill_id
        for ctx in recipe.applicable_context:
            if ctx:
                self._capability_index.setdefault(ctx.lower(), recipe.skill_id)

    def __len__(self) -> int:
        return len(self._recipes)

    def lookup(self, capability: str) -> SkillRecipe:
        """Return the best recipe for a capability.

        Raises KeyError instead of returning None so callers cannot silently
        continue with an unbound skill.
        """
        key = capability.strip().lower()
        recipe_id = self._capability_index.get(key, capability)
        recipe = self._recipes.get(recipe_id)
        if recipe is None:
            raise KeyError(f"no skill recipe registered for capability: {capability}")
        return recipe

    def lookup_recipe(self, skill_id: str) -> dict[str, Any]:
        """Return a plain dict view for legacy callers."""
        recipe = self.lookup(skill_id)
        return {
            "skill_id": recipe.skill_id,
            "title": recipe.title,
            "goal_template": recipe.goal_template,
            "applicable_context": list(recipe.applicable_context),
            "preconditions": list(recipe.preconditions),
            "steps": [
                {
                    "step_id": step.step_id,
                    "intent": step.intent,
                    "target_query": step.target_query,
                    "expected_delta": step.expected_delta,
                    "locator_policy": step.locator_policy,
                    "retry_policy": step.retry_policy,
                }
                for step in recipe.steps
            ],
            "verifiers": list(recipe.verifiers),
            "recovery_policies": list(recipe.recovery_policies),
            "risk_level": recipe.risk_level,
            "version": recipe.version,
        }

    def find_applicable(self, context: str, goal: Any) -> list[SkillRecipe]:
        """Find recipes by context text, goal id, or goal description."""
        tokens = {
            part.lower()
            for part in (
                context,
                getattr(goal, "goal_id", ""),
                getattr(goal, "description", ""),
                str(goal),
            )
            if part
        }
        results: list[SkillRecipe] = []
        for capability, recipe_id in self._capability_index.items():
            recipe = self._recipes[recipe_id]
            haystack = " ".join((
                capability,
                recipe.skill_id,
                recipe.title,
                recipe.goal_template,
                " ".join(recipe.applicable_context),
            )).lower()
            if any(token in haystack or haystack in token for token in tokens):
                if recipe not in results:
                    results.append(recipe)
        return results

    @classmethod
    def from_capsule_library(cls, library: dict[str, Any]) -> "KernelSkillRecipeLookup":
        """Build a lookup from a capsule `skill_library()` dict."""
        lookup = cls()
        for capability, raw in library.items():
            recipe = _coerce_recipe(capability, raw)
            lookup.register(capability, recipe)
        return lookup

    @classmethod
    def with_recipes(cls, recipes: Iterable[SkillRecipe]) -> "KernelSkillRecipeLookup":
        lookup = cls()
        for recipe in recipes:
            lookup.register(recipe.skill_id, recipe)
        return lookup


def _coerce_recipe(capability: str, raw: Any) -> SkillRecipe:
    if isinstance(raw, SkillRecipe):
        if capability not in raw.applicable_context:
            return replace(raw, applicable_context=(*raw.applicable_context, capability))
        return raw
    if not isinstance(raw, dict):
        return SkillRecipe(
            skill_id=str(capability),
            title=str(capability).replace("_", " ").title(),
            goal_template=str(raw),
            applicable_context=(str(capability),),
        )

    steps = tuple(
        SkillStep(
            step_id=str(step.get("step_id", f"step_{index}")),
            intent=str(step.get("intent", step.get("action", ""))),
            target_query=str(step.get("target_query", step.get("target", ""))),
            expected_delta=str(step.get("expected_delta", "")),
            locator_policy=str(step.get("locator_policy", "affordance_then_vlm")),
            retry_policy=str(step.get("retry_policy", "resample_relocate_replan")),
        )
        for index, step in enumerate(raw.get("steps", ()))
        if isinstance(step, dict)
    )
    return SkillRecipe(
        skill_id=str(raw.get("skill_id", capability)),
        title=str(raw.get("title", capability.replace("_", " ").title())),
        goal_template=str(raw.get("goal_template", raw.get("goal", capability))),
        applicable_context=tuple(str(v) for v in raw.get("applicable_context", (capability,))),
        preconditions=tuple(str(v) for v in raw.get("preconditions", ())),
        steps=steps,
        verifiers=tuple(str(v) for v in raw.get("verifiers", ())),
        recovery_policies=tuple(str(v) for v in raw.get("recovery_policies", ())),
        risk_level=raw.get("risk_level", "low"),
        version=str(raw.get("version", "1.0")),
    )
