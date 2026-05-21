from __future__ import annotations

import json
import os
import tempfile

import pytest

from runtime.claim_adjudicator import (
    AdjudicationResult,
    ClaimAdjudicator,
    ClaimRecipe,
    CORE_RECIPES,
    EvidenceVote,
    _aggregate_family_weights,
    _check_structural_gates,
)
from runtime.claim_runtime import ObservationClaim, StateDeltaClaim
from reliability.reliability_store import (
    ContextKeyBuilder,
    ExecutionTrust,
    RecipeReliability,
    SkillClaimReliability,
    ThreeLayerReliabilityStore,
    VerifierReliability,
)


class TestEvidenceVote:
    def test_weight_computation(self):
        vote = EvidenceVote(
            claim_id="c1", source_family="toast", polarity="support",
            signal_quality=0.8, verifier_reliability=0.9,
            context_match=0.85, temporal_fit=0.95, freshness=1.0,
        )
        expected = 0.8 * 0.9 * 0.85 * 0.95 * 1.0
        assert abs(vote.weight - expected) < 0.001

    def test_weight_clamped(self):
        vote = EvidenceVote(
            claim_id="c1", source_family="toast", polarity="support",
            signal_quality=1.5, verifier_reliability=1.5,
        )
        assert vote.weight <= 1.0


class TestFamilyAggregation:
    def test_single_vote(self):
        votes = [EvidenceVote("c1", "toast", "support", 0.8)]
        result = _aggregate_family_weights(votes)
        assert abs(result - 0.8) < 0.001

    def test_independent_families(self):
        votes = [
            EvidenceVote("c1", "toast", "support", 0.8, independence_group="toast"),
            EvidenceVote("c1", "inventory", "support", 0.7, independence_group="inventory"),
        ]
        result = _aggregate_family_weights(votes)
        assert result > 0.8  # combined > either alone
        assert result < 1.0

    def test_same_family_dedup(self):
        votes = [
            EvidenceVote("c1", "toast", "support", 0.7, independence_group="toast"),
            EvidenceVote("c1", "toast", "support", 0.9, independence_group="toast"),
        ]
        result = _aggregate_family_weights(votes)
        assert abs(result - 0.9) < 0.001  # takes max within group

    def test_empty(self):
        assert _aggregate_family_weights([]) == 0.0


class TestStructuralGates:
    def test_pass_with_required_families(self):
        recipe = ClaimRecipe("test", required_families=["toast"], min_independent_support_families=1)
        votes = [EvidenceVote("c1", "toast", "support", 0.8)]
        ok, coverage, reason = _check_structural_gates(votes, recipe)
        assert ok
        assert reason == "structure_ok"

    def test_fail_missing_required(self):
        recipe = ClaimRecipe("test", required_families=["toast", "inventory"], min_independent_support_families=2)
        votes = [EvidenceVote("c1", "toast", "support", 0.8)]
        ok, coverage, reason = _check_structural_gates(votes, recipe)
        assert not ok
        assert "missing_required" in reason

    def test_negative_family_blocks(self):
        recipe = ClaimRecipe("test", negative_families=["inventory_full"])
        votes = [
            EvidenceVote("c1", "toast", "support", 0.8),
            EvidenceVote("c1", "inventory_full", "refute", 0.9),
        ]
        ok, _, reason = _check_structural_gates(votes, recipe)
        assert not ok
        assert "refute_strong" in reason


