"""Tests for Skill OS MVP — schema, registry, applicability, promotion."""
from __future__ import annotations

import pytest

from skills.schema import (
    SkillApplicability,
    SkillBeliefTemplate,
    SkillDef,
    SkillFallback,
    SkillProducedClaim,
    SkillStep,
    PromotionConfig,
)
from skills.registry import SkillRegistry
from skills.applicability import ApplicabilityScore, SkillApplicabilityMatcher
from skills.promotion import (
    can_promote_to,
    meets_wilson_threshold,
    tier_index,
    wilson_lower_bound,
)


# -- Helpers --

def _step(action: str = "click_anchor", target: str = "btn") -> SkillStep:
    return SkillStep(action=action, target=target)  # type: ignore


def _claim(claim_type: str = "dialogue_advanced") -> SkillProducedClaim:
    return SkillProducedClaim(claim_type=claim_type)


def _dialogue_skill(tier: str = "draft") -> SkillDef:
    return SkillDef(
        skill_id="proc_dialogue_advance",
        version=1,
        kind="procedure",
        risk_level="low",
        tier=tier,
        applicability=SkillApplicability(
            screen_states=("dialogue",),
            required_anchors=("dialogue_continue",),
            required_claims=("screen_state_match",),
        ),
        steps=(_step("click_anchor", "dialogue_continue"),),
        produced_claims=(
            SkillProducedClaim("dialogue_advanced", "active_dialogue.turn_index", "dependency",
                               "dialogue_delta.default"),
        ),
        belief_templates=(
            SkillBeliefTemplate("dialogue_overlay", "ui_affordance_hypothesis",
                                falsification_condition="dialogue_continue anchor absent for 3 frames"),
        ),
        fallbacks=(SkillFallback("UI_LOST_RECOVERY"),),
    )


# -- Schema tests --

class TestSkillDefSchema:
    def test_roundtrip_dict(self) -> None:
        skill = _dialogue_skill()
        d = skill.to_dict()
        assert d["skill_id"] == "proc_dialogue_advance"
        assert d["tier"] == "draft"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["action"] == "click_anchor"
        assert len(d["produced_claims"]) == 1

        restored = SkillDef.from_dict(d)
        assert restored.skill_id == skill.skill_id
        assert restored.tier == skill.tier
        assert restored.steps == skill.steps
        assert restored.produced_claims == skill.produced_claims
        assert restored.to_dict() == d

    def test_default_values(self) -> None:
        skill = SkillDef(skill_id="minimal")
        assert skill.version == 1
        assert skill.kind == "procedure"
        assert skill.risk_level == "medium"
        assert skill.tier == "draft"
        assert skill.capsule_id == "core"
        assert skill.steps == ()
        assert skill.produced_claims == ()

    def test_metadata_roundtrip(self) -> None:
        skill = SkillDef(
            skill_id="meta_test",
            metadata={"author": "test", "tags": ["combat", "boss"]},
        )
        d = skill.to_dict()
        assert d["metadata"]["tags"] == ["combat", "boss"]
        restored = SkillDef.from_dict(d)
        assert restored.metadata["tags"] == ["combat", "boss"]

    def test_applicability_empty_means_always(self) -> None:
        """Empty applicability means skill applies to any screen state."""
        skill = SkillDef(
            skill_id="universal",
            applicability=SkillApplicability(),
        )
        assert not skill.applicability.screen_states
        assert not skill.applicability.required_claims
        assert not skill.applicability.required_anchors


# -- Registry tests --

