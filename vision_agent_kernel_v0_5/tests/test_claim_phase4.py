from __future__ import annotations

import pytest

from runtime.claim_adjudicator import ClaimRecipe
from runtime.verifier_compiler import (
    CORE_BUNDLES,
    VerifierBundle,
    VerifierCompiler,
    VerifierStep,
    UncertaintyPolicyDecl,
)


class TestVerifierStep:
    def test_create_text_match(self):
        step = VerifierStep(type="text_match", roi="toast_area", contains="+1", timeout_ms=1500)
        assert step.type == "text_match"
        assert step.contains == "+1"

    def test_create_composite(self):
        step = VerifierStep(
            type="composite",
            all_of=[
                VerifierStep(type="screen_state_stable", state="overworld", frames=5),
                VerifierStep(type="element_disappearance", anchor="loading_spinner"),
            ],
        )
        assert len(step.all_of) == 2


class TestVerifierBundle:
    def test_create(self):
        bundle = VerifierBundle(
            claim_type="inventory_delta",
            primary=[VerifierStep(type="text_match", contains="+1")],
            secondary=[VerifierStep(type="element_disappearance", anchor="prompt")],
        )
        assert bundle.claim_type == "inventory_delta"
        assert len(bundle.primary) == 1
        assert len(bundle.secondary) == 1


class TestVerifierCompiler:
    def test_lookup_existing_bundle(self):
        compiler = VerifierCompiler(CORE_BUNDLES)
        bundle = compiler.compile("inventory_delta")
        assert bundle.claim_type == "inventory_delta"
        assert len(bundle.primary) > 0

    def test_lookup_unknown_returns_empty(self):
        compiler = VerifierCompiler()
        bundle = compiler.compile("unknown_type")
        assert bundle.claim_type == "unknown_type"
        assert bundle.primary == []

    def test_register_custom_bundle(self):
        compiler = VerifierCompiler()
        bundle = VerifierBundle(
            claim_type="custom_claim",
            primary=[VerifierStep(type="anchor_exists", anchor="custom_anchor")],
        )
        compiler.register_bundle(bundle, custom_mapping=True)
        result = compiler.compile("custom_claim")
        assert len(result.primary) == 1
        assert compiler.is_custom_mapping("custom_claim")

    def test_recipe_fallback(self):
        compiler = VerifierCompiler()
        recipe = ClaimRecipe(
            "test_type",
            required_families=["toast", "inventory_delta"],
            optional_families=["prompt_disappeared"],
        )
        bundle = compiler.compile("test_type", recipe=recipe)
        assert len(bundle.primary) == 2  # one per required family
        assert len(bundle.secondary) == 1  # one per optional family

    def test_core_bundles_coverage(self):
        expected = [
            "inventory_delta", "screen_state_transition", "navigation_arrival",
            "combat_target_killed", "collection_pickup", "dialogue_advance",
            "teleport_loaded", "danger_cleared",
        ]
        for claim_type in expected:
            assert claim_type in CORE_BUNDLES, f"Missing core bundle for {claim_type}"

    def test_inventory_delta_bundle_structure(self):
        bundle = CORE_BUNDLES["inventory_delta"]
        assert len(bundle.primary) > 0
        assert len(bundle.delayed_audit) > 0
        assert bundle.uncertainty_policy.on_low_confidence == "resample_then_inventory_audit"

    def test_combat_target_killed_bundle(self):
        bundle = CORE_BUNDLES["combat_target_killed"]
        assert any(s.type == "danger_score_below" for s in bundle.primary)

    def test_teleport_loaded_bundle(self):
        bundle = CORE_BUNDLES["teleport_loaded"]
        assert any(s.type == "element_disappearance" for s in bundle.primary)

    def test_custom_mapping_flag(self):
        compiler = VerifierCompiler()
        bundle = VerifierBundle(claim_type="test", primary=[])
        compiler.register_bundle(bundle)
        assert not compiler.is_custom_mapping("test")
        compiler.register_bundle(bundle, custom_mapping=True)
        assert compiler.is_custom_mapping("test")
