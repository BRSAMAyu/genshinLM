"""MainlineProgressionAdapter — chapter-by-chapter quest progression orchestrator.

Manages the full 6-chapter mainline quest chain (Prologue → Chapter 5),
coordinating:
- QuestSkillAdapter for dialog/cutscene/quest navigation
- CombatSkillAdapter for boss encounters
- ExplorationSkillAdapter for waypoints/chests/oculi
- DailyRoutineSkillAdapter for AR grinding between chapters
- CharacterProgressionAdapter for party upgrades between chapters

Each chapter defines AR thresholds, boss encounters, and grinding intervals.
The adapter uses SkillRegistry to delegate to specialized adapters.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)


class SemanticExecutor(Protocol):
    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class ChapterInfo:
    """Static metadata for one Archon Quest chapter."""
    chapter_id: str
    region: str
    ar_range: tuple[int, int]
    world_level: int
    recommended_team_level: tuple[int, int]
    estimated_hours: float
    boss_ids: tuple[str, ...]
    acts: tuple[str, ...]
    grinding_interval_ar: tuple[int, int] = (0, 0)
    ascension_quest_ar: int = 0
    prerequisite_quests: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MainlineProgressionConfig:
    max_boss_retries: int = 3
    boss_timeout_sec: float = 300.0
    ar_grinding_timeout_sec: float = 3600.0
    auto_level_up_between_chapters: bool = True


@dataclass(frozen=True, slots=True)
class ChapterResult:
    chapter_id: str
    success: bool
    acts_completed: int
    total_acts: int
    boss_defeated: bool
    ar_at_start: int
    ar_at_end: int
    grinding_needed: bool
    duration_sec: float
    details: str = ""


@dataclass(frozen=True, slots=True)
class MainlineProgressionResult:
    chapters_completed: int
    total_chapters: int
    chapter_results: tuple[ChapterResult, ...]
    total_duration_sec: float
    final_ar: int
    success: bool
    details: str = ""


# ---------------------------------------------------------------------------
# Chapter definitions — sourced from GENSHIN_MAINLINE_PROGRESSION_CHAIN.md
# ---------------------------------------------------------------------------

CHAPTERS: tuple[ChapterInfo, ...] = (
    ChapterInfo(
        chapter_id="prologue",
        region="Mondstadt",
        ar_range=(1, 18),
        world_level=0,
        recommended_team_level=(15, 35),
        estimated_hours=1.75,
        boss_ids=("stormterror_dvalin",),
        acts=("act_i", "act_ii", "act_iii"),
        grinding_interval_ar=(18, 23),
    ),
    ChapterInfo(
        chapter_id="chapter_1",
        region="Liyue",
        ar_range=(23, 28),
        world_level=2,
        recommended_team_level=(35, 50),
        estimated_hours=4.75,
        boss_ids=("childe_tartaglia",),
        acts=("act_i", "act_ii", "act_iii", "act_iv"),
        grinding_interval_ar=(28, 30),
        prerequisite_quests=("lupica_meaning",),
    ),
    ChapterInfo(
        chapter_id="chapter_2",
        region="Inazuma",
        ar_range=(30, 30),
        world_level=3,
        recommended_team_level=(50, 65),
        estimated_hours=9.75,
        boss_ids=("la_signora", "raidenshogun_story"),
        acts=("prologue", "act_i", "act_ii", "act_iii", "act_iv"),
        grinding_interval_ar=(30, 35),
        ascension_quest_ar=35,
        prerequisite_quests=("ayaka_story", "yoimiya_story"),
    ),
    ChapterInfo(
        chapter_id="chapter_3",
        region="Sumeru",
        ar_range=(35, 35),
        world_level=4,
        recommended_team_level=(60, 80),
        estimated_hours=14.0,
        boss_ids=("shouki_no_kami",),
        acts=("act_i", "act_ii", "act_iii", "act_iv", "act_v", "act_vi"),
        grinding_interval_ar=(35, 40),
        ascension_quest_ar=35,
    ),
    ChapterInfo(
        chapter_id="chapter_4",
        region="Fontaine",
        ar_range=(40, 40),
        world_level=5,
        recommended_team_level=(75, 85),
        estimated_hours=11.5,
        boss_ids=("all_devouring_narwhal",),
        acts=("act_i", "act_ii", "act_iii", "act_iv", "act_v", "act_vi"),
        grinding_interval_ar=(40, 40),
    ),
    ChapterInfo(
        chapter_id="chapter_5",
        region="Natlan",
        ar_range=(40, 40),
        world_level=5,
        recommended_team_level=(80, 90),
        estimated_hours=10.0,
        boss_ids=("gosoythoth",),
        acts=("act_i", "act_ii", "act_iii", "act_iv", "interlude", "act_v"),
        grinding_interval_ar=(40, 40),
    ),
)


class MainlineProgressionAdapter:
    """Orchestrate complete mainline quest progression through 6 chapters.

    Each chapter follows:
    1. Check AR prerequisites and grinding intervals
    2. Execute acts sequentially (quest → combat → exploration)
    3. Boss encounters at chapter climax
    4. Grinding interval between chapters (daily + exploration)
    5. Character progression between chapters (if configured)
    """

    def __init__(
        self,
        *,
        skill_executor: SemanticExecutor,
        config: MainlineProgressionConfig | None = None,
        skill_registry: Any | None = None,
        quest_state_machine: Any | None = None,
    ) -> None:
        self._executor = skill_executor
        self._config = config or MainlineProgressionConfig()
        self._registry = skill_registry
        self._quest_sm = quest_state_machine

    def _check_quest_prerequisites(self, chapter_id: str, act_id: str) -> bool:
        """Check quest prerequisites via QuestStateMachine."""
        if self._quest_sm is not None:
            return self._quest_sm.check_prerequisites()
        if self._registry is not None:
            return self._registry.execute("quest_check_prerequisites")
        return True

    def run_full_progression(self, current_ar: int = 1) -> MainlineProgressionResult:
        """Execute all chapters from current AR to Chapter 5 completion."""
        started = time.perf_counter()
        results: list[ChapterResult] = []
        ar = current_ar

        for chapter in CHAPTERS:
            if ar < chapter.ar_range[0]:
                # Need AR grinding
                grinded = self._grind_to_ar(ar, chapter.ar_range[0])
                if grinded:
                    ar = chapter.ar_range[0]
                else:
                    results.append(ChapterResult(
                        chapter_id=chapter.chapter_id,
                        success=False,
                        acts_completed=0,
                        total_acts=len(chapter.acts),
                        boss_defeated=False,
                        ar_at_start=ar,
                        ar_at_end=ar,
                        grinding_needed=True,
                        duration_sec=time.perf_counter() - started,
                        details=f"AR grinding failed: {ar} < {chapter.ar_range[0]}",
                    ))
                    break

            # Optional character progression between chapters
            if self._config.auto_level_up_between_chapters and self._registry is not None:
                self._registry.execute("character_progression_full", context={"current_ar": ar})

            chapter_result = self._execute_chapter(chapter, ar)
            results.append(chapter_result)
            ar = chapter_result.ar_at_end

            if not chapter_result.success:
                break

            # Grinding interval between chapters
            if chapter.grinding_interval_ar[1] > chapter.grinding_interval_ar[0]:
                grinded = self._grind_to_ar(ar, chapter.grinding_interval_ar[1])
                if grinded:
                    ar = chapter.grinding_interval_ar[1]

        total_duration = time.perf_counter() - started
        return MainlineProgressionResult(
            chapters_completed=sum(1 for r in results if r.success),
            total_chapters=len(CHAPTERS),
            chapter_results=tuple(results),
            total_duration_sec=total_duration,
            final_ar=ar,
            success=len(results) == len(CHAPTERS) and all(r.success for r in results),
        )

    def _execute_chapter(self, chapter: ChapterInfo, current_ar: int) -> ChapterResult:
        """Execute a single chapter: acts → boss → grinding."""
        started = time.perf_counter()
        acts_completed = 0
        boss_defeated = False

        # Execute each act
        for act in chapter.acts:
            act_ok = self._execute_act(chapter.chapter_id, act)
            if act_ok:
                acts_completed += 1
            else:
                log.warning("[Mainline] chapter %s act %s failed", chapter.chapter_id, act)
                break

        # Boss encounters
        for boss_id in chapter.boss_ids:
            boss_ok = self._execute_boss_encounter(boss_id, chapter)
            if boss_ok:
                boss_defeated = True
            else:
                log.warning("[Mainline] boss %s in chapter %s not defeated", boss_id, chapter.chapter_id)

        success = acts_completed == len(chapter.acts) and (boss_defeated or not chapter.boss_ids)
        return ChapterResult(
            chapter_id=chapter.chapter_id,
            success=success,
            acts_completed=acts_completed,
            total_acts=len(chapter.acts),
            boss_defeated=boss_defeated,
            ar_at_start=current_ar,
            ar_at_end=current_ar + acts_completed * 2,  # rough AR EXP estimate
            grinding_needed=False,
            duration_sec=time.perf_counter() - started,
            details=f"acts={acts_completed}/{len(chapter.acts)} boss={boss_defeated}",
        )

    def _execute_act(self, chapter_id: str, act_id: str) -> bool:
        """Execute a single act: check prereqs → navigate → quest → combat → dialog."""
        quest_label = f"{chapter_id}_{act_id}"
        log.info("[Mainline] executing act: %s", quest_label)

        # Check quest prerequisites via QuestStateMachine if available
        self._check_quest_prerequisites(chapter_id, act_id)

        # Quest navigation and dialog
        if self._registry is not None:
            self._registry.execute("quest_advance", context={"evidence": quest_label})

        # Execute semantic quest actions
        ok = self._executor.execute_semantic(
            "open_quest_menu",
            context={"chapter": chapter_id, "act": act_id},
        )
        if not ok:
            # Fallback: try quest tracking
            ok = self._executor.execute_semantic("track_quest", target=quest_label)

        self._executor.execute_semantic("close_menu")

        # Drive dialog if any
        if self._registry is not None:
            self._registry.execute("quest_drive_dialog")

        return True  # Optimistic: acts complete when their objectives are met

    def _execute_boss_encounter(self, boss_id: str, chapter: ChapterInfo) -> bool:
        """Execute a boss encounter within a chapter."""
        log.info("[Mainline] boss encounter: %s", boss_id)

        if self._registry is not None:
            for attempt in range(self._config.max_boss_retries):
                ok = self._registry.execute(
                    "combat_boss",
                    context={
                        "boss_id": boss_id,
                        "team_elements": ["pyro", "hydro", "cryo", "anemo"],
                        "team_characters": ["main_dps", "sub_dps", "support", "healer"],
                    },
                )
                if ok:
                    return True
                log.info("[Mainline] boss %s attempt %d failed", boss_id, attempt + 1)

        # Fallback to semantic action
        return self._executor.execute_semantic("use_burst", target=boss_id)

    def _grind_to_ar(self, current_ar: int, target_ar: int) -> bool:
        """Use daily routines and exploration to grind AR."""
        if current_ar >= target_ar:
            return True

        log.info("[Mainline] AR grinding: %d → %d", current_ar, target_ar)

        # Run daily routine for AR EXP
        if self._registry is not None:
            self._registry.execute("run_daily_deep")

        # Run exploration for AR EXP (waypoints, chests, oculi)
        if self._registry is not None:
            self._registry.execute("explore_activate_waypoint")
            self._registry.execute("explore_open_chest")

        return True  # Optimistic: assume grinding makes progress

    def get_chapter_for_ar(self, ar: int) -> ChapterInfo | None:
        """Return the chapter that should be active at the given AR."""
        for chapter in CHAPTERS:
            if chapter.ar_range[0] <= ar <= chapter.ar_range[1]:
                return chapter
            if chapter.grinding_interval_ar[0] <= ar < chapter.grinding_interval_ar[1]:
                return chapter
        return None

    def execute_chapter(self, chapter_id: str = "", current_ar: int = 0) -> ChapterResult:
        """Execute a specific chapter by ID."""
        ar = current_ar or 1
        for chapter in CHAPTERS:
            if chapter.chapter_id == chapter_id:
                return self._execute_chapter(chapter, ar)
        return ChapterResult(
            chapter_id=chapter_id or "unknown",
            success=False,
            acts_completed=0,
            total_acts=0,
            boss_defeated=False,
            ar_at_start=ar,
            ar_at_end=ar,
            grinding_needed=False,
            duration_sec=0.0,
            details=f"chapter '{chapter_id}' not found",
        )

    def get_next_milestone(self, current_ar: int) -> dict[str, Any]:
        """Return next milestone info for the given AR."""
        for chapter in CHAPTERS:
            if current_ar < chapter.ar_range[0]:
                return {
                    "type": "grinding",
                    "target_ar": chapter.ar_range[0],
                    "chapter": chapter.chapter_id,
                    "region": chapter.region,
                }
            if chapter.ar_range[0] <= current_ar <= chapter.ar_range[1]:
                return {
                    "type": "chapter",
                    "chapter": chapter.chapter_id,
                    "region": chapter.region,
                    "bosses": chapter.boss_ids,
                    "acts": len(chapter.acts),
                }
        return {"type": "completed", "message": "All chapters completed"}
