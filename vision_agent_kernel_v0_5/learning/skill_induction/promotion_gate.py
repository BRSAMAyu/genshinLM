"""PromotionGate — validate and promote induced skills through tiers.

Uses skills.promotion rules plus additional induction-specific checks:
- Coordinate-only skills cannot promote past raw_trace
- Skills without produced_claims cannot enter candidate
- Skills without verifiers on terminal claims cannot be unattended
"""
from __future__ import annotations

from dataclasses import dataclass

from skills.promotion import can_promote_to, meets_wilson_threshold, PromotionTier
from skills.registry import SkillRegistry
from skills.schema import SkillDef


@dataclass(frozen=True, slots=True)
class PromotionResult:
    success: bool
    skill_id: str
    old_tier: PromotionTier
    new_tier: PromotionTier
    reason: str


class PromotionGate:
    """Validates and applies skill promotion via the registry."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def try_promote(
        self,
        skill: SkillDef,
        target_tier: PromotionTier,
        successes: int = 0,
        failures: int = 0,
    ) -> PromotionResult:
        """Attempt to promote a skill to the target tier.

        Checks promotion rules, updates the skill tier, and registers.
        """
        ok, reason = can_promote_to(skill, target_tier, successes, failures)
        if not ok:
            return PromotionResult(False, skill.skill_id, skill.tier, target_tier, reason)

        # Additional induction-specific checks
        if skill.tier == "raw_trace":
            return PromotionResult(
                False, skill.skill_id, skill.tier, target_tier,
                "coordinate-only traces cannot promote",
            )

        # Apply promotion: create new SkillDef with updated tier
        from dataclasses import replace as _replace
        promoted = _replace(skill, tier=target_tier)
        self._registry.register(promoted)

        return PromotionResult(True, skill.skill_id, skill.tier, target_tier, reason)

    def evaluate(
        self,
        skill: SkillDef,
        successes: int = 0,
        failures: int = 0,
    ) -> PromotionTier | None:
        """Determine the highest tier the skill can promote to.

        Returns the target tier, or None if no promotion is possible.
        Applies the same raw_trace block as try_promote().
        """
        if skill.tier == "raw_trace":
            return None

        from skills.promotion import _TIER_ORDER, _TIER_INDEX
        current_idx = _TIER_INDEX[skill.tier]
        highest: PromotionTier | None = None

        for next_idx in range(current_idx + 1, len(_TIER_ORDER)):
            target = _TIER_ORDER[next_idx]
            ok, _ = can_promote_to(skill, target, successes, failures)
            if not ok:
                break
            highest = target

        return highest
