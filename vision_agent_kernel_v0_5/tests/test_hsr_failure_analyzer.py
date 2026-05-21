from __future__ import annotations

import time

import pytest

from learning.hsr_failure_analyzer import HSRFailureAnalyzer
from learning.genshin_failure_analyzer import FailureCategory, make_failure_signature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sig(
    category: FailureCategory = FailureCategory.COMBAT_TIMEOUT,
    enemy_id: str = "enemy_a",
    region: str = "",
    team: list[str] | None = None,
    step_index: int = 0,
    context: dict | None = None,
) -> ...:
    return make_failure_signature(
        category=category,
        playbook_id="pb_test",
        step_index=step_index,
        enemy_id=enemy_id,
        team_composition=team or ["char_a", "char_b"],
        region=region,
        duration_ms=100.0,
        context=context or {},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHSRFailureAnalyzer:
    def test_record_and_analyze(self) -> None:
        """3 failures with the same enemy_id should produce an enemy pattern."""
        analyzer = HSRFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(_sig(
                category=FailureCategory.COMBAT_TIMEOUT,
                enemy_id="boss_venti",
            ))
        patterns = analyzer.analyze_patterns()
        enemy_patterns = [p for p in patterns if "enemy" in p.pattern_id]
        assert len(enemy_patterns) >= 1
        assert enemy_patterns[0].occurrence_count == 3
        assert "boss_venti" in enemy_patterns[0].affected_enemies

    def test_sp_pattern_detection(self) -> None:
        """3 STAMINA_EXHAUSTED failures should trigger SP pattern."""
        analyzer = HSRFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(_sig(
                category=FailureCategory.STAMINA_EXHAUSTED,
                enemy_id="enemy_sp",
            ))
        patterns = analyzer.analyze_patterns()
        sp_patterns = [p for p in patterns if p.pattern_id == "hsr_sp_exhaustion"]
        assert len(sp_patterns) == 1
        assert sp_patterns[0].occurrence_count == 3
        assert "basic_attacks" in sp_patterns[0].suggested_fix.lower() or "SP" in sp_patterns[0].suggested_fix

    def test_weakness_pattern_detection(self) -> None:
        """3 ELEMENT_MISMATCH failures should trigger weakness pattern."""
        analyzer = HSRFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(_sig(
                category=FailureCategory.ELEMENT_MISMATCH,
                enemy_id="enemy_weak",
            ))
        patterns = analyzer.analyze_patterns()
        weak_patterns = [p for p in patterns if p.pattern_id == "hsr_weakness_miss"]
        assert len(weak_patterns) == 1
        assert weak_patterns[0].occurrence_count == 3
        assert len(weak_patterns[0].suggested_fix) > 0

    def test_wave_pattern_detection(self) -> None:
        """3 failures with the same wave_number context should produce a wave pattern."""
        analyzer = HSRFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(_sig(
                category=FailureCategory.COMBAT_TIMEOUT,
                enemy_id="enemy_wave",
                context={"wave_number": 2},
            ))
        patterns = analyzer.analyze_patterns()
        wave_patterns = [p for p in patterns if "wave" in p.pattern_id]
        assert len(wave_patterns) >= 1
        assert wave_patterns[0].occurrence_count == 3
        assert "wave 2" in wave_patterns[0].suggested_fix.lower() or "wave" in wave_patterns[0].suggested_fix.lower()

    def test_suggestions_returned(self) -> None:
        """After patterns are detected, get_suggestions should return non-empty list."""
        analyzer = HSRFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(_sig(
                category=FailureCategory.ELEMENT_MISMATCH,
                enemy_id="boss_ice",
            ))
        suggestions = analyzer.get_suggestions()
        assert len(suggestions) >= 1
        for s in suggestions:
            assert isinstance(s, str)
            assert len(s) > 0

    def test_no_pattern_below_threshold(self) -> None:
        """Fewer than 3 failures of the same type should not produce patterns."""
        analyzer = HSRFailureAnalyzer()
        analyzer.record_failure(_sig(category=FailureCategory.COMBAT_TIMEOUT, enemy_id="boss"))
        analyzer.record_failure(_sig(category=FailureCategory.COMBAT_TIMEOUT, enemy_id="boss"))
        patterns = analyzer.analyze_patterns()
        assert len(patterns) == 0

    def test_get_failure_stats(self) -> None:
        analyzer = HSRFailureAnalyzer()
        analyzer.record_failure(_sig(category=FailureCategory.COMBAT_TIMEOUT))
        analyzer.record_failure(_sig(category=FailureCategory.STAMINA_EXHAUSTED))
        analyzer.record_failure(_sig(category=FailureCategory.STAMINA_EXHAUSTED))
        stats = analyzer.get_failure_stats()
        assert stats["combat_timeout"] == 1
        assert stats["stamina_exhausted"] == 2

    def test_region_pattern_detection(self) -> None:
        """3 failures in the same region should produce a region pattern."""
        analyzer = HSRFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(_sig(
                category=FailureCategory.NAVIGATION_FAILED,
                enemy_id="enemy_nav",
                region="jarilo_underground",
            ))
        patterns = analyzer.analyze_patterns()
        region_patterns = [p for p in patterns if "region" in p.pattern_id]
        assert len(region_patterns) >= 1
        assert "jarilo_underground" in region_patterns[0].affected_regions

    def test_team_pattern_detection(self) -> None:
        """3 failures with the same team composition should produce a team pattern."""
        analyzer = HSRFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(_sig(
                category=FailureCategory.HP_DEPLETED,
                enemy_id="boss_hp",
                team=["char_x", "char_y"],
            ))
        patterns = analyzer.analyze_patterns()
        team_patterns = [p for p in patterns if "team" in p.pattern_id]
        assert len(team_patterns) >= 1
        assert team_patterns[0].occurrence_count == 3

    def test_step_pattern_detection(self) -> None:
        """3 failures at the same step index should produce a step pattern."""
        analyzer = HSRFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(_sig(
                category=FailureCategory.SKILL_MISS,
                enemy_id="boss_step",
                step_index=5,
            ))
        patterns = analyzer.analyze_patterns()
        step_patterns = [p for p in patterns if "step" in p.pattern_id]
        assert len(step_patterns) >= 1
        assert step_patterns[0].occurrence_count == 3

    def test_patterns_cached(self) -> None:
        """Second call to analyze_patterns returns cached results."""
        analyzer = HSRFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(_sig(
                category=FailureCategory.COMBAT_TIMEOUT,
                enemy_id="boss_cache",
            ))
        first = analyzer.analyze_patterns()
        second = analyzer.analyze_patterns()
        assert len(first) == len(second)

    def test_recording_new_failure_clears_cache(self) -> None:
        """Recording a new failure after analysis should clear the pattern cache."""
        analyzer = HSRFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(_sig(
                category=FailureCategory.COMBAT_TIMEOUT,
                enemy_id="boss_a",
            ))
        _ = analyzer.analyze_patterns()
        # Recording a new failure should clear the cache
        analyzer.record_failure(_sig(
            category=FailureCategory.COMBAT_TIMEOUT,
            enemy_id="boss_a",
        ))
        # Internal pattern cache should be cleared
        assert len(analyzer._patterns) == 0
