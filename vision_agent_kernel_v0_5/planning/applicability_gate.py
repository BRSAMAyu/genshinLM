from __future__ import annotations

import logging
from dataclasses import dataclass

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
        goal_tokens = _normalize_tokens(goal)
        matched_entries = self.catalog.by_capability(goal)
        if not matched_entries:
            matched_entries = [
                e for e in self.catalog.entries()
                if e.skill_id == goal or goal in set(e.planner_tags)
            ]

        if not matched_entries:
            log.debug("[ApplicabilityGate] No matching skills found for goal: %s", goal)
            return []

        threshold = RISK_THRESHOLDS.get(risk_policy)
        if threshold is None:
            log.warning("[ApplicabilityGate] Unknown risk policy: %s, falling back to medium", risk_policy)
            threshold = RISK_THRESHOLDS["medium"]

        scores: list[ApplicabilityScore] = []
        for entry in matched_entries:
            missing_caps = [
                cap for cap in entry.capabilities_required
                if cap and cap not in {state.screen_state, state.game_id, *state.raw_ocr_texts}
            ]

            # 1. Compute anchor coverage
            anchor_refs = _anchor_references(entry)
            anchors_found = sum(1 for anchor in anchor_refs if _screen_has_anchor(state, anchor))
            anchor_coverage = anchors_found / len(anchor_refs) if anchor_refs else 1.0

            # 2. Query ReliabilityStore
            context = {
                "capsule_id": entry.capsule_id,
                "screen_state": state.screen_state,
                "mission_phase": goal,
                "target_class": goal,
            }
            estimate = self.store.estimate(entry.skill_id, context)

            # 3. Compute dynamic score. Goal match is intentionally lexical and
            # conservative; the LLM can propose candidates, but runtime ranking
            # must be explainable from catalog metadata and screen evidence.
            goal_match = _goal_match(goal_tokens, entry)
            precondition_score = 0.0 if missing_caps else 1.0
            score = (
                0.25 * goal_match
                + 0.20 * precondition_score
                + 0.25 * estimate.reliability
                + 0.25 * anchor_coverage
                + 0.05 * min(1.0, len(entry.verifiers) / 2)
            )

            # 4. Check safety rules
            allowed = True
            reason = "reliability_above_threshold"

            # Check reliability against policy thresholds
            if estimate.reliability < threshold.min_auto_execution_confidence:
                allowed = False
                reason = f"reliability {estimate.reliability:.2f} below threshold {threshold.min_auto_execution_confidence:.2f}"
            if missing_caps:
                allowed = False
                reason = "missing_required_capabilities:" + ",".join(missing_caps)
            if anchor_refs and anchor_coverage <= 0.0:
                allowed = False
                reason = "required_ui_anchor_not_visible"

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


def _normalize_tokens(text: str) -> set[str]:
    normalized = text.lower().replace("_", " ").replace("-", " ")
    return {token for token in normalized.split() if token}


def _goal_match(goal_tokens: set[str], entry: SkillCatalogEntry) -> float:
    corpus = " ".join([
        entry.skill_id,
        *entry.capabilities,
        *entry.capabilities_provided,
        *entry.planner_tags,
    ]).lower().replace("_", " ").replace("-", " ")
    if not goal_tokens:
        return 1.0
    matched = sum(1 for token in goal_tokens if token in corpus)
    return matched / len(goal_tokens)


def _anchor_references(entry: SkillCatalogEntry) -> list[str]:
    refs: list[str] = []
    refs.extend(entry.ui_anchors)
    refs.extend(res.removeprefix("ui_anchor:") for res in entry.resources if res.startswith("ui_anchor:"))
    # Legacy compatibility: older tests and manifests used verifier ids as
    # text anchors. Keep this fallback, but prefer explicit ui_anchors/resources.
    if not refs:
        refs.extend(entry.verifiers)
    return [ref for ref in dict.fromkeys(refs) if ref]


def _screen_has_anchor(state: ScreenStateClaim, anchor: str) -> bool:
    if state.find_element(anchor) is not None:
        return True
    if state.find_elements_by_text(anchor):
        return True
    return any(element.element_id == anchor for element in state.ui_elements)
