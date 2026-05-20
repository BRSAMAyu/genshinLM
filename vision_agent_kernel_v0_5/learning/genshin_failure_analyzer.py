from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum


class FailureCategory(Enum):
    TARGET_LOST = "target_lost"
    COMBAT_TIMEOUT = "combat_timeout"
    HP_DEPLETED = "hp_depleted"
    SKILL_MISS = "skill_miss"
    NAVIGATION_FAILED = "navigation_failed"
    COLLECTION_FAILED = "collection_failed"
    DANGER_UNAVOIDED = "danger_unavoided"
    ELEMENT_MISMATCH = "element_mismatch"
    STAMINA_EXHAUSTED = "stamina_exhausted"


@dataclass(frozen=True, slots=True)
class FailureSignature:
    failure_id: str
    category: FailureCategory
    timestamp: float
    context: dict
    playbook_id: str
    step_index: int
    enemy_id: str
    team_composition: list[str]
    region: str
    duration_ms: float


@dataclass(frozen=True, slots=True)
class FailurePattern:
    pattern_id: str
    category: FailureCategory
    occurrence_count: int
    common_context: dict
    affected_enemies: list[str]
    affected_regions: list[str]
    suggested_fix: str
    confidence: float

    def with_fix(self, suggested_fix: str) -> FailurePattern:
        return FailurePattern(
            pattern_id=self.pattern_id,
            category=self.category,
            occurrence_count=self.occurrence_count,
            common_context=self.common_context,
            affected_enemies=self.affected_enemies,
            affected_regions=self.affected_regions,
            suggested_fix=suggested_fix,
            confidence=self.confidence,
        )


_PATTERN_THRESHOLD = 3


