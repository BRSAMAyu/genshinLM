"""Flanking and positioning system (C-07).

Provides intelligent flanking and positioning for combat scenarios where:
- Elemental shields block frontal damage (木盾/冰盾丘丘暴徒)
- Back-attack provides ~10% CRIT rate bonus
- Boss mechanics require specific positioning (e.g., behind Dvalin during spine break)

Not a full pathfinding engine — delegates actual movement to the existing
NavigationController via StateBus navigation_signal or direct semantic execution.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class PositionStrategy(str, Enum):
    """Combat positioning strategies."""
    AGGRESSIVE_FRONT = "aggressive_front"    # Face-to-face, direct assault
    FLANK_LEFT = "flank_left"               # Circle to enemy's left side
    FLANK_RIGHT = "flank_right"            # Circle to enemy's right side
    FLANK_REAR = "flank_rear"              # Go behind enemy (for shields)
    STALK_REAR = "stalk_rear"             # Maintain rear position (back-attack bonus)
    KITE_AROUND = "kite_around"           # Continuous repositioning
    HOLD_GROUND = "hold_ground"           # Keep current position
    PHASE_BURST = "phase_burst"           # Sprint to burst position during stun window


@dataclass(frozen=True, slots=True)
class FlankingContext:
    """Context for flanking decision-making."""
    enemy_name: str = ""
    enemy_type: str = "" # "mitachurl_wood", "mitachurl_ice", "abyss_mage"
    has_shield: bool = False
    shield_element: str = "" # "Pyro", "Cryo", "Hydro", etc.
    shield_broken: bool = False
    is_staggered: bool = False
    is_boss: bool = False
    boss_phase: str = ""
    in_stun_window: bool = False
    stun_window_remaining_sec: float = 0.0
    front_blocked: bool = False # True when shield blocks frontal attacks
    distance_to_enemy: float = 0.0       # Estimated world units
    facing_away: bool = False             # Enemy facing away from character


@dataclass(slots=True)
class FlankingState:
    """Runtime state for the flanking system."""
    current_strategy: PositionStrategy = PositionStrategy.AGGRESSIVE_FRONT
    last_strategy_change_sec: float = 0.0
    strategy_streak: int = 0               # Consecutive frames using same strategy
    rear_achieved: bool = False
    flank_attempts: int = 0
    max_flank_attempts: int = 3


@dataclass(frozen=True, slots=True)
class FlankingAction:
    """A computed flanking action to execute."""
    action_type: str                      # "move_left", "move_right", "sprint_back", "circles"
    reason: str = ""
    urgency: float = 1.0                 # 0.0-1.0, higher = more urgent
    duration_sec: float = 0.5
    target_strategy: PositionStrategy = PositionStrategy.AGGRESSIVE_FRONT


class FlankingPolicy:
    """Decide the best positioning strategy based on combat context.

    Evaluates enemy type, shield state, stun windows, and boss mechanics
    to select the optimal positioning strategy.
    """

    # Shield types that require flanking (frontal damage heavily reduced)
    FLANK_REQUIRED_SHIELDS: frozenset[str] = frozenset({
        "wood", "ice", "rock", "wooden", "wood_shield",
    })

    # Map shield element names to the FLANK_REQUIRED_SHIELDS keys
    _ELEMENT_TO_SHIELD: dict[str, str] = {
        "cryo": "ice",
        "pyro": "wood",   # burning
        "electro": "ice", # similar frontal issue
        "hydro": "ice",
    }

    # Bosses with known rear-positioning mechanics
    REAR_POSITIVE_BOSSES: frozenset[str] = frozenset({
        "dvalin", "windy",        # Rear for spine break
        "wolf", "lord_of_fire",  # Rear attack bonus
    })

    # Elements that bypass shields (used to decide if flanking can be skipped)
    SHIELD_BYPASS_ELEMENTS: frozenset[str] = frozenset({
        "pyro", "cryo", "electro", "hydro", "anemo", "geo", "dendro",
    })

    def decide(
        self, ctx: FlankingContext, state: FlankingState,
    ) -> PositionStrategy:
        """Decide the optimal positioning strategy."""
        now = time.perf_counter()

        # Priority 1: Stun window — sprint to burst position
        if ctx.in_stun_window and ctx.stun_window_remaining_sec > 0.5:
            return PositionStrategy.PHASE_BURST

        # Priority 2: Shield management
        if ctx.has_shield and not ctx.shield_broken:
            shield_lower = ctx.shield_element.lower()
            if shield_lower in self.FLANK_REQUIRED_SHIELDS:
                # Direct match (wood, ice, rock)
                return PositionStrategy.FLANK_REAR
            if self._ELEMENT_TO_SHIELD.get(shield_lower, "") in self.FLANK_REQUIRED_SHIELDS:
                # Element → shield type mapping
                return PositionStrategy.FLANK_LEFT

        # Priority 3: Boss positioning requirements
        if ctx.is_boss:
            boss_lower = ctx.enemy_name.lower()
            if boss_lower in self.REAR_POSITIVE_BOSSES:
                if ctx.boss_phase == "stunned":
                    return PositionStrategy.PHASE_BURST
                return PositionStrategy.STALK_REAR

        # Priority 4: Already flanking — maintain until stable
        if state.current_strategy in (PositionStrategy.FLANK_REAR, PositionStrategy.STALK_REAR):
            if state.rear_achieved:
                return PositionStrategy.STALK_REAR
            return PositionStrategy.FLANK_REAR

        # Priority 5: Boss staggered — aggressive rear burst
        if ctx.is_staggered:
            return PositionStrategy.PHASE_BURST

        # Default: kite around for repositioning flexibility
        return PositionStrategy.KITE_AROUND

    def is_flanking_required(self, ctx: FlankingContext) -> bool:
        """Quick check: does the current situation require flanking?"""
        if ctx.has_shield and not ctx.shield_broken:
            shield_lower = ctx.shield_element.lower()
            if shield_lower in self.FLANK_REQUIRED_SHIELDS:
                return True
            # Also check element → shield type mapping
            mapped = self._ELEMENT_TO_SHIELD.get(shield_lower, "")
            if mapped in self.FLANK_REQUIRED_SHIELDS:
                return True
        if ctx.is_boss and ctx.enemy_name.lower() in self.REAR_POSITIVE_BOSSES:
            return True
        return False


class FlankingNavigator:
    """Compute and execute flanking movement.

    Does NOT directly control the camera or character movement — instead
    emits semantic actions that are consumed by the existing movement system
    (NavigationController / CharacterMoveSkill / combat backend).
    """

    def __init__(self, semantic_executor: Any | None = None) -> None:
        self._executor = semantic_executor
        self._policy = FlankingPolicy()

    def compute_action(
        self, strategy: PositionStrategy, ctx: FlankingContext,
    ) -> FlankingAction:
        """Compute the next flanking action for the given strategy."""
        if strategy == PositionStrategy.FLANK_REAR:
            return FlankingAction(
                action_type="move_back_then_circles_left",
                reason=f"flank_rear for {ctx.enemy_name} shield",
                urgency=0.9,
                duration_sec=1.5,
                target_strategy=PositionStrategy.FLANK_REAR,
            )
        if strategy == PositionStrategy.STALK_REAR:
            return FlankingAction(
                action_type="adjust_to_rear",
                reason="maintain rear position for back-attack bonus",
                urgency=0.5,
                duration_sec=0.8,
                target_strategy=PositionStrategy.STALK_REAR,
            )
        if strategy == PositionStrategy.FLANK_LEFT:
            return FlankingAction(
                action_type="circles_left",
                reason=f"circle left around {ctx.enemy_name}",
                urgency=0.7,
                duration_sec=1.0,
                target_strategy=PositionStrategy.FLANK_LEFT,
            )
        if strategy == PositionStrategy.FLANK_RIGHT:
            return FlankingAction(
                action_type="circles_right",
                reason=f"circle right around {ctx.enemy_name}",
                urgency=0.7,
                duration_sec=1.0,
                target_strategy=PositionStrategy.FLANK_RIGHT,
            )
        if strategy == PositionStrategy.PHASE_BURST:
            return FlankingAction(
                action_type="sprint_to_rear",
                reason=f"burst window ({ctx.stun_window_remaining_sec:.1f}s remaining)",
                urgency=1.0,
                duration_sec=0.5,
                target_strategy=PositionStrategy.PHASE_BURST,
            )
        if strategy == PositionStrategy.KITE_AROUND:
            return FlankingAction(
                action_type="reposition",
                reason="maintain repositioning flexibility",
                urgency=0.4,
                duration_sec=0.6,
                target_strategy=PositionStrategy.KITE_AROUND,
            )
        # Default: aggressive front
        return FlankingAction(
            action_type="advance",
            reason="advance to frontal assault",
            urgency=0.3,
            duration_sec=0.5,
            target_strategy=PositionStrategy.AGGRESSIVE_FRONT,
        )

    def execute_action(
        self, action: FlankingAction, backend: Any | None = None,
    ) -> bool:
        """Execute a flanking action via the backend."""
        exec_backend = backend or self._executor
        if exec_backend is None:
            log.warning("[FlankingNavigator] no backend to execute flanking action")
            return False

        action_type = action.action_type
        try:
            if action_type == "move_back_then_circles_left":
                # Back up, then strafe left behind enemy
                exec_backend.key_press("S", reason="flank_rear_back_up")
                exec_backend.key_press("A", reason="flank_rear_circle_left")
            elif action_type == "circles_left":
                exec_backend.key_press("A", reason="flank_circle_left")
            elif action_type == "circles_right":
                exec_backend.key_press("D", reason="flank_circle_right")
            elif action_type == "sprint_to_rear":
                exec_backend.key_down("LShift", reason="sprint_start")
                exec_backend.key_press("S", reason="sprint_rear")
                exec_backend.key_up("LShift", reason="sprint_end")
            elif action_type == "adjust_to_rear":
                exec_backend.key_press("A", reason="adjust_rear_left")
            elif action_type == "reposition":
                exec_backend.key_press("D", reason="reposition_right")
            elif action_type == "advance":
                exec_backend.key_press("W", reason="advance_front")
            return True
        except Exception as exc:
            log.warning("[FlankingNavigator] execute failed: %s", exc)
            return False

    def update_state(
        self, strategy: PositionStrategy, state: FlankingState,
    ) -> None:
        """Update runtime flanking state after a strategy change."""
        now = time.perf_counter()
        if strategy == state.current_strategy:
            state.strategy_streak += 1
        else:
            state.current_strategy = strategy
            state.last_strategy_change_sec = now
            state.strategy_streak = 0

    def build_flanking_context(
        self,
        enemy_name: str = "",
        enemy_type: str = "",
        shield_element: str = "",
        shield_broken: bool = False,
        is_staggered: bool = False,
        is_boss: bool = False,
        boss_phase: str = "",
        stun_window_remaining_sec: float = 0.0,
        front_blocked: bool = False,
        distance_to_enemy: float = 5.0,
    ) -> FlankingContext:
        """Build a FlankingContext from raw detection data."""
        has_shield = bool(shield_element and not shield_broken)
        return FlankingContext(
            enemy_name=enemy_name,
            enemy_type=enemy_type,
            has_shield=has_shield,
            shield_element=shield_element,
            shield_broken=shield_broken,
            is_staggered=is_staggered,
            is_boss=is_boss,
            boss_phase=boss_phase,
            in_stun_window=stun_window_remaining_sec > 0,
            stun_window_remaining_sec=stun_window_remaining_sec,
            front_blocked=front_blocked,
            distance_to_enemy=distance_to_enemy,
        )


class FlankingIntegration:
    """Integrate flanking system into combat rotation runners.

    This class bridges the FlankingPolicy/FlankingNavigator to the existing
    combat rotation system. It is NOT a standalone executor — it is called
    by the combat rotation runner between skill uses.
    """

    def __init__(
        self,
        semantic_executor: Any | None = None,
        backend: Any | None = None,
    ) -> None:
        self._nav = FlankingNavigator(semantic_executor)
        self._policy = FlankingPolicy()
        self._state = FlankingState()
        self._backend = backend

    def evaluate_and_execute(
        self, ctx: FlankingContext,
    ) -> tuple[bool, str]:
        """Evaluate flanking need and execute if required.

        Returns (executed, strategy) — executed=True if an action was taken.
        """
        strategy = self._policy.decide(ctx, self._state)

        # Only act if strategy changed or high urgency
        if strategy != self._state.current_strategy or strategy == PositionStrategy.PHASE_BURST:
            action = self._nav.compute_action(strategy, ctx)
            if action.urgency >= 0.7 or strategy == PositionStrategy.PHASE_BURST:
                ok = self._nav.execute_action(action, self._backend)
                self._nav.update_state(strategy, self._state)
                return ok, strategy.value

        return False, self._state.current_strategy.value

    def get_current_strategy(self) -> str:
        return self._state.current_strategy.value