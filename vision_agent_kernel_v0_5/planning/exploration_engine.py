"""Exploration engine: systematic waypoint unlocking, chest/oculi collection, region progression.

Orchestrates exploration activities by planning efficient routes to unlock
waypoints, discover chests, collect oculi, and complete regional objectives.
Covers E-01 through E-22 capability requirements.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Region(Enum):
    MONDSTADT = "mondstadt"
    LIYUE = "liyue"
    INAZUMA = "inazuma"
    SUMERU = "sumeru"
    FONTAINE = "fontaine"
    NATLAN = "natlan"
    SNYEZHNAYA = "snezhnaya"  # future


class ExplorationObjective(Enum):
    WAYPOINT_UNLOCK = "waypoint_unlock"
    STATUE_ACTIVATE = "statue_activate"
    CHEST_OPEN = "chest_open"
    OCULUS_COLLECT = "oculus_collect"
    DOMAIN_UNLOCK = "domain_unlock"
    PUZZLE_SOLVE = "puzzle_solve"
    CHALLENGE_COMPLETE = "challenge_complete"


class OculiType(Enum):
    ANEMOCULUS = "anemoculus"      # Mondstadt
    GEOCULUS = "geoculus"          # Liyue
    ELECTROCULUS = "electroculus"  # Inazuma
    DENDROCULUS = "dendroculus"    # Sumeru
    HYDROCULUS = "hydroculus"      # Fontaine
    PYROCULUS = "pyroculus"        # Natlan


class ChestRarity(Enum):
    COMMON = "common"          # 2★
    EXQUISITE = "exquisite"    # 3★
    PRECIOUS = "precious"      # 4★
    LUXURIOUS = "luxurious"    # 5★
    REMARKABLE = "remarkable"  # event only


# ---------------------------------------------------------------------------
# Region data
# ---------------------------------------------------------------------------

# Region unlock order (follows Archon Quest progression)
REGION_UNLOCK_ORDER: tuple[Region, ...] = (
    Region.MONDSTADT,
    Region.LIYUE,
    Region.INAZUMA,
    Region.SUMERU,
    Region.FONTAINE,
    Region.NATLAN,
)

# Minimum AR to access each region
REGION_AR_REQUIREMENTS: dict[Region, int] = {
    Region.MONDSTADT: 1,
    Region.LIYUE: 23,
    Region.INAZUMA: 30,
    Region.SUMERU: 35,
    Region.FONTAINE: 40,
    Region.NATLAN: 40,
}

# Oculi type per region
REGION_OCULI: dict[Region, OculiType] = {
    Region.MONDSTADT: OculiType.ANEMOCULUS,
    Region.LIYUE: OculiType.GEOCULUS,
    Region.INAZUMA: OculiType.ELECTROCULUS,
    Region.SUMERU: OculiType.DENDROCULUS,
    Region.FONTAINE: OculiType.HYDROCULUS,
    Region.NATLAN: OculiType.PYROCULUS,
}

# Oculi total counts per region
OCULI_TOTALS: dict[OculiType, int] = {
    OculiType.ANEMOCULUS: 66,
    OculiType.GEOCULUS: 131,
    OculiType.ELECTROCULUS: 181,
    OculiType.DENDROCULUS: 271,
    OculiType.HYDROCULUS: 271,
    OculiType.PYROCULUS: 222,
}

# Statue offering levels (how many oculi per level)
STATUE_OFFERING_LEVELS: dict[OculiType, tuple[int, ...]] = {
    OculiType.ANEMOCULUS: (1, 2, 4, 6, 7, 8, 10, 12, 15),
    OculiType.GEOCULUS: (2, 4, 8, 12, 15, 15, 18, 20, 25),
    OculiType.ELECTROCULUS: (5, 10, 12, 15, 18, 20, 22, 25, 28, 30),
    OculiType.DENDROCULUS: (10, 12, 15, 18, 20, 22, 25, 28, 30, 35),
    OculiType.HYDROCULUS: (10, 12, 15, 18, 20, 22, 25, 28, 30, 35),
    OculiType.PYROCULUS: (10, 12, 15, 18, 20, 22, 25, 28, 30, 35),
}

# Environment hazards per region
REGION_HAZARDS: dict[Region, tuple[str, ...]] = {
    Region.MONDSTADT: (),
    Region.LIYUE: (),
    Region.INAZUMA: ("lightning_storm",),
    Region.SUMERU: ("sandstorm", "withering_zone"),
    Region.FONTAINE: ("underwater_oxygen",),
    Region.NATLAN: ("lava", "extreme_heat"),
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class ExplorationTarget:
    """A single exploration objective."""
    target_id: str
    objective: ExplorationObjective
    region: Region
    position: tuple[float, float, float]  # world coordinates
    nearest_waypoint: str = ""      # nearest teleport waypoint ID
    priority: int = 100             # lower = higher priority
    requires: tuple[str, ...] = ()  # prerequisite target IDs
    estimated_time_sec: float = 30.0


@dataclass(slots=True)
class RegionProgress:
    """Exploration progress for a region."""
    region: Region
    waypoints_total: int = 0
    waypoints_unlocked: int = 0
    chests_total: int = 0
    chests_opened: int = 0
    oculi_total: int = 0
    oculi_collected: int = 0
    exploration_pct: float = 0.0
    unlocked: bool = False

    @property
    def waypoint_pct(self) -> float:
        if self.waypoints_total <= 0:
            return 0.0
        return self.waypoints_unlocked / self.waypoints_total * 100.0

    @property
    def completion_score(self) -> float:
        """Weighted exploration score (0-100)."""
        if not self.unlocked:
            return 0.0
        wp_score = self.waypoint_pct * 0.4
        chest_score = (self.chests_opened / max(1, self.chests_total) * 100) * 0.2
        oculus_score = (self.oculi_collected / max(1, self.oculi_total) * 100) * 0.3
        pct_score = self.exploration_pct * 0.1
        return wp_score + chest_score + oculus_score + pct_score


@dataclass(slots=True)
class ExplorationPlan:
    """Planned exploration session."""
    region: Region
    targets: list[ExplorationTarget] = field(default_factory=list)
    estimated_resin: int = 0
    estimated_time_min: float = 0.0

    @property
    def waypoint_targets(self) -> list[ExplorationTarget]:
        return [t for t in self.targets if t.objective == ExplorationObjective.WAYPOINT_UNLOCK]

    @property
    def chest_targets(self) -> list[ExplorationTarget]:
        return [t for t in self.targets if t.objective == ExplorationObjective.CHEST_OPEN]

    @property
    def oculus_targets(self) -> list[ExplorationTarget]:
        return [t for t in self.targets if t.objective == ExplorationObjective.OCULUS_COLLECT]


# ---------------------------------------------------------------------------
# Exploration Engine
# ---------------------------------------------------------------------------

class ExplorationEngine:
    """Plans and prioritizes exploration activities across all regions.

    Integrates with:
    - GenshinNavigator for route planning
    - QuestMarkerFollower for navigation
    - ChestInteraction for chest opening
    - StatueInteraction for oculi offering
    - GenshinScreenClassifier for state detection
    """

    def __init__(self) -> None:
        self._progress: dict[Region, RegionProgress] = {}
        self._discovered_targets: dict[str, ExplorationTarget] = {}
        self._completed: set[str] = set()
        self._initialize_regions()

    def _initialize_regions(self) -> None:
        for region in Region:
            oculus_type = REGION_OCULI.get(region)
            total_oculi = OCULI_TOTALS.get(oculus_type, 0) if oculus_type else 0
            self._progress[region] = RegionProgress(
                region=region,
                oculi_total=total_oculi,
                unlocked=region == Region.MONDSTADT,  # Mondstadt always unlocked
            )

    def get_progress(self, region: Region) -> RegionProgress:
        return self._progress.get(region, RegionProgress(region=region))

    def update_progress(
        self,
        region: Region,
        *,
        waypoints_total: int | None = None,
        waypoints_unlocked: int | None = None,
        chests_total: int | None = None,
        chests_opened: int | None = None,
        oculi_total: int | None = None,
        oculi_collected: int | None = None,
        exploration_pct: float | None = None,
        unlocked: bool | None = None,
    ) -> None:
        progress = self._progress.get(region)
        if progress is None:
            return
        if waypoints_total is not None:
            progress.waypoints_total = waypoints_total
        if waypoints_unlocked is not None:
            progress.waypoints_unlocked = waypoints_unlocked
        if chests_total is not None:
            progress.chests_total = chests_total
        if chests_opened is not None:
            progress.chests_opened = chests_opened
        if oculi_total is not None:
            progress.oculi_total = oculi_total
        if oculi_collected is not None:
            progress.oculi_collected = oculi_collected
        if exploration_pct is not None:
            progress.exploration_pct = exploration_pct
        if unlocked is not None:
            progress.unlocked = unlocked

    def mark_completed(self, target_id: str) -> None:
        self._completed.add(target_id)
        # Update region progress counters
        target = self._discovered_targets.get(target_id)
        if target is None:
            return
        region = target.region
        progress = self._progress.get(region)
        if progress is None:
            return
        if target.objective == ExplorationObjective.WAYPOINT_UNLOCK:
            progress.waypoints_unlocked += 1
        elif target.objective == ExplorationObjective.CHEST_OPEN:
            progress.chests_opened += 1
        elif target.objective == ExplorationObjective.OCULUS_COLLECT:
            progress.oculi_collected += 1

    def add_target(self, target: ExplorationTarget) -> None:
        self._discovered_targets[target.target_id] = target

    def plan_session(
        self,
        current_region: Region,
        current_ar: int,
        time_budget_min: float = 30.0,
        prioritize: ExplorationObjective | None = None,
    ) -> ExplorationPlan:
        """Generate an exploration plan for the current session.

        Args:
            current_region: Where the player currently is.
            current_ar: Current Adventure Rank.
            time_budget_min: Available time for exploration.
            prioritize: If set, focus on this objective type first.
        """
        plan = ExplorationPlan(region=current_region)
        remaining_time = time_budget_min * 60  # convert to seconds

        # Get unlocked regions the player can access
        accessible = [
            r for r in REGION_UNLOCK_ORDER
            if current_ar >= REGION_AR_REQUIREMENTS.get(r, 999)
        ]

        # Build candidate target list
        candidates = self._get_candidates(accessible, prioritize)
        # Sort by priority, then by region proximity
        candidates.sort(key=lambda t: (t.priority, 0 if t.region == current_region else 1))

        for target in candidates:
            if remaining_time <= 0:
                break
            plan.targets.append(target)
            remaining_time -= target.estimated_time_sec

        plan.estimated_time_min = max(0.0, (time_budget_min * 60 - remaining_time) / 60.0)
        return plan

    def plan_waypoint_sweep(self, region: Region, unlocked_waypoints: set[str]) -> ExplorationPlan:
        """Plan a systematic sweep to unlock all waypoints in a region.

        Args:
            region: Target region.
            unlocked_waypoints: Set of already-unlocked waypoint IDs.
        """
        plan = ExplorationPlan(region=region)
        targets = [
            t for t in self._discovered_targets.values()
            if t.region == region
            and t.objective == ExplorationObjective.WAYPOINT_UNLOCK
            and t.target_id not in self._completed
            and t.target_id not in unlocked_waypoints
        ]
        # Sort by priority
        targets.sort(key=lambda t: t.priority)
        plan.targets = targets
        plan.estimated_time_min = sum(t.estimated_time_sec for t in targets) / 60.0
        return plan

    def next_region_to_explore(self, current_ar: int) -> Region | None:
        """Determine the next region that needs exploration."""
        for region in REGION_UNLOCK_ORDER:
            if current_ar < REGION_AR_REQUIREMENTS.get(region, 999):
                continue
            progress = self._progress.get(region)
            if progress is None or not progress.unlocked:
                continue
            if progress.completion_score < 80.0:
                return region
        return None

    def get_environment_hazards(self, region: Region) -> tuple[str, ...]:
        return REGION_HAZARDS.get(region, ())

    def oculus_offering_plan(self, region: Region) -> dict[str, Any]:
        """Calculate oculi offering status and next level."""
        oculus_type = REGION_OCULI.get(region)
        if oculus_type is None:
            return {"status": "no_oculus", "region": region.value}
        progress = self._progress.get(region)
        collected = progress.oculi_collected if progress else 0
        levels = STATUE_OFFERING_LEVELS.get(oculus_type, ())
        current_level = 0
        remaining = collected
        needed_for_next = 0
        for i, cost in enumerate(levels):
            if remaining >= cost:
                remaining -= cost
                current_level = i + 1
            else:
                needed_for_next = cost - remaining
                break
        return {
            "oculus_type": oculus_type.value,
            "current_level": current_level,
            "max_level": len(levels),
            "collected": collected,
            "total": OCULI_TOTALS.get(oculus_type, 0),
            "needed_for_next": needed_for_next,
            "remaining_after_offer": remaining,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_candidates(
        self,
        accessible_regions: list[Region],
        prioritize: ExplorationObjective | None,
    ) -> list[ExplorationTarget]:
        candidates: list[ExplorationTarget] = []
        for target in self._discovered_targets.values():
            if target.target_id in self._completed:
                continue
            if target.region not in accessible_regions:
                continue
            # Check prerequisites (all must be met)
            if target.requires and not all(pre in self._completed for pre in target.requires):
                continue
            # Boost priority for preferred objective
            if prioritize and target.objective == prioritize:
                candidates.append(ExplorationTarget(
                    target_id=target.target_id,
                    objective=target.objective,
                    region=target.region,
                    position=target.position,
                    nearest_waypoint=target.nearest_waypoint,
                    priority=max(0, target.priority - 50),
                    requires=target.requires,
                    estimated_time_sec=target.estimated_time_sec,
                ))
            else:
                candidates.append(target)
        return candidates


# ---------------------------------------------------------------------------
# S-38: 100% exploration strategy
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ExplorationCompletionPlan:
    """Plan for achieving 100% exploration in a region."""
    region: Region
    targets_remaining: int = 0
    chests_remaining: int = 0
    waypoints_remaining: int = 0
    oculi_remaining: int = 0
    estimated_hours: float = 0.0
    priority_order: list[str] = field(default_factory=list)


class HundredPercentExplorationStrategy:
    """Strategy for achieving 100% exploration in all regions (S-38).

    Identifies unexplored areas, optimizes route planning, and tracks
    progress toward complete exploration.
    """

    # Exploration completion thresholds per region
    REGION_COMPLETION_THRESHOLDS: dict[Region, float] = {
        Region.MONDSTADT: 100.0,
        Region.LIYUE: 100.0,
        Region.INAZUMA: 100.0,
        Region.SUMERU: 100.0,
        Region.FONTAINE: 100.0,
        Region.NATLAN: 100.0,
    }

    def __init__(self, exploration_engine: ExplorationEngine) -> None:
        self._engine = exploration_engine

    def generate_completion_plan(
        self,
        region: Region,
        current_progress: RegionProgress,
    ) -> ExplorationCompletionPlan:
        """Generate a plan for 100% exploration of a region.

        Args:
            region: Target region
            current_progress: Current exploration progress

        Returns:
            ExplorationCompletionPlan with targets and time estimates
        """
        plan = ExplorationCompletionPlan(region=region)

        # Calculate remaining targets
        plan.waypoints_remaining = max(0, current_progress.waypoints_total - current_progress.waypoints_unlocked)
        plan.chests_remaining = max(0, current_progress.chests_total - current_progress.chests_opened)
        plan.oculi_remaining = max(0, current_progress.oculi_total - current_progress.oculi_collected)
        plan.targets_remaining = plan.waypoints_remaining + plan.chests_remaining

        # Estimate time (waypoints faster, chests slower, oculi slowest)
        plan.estimated_hours = (
            plan.waypoints_remaining * 0.5 +  # 30 min per waypoint
            plan.chests_remaining * 1.0 +        # 60 min per chest
            plan.oculi_remaining * 1.5          # 90 min per oculus
        )

        # Generate priority order
        plan.priority_order = self._generate_priority_order(region, current_progress)

        return plan

    def _generate_priority_order(
        self,
        region: Region,
        progress: RegionProgress,
    ) -> list[str]:
        """Generate priority order for exploration targets."""
        priorities = []

        # Priority 1: Oculi (unlock statue bonuses)
        priorities.extend([f"{region.value}_oculus_{i}" for i in range(progress.oculi_collected, progress.oculi_total)])

        # Priority 2: Waypoints (enable fast travel)
        priorities.extend([f"{region.value}_waypoint_{i}" for i in range(progress.waypoints_unlocked, progress.waypoints_total)])

        # Priority 3: Chests (AR EXP and primogems)
        priorities.extend([f"{region.value}_chest_{i}" for i in range(progress.chests_opened, progress.chests_total)])

        return priorities

    def is_exploration_complete(self, region: Region, progress: RegionProgress) -> bool:
        """Check if exploration is 100% complete."""
        threshold = self.REGION_COMPLETION_THRESHOLDS.get(region, 100.0)
        return progress.exploration_pct >= threshold

    def get_remaining_exploration(
        self,
        regions: list[Region],
    ) -> dict[Region, float]:
        """Get remaining exploration percentage for all regions.

        Returns dict of region -> remaining percentage.
        """
        remaining = {}
        for region in regions:
            progress = self._engine.get_progress(region)
            if progress.exploration_pct < 100.0:
                remaining[region] = 100.0 - progress.exploration_pct
            else:
                remaining[region] = 0.0
        return remaining
