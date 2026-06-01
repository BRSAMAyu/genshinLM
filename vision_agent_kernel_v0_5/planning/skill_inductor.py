"""SkillInductor — induce SkillRecipes from execution traces (Experience records).

M6 of the SPARKLE roadmap: "将录制轨迹和成功运行自动归纳为 Skill Recipe"

The induction pipeline:
1. Collect successful Experience records with matching goal patterns
2. Cluster by scene context + action sequence similarity
3. Generate a SkillRecipe with extracted steps, verifiers, and recovery policies
4. Register the induced skill in the SkillCapabilityCatalog
5. Promote after N successful verifications (promotion threshold)

Also handles version drift: when a skill's verifier starts failing consistently,
the skill is demoted to bootstrap status for re-induction.

See: docs/SPARKLE_AGENT_KERNEL_DESIGN.md §8 (Skill Compression)
See: agent_kernel/types.py SkillRecipe, Experience
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass

from agent_kernel.types import Experience, SkillRecipe, SkillStep

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Induction types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class InductionConfig:
    """Configuration for skill induction."""
    min_successes: int = 3          # Minimum successful experiences to induce a skill
    min_confidence: float = 0.7     # Minimum average confidence for induced steps
    promotion_threshold: int = 5    # Successful runs before promoting to "verified"
    demotion_failures: int = 3      # Consecutive failures before demoting to "bootstrap"
    version: str = "1.0"


@dataclass(frozen=True, slots=True)
class InductionResult:
    """Result of a skill induction attempt."""
    induced: bool
    skill: SkillRecipe | None = None
    reason: str = ""
    experiences_used: int = 0


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Result of a skill promotion/demotion evaluation."""
    skill_id: str
    old_status: str
    new_status: str
    reason: str = ""


# ---------------------------------------------------------------------------
# SkillInductor — core induction engine
# ---------------------------------------------------------------------------

