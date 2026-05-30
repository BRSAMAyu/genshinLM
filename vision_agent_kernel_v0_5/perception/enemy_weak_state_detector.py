"""Enemy weak state detection: identify vulnerability windows during combat.

Detects when enemies enter weakened states (staggered, downed, shield-broken,
elemental reaction stunned) enabling optimal burst timing for maximum DPS.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


class WeakStateType(str, Enum):
    STAGGERED = "staggered"       # Flinch from heavy hit
    DOWNED = "downed"             # Knocked down, vulnerable
    SHIELD_BROKEN = "shield_broken"  # Elemental shield destroyed
    FROZEN = "frozen"             # Cryo application
    STUNNED = "stunned"           # Overload/electrocharge stun
    PARALYZED = "paralyzed"       # Boss mechanic (e.g., Dvalin spine break)
    EXPOSED_CORE = "exposed_core"  # Boss core exposed (e.g., Shouki armor break)


@dataclass(frozen=True, slots=True)
class WeakStateEvent:
    """A detected weak state window."""
    state_type: WeakStateType
    target_id: str = ""
    estimated_duration: float = 5.0  # Seconds of vulnerability
    confidence: float = 0.8
    timestamp: float = 0.0


@dataclass(slots=True)
class WeakStateTracker:
    """Track enemy weak state windows for burst timing."""
    active_states: list[WeakStateEvent] = field(default_factory=list)
    expired_states: list[WeakStateEvent] = field(default_factory=list)
    burst_windows_used: int = 0
    burst_windows_missed: int = 0

    @property
    def has_burst_window(self) -> bool:
        return any(s.confidence >= 0.6 for s in self.active_states)

    @property
    def best_window(self) -> WeakStateEvent | None:
        viable = [s for s in self.active_states if s.confidence >= 0.6]
        if not viable:
            return None
        return max(viable, key=lambda s: (s.estimated_duration, s.confidence))


class EnemyWeakStateDetector:
    """Detect and track enemy weak state windows during combat.

    Weak states are detected via visual cues:
    - STAGGERED: enemy flinches, brief ~2s window
    - DOWNED: enemy on ground, ~5s window
    - SHIELD_BROKEN: shield HP depleted, ~8s window
    - FROZEN: cryo applied, ~3s window
    - STUNNED: overload reaction, ~4s window
    - PARALYZED: boss-specific mechanic, ~10s window
    - EXPOSED_CORE: boss armor broken, ~15s window

    Usage::

        detector = EnemyWeakStateDetector()
        events = detector.detect(visual_state, target_id="boss_1")
        if detector.tracker.has_burst_window:
            executor.execute_semantic("use_burst")
    """

    _DURATION_MAP: dict[WeakStateType, float] = {
        WeakStateType.STAGGERED: 2.0,
        WeakStateType.DOWNED: 5.0,
        WeakStateType.SHIELD_BROKEN: 8.0,
        WeakStateType.FROZEN: 3.0,
        WeakStateType.STUNNED: 4.0,
        WeakStateType.PARALYZED: 10.0,
        WeakStateType.EXPOSED_CORE: 15.0,
    }

    def __init__(self) -> None:
        self.tracker = WeakStateTracker()
        self._max_expired: int = 50

    def detect(
        self,
        visual_state: dict | None = None,
        target_id: str = "",
    ) -> list[WeakStateEvent]:
        """Detect weak states from visual observation."""
        now = time.perf_counter()

        # Expire old states
        self.tracker.active_states = [
            s for s in self.tracker.active_states
            if now - s.timestamp < s.estimated_duration
        ]

        if not visual_state:
            return []

        events: list[WeakStateEvent] = []

        # Detect from visual state cues
        if visual_state.get("shield_broken"):
            events.append(self._make_event(
                WeakStateType.SHIELD_BROKEN, target_id, now,
            ))
        if visual_state.get("frozen"):
            events.append(self._make_event(
                WeakStateType.FROZEN, target_id, now,
            ))
        if visual_state.get("stunned"):
            events.append(self._make_event(
                WeakStateType.STUNNED, target_id, now,
            ))
        if visual_state.get("downed"):
            events.append(self._make_event(
                WeakStateType.DOWNED, target_id, now,
            ))
        if visual_state.get("staggered"):
            events.append(self._make_event(
                WeakStateType.STAGGERED, target_id, now,
            ))
        if visual_state.get("core_exposed"):
            events.append(self._make_event(
                WeakStateType.EXPOSED_CORE, target_id, now,
            ))
        if visual_state.get("paralyzed"):
            events.append(self._make_event(
                WeakStateType.PARALYZED, target_id, now,
            ))

        # Add new events to tracker
        self.tracker.active_states.extend(events)
        return events

    def record_burst(self, used_window: bool) -> None:
        if used_window:
            self.tracker.burst_windows_used += 1
        else:
            self.tracker.burst_windows_missed += 1

    @property
    def burst_efficiency(self) -> float:
        total = self.tracker.burst_windows_used + self.tracker.burst_windows_missed
        if total == 0:
            return 0.0
        return self.tracker.burst_windows_used / total

    def _make_event(
        self, state_type: WeakStateType, target_id: str, now: float,
    ) -> WeakStateEvent:
        return WeakStateEvent(
            state_type=state_type,
            target_id=target_id,
            estimated_duration=self._DURATION_MAP[state_type],
            confidence=0.8,
            timestamp=now,
        )
