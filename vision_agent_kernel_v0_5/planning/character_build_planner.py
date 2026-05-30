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
# Crown allocation strategy (R-39)
# ---------------------------------------------------------------------------

class CrownPriority(str, Enum):
    """Priority for crown usage."""
    CORE = "core"           # Core characters (national team, etc.)
    SUB_DPS = "sub_dps"     # Sub DPS characters
    SUPPORT = "support"     # Support characters
    FLEX = "flex"           # Flex/situational characters


@dataclass(slots=True)
class CrownAllocation:
    """Crown allocation decision."""
    character_id: str
    talent: str
    current_level: int
    target_level: int
    priority: CrownPriority
    crowns_needed: int = 1


@dataclass(slots=True)
class CrownBudget:
    """Budget for crown allocation across multiple characters."""
    crowns_owned: int = 0
    crowns_reserved: int = 0

    @property
    def crowns_available(self) -> int:
        return max(0, self.crowns_owned - self.crowns_reserved)


class CrownAllocator:
    """Allocates crown resources based on character priority (R-39).

    Distinguishes between core characters (burst to 9/10) and
    utility characters (skill to 6 or skip).
    """

    # Characters and their crown priorities
    CORE_CHARACTERS: frozenset[str] = frozenset({
        "xiangling", "xingqiu", "bennett", "kaeya",
    })
    SUB_DPS_CHARACTERS: frozenset[str] = frozenset({
        "fischl", "barbara", "noelle", "collei",
    })
    SUPPORT_CHARACTERS: frozenset[str] = frozenset({
        "lisa", "amber",
    })

    # Crown thresholds
    CORE_BURST_TARGET = 9      # Core burst to 9 (needs crown)
    CORE_OTHER_TARGET = 6       # Core other talents to 6 (no crown)
    SUB_DPS_TARGET = 6          # Sub DPS talents to 6
    SUPPORT_SKIP = 4            # Support talents stop at 4

    def get_priority(self, character_id: str) -> CrownPriority:
        """Determine crown priority for a character."""
        if character_id in self.CORE_CHARACTERS:
            return CrownPriority.CORE
        if character_id in self.SUB_DPS_CHARACTERS:
            return CrownPriority.SUB_DPS
        if character_id in self.SUPPORT_CHARACTERS:
            return CrownPriority.SUPPORT
        return CrownPriority.FLEX

    def plan_allocation(
        self,
        character_states: list[Any],
        crowns_owned: int,
    ) -> list[CrownAllocation]:
        """Plan crown allocation across multiple characters."""
        allocations: list[CrownAllocation] = []
        available = crowns_owned

        # Sort by priority
        sorted_chars = sorted(
            character_states,
            key=lambda c: (
                list(CrownPriority).index(self.get_priority(c.character_id)),
                -max(c.talent_levels.values()) if c.talent_levels else 0,
            ),
        )

        for state in sorted_chars:
            if available <= 0:
                break

            priority = self.get_priority(state.character_id)
            crown_talent, crown_needed = self._calculate_needs(state, priority)

            if crown_needed > 0 and available >= crown_needed:
                allocations.append(CrownAllocation(
                    character_id=state.character_id,
                    talent=crown_talent,
                    current_level=state.talent_levels.get(crown_talent, 1),
                    target_level=state.talent_levels.get(crown_talent, 1) + crown_needed,
                    priority=priority,
                    crowns_needed=crown_needed,
                ))
                available -= crown_needed

        return allocations

    def _calculate_needs(
        self,
        state: Any,
        priority: CrownPriority,
    ) -> tuple[str, int]:
        """Calculate crown needs for a character."""
        if priority == CrownPriority.CORE:
            burst = state.talent_levels.get("burst", 1)
            if burst < self.CORE_BURST_TARGET:
                return ("burst", self.CORE_BURST_TARGET - burst)
            return ("", 0)
        if priority == CrownPriority.SUB_DPS:
            # Check which talent is lowest
            lowest_talent = min(state.talent_levels.items(), key=lambda x: x[1])
            if lowest_talent[1] < self.SUB_DPS_TARGET:
                return (lowest_talent[0], self.SUB_DPS_TARGET - lowest_talent[1])
            return ("", 0)
        return ("", 0)

    def reserve_crowns(self, crowns_needed: int, allocations: list[CrownAllocation]) -> int:
        """Calculate crowns to reserve for planned allocations."""
        return sum(a.crowns_needed for a in allocations if a.crowns_needed > 0)


# ---------------------------------------------------------------------------
# R-40~R-41: Material planning with uncertainty and scarcity detection
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class WeeklyBossUncertainty:
    """Tracks uncertainty in weekly boss material acquisition."""
    boss_name: str
    material_id: str
    expected_drop_rate: float = 0.5  # ~50% expected drop rate
    runs_estimated: int = 1
    risk_level: str = "normal"  # "low", "normal", "high"


