"""Tests for online guide search, extraction, and version awareness (S-13, S-14, S-16)."""
from __future__ import annotations

import pytest

from knowledge.online_guide_system import (
    ActionableTip,
    ExtractedGuide,
    GuideCategory,
    GuideExtractor,
    GuideSearchQuery,
    GuideSearchResult,
    OnlineGuideSearcher,
    VersionUpdateAwareness,
    VersionUpdateInfo,
)


# ---------------------------------------------------------------------------
# OnlineGuideSearcher (S-13)
# ---------------------------------------------------------------------------
class TestOnlineGuideSearcher:
    def test_build_boss_queries(self) -> None:
        searcher = OnlineGuideSearcher()
        query = GuideSearchQuery(
            topic="Stormterror",
            category=GuideCategory.BOSS_STRATEGY,
            boss_name="Dvalin",
        )
        queries = searcher.build_queries(query)
        assert len(queries) > 0
        assert any("Dvalin" in q for q in queries)

    def test_build_team_queries(self) -> None:
        searcher = OnlineGuideSearcher()
        query = GuideSearchQuery(
            topic="Hu Tao",
            category=GuideCategory.TEAM_BUILD,
            character_name="胡桃",
        )
        queries = searcher.build_queries(query)
        assert len(queries) > 0

    def test_search_returns_results(self) -> None:
        searcher = OnlineGuideSearcher()
        query = GuideSearchQuery(topic="Dvalin", category=GuideCategory.BOSS_STRATEGY)
        results = searcher.search(query)
        assert len(results) > 0
        assert results[0].relevance_score > 0

    def test_search_result_category(self) -> None:
        searcher = OnlineGuideSearcher()
        query = GuideSearchQuery(topic="test", category=GuideCategory.ARTIFACT_RECOMMENDATION)
        results = searcher.search(query)
        assert all(r.category == GuideCategory.ARTIFACT_RECOMMENDATION for r in results)

    def test_query_limit(self) -> None:
        searcher = OnlineGuideSearcher()
        query = GuideSearchQuery(topic="test", category=GuideCategory.BOSS_STRATEGY, boss_name="Boss")
        queries = searcher.build_queries(query)
        assert len(queries) <= 3


# ---------------------------------------------------------------------------
# GuideExtractor (S-14)
# ---------------------------------------------------------------------------
class TestGuideExtractor:
    def test_extract_tips(self) -> None:
        extractor = GuideExtractor()
        result = GuideSearchResult(
            title="Boss攻略: 注意攻击前摇",
            url="https://example.com",
            snippet="使用火元素破盾，注意Boss攻击前摇",
            category=GuideCategory.BOSS_STRATEGY,
            relevance_score=0.9,
        )
        guide = extractor.extract(result)
        assert len(guide.tips) > 0
        assert guide.confidence == 0.9

    def test_extract_elements(self) -> None:
        extractor = GuideExtractor()
        result = GuideSearchResult(
            title="攻略",
            url="https://example.com",
            snippet="需要火元素和冰元素配合",
            category=GuideCategory.BOSS_STRATEGY,
        )
        guide = extractor.extract(result)
        assert "pyro" in guide.element_recommendations
        assert "cryo" in guide.element_recommendations

    def test_extract_warnings(self) -> None:
        extractor = GuideExtractor()
        result = GuideSearchResult(
            title="小心Boss攻略",
            url="https://example.com",
            snippet="注意Boss的范围攻击，小心被秒杀",
            category=GuideCategory.BOSS_STRATEGY,
        )
        guide = extractor.extract(result)
        assert len(guide.warning_notes) > 0

    def test_extract_batch(self) -> None:
        extractor = GuideExtractor()
        results = [
            GuideSearchResult(title="A", url="a", snippet="注意攻击"),
            GuideSearchResult(title="B", url="b", snippet="使用火元素"),
        ]
        guides = extractor.extract_batch(results)
        assert len(guides) == 2

    def test_get_top_tips(self) -> None:
        extractor = GuideExtractor()
        result = GuideSearchResult(
            title="推荐队伍: 胡桃+行秋",
            url="https://example.com",
            snippet="优先升级武器",
            category=GuideCategory.TEAM_BUILD,
        )
        guides = [extractor.extract(result)]
        tips = extractor.get_top_tips(guides, max_tips=3)
        assert len(tips) <= 3

    def test_get_top_tips_filter_category(self) -> None:
        extractor = GuideExtractor()
        result = GuideSearchResult(
            title="推荐队伍",
            url="https://example.com",
            snippet="优先升级武器，注意攻击前摇",
            category=GuideCategory.TEAM_BUILD,
        )
        guides = [extractor.extract(result)]
        tips = extractor.get_top_tips(guides, category="combat", max_tips=5)
        for tip in tips:
            assert tip.category == "combat"

    def test_team_recommendation_extraction(self) -> None:
        extractor = GuideExtractor()
        result = GuideSearchResult(
            title="配队",
            url="https://example.com",
            snippet="test",
            category=GuideCategory.TEAM_BUILD,
        )
        guide = extractor.extract(result)
        # Team extraction returns empty until real NLP extraction is implemented
        assert isinstance(guide.recommended_teams, list)


