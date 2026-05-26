from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from planning.screen_state_claim import ScreenStateClaim
from planning.skill_capability_catalog import SkillCatalogEntry, SkillCapabilityCatalog
from runtime.claim_runtime import RISK_THRESHOLDS, ReliabilityStore, RiskLevel

log = logging.getLogger(__name__)


def risk_rank(risk: str) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(risk.lower(), 1)


@dataclass(frozen=True, slots=True)
class ApplicabilityScore:
    skill_entry: SkillCatalogEntry
    score: float
    reliability: float
    risk_level: str
    allowed: bool
    reason: str


class SkillApplicabilityGate:
    """Evaluates and ranks available skills for a given goal and screen state.

    Integrates with ReliabilityStore and SkillCapabilityCatalog to balance performance
    and safety (Section B / Phase 1 of the Unified Execution Plan).
    """

    def __init__(self, catalog: SkillCapabilityCatalog, store: ReliabilityStore) -> None:
        self.catalog = catalog
        self.store = store

    def evaluate_skills(
        self,
        goal: str,
        state: ScreenStateClaim,
        risk_policy: RiskLevel = "medium",
    ) -> list[ApplicabilityScore]:
        """Filters, scores, and ranks skills based on current state and goal context."""
        matched_entries = self.catalog.by_capability(goal)
        if not matched_entries:
            # Fallback to direct skill_id match
            matched_entries = [e for e in self.catalog.entries() if e.skill_id == goal]

        if not matched_entries:
            log.debug("[ApplicabilityGate] No matching skills found for goal: %s", goal)
            return []

        threshold = RISK_THRESHOLDS.get(risk_policy)
        if threshold is None:
            log.warning("[ApplicabilityGate] Unknown risk policy: %s, falling back to medium", risk_policy)
            threshold = RISK_THRESHOLDS["medium"]

        scores: list[ApplicabilityScore] = []
        for entry in matched_entries:
            # 1. Compute anchor coverage
            anchors_found = 0
            for v in entry.verifiers:
                if state.find_elements_by_text(v) or state.find_element(v):
                    anchors_found += 1
            anchor_coverage = anchors_found / len(entry.verifiers) if entry.verifiers else 1.0

            # 2. Query ReliabilityStore
            context = {
                "capsule_id": entry.capsule_id,
                "screen_state": state.screen_state,
                "mission_phase": goal,
                "target_class": goal,
            }
            estimate = self.store.estimate(entry.skill_id, context)

            # 3. Compute dynamic score
            # score = 0.4 * goal_match + 0.3 * reliability + 0.3 * anchor_coverage
            goal_match = 1.0  # Since it's in matched_entries
            score = 0.4 * goal_match + 0.3 * estimate.reliability + 0.3 * anchor_coverage

            # 4. Check safety rules
            allowed = True
            reason = "reliability_above_threshold"

            # Check reliability against policy thresholds
            if estimate.reliability < threshold.min_auto_execution_confidence:
                allowed = False
                reason = f"reliability {estimate.reliability:.2f} below threshold {threshold.min_auto_execution_confidence:.2f}"

            # High or critical risk checks
            entry_risk = entry.risk_level
            if risk_rank(entry_risk) >= 3:
                allowed = False
                reason = "critical_risk_requires_confirmation"
            elif risk_rank(entry_risk) >= 2 and risk_policy in ("medium", "high", "critical"):
                # If skill is high risk, and reliability is below high threshold or policy is medium
                if estimate.reliability < RISK_THRESHOLDS["high"].min_auto_execution_confidence:
                    allowed = False
                    reason = f"high_risk_skill_requires_high_threshold ({RISK_THRESHOLDS['high'].min_auto_execution_confidence:.2f})"

            scores.append(
                ApplicabilityScore(
                    skill_entry=entry,
                    score=score,
                    reliability=estimate.reliability,
                    risk_level=entry_risk,
                    allowed=allowed,
                    reason=reason,
                )
            )

        # Rank by score descending, putting allowed skills first
        scores.sort(key=lambda x: (x.allowed, x.score), reverse=True)
        return scores
