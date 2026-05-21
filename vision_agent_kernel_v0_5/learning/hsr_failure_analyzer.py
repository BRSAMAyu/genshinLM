from __future__ import annotations

from collections import defaultdict

from learning.genshin_failure_analyzer import (
    FailureCategory,
    FailurePattern,
    FailureSignature,
    _PATTERN_THRESHOLD,
    _common_keys,
)


class HSRFailureAnalyzer:
    """Analyze HSR-specific failure patterns: wave-based encounters, SP exhaustion, weakness exploitation."""

    def __init__(self) -> None:
        self._failures: list[FailureSignature] = []
        self._patterns: dict[str, FailurePattern] = {}

    def record_failure(self, signature: FailureSignature) -> None:
        self._failures.append(signature)
        self._patterns.clear()

    def analyze_patterns(self) -> list[FailurePattern]:
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
            patterns.extend(self._detect_wave_pattern(group))
            patterns.extend(self._detect_sp_pattern(group))
            patterns.extend(self._detect_weakness_pattern(group))

        self._patterns = {p.pattern_id: p for p in patterns}
        return patterns

    def get_suggestions(self) -> list[str]:
        patterns = self.analyze_patterns()
        return [p.suggested_fix for p in patterns if p.suggested_fix]

    def get_failure_stats(self) -> dict[str, int]:
        stats: dict[str, int] = defaultdict(int)
        for f in self._failures:
            stats[f.category.value] += 1
        return dict(stats)

    def _detect_enemy_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
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
                pattern_id=f"hsr_enemy_{group[0].category.value}_{enemy_id}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=common_ctx,
                affected_enemies=[enemy_id],
                affected_regions=regions,
                suggested_fix=f"Consider adjusting strategy against {enemy_id}",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern)
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
            enemies = list({f.enemy_id for f in group if f.enemy_id})
            pattern = FailurePattern(
                pattern_id=f"hsr_region_{group[0].category.value}_{region}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=common_ctx,
                affected_enemies=enemies,
                affected_regions=[region],
                suggested_fix=f"Review approach strategy in {region}",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern)
        return patterns

    def _detect_team_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
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
                pattern_id=f"hsr_team_{group[0].category.value}_{team_key}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=common_ctx,
                affected_enemies=enemies,
                affected_regions=regions,
                suggested_fix="Consider adjusting team composition for better element coverage",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern)
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
            enemies = list({f.enemy_id for f in group if f.enemy_id})
            regions = list({f.region for f in group if f.region})
            pattern = FailurePattern(
                pattern_id=f"hsr_step_{group[0].category.value}_{step_idx}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=common_ctx,
                affected_enemies=enemies,
                affected_regions=regions,
                suggested_fix=f"Adjust action at step {step_idx}",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern)
        return patterns

    def _detect_wave_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
        """Detect patterns tied to specific wave numbers in multi-wave encounters."""
        by_wave: dict[int, list[FailureSignature]] = defaultdict(list)
        for f in failures:
            wave = f.context.get("wave_number")
            if wave is not None:
                by_wave[int(wave)].append(f)
        patterns: list[FailurePattern] = []
        for wave, group in by_wave.items():
            if len(group) < _PATTERN_THRESHOLD:
                continue
            enemies = list({f.enemy_id for f in group if f.enemy_id})
            pattern = FailurePattern(
                pattern_id=f"hsr_wave_{group[0].category.value}_{wave}",
                category=group[0].category,
                occurrence_count=len(group),
                common_context=_common_keys([f.context for f in group]),
                affected_enemies=enemies,
                affected_regions=[],
                suggested_fix=f"Reserve resources for wave {wave} — consider SP conservation earlier",
                confidence=min(len(group) / 10.0, 1.0),
            )
            patterns.append(pattern)
        return patterns

    def _detect_sp_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
        """Detect patterns tied to SP exhaustion."""
        sp_failures = [f for f in failures if f.category == FailureCategory.STAMINA_EXHAUSTED]
        if len(sp_failures) < _PATTERN_THRESHOLD:
            return []
        enemies = list({f.enemy_id for f in sp_failures if f.enemy_id})
        pattern = FailurePattern(
            pattern_id="hsr_sp_exhaustion",
            category=FailureCategory.STAMINA_EXHAUSTED,
            occurrence_count=len(sp_failures),
            common_context=_common_keys([f.context for f in sp_failures]),
            affected_enemies=enemies,
            affected_regions=[],
            suggested_fix="Prioritize basic attacks to regenerate SP — balance skill usage across turns",
            confidence=min(len(sp_failures) / 10.0, 1.0),
        )
        return [pattern]

    def _detect_weakness_pattern(self, failures: list[FailureSignature]) -> list[FailurePattern]:
        """Detect patterns tied to incorrect element usage (weakness not exploited)."""
        weak_failures = [f for f in failures if f.category == FailureCategory.ELEMENT_MISMATCH]
        if len(weak_failures) < _PATTERN_THRESHOLD:
            return []
        enemies = list({f.enemy_id for f in weak_failures if f.enemy_id})
        enemy_str = ", ".join(enemies) if enemies else "unknown enemies"
        pattern = FailurePattern(
            pattern_id="hsr_weakness_miss",
            category=FailureCategory.ELEMENT_MISMATCH,
            occurrence_count=len(weak_failures),
            common_context=_common_keys([f.context for f in weak_failures]),
            affected_enemies=enemies,
            affected_regions=[],
            suggested_fix=f"Switch to characters that exploit weaknesses of {enemy_str}",
            confidence=min(len(weak_failures) / 10.0, 1.0),
        )
        return [pattern]
