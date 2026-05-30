"""Boss mechanic management with enrage handling.

S-24: BossEnrageManager - Enrage phase recognition and emergency strategies

This module handles boss enrage mechanics and provides emergency response
when bosses enter their enrage/berserk phases.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# S-24: Boss Enrage Management
# ---------------------------------------------------------------------------

class EnragePhase(str, Enum):
    """Boss enrage phase states."""
    NORMAL = "normal"            # Normal combat phase
    WARNING = "warning"          # Enrage about to trigger
    ENRAGED = "enraged"          # Enrage active - damage increased
    BERSERK = "berserk"          # Final phase - extremely dangerous
    RECOVERY = "recovery"        # Post-enrage cooldown window


class EmergencyStrategy(str, Enum):
    """Emergency response strategies for enrage phases."""
    DEFENSIVE = "defensive"       # Focus on survival, minimize risk
    AGGRESSIVE_BURST = "aggressive_burst"  # Maximize DPS before enrage
    PHASE_THROUGH = "phase_through"  # Accept damage, push through
    RETREAT_RESET = "retreat_reset"  # Retreat and reset fight


@dataclass(frozen=True, slots=True)
class EnrageWarning:
    """Warning indicators that enrage is approaching."""
    time_elapsed_min: float
    boss_health_percent: float
    warning_signals: tuple[str, ...]  # e.g., "screen_tint_red", "boss_animation"
    estimated_time_to_enrage: float


@dataclass(frozen=True, slots=True)
class EnrageThresholds:
    """Thresholds for enrage phase detection."""
    time_based_min: float | None = None      # Time until enrage (if time-based)
    health_percent_trigger: float | None = None  # Health % that triggers enrage
    damage_multiplier_on_enrage: float = 1.0
    speed_multiplier_on_enrage: float = 1.0
    enrage_duration_sec: float | None = None  # How long enrage lasts


@dataclass(frozen=True, slots=True)
class EnrageState:
    """Current state of boss enrage."""
    phase: EnragePhase
    time_in_phase_sec: float = 0.0
    damage_multiplier: float = 1.0
    speed_multiplier: float = 1.0
    next_enrage_window: float | None = None


@dataclass(frozen=True, slots=True)
class EmergencyResponse:
    """Emergency response plan for enrage situations."""
    strategy: EmergencyStrategy
    immediate_actions: tuple[str, ...]
    team_adjustments: tuple[str, ...]
    target_dps_requirement: float | None = None  # DPS needed to phase through
    survival_priority: tuple[str, ...]
    fallback_action: str


@dataclass(frozen=True, slots=True)
class EnragePlan:
    """Complete enrage management plan."""
    boss_name: str
    thresholds: EnrageThresholds
    current_state: EnrageState
    warnings: tuple[EnrageWarning, ...]
    emergency_response: EmergencyResponse
    recommended_approach: str
    success_probability: float


class BossEnrageManager:
    """Manages boss enrage phases with emergency response strategies.

    S-24: Identifies when bosses enter enrage/berserk phases and provides
    strategic responses for survival and successful completion.
    """

    # Common boss enrage thresholds (can be overridden per boss)
    DEFAULT_THRESHOLDS = EnrageThresholds(
        time_based_min=8.0,
        health_percent_trigger=0.30,
        damage_multiplier_on_enrage=2.0,
        speed_multiplier_on_enrage=1.5,
    )

    # Warning signals to detect
    ENRAGE_WARNINGS = (
        "screen_tint_orange",
        "boss_roar_animation",
        "boss_charge_up_animation",
        "boss_color_shift",
        "background_darken",
        "music_intensify",
    )

    def __init__(self) -> None:
        self._thresholds: dict[str, EnrageThresholds] = {}
        self._current_warnings: list[str] = []

    def register_boss_thresholds(
        self,
        boss_name: str,
        thresholds: EnrageThresholds,
    ) -> None:
        """Register custom thresholds for a specific boss."""
        self._thresholds[boss_name.lower()] = thresholds

    def get_thresholds(self, boss_name: str) -> EnrageThresholds:
        """Get thresholds for a boss, falling back to defaults."""
        return self._thresholds.get(
            boss_name.lower(), self.DEFAULT_THRESHOLDS
        )

    def detect_enrage_warning(
        self,
        boss_name: str,
        time_elapsed_sec: float,
        boss_health_percent: float,
        detected_signals: tuple[str, ...],
    ) -> EnrageWarning | None:
        """Detect warning signs that enrage is approaching."""
        thresholds = self.get_thresholds(boss_name)

        # Check time-based warning
        time_warning = False
        if thresholds.time_based_min:
            time_remaining = thresholds.time_based_min * 60 - time_elapsed_sec
            if 0 < time_remaining <= 60:  # 1 minute or less
                time_warning = True

        # Check health-based warning
        health_warning = False
        if thresholds.health_percent_trigger:
            if boss_health_percent <= thresholds.health_percent_trigger + 0.10:
                health_warning = True

        # Check detected signals
        signal_match = bool(
            set(detected_signals) & set(self.ENRAGE_WARNINGS)
        )

        if not (time_warning or health_warning or signal_match):
            return None

        # Estimate time to enrage
        if thresholds.time_based_min:
            time_to = max(0, thresholds.time_based_min * 60 - time_elapsed_sec)
        elif thresholds.health_percent_trigger:
            # Rough estimate based on typical boss HP curve
            health_gap = boss_health_percent - thresholds.health_percent_trigger
            time_to = health_gap * 120  # Rough: 2 min per 10% health
        else:
            time_to = 60.0  # Default 1 minute

        return EnrageWarning(
            time_elapsed_min=time_elapsed_sec / 60.0,
            boss_health_percent=boss_health_percent,
            warning_signals=tuple(s for s in detected_signals if s in self.ENRAGE_WARNINGS),
            estimated_time_to_enrage=time_to,
        )

    def determine_enrage_state(
        self,
        boss_name: str,
        time_elapsed_sec: float,
        boss_health_percent: float,
        phase_time_sec: float = 0.0,
    ) -> EnrageState:
        """Determine current enrage state."""
        thresholds = self.get_thresholds(boss_name)

        # Check if in normal phase
        if thresholds.time_based_min:
            if time_elapsed_sec >= thresholds.time_based_min * 60:
                return EnrageState(
                    phase=EnragePhase.ENRAGED,
                    time_in_phase_sec=phase_time_sec,
                    damage_multiplier=thresholds.damage_multiplier_on_enrage,
                    speed_multiplier=thresholds.speed_multiplier_on_enrage,
                )

        if thresholds.health_percent_trigger:
            if boss_health_percent <= thresholds.health_percent_trigger:
                return EnrageState(
                    phase=EnragePhase.ENRAGED,
                    time_in_phase_sec=phase_time_sec,
                    damage_multiplier=thresholds.damage_multiplier_on_enrage,
                    speed_multiplier=thresholds.speed_multiplier_on_enrage,
                )

        # Check warning phase
        if thresholds.time_based_min:
            time_remaining = thresholds.time_based_min * 60 - time_elapsed_sec
            if 0 < time_remaining <= 120:  # 2 minutes
                return EnrageState(
                    phase=EnragePhase.WARNING,
                    time_in_phase_sec=phase_time_sec,
                )

        if thresholds.health_percent_trigger:
            if boss_health_percent <= thresholds.health_percent_trigger + 0.15:
                return EnrageState(
                    phase=EnragePhase.WARNING,
                    time_in_phase_sec=phase_time_sec,
                )

        return EnrageState(phase=EnragePhase.NORMAL)

    def create_emergency_response(
        self,
        boss_name: str,
        current_state: EnrageState,
        team_has_shield: bool,
        team_has_healer: bool,
        team_dps_estimate: float,
        boss_health_remaining_pct: float,
        available_revival_count: int,
    ) -> EmergencyResponse:
        """Create emergency response plan for enrage."""
        thresholds = self.get_thresholds(boss_name)

        immediate: list[str] = []
        adjustments: list[str] = []
        survival: list[str] = []

        # Determine strategy based on state
        if current_state.phase == EnragePhase.WARNING:
            strategy = EmergencyStrategy.AGGRESSIVE_BURST
            immediate.append("Maximize damage output immediately")
            immediate.append("Save bursts for enrage window")
            target_dps = self._calculate_required_dps(
                boss_health_remaining_pct, 60.0
            )
            survival.append("Position characters for burst window")
            survival.append("Pre-heal to full before enrage")

        elif current_state.phase == EnragePhase.ENRAGED:
            if team_has_shield and team_has_healer:
                strategy = EmergencyStrategy.DEFENSIVE
                immediate.append("Switch to defensive playstyle")
                immediate.append("Maintain shield uptime")
                adjustments.append("Ensure healer is active")
                survival.extend([
                    "Prioritize dodging over damage",
                    "Don't facetank enrage attacks",
                ])
            elif team_dps_estimate >= self._calculate_required_dps(
                boss_health_remaining_pct, 30.0
            ):
                strategy = EmergencyStrategy.PHASE_THROUGH
                immediate.append("Burst damage during enrage window")
                immediate.append("Accept damage to push through")
                survival.append("Use i-frames strategically")
            else:
                strategy = EmergencyStrategy.RETREAT_RESET
                immediate.append("Consider retreat and reset")
                immediate.append("Regroup with better buffs")

            target_dps = None if strategy == EmergencyStrategy.RETREAT_RESET else \
                self._calculate_required_dps(boss_health_remaining_pct, 30.0)

        else:
            strategy = EmergencyStrategy.DEFENSIVE
            immediate.append("Maintain normal rotation")
            target_dps = None

        survival.extend([
            "Keep HP above 50% at all times",
            "Save one revival for emergency",
        ])

        return EmergencyResponse(
            strategy=strategy,
            immediate_actions=tuple(immediate),
            team_adjustments=tuple(adjustments),
            target_dps_requirement=target_dps,
            survival_priority=tuple(survival),
            fallback_action="Retreat and re-prepare" if strategy == EmergencyStrategy.RETREAT_RESET
                else "Continue until enrage ends",
        )

    def create_enrage_plan(
        self,
        boss_name: str,
        time_elapsed_sec: float,
        boss_health_percent: float,
        team_has_shield: bool,
        team_has_healer: bool,
        team_dps_estimate: float,
        available_revival_count: int,
        detected_signals: tuple[str, ...] = (),
    ) -> EnragePlan:
        """Create complete enrage management plan."""
        thresholds = self.get_thresholds(boss_name)

        # Get warnings
        warnings: list[EnrageWarning] = []
        warning = self.detect_enrage_warning(
            boss_name, time_elapsed_sec, boss_health_percent, detected_signals
        )
        if warning:
            warnings.append(warning)

        # Determine state
        state = self.determine_enrage_state(
            boss_name, time_elapsed_sec, boss_health_percent
        )

        # Create emergency response
        response = self.create_emergency_response(
            boss_name, state, team_has_shield, team_has_healer,
            team_dps_estimate, boss_health_percent, available_revival_count,
        )

        # Determine recommended approach
        if state.phase == EnragePhase.NORMAL:
            approach = "Maintain normal damage output, watch for warning signs"
        elif state.phase == EnragePhase.WARNING:
            approach = "Begin burst rotation, prepare for enrage"
        elif state.phase == EnragePhase.ENRAGED:
            if response.strategy == EmergencyStrategy.DEFENSIVE:
                approach = "Switch to defensive, survive enrage window"
            elif response.strategy == EmergencyStrategy.AGGRESSIVE_BURST:
                approach = "Push damage to phase through enrage"
            else:
                approach = "Retreat recommended - insufficient DPS"
        else:
            approach = "Continue current strategy"

        # Calculate success probability
        if state.phase == EnragePhase.NORMAL:
            prob = 0.9
        elif state.phase == EnragePhase.WARNING:
            prob = 0.8
        else:
            if response.strategy == EmergencyStrategy.RETREAT_RESET:
                prob = 0.3
            elif response.strategy == EmergencyStrategy.DEFENSIVE:
                prob = 0.7 if team_has_shield else 0.5
            else:
                prob = 0.6

        return EnragePlan(
            boss_name=boss_name,
            thresholds=thresholds,
            current_state=state,
            warnings=tuple(warnings),
            emergency_response=response,
            recommended_approach=approach,
            success_probability=prob,
        )

    def _calculate_required_dps(
        self,
        boss_health_remaining_pct: float,
        time_limit_sec: float,
    ) -> float:
        """Calculate DPS required to kill boss in time limit."""
        # Assume 100% HP = 10000 HP for scaling
        estimated_hp = boss_health_remaining_pct * 10000
        return estimated_hp / time_limit_sec