class GenshinFailureAnalyzer:
    """Analyze combat failures and generate improvement suggestions."""

    def __init__(self) -> None:
        self._failures: list[FailureSignature] = []
        self._patterns: dict[str, FailurePattern] = {}

    def record_failure(self, signature: FailureSignature) -> None:
        """Record a new failure event."""
        self._failures.append(signature)
        self._patterns.clear()

    def analyze_patterns(self) -> list[FailurePattern]:
        """Identify recurring failure patterns from recorded failures."""
        if self._patterns:
            return list(self._patterns.values())

        patterns: list[FailurePattern] = []
        by_category: dict[FailureCategory, list[FailureSignature]] = defaultdict(list)
        for f in self._failures:
            by_category[f.category].append(f)

        for _cat, group in by_category.items():
            patterns.extend(self._detect_enemy_pattern(group))
            patterns.extend(self._detect_region_pattern(group))
            patterns.extend(self._detect_team_pattern(group))
            patterns.extend(self._detect_step_pattern(group))

        self._patterns = {p.pattern_id: p for p in patterns}
        return patterns

    def generate_improved_playbook(self, original_playbook_id: str) -> dict:
        """Generate an improved playbook based on failure analysis."""
        if not self._patterns:
            self.analyze_patterns()

        relevant = [
            f for f in self._failures if f.playbook_id == original_playbook_id
        ]
        if not relevant:
            return {"playbook_id": original_playbook_id, "adjustments": []}

        adjustments: list[dict] = []
        seen_categories: set[FailureCategory] = set()

        for failure in relevant:
            cat = failure.category
            if cat in seen_categories:
                continue
            seen_categories.add(cat)

            if cat == FailureCategory.TARGET_LOST:
                adjustments.append({
                    "type": "tracking_patience",
                    "change": "increase_coasting_window_ms",
                    "value": 2000,
                })
                adjustments.append({
                    "type": "re_acquisition",
                    "change": "add_re_acquire_step_after_lost",
                    "value": True,
                })
            elif cat == FailureCategory.HP_DEPLETED:
                adjustments.append({
                    "type": "defensive_trigger",
                    "change": "lower_hp_threshold",
                    "value": 0.4,
                })
                adjustments.append({
                    "type": "defensive_trigger",
                    "change": "add_shield_check",
                    "value": True,
                })
            elif cat == FailureCategory.COMBAT_TIMEOUT:
                adjustments.append({
                    "type": "rotation",
                    "change": "prioritize_burst_damage",
                    "value": True,
                })
                adjustments.append({
                    "type": "rotation",
                    "change": "reduce_normal_attack_repeat",
                    "value": 3,
                })
            elif cat == FailureCategory.DANGER_UNAVOIDED:
                adjustments.append({
                    "type": "dodge_sensitivity",
                    "change": "lower_danger_threshold",
                    "value": 0.5,
                })
                adjustments.append({
                    "type": "dodge_sensitivity",
                    "change": "increase_danger_sensitivity",
                    "value": True,
                })
            elif cat == FailureCategory.ELEMENT_MISMATCH:
                adjustments.append({
                    "type": "team_suggestion",
                    "change": "recommend_counter_elements",
                    "value": True,
                })

        return {"playbook_id": original_playbook_id, "adjustments": adjustments}

    def get_failure_stats(self) -> dict[str, int]:
        """Return failure counts by category."""
        stats: dict[str, int] = defaultdict(int)
        for f in self._failures:
            stats[f.category.value] += 1
        return dict(stats)

    def get_suggestions(self) -> list[str]:
        """Get human-readable suggestions for improvement."""
        patterns = self.analyze_patterns()
        return [p.suggested_fix for p in patterns if p.suggested_fix]

    def _detect_enemy_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
        """Detect patterns tied to specific enemies."""
        by_enemy: dict[str, list[FailureSignature]] = defaultdict(list)
        for f in failures:
            if f.enemy_id:
                by_enemy[f.enemy_id].append(f)

        patterns: list[FailurePattern] = []
        for enemy_id, group in by_enemy.items():
            if len(group) < _PATTERN_THRESHOLD:
                continue
            common_ctx = _common_keys([f.context for f in group])
            regions = list({f.region for f in group if f.region})
            pattern = FailurePattern(
                pattern_id=f"enemy_{group[0].category.value}_{enemy_id}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=common_ctx,
                affected_enemies=[enemy_id],
                affected_regions=regions,
                suggested_fix="",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern.with_fix(self._generate_fix(pattern)))
        return patterns

    def _detect_region_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
        """Detect patterns tied to specific regions."""
        by_region: dict[str, list[FailureSignature]] = defaultdict(list)
        for f in failures:
            if f.region:
                by_region[f.region].append(f)

        patterns: list[FailurePattern] = []
        for region, group in by_region.items():
            if len(group) < _PATTERN_THRESHOLD:
                continue
            common_ctx = _common_keys([f.context for f in group])
            enemies = list({f.enemy_id for f in group if f.enemy_id})
            pattern = FailurePattern(
                pattern_id=f"region_{group[0].category.value}_{region}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=common_ctx,
                affected_enemies=enemies,
                affected_regions=[region],
                suggested_fix="",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern.with_fix(self._generate_fix(pattern)))
        return patterns

    def _detect_team_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
        """Detect patterns tied to specific team compositions."""
        by_team: dict[str, list[FailureSignature]] = defaultdict(list)
        for f in failures:
            key = ",".join(sorted(f.team_composition))
            by_team[key].append(f)

        patterns: list[FailurePattern] = []
        for team_key, group in by_team.items():
            if len(group) < _PATTERN_THRESHOLD:
                continue
            common_ctx = _common_keys([f.context for f in group])
            enemies = list({f.enemy_id for f in group if f.enemy_id})
            regions = list({f.region for f in group if f.region})
            pattern = FailurePattern(
                pattern_id=f"team_{group[0].category.value}_{team_key}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=common_ctx,
                affected_enemies=enemies,
                affected_regions=regions,
                suggested_fix="",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern.with_fix(self._generate_fix(pattern)))
        return patterns

    def _detect_step_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
        """Detect patterns tied to specific playbook step indices."""
        by_step: dict[int, list[FailureSignature]] = defaultdict(list)
        for f in failures:
            by_step[f.step_index].append(f)

        patterns: list[FailurePattern] = []
        for step_idx, group in by_step.items():
            if len(group) < _PATTERN_THRESHOLD:
                continue
            common_ctx = _common_keys([f.context for f in group])
            enemies = list({f.enemy_id for f in group if f.enemy_id})
            regions = list({f.region for f in group if f.region})
            pattern = FailurePattern(
                pattern_id=f"step_{group[0].category.value}_{step_idx}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=common_ctx,
                affected_enemies=enemies,
                affected_regions=regions,
                suggested_fix="",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern.with_fix(self._generate_fix(pattern)))
        return patterns

    def _generate_fix(self, pattern: FailurePattern) -> str:
        """Generate an actionable fix suggestion for a pattern."""
        cat = pattern.category
        enemies = ", ".join(pattern.affected_enemies) if pattern.affected_enemies else "unknown enemy"
        regions = ", ".join(pattern.affected_regions) if pattern.affected_regions else ""

        if cat == FailureCategory.TARGET_LOST:
            return f"Add re-acquisition steps when tracking {enemies}"
        if cat == FailureCategory.COMBAT_TIMEOUT:
            return f"Optimize rotation for burst damage against {enemies}"
        if cat == FailureCategory.HP_DEPLETED:
            return f"Lower HP threshold triggers and add defensive actions for {enemies}"
        if cat == FailureCategory.SKILL_MISS:
            return f"Adjust skill timing or positioning for {enemies}"
        if cat == FailureCategory.NAVIGATION_FAILED:
            loc = f" in {regions}" if regions else ""
            return f"Review navigation waypoints{loc} for {enemies}"
        if cat == FailureCategory.COLLECTION_FAILED:
            return f"Check collection distance and approach angle for {enemies}"
        if cat == FailureCategory.DANGER_UNAVOIDED:
            return f"Increase danger sensitivity and lower dodge threshold for {enemies}"
        if cat == FailureCategory.ELEMENT_MISMATCH:
            return f"Consider switching team elements to counter {enemies}"
        if cat == FailureCategory.STAMINA_EXHAUSTED:
            return f"Reduce sprint usage and add stamina recovery pauses against {enemies}"
        return f"Review strategy for {enemies}"


def make_failure_signature(
    category: FailureCategory,
    playbook_id: str = "",
    step_index: int = 0,
    enemy_id: str = "",
    team_composition: list[str] | None = None,
    region: str = "",
    duration_ms: float = 0.0,
    context: dict | None = None,
) -> FailureSignature:
    """Convenience factory for FailureSignature."""
    return FailureSignature(
        failure_id=str(uuid.uuid4()),
        category=category,
        timestamp=time.perf_counter(),
        context=context or {},
        playbook_id=playbook_id,
        step_index=step_index,
        enemy_id=enemy_id,
        team_composition=list(team_composition) if team_composition else [],
        region=region,
        duration_ms=duration_ms,
    )


def _common_keys(dicts: list[dict]) -> dict:
    """Return key-value pairs shared across all dicts with identical values."""
    if not dicts:
        return {}
    common: dict = {}
    first = dicts[0]
    for key, value in first.items():
        if all(d.get(key) == value for d in dicts[1:]):
            common[key] = value
    return common