# ---------------------------------------------------------------------------
# VersionUpdateAwareness (S-16)
# ---------------------------------------------------------------------------
class TestVersionUpdateAwareness:
    def test_current_version(self) -> None:
        va = VersionUpdateAwareness()
        assert va.current_version == "5.0"

    def test_get_version_info(self) -> None:
        va = VersionUpdateAwareness()
        info = va.get_version_info("5.0")
        assert info is not None
        assert "Natlan" in info.new_regions

    def test_get_version_info_unknown(self) -> None:
        va = VersionUpdateAwareness()
        assert va.get_version_info("99.0") is None

    def test_get_behavior_impacts(self) -> None:
        va = VersionUpdateAwareness()
        impacts = va.get_behavior_impacts("5.0")
        assert len(impacts) > 0

    def test_get_behavior_impacts_unknown(self) -> None:
        va = VersionUpdateAwareness()
        assert va.get_behavior_impacts("99.0") == []

    def test_update_current_version(self) -> None:
        va = VersionUpdateAwareness()
        impacts = va.update_current_version("4.0")
        assert va.current_version == "4.0"
        # 4.0 has underwater mechanics
        assert len(impacts) > 0

    def test_check_for_updates(self) -> None:
        va = VersionUpdateAwareness()
        result = va.check_for_updates()
        # Mock returns None (no updates)
        assert result is None

    def test_parse_patch_notes_version(self) -> None:
        va = VersionUpdateAwareness()
        info = va.parse_patch_notes("版本 5.2 更新内容")
        assert info.version == "5.2"

    def test_parse_patch_notes_characters(self) -> None:
        va = VersionUpdateAwareness()
        info = va.parse_patch_notes("版本 5.1\n新角色：纳西妲、妮露")
        assert len(info.new_characters) >= 2

    def test_parse_patch_notes_regions(self) -> None:
        va = VersionUpdateAwareness()
        info = va.parse_patch_notes("版本 6.0\n新区域：至冬国")
        assert len(info.new_regions) > 0

    def test_parse_patch_notes_mechanics(self) -> None:
        va = VersionUpdateAwareness()
        info = va.parse_patch_notes("版本 5.5\n新机制：飞行模式")
        assert len(info.new_mechanics) > 0

    def test_parse_patch_notes_major_flag(self) -> None:
        va = VersionUpdateAwareness()
        info = va.parse_patch_notes("版本 6.0\n新区域\n新机制")
        assert info.is_major

    def test_state_knows_versions(self) -> None:
        va = VersionUpdateAwareness()
        assert "3.0" in va.state.known_versions
        assert "5.0" in va.state.known_versions

    def test_update_adds_unknown_version(self) -> None:
        va = VersionUpdateAwareness()
        va.update_current_version("6.0")
        assert "6.0" in va.state.known_versions
