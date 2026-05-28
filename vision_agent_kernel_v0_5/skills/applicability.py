"""Skill OS Applicability — match skills to current screen context.

Given a screen state (from ScreenStateTree) and available claims (from
ClaimGraph), score and rank skills by applicability.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from skills.schema import SkillDef


@dataclass(frozen=True, slots=True)
class ApplicabilityScore:
    """Scored match between a skill and current context."""
    skill_id: str
    score: float  # 0.0 to 1.0
    screen_state_match: bool
    claims_satisfied: bool
    anchors_available: bool
    missing_claims: tuple[str, ...] = ()
    missing_anchors: tuple[str, ...] = ()
    reliability_lower_bound: float = 1.0
    route: str = "execute"


@dataclass(frozen=True, slots=True)
class ReliabilitySample:
    successes: int
    attempts: int


class SkillReliabilityGate:
    """Wilson lower-bound gate over profile-aware skill statistics."""

    def __init__(self, min_lower_bound: float = 0.70) -> None:
        self.min_lower_bound = min_lower_bound

    def decide(self, sample: ReliabilitySample, risk_level: str = "medium") -> tuple[str, float]:
        lower = wilson_lower_bound(sample.successes, sample.attempts)
        threshold = self.min_lower_bound
        if risk_level in {"high", "critical"}:
            threshold = max(threshold, 0.85)
        if sample.attempts == 0:
            return "exploration", 0.0
        if lower >= threshold:
            return "execute", lower
        if lower >= threshold * 0.75:
            return "exploration", lower
        return "human-review-needed", lower


class SkillApplicabilityMatcher:
    """Scores skills against current context for ranking."""

    def match(
        self,
        skill: SkillDef,
        screen_state: str,
        available_claims: set[str] | None = None,
        available_anchors: set[str] | None = None,
    ) -> ApplicabilityScore:
        """Score a single skill against context."""
        available_claims = available_claims or set()
        available_anchors = available_anchors or set()

        # Screen state match
        screen_match = (
            not skill.applicability.screen_states
            or screen_state in skill.applicability.screen_states
        )

        # Claims satisfaction
        required_claims = set(skill.applicability.required_claims)
        missing_claims = tuple(required_claims - available_claims)
        claims_ok = not required_claims or not missing_claims

        # Anchor availability
        required_anchors = set(skill.applicability.required_anchors)
        missing_anchors = tuple(required_anchors - available_anchors)
        anchors_ok = not required_anchors or not missing_anchors

        # Compute score
        score = 0.0
        if screen_match:
            score += 0.5
        if claims_ok:
            score += 0.3
        if anchors_ok:
            score += 0.2

        return ApplicabilityScore(
            skill_id=skill.skill_id,
            score=score,
            screen_state_match=screen_match,
            claims_satisfied=claims_ok,
            anchors_available=anchors_ok,
            missing_claims=missing_claims,
            missing_anchors=missing_anchors,
        )

    def rank(
        self,
        skills: list[SkillDef],
        screen_state: str,
        available_claims: set[str] | None = None,
        available_anchors: set[str] | None = None,
    ) -> list[ApplicabilityScore]:
        """Score and rank skills by applicability (highest first)."""
        scores = [
            self.match(s, screen_state, available_claims, available_anchors)
            for s in skills
        ]
        return sorted(scores, key=lambda s: s.score, reverse=True)


def wilson_lower_bound(successes: int, attempts: int, z: float = 1.96) -> float:
    if attempts <= 0:
        return 0.0
    phat = successes / attempts
    denom = 1 + z * z / attempts
    centre = phat + z * z / (2 * attempts)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * attempts)) / attempts)
    return max(0.0, (centre - margin) / denom)