class TestSkillRegistry:
    def test_register_and_get(self) -> None:
        reg = SkillRegistry()
        skill = _dialogue_skill()
        reg.register(skill)
        assert reg.get("proc_dialogue_advance") is skill
        assert reg.size == 1

    def test_get_nonexistent(self) -> None:
        reg = SkillRegistry()
        assert reg.get("nope") is None

    def test_unregister(self) -> None:
        reg = SkillRegistry()
        reg.register(_dialogue_skill())
        reg.unregister("proc_dialogue_advance")
        assert reg.get("proc_dialogue_advance") is None
        assert reg.size == 0

    def test_find_by_screen_state(self) -> None:
        reg = SkillRegistry()
        reg.register(_dialogue_skill())
        reg.register(SkillDef(
            skill_id="proc_combat",
            applicability=SkillApplicability(screen_states=("combat",)),
            steps=(_step("click_anchor", "attack"),),
        ))
        results = reg.find_by_screen_state("dialogue")
        ids = [s.skill_id for s in results]
        assert "proc_dialogue_advance" in ids
        assert "proc_combat" not in ids

    def test_universal_skill_matches_any_screen(self) -> None:
        reg = SkillRegistry()
        reg.register(SkillDef(
            skill_id="observe",
            steps=(_step("observe", ""),),
        ))
        results = reg.find_by_screen_state("anything")
        assert len(results) == 1

    def test_find_by_capability(self) -> None:
        reg = SkillRegistry()
        reg.register(_dialogue_skill())
        reg.register(SkillDef(
            skill_id="proc_map_open",
            produced_claims=(SkillProducedClaim("map_opened"),),
        ))
        results = reg.find_by_capability("dialogue_advanced")
        assert len(results) == 1
        assert results[0].skill_id == "proc_dialogue_advance"

    def test_find_by_tier(self) -> None:
        reg = SkillRegistry()
        reg.register(SkillDef(skill_id="raw", tier="raw_trace"))
        reg.register(SkillDef(skill_id="cand", tier="candidate",
                               produced_claims=(_claim(),)))
        reg.register(SkillDef(skill_id="trust", tier="trusted",
                               produced_claims=(_claim(),)))
        results = reg.find_by_tier("candidate")
        ids = [s.skill_id for s in results]
        assert "raw" not in ids
        assert "cand" in ids
        assert "trust" in ids

    def test_find_applicable_filters_all(self) -> None:
        reg = SkillRegistry()
        reg.register(_dialogue_skill())  # requires dialogue + screen_state_match claim
        reg.register(SkillDef(
            skill_id="proc_observe",
            tier="candidate",
            produced_claims=(_claim("observed"),),
        ))
        # Should only match proc_observe (universal, candidate+)
        results = reg.find_applicable("dialogue", available_claims=set(), min_tier="candidate")
        ids = [s.skill_id for s in results]
        assert "proc_observe" in ids
        assert "proc_dialogue_advance" not in ids  # draft < candidate

    def test_find_applicable_with_claims(self) -> None:
        reg = SkillRegistry()
        skill = SkillDef(
            skill_id="proc_dialogue_v2",
            tier="candidate",
            applicability=SkillApplicability(
                screen_states=("dialogue",),
                required_claims=("screen_state_match",),
            ),
            produced_claims=(_claim("dialogue_advanced"),),
        )
        reg.register(skill)
        results = reg.find_applicable("dialogue", available_claims={"screen_state_match"})
        assert len(results) == 1

    def test_clear(self) -> None:
        reg = SkillRegistry()
        reg.register(_dialogue_skill())
        reg.clear()
        assert reg.size == 0


# -- Applicability tests --

