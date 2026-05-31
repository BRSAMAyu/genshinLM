"""MapNavigationRuntime: NavigationPlan producer per AUTONOMY_RUNTIME_CONTRACT.md §1.7.

Produces NavigationPlan (plan_id, legs[], arrived, arrived_leg_index) by:
1. Resolving current region from NavigationSignal
2. Finding optimal waypoint path via WaypointGraph
3. Building NavigationLeg sequence (teleport/walk/swim)
4. Writing result to StateBus.navigation_plan
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.state_bus import StateBus
    from knowledge.world_graph import WaypointGraph
    from navigation.teleport_sequence import TeleportSequence
    from navigation.quest_marker_follower import QuestMarkerFollower


@dataclass(frozen=True, slots=True)
class AnchorScreenLocation:
    """Per AUTONOMY_RUNTIME_CONTRACT.md §1.7."""

    anchor_id: str
    screen_xy: tuple[float, float]
    confidence: float
    locked: bool = False
    cooldown_until: float = 0.0


@dataclass(frozen=True, slots=True)
class NavigationLeg:
    """Per AUTONOMY_RUNTIME_CONTRACT.md §1.7."""

    method: str  # "teleport", "walk", "swim"
    waypoint_id: str = ""
    target_xy: tuple[float, float] = (0.0, 0.0)
    expected_duration_sec: float = 0.0


@dataclass(frozen=True, slots=True)
class NavigationPlan:
    """Per AUTONOMY_RUNTIME_CONTRACT.md §1.7."""

    plan_id: str
    objective: str
    legs: tuple[NavigationLeg, ...] = ()
    fallback_allowed: bool = True
    timeout_sec: float = 120.0
    failed_legs: tuple[str, ...] = ()
    arrived: bool = False
    arrived_leg_index: int = -1


class MapNavigationRuntime:
    """Produces NavigationPlan for navigation objectives using WaypointGraph."""

    __slots__ = ("_graph", "_state_bus", "_teleport", "_marker_follower")

    def __init__(
        self,
        waypoint_graph: WaypointGraph,
        state_bus: StateBus | None = None,
        teleport_sequence: TeleportSequence | None = None,
        quest_marker_follower: QuestMarkerFollower | None = None,
    ) -> None:
        self._graph = waypoint_graph
        self._state_bus = state_bus
        self._teleport = teleport_sequence
        self._marker_follower = quest_marker_follower

    def select_destination(
        self,
        objective: str,
        current_region: str = "",
        current_waypoint: str = "",
    ) -> NavigationPlan:
        """Resolve objective to NavigationPlan using WaypointGraph.

        Parameters
        ----------
        objective : str
            Semantic target, e.g. "mon:windrise", "npc:amber", "chest:serpent_head"
        current_region : str
            Player's current region
        current_waypoint : str
            Player's current waypoint ID

        Returns
        -------
        NavigationPlan
            Populated plan with NavigationLeg sequence
        """
        plan_id = f"nav_{uuid.uuid4().hex[:8]}"

        # Resolve objective → waypoint_id
        target_wp = self._resolve_objective(objective)
        if not target_wp:
            return NavigationPlan(
                plan_id=plan_id,
                objective=objective,
                legs=(),
                fallback_allowed=False,
                arrived=False,
            )

        # Find shortest path
        if current_waypoint and current_waypoint in self._graph._adj:
            path_result = self._graph.shortest_path(current_waypoint, target_wp)
        else:
            # Fall back to nearest waypoint in target region
            nearest = self._graph.nearest_waypoint(
                _source_node_from_region(current_region)
            )
            if nearest:
                path_result = self._graph.shortest_path(nearest, target_wp)
            else:
                path_result = _PathResult(False, float("inf"), [])

        if not path_result.ok:
            return NavigationPlan(
                plan_id=plan_id,
                objective=objective,
                legs=(),
                fallback_allowed=True,
                arrived=False,
            )

        # Build NavigationLeg sequence
        legs = self._build_legs(path_result.path, target_wp)

        plan = NavigationPlan(
            plan_id=plan_id,
            objective=objective,
            legs=legs,
            fallback_allowed=True,
            arrived=False,
        )

        # Write to StateBus if available
        if self._state_bus is not None:
            self._state_bus.navigation_plan.put(plan)

        return plan

    def mark_arrived(self, plan: NavigationPlan, leg_index: int) -> NavigationPlan:
        """Mark a plan as arrived at a given leg index."""
        updated = NavigationPlan(
            plan_id=plan.plan_id,
            objective=plan.objective,
            legs=plan.legs,
            fallback_allowed=plan.fallback_allowed,
            timeout_sec=plan.timeout_sec,
            failed_legs=plan.failed_legs,
            arrived=True,
            arrived_leg_index=leg_index,
        )
        if self._state_bus is not None:
            self._state_bus.navigation_plan.put(updated)
        return updated

    def mark_failed(self, plan: NavigationPlan, failed_leg_id: str) -> NavigationPlan:
        """Record a failed leg and continue."""
        updated = NavigationPlan(
            plan_id=plan.plan_id,
            objective=plan.objective,
            legs=plan.legs,
            fallback_allowed=False,
            timeout_sec=plan.timeout_sec,
            failed_legs=(*plan.failed_legs, failed_leg_id),
            arrived=False,
        )
        if self._state_bus is not None:
            self._state_bus.navigation_plan.put(updated)
        return updated

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_objective(self, objective: str) -> str | None:
        """Parse semantic objective → waypoint_id."""
        # Format: "mon:windrise", "npc:amber", "waypoint:starsnape"
        if ":" in objective:
            prefix, name = objective.split(":", 1)
            if prefix in ("mon", "npc", "waypoint", "chest", "domain"):
                return name
        # Bare waypoint name
        if objective in self._graph._waypoints:
            return objective
        return None

    def _build_legs(
        self,
        path: list[str],
        target_wp: str,
    ) -> tuple[NavigationLeg, ...]:
        """Convert waypoint path to NavigationLeg sequence."""
        if not path:
            return ()

        legs: list[NavigationLeg] = []
        for i, waypoint_id in enumerate(path):
            wp = self._graph._waypoints.get(waypoint_id)
            if wp is None:
                continue

            # Determine method: teleport if not the last leg
            method = "teleport" if i < len(path) - 1 else "walk"

            leg = NavigationLeg(
                method=method,
                waypoint_id=waypoint_id,
                target_xy=wp.position,
                expected_duration_sec=_estimate_duration(method, wp),
            )
            legs.append(leg)

        return tuple(legs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _SourceNode:
    region: str = ""
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)


def _source_node_from_region(region: str) -> _SourceNode:
    return _SourceNode(region=region)


@dataclass(frozen=True, slots=True)
class _PathResult:
    ok: bool
    cost: float
    path: list[str]


def _estimate_duration(method: str, wp: Any | None) -> float:
    """Estimate travel time in seconds."""
    if method == "teleport":
        return 5.0
    if wp is not None:
        x, y, z = wp.position
        distance = (x**2 + y**2) ** 0.5
        return max(1.0, distance * 0.1)
    return 10.0