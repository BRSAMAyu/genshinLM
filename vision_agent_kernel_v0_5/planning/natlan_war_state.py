"""Q-39: Natlan war state handler.

Handles Natlan's tribal war state system where different tribes
may be in conflict, affecting available quests, NPCs, and areas.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class Tribe(str, Enum):
    MASTERLESS = "masterless"      # Unaffiliated
    FALLS = "falls"               # Children of Echoes
    MOLLENTS = "mollents"         # Flower-Feather Clan
    SCIONS = "scions"             # Scions of the Canopy
    COLD = "cold"                 # People of the Springs
    NATLAN_CITY = "natlan_city"   # Natlan City


class WarState(str, Enum):
    PEACE = "peace"               # No active conflict
    TENSION = "tension"           # Building tension, minor incidents
    ACTIVE_CONFLICT = "active_conflict"  # Active tribal war
    CEASEFIRE = "ceasefire"       # Temporary halt
    AFTERMATH = "aftermath"       # Post-conflict recovery


@dataclass(frozen=True, slots=True)
class TribalStanding:
    """Standing with a specific tribe."""
    tribe: Tribe
    relationship_level: int  # -100 to 100
    war_participation: bool  # Is tribe involved in conflict
    accessible: bool         # Can access tribe's territory


@dataclass(frozen=True, slots=True)
class WarStateStatus:
    """Current war state status."""
    current_state: WarState
    active_tribes: list[Tribe]
    affected_areas: list[str]
    quest_restrictions: list[str]
    conflict_intensity: float  # 0.0-1.0


class NatlanWarStateHandler:
    """Handle Natlan tribal war state and its effects."""

    _REF_W = 1920
    _REF_H = 1080

    # War/conflict indicators
    _CONFLICT_RED_LOW = np.array([0, 100, 100], dtype=np.uint8)
    _CONFLICT_RED_HIGH = np.array([10, 255, 255], dtype=np.uint8)

    # Peace indicators
    _PEACE_GREEN_LOW = np.array([50, 100, 100], dtype=np.uint8)
    _PEACE_GREEN_HIGH = np.array([70, 255, 255], dtype=np.uint8)

    # Warning indicators
    _WARNING_YELLOW_LOW = np.array([20, 100, 150], dtype=np.uint8)
    _WARNING_YELLOW_HIGH = np.array([30, 255, 255], dtype=np.uint8)

    def __init__(
        self,
        on_war_state_change: Any = None,
        on_area_restricted: Any = None,
        on_area_opened: Any = None,
    ) -> None:
        self._on_war_state_change = on_war_state_change
        self._on_area_restricted = on_area_restricted
        self._on_area_opened = on_area_opened

        self._current_state: WarState = WarState.PEACE
        self._tribal_standings: dict[Tribe, TribalStanding] = {}
        self._affected_areas: dict[str, bool] = {}  # area -> restricted
        self._state_change_time: float = 0.0

        # Initialize tribal standings
        for tribe in Tribe:
            self._tribal_standings[tribe] = TribalStanding(
                tribe=tribe,
                relationship_level=0,
                war_participation=False,
                accessible=True,
            )

    def detect_war_state(
        self,
        frame: np.ndarray,
        frame_id: int = 0,
    ) -> WarStateStatus:
        """Detect current war state from frame.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            WarStateStatus with current state
        """
        if cv2 is None:
            return self._build_status()

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Check for conflict indicators
        conflict_mask = cv2.inRange(hsv, self._CONFLICT_RED_LOW, self._CONFLICT_RED_HIGH)
        conflict_pixels = cv2.countNonZero(conflict_mask)

        # Check for peace indicators
        peace_mask = cv2.inRange(hsv, self._PEACE_GREEN_LOW, self._PEACE_GREEN_HIGH)
        peace_pixels = cv2.countNonZero(peace_mask)

        # Check for tension/warning indicators
        warning_mask = cv2.inRange(hsv, self._WARNING_YELLOW_LOW, self._WARNING_YELLOW_HIGH)
        warning_pixels = cv2.countNonZero(warning_mask)

        # Determine state based on indicators
        new_state = self._current_state

        if conflict_pixels > 5000:
            new_state = WarState.ACTIVE_CONFLICT
        elif warning_pixels > 3000:
            new_state = WarState.TENSION
        elif peace_pixels > 5000:
            new_state = WarState.PEACE

        # State transition
        if new_state != self._current_state:
            self._on_state_change(new_state)

        # Calculate conflict intensity
        total_pixels = frame.shape[0] * frame.shape[1]
        conflict_intensity = conflict_pixels / max(total_pixels, 1)

        return self._build_status(conflict_intensity=conflict_intensity)

    def _on_state_change(self, new_state: WarState) -> None:
        """Handle war state change."""
        old_state = self._current_state
        self._current_state = new_state
        self._state_change_time = time.perf_counter()

        log.info("[NatlanWar] State changed: %s -> %s", old_state.value, new_state.value)

        if self._on_war_state_change:
            try:
                self._on_war_state_change(old_state, new_state)
            except Exception as exc:
                log.warning("[NatlanWar] State change callback failed: %s", exc)

    def _build_status(
        self,
        conflict_intensity: float = 0.0,
    ) -> WarStateStatus:
        """Build current war state status."""
        active_tribes = [
            t for t, s in self._tribal_standings.items()
            if s.war_participation
        ]

        affected_areas = [area for area, restricted in self._affected_areas.items() if restricted]

        quest_restrictions = self._get_quest_restrictions()

        return WarStateStatus(
            current_state=self._current_state,
            active_tribes=active_tribes,
            affected_areas=affected_areas,
            quest_restrictions=quest_restrictions,
            conflict_intensity=conflict_intensity,
        )

    def _get_quest_restrictions(self) -> list[str]:
        """Get list of current quest restrictions."""
        restrictions = []

        if self._current_state == WarState.ACTIVE_CONFLICT:
            restrictions.append("Cannot start peace-related quests")
            restrictions.append("Some NPC dialogues restricted")
        elif self._current_state == WarState.TENSION:
            restrictions.append("Some tribal borders restricted")
        elif self._current_state == WarState.CEASEFIRE:
            restrictions.append("Limited conflict - some areas still dangerous")

        return restrictions

    def set_war_state(
        self,
        state: WarState,
        active_tribes: list[Tribe] | None = None,
    ) -> None:
        """Set war state (for testing or scripted events).

        Args:
            state: New war state
            active_tribes: Tribes involved in conflict
        """
        if active_tribes:
            for tribe in Tribe:
                self._tribal_standings[tribe] = TribalStanding(
                    tribe=tribe,
                    relationship_level=self._tribal_standings[tribe].relationship_level,
                    war_participation=tribe in active_tribes,
                    accessible=tribe not in active_tribes or state != WarState.ACTIVE_CONFLICT,
                )

        self._on_state_change(state)

    def update_tribal_standing(
        self,
        tribe: Tribe,
        relationship_change: int,
        is_war_participant: bool | None = None,
    ) -> None:
        """Update standing with a tribe.

        Args:
            tribe: Tribe to update
            relationship_change: Change in relationship (-100 to 100)
            is_war_participant: Optional override for war participation
        """
        current = self._tribal_standings[tribe]

        new_relationship = max(-100, min(100, current.relationship_level + relationship_change))
        new_war = is_war_participant if is_war_participant is not None else current.war_participation
        new_accessible = not new_war or self._current_state != WarState.ACTIVE_CONFLICT

        self._tribal_standings[tribe] = TribalStanding(
            tribe=tribe,
            relationship_level=new_relationship,
            war_participation=new_war,
            accessible=new_accessible,
        )

        log.info(
            "[NatlanWar] Standing with %s: %d (participating: %s)",
            tribe.value, new_relationship, new_war
        )

    def is_area_accessible(self, area: str) -> bool:
        """Check if an area is accessible.

        Args:
            area: Area identifier

        Returns:
            True if area can be accessed
        """
        if area in self._affected_areas:
            return not self._affected_areas[area]

        # Check tribal accessibility
        for tribe, standing in self._tribal_standings.items():
            if not standing.accessible:
                # This area might be tribal territory
                if self._tribe_occupies_area(tribe, area):
                    return False

        return True

    def _tribe_occupies_area(self, tribe: Tribe, area: str) -> bool:
        """Check if a tribe occupies an area."""
        # Simple mapping - would be more complex in production
        tribe_areas = {
            Tribe.FALLS: ["echoes", "children"],
            Tribe.MOLLENTS: ["flower", "feather", "cliffs"],
            Tribe.SCIONS: ["canopy", "forest"],
            Tribe.COLD: ["springs", "hot_springs"],
            Tribe.NATLAN_CITY: ["city", "central"],
            Tribe.MASTERLESS: ["neutral", "common"],
        }

        areas = tribe_areas.get(tribe, [])
        return any(a in area.lower() for a in areas)

    def set_area_restricted(
        self,
        area: str,
        restricted: bool,
    ) -> None:
        """Set area restriction status.

        Args:
            area: Area identifier
            restricted: Whether area is restricted
        """
        was_restricted = self._affected_areas.get(area, False)
        self._affected_areas[area] = restricted

        if restricted and not was_restricted and self._on_area_restricted:
            try:
                self._on_area_restricted(area)
            except Exception as exc:
                log.warning("[NatlanWar] Area restricted callback failed: %s", exc)

        if not restricted and was_restricted and self._on_area_opened:
            try:
                self._on_area_opened(area)
            except Exception as exc:
                log.warning("[NatlanWar] Area opened callback failed: %s", exc)

    def get_guidance(self, status: WarStateStatus) -> str | None:
        """Get guidance based on war state.

        Args:
            status: Current war state

        Returns:
            Guidance string
        """
        if status.current_state == WarState.ACTIVE_CONFLICT:
            if status.conflict_intensity > 0.3:
                return "Active conflict - avoid affected areas"
            return "Conflict in progress - proceed with caution"
        elif status.current_state == WarState.TENSION:
            return "Tension building - some areas may become restricted"
        elif status.current_state == WarState.CEASEFIRE:
            return "Ceasefire active - some restrictions remain"
        elif status.current_state == WarState.AFTERMATH:
            return "Post-conflict recovery - areas gradually reopening"
        return "Area is peaceful"

    def get_peace_travel_routes(self) -> list[list[str]]:
        """Get recommended travel routes during conflict.

        Returns:
            List of route lists (each route is list of area IDs)
        """
        if self._current_state != WarState.ACTIVE_CONFLICT:
            return [["safe_path"]]

        # Routes that avoid conflict zones
        routes = []

        for area, restricted in self._affected_areas.items():
            if not restricted:
                routes.append([area, "neutral_area"])

        return routes if routes else [["emergency_route"]]

    def reset(self) -> None:
        """Reset handler state."""
        self._current_state = WarState.PEACE
        for tribe in Tribe:
            self._tribal_standings[tribe] = TribalStanding(
                tribe=tribe,
                relationship_level=0,
                war_participation=False,
                accessible=True,
            )
        self._affected_areas = {}
        self._state_change_time = 0.0
        log.info("[NatlanWarStateHandler] Handler reset")