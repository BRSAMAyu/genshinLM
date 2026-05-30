"""Narwhal combat handler for underwater boss fight.

Implements C-53: Narwhal Combat Handler
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.state_bus import StateBus

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C-53: Narwhal Combat Handler
# ---------------------------------------------------------------------------

class NarwhalPhase(str, Enum):
    """Narwhal boss fight phases."""
    OUTSIDE = "outside"           # Outside the narwhal
    ENTERING = "entering"         # Entering narwhal
    INSIDE_CORE = "inside_core"    # Inside narwhal core
    DANGER_ZONE = "danger_zone"    # Moving to danger zone
    ATTACK_WINDOW = "attack_window"  # Safe to attack
    EXITING = "exiting"           # Exiting narwhal


class NarwhalState(str, Enum):
    """Narwhal visual states."""
    CALM = "calm"
    AGITATED = "agitated"
    CHARGING = "charging"
    VULNERABLE = "vulnerable"
    DEFEATED = "defeated"


@dataclass(frozen=True, slots=True)
class NarwhalStatus:
    """Status of narwhal boss."""
    state: NarwhalState
    health_percent: float
    current_phase: NarwhalPhase
    attack_count: int  # Number of attacks in sequence
    is_exposed: bool    # Core/mouth exposed
    vulnerability_window_ms: float
    next_attack_predict: float | None


@dataclass(frozen=True, slots=True)
class AttackSequence:
    """Sequence of attacks in narwhal fight."""
    attack_types: tuple[str, ...]  # "swipe", "charge", "spit"
    current_index: int
    time_between_attacks_ms: float
    total_sequence_duration_ms: float


@dataclass(frozen=True, slots=True)
class NarwhalCombatContext:
    """Combat context for narwhal fight."""
    narwhal_status: NarwhalStatus
    player_position: str  # "outside", "inside", "danger_zone"
    oxygen_remaining_ms: float
    attack_sequence: AttackSequence | None
    recommended_action: str
    survival_priority: float


class NarwhalCombatHandler:
    """Handles combat against the narwhal boss.

    The narwhal fight involves:
    1. Outside phase: Attack while avoiding charges
    2. Entering: Get inside during safe window
    3. Inside: Attack core, manage oxygen
    4. Attack windows: Safe periods to deal damage

    Key mechanics:
    - Narwhal has attack sequences (3-5 attacks)
    - Core exposed after sequence completes
    - Oxygen depletes when inside
    - Must exit before oxygen runs out
    """

    # Attack sequence patterns
    ATTACK_PATTERNS: dict[str, list[str]] = {
        "charge_sequence": ["charge", "swipe", "charge"],
        "spit_sequence": ["spit", "spit", "charge"],
        "full_sequence": ["charge", "swipe", "spit", "charge", "swipe"],
    }

    def __init__(self) -> None:
        self._now_fn = time.perf_counter
        self._fight_start_time: float = 0.0
        self._current_status: NarwhalStatus | None = None
        self._attack_count = 0
        self._sequence_start_time: float = 0.0
        self._current_pattern: list[str] = []
        self._pattern_index = 0

    def detect_narwhal_status(
        self,
        frame: np.ndarray | None,
        narwhal_visible: bool,
        player_in_water: bool,
        oxygen_percent: float,
        timestamp: float | None = None,
    ) -> NarwhalStatus:
        """Detect narwhal status from visual and game state.

        Args:
            frame: Frame for visual detection.
            narwhal_visible: Whether narwhal is visible.
            player_in_water: Whether player is in water zone.
            oxygen_percent: Current oxygen percentage.
            timestamp: Current time.

        Returns:
            NarwhalStatus with current state.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        if not narwhal_visible:
            return NarwhalStatus(
                state=NarwhalState.DEFEATED,
                health_percent=0.0,
                current_phase=NarwhalPhase.OUTSIDE,
                attack_count=0,
                is_exposed=False,
                vulnerability_window_ms=0.0,
                next_attack_predict=None,
            )

        # Determine state from visual cues and game state
        state = self._determine_narwhal_state(
            narwhal_visible, player_in_water, oxygen_percent, now
        )

        # Determine phase
        phase = self._determine_phase(state, player_in_water, oxygen_percent)

        # Check if exposed
        is_exposed = (state == NarwhalState.VULNERABLE)

        # Estimate attack sequence progress
        self._update_attack_sequence(now)

        # Predict next attack
        next_attack = self._predict_next_attack(now) if self._attack_count > 0 else None

        status = NarwhalStatus(
            state=state,
            health_percent=1.0,  # Would be extracted from UI
            current_phase=phase,
            attack_count=self._attack_count,
            is_exposed=is_exposed,
            vulnerability_window_ms=3000.0 if is_exposed else 0.0,
            next_attack_predict=next_attack,
        )

        self._current_status = status
        return status

    def _determine_narwhal_state(
        self,
        visible: bool,
        in_water: bool,
        oxygen: float,
        timestamp: float,
    ) -> NarwhalState:
        """Determine narwhal visual state."""
        # This would need visual detection from frame
        # Simplified for now
        if self._attack_count >= 5:
            return NarwhalState.VULNERABLE

        elapsed = timestamp - self._sequence_start_time if self._sequence_start_time > 0 else 0

        if elapsed > 1000 and elapsed < 3000:
            return NarwhalState.CHARGING

        if self._attack_count > 0:
            return NarwhalState.AGITATED

        return NarwhalState.CALM

    def _determine_phase(
        self,
        state: NarwhalState,
        in_water: bool,
        oxygen: float,
    ) -> NarwhalPhase:
        """Determine current fight phase."""
        if state == NarwhalState.DEFEATED:
            return NarwhalPhase.OUTSIDE

        if not in_water:
            return NarwhalPhase.OUTSIDE

        if oxygen < 20:
            return NarwhalPhase.EXITING

        if state == NarwhalState.VULNERABLE:
            return NarwhalPhase.ATTACK_WINDOW

        if in_water:
            if state == NarwhalState.CHARGING:
                return NarwhalPhase.DANGER_ZONE
            return NarwhalPhase.INSIDE_CORE

        return NarwhalPhase.ENTERING

    def _update_attack_sequence(self, timestamp: float) -> None:
        """Update attack sequence tracking."""
        if self._sequence_start_time == 0:
            self._sequence_start_time = timestamp
            self._current_pattern = self.ATTACK_PATTERNS["charge_sequence"]
            self._pattern_index = 0
            self._attack_count = 0

        # Increment attack count based on time
        elapsed = timestamp - self._sequence_start_time
        expected_attacks = int(elapsed / 2000)  # Attack every 2 seconds

        if expected_attacks > self._attack_count:
            self._attack_count = expected_attacks

    def _predict_next_attack(self, timestamp: float) -> float | None:
        """Predict when next attack will occur."""
        if self._pattern_index >= len(self._current_pattern):
            return None

        elapsed = timestamp - self._sequence_start_time
        next_expected = (self._pattern_index + 1) * 2000  # 2 second interval

        if elapsed < next_expected:
            return timestamp + (next_expected - elapsed)

        return timestamp + 2000  # Default 2 second

    def get_combat_context(
        self,
        status: NarwhalStatus,
        player_position: str,
        oxygen_ms: float,
        timestamp: float | None = None,
    ) -> NarwhalCombatContext:
        """Get full combat context for narwhal fight.

        Args:
            status: Current narwhal status.
            player_position: Where player is ("outside", "inside", etc.).
            oxygen_ms: Oxygen remaining in milliseconds.
            timestamp: Current time.

        Returns:
            NarwhalCombatContext with full situation analysis.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        # Build attack sequence
        if self._current_pattern:
            seq = AttackSequence(
                attack_types=tuple(self._current_pattern),
                current_index=self._pattern_index,
                time_between_attacks_ms=2000.0,
                total_sequence_duration_ms=len(self._current_pattern) * 2000.0,
            )
        else:
            seq = None

        # Determine recommended action
        action = self._recommend_action(status, player_position, oxygen_ms)

        # Calculate survival priority
        survival_priority = self._calculate_survival_priority(
            status, player_position, oxygen_ms
        )

        return NarwhalCombatContext(
            narwhal_status=status,
            player_position=player_position,
            oxygen_remaining_ms=oxygen_ms,
            attack_sequence=seq,
            recommended_action=action,
            survival_priority=survival_priority,
        )

    def _recommend_action(
        self,
        status: NarwhalStatus,
        player_position: str,
        oxygen_ms: float,
    ) -> str:
        """Recommend action based on current context."""
        # Critical: Oxygen running out
        if oxygen_ms < 5000:
            return "exit_narwhal_immediately"

        # Outside narwhal - attack when possible
        if player_position == "outside":
            if status.is_exposed:
                return "max_damage_output"
            return "dodge_and_wait"

        # Inside narwhal
        if player_position == "inside":
            if status.is_exposed:
                return "attack_core"
            if oxygen_ms < 15000:
                return "prepare_exit"
            return "find_safe_spot"

        # Entering
        if player_position == "entering":
            return "move_to_core"

        return "wait"

    def _calculate_survival_priority(
        self,
        status: NarwhalStatus,
        player_position: str,
        oxygen_ms: float,
    ) -> float:
        """Calculate survival priority (0.0-1.0)."""
        priority = 0.1  # Base priority

        # Oxygen is critical
        if oxygen_ms < 5000:
            priority = 1.0
        elif oxygen_ms < 10000:
            priority = 0.8
        elif oxygen_ms < 20000:
            priority = 0.5

        # In danger zone
        if status.current_phase == NarwhalPhase.DANGER_ZONE:
            priority = max(priority, 0.9)

        # Narwhal charging
        if status.state == NarwhalState.CHARGING:
            priority = max(priority, 0.7)

        return priority

    def should_enter_narwhal(
        self,
        status: NarwhalStatus,
        oxygen_ms: float,
        timestamp: float | None = None,
    ) -> bool:
        """Determine if should enter narwhal (safe window).

        Args:
            status: Current narwhal status.
            oxygen_ms: Current oxygen in ms.
            timestamp: Current time.

        Returns:
            True if safe to enter.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        # Must have enough oxygen
        if oxygen_ms < 20000:
            return False

        # Safe during calm or after attack sequence
        if status.state == NarwhalState.CALM:
            return True

        if status.is_exposed:
            return True

        # Check timing
        if self._sequence_start_time > 0:
            elapsed = now - self._sequence_start_time
            # Safe window: after full sequence but before next
            if self._attack_count >= len(self._current_pattern):
                return True

        return False

    def get_damage_timing(
        self,
        status: NarwhalStatus,
        timestamp: float | None = None,
    ) -> tuple[bool, float]:
        """Get optimal damage timing.

        Returns:
            Tuple of (is_damage_window, window_duration_ms).
        """
        if status.is_exposed:
            return (True, status.vulnerability_window_ms)

        if status.current_phase == NarwhalPhase.ATTACK_WINDOW:
            return (True, 3000.0)

        return (False, 0.0)

    def reset(self) -> None:
        """Reset handler state."""
        self._fight_start_time = 0.0
        self._current_status = None
        self._attack_count = 0
        self._sequence_start_time = 0.0
        self._current_pattern = []
        self._pattern_index = 0