from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from runtime.claim_runtime import (
    AdjudicationEvent,
    ClaimStatus,
    ObservationClaim,
    RiskLevel,
    StateDeltaClaim,
    _clamp,
)


# --- EvidenceVote (Section 10.2) ---

@dataclass(frozen=True, slots=True)
class EvidenceVote:
    claim_id: str
    source_family: str
    polarity: Literal["support", "refute", "neutral"]
    signal_quality: float
    verifier_reliability: float = 1.0
    context_match: float = 1.0
    temporal_fit: float = 1.0
    freshness: float = 1.0
    independence_group: str = ""

    @property
    def weight(self) -> float:
        return _clamp(
            self.signal_quality
            * self.verifier_reliability
            * self.context_match
            * self.temporal_fit
            * self.freshness
        )


# --- ClaimRecipe (Section 9.4) ---

@dataclass(frozen=True, slots=True)
class ClaimRecipe:
    claim_type: str
    recipe_id: str = "default"
    required_families: list[str] = field(default_factory=list)
    optional_families: list[str] = field(default_factory=list)
    negative_families: list[str] = field(default_factory=list)
    min_independent_support_families: int = 1
    terminal_requires: list[str] = field(default_factory=list)
    vlm_allowed: str = "supplement_only"
    family_correlations: list[dict[str, Any]] = field(default_factory=list)


# --- Adjudication result ---

@dataclass(frozen=True, slots=True)
class AdjudicationResult:
    claim_id: str
    status: ClaimStatus
    confidence: float
    reason: str
    support_score: float = 0.0
    refute_score: float = 0.0
    family_coverage: float = 0.0
    recipe_complete: bool = True
    next_action: str = ""


# --- Family aggregation ---

def _aggregate_family_weights(
    votes: list[EvidenceVote],
    family_correlations: list[dict[str, Any]] | None = None,
) -> float:
    if not votes:
        return 0.0
    by_group: dict[str, list[EvidenceVote]] = defaultdict(list)
    ungrouped: list[EvidenceVote] = []
    for v in votes:
        if v.independence_group:
            by_group[v.independence_group].append(v)
        else:
            ungrouped.append(v)

    group_weights: list[float] = []
    for group_votes in by_group.values():
        group_weights.append(max(v.weight for v in group_votes))
    for v in ungrouped:
        group_weights.append(v.weight)

    if family_correlations:
        group_weights = _apply_family_correlation_discount(by_group, ungrouped, group_weights, family_correlations)

    if not group_weights:
        return 0.0
    fail_probs = [_clamp(1.0 - w) for w in group_weights]
    return _clamp(1.0 - math.prod(fail_probs))


def _apply_family_correlation_discount(
    grouped_votes: dict[str, list[EvidenceVote]],
    ungrouped_votes: list[EvidenceVote],
    group_weights: list[float],
    family_correlations: list[dict[str, Any]],
) -> list[float]:
    """Conservatively discount correlated evidence families before noisy-or.

    The MVP treats the highest declared correlation touching a family as a
    penalty against that family's independent contribution. This avoids
    over-counting signals such as toast OCR and prompt disappearance when they
    are driven by the same underlying UI event.
    """
    family_weight: dict[str, float] = {}
    for family, votes in grouped_votes.items():
        family_weight[family] = max((vote.weight for vote in votes), default=0.0)
    for vote in ungrouped_votes:
        family_weight[vote.source_family] = max(family_weight.get(vote.source_family, 0.0), vote.weight)

    max_penalty: dict[str, float] = defaultdict(float)
    for item in family_correlations:
        families = item.get("families", [])
        try:
            correlation = _clamp(float(item.get("correlation", 0.0)))
        except (TypeError, ValueError):
            correlation = 0.0
        if not isinstance(families, list) or correlation <= 0.0:
            continue
        present = [str(family) for family in families if str(family) in family_weight]
        if len(present) < 2:
            continue
        for family in present:
            others = [family_weight[other] for other in present if other != family]
            other_strength = max(others) if others else 0.0
            max_penalty[family] = max(max_penalty[family], correlation * other_strength)

    discounted: list[float] = []
    for family, weight in family_weight.items():
        discounted.append(_clamp(weight * (1.0 - max_penalty.get(family, 0.0))))
    return discounted


