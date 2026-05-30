"""Investment rollback: evaluating when to abandon a failed build investment.

Covers S-31: Decision framework for backing out of character/weapon investment
that proves suboptimal. Evaluates sunk cost vs. future gains to determine whether
to continue or rollback an investment path.

Integrates with:
- planning/character_build_planner.py for build plans
- planning/character_build_workflows.py for artifact evaluation
- knowledge/genshin_f2p_builds.py for build data
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Investment types
# ---------------------------------------------------------------------------

class InvestmentType(str, Enum):
    CHARACTER_LEVEL = "character_level"
    CHARACTER_ASCENSION = "character_ascension"
    WEAPON_LEVEL = "weapon_level"
    WEAPON_REFINEMENT = "weapon_refinement"
    TALENT_LEVEL = "talent_level"
    ARTIFACT_FARM = "artifact_farm"
    ARTIFACT_ENHANCEMENT = "artifact_enhancement"
    CONSTELLATION = "constellation"


class RollbackDecision(str, Enum):
    CONTINUE = "continue"        # Keep investing
    PAUSE = "pause"             # Stop for now, don't abandon
    ROLLBACK = "rollback"        # Reallocate resources
    ABANDON = "abandon"          # Give up on this path entirely


# ---------------------------------------------------------------------------
# Investment tracking
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class InvestmentRecord:
    """Record of resources invested into something."""
    target_id: str              # character_id, weapon_id, etc.
    investment_type: InvestmentType
    resin_spent: int = 0
    mora_spent: int = 0
    fragile_resin_used: int = 0
    time_invested_hours: float = 0.0
    progress_pct: float = 0.0   # 0.0 - 1.0
    start_date: str = ""
    last_update: str = ""


@dataclass(slots=True)
class InvestmentSnapshot:
    """Current state of an investment."""
    target_id: str
    target_name: str
    investment_type: InvestmentType
    current_level: int
    target_level: int
    current_rank: int = 1
    target_rank: int = 5

    # Resource totals
    total_resin: int = 0
    total_mora: int = 0
    total_fragile_resin: int = 0
    total_time_hours: float = 0.0

    # Assessment
    utility_score: float = 0.0   # How useful this character/weapon is
    alternative_value: float = 0.0  # What we could get instead
    remaining_cost: int = 0     # Resin needed to complete


@dataclass(slots=True)
class RollbackAnalysis:
    """Analysis of whether to continue or rollback an investment."""
    target_id: str
    decision: RollbackDecision
    confidence: float = 0.0

    # Comparison metrics
    sunk_cost_resin: int
    sunk_cost_mora: int
    remaining_cost_resin: int

    roi_score: float = 0.0       # Return on investment score
    sunk_cost_ratio: float = 0.0  # sunk / total

    reasoning: str = ""
    recommended_action: str = ""
    alternative_target: str = ""
    estimated_savings_resin: int = 0
    estimated_savings_mora: int = 0


# ---------------------------------------------------------------------------
# Rollback thresholds
# ---------------------------------------------------------------------------

# ROI thresholds for continuation vs rollback
CONTINUE_ROI_THRESHOLD = 1.5     # Continue if ROI >= 1.5
PAUSE_ROI_THRESHOLD = 0.8        # Pause if ROI >= 0.8
ROLLBACK_ROI_THRESHOLD = 0.5     # Rollback if ROI >= 0.5
ABANDON_ROI_THRESHOLD = 0.3      # Abandon if ROI < 0.3

# Sunk cost thresholds
MAX_SUNK_COST_PCT = 0.7         # Rollback if >70% invested but <30% complete


# ---------------------------------------------------------------------------
# Rollback calculator
# ---------------------------------------------------------------------------

class InvestmentRollbackCalculator:
    """Calculates optimal rollback decisions for suboptimal investments.

    Decision logic:
    1. Calculate ROI of remaining investment
    2. Compare to alternative investment opportunities
    3. Factor in sunk cost and strategic value
    4. Output: continue/pause/rollback/abandon
    """

    # Character utility scores (from F2P perspective)
    CHARACTER_UTILITY_SCORE: dict[str, float] = {
        "xiangling": 0.95,
        "xingqiu": 0.95,
        "bennett": 0.95,
        "kaeya": 0.7,
        "fischl": 0.8,
        "barbara": 0.7,
        "noelle": 0.5,
        "collei": 0.5,
        "lisa": 0.4,
        "amber": 0.3,
    }

    # Tier thresholds
    S_TIER_THRESHOLD = 0.9
    A_TIER_THRESHOLD = 0.7
    B_TIER_THRESHOLD = 0.5

    def analyze(
        self,
        snapshot: InvestmentSnapshot,
        alternative_characters: list[str] | None = None,
        current_ar: int = 1,
    ) -> RollbackAnalysis:
        """Analyze whether to continue or rollback an investment.

        Args:
            snapshot: Current state of the investment
            alternative_characters: Characters we could invest in instead
            current_ar: Current adventure rank (affects opportunity cost)

        Returns:
            RollbackAnalysis with decision and reasoning
        """
        total_cost = snapshot.total_resin + snapshot.remaining_cost
        sunk_pct = (snapshot.total_resin / max(total_cost, 1)) if total_cost > 0 else 0.0

        # Calculate utility vs cost
        utility_per_resin = snapshot.utility_score / max(snapshot.total_resin, 1)

        # Calculate ROI
        if snapshot.remaining_cost > 0:
            roi = (snapshot.utility_score * 100) / snapshot.remaining_cost
        else:
            roi = snapshot.utility_score * 10  # Already completed

        # Check alternative value
        alt_value = self._calculate_alternative_value(
            snapshot, alternative_characters, current_ar
        )

        # Decision tree
        decision, reasoning = self._make_decision(
            snapshot, roi, sunk_pct, alt_value
        )

        # Calculate savings from rollback
        savings_resin = 0
        savings_mora = 0
        if decision in (RollbackDecision.ROLLBACK, RollbackDecision.ABANDON):
            if snapshot.remaining_cost > 0:
                savings_resin = snapshot.remaining_cost
                savings_mora = int(snapshot.total_mora * (snapshot.remaining_cost / max(snapshot.total_resin, 1)))

        return RollbackAnalysis(
            target_id=snapshot.target_id,
            decision=decision,
            confidence=self._get_confidence(roi, sunk_pct, alt_value),
            sunk_cost_resin=snapshot.total_resin,
            sunk_cost_mora=snapshot.total_mora,
            remaining_cost_resin=snapshot.remaining_cost,
            roi_score=roi,
            sunk_cost_ratio=sunk_pct,
            reasoning=reasoning,
            recommended_action=self._get_action(decision),
            alternative_target=alt_value.get("alternative", ""),
            estimated_savings_resin=savings_resin,
            estimated_savings_mora=savings_mora,
        )

    def _calculate_alternative_value(
        self,
        snapshot: InvestmentSnapshot,
        alternatives: list[str] | None,
        current_ar: int,
    ) -> dict[str, Any]:
        """Calculate value of alternative investment options."""
        if not alternatives:
            return {}

        best_alt = ""
        best_score = 0.0
        for char_id in alternatives:
            score = self.CHARACTER_UTILITY_SCORE.get(char_id, 0.5)
            # Adjust for AR phase
            if current_ar < 30 and score >= 0.7:
                score *= 1.2  # Boost high-value chars early
            elif current_ar >= 45 and score < 0.8:
                score *= 0.8  # Deprioritize low-value late game
            if score > best_score:
                best_score = score
                best_alt = char_id

        return {
            "alternative": best_alt,
            "score": best_score,
            "utility_delta": best_score - snapshot.utility_score,
        }

    def _make_decision(
        self,
        snapshot: InvestmentSnapshot,
        roi: float,
        sunk_pct: float,
        alt: dict[str, Any],
    ) -> tuple[RollbackDecision, str]:
        """Make rollback decision based on ROI and alternatives."""
        # High utility character: always continue
        if snapshot.utility_score >= self.S_TIER_THRESHOLD:
            return RollbackDecision.CONTINUE, \
                "S-tier character - complete investment regardless of cost"

        # Low utility + high sunk cost
        if snapshot.utility_score < self.A_TIER_THRESHOLD and sunk_pct > MAX_SUNK_COST_PCT:
            return RollbackDecision.ROLLBACK, \
                f"Low utility ({snapshot.utility_score:.0%}) with {sunk_pct:.0%} sunk - rollback"

        # Check alternatives
        if alt:
            delta = alt.get("utility_delta", 0.0)
            # Much better alternative available
            if delta >= 0.4 and roi < CONTINUE_ROI_THRESHOLD:
                return RollbackDecision.ROLLBACK, \
                    f"Better alternative ({alt['alternative']}) has {delta:.0%} higher utility"

        # ROI-based decisions
        if roi >= CONTINUE_ROI_THRESHOLD:
            return RollbackDecision.CONTINUE, \
                f"ROI {roi:.1f} above threshold - continue investing"

        if roi >= PAUSE_ROI_THRESHOLD:
            return RollbackDecision.PAUSE, \
                f"ROI {roi:.1f} marginal - pause and reassess"

        if roi >= ROLLBACK_ROI_THRESHOLD:
            return RollbackDecision.ROLLBACK, \
                f"ROI {roi:.1f} low - consider rolling back"

        return RollbackDecision.ABANDON, \
            f"ROI {roi:.1f} too low - abandon investment"

    def _get_confidence(
        self,
        roi: float,
        sunk_pct: float,
        alt: dict[str, Any],
    ) -> float:
        """Calculate confidence in the decision."""
        confidence = 0.7

        # Higher confidence if ROI is extreme (very high or very low)
        if roi >= 3.0 or roi <= 0.2:
            confidence += 0.2
        elif roi >= 2.0 or roi <= 0.5:
            confidence += 0.1

        # Higher confidence with alternative data
        if alt:
            confidence += 0.1

        return min(confidence, 1.0)

    def _get_action(self, decision: RollbackDecision) -> str:
        """Get recommended action string."""
        actions = {
            RollbackDecision.CONTINUE: "Continue full investment",
            RollbackDecision.PAUSE: "Pause investment, focus on other priorities",
            RollbackDecision.ROLLBACK: "Reallocate resources to better target",
            RollbackDecision.ABANDON: "Stop investing, accept sunk cost loss",
        }
        return actions.get(decision, "Unknown action")

    def batch_analyze(
        self,
        snapshots: list[InvestmentSnapshot],
        alternative_characters: list[str] | None = None,
        current_ar: int = 1,
    ) -> list[RollbackAnalysis]:
        """Analyze multiple investments and return priority rollback list."""
        analyses = [
            self.analyze(s, alternative_characters, current_ar)
            for s in snapshots
        ]

        # Sort by ROI (worst first for rollback priority)
        analyses.sort(key=lambda a: a.roi_score)
        return analyses


# ---------------------------------------------------------------------------
# Investment tracker
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TrackedInvestment:
    """Active investment being tracked."""
    investment_id: str
    snapshot: InvestmentSnapshot
    rollback_analysis: RollbackAnalysis | None = None
    last_analyzed: float = 0.0


class InvestmentTracker:
    """Tracks investments and periodically re-evaluates rollback decisions.

    Maintains state about ongoing investments and automatically triggers
    rollback analysis when conditions change.
    """

    def __init__(self) -> None:
        self._investments: dict[str, TrackedInvestment] = {}
        self._calculator = InvestmentRollbackCalculator()

    def track(self, snapshot: InvestmentSnapshot) -> str:
        """Start tracking an investment."""
        inv_id = f"{snapshot.investment_type.value}:{snapshot.target_id}"
        tracked = TrackedInvestment(
            investment_id=inv_id,
            snapshot=snapshot,
        )
        self._investments[inv_id] = tracked
        log.info("[Tracker] tracking investment %s (level %d/%d)",
                 snapshot.target_id, snapshot.current_level, snapshot.target_level)
        return inv_id

    def update(self, investment_id: str, snapshot: InvestmentSnapshot) -> None:
        """Update investment state."""
        tracked = self._investments.get(investment_id)
        if tracked:
            tracked.snapshot = snapshot
            tracked.last_analyzed = 0.0  # Mark for re-analysis

    def analyze_all(
        self,
        alternatives: list[str] | None = None,
        current_ar: int = 1,
    ) -> list[RollbackAnalysis]:
        """Re-analyze all tracked investments."""
        results = []
        for inv_id, tracked in self._investments.items():
            analysis = self._calculator.analyze(
                tracked.snapshot, alternatives, current_ar
            )
            tracked.rollback_analysis = analysis
            results.append(analysis)
        return sorted(results, key=lambda a: a.roi_score)

    def get_rollback_candidates(self) -> list[str]:
        """Get investment IDs that should be rolled back."""
        candidates = []
        for inv_id, tracked in self._investments.items():
            if tracked.rollback_analysis and \
               tracked.rollback_analysis.decision in (
                   RollbackDecision.ROLLBACK, RollbackDecision.ABANDON
               ):
                candidates.append(inv_id)
        return candidates

    def get_savings_summary(self) -> dict[str, int]:
        """Get total savings from all rollback candidates."""
        total_resin = 0
        total_mora = 0
        for tracked in self._investments.values():
            if tracked.rollback_analysis and \
               tracked.rollback_analysis.decision in (
                   RollbackDecision.ROLLBACK, RollbackDecision.ABANDON
               ):
                total_resin += tracked.rollback_analysis.estimated_savings_resin
                total_mora += tracked.rollback_analysis.estimated_savings_mora
        return {"resin": total_resin, "mora": total_mora}

    def stop_tracking(self, investment_id: str) -> bool:
        """Stop tracking an investment."""
        if investment_id in self._investments:
            del self._investments[investment_id]
            return True
        return False