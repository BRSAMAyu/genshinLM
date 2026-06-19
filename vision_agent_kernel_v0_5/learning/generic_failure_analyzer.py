"""Generic failure analyzer protocol — game-agnostic failure analysis.

Extracts the pattern detection and improvement suggestion logic from
GenshinFailureAnalyzer into a protocol that any game capsule can implement.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)


class FailureCategory(str, Enum):
    """Universal failure categories applicable across games."""
    TARGET_LOST = "target_lost"
    COMBAT_TIMEOUT = "combat_timeout"
    HP_DEPLETED = "hp_depleted"
    SKILL_MISS = "skill_miss"
    NAVIGATION_FAILED = "navigation_failed"
    COLLECTION_FAILED = "collection_failed"
    DANGER_UNAVOIDED = "danger_unavoided"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    STUCK_STATE = "stuck_state"
    PUZZLE_FAILED = "puzzle_failed"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class FailureSignature:
    """Universal failure signature — game-agnostic."""
    failure_id: str
    category: FailureCategory
    timestamp: float
    context: dict
    encounter_id: str
    step_index: int
    region: str
    duration_ms: float
    game_specific: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FailurePattern:
    """A detected recurring failure pattern."""
    pattern_id: str
    category: FailureCategory
    occurrence_count: int
    common_context: dict
    affected_encounters: list[str]
    affected_regions: list[str]
    suggested_fix: str
    confidence: float

    def with_fix(self, suggested_fix: str) -> FailurePattern:
        return FailurePattern(
            pattern_id=self.pattern_id,
            category=self.category,
            occurrence_count=self.occurrence_count,
            common_context=self.common_context,
            affected_encounters=self.affected_encounters,
            affected_regions=self.affected_regions,
            suggested_fix=suggested_fix,
            confidence=self.confidence,
        )


@runtime_checkable
class FailureAnalyzer(Protocol):
    """Protocol for game-agnostic failure analysis."""

    def record_failure(self, signature: FailureSignature) -> None: ...
    def analyze_patterns(self) -> list[FailurePattern]: ...
    def get_failure_stats(self) -> dict[str, int]: ...
    def get_suggestions(self) -> list[str]: ...


_PATTERN_THRESHOLD = 3


class GenericFailureAnalyzer:
    """Default generic failure analyzer that works across all games.

    Uses the same pattern detection logic (by encounter, region, step)
    but applies to universal FailureCategory values.
    """

    _MAX_FAILURES = 1000

    def __init__(self) -> None:
        self._failures: list[FailureSignature] = []
        self._patterns: dict[str, FailurePattern] = {}

    def record_failure(self, signature: FailureSignature) -> None:
        self._failures.append(signature)
        if len(self._failures) > self._MAX_FAILURES:
            self._failures = self._failures[-self._MAX_FAILURES:]
        self._patterns.clear()

    def analyze_patterns(self) -> list[FailurePattern]:
        if self._patterns:
            return list(self._patterns.values())

        patterns: list[FailurePattern] = []
        by_category: dict[FailureCategory, list[FailureSignature]] = defaultdict(list)
        for f in self._failures:
            by_category[f.category].append(f)

        for _cat, group in by_category.items():
            patterns.extend(self._detect_encounter_pattern(group))
            patterns.extend(self._detect_region_pattern(group))
            patterns.extend(self._detect_step_pattern(group))

        self._patterns = {p.pattern_id: p for p in patterns}
        return patterns

    def get_failure_stats(self) -> dict[str, int]:
        stats: dict[str, int] = defaultdict(int)
        for f in self._failures:
            stats[f.category.value] += 1
        return dict(stats)

    def get_suggestions(self) -> list[str]:
        patterns = self.analyze_patterns()
        return [p.suggested_fix for p in patterns if p.suggested_fix]

    def _detect_encounter_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
        by_encounter: dict[str, list[FailureSignature]] = defaultdict(list)
        for f in self._failures:
            if f.encounter_id:
                by_encounter[f.encounter_id].append(f)

        patterns: list[FailurePattern] = []
        for encounter_id, group in by_encounter.items():
            if len(group) < _PATTERN_THRESHOLD:
                continue
            common_ctx = _common_keys([f.context for f in group])
            regions = list({f.region for f in group if f.region})
            pattern = FailurePattern(
                pattern_id=f"encounter_{group[0].category.value}_{encounter_id}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=common_ctx,
                affected_encounters=[encounter_id],
                affected_regions=regions,
                suggested_fix="",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern.with_fix(_generate_fix(pattern)))
        return patterns

    def _detect_region_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
        by_region: dict[str, list[FailureSignature]] = defaultdict(list)
        for f in failures:
            if f.region:
                by_region[f.region].append(f)

        patterns: list[FailurePattern] = []
        for region, group in by_region.items():
            if len(group) < _PATTERN_THRESHOLD:
                continue
            common_ctx = _common_keys([f.context for f in group])
            encounters = list({f.encounter_id for f in group if f.encounter_id})
            pattern = FailurePattern(
                pattern_id=f"region_{group[0].category.value}_{region}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=common_ctx,
                affected_encounters=encounters,
                affected_regions=[region],
                suggested_fix="",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern.with_fix(_generate_fix(pattern)))
        return patterns

    def _detect_step_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
        by_step: dict[int, list[FailureSignature]] = defaultdict(list)
        for f in failures:
            by_step[f.step_index].append(f)

        patterns: list[FailurePattern] = []
        for step_idx, group in by_step.items():
            if len(group) < _PATTERN_THRESHOLD:
                continue
            common_ctx = _common_keys([f.context for f in group])
            encounters = list({f.encounter_id for f in group if f.encounter_id})
            regions = list({f.region for f in group if f.region})
            pattern = FailurePattern(
                pattern_id=f"step_{group[0].category.value}_{step_idx}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=common_ctx,
                affected_encounters=encounters,
                affected_regions=regions,
                suggested_fix="",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern.with_fix(_generate_fix(pattern)))
        return patterns


def make_failure_signature(
    category: FailureCategory,
    encounter_id: str = "",
    step_index: int = 0,
    region: str = "",
    duration_ms: float = 0.0,
    context: dict | None = None,
    game_specific: dict | None = None,
) -> FailureSignature:
    return FailureSignature(
        failure_id=str(uuid.uuid4()),
        category=category,
        timestamp=time.perf_counter(),
        context=context or {},
        encounter_id=encounter_id,
        step_index=step_index,
        region=region,
        duration_ms=duration_ms,
        game_specific=game_specific or {},
    )


def _common_keys(dicts: list[dict]) -> dict:
    if not dicts:
        return {}
    common: dict = {}
    first = dicts[0]
    for key, value in first.items():
        if all(d.get(key) == value for d in dicts[1:]):
            common[key] = value
    return common


def _generate_fix(pattern: FailurePattern) -> str:
    cat = pattern.category
    encounters = ", ".join(pattern.affected_encounters) if pattern.affected_encounters else "unknown"
    regions = ", ".join(pattern.affected_regions) if pattern.affected_regions else ""

    _FIX_TEMPLATES: dict[FailureCategory, str] = {
        FailureCategory.TARGET_LOST: f"Add re-acquisition steps when tracking {encounters}",
        FailureCategory.COMBAT_TIMEOUT: f"Optimize rotation for burst damage against {encounters}",
        FailureCategory.HP_DEPLETED: f"Lower HP threshold triggers for {encounters}",
        FailureCategory.SKILL_MISS: f"Adjust skill timing or positioning for {encounters}",
        FailureCategory.NAVIGATION_FAILED: f"Review navigation waypoints for {encounters}",
        FailureCategory.COLLECTION_FAILED: f"Check collection distance for {encounters}",
        FailureCategory.DANGER_UNAVOIDED: f"Increase danger sensitivity for {encounters}",
        FailureCategory.RESOURCE_EXHAUSTED: f"Add resource recovery pauses against {encounters}",
        FailureCategory.STUCK_STATE: f"Add state change detection and recovery for {encounters}",
        FailureCategory.PUZZLE_FAILED: f"Review puzzle solution approach for {encounters}",
        FailureCategory.CUSTOM: f"Review strategy for {encounters}",
    }
    return _FIX_TEMPLATES.get(cat, f"Review strategy for {encounters}")