class TestSkillApplicability:
    def test_perfect_match(self) -> None:
        matcher = SkillApplicabilityMatcher()
        skill = _dialogue_skill()
        score = matcher.match(
            skill,
            screen_state="dialogue",
            available_claims={"screen_state_match"},
            available_anchors={"dialogue_continue"},
        )
        assert score.score == pytest.approx(1.0)
        assert score.screen_state_match
        assert score.claims_satisfied
        assert score.anchors_available
        assert score.missing_claims == ()
        assert score.missing_anchors == ()

    def test_wrong_screen_state(self) -> None:
        matcher = SkillApplicabilityMatcher()
        score = matcher.match(_dialogue_skill(), "combat")
        assert not score.screen_state_match
        assert score.score < 0.5

    def test_missing_claims(self) -> None:
        matcher = SkillApplicabilityMatcher()
        score = matcher.match(
            _dialogue_skill(), "dialogue",
            available_claims=set(),
        )
        assert not score.claims_satisfied
        assert "screen_state_match" in score.missing_claims

    def test_missing_anchors(self) -> None:
        matcher = SkillApplicabilityMatcher()
        score = matcher.match(
            _dialogue_skill(), "dialogue",
            available_claims={"screen_state_match"},
            available_anchors=set(),
        )
        assert not score.anchors_available
        assert "dialogue_continue" in score.missing_anchors

    def test_rank_orders_by_score(self) -> None:
        matcher = SkillApplicabilityMatcher()
        skills = [
            _dialogue_skill(),  # needs dialogue
            SkillDef(skill_id="universal", steps=(_step(),)),  # universal
        ]
        ranked = matcher.rank(skills, "dialogue", available_claims={"screen_state_match"})
        scores = [r.score for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_universal_skill_scores_perfect(self) -> None:
        """Skill with no applicability constraints matches everything."""
        matcher = SkillApplicabilityMatcher()
        skill = SkillDef(skill_id="observe", steps=(_step("observe", ""),))
        score = matcher.match(skill, "any_screen")
        assert score.screen_state_match
        assert score.claims_satisfied  # no required claims = vacuously satisfied
        assert score.anchors_available
        assert score.score == pytest.approx(1.0)


# -- Promotion tests --

class TestPromotion:
    def test_raw_trace_cannot_skip_to_candidate(self) -> None:
        skill = SkillDef(skill_id="raw", tier="raw_trace", steps=(_step(),))
        ok, reason = can_promote_to(skill, "candidate")
        assert not ok
        assert "skip" in reason

    def test_raw_trace_to_draft_needs_steps(self) -> None:
        skill = SkillDef(skill_id="empty_raw", tier="raw_trace")
        ok, reason = can_promote_to(skill, "draft")
        assert not ok
        assert "step" in reason

    def test_raw_trace_to_draft_with_steps(self) -> None:
        skill = SkillDef(skill_id="has_steps", tier="raw_trace", steps=(_step(),))
        ok, reason = can_promote_to(skill, "draft")
        assert ok

    def test_draft_to_experimental(self) -> None:
        skill = _dialogue_skill("draft")
        ok, reason = can_promote_to(skill, "experimental")
        assert ok

    def test_experimental_to_candidate_needs_claims(self) -> None:
        skill = SkillDef(skill_id="no_claims", tier="experimental", steps=(_step(),))
        ok, reason = can_promote_to(skill, "candidate")
        assert not ok
        assert "produced_claim" in reason

    def test_experimental_to_candidate_with_claims(self) -> None:
        skill = SkillDef(
            skill_id="has_claims", tier="experimental",
            steps=(_step(),),
            produced_claims=(_claim(),),
        )
        ok, reason = can_promote_to(skill, "candidate")
        assert ok

    def test_candidate_to_stable_needs_replays(self) -> None:
        skill = SkillDef(
            skill_id="low_replays", tier="candidate",
            steps=(_step(),),
            produced_claims=(_claim(),),
            promotion=PromotionConfig(min_replays=3),
        )
        ok, reason = can_promote_to(skill, "stable")
        assert not ok
        assert "replays" in reason

    def test_candidate_to_stable_with_enough_replays(self) -> None:
        skill = SkillDef(
            skill_id="enough", tier="candidate",
            steps=(_step(),),
            produced_claims=(_claim(),),
            promotion=PromotionConfig(min_replays=3),
            metadata={"execution_stats": {"success_count": 5}},
        )
        ok, reason = can_promote_to(skill, "stable")
        assert ok

    def test_stable_to_trusted_needs_profiles(self) -> None:
        skill = SkillDef(
            skill_id="no_profiles", tier="stable",
            steps=(_step(),),
            produced_claims=(_claim(),),
            promotion=PromotionConfig(required_profiles=("default_1920x1080", "mobile_720x1280")),
            metadata={"verified_profiles": ["default_1920x1080"]},
        )
        ok, reason = can_promote_to(skill, "trusted")
        assert not ok
        assert "missing profiles" in reason.lower() or "profiles" in reason.lower()

    def test_stable_to_trusted_with_all_profiles(self) -> None:
        skill = SkillDef(
            skill_id="all_profiles", tier="stable",
            steps=(_step(),),
            produced_claims=(_claim(),),
            promotion=PromotionConfig(required_profiles=("default_1920x1080",)),
            metadata={"verified_profiles": ["default_1920x1080"]},
        )
        ok, reason = can_promote_to(skill, "trusted")
        assert ok

    def test_cannot_promote_to_same_tier(self) -> None:
        skill = _dialogue_skill("candidate")
        ok, reason = can_promote_to(skill, "candidate")
        assert not ok

    def test_cannot_demote(self) -> None:
        skill = _dialogue_skill("stable")
        ok, reason = can_promote_to(skill, "draft")
        assert not ok

    def test_wilson_lower_bound(self) -> None:
        # All successes
        assert wilson_lower_bound(10, 0) > 0.7
        # Half successes
        assert wilson_lower_bound(5, 5) < 0.7
        # No data
        assert wilson_lower_bound(0, 0) == 0.0

    def test_meets_wilson_threshold(self) -> None:
        skill = SkillDef(
            skill_id="reliable",
            promotion=PromotionConfig(min_wilson_lower_bound=0.70),
        )
        assert meets_wilson_threshold(skill, 20, 1)  # ~0.82
        assert not meets_wilson_threshold(skill, 5, 5)  # ~0.36
        assert not meets_wilson_threshold(skill, 1, 10)
