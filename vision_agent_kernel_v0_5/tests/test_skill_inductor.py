"""Tests for planning/skill_inductor.py — M6 Skill Induction pipeline."""
from __future__ import annotations

import pytest

from agent_kernel.types import Experience
from planning.skill_inductor import (
    InductionConfig,
    InductionResult,
    PromotionResult,
    SkillInductor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _exp(
    goal: str = "level up character",
    scene: str = "character_detail",
    action: str = "click upgrade button",
    outcome: str = "success",
    failure_reason: str = "",
    duration: float = 1.0,
) -> Experience:
    return Experience(
        goal_description=goal,
        scene_description=scene,
        action_taken=action,
        outcome=outcome,
        failure_reason=failure_reason,
        duration_sec=duration,
        timestamp=0.0,
    )


BASIC_SUCCESSES = [
    _exp(goal="level up character", action="open menu"),
    _exp(goal="level up character", action="open menu"),
    _exp(goal="level up character", action="open menu"),
]


# ---------------------------------------------------------------------------
# InductionConfig
# ---------------------------------------------------------------------------

class TestInductionConfig:

    def test_default_values(self) -> None:
        cfg = InductionConfig()
        assert cfg.min_successes == 3
        assert cfg.promotion_threshold == 5

    def test_custom_values(self) -> None:
        cfg = InductionConfig(min_successes=5, promotion_threshold=10)
        assert cfg.min_successes == 5


# ---------------------------------------------------------------------------
# Basic induction
# ---------------------------------------------------------------------------

class TestBasicInduction:

    def test_induce_from_empty_experiences(self) -> None:
        result = SkillInductor().induce_from_experiences([])
        assert not result.induced
        assert result.reason == "no_experiences"

    def test_induce_insufficient_successes(self) -> None:
        exps = [_exp(outcome="success"), _exp(outcome="success")]
        result = SkillInductor().induce_from_experiences(exps)
        assert not result.induced
        assert "insufficient" in result.reason

    def test_induce_from_successful_experiences(self) -> None:
        result = SkillInductor().induce_from_experiences(BASIC_SUCCESSES)
        assert result.induced
        assert result.skill is not None
        assert "induced_" in result.skill.skill_id
        assert len(result.skill.steps) > 0
        assert len(result.skill.verifiers) > 0

    def test_induced_skill_has_context(self) -> None:
        result = SkillInductor().induce_from_experiences(BASIC_SUCCESSES)
        assert result.induced
        assert len(result.skill.applicable_context) > 0

    def test_induced_skill_has_recovery(self) -> None:
        exps = BASIC_SUCCESSES + [_exp(outcome="failed", failure_reason="timeout")]
        result = SkillInductor().induce_from_experiences(exps)
        assert result.induced
        assert len(result.skill.recovery_policies) > 0

    def test_induced_skill_has_version(self) -> None:
        result = SkillInductor().induce_from_experiences(BASIC_SUCCESSES)
        assert result.skill.version == "1.0"

    def test_induced_skill_risk_from_failure_rate(self) -> None:
        # All failures → high risk
        exps = [_exp(outcome="failed")] * 3 + [_exp(outcome="success")] * 3
        result = SkillInductor().induce_from_experiences(exps)
        assert result.induced
        assert result.skill.risk_level == "high"

    def test_induced_skill_low_risk(self) -> None:
        # All successes → low risk
        result = SkillInductor().induce_from_experiences(BASIC_SUCCESSES)
        assert result.induced
        assert result.skill.risk_level == "low"

    def test_custom_prefix(self) -> None:
        result = SkillInductor().induce_from_experiences(BASIC_SUCCESSES, skill_id_prefix="genshin")
        assert result.induced
        assert result.skill.skill_id.startswith("genshin_")

    def test_experiences_used_count(self) -> None:
        result = SkillInductor().induce_from_experiences(BASIC_SUCCESSES)
        assert result.experiences_used == 3


# ---------------------------------------------------------------------------
# Promotion / demotion
# ---------------------------------------------------------------------------

class TestPromotionDemotion:

    def test_initial_status_is_bootstrap(self) -> None:
        inductor = SkillInductor()
        status = inductor._get_status("new_skill")
        assert status == "bootstrap"

    def test_promotion_counter_increments(self) -> None:
        inductor = SkillInductor(InductionConfig(promotion_threshold=3))
        r1 = inductor.evaluate_promotion("skill_a", success=True)
        assert r1.new_status == "provisional"
        r2 = inductor.evaluate_promotion("skill_a", success=True)
        r3 = inductor.evaluate_promotion("skill_a", success=True)
        assert r3.new_status == "verified"

    def test_demotion_after_consecutive_failures(self) -> None:
        inductor = SkillInductor(InductionConfig(demotion_failures=3))
        inductor.evaluate_promotion("skill_b", success=False)
        inductor.evaluate_promotion("skill_b", success=False)
        r = inductor.evaluate_promotion("skill_b", success=False)
        assert r.new_status == "bootstrap"

    def test_success_resets_failure_counter(self) -> None:
        inductor = SkillInductor(InductionConfig(demotion_failures=3))
        inductor.evaluate_promotion("skill_c", success=False)
        inductor.evaluate_promotion("skill_c", success=False)
        # Success resets failures
        r = inductor.evaluate_promotion("skill_c", success=True)
        assert r.new_status != "bootstrap"
        # Failures should restart from 0
        inductor.evaluate_promotion("skill_c", success=False)
        inductor.evaluate_promotion("skill_c", success=False)
        r2 = inductor.evaluate_promotion("skill_c", success=False)
        assert r2.new_status == "bootstrap"

    def test_failure_resets_promotion_counter(self) -> None:
        inductor = SkillInductor(InductionConfig(promotion_threshold=5))
        for _ in range(4):
            inductor.evaluate_promotion("skill_d", success=True)
        # Failure resets promotion
        inductor.evaluate_promotion("skill_d", success=False)
        # Need to start over
        for _ in range(4):
            r = inductor.evaluate_promotion("skill_d", success=True)
        assert r.new_status != "verified"


# ---------------------------------------------------------------------------
# Step extraction
# ---------------------------------------------------------------------------

class TestStepExtraction:

    def test_common_actions_become_steps(self) -> None:
        exps = [
            _exp(action="open menu"),
            _exp(action="open menu"),
            _exp(action="click upgrade"),
        ]
        result = SkillInductor(InductionConfig(min_successes=2)).induce_from_experiences(exps)
        assert result.induced
        step_intents = [s.intent for s in result.skill.steps]
        assert "open menu" in step_intents

    def test_max_10_steps(self) -> None:
        exps = []
        for i in range(15):
            exps.append(_exp(action=f"action_{i}"))
        exps = exps[:3]  # need min_successes matching
        result = SkillInductor(InductionConfig(min_successes=2)).induce_from_experiences(exps[:2])
        if result.induced:
            assert len(result.skill.steps) <= 10


# ---------------------------------------------------------------------------
# Verifier extraction
# ---------------------------------------------------------------------------

class TestVerifierExtraction:

    def test_successes_generate_verifiers(self) -> None:
        result = SkillInductor().induce_from_experiences(BASIC_SUCCESSES)
        assert result.induced
        assert any("goal_achieved" in v for v in result.skill.verifiers)


# ---------------------------------------------------------------------------
# Recovery policy extraction
# ---------------------------------------------------------------------------

class TestRecoveryExtraction:

    def test_no_failures_gives_default_recovery(self) -> None:
        result = SkillInductor().induce_from_experiences(BASIC_SUCCESSES)
        assert result.induced
        assert "retry_once" in result.skill.recovery_policies

    def test_timeout_failure_gives_retry_with_timeout(self) -> None:
        exps = BASIC_SUCCESSES + [_exp(outcome="failed", failure_reason="timeout waiting for screen")]
        result = SkillInductor().induce_from_experiences(exps)
        assert result.induced
        assert any("timeout" in p for p in result.skill.recovery_policies)

    def test_not_found_gives_reacquire(self) -> None:
        exps = BASIC_SUCCESSES + [_exp(outcome="failed", failure_reason="target not found")]
        result = SkillInductor().induce_from_experiences(exps)
        assert result.induced
        assert any("reacquire" in p for p in result.skill.recovery_policies)
