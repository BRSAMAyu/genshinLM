"""Enrage timer and phase management.

Implements C-45: Enrage Timer
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
# C-45: Enrage Timer
# ---------------------------------------------------------------------------

class EnragePhase(str, Enum):
    """Boss enrage phases."""
    NORMAL = "normal"
    WARNING = "warning"        # Enrage approaching
    ENRAGED = "enraged"       # Boss enrage active
    BERSERK = "berserk"       # Final/beyond enrage
    COOLDOWN = "cooldown"     # Post-enrage recovery


@dataclass(frozen=True, slots=True)
class EnrageTimerConfig:
    """Configuration for enrage timer."""
    time_limit_sec: float
    warning_threshold_sec: float = 60.0  # Start warning 60s before
    enrage_duration_sec: float = 10.0    # How long enrage lasts
    damage_multiplier: float = 2.0
    speed_multiplier: float = 1.5
    berserk_threshold_sec: float | None = None  # Beyond enrage


@dataclass(frozen=True, slots=True)
class EnrageTimerState:
    """Current state of enrage timer."""
    phase: EnragePhase
    time_elapsed_sec: float
    time_remaining_sec: float
    time_until_enrage_sec: float
    in_enrage_window: bool
    damage_multiplier: float
    speed_multiplier: float


@dataclass(frozen=True, slots=True)
class EnrageStrategy:
    """Strategy for handling enrage phase."""
    phase: EnragePhase
    recommended_actions: tuple[str, ...]
    damage_boost_priority: float
    survival_priority: float
    burst_timing: str


class EnrageMechanismHandler:
    """Handles boss enrage mechanics and timing.

    Many bosses have enrage timers:
    - Spiral Abyss: 180 second clear time per floor
    - Boss fights: 8-10 minute enrage timers
    - Event challenges: Varying time limits

    This system tracks time and provides strategic guidance.
    """

    # Default configurations for common boss types
    DEFAULT_CONFIGS: dict[str, EnrageTimerConfig] = {
        "spiral_abyss": EnrageTimerConfig(
            time_limit_sec=180.0,
            warning_threshold_sec=60.0,
            enrage_duration_sec=0.0,  # No enrage, just timer
            damage_multiplier=1.0,
            speed_multiplier=1.0,
        ),
        "world_boss": EnrageTimerConfig(
            time_limit_sec=600.0,
            warning_threshold_sec=120.0,
            enrage_duration_sec=15.0,
            damage_multiplier=2.0,
            speed_multiplier=1.5,
        ),
        "weekly_boss": EnrageTimerConfig(
            time_limit_sec=480.0,
            warning_threshold_sec=90.0,
            enrage_duration_sec=10.0,
            damage_multiplier=1.5,
            speed_multiplier=1.3,
        ),
        "event_challenge": EnrageTimerConfig(
            time_limit_sec=120.0,
            warning_threshold_sec=30.0,
            enrage_duration_sec=5.0,
            damage_multiplier=1.8,
            speed_multiplier=1.4,
        ),
    }

    def __init__(self) -> None:
        self._now_fn = time.perf_counter
        self._fight_start_time: float = 0.0
        self._enrage_start_time: float | None = None
        self._current_config: EnrageTimerConfig | None = None
        self._boss_name: str | None = None

    def start_fight(
        self,
        boss_type: str,
        custom_config: EnrageTimerConfig | None = None,
        timestamp: float | None = None,
    ) -> None:
        """Start enrage timer tracking for a fight.

        Args:
            boss_type: Type of boss for config lookup.
            custom_config: Override config if needed.
            timestamp: Current time.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        self._fight_start_time = now
        self._enrage_start_time = None
        self._boss_name = boss_type

        if custom_config:
            self._current_config = custom_config
        else:
            self._current_config = self.DEFAULT_CONFIGS.get(
                boss_type, self.DEFAULT_CONFIGS["world_boss"]
            )

        log.info("[EnrageTimer] Started fight timer for %s", boss_type)

    def update(
        self,
        boss_health_percent: float | None = None,
        timestamp: float | None = None,
    ) -> EnrageTimerState:
        """Update timer and return current state.

        Args:
            boss_health_percent: Current boss health (optional).
            timestamp: Current time.

        Returns:
            Current EnrageTimerState.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        if self._current_config is None:
            return EnrageTimerState(
                phase=EnragePhase.NORMAL,
                time_elapsed_sec=0.0,
                time_remaining_sec=0.0,
                time_until_enrage_sec=999.0,
                in_enrage_window=False,
                damage_multiplier=1.0,
                speed_multiplier=1.0,
            )

        elapsed = now - self._fight_start_time
        time_limit = self._current_config.time_limit_sec
        remaining = max(0.0, time_limit - elapsed)

        # Determine phase
        warning_threshold = self._current_config.warning_threshold_sec
        enrage_duration = self._current_config.enrage_duration_sec

        # Calculate time until enrage
        time_until_enrage = warning_threshold - elapsed

        phase: EnragePhase
        in_enrage_window = False
        damage_mult = 1.0
        speed_mult = 1.0

        if remaining <= 0:
            # Time's up
            phase = EnragePhase.BERSERK
            damage_mult = self._current_config.damage_multiplier * 1.5
            speed_mult = self._current_config.speed_multiplier * 1.2
        elif time_until_enrage <= 0:
            # In enrage window
            if self._enrage_start_time is None:
                self._enrage_start_time = now

            enrage_elapsed = now - self._enrage_start_time

            if enrage_elapsed >= enrage_duration:
                phase = EnragePhase.COOLDOWN
            else:
                phase = EnragePhase.ENRAGED
                in_enrage_window = True
                damage_mult = self._current_config.damage_multiplier
                speed_mult = self._current_config.speed_multiplier
        elif time_until_enrage <= 30:
            # Warning phase
            phase = EnragePhase.WARNING
        else:
            phase = EnragePhase.NORMAL

        # Check berserk threshold if defined
        if self._current_config.berserk_threshold_sec:
            if elapsed >= self._current_config.berserk_threshold_sec:
                phase = EnragePhase.BERSERK

        return EnrageTimerState(
            phase=phase,
            time_elapsed_sec=elapsed,
            time_remaining_sec=remaining,
            time_until_enrage_sec=max(0.0, time_until_enrage),
            in_enrage_window=in_enrage_window,
            damage_multiplier=damage_mult,
            speed_multiplier=speed_mult,
        )

    def create_strategy(
        self,
        state: EnrageTimerState,
        team_has_shield: bool,
        team_has_healer: bool,
        current_dps: float,
        remaining_boss_hp_percent: float,
    ) -> EnrageStrategy:
        """Create strategy based on current enrage state.

        Args:
            state: Current enrage timer state.
            team_has_shield: Whether team has shield capability.
            team_has_healer: Whether team has healer.
            current_dps: Current team DPS.
            remaining_boss_hp_percent: Remaining boss HP percentage.

        Returns:
            EnrageStrategy with recommended actions.
        """
        actions: list[str] = []
        burst_timing = "normal"

        if state.phase == EnragePhase.NORMAL:
            actions.append("Maintain consistent damage output")
            actions.append("Save bursts for warning phase")
            burst_timing = "save_for_warning"
            damage_boost = 0.8
            survival = 0.2

        elif state.phase == EnragePhase.WARNING:
            actions.append("Begin burst rotation immediately")
            actions.append("Pre-heal to full before enrage")
            if current_dps > 500:
                actions.append("Push for kill before enrage")
                burst_timing = "burst_now"
            else:
                actions.append("Prepare for sustained enrage")
                burst_timing = "prepare_enrage"
            damage_boost = 0.9
            survival = 0.3

        elif state.phase == EnragePhase.ENRAGED:
            if team_has_shield:
                actions.append("Maintain shield uptime")
            if team_has_healer:
                actions.append("Ensure healer is active")
            actions.append("Position for burst window")
            actions.append("Minimize risk, maximize DPS")
            burst_timing = "burst_in_window"
            damage_boost = 0.7
            survival = 0.6

        elif state.phase == EnragePhase.BERSERK:
            if team_has_shield and team_has_healer:
                actions.append("Full defensive mode")
                actions.append("I-frame through attacks")
                burst_timing = "i_frame_dps"
            else:
                actions.append("Emergency: Consider retreat")
                actions.append("Use all revives")
                burst_timing = "emergency_burst"
            damage_boost = 0.5
            survival = 0.9

        else:  # COOLDOWN
            actions.append("Resume normal rotation")
            actions.append("Recover from enrage")
            burst_timing = "normal"
            damage_boost = 0.8
            survival = 0.3

        return EnrageStrategy(
            phase=state.phase,
            recommended_actions=tuple(actions),
            damage_boost_priority=damage_boost,
            survival_priority=survival,
            burst_timing=burst_timing,
        )

    def estimate_clear_time(
        self,
        current_hp_percent: float,
        current_dps: float,
    ) -> float | None:
        """Estimate time to clear based on current DPS.

        Args:
            current_hp_percent: Remaining HP percentage.
            current_dps: Current DPS.

        Returns:
            Estimated clear time in seconds, or None if cannot estimate.
        """
        if current_dps <= 0 or current_hp_percent <= 0:
            return None

        # Assume 100% HP = 100000 damage for scaling
        remaining_hp = current_hp_percent * 100000
        clear_time = remaining_hp / current_dps

        return clear_time

    def is_time_critical(self, state: EnrageTimerState) -> bool:
        """Check if time is critical (low remaining time or enrage active).

        Args:
            state: Current timer state.

        Returns:
            True if time is critical.
        """
        return (
            state.phase in (EnragePhase.ENRAGED, EnragePhase.BERSERK) or
            state.time_remaining_sec < 30.0 or
            state.time_until_enrage_sec < 20.0
        )

    def reset(self) -> None:
        """Reset timer state."""
        self._fight_start_time = 0.0
        self._enrage_start_time = None
        self._current_config = None
        self._boss_name = None