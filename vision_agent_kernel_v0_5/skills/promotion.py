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


def promotion_path(current: PromotionTier, target: PromotionTier | None = None) -> list[PromotionTier]:
    """Return subsequent tiers from current, optionally stopping at target."""
    current_idx = _TIER_INDEX[current]
    stop_idx = _TIER_INDEX[target] if target is not None else len(_TIER_ORDER) - 1
    if stop_idx <= current_idx:
        return []
    return _TIER_ORDER[current_idx + 1: stop_idx + 1]


def can_promote_to(
    skill: SkillDef,
    target: PromotionTier,
    successes: int = 0,
    failures: int = 0,
) -> tuple[bool, str]:
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
        if _is_coordinate_only(skill):
            return False, "coordinate-only skills cannot promote"
        return True, "has semantic steps"

    if _is_coordinate_only(skill):
        return False, "coordinate-only skills cannot promote"

    # draft → experimental: no hard requirements
    if target == "experimental":
        return True, "draft to experimental allowed"

    # experimental → candidate: must have produced_claims with verifiers
    if target == "candidate":
        if not skill.produced_claims:
            return False, "candidate requires at least one produced_claim"
        # Hard rule: skills without verifiers on claims cannot be unattended
        missing_verifiers = [
            c.claim_type for c in skill.produced_claims
            if not c.verifier_recipe
        ]
        if missing_verifiers:
            return False, f"claims missing verifiers: {missing_verifiers}"
        return True, "has produced claims with verifiers"

    # candidate → stable: must meet replay + Wilson thresholds
    if target == "stable":
        stats = skill.metadata.get("execution_stats", {})
        replays = stats.get("success_count", 0)
        if replays < skill.promotion.min_replays:
            return False, f"needs {skill.promotion.min_replays} replays, has {replays}"
        # Consecutive failure circuit breaker
        consecutive = stats.get("consecutive_failures", 0)
        if consecutive >= 5:
            return False, f"consecutive failure breaker: {consecutive} consecutive failures"
        if not meets_wilson_threshold(skill, successes, failures):
            return False, f"Wilson lower bound below threshold ({successes}/{successes + failures})"
        # BAGEL probe policy enforcement
        non_decidable = stats.get("non_decidable_count", 0)
        if non_decidable > skill.bagel_probe_policy.max_non_decidable:
            return False, f"too many non-decidable probe results: {non_decidable}"
        return True, "meets replay + Wilson threshold"

    # stable → trusted: must have multi-profile verification + Wilson
    if target == "trusted":
        profiles = skill.metadata.get("verified_profiles", [])
        required = set(skill.promotion.required_profiles)
        if not required.issubset(set(profiles)):
            missing = required - set(profiles)
            return False, f"missing profiles: {missing}"
        stats = skill.metadata.get("execution_stats", {})
        consecutive = stats.get("consecutive_failures", 0)
        if consecutive >= 5:
            return False, f"consecutive failure breaker: {consecutive} consecutive failures"
        if not meets_wilson_threshold(skill, successes, failures):
            return False, f"Wilson lower bound below threshold ({successes}/{successes + failures})"
        return True, "all profiles verified + Wilson threshold met"

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


def can_demote_to(
    skill: SkillDef,
    target: PromotionTier,
    consecutive_failures: int = 0,
) -> tuple[bool, str]:
    """Check if a skill should be demoted to a lower tier.

    Demotion triggers:
    - consecutive_failures >= 5: mandatory demotion
    - Explicit caller request with reason
    """
    current_idx = _TIER_INDEX[skill.tier]
    target_idx = _TIER_INDEX[target]

    if target_idx >= current_idx:
        return False, f"target tier {target!r} is not lower than current {skill.tier!r}"

    if current_idx - target_idx > 1:
        return False, f"cannot skip tiers on demotion: {skill.tier!r} -> {target!r}"

    if consecutive_failures >= 5:
        return True, f"mandatory demotion: {consecutive_failures} consecutive failures"

    return True, f"demotion from {skill.tier!r} to {target!r} allowed"


def demote_skill(skill: SkillDef, target: PromotionTier) -> SkillDef:
    """Create a new SkillDef with lowered tier and reset promotion counters."""
    import dataclasses
    new_metadata = dict(skill.metadata)
    stats = dict(new_metadata.get("execution_stats", {}))
    stats["consecutive_failures"] = 0
    stats["demoted_at"] = __import__("time").perf_counter()
    new_metadata["execution_stats"] = stats
    new_metadata["demoted_from"] = skill.tier
    return dataclasses.replace(skill, tier=target, metadata=new_metadata)


def windowed_wilson(
    recent_successes: int,
    recent_failures: int,
    total_successes: int,
    total_failures: int,
    window_weight: float = 0.7,
    z: float = 1.96,
) -> float:
    """Wilson lower bound blended with recency weighting.

    Recent observations get `window_weight`, historical get `(1 - window_weight)`.
    """
    effective_s = window_weight * recent_successes + (1 - window_weight) * max(0, total_successes - recent_successes)
    effective_f = window_weight * recent_failures + (1 - window_weight) * max(0, total_failures - recent_failures)
    return wilson_lower_bound(int(effective_s), int(effective_f), z)


def meets_wilson_threshold(skill: SkillDef, successes: int, failures: int) -> bool:
    """Check if skill reliability meets its promotion Wilson threshold."""
    wlb = wilson_lower_bound(successes, failures)
    return wlb >= skill.promotion.min_wilson_lower_bound


def _is_coordinate_only(skill: SkillDef) -> bool:
    if bool(skill.metadata.get("coordinate_only")):
        return True
    if not skill.applicability.required_anchors:
        pointer_steps = [
            step for step in skill.steps
            if step.action in ("click_anchor", "click_text", "select_list_item", "confirm_dialog")
        ]
        if pointer_steps and not any(step.target for step in pointer_steps):
            return True
    return False
