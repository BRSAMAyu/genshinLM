from __future__ import annotations

import pytest

from app_service.genshin_version_adapter import GenshinVersionAdapter, VersionProfile
from learning.genshin_failure_analyzer import (
    FailureCategory,
    FailureSignature,
    GenshinFailureAnalyzer,
    make_failure_signature,
)


# ---------------------------------------------------------------------------
# Failure analyzer tests
# ---------------------------------------------------------------------------


class TestRecordFailure:
    def test_record_failure_count(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        sig = make_failure_signature(FailureCategory.TARGET_LOST)
        analyzer.record_failure(sig)
        assert len(analyzer._failures) == 1
        analyzer.record_failure(make_failure_signature(FailureCategory.HP_DEPLETED))
        assert len(analyzer._failures) == 2


class TestFailureCategories:
    @pytest.mark.parametrize("cat", list(FailureCategory))
    def test_all_categories_exist(self, cat: FailureCategory) -> None:
        assert cat.value is not None
        assert isinstance(cat.value, str)

    def test_category_count(self) -> None:
        assert len(FailureCategory) == 9


class TestAnalyzeNoPatterns:
    def test_few_failures_no_patterns(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        analyzer.record_failure(make_failure_signature(FailureCategory.TARGET_LOST))
        analyzer.record_failure(make_failure_signature(FailureCategory.TARGET_LOST))
        patterns = analyzer.analyze_patterns()
        assert patterns == []


class TestAnalyzeEnemyPattern:
    def test_three_same_enemy_creates_pattern(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(
                make_failure_signature(
                    FailureCategory.TARGET_LOST, enemy_id="ruin_guard",
                ),
            )
        patterns = analyzer.analyze_patterns()
        enemy_patterns = [p for p in patterns if p.pattern_id.startswith("enemy_")]
        assert len(enemy_patterns) >= 1
        assert enemy_patterns[0].occurrence_count == 3
        assert "ruin_guard" in enemy_patterns[0].affected_enemies

    def test_different_enemies_no_pattern(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        analyzer.record_failure(
            make_failure_signature(FailureCategory.TARGET_LOST, enemy_id="ruin_guard"),
        )
        analyzer.record_failure(
            make_failure_signature(FailureCategory.TARGET_LOST, enemy_id="hilichurl"),
        )
        analyzer.record_failure(
            make_failure_signature(FailureCategory.TARGET_LOST, enemy_id="slime"),
        )
        patterns = analyzer.analyze_patterns()
        enemy_patterns = [p for p in patterns if p.pattern_id.startswith("enemy_")]
        assert enemy_patterns == []


class TestAnalyzeRegionPattern:
    def test_three_same_region_creates_pattern(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(
                make_failure_signature(
                    FailureCategory.NAVIGATION_FAILED, region="liyue",
                ),
            )
        patterns = analyzer.analyze_patterns()
        region_patterns = [p for p in patterns if p.pattern_id.startswith("region_")]
        assert len(region_patterns) >= 1
        assert "liyue" in region_patterns[0].affected_regions


class TestFailureStatsByCategory:
    def test_stats_count_correctly(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        analyzer.record_failure(make_failure_signature(FailureCategory.TARGET_LOST))
        analyzer.record_failure(make_failure_signature(FailureCategory.TARGET_LOST))
        analyzer.record_failure(make_failure_signature(FailureCategory.HP_DEPLETED))
        stats = analyzer.get_failure_stats()
        assert stats["target_lost"] == 2
        assert stats["hp_depleted"] == 1

    def test_empty_stats(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        stats = analyzer.get_failure_stats()
        assert stats == {}


class TestSuggestionsGenerated:
    def test_suggestions_after_analysis(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        for _ in range(3):
            analyzer.record_failure(
                make_failure_signature(
                    FailureCategory.TARGET_LOST, enemy_id="abyss_mage",
                ),
            )
        suggestions = analyzer.get_suggestions()
        assert len(suggestions) >= 1
        assert any("abyss_mage" in s for s in suggestions)

    def test_no_suggestions_without_patterns(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        analyzer.record_failure(make_failure_signature(FailureCategory.TARGET_LOST))
        suggestions = analyzer.get_suggestions()
        assert suggestions == []


class TestImprovedPlaybookTargetLost:
    def test_target_lost_adds_reacquisition(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        analyzer.record_failure(
            make_failure_signature(
                FailureCategory.TARGET_LOST,
                playbook_id="pb_test_enemy",
            ),
        )
        result = analyzer.generate_improved_playbook("pb_test_enemy")
        assert result["playbook_id"] == "pb_test_enemy"
        adjustments = result["adjustments"]
        types = [a["type"] for a in adjustments]
        assert "tracking_patience" in types
        assert "re_acquisition" in types


class TestImprovedPlaybookHpDepleted:
    def test_hp_depleted_adds_defensive_triggers(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        analyzer.record_failure(
            make_failure_signature(
                FailureCategory.HP_DEPLETED,
                playbook_id="pb_test_enemy",
            ),
        )
        result = analyzer.generate_improved_playbook("pb_test_enemy")
        adjustments = result["adjustments"]
        types = [a["type"] for a in adjustments]
        assert "defensive_trigger" in types

    def test_empty_playbook_no_adjustments(self) -> None:
        analyzer = GenshinFailureAnalyzer()
        result = analyzer.generate_improved_playbook("nonexistent")
        assert result["adjustments"] == []


# ---------------------------------------------------------------------------
# Version adapter tests
# ---------------------------------------------------------------------------


class TestVersionDefault:
    def test_default_version_is_5_0(self) -> None:
        adapter = GenshinVersionAdapter()
        assert adapter.version == (5, 0)


class TestVersionString:
    def test_version_string_formatting(self) -> None:
        adapter = GenshinVersionAdapter()
        assert adapter.version_string == "5.0"

    def test_version_string_after_update(self) -> None:
        adapter = GenshinVersionAdapter()
        adapter.update_version((4, 0))
        assert adapter.version_string == "4.0"


class TestVersionUpdateManual:
    def test_manual_update_works(self) -> None:
        adapter = GenshinVersionAdapter()
        adapter.update_version((3, 0))
        assert adapter.version == (3, 0)

    def test_manual_update_unknown_version(self) -> None:
        adapter = GenshinVersionAdapter()
        adapter.update_version((6, 0))
        assert adapter.version == (6, 0)
        assert adapter.version_string == "6.0"


class TestRoiAdjustmentsDefault:
    def test_default_adjustments_empty(self) -> None:
        adapter = GenshinVersionAdapter()
        assert adapter.get_roi_adjustments() == {}


class TestVersionKnownVersions:
    def test_at_least_three_known_versions(self) -> None:
        assert len(GenshinVersionAdapter.KNOWN_VERSIONS) >= 3

    def test_known_versions_keys(self) -> None:
        keys = list(GenshinVersionAdapter.KNOWN_VERSIONS.keys())
        assert (5, 0) in keys
        assert (4, 0) in keys
        assert (3, 0) in keys


class TestMenuLayout:
    def test_default_menu_layout(self) -> None:
        adapter = GenshinVersionAdapter()
        assert adapter.get_menu_layout() == "grid_v5"

    def test_menu_layout_after_version_change(self) -> None:
        adapter = GenshinVersionAdapter()
        adapter.update_version((3, 0))
        assert adapter.get_menu_layout() == "grid_v3"


class TestCheckUiCompatibility:
    def test_compatible_result(self) -> None:
        adapter = GenshinVersionAdapter()
        result = adapter.check_ui_compatibility({
            "state": "world_hud",
            "confidence": 0.9,
            "indicators": {"minimap": True, "dark_frame": False},
        })
        assert result["compatible"] is True
        assert result["confidence"] == 0.9
        assert result["warnings"] == []

    def test_incompatible_low_confidence(self) -> None:
        adapter = GenshinVersionAdapter()
        result = adapter.check_ui_compatibility({
            "state": "world_hud",
            "confidence": 0.1,
            "indicators": {"minimap": True},
        })
        assert result["compatible"] is False


class TestFailureSignatureFrozen:
    def test_failure_signature_is_frozen(self) -> None:
        sig = make_failure_signature(FailureCategory.TARGET_LOST)
        with pytest.raises(AttributeError):
            sig.category = FailureCategory.HP_DEPLETED  # type: ignore[misc]

    def test_failure_signature_fields(self) -> None:
        sig = make_failure_signature(
            FailureCategory.COMBAT_TIMEOUT,
            playbook_id="pb_001",
            step_index=2,
            enemy_id="ruin_guard",
            team_composition=["pyro", "hydro"],
            region="mondstadt",
            duration_ms=5000.0,
            context={"hp": 0.2},
        )
        assert sig.category == FailureCategory.COMBAT_TIMEOUT
        assert sig.playbook_id == "pb_001"
        assert sig.step_index == 2
        assert sig.enemy_id == "ruin_guard"
        assert sig.team_composition == ["pyro", "hydro"]
        assert sig.region == "mondstadt"
        assert sig.duration_ms == 5000.0
        assert sig.context == {"hp": 0.2}
        assert sig.failure_id != ""
        assert sig.timestamp > 0.0


class TestVersionProfileFrozen:
    def test_version_profile_is_frozen(self) -> None:
        vp = VersionProfile(4, 0, "grid_v4", "v4_redesign", "v4", {})
        with pytest.raises(AttributeError):
            vp.major = 5  # type: ignore[misc]