@dataclass(slots=True)
class ScarceMaterial:
    """Identifies scarce/hard-to-acquire materials."""
    material_id: str
    name: str
    acquisition_difficulty: str = "normal"  # "easy", "normal", "hard", "very_hard"
    acquisition_locations: list[str] = field(default_factory=list)
    time_to_acquire_hours: float = 0.0
    is_time_gated: bool = False


# Local specialty scarcity data
LOCAL_SPECIALTY_SCARCIty: dict[str, ScarceMaterial] = {
    "wind_aster": ScarceMaterial(
        material_id="wind_aster",
        name="Wind Aster",
        acquisition_difficulty="easy",
        acquisition_locations=["Mondstadt", "Starfell Valley"],
        time_to_acquire_hours=1.0,
    ),
    "philanemo_mushroom": ScarceMaterial(
        material_id="philanemo_mushroom",
        name="Philanemo Mushroom",
        acquisition_difficulty="hard",
        acquisition_locations=["Starsnatch Cliff", "Windrise"],
        time_to_acquire_hours=3.0,
    ),
    "crystal_marrow": ScarceMaterial(
        material_id="crystal_marrow",
        name="Crystal Marrow",
        acquisition_difficulty="very_hard",
        acquisition_locations=["Inazuma (only from enemies, time-gated)"],
        time_to_acquire_hours=8.0,
        is_time_gated=True,
    ),
}


class MaterialUncertaintyAnalyzer:
    """Analyzes uncertainty in material acquisition (R-40)."""

    def __init__(self) -> None:
        self._weekly_boss_runs: dict[str, int] = {}

    def estimate_weekly_boss_runs(
        self,
        material_id: str,
        quantity_needed: int,
    ) -> int:
        """Estimate number of weekly boss runs needed for material.

        Uses expected drop rate to estimate runs.
        """
        expected_rate = 0.5  # ~50% drop rate
        base_runs = int(quantity_needed / expected_rate)

        # Count current runs
        current_runs = self._weekly_boss_runs.get(material_id, 0)

        # Buffer for variance
        buffer = max(1, int(base_runs * 0.3))
        return base_runs + buffer

    def get_uncertainty(
        self,
        material_id: str,
        quantity_needed: int,
    ) -> WeeklyBossUncertainty | None:
        """Get uncertainty info for a weekly boss material."""
        weekly_materials = {
            "diluc_talent", "ningguang_talent", "mona_talent",
            "tartaglia_talent", "keqing_talent",
        }

        if material_id not in weekly_materials:
            return None

        runs = self.estimate_weekly_boss_runs(material_id, quantity_needed)

        return WeeklyBossUncertainty(
            boss_name=material_id,
            material_id=material_id,
            expected_drop_rate=0.5,
            runs_estimated=runs,
            risk_level="high" if runs > 4 else "normal",
        )

    def get_scarce_materials(
        self,
        material_ids: list[str],
    ) -> list[ScarceMaterial]:
        """Identify scarce materials from a list."""
        scarce: list[ScarceMaterial] = []
        for mat_id in material_ids:
            if mat_id in LOCAL_SPECIALTY_SCARCIty:
                scarcity = LOCAL_SPECIALTY_SCARCIty[mat_id]
                if scarcity.acquisition_difficulty in ("hard", "very_hard"):
                    scarce.append(scarcity)
        return scarce


class MaterialScarcityDetector:
    """Detects scarcity in material acquisition paths (R-41)."""

    SCARCE_MATERIALS: frozenset[str] = frozenset({
        "crystal_marrow",  # Inazuma - very hard
        "sea_ganoderma",    # Inazuma water areas
        "sand_grease_pupae",  # Sumeru desert
        "lightning_essential_oil",  # Event limited
        "floral_essence",  # Event limited
    })

    def is_scarce(self, material_id: str) -> bool:
        """Check if a material is considered scarce."""
        return material_id in self.SCARCE_MATERIALS

    def get_scarcity_alert(
        self,
        material_id: str,
        current_count: int,
        needed_count: int,
    ) -> dict[str, Any] | None:
        """Generate scarcity alert if material is rare."""
        if not self.is_scarce(material_id):
            return None

        deficit = max(0, needed_count - current_count)
        if deficit == 0:
            return None

        scarcity = LOCAL_SPECIALTY_SCARCIty.get(material_id)
        difficulty = scarcity.acquisition_difficulty if scarcity else "hard"

        return {
            "material_id": material_id,
            "acquisition_difficulty": difficulty,
            "deficit": deficit,
            "estimated_time_hours": (scarcity.time_to_acquire_hours if scarcity else 5.0) * deficit,
            "recommendation": f"Start farming {material_id} early - it's scarce",
            "is_time_gated": scarcity.is_time_gated if scarcity else False,
        }


# ---------------------------------------------------------------------------
# R-38: Refinement priority (imported from knowledge module)
# ---------------------------------------------------------------------------

from knowledge.weapon_refinement_priority import (
    RefinementPriorityCalculator,
    MultiCharacterRefinementPlan,
)


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
