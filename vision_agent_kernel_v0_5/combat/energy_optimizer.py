"""Energy recharge optimization system.

Implements C-44: Energy Recharge Optimization
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from combat.character_switch_manager import CharacterSwitchManager

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C-44: Energy Optimizer
# ---------------------------------------------------------------------------

class BurstTiming(str, Enum):
    """Burst timing quality."""
    PREMATURE = "premature"       # Too early, wastes potential
    OPTIMAL = "optimal"          # Perfect timing
    DELAYED = "delayed"          # Slightly late
    MISSED = "missed"            # Overkill or enemy dead


@dataclass(frozen=True, slots=True)
class EnergyState:
    """Current energy state of a character."""
    character_name: str
    current_energy: float
    max_energy: float
    energy_percent: float
    energy_gain_rate: float  # Energy per second
    particle_available: bool
    time_to_full_sec: float


@dataclass(frozen=True, slots=True)
class BurstPrediction:
    """Predicted burst opportunity."""
    character_name: str
    estimated_ready_time: float
    confidence: float
    target_encounter_id: str | None
    urgency: float  # 0.0-1.0


@dataclass(frozen=True, slots=True)
class EnergyOptimizationResult:
    """Result of energy optimization analysis."""
    current_state: EnergyState
    burst_prediction: BurstPrediction | None
    recommended_action: str
    particle_priority: float
    wait_time_sec: float | None


class EnergyRechargeOptimizer:
    """Optimizes energy recharge and burst timing.

    Key decisions:
    - When to collect particles vs. continue attacking
    - Optimal burst timing relative to enemy phases
    - Character switch timing for particle sharing
    - Save bursts for enrage/damage windows

    Energy mechanics:
    - Base energy gain is slow (~1-2 per second)
    - Particle collection gives burst (~10-15)
    - Elemental skills give energy (~10-13)
    - Taking damage gives small energy
    """

    # Energy thresholds
    PARTICLE_COLLECT_THRESHOLD = 0.6  # Collect particles at 60% energy
    BURST_READY_THRESHOLD = 0.95     # Burst when 95% ready
    MIN_BURST_ENERGY = 0.60          # Minimum energy to consider burst

    def __init__(self, switch_manager: CharacterSwitchManager | None = None) -> None:
        self._now_fn = time.perf_counter
        self._switch_manager = switch_manager
        self._character_states: dict[str, EnergyState] = {}
        self._burst_predictions: dict[str, BurstPrediction] = {}
        self._particle_history: list[tuple[float, float]] = []  # (time, energy)

    def update_energy(
        self,
        character_name: str,
        current_energy: float,
        max_energy: float,
        particle_detected: bool,
        timestamp: float | None = None,
    ) -> EnergyState:
        """Update energy state for a character.

        Args:
            character_name: Name of character.
            current_energy: Current energy amount.
            max_energy: Maximum energy (usually 160 for bursts).
            particle_detected: Whether elemental particle is visible.
            timestamp: Current time.

        Returns:
            Updated EnergyState.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        energy_percent = current_energy / max_energy if max_energy > 0 else 0.0

        # Calculate energy gain rate
        self._particle_history.append((now, energy_percent))
        # Keep last 30 seconds of history
        cutoff = now - 30.0
        self._particle_history = [(t, e) for t, e in self._particle_history if t >= cutoff]

        gain_rate = self._calculate_gain_rate(now)

        # Calculate time to full energy
        if gain_rate > 0:
            remaining = max_energy - current_energy
            time_to_full = remaining / gain_rate
        else:
            time_to_full = 999.0  # Essentially infinite

        state = EnergyState(
            character_name=character_name,
            current_energy=current_energy,
            max_energy=max_energy,
            energy_percent=energy_percent,
            energy_gain_rate=gain_rate,
            particle_available=particle_detected,
            time_to_full_sec=time_to_full,
        )

        self._character_states[character_name] = state
        return state

    def _calculate_gain_rate(self, now: float) -> float:
        """Calculate energy gain rate from particle history."""
        if len(self._particle_history) < 2:
            return 1.0  # Default rate

        recent = [(t, e) for t, e in self._particle_history if now - t <= 10.0]
        if len(recent) < 2:
            return 1.0

        # Calculate slope of energy over time
        dt = recent[-1][0] - recent[0][0]
        if dt <= 0:
            return 1.0

        de = (recent[-1][1] - recent[0][1]) * 160  # Convert percent to energy
        return max(0.1, de / dt)

    def predict_burst_opportunity(
        self,
        character_name: str,
        target_enemy_phase: str | None = None,
        timestamp: float | None = None,
    ) -> BurstPrediction | None:
        """Predict when a burst will be ready.

        Args:
            character_name: Name of character.
            target_enemy_phase: Phase of target enemy (for timing).
            timestamp: Current time.

        Returns:
            BurstPrediction if opportunity can be predicted.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        state = self._character_states.get(character_name)
        if state is None:
            return None

        # Calculate when burst will be ready
        ready_time = now + state.time_to_full_sec

        # Calculate confidence based on consistency
        confidence = min(1.0, 0.5 + (state.energy_gain_rate / 5.0))

        # Adjust confidence based on particle availability
        if state.particle_available:
            confidence = min(1.0, confidence + 0.2)

        prediction = BurstPrediction(
            character_name=character_name,
            estimated_ready_time=ready_time,
            confidence=confidence,
            target_encounter_id=None,
            urgency=self._calculate_burst_urgency(state, target_enemy_phase),
        )

        self._burst_predictions[character_name] = prediction
        return prediction

    def _calculate_burst_urgency(
        self,
        state: EnergyState,
        enemy_phase: str | None,
    ) -> float:
        """Calculate how urgent it is to use burst."""
        # High urgency when energy is full
        if state.energy_percent >= 1.0:
            return 0.9

        # Higher urgency during enrage phase
        if enemy_phase == "enrage":
            return 0.8

        # Normal urgency
        return 0.5

    def analyze_optimization(
        self,
        character_name: str,
        current_target_info: dict | None = None,
        timestamp: float | None = None,
    ) -> EnergyOptimizationResult:
        """Analyze optimal energy usage decisions.

        Args:
            character_name: Name of character.
            current_target_info: Information about current target.
            timestamp: Current time.

        Returns:
            EnergyOptimizationResult with recommendations.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        state = self._character_states.get(character_name)
        if state is None:
            return EnergyOptimizationResult(
                current_state=EnergyState(
                    character_name=character_name,
                    current_energy=0.0,
                    max_energy=160.0,
                    energy_percent=0.0,
                    energy_gain_rate=0.0,
                    particle_available=False,
                    time_to_full_sec=999.0,
                ),
                burst_prediction=None,
                recommended_action="wait_for_energy",
                particle_priority=0.0,
                wait_time_sec=None,
            )

        # Predict burst opportunity
        enemy_phase = current_target_info.get("phase") if current_target_info else None
        prediction = self.predict_burst_opportunity(character_name, enemy_phase, now)

        # Determine recommended action
        action, particle_priority, wait_time = self._determine_action(state, prediction)

        return EnergyOptimizationResult(
            current_state=state,
            burst_prediction=prediction,
            recommended_action=action,
            particle_priority=particle_priority,
            wait_time_sec=wait_time,
        )

    def _determine_action(
        self,
        state: EnergyState,
        prediction: BurstPrediction | None,
    ) -> tuple[str, float, float | None]:
        """Determine optimal action based on energy state."""
        # High energy - collect particles anyway if available
        if state.energy_percent >= self.BURST_READY_THRESHOLD:
            if state.particle_available:
                return ("collect_and_burst", 0.9, None)
            return ("ready_for_burst", 0.8, None)

        # Medium energy - prioritize particle collection
        if state.energy_percent >= self.PARTICLE_COLLECT_THRESHOLD:
            if state.particle_available:
                return ("prioritize_particles", 0.7, 5.0)
            return ("wait_for_particles", 0.5, 10.0)

        # Low energy - continue attacking
        return ("continue_attacking", 0.3, None)

    def get_best_burst_timing(
        self,
        character_names: list[str],
        target_encounter_duration: float,
        timestamp: float | None = None,
    ) -> tuple[str, float]:
        """Find the best character and timing for burst usage.

        Args:
            character_names: List of characters to consider.
            target_encounter_duration: How long the encounter will last.

        Returns:
            Tuple of (best_character, optimal_time_until_burst).
        """
        now = timestamp if timestamp is not None else self._now_fn()

        best_char = ""
        earliest_ready = float('inf')

        for char_name in character_names:
            pred = self._burst_predictions.get(char_name)
            if pred and pred.estimated_ready_time < earliest_ready:
                best_char = char_name
                earliest_ready = pred.estimated_ready_time

        if not best_char:
            # Default to first character
            best_char = character_names[0] if character_names else ""
            earliest_ready = now + 10.0

        return (best_char, max(0.0, earliest_ready - now))

    def should_switch_for_particles(
        self,
        current_character: str,
        target_character: str,
        particle_element: str,
        timestamp: float | None = None,
    ) -> bool:
        """Determine if character switch is worth it for particles.

        Args:
            current_character: Currently active character.
            target_character: Potential switch target.
            particle_element: Element of available particles.
            timestamp: Current time.

        Returns:
            True if switch is recommended.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        current_state = self._character_states.get(current_character)
        target_state = self._character_states.get(target_character)

        if current_state is None or target_state is None:
            return False

        # Switch if current is already high energy and target is low
        if current_state.energy_percent >= 0.8:
            if target_state.energy_percent < 0.5:
                return True

        return False

    def reset(self) -> None:
        """Reset optimizer state."""
        self._character_states.clear()
        self._burst_predictions.clear()
        self._particle_history.clear()