class TestClaimAdjudicator:
    def test_verified_with_sufficient_evidence(self):
        adj = ClaimAdjudicator()
        claim = _make_claim("c1", "inventory_delta")
        observations = [
            ObservationClaim("obs_1", "c1", "toast", "support", 0.85),
            ObservationClaim("obs_2", "c1", "inventory_delta", "support", 0.9),
        ]
        result = adj.adjudicate(claim, observations)
        assert result.status == "verified"
        assert result.confidence > 0.7

    def test_tentative_with_partial_evidence(self):
        recipe = ClaimRecipe(
            "inventory_delta", recipe_id="default",
            required_families=["inventory_delta"],
            min_independent_support_families=2,
        )
        adj = ClaimAdjudicator(default_recipes={"inventory_delta.default": recipe})
        claim = _make_claim("c1", "inventory_delta")
        observations = [
            ObservationClaim("obs_1", "c1", "toast", "support", 0.8),
        ]
        result = adj.adjudicate(claim, observations)
        # single family but recipe wants 2 independent → tentative
        assert result.status in ("tentative", "uncertain", "verified")
        assert not result.recipe_complete  # only 1 family, needs 2

    def test_rejected_with_no_evidence(self):
        adj = ClaimAdjudicator()
        claim = _make_claim("c1", "test")
        result = adj.adjudicate(claim, [])
        assert result.status == "rejected"
        assert result.confidence == 0.0

    def test_disputed_conflict(self):
        adj = ClaimAdjudicator()
        claim = _make_claim("c1", "test")
        observations = [
            ObservationClaim("obs_1", "c1", "toast", "support", 0.9),
            ObservationClaim("obs_2", "c1", "inventory", "refute", 0.85),
        ]
        result = adj.adjudicate(claim, observations)
        # close support vs refute → disputed
        assert result.status == "disputed"
        assert "disputed" in result.reason

    def test_with_custom_recipe(self):
        recipe = ClaimRecipe(
            "custom_type", recipe_id="strict",
            required_families=["a", "b"],
            min_independent_support_families=2,
        )
        adj = ClaimAdjudicator()
        adj.register_recipe(recipe)
        claim = _make_claim("c1", "custom_type")
        observations = [
            ObservationClaim("obs_1", "c1", "a", "support", 0.9),
            ObservationClaim("obs_2", "c1", "b", "support", 0.85),
        ]
        result = adj.adjudicate(claim, observations)
        assert result.status == "verified"

    def test_verifier_reliability_applied(self):
        adj = ClaimAdjudicator()
        adj.set_verifier_reliability("unreliable_v", 0.3)
        claim = _make_claim("c1", "test")
        observations = [
            ObservationClaim("obs_1", "c1", "toast", "support", 0.9, verifier_id="unreliable_v"),
        ]
        result = adj.adjudicate(claim, observations)
        # Low verifier reliability should reduce confidence
        assert result.confidence < 0.9

    def test_adjudication_count(self):
        adj = ClaimAdjudicator()
        claim = _make_claim("c1", "test")
        adj.adjudicate(claim, [])
        adj.adjudicate(claim, [])
        assert adj.adjudication_count == 2

    def test_core_recipes_loaded(self):
        assert "inventory_delta.default" in CORE_RECIPES
        assert "combat_target_killed.default" in CORE_RECIPES
        assert "navigation_arrival.default" in CORE_RECIPES


class TestContextKeyBuilder:
    def test_level_0_global(self):
        builder = ContextKeyBuilder()
        key = builder.build({"capsule_id": "genshin", "skill_id": "s1"}, 0)
        assert key == ("global",)

    def test_level_1_capsule_skill(self):
        builder = ContextKeyBuilder()
        key = builder.build({"capsule_id": "genshin", "skill_id": "collect"}, 1)
        assert key == ("genshin", "collect")

    def test_level_2_with_screen(self):
        builder = ContextKeyBuilder()
        key = builder.build({
            "capsule_id": "genshin", "skill_id": "s1",
            "screen_state": "overworld", "mission_phase": "collect",
        }, 2)
        assert "overworld" in key
        assert "collect" in key

    def test_level_3_with_target(self):
        builder = ContextKeyBuilder()
        key = builder.build({
            "capsule_id": "g", "skill_id": "s", "screen_state": "ow",
            "mission_phase": "mp", "target_class": "qingxin",
        }, 3)
        assert "qingxin" in key

    def test_parse(self):
        builder = ContextKeyBuilder()
        dims = builder.parse({"capsule_id": "hsr", "skill_id": "combat"})
        assert dims.capsule_id == "hsr"
        assert dims.skill_id == "combat"


class TestVerifierReliability:
    def test_record_and_get(self):
        vr = VerifierReliability()
        vr.record("v1", "toast", {"capsule_id": "g"}, "support", True)
        entry = vr.get("v1", "toast", {"capsule_id": "g"})
        assert entry is not None
        assert entry.total == 1
        assert entry.support_correct == 1

    def test_reliability_with_samples(self):
        vr = VerifierReliability()
        ctx = {"capsule_id": "g"}
        for _ in range(5):
            vr.record("v1", "toast", ctx, "support", True)
        rel = vr.get_reliability("v1", "toast", ctx)
        assert rel > 0.5

    def test_reliability_no_samples(self):
        vr = VerifierReliability()
        assert vr.get_reliability("v1", "toast", {}) == 0.5

    def test_contaminated_record(self):
        vr = VerifierReliability()
        vr.record_contaminated("v1", "toast", {"capsule_id": "g"})
        entry = vr.get("v1", "toast", {"capsule_id": "g"})
        assert entry is not None
        assert entry.contaminated_count == 1
        assert entry.total == 0  # contaminated doesn't count toward total