class SkillInductor:
    """Induce SkillRecipes from successful execution traces.

    Usage:
        inductor = SkillInductor()
        result = inductor.induce_from_experiences(experiences)
        if result.induced:
            catalog.register_induced_skill(entry_from_recipe(result.skill))
    """

    def __init__(self, config: InductionConfig | None = None) -> None:
        self._config = config or InductionConfig()
        self._promotion_counters: dict[str, int] = {}  # skill_id → success count
        self._failure_counters: dict[str, int] = {}     # skill_id → consecutive fail count

    @property
    def config(self) -> InductionConfig:
        return self._config

    def induce_from_experiences(
        self,
        experiences: list[Experience],
        skill_id_prefix: str = "induced",
    ) -> InductionResult:
        """Attempt to induce a SkillRecipe from a list of experiences.

        Groups successful experiences by goal pattern, extracts common
        action sequences, and generates a SkillRecipe if enough data exists.
        """
        if not experiences:
            return InductionResult(induced=False, reason="no_experiences")

        # Filter to successful experiences only
        successes = [e for e in experiences if e.outcome == "success"]
        if len(successes) < self._config.min_successes:
            return InductionResult(
                induced=False,
                reason=f"insufficient_successes({len(successes)}<{self._config.min_successes})",
                experiences_used=len(successes),
            )

        # Extract common goal pattern
        goal_pattern = self._extract_goal_pattern(successes)
        if not goal_pattern:
            return InductionResult(induced=False, reason="no_goal_pattern")

        # Extract common context
        contexts = self._extract_contexts(successes)

        # Generate steps from action sequences
        steps = self._extract_steps(successes)
        if not steps:
            return InductionResult(induced=False, reason="no_steps_extracted")

        # Generate verifiers from outcomes
        verifiers = self._extract_verifiers(successes)

        # Generate recovery policies from failures
        failures = [e for e in experiences if e.outcome == "failed"]
        recoveries = self._extract_recovery_policies(failures)

        # Compute confidence
        avg_duration = sum(e.duration_sec for e in successes) / len(successes)
        confidence = min(1.0, len(successes) / (2 * self._config.min_successes))

        # Determine risk level from failure rate
        fail_rate = len(failures) / max(1, len(experiences))
        risk = "low" if fail_rate < 0.1 else "medium" if fail_rate < 0.3 else "high"

        skill_id = f"{skill_id_prefix}_{goal_pattern}_{uuid.uuid4().hex[:6]}"
        recipe = SkillRecipe(
            skill_id=skill_id,
            title=f"Induced: {goal_pattern}",
            goal_template=goal_pattern,
            applicable_context=tuple(contexts),
            preconditions=(),
            steps=tuple(steps),
            verifiers=tuple(verifiers),
            recovery_policies=tuple(recoveries),
            risk_level=risk,
            version=self._config.version,
        )

        log.info("[SkillInductor] Induced skill %s from %d experiences (%.0f%% success)",
                 skill_id, len(successes), (1 - fail_rate) * 100)

        return InductionResult(
            induced=True,
            skill=recipe,
            reason=f"induced_from_{len(successes)}_successes",
            experiences_used=len(successes),
        )

    def evaluate_promotion(self, skill_id: str, success: bool) -> PromotionResult:
        """Evaluate whether a skill should be promoted or demoted.

        Promotion: after N consecutive successes → "verified"
        Demotion: after N consecutive failures → "bootstrap"
        """
        old_status = self._get_status(skill_id)

        if success:
            self._promotion_counters[skill_id] = self._promotion_counters.get(skill_id, 0) + 1
            self._failure_counters.pop(skill_id, None)

            new_status = self._get_status(skill_id)
            if self._promotion_counters[skill_id] >= self._config.promotion_threshold:
                new_status = "verified"
            return PromotionResult(
                skill_id=skill_id,
                old_status=old_status,
                new_status=new_status,
                reason="promoting" if new_status != "verified" else f"{self._promotion_counters[skill_id]}_consecutive_successes",
            )
        else:
            self._failure_counters[skill_id] = self._failure_counters.get(skill_id, 0) + 1
            self._promotion_counters.pop(skill_id, None)

            new_status = self._get_status(skill_id)
            if self._failure_counters[skill_id] >= self._config.demotion_failures:
                return PromotionResult(
                    skill_id=skill_id,
                    old_status=old_status,
                    new_status="bootstrap",
                    reason=f"{self._failure_counters[skill_id]}_consecutive_failures",
                )
            return PromotionResult(
                skill_id=skill_id,
                old_status=old_status,
                new_status=new_status,
                reason="demoting",
            )

    def _get_status(self, skill_id: str) -> str:
        if skill_id in self._promotion_counters:
            if self._promotion_counters[skill_id] >= self._config.promotion_threshold:
                return "verified"
            return "provisional"
        return "bootstrap"

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_goal_pattern(self, experiences: list[Experience]) -> str:
        """Extract a common goal pattern from experiences."""
        if not experiences:
            return ""
        goals = [e.goal_description for e in experiences]
        # Simple approach: use the shortest common substring
        base = goals[0]
        for goal in goals[1:]:
            # Find longest common prefix (simplified)
            common_len = 0
            for a, b in zip(base, goal):
                if a == b:
                    common_len += 1
                else:
                    break
            if common_len > 3:
                base = base[:common_len]
        return base.strip() if len(base) > 3 else goals[0].split()[0] if goals[0] else ""

    def _extract_contexts(self, experiences: list[Experience]) -> list[str]:
        """Extract common scene contexts."""
        scenes: dict[str, int] = {}
        for e in experiences:
            for word in e.scene_description.split():
                word = word.strip(" ,.，。")
                if len(word) >= 2:
                    scenes[word] = scenes.get(word, 0) + 1
        threshold = max(1, len(experiences) // 2)
        return sorted(w for w, c in scenes.items() if c >= threshold)[:5]

    def _extract_steps(self, experiences: list[Experience]) -> list[SkillStep]:
        """Extract skill steps from action descriptions."""
        actions = [e.action_taken for e in experiences]
        # Count action frequency
        action_counts: dict[str, int] = {}
        for action in actions:
            action_counts[action] = action_counts.get(action, 0) + 1

        # Use actions that appear in majority of experiences
        threshold = max(1, len(experiences) // 2)
        common_actions = sorted(
            (a for a, c in action_counts.items() if c >= threshold),
            key=lambda a: action_counts[a],
            reverse=True,
        )

        steps: list[SkillStep] = []
        for i, action in enumerate(common_actions[:10]):
            steps.append(SkillStep(
                step_id=f"s{i+1}",
                intent=action,
                target_query=action,
            ))
        return steps

    def _extract_verifiers(self, experiences: list[Experience]) -> list[str]:
        """Extract verifier names from successful outcomes."""
        verifiers: set[str] = set()
        for e in experiences:
            if e.outcome == "success":
                # Derive verifier from goal + outcome
                goal_words = e.goal_description.split()[:3]
                verifiers.add(f"goal_achieved_{'_'.join(goal_words)}")
        return sorted(verifiers)

    def _extract_recovery_policies(self, failures: list[Experience]) -> list[str]:
        """Extract recovery policies from failure patterns."""
        if not failures:
            return ["retry_once"]

        reasons: dict[str, int] = {}
        for f in failures:
            reason = f.failure_reason or "unknown"
            # Normalize common patterns
            reason = re.sub(r"\d+", "N", reason)
            reasons[reason] = reasons.get(reason, 0) + 1

        policies: list[str] = []
        top_reasons = sorted(reasons, key=reasons.get, reverse=True)[:3]
        for reason in top_reasons:
            if "timeout" in reason.lower():
                policies.append("retry_with_longer_timeout")
            elif "not found" in reason.lower() or "丢失" in reason:
                policies.append("reacquire_target")
            elif "fail" in reason.lower() or "失败" in reason:
                policies.append("retry_with_different_approach")
            else:
                policies.append("retry_once")

        if not policies:
            policies = ["retry_once"]
        return policies