def _check_structural_gates(
    votes: list[EvidenceVote],
    recipe: ClaimRecipe,
) -> tuple[bool, float, str]:
    support_by_family: dict[str, list[EvidenceVote]] = defaultdict(list)
    refute_by_family: dict[str, list[EvidenceVote]] = defaultdict(list)
    for v in votes:
        if v.polarity == "support":
            support_by_family[v.source_family].append(v)
        elif v.polarity == "refute":
            refute_by_family[v.source_family].append(v)

    for neg_family in recipe.negative_families:
        if neg_family in refute_by_family:
            neg_votes = refute_by_family[neg_family]
            if neg_votes and neg_votes[0].weight > 0.7:
                return False, 0.0, f"negative_family_{neg_family}_refute_strong"

    if recipe.required_families:
        covered = sum(1 for f in recipe.required_families if f in support_by_family)
        if covered < len(recipe.required_families):
            missing = [f for f in recipe.required_families if f not in support_by_family]
            return False, covered / len(recipe.required_families), f"missing_required_families_{missing}"

    support_families = set(support_by_family.keys())
    optional_hit = support_families.intersection(recipe.optional_families)
    family_coverage = len(support_families) / max(1, len(recipe.required_families) + len(recipe.optional_families))

    return True, _clamp(family_coverage), "structure_ok"


# --- ClaimAdjudicator (Section 10) ---

class ClaimAdjudicator:
    def __init__(self, default_recipes: dict[str, ClaimRecipe] | None = None) -> None:
        self._recipes: dict[str, ClaimRecipe] = dict(CORE_RECIPES if default_recipes is None else default_recipes)
        self._verifier_reliability: dict[str, float] = {}
        self._adjudication_count: int = 0

    def register_recipe(self, recipe: ClaimRecipe) -> None:
        key = f"{recipe.claim_type}.{recipe.recipe_id}"
        self._recipes[key] = recipe

    def set_verifier_reliability(self, verifier_id: str, reliability: float) -> None:
        self._verifier_reliability[verifier_id] = _clamp(reliability)

    def adjudicate(
        self,
        claim: StateDeltaClaim,
        observations: list[ObservationClaim],
        *,
        dependency_health: float = 1.0,
        drift_penalty: float = 1.0,
        sample_sufficiency: float = 1.0,
    ) -> AdjudicationResult:
        self._adjudication_count += 1
        recipe = self._find_recipe(claim.claim_type)
        votes = self._observations_to_votes(observations)
        support_votes = [v for v in votes if v.polarity == "support"]
        refute_votes = [v for v in votes if v.polarity == "refute"]

        struct_ok, family_coverage, struct_reason = _check_structural_gates(votes, recipe)
        if not struct_ok:
            status: ClaimStatus = "rejected" if "refute_strong" in struct_reason else "uncertain"
            return AdjudicationResult(
                claim_id=claim.claim_id, status=status, confidence=0.0,
                reason=struct_reason, family_coverage=family_coverage,
                recipe_complete=False, next_action="alternate_verify" if status == "uncertain" else "abort",
            )

        support_score = _aggregate_family_weights(support_votes, recipe.family_correlations)
        refute_score = _aggregate_family_weights(refute_votes, recipe.family_correlations)

        independent_support_count = len({v.source_family for v in support_votes})
        recipe_complete = independent_support_count >= recipe.min_independent_support_families

        conflict_threshold = 0.15
        if support_score > 0.5 and refute_score > 0.5 and abs(support_score - refute_score) < conflict_threshold:
            return AdjudicationResult(
                claim_id=claim.claim_id, status="disputed", confidence=support_score * 0.5,
                reason="disputed_evidence", support_score=support_score, refute_score=refute_score,
                family_coverage=family_coverage, recipe_complete=recipe_complete,
                next_action="alternate_verify",
            )

        confidence = _clamp(
            support_score
            * dependency_health
            * (1.0 if recipe_complete else 0.7)
            * sample_sufficiency
            * drift_penalty
            * (1.0 - refute_score * 0.8)
        )

        if confidence >= 0.7 and recipe_complete:
            status = "verified"
            next_action = ""
        elif confidence >= 0.5:
            status = "tentative"
            next_action = "delayed_audit"
        elif confidence > 0.0:
            status = "uncertain"
            next_action = "resample"
        else:
            status = "rejected"
            next_action = "abort"

        return AdjudicationResult(
            claim_id=claim.claim_id, status=status, confidence=confidence,
            reason=f"support={support_score:.2f} refute={refute_score:.2f} families={independent_support_count}",
            support_score=support_score, refute_score=refute_score,
            family_coverage=family_coverage, recipe_complete=recipe_complete,
            next_action=next_action,
        )

    def _observations_to_votes(self, observations: list[ObservationClaim]) -> list[EvidenceVote]:
        votes: list[EvidenceVote] = []
        for obs in observations:
            try:
                if not obs.claim_id or not obs.source_family:
                    raise ValueError("missing_claim_or_source_family")
                verifier_rel = self._verifier_reliability.get(obs.verifier_id, 1.0)
                freshness = _clamp(float(obs.metadata.get("freshness", 1.0)))
                votes.append(EvidenceVote(
                    claim_id=obs.claim_id,
                    source_family=obs.source_family,
                    polarity=obs.polarity,
                    signal_quality=obs.signal_quality,
                    verifier_reliability=verifier_rel,
                    freshness=freshness,
                    independence_group=str(obs.metadata.get("independence_group", obs.source_family)),
                ))
            except Exception:
                votes.append(EvidenceVote(
                    claim_id=obs.claim_id or "invalid",
                    source_family="adjudication_error",
                    polarity="refute",
                    signal_quality=1.0,
                    verifier_reliability=1.0,
                ))
        return votes

    def _find_recipe(self, claim_type: str) -> ClaimRecipe:
        key = f"{claim_type}.default"
        if key in self._recipes:
            return self._recipes[key]
        return ClaimRecipe(claim_type=claim_type)

    @property
    def adjudication_count(self) -> int:
        return self._adjudication_count


