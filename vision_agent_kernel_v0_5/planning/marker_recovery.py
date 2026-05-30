"""Q-31: Marker recovery from disappeared quest markers.

Handles cases where quest markers disappear unexpectedly (common in
certain quests) and provides recovery strategies.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class MarkerState(str, Enum):
    VISIBLE = "visible"
    INVISIBLE = "invisible"
    DISAPPEARED = "disappeared"
    REAPPEARED = "reappeared"


@dataclass(frozen=True, slots=True)
class MarkerStatus:
    """Status of a quest marker."""
    marker_id: str
    state: MarkerState
    last_seen: float
    disappearance_duration: float | None
    position: tuple[float, float] | None
    is_stale: bool


@dataclass(frozen=True, slots=True)
class MarkerRecovery:
    """Recovery action for lost markers."""
    strategy: str  # "wait", "teleport", "npc_search", "area_search"
    target_position: tuple[float, float] | None
    wait_time_seconds: float
    reason: str


class MarkerRecoveryHandler:
    """Handle recovery when quest markers disappear."""

    # Time thresholds (seconds)
    _DISAPPEAR_THRESHOLD = 10.0      # Consider disappeared after 10s invisible
    _STALE_THRESHOLD = 60.0          # Stale after 60s disappeared

    def __init__(
        self,
        teleport_callback: Any = None,
        on_marker_lost: Any = None,
        on_marker_recovered: Any = None,
    ) -> None:
        self._teleport_callback = teleport_callback
        self._on_marker_lost = on_marker_lost
        self._on_marker_recovered = on_marker_recovered

        self._marker_status: dict[str, MarkerStatus] = {}
        self._marker_positions: dict[str, tuple[float, float]] = {}
        self._last_visible_time: float = 0.0

    def track_marker(
        self,
        marker_id: str,
        position: tuple[float, float],
    ) -> None:
        """Track a quest marker.

        Args:
            marker_id: Unique marker identifier
            position: Marker position (normalized 0-1)
        """
        now = time.perf_counter()
        status = MarkerStatus(
            marker_id=marker_id,
            state=MarkerState.VISIBLE,
            last_seen=now,
            disappearance_duration=None,
            position=position,
            is_stale=False,
        )
        self._marker_status[marker_id] = status
        self._marker_positions[marker_id] = position
        self._last_visible_time = now

    def update_marker_visibility(
        self,
        marker_id: str | None,
        visible: bool,
    ) -> MarkerStatus | None:
        """Update visibility status of a marker.

        Args:
            marker_id: Marker to update (None = any marker)
            visible: Whether marker is visible

        Returns:
            Updated MarkerStatus or None
        """
        now = time.perf_counter()

        if marker_id is None:
            # Update based on general visibility
            if visible:
                self._last_visible_time = now
                # Mark any disappeared markers as reappeared
                for mid, status in self._marker_status.items():
                    if status.state in (MarkerState.INVISIBLE, MarkerState.DISAPPEARED):
                        self._marker_status[mid] = MarkerStatus(
                            marker_id=mid,
                            state=MarkerState.REAPPEARED,
                            last_seen=now,
                            disappearance_duration=now - status.last_seen,
                            position=status.position,
                            is_stale=False,
                        )
                        if self._on_marker_recovered:
                            try:
                                self._on_marker_recovered(mid)
                            except Exception as exc:
                                log.warning("[MarkerRecovery] Recovery callback failed: %s", exc)
            else:
                # Check for disappeared markers
                for mid, status in self._marker_status.items():
                    if status.state == MarkerState.VISIBLE:
                        time_since_seen = now - status.last_seen
                        if time_since_seen > self._DISAPPEAR_THRESHOLD:
                            is_stale = time_since_seen > self._STALE_THRESHOLD
                            self._marker_status[mid] = MarkerStatus(
                                marker_id=mid,
                                state=MarkerState.DISAPPEARED,
                                last_seen=status.last_seen,
                                disappearance_duration=time_since_seen,
                                position=status.position,
                                is_stale=is_stale,
                            )
                            log.warning(
                                "[MarkerRecovery] Marker %s disappeared (%.1fs ago)",
                                mid, time_since_seen
                            )
                            if self._on_marker_lost:
                                try:
                                    self._on_marker_lost(mid, time_since_seen)
                                except Exception as exc:
                                    log.warning("[MarkerRecovery] Lost callback failed: %s", exc)

            return None

        # Update specific marker
        if marker_id not in self._marker_status:
            return None

        status = self._marker_status[marker_id]

        if visible:
            self._marker_status[marker_id] = MarkerStatus(
                marker_id=marker_id,
                state=MarkerState.VISIBLE,
                last_seen=now,
                disappearance_duration=None,
                position=status.position,
                is_stale=False,
            )
        else:
            time_since_seen = now - status.last_seen
            is_stale = time_since_seen > self._STALE_THRESHOLD
            self._marker_status[marker_id] = MarkerStatus(
                marker_id=marker_id,
                state=MarkerState.INVISIBLE if time_since_seen < self._DISAPPEAR_THRESHOLD else MarkerState.DISAPPEARED,
                last_seen=status.last_seen,
                disappearance_duration=time_since_seen,
                position=status.position,
                is_stale=is_stale,
            )

        return self._marker_status[marker_id]

    def get_disappeared_markers(self) -> list[MarkerStatus]:
        """Get all disappeared markers."""
        return [
            s for s in self._marker_status.values()
            if s.state in (MarkerState.INVISIBLE, MarkerState.DISAPPEARED)
        ]

    def generate_recovery(
        self,
        marker_id: str,
    ) -> MarkerRecovery | None:
        """Generate recovery plan for a disappeared marker.

        Args:
            marker_id: Disappeared marker

        Returns:
            MarkerRecovery with recovery strategy
        """
        if marker_id not in self._marker_status:
            return None

        status = self._marker_status[marker_id]

        if status.state == MarkerState.VISIBLE:
            return MarkerRecovery(
                strategy="none",
                target_position=None,
                wait_time_seconds=0.0,
                reason="Marker is visible",
            )

        duration = status.disappearance_duration or 0.0

        # Recovery strategies based on disappearance duration
        if duration < 30:
            # Short disappearance - just wait
            return MarkerRecovery(
                strategy="wait",
                target_position=None,
                wait_time_seconds=10.0,
                reason="Marker may reappear shortly",
            )

        elif duration < 120:
            # Medium disappearance - try area search first
            return MarkerRecovery(
                strategy="area_search",
                target_position=status.position,
                wait_time_seconds=30.0,
                reason="Search last known area",
            )

        elif status.is_stale:
            # Stale marker - teleport or NPC search
            if self._is_npc_marker(marker_id):
                return MarkerRecovery(
                    strategy="npc_search",
                    target_position=status.position,
                    wait_time_seconds=60.0,
                    reason="Quest NPC may be at location",
                )
            else:
                return MarkerRecovery(
                    strategy="teleport",
                    target_position=status.position,
                    wait_time_seconds=5.0,
                    reason="Teleport to last known marker location",
                )

        else:
            return MarkerRecovery(
                strategy="area_search",
                target_position=status.position,
                wait_time_seconds=45.0,
                reason="Extended search needed",
            )

    def _is_npc_marker(self, marker_id: str) -> bool:
        """Check if marker is associated with an NPC."""
        # Simple heuristic: markers with "npc" or "talk" in ID
        return "npc" in marker_id.lower() or "talk" in marker_id.lower()

    def execute_recovery(
        self,
        recovery: MarkerRecovery,
    ) -> bool:
        """Execute a recovery action.

        Args:
            recovery: Recovery to execute

        Returns:
            True if executed successfully
        """
        log.info(
            "[MarkerRecovery] Executing recovery: %s (target=%s)",
            recovery.strategy, recovery.target_position
        )

        if recovery.strategy == "teleport" and self._teleport_callback:
            try:
                self._teleport_callback(recovery.target_position)
                return True
            except Exception as exc:
                log.warning("[MarkerRecovery] Teleport failed: %s", exc)
                return False

        return True  # Wait and search don't need special handling

    def clear_marker(self, marker_id: str) -> None:
        """Clear a marker from tracking.

        Args:
            marker_id: Marker to clear
        """
        if marker_id in self._marker_status:
            del self._marker_status[marker_id]
        if marker_id in self._marker_positions:
            del self._marker_positions[marker_id]

    def get_all_marker_status(self) -> list[MarkerStatus]:
        """Get status of all tracked markers."""
        return list(self._marker_status.values())

    def is_any_marker_visible(self) -> bool:
        """Check if any marker is currently visible."""
        return any(s.state == MarkerState.VISIBLE for s in self._marker_status.values())

    def reset(self) -> None:
        """Reset handler state."""
        self._marker_status = {}
        self._marker_positions = {}
        self._last_visible_time = 0.0
        log.info("[MarkerRecoveryHandler] Handler reset")