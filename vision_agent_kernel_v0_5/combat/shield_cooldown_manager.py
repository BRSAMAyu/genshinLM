"""Shield ability tracking and proactive trigger decision making.

Implements C-40: Shield Cooldown Manager
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shield Ability Types
# ---------------------------------------------------------------------------

class ShieldType(Enum):
    ELEMENTAL = "elemental"         # Character-specific elemental shields
    CRYO = "cryo"
    PYRO = "pyro"
    ELECTRO = "electro"
    HYDRO = "hydro"
    GEO = "geo"
    DENDRO = "dendro"
    ANEMO = "anemo"
    PHYSICAL = "physical"          # Generic physical shield
    ULTIMATE = "ultimate"         # Burst-generated shields


# ---------------------------------------------------------------------------
# Shield Tracking Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ShieldAbility:
    character_name: str
    shield_type: ShieldType
    cooldown_sec: float
    duration_sec: float
    max_hits: int                 # Max hits the shield can absorb
    current_hits: int = 0
    remaining_hits: int = 0       # hits left
    is_active: bool = False


@dataclass(frozen=True, slots=True)
class ShieldTriggerDecision:
    action: Literal["activate", "wait", "save_for_burst"] = "wait"
    target_character: str = ""
    shield_type: ShieldType | None = None
    confidence: float = 0.0
    urgency: int = 10             # 0=immediate, higher=less urgent
    reason: str = ""


# ---------------------------------------------------------------------------
# C-40: Shield Ability Tracker
# ---------------------------------------------------------------------------

class ShieldAbilityTracker:
    """Tracks shield ability cooldowns and makes proactive trigger decisions.

    Features:
    - Track cooldowns for all shield-capable characters
    - Monitor active shield status
    - Proactive activation timing based on:
        - Incoming damage patterns
        - Burst windows where i-frames are needed
        - Elemental reaction timing
    - Decision: activate now, wait, or save for burst

    Usage:
        tracker = ShieldAbilityTracker()
        tracker.register_shield("Zhongli", ShieldType.GEO, cooldown=12.0, duration=20.0, hits=5)

        decision = tracker.evaluate(incoming_damage=0.8, boss_phase="aggressive", now=time.perf_counter())
    """

    # Thresholds for trigger decisions
    DAMAGE_THRESHOLD_HIGH = 0.7      # Immediate shield activation
    DAMAGE_THRESHOLD_MEDIUM = 0.4     # Consider activation
    BURST_WINDOW_BUFFER_SEC = 2.0    # Activate this many seconds before burst

    def __init__(self, now_fn=None) -> None:
        self._now_fn = now_fn or time.perf_counter
        self._shields: dict[str, ShieldAbility] = {}
        self._last_use_time: dict[str, float] = {}
        self._active_until: dict[str, float] = {}

    # ---------------------------------------------------------------------------
    # Properties
    # ---------------------------------------------------------------------------

    @property
    def shields(self) -> dict[str, ShieldAbility]:
        return self._shields.copy()

    @property
    def available_shields(self) -> list[str]:
        """List of characters with available shield abilities."""
        now = self._now_fn()
        return [
            name for name, shield in self._shields.items()
            if shield.cooldown_sec == 0 or
               now - self._last_use_time.get(name, -float('inf')) >= shield.cooldown_sec
        ]

    # ---------------------------------------------------------------------------
    # Shield Registration
    # ---------------------------------------------------------------------------

    def register_shield(
        self,
        character_name: str,
        shield_type: ShieldType,
        cooldown_sec: float,
        duration_sec: float,
        max_hits: int = 3,
    ) -> None:
        """Register a character's shield ability."""
        self._shields[character_name] = ShieldAbility(
            character_name=character_name,
            shield_type=shield_type,
            cooldown_sec=cooldown_sec,
            duration_sec=duration_sec,
            max_hits=max_hits,
            current_hits=0,
            remaining_hits=max_hits,
            is_active=False,
        )

    def unregister_shield(self, character_name: str) -> None:
        """Remove a character's shield registration."""
        self._shields.pop(character_name, None)
        self._last_use_time.pop(character_name, None)
        self._active_until.pop(character_name, None)

    # ---------------------------------------------------------------------------
    # Shield State Updates
    # ---------------------------------------------------------------------------

    def activate_shield(self, character_name: str, now: float | None = None) -> bool:
        """Mark a shield as activated."""
        now = now or self._now_fn()
        shield = self._shields.get(character_name)
        if shield is None:
            return False

        # Check cooldown
        last_used = self._last_use_time.get(character_name, -float('inf'))
        if now - last_used < shield.cooldown_sec:
            return False

        # Activate
        self._last_use_time[character_name] = now
        self._active_until[character_name] = now + shield.duration_sec

        # Update shield state
        active_shield = ShieldAbility(
            character_name=character_name,
            shield_type=shield.shield_type,
            cooldown_sec=shield.cooldown_sec,
            duration_sec=shield.duration_sec,
            max_hits=shield.max_hits,
            current_hits=0,
            remaining_hits=shield.max_hits,
            is_active=True,
        )
        self._shields[character_name] = active_shield

        log.info("Shield activated: %s (%s)", character_name, shield.shield_type.value)
        return True

    def record_hit(self, character_name: str) -> None:
        """Record a shield hit absorption."""
        shield = self._shields.get(character_name)
        if shield is None or not shield.is_active:
            return

        self._shields[character_name] = ShieldAbility(
            character_name=character_name,
            shield_type=shield.shield_type,
            cooldown_sec=shield.cooldown_sec,
            duration_sec=shield.duration_sec,
            max_hits=shield.max_hits,
            current_hits=shield.current_hits + 1,
            remaining_hits=shield.remaining_hits - 1,
            is_active=shield.remaining_hits > 1,
        )

    def expire_shield(self, character_name: str) -> None:
        """Manually expire a shield."""
        if character_name in self._shields:
            shield = self._shields[character_name]
            self._shields[character_name] = ShieldAbility(
                character_name=character_name,
                shield_type=shield.shield_type,
                cooldown_sec=shield.cooldown_type,
                duration_sec=shield.duration_sec,
                max_hits=shield.max_hits,
                current_hits=shield.current_hits,
                remaining_hits=0,
                is_active=False,
            )
        self._active_until.pop(character_name, None)

    # ---------------------------------------------------------------------------
    # Evaluation
    # ---------------------------------------------------------------------------

    def evaluate(
        self,
        incoming_damage: float,            # 0.0-1.0 damage threat level
        boss_phase: str = "normal",
        now: float | None = None,
        target_character: str | None = None,
    ) -> ShieldTriggerDecision:
        """Evaluate whether to activate a shield ability.

        Args:
            incoming_damage: Estimated damage threat (0.0-1.0).
            boss_phase: Current boss phase for context.
            now: Current timestamp.
            target_character: Preferred character to use (None = best available).

        Returns:
            ShieldTriggerDecision with action recommendation.
        """
        now = now or self._now_fn()

        # Get available shields
        available = self._get_available_shields(now)
        if not available:
            return ShieldTriggerDecision(
                action="wait",
                reason="no_shields_available",
                confidence=1.0,
                urgency=10,
            )

        # Select target character
        if target_character and target_character in available:
            selected = target_character
        else:
            selected = self._select_best_shield(available, incoming_damage, boss_phase)

        if selected is None:
            return ShieldTriggerDecision(action="wait", reason="no_suitable_shield")

        shield = self._shields[selected]

        # High damage = immediate activation
        if incoming_damage >= self.DAMAGE_THRESHOLD_HIGH:
            return ShieldTriggerDecision(
                action="activate",
                target_character=selected,
                shield_type=shield.shield_type,
                confidence=0.9,
                urgency=0,
                reason=f"high_damage_{incoming_damage:.0%}",
            )

        # Burst window consideration
        if boss_phase in ("stunned", "enraged"):
            return ShieldTriggerDecision(
                action="activate",
                target_character=selected,
                shield_type=shield.shield_type,
                confidence=0.85,
                urgency=3,
                reason=f"burst_window_{boss_phase}",
            )

        # Medium damage = consider activation
        if incoming_damage >= self.DAMAGE_THRESHOLD_MEDIUM:
            # Activate if shield has high remaining hits
            if shield.remaining_hits >= shield.max_hits // 2:
                return ShieldTriggerDecision(
                    action="activate",
                    target_character=selected,
                    shield_type=shield.shield_type,
                    confidence=0.7,
                    urgency=5,
                    reason=f"medium_damage_preemptive",
                )
            else:
                return ShieldTriggerDecision(
                    action="save_for_burst",
                    target_character=selected,
                    shield_type=shield.shield_type,
                    confidence=0.6,
                    urgency=7,
                    reason="conserve_for_burst",
                )

        # Low damage = wait
        return ShieldTriggerDecision(
            action="wait",
            target_character=selected,
            shield_type=shield.shield_type,
            confidence=0.5,
            urgency=10,
            reason="low_threat",
        )

    def _get_available_shields(self, now: float) -> list[str]:
        """Get list of characters with ready shields."""
        available = []
        for name, shield in self._shields.items():
            last_used = self._last_use_time.get(name, -float('inf'))
            if now - last_used >= shield.cooldown_sec:
                # Also check if shield is not currently active with no hits left
                active_until = self._active_until.get(name, 0)
                if now < active_until:
                    # Shield is active, check if it has hits remaining
                    if shield.remaining_hits > 0:
                        available.append(name)
                else:
                    available.append(name)
        return available

    def _select_best_shield(
        self,
        available: list[str],
        incoming_damage: float,
        boss_phase: str,
    ) -> str | None:
        """Select the best shield for current situation."""
        if not available:
            return None

        def shield_score(name: str) -> float:
            shield = self._shields[name]
            score = 0.0

            # Prefer shields with more remaining hits
            score += shield.remaining_hits * 10

            # Prefer shorter cooldowns for reactive play
            score += (60 - shield.cooldown_sec) * 0.5

            # Prefer longer duration for sustained fights
            score += shield.duration_sec * 0.1

            # Elemental shield bonuses (can counter certain enemies)
            # This is a simplified version - could be expanded with enemy info
            if shield.shield_type == ShieldType.GEO:
                score += 5  # Universal good shield

            return score

        return max(available, key=shield_score, default=None)

    # ---------------------------------------------------------------------------
    # Reset
    # ---------------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all shield tracking state."""
        self._shields.clear()
        self._last_use_time.clear()
        self._active_until.clear()

    def reset_character(self, character_name: str) -> None:
        """Reset tracking for a specific character."""
        self._last_use_time.pop(character_name, None)
        self._active_until.pop(character_name, None)
        if character_name in self._shields:
            shield = self._shields[character_name]
            self._shields[character_name] = ShieldAbility(
                character_name=character_name,
                shield_type=shield.shield_type,
                cooldown_sec=shield.cooldown_sec,
                duration_sec=shield.duration_sec,
                max_hits=shield.max_hits,
                current_hits=0,
                remaining_hits=shield.max_hits,
                is_active=False,
            )