# --- Default recipes for common claim types ---

CORE_RECIPES: dict[str, ClaimRecipe] = {
    "inventory_delta.default": ClaimRecipe(
        claim_type="inventory_delta",
        recipe_id="default",
        required_families=["inventory_delta"],
        optional_families=["toast", "prompt_disappeared", "screen_stable"],
        negative_families=["inventory_full"],
        min_independent_support_families=2,
        terminal_requires=["delayed_audit_or_inventory_delta"],
    ),
    "screen_state_transition.default": ClaimRecipe(
        claim_type="screen_state_transition",
        recipe_id="default",
        required_families=["screen_state"],
        optional_families=["element_disappeared", "element_appeared"],
        min_independent_support_families=1,
    ),
    "navigation_arrival.default": ClaimRecipe(
        claim_type="navigation_arrival",
        recipe_id="default",
        required_families=["navigation_signal"],
        optional_families=["screen_stable", "anchor_exists"],
        min_independent_support_families=1,
    ),
    "combat_target_killed.default": ClaimRecipe(
        claim_type="combat_target_killed",
        recipe_id="default",
        required_families=["danger_signal"],
        optional_families=["combat_reward", "screen_state"],
        negative_families=["target_still_alive"],
        min_independent_support_families=1,
    ),
    "collection_pickup.default": ClaimRecipe(
        claim_type="collection_pickup",
        recipe_id="default",
        required_families=["toast", "inventory_delta"],
        optional_families=["prompt_disappeared", "screen_stable"],
        negative_families=["inventory_full"],
        min_independent_support_families=2,
    ),
    "dialogue_advance.default": ClaimRecipe(
        claim_type="dialogue_advance",
        recipe_id="default",
        required_families=["text_change"],
        optional_families=["screen_stable", "anchor_exists"],
        min_independent_support_families=1,
    ),
    "teleport_loaded.default": ClaimRecipe(
        claim_type="teleport_loaded",
        recipe_id="default",
        required_families=["loading_disappeared"],
        optional_families=["screen_stable", "map_visible"],
        min_independent_support_families=1,
    ),
    "danger_cleared.default": ClaimRecipe(
        claim_type="danger_cleared",
        recipe_id="default",
        required_families=["danger_signal"],
        optional_families=["screen_state"],
        min_independent_support_families=1,
    ),
}
