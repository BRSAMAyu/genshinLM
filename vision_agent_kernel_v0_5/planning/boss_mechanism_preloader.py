"""Boss mechanism preloader: pre-challenge strategy preparation.

Covers S-23: Automatically search and learn boss mechanisms before first attempt.
Downloads boss strategy data, generates pre-fight checklists, and prepares
recommended teams for unfamiliar boss encounters.

Integrates with:
- knowledge/online_guide_system.py for strategy search
- knowledge/genshin_boss_mechanisms.py for mechanism data
- planning/meta_learning.py for knowledge persistence
- combat/spiral_abyss.py for team building
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Boss categories
# ---------------------------------------------------------------------------

class BossCategory(str, Enum):
    WEEKLY_BOSS = "weekly_boss"     # Resin cost discount applies
    WORLD_BOSS = "world_boss"       # Regular boss for materials
    ARCHON_QUEST = "archon_quest"    # Story boss (main quest)
    LOCAL_LEGEND = "local_legend"    # Special overworld bosses
    SPIDER_BOSS = "spider_boss"      # Secret boss (optional)


# ---------------------------------------------------------------------------
# Preload result data types
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class BossMechanic:
    """A single boss mechanic/attack pattern."""
    name: str
    description: str
    warning_sign: str = ""           # Visual/audio cue before attack
    counter_strategy: str = ""
    is_lethal: bool = False
    phase: int = 1                  # Which phase this appears in


@dataclass(slots=True)
class BossPhase:
    """A phase of boss combat."""
    phase_id: int
    name: str
    entry_condition: str = ""
    mechanics: list[BossMechanic] = field(default_factory=list)
    recommended_elements: list[str] = field(default_factory=list)
    special_requirement: str = ""


@dataclass(slots=True)
class BossPreloadData:
    """Complete boss strategy data for pre-challenge preparation."""
    boss_id: str
    boss_name: str
    category: BossCategory
    region: str
    level_range: tuple[int, int] = (1, 90)
    recommended_level: int = 0

    phases: list[BossPhase] = field(default_factory=list)
    mechanics: list[BossMechanic] = field(default_factory=list)

    recommended_team: list[str] = field(default_factory=list)
    recommended_elements: list[str] = field(default_factory=list)

    pre_fight_checklist: list[str] = field(default_factory=list)
    food_recommendations: list[str] = field(default_factory=list)

    video_guide_url: str = ""
    written_guide_url: str = ""

    difficulty_rating: float = 0.0   # 1.0-5.0
    time_estimate_min: float = 0.0


@dataclass(slots=True)
class PreloadResult:
    """Result of boss mechanism preloading."""
    boss_id: str
    success: bool
    data: BossPreloadData | None = None
    error_message: str = ""
    sources_consulted: list[str] = field(default_factory=list)
    confidence: float = 0.0  # How confident we are in this data


# ---------------------------------------------------------------------------
# Known boss data (from official game data + community guides)
# ---------------------------------------------------------------------------

# Weekly bosses
WEEKLY_BOSS_DB: dict[str, BossPreloadData] = {
    "andrius": BossPreloadData(
        boss_id="andrius",
        boss_name="Anemo Hypostasis",
        category=BossCategory.WEEKLY_BOSS,
        region="Mondstadt",
        level_range=(30, 90),
        recommended_level=45,
        recommended_elements=["pyro", "electro"],
        pre_fight_checklist=[
            "Bring ranged character for flying phase",
            "Ensure team has pyro or electro for shield phases",
            "Use burst during summon phases for maximum damage",
        ],
        food_recommendations=["mondstadt_hash_brown", "sticky_honey_roast"],
        difficulty_rating=2.5,
        time_estimate_min=3.0,
    ),
    "marionette": BossPreloadData(
        boss_id="marionette",
        boss_name="Geo Hypostasis",
        category=BossCategory.WEEKLY_BOSS,
        region="Mondstadt",
        level_range=(30, 90),
        recommended_level=45,
        recommended_elements=["hydro", "cryo", "pyro"],
        pre_fight_checklist=[
            "Geo shields require hydro/cryo/pyro to break",
            "Stay close to boss for melee attacks",
            "Watch for falling pillars - dodge sideways",
        ],
        food_recommendations=["mushroom_pizza", "tea_break_pancake"],
        difficulty_rating=2.0,
        time_estimate_min=3.0,
    ),
    "stormbird": BossPreloadData(
        boss_id="stormbird",
        boss_name="Electro Hypostasis",
        category=BossCategory.WEEKLY_BOSS,
        region="Mondstadt",
        level_range=(40, 90),
        recommended_level=50,
        recommended_elements=["pyro"],
        pre_fight_checklist=[
            "Pyro is best counter for electro shields",
            "Wait for orbs to form before collecting",
            "Burst during lightning field for survival",
        ],
        food_recommendations=["sweet_madame", "sticky_honey_roast"],
        difficulty_rating=2.5,
        time_estimate_min=3.0,
    ),
    "childe": BossPreloadData(
        boss_id="childe",
        boss_name="Liyue Harbinger Childe",
        category=BossCategory.WEEKLY_BOSS,
        region="Liyue",
        level_range=(55, 90),
        recommended_level=70,
        recommended_elements=["pyro", "cryo", "electro"],
        phases=[
            BossPhase(
                phase_id=1, name="Melee Phase",
                mechanics=[
                    BossMechanic(
                        name="Whale Attack", description="Large hydro whale attack",
                        warning_sign="Childe raises bow", is_lethal=True,
                    ),
                ],
                recommended_elements=["shield"],
            ),
            BossPhase(
                phase_id=2, name="Ranged Phase",
                mechanics=[],
                recommended_elements=["healer"],
            ),
        ],
        pre_fight_checklist=[
            "Bring shield character for melee phase",
            "Healer recommended for phase transitions",
            "Save bursts for damage windows",
        ],
        food_recommendations=["tianshu_meat", "mushroom_pizza"],
        difficulty_rating=4.0,
        time_estimate_min=5.0,
    ),
    "azhdaha": BossPreloadData(
        boss_id="azhdaha",
        boss_name="Liyue Dragon Azhdaha",
        category=BossCategory.WEEKLY_BOSS,
        region="Liyue",
        level_range=(60, 90),
        recommended_level=80,
        recommended_elements=["cryo", "pyro", "electro", "hydro"],
        pre_fight_checklist=[
            "Build up 4 different elemental reactions",
            "Bring shield character for safety",
            "Wait for boss to emerge before attacking",
        ],
        food_recommendations=["tianshu_meat", "sticky_honey_roast"],
        difficulty_rating=4.5,
        time_estimate_min=5.0,
    ),
    "signora": BossPreloadData(
        boss_id="signora",
        boss_name="Liyue Harbinger Signora",
        category=BossCategory.WEEKLY_BOSS,
        region="Inazuma",
        level_range=(70, 90),
        recommended_level=80,
        recommended_elements=["cryo", "hydro"],
        phases=[
            BossPhase(
                phase_id=1, name="Cryo Phase",
                mechanics=[
                    BossMechanic(
                        name="Temperature Gauge",
                        description="Stay near Hearts of Flame",
                        counter_strategy="Collect temperature pickups",
                    ),
                ],
                recommended_elements=["hydro"],
            ),
            BossPhase(
                phase_id=2, name="Pyro Phase",
                mechanics=[],
                recommended_elements=["cryo"],
            ),
        ],
        pre_fight_checklist=[
            "Monitor temperature gauge carefully",
            "Collect pickups before gauge fills",
            "Phase 2 has heavy damage - heal frequently",
        ],
        food_recommendations=["tea_break_pancake", "sweet_madame"],
        difficulty_rating=4.0,
        time_estimate_min=5.0,
    ),
    "raiden_shogun": BossPreloadData(
        boss_id="raiden_shogun",
        boss_name="Electro Archon Raiden Shogun",
        category=BossCategory.WEEKLY_BOSS,
        region="Inazuma",
        level_range=(75, 90),
        recommended_level=80,
        recommended_elements=["pyro", "hydro"],
        pre_fight_checklist=[
            "Focus on destroying Eye of the Storm",
            "Build elemental energy for bursting",
            "Use bursts during special windows",
        ],
        food_recommendations=["tianshu_meat", "mondstadt_hash_brown"],
        difficulty_rating=4.5,
        time_estimate_min=5.0,
    ),
    "scaramouche": BossPreloadData(
        boss_id="scaramouche",
        boss_name="Scaramouche",
        category=BossCategory.WEEKLY_BOSS,
        region="Sumeru",
        level_range=(80, 90),
        recommended_level=85,
        recommended_elements=["pyro", "hydro"],
        pre_fight_checklist=[
            "Phase 2: collect energy blocks for machine",
            "Stun the machine to deal damage",
            "Watch for wide AoE attacks",
        ],
        food_recommendations=["tianshu_meat", "mushroom_pizza"],
        difficulty_rating=4.5,
        time_estimate_min=6.0,
    ),
    "dvalin": BossPreloadData(
        boss_id="dvalin",
        boss_name="Stormterror Dvalin",
        category=BossCategory.WEEKLY_BOSS,
        region="Mondstadt",
        level_range=(20, 90),
        recommended_level=40,
        recommended_elements=["ranged", "anemo"],
        pre_fight_checklist=[
            "Ranged character needed for flying phases",
            "Anemo traveler can handle most content",
            "Break platforms to deal damage",
        ],
        food_recommendations=["sweet_madame"],
        difficulty_rating=3.0,
        time_estimate_min=4.0,
    ),
}


# Archon quest boss data
ARCHON_BOSS_DB: dict[str, BossPreloadData] = {
    "tartaglia_archon": BossPreloadData(
        boss_id="tartaglia_archon",
        boss_name="Tartaglia (Story)",
        category=BossCategory.ARCHON_QUEST,
        region="Liyue",
        level_range=(20, 50),
        recommended_level=30,
        recommended_team=["xiangling", "bennett", "kaeya", "noelle"],
        recommended_elements=["pyro", "cryo", "geo"],
        pre_fight_checklist=[
            "National team can handle this fight",
            "Use shields for melee phase",
            "Heal during phase transitions",
        ],
        difficulty_rating=2.5,
        time_estimate_min=3.0,
    ),
    "signora_archon": BossPreloadData(
        boss_id="signora_archon",
        boss_name="Signora (Story)",
        category=BossCategory.ARCHON_QUEST,
        region="Inazuma",
        level_range=(30, 60),
        recommended_level=45,
        recommended_team=["xiangling", "bennett", "kaeya", "barbara"],
        recommended_elements=["cryo", "hydro"],
        pre_fight_checklist=[
            "Watch temperature gauge constantly",
            "Collect temperature pickups regularly",
            "Phase 2 is significantly harder",
        ],
        difficulty_rating=3.5,
        time_estimate_min=4.0,
    ),
}


# ---------------------------------------------------------------------------
# Preloader
# ---------------------------------------------------------------------------

class BossMechanismPreloader:
    """Preloads boss mechanism data before first challenge.

    Integrates with:
    - Online guide search for latest boss strategies
    - Local database for known boss patterns
    - Meta-learning for personalized strategy updates
    """

    def __init__(self) -> None:
        self._cache: dict[str, PreloadResult] = {}
        self._preload_history: dict[str, float] = {}  # boss_id -> last_preload_timestamp

    def preload_boss(
        self,
        boss_id: str,
        force_refresh: bool = False,
    ) -> PreloadResult:
        """Preload boss mechanism data.

        Args:
            boss_id: Unique boss identifier
            force_refresh: Force reload from online sources

        Returns:
            PreloadResult with boss data and strategy recommendations
        """
        # Check cache
        if not force_refresh and boss_id in self._cache:
            cached = self._cache[boss_id]
            log.info("[Preloader] using cached data for %s (confidence: %.1f)",
                     boss_id, cached.confidence)
            return cached

        # Try local databases first
        result = self._load_from_local(boss_id)
        if result is not None and result.success:
            self._cache[boss_id] = result
            self._preload_history[boss_id] = 0.0  # Will be set by timebase
            return result

        # Fall back to online search
        result = self._search_online(boss_id)
        if result is not None:
            self._cache[boss_id] = result
            return result

        # Return failure result
        return PreloadResult(
            boss_id=boss_id,
            success=False,
            error_message=f"Could not find data for boss: {boss_id}",
        )

    def preload_if_unknown(
        self,
        boss_id: str,
        encounter_count: int,
    ) -> PreloadResult | None:
        """Preload boss if not previously encountered.

        Args:
            boss_id: Boss identifier
            encounter_count: Number of times this boss has been fought

        Returns:
            PreloadResult if preloading was triggered, None otherwise
        """
        if encounter_count == 0:
            log.info("[Preloader] first encounter with %s, preloading", boss_id)
            return self.preload_boss(boss_id)
        return None

    def get_cached_data(self, boss_id: str) -> BossPreloadData | None:
        """Get cached boss data without triggering a search."""
        result = self._cache.get(boss_id)
        return result.data if result else None

    def get_pre_fight_checklist(self, boss_id: str) -> list[str]:
        """Get pre-fight checklist for a boss."""
        data = self.get_cached_data(boss_id)
        if data is None:
            self.preload_boss(boss_id)
            data = self.get_cached_data(boss_id)
        return data.pre_fight_checklist if data else []

    def get_recommended_team(self, boss_id: str) -> list[str]:
        """Get recommended team for a boss."""
        data = self.get_cached_data(boss_id)
        return data.recommended_team if data else []

    def _load_from_local(self, boss_id: str) -> PreloadResult | None:
        """Try to load boss data from local database."""
        # Check weekly boss database
        if boss_id in WEEKLY_BOSS_DB:
            data = WEEKLY_BOSS_DB[boss_id]
            return PreloadResult(
                boss_id=boss_id,
                success=True,
                data=data,
                sources_consulted=["local_weekly_boss_db"],
                confidence=0.9,
            )

        # Check archon boss database
        if boss_id in ARCHON_BOSS_DB:
            data = ARCHON_BOSS_DB[boss_id]
            return PreloadResult(
                boss_id=boss_id,
                success=True,
                data=data,
                sources_consulted=["local_archon_boss_db"],
                confidence=0.85,
            )

        return None

    def _search_online(self, boss_id: str) -> PreloadResult | None:
        """Search online for boss mechanism data."""
        try:
            from knowledge.online_guide_system import (
                OnlineGuideSearcher,
                GuideExtractor,
                GuideCategory,
            )

            searcher = OnlineGuideSearcher()
            extractor = GuideExtractor()

            # Build search query
            from knowledge.online_guide_system import GuideSearchQuery
            query = GuideSearchQuery(
                topic=boss_id,
                category=GuideCategory.BOSS_STRATEGY,
                boss_name=boss_id,
            )

            # Execute search
            results = searcher.search(query)
            if not results:
                return None

            # Extract strategy
            guides = extractor.extract_batch(results)
            if not guides:
                return None

            # Build boss data from guide
            # This is simplified - real implementation would parse guide content more thoroughly
            return PreloadResult(
                boss_id=boss_id,
                success=True,
                data=BossPreloadData(
                    boss_id=boss_id,
                    boss_name=boss_id.replace("_", " ").title(),
                    category=BossCategory.WORLD_BOSS,
                    region="Unknown",
                    pre_fight_checklist=[tip.action for tip in guides[0].tips[:5]],
                ),
                sources_consulted=[r.url for r in results[:3]],
                confidence=0.6,  # Lower confidence for online-only data
            )

        except Exception as e:
            log.warning("[Preloader] online search failed for %s: %s", boss_id, e)
            return None

    def generate_fight_plan(
        self,
        boss_id: str,
        available_characters: list[str],
    ) -> dict[str, Any]:
        """Generate a fight plan based on preloaded boss data.

        Returns:
            Dictionary with team recommendations, mechanic counters, and timing
        """
        data = self.get_cached_data(boss_id)
        if data is None:
            self.preload_boss(boss_id)
            data = self.get_cached_data(boss_id)

        if data is None:
            return {"status": "no_data", "boss_id": boss_id}

        plan: dict[str, Any] = {
            "status": "ready",
            "boss_id": boss_id,
            "difficulty": data.difficulty_rating,
            "estimated_time_min": data.time_estimate_min,
            "recommended_elements": data.recommended_elements,
            "pre_fight_checklist": data.pre_fight_checklist,
            "food_to_prepare": data.food_recommendations,
        }

        # Match recommended team with available characters
        if data.recommended_team:
            matched_team = []
            for char in data.recommended_team:
                if char in available_characters:
                    matched_team.append(char)
            plan["matched_team"] = matched_team
            plan["missing_characters"] = [
                c for c in data.recommended_team if c not in available_characters
            ]

        # Add phase-specific advice
        if data.phases:
            plan["phase_strategy"] = [
                {
                    "phase": p.phase_id,
                    "name": p.name,
                    "recommended_elements": p.recommended_elements,
                    "special_note": p.special_requirement,
                }
                for p in data.phases
            ]

        return plan

    def preload_multiple(
        self,
        boss_ids: list[str],
    ) -> dict[str, PreloadResult]:
        """Preload multiple bosses in sequence.

        Returns:
            Dict of boss_id -> PreloadResult
        """
        results: dict[str, PreloadResult] = {}
        for boss_id in boss_ids:
            results[boss_id] = self.preload_boss(boss_id)
        return results