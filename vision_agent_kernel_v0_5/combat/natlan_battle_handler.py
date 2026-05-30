"""Natlan battle handler for the Incandescent Zone.

Implements C-54: Natlan Battle Handler
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
# C-54: Natlan Battle Handler
# ---------------------------------------------------------------------------

class NatlanPhase(str, Enum):
    """Natlan zone phases."""
    ENTRANCE = "entrance"          # Entering Natlan
    NORMAL_COMBAT = "normal"       # Normal combat
    BATTLE_MUSIC = "battle_music"   # Battle music phase (enhanced)
    DANCE_SEQUENCE = "dance"        # Dance/rhythm sequence
    ULTIMATE_FORM = "ultimate"      # Ultimate form activation
    VICTORY = "victory"            # Victory phase


class BattleMusicState(str, Enum):
    """Battle music state detection."""
    CALM = "calm"                  # No music / calm
    BATTLE = "battle"              # Active battle music
    INTENSE = "intense"            # Intense phase (enrage)
    TRIBAL = "tribal"             # Tribal music (Natlan specific)


class FieldDomainType(str, Enum):
    """Type of field domain/arena."""
    TRIBAL_ARENA = "tribal_arena"
    PYRO_TERRAIN = "pyro_terrain"
    DANCE_FLOOR = "dance_floor"
    TRIBAL_CIRCLE = "tribal_circle"


@dataclass(frozen=True, slots=True)
class NatlanBattleStatus:
    """Status of Natlan battle."""
    current_phase: NatlanPhase
    music_state: BattleMusicState
    music_beat_ms: float | None     # Beat timing if detected
    field_domain: FieldDomainType
    tribal_power_percent: float     # 0.0-1.0 tribal power gauge
    dance_progress_percent: float   # Dance sequence progress
    is_ultimate_active: bool
    nearby_tribesmen_count: int


@dataclass(frozen=True, slots=True)
class DanceSequence:
    """Dance/rhythm sequence state."""
    is_active: bool
    current_step: int
    total_steps: int
    next_beat_ms: float
    accuracy_percent: float
    reward_multiplier: float


@dataclass(frozen=True, slots=True)
class NatlanCombatStrategy:
    """Combat strategy for Natlan zone."""
    phase: NatlanPhase
    beat_synced: bool
    tribal_bonus: float
    recommended_actions: tuple[str, ...]
    ultimate_ready: bool
    dance_optimization: DanceSequence | None


class NatlanBattleHandler:
    """Handles combat in Natlan (Snezhnaya's fire region).

    Natlan introduces several unique mechanics:
    1. Battle Music Sync: Combat节奏与音乐同步
    2. Tribal System: Nearby tribesmen provide bonuses
    3. Dance Sequences: Rhythmic action sequences
    4. Ultimate Forms: Power transformation

    Key mechanics:
    - Music beats provide damage/execution windows
    - Dance sequences grant buffs on success
    - Tribal power builds with nearby allies
    - Ultimate form has extended duration
    """

    # Beat timing (assuming 120 BPM = 500ms per beat)
    DEFAULT_BPM = 120
    BEAT_INTERVAL_MS = 500

    # Dance sequence steps
    DANCE_STEPS_TOTAL = 8

    def __init__(self) -> None:
        self._now_fn = time.perf_counter
        self._phase_start_time: float = 0.0
        self._beat_start_time: float = 0.0
        self._current_status: NatlanBattleStatus | None = None
        self._dance_state: DanceSequence | None = None
        self._music_beats_detected: int = 0

    def detect_battle_status(
        self,
        frame: np.ndarray | None,
        music_playing: bool,
        nearby_entities: list[str],
        tribal_power: float,
        timestamp: float | None = None,
    ) -> NatlanBattleStatus:
        """Detect Natlan battle status.

        Args:
            frame: Frame for visual detection.
            music_playing: Whether battle music is playing.
            nearby_entities: List of nearby entities (tribesmen, enemies).
            tribal_power: Current tribal power gauge (0.0-1.0).
            timestamp: Current time.

        Returns:
            NatlanBattleStatus with current state.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        # Detect music state
        music_state = self._detect_music_state(music_playing, now)

        # Determine phase
        phase = self._determine_phase(music_playing, tribal_power, nearby_entities)

        # Detect field domain
        domain = self._detect_domain(nearby_entities)

        # Calculate next beat timing
        beat_ms = self._calculate_beat_timing(now)

        # Update dance state if active
        if phase == NatlanPhase.DANCE_SEQUENCE:
            self._update_dance_state(now)

        status = NatlanBattleStatus(
            current_phase=phase,
            music_state=music_state,
            music_beat_ms=beat_ms,
            field_domain=domain,
            tribal_power_percent=tribal_power,
            dance_progress_percent=(
                self._dance_state.progress_percent if self._dance_state else 0.0
            ),
            is_ultimate_active=(phase == NatlanPhase.ULTIMATE_FORM),
            nearby_tribesmen_count=len([e for e in nearby_entities if "tribesman" in e.lower()]),
        )

        self._current_status = status
        return status

    def _detect_music_state(
        self,
        music_playing: bool,
        timestamp: float,
    ) -> BattleMusicState:
        """Detect battle music state."""
        if not music_playing:
            return BattleMusicState.CALM

        # Would need audio analysis for actual detection
        # Simplified here
        if self._music_beats_detected > 20:
            return BattleMusicState.TRIBAL
        elif self._music_beats_detected > 10:
            return BattleMusicState.INTENSE
        else:
            return BattleMusicState.BATTLE

    def _determine_phase(
        self,
        music_playing: bool,
        tribal_power: float,
        entities: list[str],
    ) -> NatlanPhase:
        """Determine current Natlan phase."""
        # Check for dance sequence trigger
        dance_keywords = ["dance", "rhythm", "sequence"]
        for entity in entities:
            if any(kw in entity.lower() for kw in dance_keywords):
                return NatlanPhase.DANCE_SEQUENCE

        # Ultimate form check
        if tribal_power >= 1.0:
            return NatlanPhase.ULTIMATE_FORM

        # Battle music phase
        if music_playing:
            return NatlanPhase.BATTLE_MUSIC

        # Normal combat
        return NatlanPhase.NORMAL_COMBAT

    def _detect_domain(self, entities: list[str]) -> FieldDomainType:
        """Detect current field domain type."""
        domain_keywords = {
            FieldDomainType.TRIBAL_ARENA: ["arena", "circle", "ring"],
            FieldDomainType.PYRO_TERRAIN: ["lava", "flame", "pyre"],
            FieldDomainType.DANCE_FLOOR: ["floor", "platform", "stage"],
            FieldDomainType.TRIBAL_CIRCLE: ["tribal", "totem"],
        }

        for domain, keywords in domain_keywords.items():
            for entity in entities:
                if any(kw in entity.lower() for kw in keywords):
                    return domain

        return FieldDomainType.TRIBAL_ARENA  # Default

    def _calculate_beat_timing(self, timestamp: float) -> float:
        """Calculate next music beat timing."""
        if self._beat_start_time == 0:
            self._beat_start_time = timestamp

        elapsed = timestamp - self._beat_start_time
        beats = int(elapsed / self.BEAT_INTERVAL_MS)
        next_beat_elapsed = (beats + 1) * self.BEAT_INTERVAL_MS

        return next_beat_elapsed - elapsed  # Time until next beat

    def _update_dance_state(self, timestamp: float) -> None:
        """Update dance sequence state."""
        if self._dance_state is None:
            self._dance_state = DanceSequence(
                is_active=True,
                current_step=0,
                total_steps=self.DANCE_STEPS_TOTAL,
                next_beat_ms=self.BEAT_INTERVAL_MS,
                accuracy_percent=100.0,
                reward_multiplier=1.0,
            )

        # Progress based on beat timing
        elapsed = timestamp - self._beat_start_time
        current_step = int(elapsed / self.BEAT_INTERVAL_MS) % self.DANCE_STEPS_TOTAL

        if self._dance_state:
            self._dance_state.current_step = current_step
            self._dance_state.next_beat_ms = self.BEAT_INTERVAL_MS - (elapsed % self.BEAT_INTERVAL_MS)

    def get_combat_strategy(
        self,
        status: NatlanBattleStatus,
        enemy_present: bool,
        timestamp: float | None = None,
    ) -> NatlanCombatStrategy:
        """Get combat strategy for Natlan zone.

        Args:
            status: Current battle status.
            enemy_present: Whether enemies are present.
            timestamp: Current time.

        Returns:
            NatlanCombatStrategy with recommendations.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        # Determine actions based on phase
        actions = self._determine_actions(status, enemy_present)

        # Calculate tribal bonus
        tribal_bonus = self._calculate_tribal_bonus(status)

        # Check ultimate readiness
        ultimate_ready = status.tribal_power_percent >= 0.9

        # Sync with beat
        beat_synced = self._is_beat_synced(status, now)

        # Build dance optimization if active
        dance_opt = self._dance_state if status.current_phase == NatlanPhase.DANCE_SEQUENCE else None

        return NatlanCombatStrategy(
            phase=status.current_phase,
            beat_synced=beat_synced,
            tribal_bonus=tribal_bonus,
            recommended_actions=tuple(actions),
            ultimate_ready=ultimate_ready,
            dance_optimization=dance_opt,
        )

    def _determine_actions(
        self,
        status: NatlanBattleStatus,
        enemy_present: bool,
    ) -> list[str]:
        """Determine recommended actions based on phase."""
        actions: list[str] = []

        if status.current_phase == NatlanPhase.DANCE_SEQUENCE:
            actions.append("follow_dance_beats")
            actions.append("sync_movements_to_music")
            actions.append("maintain_accuracy")
            return actions

        if status.is_ultimate_active:
            actions.append("max_damage_output")
            actions.append("use_ultimate_skills")
            actions.append("maintain_ult_duration")
            return actions

        if status.current_phase == NatlanPhase.BATTLE_MUSIC:
            actions.append("attack_on_beat")
            if status.nearby_tribesmen_count > 0:
                actions.append("coordinate_with_tribesmen")

        if enemy_present:
            actions.append("maintain_combat_pressure")
        else:
            actions.append("explore_and_collect")

        # Tribal power management
        if status.tribal_power_percent < 0.5:
            actions.append("build_tribal_power")
        elif status.tribal_power_percent >= 0.9:
            actions.append("prepare_ultimate")

        return actions

    def _calculate_tribal_bonus(self, status: NatlanBattleStatus) -> float:
        """Calculate bonus from tribal system."""
        base_bonus = 0.0

        # Base bonus from nearby tribesmen
        tribesmen_bonus = status.nearby_tribesmen_count * 0.1
        base_bonus += min(0.3, tribesmen_bonus)

        # Tribal power bonus
        power_bonus = status.tribal_power_percent * 0.2
        base_bonus += power_bonus

        # Music sync bonus
        if status.music_state != BattleMusicState.CALM:
            base_bonus += 0.1

        return min(1.0, base_bonus)

    def _is_beat_synced(self, status: NatlanBattleStatus, timestamp: float) -> bool:
        """Check if actions are synced to beat."""
        if status.music_beat_ms is None:
            return False

        # Within 100ms of beat is considered synced
        return status.music_beat_ms < 100 or status.music_beat_ms > (self.BEAT_INTERVAL_MS - 100)

    def record_dance_action(
        self,
        action: str,
        on_beat: bool,
        timestamp: float | None = None,
    ) -> float:
        """Record dance action and update accuracy.

        Args:
            action: Dance action performed.
            on_beat: Whether action was on beat.
            timestamp: Current time.

        Returns:
            Updated accuracy percentage.
        """
        if self._dance_state is None:
            return 100.0

        # Calculate accuracy adjustment
        if on_beat:
            self._dance_state.accuracy_percent = min(
                100.0,
                self._dance_state.accuracy_percent + 5.0
            )
            self._dance_state.reward_multiplier = min(
                2.0,
                self._dance_state.reward_multiplier + 0.1
            )
        else:
            self._dance_state.accuracy_percent = max(
                0.0,
                self._dance_state.accuracy_percent - 10.0
            )
            self._dance_state.reward_multiplier = max(
                0.5,
                self._dance_state.reward_multiplier - 0.2
            )

        return self._dance_state.accuracy_percent

    def get_beat_attack_window(
        self,
        status: NatlanBattleStatus,
        timestamp: float | None = None,
    ) -> tuple[bool, float]:
        """Get optimal attack window synced to beat.

        Returns:
            Tuple of (in_window, window_duration_ms).
        """
        if status.music_beat_ms is None:
            return (False, 0.0)

        # Attack window is 100ms before and after beat
        time_to_beat = status.music_beat_ms

        if time_to_beat < 100 or time_to_beat > (self.BEAT_INTERVAL_MS - 100):
            return (True, 200.0)  # 200ms window

        return (False, 0.0)

    def should_activate_ultimate(
        self,
        status: NatlanBattleStatus,
        enemy_health_percent: float | None = None,
    ) -> bool:
        """Determine if should activate ultimate form.

        Args:
            status: Current battle status.
            enemy_health_percent: Current enemy HP percentage.

        Returns:
            True if should activate ultimate.
        """
        # Must have enough tribal power
        if status.tribal_power_percent < 0.9:
            return False

        # Good timing: enemy at 30-50% health
        if enemy_health_percent is not None:
            if 0.3 <= enemy_health_percent <= 0.5:
                return True
            if enemy_health_percent > 0.7:
                return False  # Too early

        # Activate if power is full and enemies present
        return status.tribal_power_percent >= 1.0

    def reset(self) -> None:
        """Reset handler state."""
        self._phase_start_time = 0.0
        self._beat_start_time = 0.0
        self._current_status = None
        self._dance_state = None
        self._music_beats_detected = 0