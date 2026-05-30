"""Activity priority system: prioritizing limited-time events.

Covers S-36: Identifying and prioritizing limited-time events for maximum primogem
and material rewards. Includes event difficulty assessment and time allocation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event types and priorities
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    PRIMOGEM_EVENT = "primogem_event"         # High primogem rewards
    MATERIAL_EVENT = "material_event"         # Materials/economy event
    CHARACTER_EVENT = "character_event"      # Character trial/event
    BATTLE_EVENT = "battle_event"            # Combat challenge event
    PUZZLE_EVENT = "puzzle_event"            # Exploration/puzzle event
    MINIGAME_EVENT = "minigame_event"         # Mini-game event


class EventPriority(str, Enum):
    CRITICAL = "critical"     # Must do - high value
    HIGH = "high"             # Should do - good value
    MEDIUM = "medium"         # Consider doing - moderate value
    LOW = "low"               # Skip if time-limited - low value


# ---------------------------------------------------------------------------
# Event data
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class LimitedTimeEvent:
    """A limited-time event."""
    event_id: str
    name: str
    event_type: EventType
    start_date: str
    end_date: str
    primogem_reward: int = 0
    material_rewards: dict[str, int] = field(default_factory=dict)
    difficulty: float = 1.0   # 1.0 (easy) to 5.0 (hard)
    estimated_time_min: float = 10.0
    priority: EventPriority = EventPriority.MEDIUM
    description: str = ""


@dataclass(slots=True)
class EventRecommendation:
    """Recommendation for event participation."""
    event: LimitedTimeEvent
    participation_value: float   # Value score (rewards / time)
    should_participate: bool
    time_allocation_min: float
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Event database
# ---------------------------------------------------------------------------

# Representative event patterns (actual events vary by version)
KNOWN_EVENT_PATTERNS: dict[str, LimitedTimeEvent] = {
    "treasure_finding": LimitedTimeEvent(
        event_id="treasure_finding",
        name="寻宝之旅",
        event_type=EventType.PRIMOGEM_EVENT,
        start_date="",
        end_date="",
        primogem_reward=420,
        difficulty=1.5,
        estimated_time_min=15.0,
        priority=EventPriority.HIGH,
        description="探索地图寻找宝箱",
    ),
    "hypostasis_survival": LimitedTimeEvent(
        event_id="hypostasis_survival",
        name="纯水精灵生存战",
        event_type=EventType.BATTLE_EVENT,
        start_date="",
        end_date="",
        primogem_reward=600,
        material_rewards={"talent_book_freedom": 3},
        difficulty=3.0,
        estimated_time_min=30.0,
        priority=EventPriority.HIGH,
        description="生存挑战战斗",
    ),
    "bounce_bounce": LimitedTimeEvent(
        event_id="bounce_bounce",
        name="弹弹弹",
        event_type=EventType.MINIGAME_EVENT,
        start_date="",
        end_date="",
        primogem_reward=300,
        difficulty=1.5,
        estimated_time_min=20.0,
        priority=EventPriority.MEDIUM,
        description="弹球小游戏",
    ),
    "mona_puzzle": LimitedTimeEvent(
        event_id="mona_puzzle",
        name="莫娜的占星课",
        event_type=EventType.PUZZLE_EVENT,
        start_date="",
        end_date="",
        primogem_reward=480,
        material_rewards={"mora": 100000},
        difficulty=2.5,
        estimated_time_min=25.0,
        priority=EventPriority.MEDIUM,
        description="解谜活动",
    ),
    "energy_drinks": LimitedTimeEvent(
        event_id="energy_drinks",
        name="能量饮料大作战",
        event_type=EventType.MATERIAL_EVENT,
        start_date="",
        end_date="",
        primogem_reward=360,
        material_rewards={"character_exp_book": 20},
        difficulty=1.0,
        estimated_time_min=10.0,
        priority=EventPriority.MEDIUM,
        description="收集材料活动",
    ),
}


# ---------------------------------------------------------------------------
# Activity priority calculator
# ---------------------------------------------------------------------------

class ActivityPriorityCalculator:
    """Calculates optimal priority for limited-time events (S-36).

    Evaluates events based on primogem value, time investment, and
    material rewards to recommend participation order.
    """

    # Time value threshold (primogems per minute)
    MIN_VALUE_THRESHOLD = 10.0   # Skip events below 10 primogems/min

    def __init__(self) -> None:
        self._participation_history: dict[str, int] = {}

    def calculate_event_value(
        self,
        event: LimitedTimeEvent,
    ) -> float:
        """Calculate event value in primogems per minute.

        Args:
            event: Event to evaluate

        Returns:
            Value score (primogems per minute)
        """
        total_primogem = event.primogem_reward

        # Add material value (estimate ~1 primogem per 1000 mora equivalent)
        for mat_id, count in event.material_rewards.items():
            if mat_id == "mora":
                total_primogem += count / 1000
            elif "talent_book" in mat_id:
                total_primogem += count * 5
            elif "exp" in mat_id.lower():
                total_primogem += count * 0.5

        value = total_primogem / max(event.estimated_time_min, 1.0)
        return value

    def recommend_events(
        self,
        available_events: list[LimitedTimeEvent],
        time_budget_min: float = 60.0,
    ) -> list[EventRecommendation]:
        """Recommend which events to participate in.

        Args:
            available_events: List of available limited-time events
            time_budget_min: Available time for events

        Returns:
            Sorted list of EventRecommendation
        """
        recommendations: list[EventRecommendation] = []
        remaining_time = time_budget_min

        for event in available_events:
            value = self.calculate_event_value(event)

            # Skip low value events
            if value < self.MIN_VALUE_THRESHOLD:
                continue

            # Calculate participation
            time_needed = event.estimated_time_min
            should_participate = remaining_time >= time_needed

            if should_participate:
                recommendations.append(EventRecommendation(
                    event=event,
                    participation_value=value,
                    should_participate=True,
                    time_allocation_min=time_needed,
                    reasoning=f"{value:.1f} primogems/min - {event.description}",
                ))
                remaining_time -= time_needed
            else:
                recommendations.append(EventRecommendation(
                    event=event,
                    participation_value=value,
                    should_participate=False,
                    time_allocation_min=0.0,
                    reasoning=f"Not enough time (need {time_needed}min, have {remaining_time:.0f}min)",
                ))

        # Sort by value
        recommendations.sort(key=lambda r: r.participation_value, reverse=True)
        return recommendations

    def get_daily_event_priority(
        self,
        day_events: list[str],  # Event IDs for today
    ) -> list[tuple[str, EventPriority]]:
        """Get priority order for today's events.

        Returns list of (event_id, priority) tuples.
        """
        events = [KNOWN_EVENT_PATTERNS.get(eid) for eid in day_events]
        events = [e for e in events if e is not None]

        # Sort by priority then by value
        sorted_events = sorted(
            events,
            key=lambda e: (self._priority_order(e.priority), -self.calculate_event_value(e)),
        )

        return [(e.event_id, e.priority) for e in sorted_events]

    def _priority_order(self, priority: EventPriority) -> int:
        """Convert priority to sort order."""
        return {
            EventPriority.CRITICAL: 0,
            EventPriority.HIGH: 1,
            EventPriority.MEDIUM: 2,
            EventPriority.LOW: 3,
        }.get(priority, 2)


# ---------------------------------------------------------------------------
# Event schedule integration
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EventSchedule:
    """Schedule for event participation."""
    events: list[EventRecommendation]
    total_time_min: float
    total_primogem: int
    priority_order: list[str]


class EventScheduleBuilder:
    """Builds optimal event participation schedule."""

    def __init__(self) -> None:
        self._calculator = ActivityPriorityCalculator()

    def build_schedule(
        self,
        available_events: list[LimitedTimeEvent],
        daily_objectives: list[str],  # Other daily tasks
        total_time_budget: float = 120.0,
    ) -> EventSchedule:
        """Build optimal event participation schedule.

        Args:
            available_events: Events available to participate in
            daily_objectives: Other daily tasks to complete
            total_time_budget: Total available time

        Returns:
            EventSchedule with optimal participation plan
        """
        # Calculate time available for events
        daily_task_time = len(daily_objectives) * 10  # Estimate 10 min per task
        event_time_budget = max(0, total_time_budget - daily_task_time)

        # Get recommendations
        recommendations = self._calculator.recommend_events(
            available_events,
            event_time_budget,
        )

        # Build schedule
        schedule = EventSchedule(
            events=recommendations,
            total_time_min=sum(r.time_allocation_min for r in recommendations if r.should_participate),
            total_primogem=sum(r.event.primogem_reward for r in recommendations if r.should_participate),
            priority_order=[r.event.event_id for r in recommendations if r.should_participate],
        )

        return schedule

    def get_next_event(
        self,
        schedule: EventSchedule,
        completed_events: set[str],
    ) -> LimitedTimeEvent | None:
        """Get the next event to complete from schedule."""
        for recommendation in schedule.events:
            if recommendation.should_participate and recommendation.event.event_id not in completed_events:
                return recommendation.event
        return None