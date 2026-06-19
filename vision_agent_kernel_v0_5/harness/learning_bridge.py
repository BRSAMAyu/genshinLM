"""Trial-and-error -> learning bridge (ROADMAP Phase 6).

Closes the self-improvement loop: the harness's failure clusters are classified
into universal :class:`~learning.generic_failure_analyzer.FailureCategory`
signatures, fed to the :class:`~learning.generic_failure_analyzer.GenericFailureAnalyzer`
to detect recurring :class:`FailurePattern`s, and persisted into the
:class:`~learning.game_knowledge_store.GameKnowledgeStore` as reusable facts.

So a failed run is no longer throwaway telemetry — each failure cluster becomes
structured, queryable knowledge the agent (and a future fix-agent) can act on.
This is the offline seed of the ROADMAP's "self-improvement speed" metric.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from harness.batch import BatchReport
from harness.core import ScenarioResult
from learning.game_knowledge_store import GameKnowledgeStore
from learning.generic_failure_analyzer import (
    FailureCategory,
    FailurePattern,
    GenericFailureAnalyzer,
    make_failure_signature,
)

# Map a (failure_code, primary tag) pair to a universal failure category.
_CODE_CATEGORY = {
    "party_wipe": FailureCategory.HP_DEPLETED,
    "out_of_bounds": FailureCategory.NAVIGATION_FAILED,
    "stuck": FailureCategory.STUCK_STATE,
    "lost": FailureCategory.NAVIGATION_FAILED,
    "wrong_choice": FailureCategory.PUZZLE_FAILED,
    "transient_fault": FailureCategory.CUSTOM,
}
_TAG_CATEGORY = {
    "combat": FailureCategory.COMBAT_TIMEOUT,   # default for combat timeouts
    "nav": FailureCategory.NAVIGATION_FAILED,
    "puzzle": FailureCategory.PUZZLE_FAILED,
    "interaction": FailureCategory.PUZZLE_FAILED,
}


def classify_failure(result: ScenarioResult) -> FailureCategory:
    """Best-effort universal category for a failed scenario result."""
    code = (result.failure_code or "").lower()
    if code in _CODE_CATEGORY:
        return _CODE_CATEGORY[code]
    if code == "timeout":
        tag = result.tags[0] if result.tags else ""
        return _TAG_CATEGORY.get(tag, FailureCategory.CUSTOM)
    if code == "max_steps":
        tag = result.tags[0] if result.tags else ""
        return _TAG_CATEGORY.get(tag, FailureCategory.STUCK_STATE)
    return FailureCategory.CUSTOM


@dataclass(slots=True)
class CampaignReport:
    """Outcome of one learn-from-failure pass over a batch."""

    total: int
    passed: int
    failure_category_counts: dict[str, int] = field(default_factory=dict)
    patterns_detected: int = 0
    knowledge_facts_written: int = 0
    top_patterns: tuple[tuple[str, str], ...] = ()  # (category, suggested_fix)


class HarnessLearningBridge:
    """Turns a BatchReport into analyzer patterns + persisted knowledge."""

    def __init__(
        self,
        analyzer: GenericFailureAnalyzer | None = None,
        store: GameKnowledgeStore | None = None,
        *,
        game_id: str = "genshin",
    ) -> None:
        self._analyzer = analyzer or GenericFailureAnalyzer()
        self._store = store
        self._game_id = game_id

    def learn_from(self, report: BatchReport, *, encounter_prefix: str = "campaign") -> CampaignReport:
        """Record every failure, detect patterns, persist knowledge facts."""
        category_counts: dict[str, int] = {}
        for result in report.results:
            if result.passed:
                continue
            category = classify_failure(result)
            category_counts[category.value] = category_counts.get(category.value, 0) + 1
            tag = result.tags[0] if result.tags else "unknown"
            self._analyzer.record_failure(make_failure_signature(
                category=category,
                encounter_id=f"{encounter_prefix}:{tag}",
                region=tag,
                context={"failure_code": result.failure_code or "",
                         "reason": result.reason, "scenario_id": result.scenario_id},
            ))

        patterns = self._analyzer.analyze_patterns()
        facts_written = self._persist(patterns)

        return CampaignReport(
            total=report.total,
            passed=report.passed,
            failure_category_counts=category_counts,
            patterns_detected=len(patterns),
            knowledge_facts_written=facts_written,
            top_patterns=tuple((p.category.value, p.suggested_fix) for p in patterns[:5]),
        )

    def _persist(self, patterns: list[FailurePattern]) -> int:
        if self._store is None:
            return 0
        written = 0
        for p in patterns:
            self._store.store(
                category="failure_pattern",
                subject=p.category.value,
                attribute="suggested_fix",
                value=p.suggested_fix,
                source="exploration",
                confidence=min(0.9, 0.4 + 0.1 * p.occurrence_count),
                game_id=self._game_id,
            )
            self._store.store(
                category="failure_pattern",
                subject=p.category.value,
                attribute="occurrence_count",
                value=str(p.occurrence_count),
                source="exploration",
                confidence=0.8,
                game_id=self._game_id,
            )
            written += 2
        return written

    @property
    def analyzer(self) -> GenericFailureAnalyzer:
        return self._analyzer


def run_campaign(
    report: BatchReport,
    *,
    store: GameKnowledgeStore | None = None,
    game_id: str = "genshin",
) -> CampaignReport:
    """One-shot convenience: learn from a finished batch report."""
    return HarnessLearningBridge(store=store, game_id=game_id).learn_from(report)


def monotonic_clock_value() -> float:
    """Stable timestamp for reproducible test seeding (perf_counter at call)."""
    return time.perf_counter()
