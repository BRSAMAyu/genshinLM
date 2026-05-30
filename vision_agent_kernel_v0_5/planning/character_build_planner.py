"""Character build planner: material gap analysis, build priority, and acquisition planning.

Orchestrates character progression by comparing current state against target builds,
calculating material gaps, and generating actionable acquisition plans.
Covers R-03, R-06, M-09, M-10 capability requirements.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from knowledge.genshin_character_progression import (
    EXP_BOOKS,
    GEM_NAMES,
    BOSS_MATERIALS,
    MORA_PER_EXP,
    get_ascension_cost,
    get_talent_cost,
    total_ascension_mats_to_level,
    exp_to_level,
    RESIN_COSTS,
    SYNTHESIS_RATIO,
    BUILD_INVESTMENT_PRIORITY,
    CHARACTER_TALENT_BOOKS,
    books_available_today,
)
from knowledge.genshin_f2p_builds import F2P_BUILDS, BUILD_PRIORITY

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class MaterialCategory(Enum):
    EXP_BOOK = "exp_book"
    MORA = "mora"
    GEM = "gem"
    LOCAL_SPECIALTY = "local_specialty"
    COMMON_DROP = "common_drop"
    BOSS_DROP = "boss_drop"
    TALENT_BOOK = "talent_book"
    WEEKLY_BOSS_DROP = "weekly_boss_drop"
    WEAPON_MATERIAL = "weapon_material"
    ARTIFACT = "artifact"
    CROWN = "crown"


@dataclass(slots=True, frozen=True)
class MaterialNeed:
    """A single material requirement."""
    item_id: str
    name: str
    category: MaterialCategory
    quantity_needed: int
    quantity_owned: int = 0

    @property
    def gap(self) -> int:
        return max(0, self.quantity_needed - self.quantity_owned)

    @property
    def satisfied(self) -> bool:
        return self.quantity_owned >= self.quantity_needed


@dataclass(slots=True)
class BuildPlan:
    """Complete build plan for a single character."""
    character_id: str
    target_level: int
    target_weapon_level: int
    talent_targets: dict[str, int]  # talent_name -> target_level
    material_needs: list[MaterialNeed] = field(default_factory=list)
    resin_estimate: int = 0
    mora_estimate: int = 0
    time_estimate_hours: float = 0.0

    @property
    def total_gap(self) -> int:
        return sum(m.gap for m in self.material_needs)

    @property
    def unsatisfied_needs(self) -> list[MaterialNeed]:
        return [m for m in self.material_needs if not m.satisfied]


@dataclass(slots=True)
class AcquisitionTask:
    """A single resin-spending task to acquire materials."""
    task_type: str          # "domain", "boss", "weekly_boss", "crafting"
    target: str             # domain/boss/material name
    resin_cost: int
    materials_gained: dict[str, int]  # material_id -> expected count
    priority: int           # lower = higher priority
    reason: str = ""
    day_restriction: int | None = None  # 0-6 for day-of-week, None = any day


@dataclass(slots=True)
class AcquisitionPlan:
    """Prioritized list of acquisition tasks."""
    character_id: str
    tasks: list[AcquisitionTask] = field(default_factory=list)
    total_resin: int = 0
    total_mora_cost: int = 0

    def tasks_by_priority(self) -> list[AcquisitionTask]:
        return sorted(self.tasks, key=lambda t: t.priority)


# ---------------------------------------------------------------------------
# Character state snapshot
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CharacterState:
    """Current state of a character."""
    character_id: str
    level: int = 1
    talent_levels: dict[str, int] = field(default_factory=lambda: {
        "normal_attack": 1, "skill": 1, "burst": 1,
    })
    weapon_id: str = ""
    weapon_level: int = 1
    artifact_set: str = ""
    # Inventory snapshot
    inventory: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Build Planner
# ---------------------------------------------------------------------------

class CharacterBuildPlanner:
    """Plans character builds by analyzing material gaps and generating acquisition tasks."""

    def __init__(self) -> None:
        self._build_data = F2P_BUILDS
        self._inventory: dict[str, int] = {}

    def plan_character(
        self,
        state: CharacterState,
        target_level: int | None = None,
        target_weapon_level: int | None = None,
        talent_targets: dict[str, int] | None = None,
    ) -> BuildPlan:
        """Generate a complete build plan for a character.

        If target values are None, uses defaults from F2P_BUILDS or sensible targets.
        """
        build = self._build_data.get(state.character_id)
        # Sync inventory from state
        if state.inventory:
            self._inventory = dict(state.inventory)
        if target_level is None:
            target_level = min(state.level + 20, 80)
        if target_weapon_level is None:
            target_weapon_level = min(state.weapon_level + 20, 80)
        if talent_targets is None:
            talent_targets = {}
            if build:
                # Use talent priority to set targets
                for i, talent in enumerate(build.talent_priority):
                    target = 8 if i == 0 else 6 if i == 1 else 4
                    talent_targets[talent] = target
            else:
                talent_targets = {"burst": 6, "skill": 6, "normal_attack": 4}

        plan = BuildPlan(
            character_id=state.character_id,
            target_level=target_level,
            target_weapon_level=target_weapon_level,
            talent_targets=talent_targets,
        )

        # Calculate EXP + Mora needs
        self._add_exp_needs(plan, state, target_level)

        # Calculate ascension needs
        self._add_ascension_needs(plan, state, target_level, build)

        # Calculate talent needs
        self._add_talent_needs(plan, state, talent_targets, build)

        return plan

    def generate_acquisition_plan(
        self,
        plan: BuildPlan,
        current_resin: int = 0,
        day_of_week: int | None = None,
    ) -> AcquisitionPlan:
        """Convert a BuildPlan into prioritized AcquisitionTasks."""
        acq = AcquisitionPlan(character_id=plan.character_id)

        unsatisfied = plan.unsatisfied_needs
        if not unsatisfied:
            return acq

        # Group needs by acquisition source
        for need in unsatisfied:
            task = self._need_to_task(need, day_of_week)
            if task is not None:
                acq.tasks.append(task)

        # Sort by priority and deduplicate
        acq.tasks = self._deduplicate_tasks(acq.tasks_by_priority())
        acq.total_resin = sum(t.resin_cost for t in acq.tasks)
        acq.total_mora_cost = plan.mora_estimate

        return acq

    def prioritize_characters(
        self,
        characters: list[CharacterState],
    ) -> list[tuple[str, int]]:
        """Return characters sorted by build priority with ROI scores.

        Returns list of (character_id, priority_score) where lower score = higher priority.
        """
        scored: list[tuple[str, int]] = []
        for i, char_id in enumerate(BUILD_PRIORITY):
            state = next((c for c in characters if c.character_id == char_id), None)
            if state is None:
                continue
            # Characters earlier in BUILD_PRIORITY get lower (higher priority) scores
            # Undergeared characters get bonus priority
            gear_score = 0
            if state.weapon_level < state.level:
                gear_score += 20
            if max(state.talent_levels.values()) < 4:
                gear_score += 10
            scored.append((char_id, i * 10 - gear_score))

        scored.sort(key=lambda x: x[1])
        return scored

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_exp_needs(self, plan: BuildPlan, state: CharacterState, target: int) -> None:
        if state.level >= target:
            return
        total_exp = exp_to_level(target) - exp_to_level(state.level)
        if total_exp <= 0:
            return

        # Calculate book counts (prefer Hero's Wit for efficiency)
        heros_wit_count = total_exp // 20000
        remaining = total_exp % 20000
        adv_count = remaining // 5000
        final_remaining = remaining % 5000
        wanderer_count = (final_remaining + 999) // 1000  # round up

        mora_cost = (
            heros_wit_count * MORA_PER_EXP["heros_wit"]
            + adv_count * MORA_PER_EXP["adventurers_experience"]
            + wanderer_count * MORA_PER_EXP["wanderers_advice"]
        )

        plan.mora_estimate += mora_cost
        if heros_wit_count > 0:
            plan.material_needs.append(MaterialNeed(
                "heros_wit", "Hero's Wit", MaterialCategory.EXP_BOOK,
                heros_wit_count, self._get_owned(plan, "heros_wit"),
            ))
        if adv_count > 0:
            plan.material_needs.append(MaterialNeed(
                "adventurers_experience", "Adventurer's Experience", MaterialCategory.EXP_BOOK,
                adv_count, self._get_owned(plan, "adventurers_experience"),
            ))
        if wanderer_count > 0:
            plan.material_needs.append(MaterialNeed(
                "wanderers_advice", "Wanderer's Advice", MaterialCategory.EXP_BOOK,
                wanderer_count, self._get_owned(plan, "wanderers_advice"),
            ))
        plan.material_needs.append(MaterialNeed(
            "mora", "Mora", MaterialCategory.MORA,
            mora_cost, self._get_owned(plan, "mora"),
        ))

    def _add_ascension_needs(
        self, plan: BuildPlan, state: CharacterState, target: int,
        build: Any | None,
    ) -> None:
        element = build.element if build else "Pyro"

        # Calculate total materials from current level's next milestone to target
        mats = total_ascension_mats_to_level(target, element)
        plan.mora_estimate += mats.get("mora", 0)

        # Count boss runs needed for boss materials
        boss_mat_name = BOSS_MATERIALS.get(element, "Unknown")
        boss_count = mats.get(boss_mat_name, 0)
        if boss_count > 0:
            plan.resin_estimate += RESIN_COSTS["normal_boss"] * ((boss_count + 1) // 2)

        # Add real material needs from the computed totals
        gems = GEM_NAMES.get(element, GEM_NAMES["Pyro"])
        for mat_name, count in mats.items():
            if mat_name == "mora" or count <= 0:
                continue
            if mat_name in gems:
                cat = MaterialCategory.GEM
            elif mat_name == boss_mat_name:
                cat = MaterialCategory.BOSS_DROP
            elif "local_specialty" in mat_name:
                cat = MaterialCategory.LOCAL_SPECIALTY
            elif "common_drop" in mat_name:
                cat = MaterialCategory.COMMON_DROP
            else:
                cat = MaterialCategory.GEM
            plan.material_needs.append(MaterialNeed(
                mat_name.lower().replace(" ", "_"), mat_name, cat,
                count, self._get_owned(plan, mat_name.lower().replace(" ", "_")),
            ))

    def _add_talent_needs(
        self, plan: BuildPlan, state: CharacterState,
        targets: dict[str, int], build: Any | None,
    ) -> None:
        # Determine character's talent book type
        char_id = state.character_id
        book_type = CHARACTER_TALENT_BOOKS.get(char_id, "Freedom")

        # Aggregate talent costs across all talent upgrades
        total_books: dict[str, int] = {}  # tier_name -> count
        total_common: dict[str, int] = {}  # tier_name -> count
        total_boss_mats = 0
        total_mora = 0
        total_crowns = 0

        for talent_name, target_lv in targets.items():
            current_lv = state.talent_levels.get(talent_name, 1)
            if current_lv >= target_lv:
                continue
            for lv in range(current_lv, target_lv):
                cost = get_talent_cost(lv)
                if cost is None:
                    continue
                total_mora += cost.mora
                plan.resin_estimate += RESIN_COSTS["talent_domain"]
                if cost.boss_material > 0:
                    total_boss_mats += cost.boss_material
                    plan.resin_estimate += RESIN_COSTS["weekly_boss_discount"]
                if cost.crown:
                    total_crowns += 1
                if cost.book_teachings > 0:
                    total_books[f"Teachings of {book_type}"] = total_books.get(
                        f"Teachings of {book_type}", 0) + cost.book_teachings
                if cost.book_guide > 0:
                    total_books[f"Guide to {book_type}"] = total_books.get(
                        f"Guide to {book_type}", 0) + cost.book_guide
                if cost.book_philosophies > 0:
                    total_books[f"Philosophies of {book_type}"] = total_books.get(
                        f"Philosophies of {book_type}", 0) + cost.book_philosophies
                if cost.common_t1 > 0:
                    total_common["common_drop_t1"] = total_common.get("common_drop_t1", 0) + cost.common_t1
                if cost.common_t2 > 0:
                    total_common["common_drop_t2"] = total_common.get("common_drop_t2", 0) + cost.common_t2
                if cost.common_t3 > 0:
                    total_common["common_drop_t3"] = total_common.get("common_drop_t3", 0) + cost.common_t3

        plan.mora_estimate += total_mora

        # Add material needs
        for book_name, count in total_books.items():
            plan.material_needs.append(MaterialNeed(
                book_name.lower().replace(" ", "_"), book_name, MaterialCategory.TALENT_BOOK,
                count, self._get_owned(plan, book_name.lower().replace(" ", "_")),
            ))
        for drop_name, count in total_common.items():
            plan.material_needs.append(MaterialNeed(
                drop_name, drop_name, MaterialCategory.COMMON_DROP,
                count, self._get_owned(plan, drop_name),
            ))
        if total_boss_mats > 0:
            plan.material_needs.append(MaterialNeed(
                "weekly_boss_drop", "Weekly Boss Material", MaterialCategory.WEEKLY_BOSS_DROP,
                total_boss_mats, self._get_owned(plan, "weekly_boss_drop"),
            ))
        if total_crowns > 0:
            plan.material_needs.append(MaterialNeed(
                "crown_of_insight", "Crown of Insight", MaterialCategory.CROWN,
                total_crowns, self._get_owned(plan, "crown_of_insight"),
            ))

    def _get_owned(self, plan: BuildPlan, item_id: str) -> int:
        return self._inventory.get(item_id, 0)

    def _need_to_task(self, need: MaterialNeed, day_of_week: int | None) -> AcquisitionTask | None:
        cat = need.category
        if cat == MaterialCategory.EXP_BOOK:
            return AcquisitionTask(
                "domain", "Ley Line Blossom of Wealth", 20,
                {need.item_id: need.gap}, priority=30,
                reason="Farm EXP books via ley lines",
            )
        if cat == MaterialCategory.MORA:
            return None  # Mora is acquired passively, not a farming task
        if cat == MaterialCategory.GEM or cat == MaterialCategory.BOSS_DROP:
            return AcquisitionTask(
                "boss", "World Boss", 40,
                {need.item_id: need.gap}, priority=20,
                reason="Farm ascension materials from world boss",
            )
        if cat == MaterialCategory.LOCAL_SPECIALTY:
            return AcquisitionTask(
                "collect", "Local Specialty", 0,
                {need.item_id: need.gap}, priority=25,
                reason="Farm local specialty materials",
            )
        if cat == MaterialCategory.COMMON_DROP:
            return AcquisitionTask(
                "domain", "Enemy Domain (common)", 20,
                {need.item_id: need.gap}, priority=35,
                reason="Farm common enemy drops",
            )
        if cat == MaterialCategory.TALENT_BOOK:
            # need.name is like "Guide to Gold" or "Philosophies of Diligence"
            # Extract the book type from the name
            book_type = need.name.split(" of ")[-1] if " of " in need.name else need.name
            day_restriction = None
            if day_of_week is not None:
                available = books_available_today(day_of_week)
                if book_type not in available and day_of_week != 6:
                    day_restriction = day_of_week
            return AcquisitionTask(
                "domain", f"Talent Domain ({book_type})", 20,
                {need.item_id: need.gap}, priority=10,
                reason=f"Farm {book_type} talent books",
                day_restriction=day_restriction,
            )
        if cat == MaterialCategory.WEEKLY_BOSS_DROP:
            return AcquisitionTask(
                "weekly_boss", "Weekly Boss", 30,
                {need.item_id: need.gap}, priority=5,
                reason="Farm weekly boss materials",
            )
        if cat == MaterialCategory.CROWN:
            return None  # Crowns are rare, no farming strategy
        return None

    def _deduplicate_tasks(self, tasks: list[AcquisitionTask]) -> list[AcquisitionTask]:
        seen: dict[str, AcquisitionTask] = {}
        for task in tasks:
            key = f"{task.task_type}:{task.target}"
            if key in seen:
                existing = seen[key]
                # Merge materials without double-counting resin (one domain run yields both)
                for mat_id, count in task.materials_gained.items():
                    existing.materials_gained[mat_id] = existing.materials_gained.get(mat_id, 0) + count
                # Keep the higher resin cost (accounts for more runs needed)
                existing.resin_cost = max(existing.resin_cost, task.resin_cost)
            else:
                seen[key] = AcquisitionTask(
                    task.task_type, task.target, task.resin_cost,
                    dict(task.materials_gained), task.priority, task.reason, task.day_restriction,
                )
        return list(seen.values())
