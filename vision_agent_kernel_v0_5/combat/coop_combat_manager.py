"""Cooperative multiplayer combat management.

Implements C-42: Multiplayer Combat
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from core.state_bus import StateBus

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C-42: Coop Combat Manager
# ---------------------------------------------------------------------------

class CoopMode(str, Enum):
    """Cooperative multiplayer mode states."""
    UNKNOWN = "unknown"
    SINGLE_PLAYER = "single_player"
    COOP_LOBBY = "coop_lobby"
    COOP_JOINED = "coop_joined"
    COOP_HOST = "coop_host"


@dataclass(frozen=True, slots=True)
class TeamMember:
    """Team member information in co-op."""
    slot: int
    character_name: str
    element: str
    health_percent: float
    energy_percent: float
    is_active: bool
    distance_to_player: float | None = None


@dataclass(frozen=True, slots=True)
class CoopState:
    """Current state of cooperative combat."""
    mode: CoopMode
    party_size: int
    host_name: str | None
    members: tuple[TeamMember, ...]
    sync_target: str | None
    last_sync_time: float


@dataclass(frozen=True, slots=True)
class SyncAction:
    """Synchronized action between team members."""
    action_type: str  # "attack", "heal", "shield", "burst"
    target_slot: int | None
    timing_window_ms: int
    leader_initiated: bool


class CoopModeDetector:
    """Detects multiplayer co-op state.

    Co-op differs from single player in several ways:
    - Multiple characters visible in overworld
    - Party UI shows 4 player names
    - Different targeting behavior (can't target other players' characters)
    """

    def __init__(self) -> None:
        self._now_fn = time.perf_counter
        self._last_state: CoopState | None = None
        self._detection_count = 0

    @property
    def last_state(self) -> CoopState | None:
        return self._last_state

    def detect(
        self,
        frame: np.ndarray | None,
        party_count: int,
        visible_characters: list[str],
        has_party_leader_name: bool,
        timestamp: float | None = None,
    ) -> CoopState:
        """Detect current co-op state from visual and game state.

        Args:
            frame: Optional frame for visual detection.
            party_count: Number of players in party (from game state).
            visible_characters: Character names visible on screen.
            has_party_leader_name: Whether party leader name is shown.
            timestamp: Current time, defaults to perf_counter.

        Returns:
            Detected CoopState.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        mode = self._determine_mode(
            party_count, visible_characters, has_party_leader_name
        )

        # Build team members from visible characters
        members: list[TeamMember] = []
        for i, name in enumerate(visible_characters[:4]):
            members.append(TeamMember(
                slot=i + 1,
                character_name=name,
                element="unknown",  # Would need element detection
                health_percent=1.0,
                energy_percent=0.0,
                is_active=(i == 0),
            ))

        state = CoopState(
            mode=mode,
            party_size=party_count if mode != CoopMode.SINGLE_PLAYER else 1,
            host_name=None,  # Would need party data extraction
            members=tuple(members),
            sync_target=None,
            last_sync_time=now,
        )

        self._last_state = state
        self._detection_count += 1
        return state

    def _determine_mode(
        self,
        party_count: int,
        visible_characters: list[str],
        has_party_leader_name: bool,
    ) -> CoopMode:
        """Determine co-op mode from detection data."""
        if party_count <= 1 and len(visible_characters) <= 1:
            return CoopMode.SINGLE_PLAYER

        if has_party_leader_name and len(visible_characters) > 1:
            return CoopMode.COOP_JOINED

        if len(visible_characters) > 1 and not has_party_leader_name:
            return CoopMode.COOP_LOBBY

        return CoopMode.UNKNOWN

    def is_coop(self) -> bool:
        """Check if currently in co-op mode."""
        if self._last_state is None:
            return False
        return self._last_state.mode not in (
            CoopMode.SINGLE_PLAYER,
            CoopMode.UNKNOWN,
        )


class TeamSyncManager:
    """Manages team synchronization in co-op combat.

    In co-op, players need to coordinate:
    - Who tanks which enemy
    - Burst timing to avoid waste
    - Healer focus management
    """

    def __init__(self) -> None:
        self._now_fn = time.perf_counter
        self._sync_queue: list[SyncAction] = []
        self._last_coordinated_burst: float = 0.0
        self._burst_cooldown_sec: float = 30.0

    def enqueue_sync_action(self, action: SyncAction) -> None:
        """Add a synchronized action to the queue."""
        self._sync_queue.append(action)

    def get_next_sync_action(self) -> SyncAction | None:
        """Get next action to execute for synchronization."""
        if not self._sync_queue:
            return None

        now = self._now_fn()
        action = self._sync_queue.pop(0)
        return action

    def can_coordinated_burst(self) -> bool:
        """Check if coordinated burst is available (not on cooldown)."""
        now = self._now_fn()
        return (now - self._last_coordinated_burst) >= self._burst_cooldown_sec

    def record_burst_executed(self) -> None:
        """Record that a coordinated burst was executed."""
        self._last_coordinated_burst = self._now_fn()

    def create_coordinated_burst(
        self,
        target_slot: int,
        action_type: str = "burst",
    ) -> SyncAction:
        """Create a coordinated burst action."""
        return SyncAction(
            action_type=action_type,
            target_slot=target_slot,
            timing_window_ms=2000,  # 2 second window
            leader_initiated=True,
        )

    def adjust_for_coop(
        self,
        single_player_plan: dict,
        coop_state: CoopState,
    ) -> dict:
        """Adjust single-player combat plan for co-op context.

        In co-op:
        - Don't overlap damage with other players
        - Target different enemies if possible
        - Coordinate burst windows
        """
        adjusted = dict(single_player_plan)

        # Reduce aggression if other players nearby
        if coop_state.party_size > 1:
            if "aggression" in adjusted:
                adjusted["aggression"] = min(1.0, adjusted["aggression"] * 0.7)

        # Add co-op specific behaviors
        adjusted["coop_mode"] = True
        adjusted["party_size"] = coop_state.party_size

        return adjusted

    def clear_queue(self) -> None:
        """Clear pending sync actions."""
        self._sync_queue.clear()