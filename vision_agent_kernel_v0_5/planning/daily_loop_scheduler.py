"""Strategic decision engine for Genshin Impact autonomous progression.

Determines WHAT to do next based on current game state:
- Adventure Rank, World Level, quest progress
- Character investment levels, team readiness
- Resource inventory (Mora, resin, materials)
- Time-of-day schedule (domain availability, daily reset)

This module produces prioritized action recommendations, not raw inputs.
It sits in the Orchestration plane and publishes ModeRequests through StateBus.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from knowledge.genshin_character_progression import TALENT_BOOK_SCHEDULE as _KNOWLEDGE_TALENT_SCHEDULE

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AR Phase switching (R-43) - Expanded phase definitions
# ---------------------------------------------------------------------------

class ARPhase(Enum):
    """Detailed AR phases for strategic decision making (R-43)."""
    AR_1_20 = "ar_1_20"       # Early game: establish core team
    AR_20_35 = "ar_20_35"    # Mid-early: build national team core
    AR_35_45 = "ar_35_45"    # Mid-late: talent/weapon focus
    AR_45_PLUS = "ar_45_plus"  # Late game: artifact optimization


@dataclass(slots=True)
class PhaseStrategy:
    """Strategic focus for each AR phase."""
    phase: ARPhase
    focus_areas: tuple[str, ...]
    domain_priority: tuple[str, ...]
    team_size_target: int
    character_level_cap: int
    notes: str


AR_PHASE_STRATEGIES: dict[ARPhase, PhaseStrategy] = {
    ARPhase.AR_1_20: PhaseStrategy(
        phase=ARPhase.AR_1_20,
        focus_areas=("quest", "exploration", "character_level"),
        domain_priority=("ley_line", "world_boss"),
        team_size_target=4,
        character_level_cap=20,
        notes="Focus on story and exploration. Use free characters. Don't invest in artifacts.",
    ),
    ARPhase.AR_20_35: PhaseStrategy(
        phase=ARPhase.AR_20_35,
        focus_areas=("character_level", "ascension", "talent"),
        domain_priority=("talent_domain", "weapon_domain", "world_boss"),
        team_size_target=4,
        character_level_cap=60,
        notes="Build national team core (Xiangling, Xingqiu, Bennett). Level to 60/70.",
    ),
    ARPhase.AR_35_45: PhaseStrategy(
        phase=ARPhase.AR_35_45,
        focus_areas=("talent", "weapon_level", "ascension"),
        domain_priority=("talent_domain", "weapon_domain", "artifact_domain"),
        team_size_target=4,
        character_level_cap=80,
        notes="Max talent levels for core team. Start preparing for AR45 artifact farming.",
    ),
    ARPhase.AR_45_PLUS: PhaseStrategy(
        phase=ARPhase.AR_45_PLUS,
        focus_areas=("artifact", "constellation", "team_building"),
        domain_priority=("artifact_domain", "talent_domain", "weapon_domain"),
        team_size_target=8,
        character_level_cap=90,
        notes="Full artifact optimization. Build second team for Abyss. Use fragile resin.",
    ),
}


def get_ar_phase(ar: int) -> ARPhase:
    """Determine AR phase from adventure rank."""
    if ar < 20:
        return ARPhase.AR_1_20
    if ar < 35:
        return ARPhase.AR_20_35
    if ar < 45:
        return ARPhase.AR_35_45
    return ARPhase.AR_45_PLUS


def get_phase_strategy(ar: int) -> PhaseStrategy:
    """Get strategic focus for the given AR."""
    phase = get_ar_phase(ar)
    return AR_PHASE_STRATEGIES[phase]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GamePhase(str, Enum):
    """Rough game phase based on Adventure Rank."""
    EARLY = "early"          # AR 1-30
    MID = "mid"              # AR 30-45
    LATE = "late"            # AR 45-55
    ENDGAME = "endgame"      # AR 55+


class ActionCategory(str, Enum):
    """Top-level action categories."""
    QUEST_ARCHON = "quest_archon"          # Push mainline story
    QUEST_WORLD = "quest_world"            # World quests for unlocks
    COMMISSIONS = "commissions"            # Daily commissions
    RESIN_SPEND = "resin_spend"            # Domains, bosses, leylines
    CHARACTER_BUILD = "character_build"    # Level/ascend/talent/artifact/weapon
    EXPLORATION = "exploration"            # Unlock waypoints, collect chests/oculi
    COMBAT_BOSS = "combat_boss"            # Weekly/world boss fights
    SHOP_MANAGE = "shop_manage"            # Buy from shops, wish
    DAILY_HOUSEKEEPING = "daily_housekeeping"  # Expeditions, teapot, parametric
    EVENT = "event"                        # Limited-time events
    SPIRAL_ABYSS = "spiral_abyss"          # Spiral Abyss runs


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class GameStateSnapshot:
    """Current game state needed for decision making."""

    adventure_rank: int = 1
    world_level: int = 0
    # Quest progress
    archon_quest_chapter: int = 0     # 0=prologue, 1=ch1, ...
    archon_quest_act: int = 0
    # Character investment (simplified)
    main_dps_level: int = 1
    main_dps_weapon_level: int = 1
    team_count: int = 1               # Number of built characters (level 60+)
    # Resources
    resin_current: int = 200
    resin_max: int = 200
    mora_millions: float = 0.0
    fragile_resin_count: int = 0
    # Time
    is_weekly_reset_day: bool = False  # Monday
    daily_commissions_done: bool = False
    weekly_bosses_done: int = 0        # 0-3 discounted
    # Flags
    has_artifact_5star_access: bool = False  # AR45+


@dataclass(slots=True)
class ActionRecommendation:
    """A single recommended action with priority and rationale."""

    category: ActionCategory
    priority: int              # Lower = more urgent (same as interrupt priority scale)
    description: str
    target: str = ""           # Specific target (domain name, character name, etc.)
    resin_cost: int = 0
    estimated_time_min: float = 5.0
    rationale: str = ""
    prerequisites: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DailySchedule:
    """Ordered list of recommended actions for the current game state."""

    phase: GamePhase = GamePhase.EARLY
    ar_phase: ARPhase = ARPhase.AR_1_20
    actions: list[ActionRecommendation] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Phase determination
# ---------------------------------------------------------------------------

def determine_phase(ar: int) -> GamePhase:
    if ar < 30:
        return GamePhase.EARLY
    if ar < 45:
        return GamePhase.MID
    if ar < 55:
        return GamePhase.LATE
    return GamePhase.ENDGAME


# ---------------------------------------------------------------------------
# Domain schedule (derived from canonical knowledge module)
# ---------------------------------------------------------------------------

# Convert knowledge module format to local format with region grouping
def _build_local_schedule() -> dict[int, dict[int, list[str]]]:
    schedule: dict[int, dict[int, list[str]]] = {}
    for day, books in _KNOWLEDGE_TALENT_SCHEDULE.items():
        region_map: dict[int, list[str]] = {}
        for book in books:
            book_lower = book.lower()
            # Mondstadt books (region 1)
            if book_lower in ("freedom", "resistance", "ballad"):
                region_map.setdefault(1, []).append(book_lower)
            # Liyue books (region 2)
            elif book_lower in ("prosperity", "diligence", "gold"):
                region_map.setdefault(2, []).append(book_lower)
            # Inazuma books (region 3)
            elif book_lower in ("transience", "elegance", "light"):
                region_map.setdefault(3, []).append(book_lower)
            # Sumeru books (region 4)
            elif book_lower in ("admonition", "ingenuity", "praxis"):
                region_map.setdefault(4, []).append(book_lower)
            # Fontaine books (region 5)
            elif book_lower in ("equity", "justice", "order"):
                region_map.setdefault(5, []).append(book_lower)
            # Natlan books (region 6)
            elif book_lower in ("contention", "kindling", "conflict"):
                region_map.setdefault(6, []).append(book_lower)
        schedule[day] = region_map
    return schedule

TALENT_BOOK_SCHEDULE: dict[int, dict[int, list[str]]] = _build_local_schedule()


# ---------------------------------------------------------------------------
# Decision engine
# ---------------------------------------------------------------------------

class StrategicDecisionEngine:
    """Produces prioritized action recommendations based on game state."""

    def evaluate(self, state: GameStateSnapshot) -> DailySchedule:
        phase = determine_phase(state.adventure_rank)
        actions: list[ActionRecommendation] = []

        # ---- P0: Commissions (always first if not done) ----
        if not state.daily_commissions_done:
            actions.append(ActionRecommendation(
                category=ActionCategory.COMMISSIONS,
                priority=5,
                description="Complete 4 daily commissions + Katheryne reward",
                estimated_time_min=10.0,
                rationale="60 primogems/day + ~1000 AR EXP",
            ))

        # ---- P1: Weekly bosses on reset day ----
        if state.is_weekly_reset_day and state.weekly_bosses_done < 3:
            remaining = 3 - state.weekly_bosses_done
            actions.append(ActionRecommendation(
                category=ActionCategory.COMBAT_BOSS,
                priority=10,
                description=f"Complete {remaining} discounted weekly boss(es)",
                resin_cost=remaining * 30,
                estimated_time_min=remaining * 10.0,
                rationale="30 resin discount, unique talent materials",
            ))

        # ---- P2: Resin spending ----
        if state.resin_current >= 40:
            actions.append(self._recommend_resin_spend(state))

        # ---- P3: Archon quest progress ----
        if self._should_push_archon(state):
            actions.append(ActionRecommendation(
                category=ActionCategory.QUEST_ARCHON,
                priority=15,
                description=f"Continue Archon Quest Chapter {state.archon_quest_chapter} Act {state.archon_quest_act}",
                estimated_time_min=30.0,
                rationale="Mainline story unlocks regions, bosses, and game systems",
            ))

        # ---- P4: Character building (if under-geared) ----
        build_rec = self._recommend_character_build(state)
        if build_rec is not None:
            actions.append(build_rec)

        # ---- P5: Exploration ----
        if self._should_explore(state):
            actions.append(ActionRecommendation(
                category=ActionCategory.EXPLORATION,
                priority=30,
                description="Explore current region: unlock waypoints, collect chests",
                estimated_time_min=20.0,
                rationale="AR EXP from exploration, primogems from chests",
            ))

        # ---- P6: Daily housekeeping ----
        actions.append(ActionRecommendation(
            category=ActionCategory.DAILY_HOUSEKEEPING,
            priority=40,
            description="Dispatch expeditions, collect teapot currency",
            estimated_time_min=3.0,
            rationale="Passive resource generation",
        ))

        # ---- P7: Events ----
        actions.append(ActionRecommendation(
            category=ActionCategory.EVENT,
            priority=35,
            description="Check and participate in active events",
            estimated_time_min=10.0,
            rationale="Limited-time primogems and materials",
        ))

        # Sort by priority
        actions.sort(key=lambda a: a.priority)
        return DailySchedule(phase=phase, actions=actions)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recommend_resin_spend(self, state: GameStateSnapshot) -> ActionRecommendation:
        phase = determine_phase(state.adventure_rank)
        if phase == GamePhase.EARLY:
            return ActionRecommendation(
                category=ActionCategory.RESIN_SPEND,
                priority=12,
                description="Spend resin on World Boss (character ascension materials)",
                resin_cost=40,
                estimated_time_min=5.0,
                rationale="AR<30: Boss drops for character ascension are highest priority",
                target="world_boss",
            )
        if phase == GamePhase.MID:
            return ActionRecommendation(
                category=ActionCategory.RESIN_SPEND,
                priority=12,
                description="Spend resin on talent/weapon domains (check daily schedule)",
                resin_cost=20,
                estimated_time_min=5.0,
                rationale="AR30-44: Talent books and weapon materials (guaranteed improvement)",
                target="domain",
            )
        # LATE / ENDGAME: Artifact domains
        return ActionRecommendation(
            category=ActionCategory.RESIN_SPEND,
            priority=12,
            description="Spend resin on Artifact domains (guaranteed 5-star drops)",
            resin_cost=20,
            estimated_time_min=5.0,
            rationale="AR45+: Artifact domains guarantee 5-star drops. Use fragile resin here.",
            target="artifact_domain",
        )

    def _should_push_archon(self, state: GameStateSnapshot) -> bool:
        # Always push if under-geared isn't blocking
        if state.main_dps_level < 40 and state.adventure_rank > 25:
            return False  # Build character first
        return True

    def _recommend_character_build(self, state: GameStateSnapshot) -> ActionRecommendation | None:
        # Weapon level is the #1 priority
        if state.main_dps_weapon_level < state.main_dps_level:
            return ActionRecommendation(
                category=ActionCategory.CHARACTER_BUILD,
                priority=20,
                description="Upgrade main DPS weapon to max available level",
                estimated_time_min=2.0,
                rationale="Weapon levels give the biggest damage boost per resource cost",
                target="weapon_upgrade",
            )
        # Character level
        if state.main_dps_level < 80 and state.adventure_rank >= 40:
            return ActionRecommendation(
                category=ActionCategory.CHARACTER_BUILD,
                priority=22,
                description="Level main DPS to 80 (or current cap)",
                estimated_time_min=2.0,
                rationale="Higher level = better base stats and talent unlock",
                target="character_level",
            )
        # Team building
        if state.team_count < 2 and state.adventure_rank >= 25:
            return ActionRecommendation(
                category=ActionCategory.CHARACTER_BUILD,
                priority=25,
                description="Build a second character to support main DPS",
                estimated_time_min=10.0,
                rationale="Need at least 2 built characters for combat flexibility",
                target="secondary_build",
            )
        return None

    def _should_explore(self, state: GameStateSnapshot) -> bool:
        # Explore when no urgent quest/build needs
        return state.adventure_rank < 55


# ---------------------------------------------------------------------------
# Failure recovery advisor
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FailureDiagnosis:
    """Analysis of why a combat encounter was lost."""

    likely_cause: str          # "undergeared", "mechanics", "team_comp", "food_needed"
    recommended_actions: list[str]
    should_retry: bool
    should_retreat: bool


class FailureAnalyzer:
    """Diagnose combat failures and recommend recovery actions."""

    def diagnose(
        self,
        state: GameStateSnapshot,
        boss_level: int = 0,
        attempts: int = 1,
        death_cause: str = "",
    ) -> FailureDiagnosis:
        level_gap = boss_level - state.main_dps_level if boss_level > 0 else 0

        # Weapon under-leveled?
        if state.main_dps_weapon_level < state.main_dps_level - 20:
            return FailureDiagnosis(
                likely_cause="undergeared",
                recommended_actions=[
                    "Upgrade main DPS weapon — it's 20+ levels behind character",
                    "This is the cheapest damage improvement",
                ],
                should_retry=False,
                should_retreat=True,
            )

        # Level gap too large?
        if level_gap > 20:
            return FailureDiagnosis(
                likely_cause="undergeared",
                recommended_actions=[
                    f"Boss is level {boss_level}, your DPS is {state.main_dps_level}",
                    "Level up main DPS and weapon before retrying",
                    "Use food buffs (ATK%, Crit Rate) for next attempt",
                ],
                should_retry=False,
                should_retreat=True,
            )

        # Died too fast → survivability issue
        if "one_shot" in death_cause.lower() or "burst" in death_cause.lower():
            return FailureDiagnosis(
                likely_cause="mechanics",
                recommended_actions=[
                    "Boss has a lethal mechanic — learn the dodge timing",
                    "Try using burst (Q) for i-frames during the lethal attack",
                    "Consider bringing a shield character",
                ],
                should_retry=True,
                should_retreat=False,
            )

        # Multiple attempts → might need strategy change
        if attempts >= 3:
            return FailureDiagnosis(
                likely_cause="team_comp",
                recommended_actions=[
                    f"Failed {attempts} times — consider changing team composition",
                    "Check element weaknesses of this boss",
                    "Search online for boss strategy guides",
                    "Use food buffs before engaging",
                ],
                should_retry=False,
                should_retreat=True,
            )

        # Default: retry with better execution
        return FailureDiagnosis(
            likely_cause="mechanics",
            recommended_actions=[
                "Learn boss attack patterns — watch for charge-up animations",
                "Dash (Shift) for i-frames on big attacks",
                "Focus damage during boss recovery windows",
            ],
            should_retry=True,
            should_retreat=False,
        )
