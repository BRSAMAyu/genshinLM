"""Q-28: NPC time availability handler.

Tracks NPC availability based on in-game time in Genshin.
Some NPCs only appear during specific time periods or weather.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class TimeOfDay(str, Enum):
    DAWN = "dawn"        # 5:00 - 8:00
    MORNING = "morning"  # 8:00 - 12:00
    NOON = "noon"        # 12:00 - 14:00
    AFTERNOON = "afternoon"  # 14:00 - 18:00
    EVENING = "evening"  # 18:00 - 21:00
    NIGHT = "night"      # 21:00 - 24:00
    MIDNIGHT = "midnight"  # 0:00 - 5:00


class Weather(str, Enum):
    CLEAR = "clear"
    CLOUDY = "cloudy"
    RAIN = "rain"
    STORM = "storm"
    SNOW = "snow"
    SANDSTORM = "sandstorm"


@dataclass(frozen=True, slots=True)
class NPCCondition:
    """Condition for NPC availability."""
    condition_type: str  # "time", "weather", "event", "quest"
    value: str | int | float
    description: str


@dataclass(frozen=True, slots=True)
class NPCAvailability:
    """NPC availability status."""
    npc_id: str
    npc_name: str
    is_available: bool
    current_conditions: list[NPCCondition]
    missing_conditions: list[NPCCondition]
    next_available_time: TimeOfDay | None = None


@dataclass(frozen=True, slots=True)
class TimeSchedule:
    """Time schedule for an NPC."""
    npc_id: str
    available_periods: list[tuple[TimeOfDay, TimeOfDay]]  # start, end
    location: str
    weather_preferences: list[Weather]


class NPCTimeAvailability:
    """Track and manage NPC availability by time and conditions."""

    def __init__(self) -> None:
        self._schedules: dict[str, TimeSchedule] = {}
        self._conditions: dict[str, list[NPCCondition]] = {}
        self._current_time: TimeOfDay = TimeOfDay.MORNING
        self._current_weather: Weather = Weather.CLEAR

    def register_npc(
        self,
        npc_id: str,
        npc_name: str,
        available_periods: list[tuple[TimeOfDay, TimeOfDay]],
        location: str,
        weather_preferences: list[Weather] | None = None,
        additional_conditions: list[NPCCondition] | None = None,
    ) -> None:
        """Register an NPC with availability schedule.

        Args:
            npc_id: Unique NPC identifier
            npc_name: Display name
            available_periods: List of time periods when available
            location: Where to find the NPC
            weather_preferences: Preferred weather conditions
            additional_conditions: Other conditions (quest states, etc.)
        """
        schedule = TimeSchedule(
            npc_id=npc_id,
            available_periods=available_periods,
            location=location,
            weather_preferences=weather_preferences or [],
        )
        self._schedules[npc_id] = schedule
        self._conditions[npc_id] = additional_conditions or []

        log.info(
            "[NPCTimeAvailability] Registered %s (%s) at %s",
            npc_name, npc_id, location
        )

    def update_time_and_weather(self, time: TimeOfDay, weather: Weather) -> None:
        """Update current time and weather.

        Args:
            time: Current in-game time of day
            weather: Current weather
        """
        self._current_time = time
        self._current_weather = weather
        log.debug("[NPCTimeAvailability] Time: %s, Weather: %s", time.value, weather.value)

    def check_availability(self, npc_id: str) -> NPCAvailability:
        """Check if an NPC is currently available.

        Args:
            npc_id: NPC identifier

        Returns:
            NPCAvailability with current status
        """
        if npc_id not in self._schedules:
            return NPCAvailability(
                npc_id=npc_id,
                npc_name="Unknown",
                is_available=False,
                current_conditions=[],
                missing_conditions=[],
                next_available_time=None,
            )

        schedule = self._schedules[npc_id]
        conditions = self._conditions.get(npc_id, [])

        # Check time availability
        time_available = self._is_time_available(schedule.available_periods, self._current_time)

        # Check weather preference
        weather_ok = (
            len(schedule.weather_preferences) == 0 or
            self._current_weather in schedule.weather_preferences
        )

        # Check additional conditions (placeholder - would need quest state)
        conditions_met: list[NPCCondition] = []
        conditions_missing: list[NPCCondition] = []

        is_available = time_available and weather_ok and len(conditions_missing) == 0

        # Calculate next available time
        next_time = None
        if not time_available:
            next_time = self._get_next_available_time(schedule.available_periods, self._current_time)

        return NPCAvailability(
            npc_id=npc_id,
            npc_name=npc_id,  # Would store actual name
            is_available=is_available,
            current_conditions=conditions_met,
            missing_conditions=conditions_missing,
            next_available_time=next_time,
        )

    def _is_time_available(
        self,
        periods: list[tuple[TimeOfDay, TimeOfDay]],
        current: TimeOfDay,
    ) -> bool:
        """Check if current time falls within any available period."""
        current_order = list(TimeOfDay)

        for start, end in periods:
            start_idx = current_order.index(start)
            end_idx = current_order.index(end)

            if start_idx <= end_idx:
                # Normal range (e.g., 8:00 - 18:00)
                current_idx = current_order.index(current)
                if start_idx <= current_idx <= end_idx:
                    return True
            else:
                # Wraps around midnight (e.g., 21:00 - 5:00)
                current_idx = current_order.index(current)
                if current_idx >= start_idx or current_idx <= end_idx:
                    return True

        return False

    def _get_next_available_time(
        self,
        periods: list[tuple[TimeOfDay, TimeOfDay]],
        current: TimeOfDay,
    ) -> TimeOfDay | None:
        """Get next available time period."""
        current_order = list(TimeOfDay)
        current_idx = current_order.index(current)

        for start, _ in periods:
            start_idx = current_order.index(start)
            if start_idx > current_idx:
                return start

        # Next day
        if periods:
            return periods[0][0]

        return None

    def get_available_npcs(self, location: str | None = None) -> list[str]:
        """Get list of currently available NPCs.

        Args:
            location: Optional location filter

        Returns:
            List of available NPC IDs
        """
        available = []

        for npc_id in self._schedules:
            avail = self.check_availability(npc_id)
            if avail.is_available:
                if location is None or self._schedules[npc_id].location == location:
                    available.append(npc_id)

        return available

    def get_where_to_find(self, npc_id: str) -> str | None:
        """Get location hint for finding an NPC.

        Args:
            npc_id: NPC identifier

        Returns:
            Location string or None if NPC not registered
        """
        if npc_id in self._schedules:
            return self._schedules[npc_id].location
        return None

    def get_wait_time_hint(self, npc_id: str) -> str | None:
        """Get hint about how long to wait for NPC.

        Args:
            npc_id: NPC identifier

        Returns:
            Hint string or None
        """
        avail = self.check_availability(npc_id)

        if avail.is_available:
            return f"{npc_id} is currently available"
        elif avail.next_available_time:
            return f"{npc_id} will be available during {avail.next_available_time.value}"
        elif avail.missing_conditions:
            cond = avail.missing_conditions[0]
            return f"{npc_id} requires: {cond.description}"
        return None