"""Skill OS Promotion — manage skill promotion across tiers.

Promotion ladder:
  raw_trace → draft → experimental → candidate → stable → trusted

Rules:
- raw_trace: never executed, only stored
- draft: has semantic actions but incomplete verifiers
- experimental: supervised execution allowed
- candidate: dry-run/testbed passed, low-risk auto-allowed
- stable: multiple audits passed
- trusted: multi-context, multi-profile, drift-tested

Hard rules:
- Coordinate-only traces cannot promote past raw_trace
- Skills without produced_claims cannot enter candidate
- Skills without verifiers on terminal claims cannot be unattended
- New skills' priors are for ranking only, not safety gating
"""
from __future__ import annotations

import math

from skills.schema import PromotionTier, SkillDef


_TIER_ORDER: list[PromotionTier] = [
    "raw_trace", "draft", "experimental", "candidate", "stable", "trusted",
]

_TIER_INDEX: dict[PromotionTier, int] = {t: i for i, t in enumerate(_TIER_ORDER)}


def tier_index(tier: PromotionTier) -> int:
    return _TIER_INDEX[tier]


def can_promote_to(skill: SkillDef, target: PromotionTier) -> tuple[bool, str]:
    """Check if a skill can promote to the target tier.

    Returns (can_promote, reason).
    """
    current_idx = _TIER_INDEX[skill.tier]
    target_idx = _TIER_INDEX[target]

    if target_idx <= current_idx:
        return False, f"target tier {target!r} is not higher than current {skill.tier!r}"

    if target_idx - current_idx > 1:
        return False, f"cannot skip tiers: {skill.tier!r} → {target!r}"

    # raw_trace → draft: must have semantic actions (not coordinate-only)
    if target == "draft":
        if not skill.steps:
            return False, "draft requires at least one semantic step"
        return True, "has semantic steps"

    # draft → experimental: no hard requirements
    if target == "experimental":
        return True, "draft to experimental allowed"

    # experimental → candidate: must have produced_claims
    if target == "candidate":
        if not skill.produced_claims:
            return False, "candidate requires at least one produced_claim"
        return True, "has produced claims"

    # candidate → stable: must meet promotion thresholds
    if target == "stable":
        stats = skill.metadata.get("execution_stats", {})
        replays = stats.get("success_count", 0)
        if replays < skill.promotion.min_replays:
            return False, f"needs {skill.promotion.min_replays} replays, has {replays}"
        return True, "meets replay threshold"

    # stable → trusted: must have multi-profile verification
    if target == "trusted":
        profiles = skill.metadata.get("verified_profiles", [])
        required = set(skill.promotion.required_profiles)
        if not required.issubset(set(profiles)):
            missing = required - set(profiles)
            return False, f"missing profiles: {missing}"
        return True, "all profiles verified"

    return False, f"unknown target tier: {target!r}"


def wilson_lower_bound(successes: int, failures: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound for reliability estimation."""
    n = successes + failures
    if n == 0:
        return 0.0
    p_hat = successes / n
    denom = 1 + z * z / n
    center = p_hat + z * z / (2 * n)
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n)) / n)
    return max(0.0, (center - spread) / denom)


def meets_wilson_threshold(skill: SkillDef, successes: int, failures: int) -> bool:
    """Check if skill reliability meets its promotion Wilson threshold."""
    wlb = wilson_lower_bound(successes, failures)
    return wlb >= skill.promotion.min_wilson_lower_bound