class TestRecipeReliability:
    def test_record_verified(self):
        rr = RecipeReliability()
        rr.record_verified("inventory_delta", "default", "genshin", {"capsule_id": "g"})
        entry = rr.get("inventory_delta", "default", "genshin", {"capsule_id": "g"})
        assert entry is not None
        assert entry.adjudicated_verified == 1

    def test_reliability(self):
        rr = RecipeReliability()
        ctx = {"capsule_id": "g"}
        for _ in range(5):
            rr.record_verified("t", "d", "g", ctx)
        rel = rr.get_reliability("t", "d", "g", ctx)
        assert rel > 0.5

    def test_no_samples_returns_neutral(self):
        rr = RecipeReliability()
        assert rr.get_reliability("t", "d", "g", {}) == 0.5


class TestSkillClaimReliability:
    def test_record_verified(self):
        sr = SkillClaimReliability()
        sr.record("s1", "inv_delta", "default", {"capsule_id": "g"}, "verified")
        entry = sr.get("s1", "inv_delta", "default", {"capsule_id": "g"})
        assert entry is not None
        assert entry.claim_verified == 1

    def test_zero_sample_returns_zero(self):
        sr = SkillClaimReliability()
        # Section 16.3: Option A - safety gate sees 0.0 for zero-sample
        assert sr.get_reliability("s1", "t", "d", {}) == 0.0

    def test_demotion_tracking(self):
        sr = SkillClaimReliability()
        ctx = {"capsule_id": "g"}
        sr.record("s1", "t", "d", ctx, "verified")
        sr.record("s1", "t", "d", ctx, "demoted")
        entry = sr.get("s1", "t", "d", ctx)
        assert entry is not None
        assert entry.claim_demoted == 1
        assert entry.demotion_rate == 0.5


class TestThreeLayerReliabilityStore:
    def test_record_adjudication(self):
        store = ThreeLayerReliabilityStore()
        store.record_adjudication(
            skill_id="s1", claim_type="inv_delta", recipe_id="default",
            capsule_id="genshin", verifier_id="v1", source_family="toast",
            context={"capsule_id": "g"}, adjudication_status="verified", was_correct=True,
        )
        trust = store.execution_trust(
            skill_id="s1", claim_type="inv_delta", recipe_id="default",
            capsule_id="genshin", context={"capsule_id": "g"},
        )
        assert trust.overall >= 0.0

    def test_execution_trust_uses_min(self):
        trust = ExecutionTrust.compute(
            recipe_trust=0.9, skill_claim_trust=0.3, dependency_health=1.0,
        )
        assert trust.overall == 0.3  # min of all three

    def test_drift_demoted(self):
        store = ThreeLayerReliabilityStore()
        store.mark_version_drift("s1")
        assert store.is_drift_demoted("s1")
        assert not store.is_drift_demoted("s2")

    def test_jsonl_persistence(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            store = ThreeLayerReliabilityStore(persistence_path=path)
            store.record_adjudication(
                skill_id="s1", claim_type="inv", recipe_id="default",
                capsule_id="g", verifier_id="v1", source_family="toast",
                context={"capsule_id": "g"}, adjudication_status="verified", was_correct=True,
            )
            store.record_audit(
                skill_id="s1", claim_type="inv", recipe_id="default",
                capsule_id="g", context={"capsule_id": "g"}, matched=True,
            )

            with open(path) as f:
                lines = [l.strip() for l in f if l.strip()]
            assert len(lines) == 2
            events = [json.loads(l) for l in lines]
            assert events[0]["type"] == "adjudication"
            assert events[1]["type"] == "audit"

            store2 = ThreeLayerReliabilityStore(persistence_path=path)
            entry = store2.skill_claim.get("s1", "inv", "default", {"capsule_id": "g"})
            assert entry is not None
            assert entry.claim_verified == 1
            assert entry.delayed_audit_matched == 1
        finally:
            os.unlink(path)


def _make_claim(claim_id: str, claim_type: str = "test") -> StateDeltaClaim:
    return StateDeltaClaim(
        claim_id=claim_id, mission_id="m1", node_id="n1", skill_id="s1",
        claim_type=claim_type, claimed_delta={"item": "test", "delta": 1},
    )
