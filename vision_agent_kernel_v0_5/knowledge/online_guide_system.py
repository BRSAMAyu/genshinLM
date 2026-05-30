"""Online guide search, extraction, and version update awareness.

Covers:
- S-13: Online guide search (Boss strategies, team builds, artifact recommendations)
- S-14: Guide information extraction (actionable recommendations from search results)
- S-16: Version update awareness (detect game patches, new content, mechanic changes)

Integrates with:
- planning/strategy_reader.py for WebSearchClient and MacroPlaybookGraph
- knowledge/guides/guide_loader.py for GuideKnowledgeBase
- app_service/genshin_version_adapter.py for version detection
- planning/meta_learning.py for strategy adaptation
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# S-13: Online Guide Search
# ---------------------------------------------------------------------------

class GuideCategory(str, Enum):
    """Categories of game guides."""
    BOSS_STRATEGY = "boss_strategy"
    TEAM_BUILD = "team_build"
    ARTIFACT_RECOMMENDATION = "artifact_recommendation"
    QUEST_WALKTHROUGH = "quest_walkthrough"
    EXPLORATION_TIPS = "exploration_tips"
    MATERIAL_FARMING = "material_farming"
    SPIRAL_ABYSS = "spiral_abyss"
    CHARACTER_BUILD = "character_build"


@dataclass(slots=True)
class GuideSearchResult:
    """A single search result from an online guide query."""
    title: str
    url: str
    snippet: str
    category: GuideCategory = GuideCategory.QUEST_WALKTHROUGH
    relevance_score: float = 0.0
    source: str = ""


@dataclass(slots=True)
class GuideSearchQuery:
    """A structured guide search query."""
    topic: str
    category: GuideCategory = GuideCategory.QUEST_WALKTHROUGH
    boss_name: str = ""
    character_name: str = ""
    domain_name: str = ""
    language: str = "zh"


class OnlineGuideSearcher:
    """Searches online game guides for actionable strategies (S-13).

    Provides structured queries for common game guide needs and ranks
    results by relevance to the current game context.
    """

    # Query templates per category
    _QUERY_TEMPLATES: dict[GuideCategory, list[str]] = {
        GuideCategory.BOSS_STRATEGY: [
            "{boss_name} 攻略 打法 弱点",
            "原神 {boss_name} 怎么打 队伍推荐",
            "Genshin {boss_name} boss guide strategy",
        ],
        GuideCategory.TEAM_BUILD: [
            "{character_name} 最佳队伍 配队",
            "原神 {character_name} 配队推荐",
        ],
        GuideCategory.ARTIFACT_RECOMMENDATION: [
            "{character_name} 圣遗物推荐 主词条",
            "原神 {character_name} artifacts build",
        ],
        GuideCategory.QUEST_WALKTHROUGH: [
            "{topic} 任务攻略 流程",
            "原神 {topic} walkthrough",
        ],
        GuideCategory.SPIRAL_ABYSS: [
            "深境螺旋 {topic} 满星攻略",
            "Spiral Abyss {topic} guide teams",
        ],
        GuideCategory.MATERIAL_FARMING: [
            "{topic} 材料采集路线 位置",
            "原神 {topic} farming route",
        ],
    }

    def build_queries(self, query: GuideSearchQuery) -> list[str]:
        """Build search queries from a structured query object."""
        templates = self._QUERY_TEMPLATES.get(query.category, ["{topic} 攻略"])

        replacements = {
            "{boss_name}": query.boss_name or query.topic,
            "{character_name}": query.character_name or query.topic,
            "{topic}": query.topic,
            "{domain_name}": query.domain_name or query.topic,
        }

        queries: list[str] = []
        for template in templates:
            q = template
            for old, new in replacements.items():
                q = q.replace(old, new)
            if q != template:  # At least one replacement happened
                queries.append(q)

        return queries[:3]  # Limit to 3 queries

    def search(self, query: GuideSearchQuery) -> list[GuideSearchResult]:
        """Execute search and return ranked results.

        In production, this calls WebSearchClient or MCP web search tools.
        Returns mock results for testing/offline use.
        """
        queries = self.build_queries(query)

        # Mock results based on category
        results: list[GuideSearchResult] = []
        for i, q in enumerate(queries):
            results.append(GuideSearchResult(
                title=f"攻略: {query.topic}",
                url=f"https://example.com/guide/{query.category.value}/{i}",
                snippet=self._generate_snippet(query),
                category=query.category,
                relevance_score=1.0 - i * 0.2,
                source="mock",
            ))

        log.info("[GuideSearch] found %d results for '%s' (category: %s)",
                 len(results), query.topic, query.category.value)
        return results

    def _generate_snippet(self, query: GuideSearchQuery) -> str:
        """Generate a mock snippet based on query category."""
        _SNIPPETS: dict[GuideCategory, str] = {
            GuideCategory.BOSS_STRATEGY: "注意Boss攻击前摇，利用元素反应破盾",
            GuideCategory.TEAM_BUILD: "推荐主C+副C+辅助+治疗的队伍配置",
            GuideCategory.ARTIFACT_RECOMMENDATION: "优先选择暴击率/暴击伤害主词条",
            GuideCategory.QUEST_WALKTHROUGH: "跟随任务标记前进，注意NPC对话选择",
            GuideCategory.SPIRAL_ABYSS: "上下半各需要独立队伍，注意元素盾需求",
            GuideCategory.MATERIAL_FARMING: "按照路线图采集，注意材料刷新时间",
            GuideCategory.EXPLORATION_TIPS: "使用元素视野发现隐藏物品",
            GuideCategory.CHARACTER_BUILD: "优先升级武器和圣遗物主词条",
        }
        return _SNIPPETS.get(query.category, "通用攻略信息")


# ---------------------------------------------------------------------------
# S-14: Guide Information Extraction
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ActionableTip:
    """An extracted actionable recommendation from a guide."""
    action: str
    category: str  # "combat", "team", "artifact", "strategy", "exploration"
    priority: str = "medium"  # "high", "medium", "low"
    context: str = ""
    source_url: str = ""


@dataclass(slots=True)
class ExtractedGuide:
    """Processed guide with extracted actionable information."""
    title: str
    source_url: str
    category: GuideCategory
    tips: list[ActionableTip] = field(default_factory=list)
    recommended_teams: list[list[str]] = field(default_factory=list)
    element_recommendations: list[str] = field(default_factory=list)
    warning_notes: list[str] = field(default_factory=list)
    confidence: float = 0.0


class GuideExtractor:
    """Extracts actionable recommendations from guide search results (S-14).

    Parses raw guide text into structured, machine-readable recommendations
    that can be fed into the combat planner and team builder.
    """

    # Action extraction patterns
    _ACTION_PATTERNS: list[tuple[str, str, str]] = [
        # (regex, category, priority)
        (r"推荐.*?队伍[：:]\s*(.+)", "team", "high"),
        (r"使用.{1,6}元素.*?破盾", "combat", "high"),
        (r"注意.*?攻击前摇", "combat", "medium"),
        (r"优先.*?升级", "strategy", "high"),
        (r"优先.*?暴击", "artifact", "high"),
        (r"需要.*?元素", "team", "high"),
        (r"避免.*?冲刺", "combat", "medium"),
        (r"安全距离", "combat", "medium"),
    ]

    # Element keywords for extraction
    _ELEMENT_NAMES = {"火", "水", "冰", "雷", "风", "岩", "草"}
    _ELEMENT_MAP = {
        "火": "pyro", "水": "hydro", "冰": "cryo",
        "雷": "electro", "风": "anemo", "岩": "geo", "草": "dendro",
    }

    def extract(self, result: GuideSearchResult) -> ExtractedGuide:
        """Extract structured information from a search result."""
        guide = ExtractedGuide(
            title=result.title,
            source_url=result.url,
            category=result.category,
            confidence=result.relevance_score,
        )

        text = f"{result.title} {result.snippet}"

        # Extract actionable tips
        for pattern, category, priority in self._ACTION_PATTERNS:
            match = re.search(pattern, text)
            if match:
                guide.tips.append(ActionableTip(
                    action=match.group(1) if match.lastindex else match.group(0),
                    category=category,
                    priority=priority,
                    source_url=result.url,
                ))

        # Extract element recommendations
        for element_char, element_en in self._ELEMENT_MAP.items():
            if element_char in text:
                guide.element_recommendations.append(element_en)

        # Extract warning keywords
        _WARNINGS = {"注意", "避免", "小心", "不要", "切勿", "危险"}
        for word in _WARNINGS:
            idx = text.find(word)
            if idx >= 0:
                context = text[max(0, idx - 10):idx + 30]
                guide.warning_notes.append(context.strip())

        # TODO: implement real team extraction from guide text
        # Currently returns empty — consumers should handle the mock case

        log.info("[GuideExtract] extracted %d tips, %d elements from '%s'",
                 len(guide.tips), len(guide.element_recommendations), result.title)
        return guide

    def extract_batch(self, results: list[GuideSearchResult]) -> list[ExtractedGuide]:
        """Extract from multiple search results."""
        return [self.extract(r) for r in results]

    def get_top_tips(self, guides: list[ExtractedGuide],
                     category: str = "",
                     max_tips: int = 5) -> list[ActionableTip]:
        """Get the highest-priority tips across all guides."""
        all_tips: list[ActionableTip] = []
        for guide in guides:
            for tip in guide.tips:
                if category and tip.category != category:
                    continue
                all_tips.append(tip)

        # Sort by priority
        _PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
        all_tips.sort(key=lambda t: _PRIORITY_ORDER.get(t.priority, 3))
        return all_tips[:max_tips]


# ---------------------------------------------------------------------------
# S-16: Version Update Awareness
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class VersionUpdateInfo:
    """Information about a game version update."""
    version: str
    release_date: str
    new_regions: list[str] = field(default_factory=list)
    new_characters: list[str] = field(default_factory=list)
    new_bosses: list[str] = field(default_factory=list)
    new_mechanics: list[str] = field(default_factory=list)
    balance_changes: list[str] = field(default_factory=list)
    ui_changes: list[str] = field(default_factory=list)
    is_major: bool = False


@dataclass(slots=True)
class VersionAwarenessState:
    """Tracks known version information and pending updates."""
    current_version: str = "5.0"
    known_versions: list[str] = field(default_factory=list)
    pending_changes: list[str] = field(default_factory=list)


class VersionUpdateAwareness:
    """Monitors and adapts to game version updates (S-16).

    Responsibilities:
    1. Track current game version
    2. Detect new version changes from patch notes
    3. Identify mechanic/UI changes that affect agent behavior
    4. Generate adaptation recommendations
    """

    # Known version history (representative)
    _VERSION_HISTORY: dict[str, VersionUpdateInfo] = {
        "3.0": VersionUpdateInfo(
            version="3.0", release_date="2022-08-24",
            new_regions=["Sumeru"],
            new_mechanics=["Dendro element", "Quicken/Spread/Bloom reactions"],
            is_major=True,
        ),
        "4.0": VersionUpdateInfo(
            version="4.0", release_date="2023-08-16",
            new_regions=["Fontaine"],
            new_mechanics=["Underwater exploration", "Arkhe system (Pneuma/Ousia)"],
            is_major=True,
        ),
        "5.0": VersionUpdateInfo(
            version="5.0", release_date="2024-08-28",
            new_regions=["Natlan"],
            new_mechanics=["Saurian possession", "Nightsoul points"],
            new_characters=["Mualani", "Kachina", "Kinich"],
            is_major=True,
        ),
    }

    # Mechanic changes that affect agent behavior
    _BEHAVIOR_IMPACTS: dict[str, list[str]] = {
        "Dendro element": ["New reaction chains", "Team composition changes"],
        "Underwater exploration": ["New movement mode", "3D navigation needed"],
        "Saurian possession": ["New interaction type", "Special movement"],
        "Nightsoul points": ["New resource to track"],
        "Arkhe system": ["Boss weakness mechanic"],
    }

    def __init__(self) -> None:
        self._state = VersionAwarenessState(
            current_version="5.0",
            known_versions=list(self._VERSION_HISTORY.keys()),
        )

    @property
    def current_version(self) -> str:
        return self._state.current_version

    @property
    def state(self) -> VersionAwarenessState:
        return self._state

    def check_for_updates(self) -> VersionUpdateInfo | None:
        """Check if there's a newer version than what we know about.

        In production, this would query official sources or patch note APIs.
        Returns None if no updates found or we're on the latest.
        """
        # Mock: no new updates in test environment
        log.info("[VersionAwareness] checking for updates, current: %s",
                 self._state.current_version)
        return None

    def get_version_info(self, version: str) -> VersionUpdateInfo | None:
        """Get information about a specific version."""
        return self._VERSION_HISTORY.get(version)

    def get_behavior_impacts(self, version: str) -> list[str]:
        """Get behavior adaptations needed for a given version."""
        info = self._VERSION_HISTORY.get(version)
        if info is None:
            return []

        impacts: list[str] = []
        for mechanic in info.new_mechanics:
            if mechanic in self._BEHAVIOR_IMPACTS:
                impacts.extend(self._BEHAVIOR_IMPACTS[mechanic])
        return impacts

    def update_current_version(self, version: str) -> list[str]:
        """Update the known current version and return adaptation needs."""
        old_version = self._state.current_version
        self._state.current_version = version

        if version not in self._state.known_versions:
            self._state.known_versions.append(version)

        impacts = self.get_behavior_impacts(version)
        if impacts:
            log.warning("[VersionAwareness] version %s has %d behavior impacts: %s",
                        version, len(impacts), ", ".join(impacts))

        log.info("[VersionAwareness] updated from %s to %s", old_version, version)
        return impacts

    def parse_patch_notes(self, notes_text: str) -> VersionUpdateInfo:
        """Parse patch notes text into structured update info.

        Extracts key information like new characters, regions, and mechanics.
        """
        info = VersionUpdateInfo(version="unknown", release_date="unknown")

        # Extract version number
        version_match = re.search(r"(\d+\.\d+)", notes_text)
        if version_match:
            info.version = version_match.group(1)

        # Extract new character names (common pattern in patch notes)
        char_matches = re.findall(r"新角色[：:]\s*(.+?)(?:\n|$)", notes_text)
        for match in char_matches:
            info.new_characters.extend(
                name.strip() for name in match.split("、") if name.strip()
            )

        # Extract new region keywords
        _REGION_KEYWORDS = ["新区域", "新地图", "新大陆", "新国家"]
        seen_regions: set[str] = set()
        for kw in _REGION_KEYWORDS:
            idx = notes_text.find(kw)
            while idx >= 0:
                fragment = notes_text[idx + len(kw):idx + len(kw) + 20].strip("：:，。、 ")
                if fragment and fragment not in seen_regions:
                    info.new_regions.append(fragment)
                    seen_regions.add(fragment)
                idx = notes_text.find(kw, idx + 1)

        # Extract mechanic changes
        _MECHANIC_KEYWORDS = ["新机制", "新元素", "新系统"]
        seen_mechanics: set[str] = set()
        for kw in _MECHANIC_KEYWORDS:
            idx = notes_text.find(kw)
            while idx >= 0:
                fragment = notes_text[idx + len(kw):idx + len(kw) + 30].strip("：:，。、 ")
                if fragment and fragment not in seen_mechanics:
                    info.new_mechanics.append(fragment)
                    seen_mechanics.add(fragment)
                idx = notes_text.find(kw, idx + 1)

        # Detect if major update
        info.is_major = bool(info.new_regions) or bool(info.new_mechanics)

        log.info("[VersionAwareness] parsed patch notes: version=%s, "
                 "regions=%d, chars=%d, mechanics=%d",
                 info.version, len(info.new_regions),
                 len(info.new_characters), len(info.new_mechanics))
        return info
