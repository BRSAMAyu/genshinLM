"""Special movement controllers: climbing, swimming, gliding, sprinting, elemental sight.

Handles N-07 through N-14 capability requirements:
- N-07: Climbing control with stamina management
- N-08: Swimming/diving (surface + Fontaine underwater)
- N-09: Gliding control (takeoff, direction, landing)
- N-10: Sprint stamina management (prevent exhaustion)
- N-11: Elemental sight usage
- N-12: Vehicle/transformation (Natlan Saurian, Four-Leaf Sigil)
- N-13: Underground navigation (multi-layer map)
- N-14: Environmental hazard avoidance

Integrates with:
- navigation/genshin_navigator.py for pathfinding
- perception/genshin_visual_detectors.py for stamina/environment state
- control/camera_servo.py for camera control
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


class MovementMode(str, Enum):
    WALKING = "walking"
    CLIMBING = "climbing"
    SWIMMING = "swimming"
    DIVING = "diving"          # Fontaine underwater
    GLIDING = "gliding"
    SPRINTING = "sprinting"
    ELEMENTAL_SIGHT = "elemental_sight"
    VEHICLE = "vehicle"        # Saurian/Waverider


class EnvironmentHazardType(str, Enum):
    NONE = "none"
    SHEER_COLD = "sheer_cold"
    BALETHUNDER = "balethunder"
    PHLOGISTON = "phlogiston"
    DARKNESS = "darkness"      # Enkanomiya/Chasm


@dataclass(slots=True)
class StaminaBudget:
    """Stamina management state for movement actions."""
    current_ratio: float = 1.0
    is_visible: bool = False
    reserve_threshold: float = 0.2      # Stop spending at this level
    recovery_threshold: float = 0.8     # Resume spending at this level

    @property
    def can_spend(self) -> bool:
        return self.current_ratio > self.reserve_threshold

    @property
    def should_recover(self) -> bool:
        return self.current_ratio < self.recovery_threshold


@dataclass(slots=True)
class ClimbingState:
    """State tracking for climbing segments."""
    is_climbing: bool = False
    direction: str = "up"               # "up", "left", "right", "down"
    stamina: StaminaBudget = field(default_factory=StaminaBudget)
    wall_detected: bool = False
    height_gained: float = 0.0
    target_height: float = 0.0
    is_exhausted: bool = False


@dataclass(slots=True)
class SwimmingState:
    """State tracking for swimming/diving."""
    is_swimming: bool = False
    is_diving: bool = False              # Fontaine underwater
    direction: tuple[float, float] = (0.0, 0.0)
    stamina: StaminaBudget = field(default_factory=StaminaBudget)
    is_exhausted: bool = False
    underwater_stamina_separate: bool = False  # Fontaine uses different stamina


@dataclass(slots=True)
class GlidingState:
    """State tracking for gliding."""
    is_gliding: bool = False
    target_direction: tuple[float, float] = (0.0, 0.0)
    altitude: float = 0.0
    target_altitude: float = 0.0
    should_land: bool = False
    thermal_updraft: bool = False


@dataclass(slots=True)
class ElementalSightState:
    """State for elemental vision mode."""
    is_active: bool = False
    objects_detected: list[tuple[float, float, str]] = field(default_factory=list)
    scan_complete: bool = False


@dataclass(slots=True)
class VehicleState:
    """State for special movement vehicles/transformations."""
    vehicle_type: str = ""               # "saurian", "waverider", "four_leaf_sigil"
    is_active: bool = False
    ability_cooldown: float = 0.0
    movement_speed: float = 1.0


@dataclass(slots=True)
class UndergroundState:
    """State for underground/cave navigation."""
    is_underground: bool = False
    layer: int = 0                       # 0=overworld, 1=surface cave, 2=deep
    has_map: bool = False
    light_source_active: bool = False


@dataclass(slots=True)
class MovementDecision:
    """Output decision from special movement controller."""
    action: str              # "move", "stop", "recover", "climb", "swim", "glide",
                             # "land", "surface", "dive", "use_sight", "use_vehicle",
                             # "retreat", "warm_up"
    keys: tuple[str, ...] = ()
    duration_ms: int = 100
    reason: str = ""


def _direction_to_keys(direction: tuple[float, float]) -> tuple[str, ...]:
    """Convert a (dx, dy) direction vector to WASD keys."""
    dx, dy = direction
    keys: list[str] = []
    if dy < -0.3:
        keys.append("w")
    elif dy > 0.3:
        keys.append("s")
    if dx < -0.3:
        keys.append("a")
    elif dx > 0.3:
        keys.append("d")
    return tuple(keys) if keys else ("w",)


class ClimbingController:
    """Controls climbing movement with stamina management (N-07).

    Manages direction, pace, and stamina to prevent falling.
    Alternates between climbing and resting to maintain stamina reserve.
    """

    def __init__(self, stamina_reserve: float = 0.25) -> None:
        self._state = ClimbingState(stamina=StaminaBudget(reserve_threshold=stamina_reserve))

    @property
    def state(self) -> ClimbingState:
        return self._state

    def start_climbing(self, direction: str = "up") -> MovementDecision:
        self._state.is_climbing = True
        self._state.direction = direction
        return MovementDecision("climb", keys=self._direction_to_keys(direction),
                                duration_ms=200, reason="start_climbing")

    def update(self, stamina_ratio: float, is_visible: bool,
               wall_ahead: bool, at_top: bool) -> MovementDecision:
        self._state.stamina.current_ratio = stamina_ratio
        self._state.stamina.is_visible = is_visible
        self._state.wall_detected = wall_ahead

        if at_top:
            self._state.is_climbing = False
            self._state.is_exhausted = False
            return MovementDecision("move", keys=("w",), duration_ms=100,
                                    reason="reached_top")

        if not self._state.stamina.can_spend or stamina_ratio < 0.15:
            self._state.is_exhausted = True
            return MovementDecision("recover", keys=(), duration_ms=2000,
                                    reason=f"stamina_low_{stamina_ratio:.0%}")

        if self._state.is_exhausted:
            if stamina_ratio > 0.6:
                self._state.is_exhausted = False
            else:
                return MovementDecision("recover", keys=(), duration_ms=2000,
                                        reason=f"recovering_{stamina_ratio:.0%}")

        if not wall_ahead:
            return MovementDecision("move", keys=("w",), duration_ms=200,
                                    reason="no_wall_advance")

        self._state.is_climbing = True
        return MovementDecision("climb", keys=self._direction_to_keys(self._state.direction),
                                duration_ms=200, reason="climbing")

    def _direction_to_keys(self, direction: str) -> tuple[str, ...]:
        return {"up": ("w",), "down": ("s",), "left": ("a",), "right": ("d",)}.get(
            direction, ("w",)
        )


class SwimmingController:
    """Controls swimming and diving movement (N-08).

    Surface swimming uses normal stamina. Fontaine underwater diving
    uses a separate stamina gauge.
    """

    def __init__(self) -> None:
        self._state = SwimmingState()

    @property
    def state(self) -> SwimmingState:
        return self._state

    def start_swimming(self, direction: tuple[float, float]) -> MovementDecision:
        self._state.is_swimming = True
        self._state.is_diving = False
        self._state.direction = direction
        return MovementDecision("swim", keys=_direction_to_keys(direction),
                                duration_ms=200, reason="start_swimming")

    def start_diving(self) -> MovementDecision:
        self._state.is_diving = True
        self._state.is_swimming = False
        return MovementDecision("dive", keys=("ctrl",), duration_ms=100,
                                reason="start_diving")

    def surface(self) -> MovementDecision:
        self._state.is_diving = False
        self._state.is_swimming = True
        return MovementDecision("surface", keys=("space",), duration_ms=100,
                                reason="surface")

    def update(self, stamina_ratio: float, is_underwater: bool,
               target_direction: tuple[float, float],
               near_shore: bool = False) -> MovementDecision:
        self._state.stamina.current_ratio = stamina_ratio

        if near_shore:
            self._state.is_swimming = False
            self._state.is_diving = False
            return MovementDecision("move", keys=("w",), duration_ms=200,
                                    reason="reached_shore")

        if not self._state.stamina.can_spend and not is_underwater:
            self._state.is_exhausted = True
            return MovementDecision("recover", keys=(), duration_ms=2000,
                                    reason="swim_stamina_low")

        self._state.direction = target_direction
        action = "swim" if not is_underwater else "dive"
        self._state.is_swimming = not is_underwater
        self._state.is_diving = is_underwater

        return MovementDecision(action, keys=_direction_to_keys(target_direction),
                                duration_ms=200, reason=f"{action}_towards_target")


class GlidingController:
    """Controls gliding movement (N-09).

    Manages takeoff, directional control, altitude, and landing.
    """

    def __init__(self) -> None:
        self._state = GlidingState()

    @property
    def state(self) -> GlidingState:
        return self._state

    def takeoff(self) -> MovementDecision:
        self._state.is_gliding = True
        return MovementDecision("glide", keys=("space",), duration_ms=200,
                                reason="takeoff")

    def land(self) -> MovementDecision:
        self._state.is_gliding = False
        return MovementDecision("land", keys=(), duration_ms=100,
                                reason="landing")

    def update(self, is_airborne: bool, target_direction: tuple[float, float],
               altitude: float, near_ground: bool) -> MovementDecision:
        self._state.is_gliding = is_airborne
        self._state.altitude = altitude
        self._state.target_direction = target_direction

        if not is_airborne:
            self._state.is_gliding = False
            return MovementDecision("move", keys=("w",), duration_ms=100,
                                    reason="grounded")

        if near_ground and altitude < 5.0:
            self._state.should_land = True
            return self.land()

        return MovementDecision("glide",
                                keys=_direction_to_keys(target_direction),
                                duration_ms=200, reason="gliding_towards_target")


class SprintManager:
    """Manages sprint stamina budget to prevent exhaustion (N-10).

    Ensures stamina is available for critical actions (dodging, climbing)
    by maintaining a reserve during overworld sprinting.
    """

    def __init__(self, reserve_ratio: float = 0.3) -> None:
        self._reserve = reserve_ratio
        self._stamina = StaminaBudget(reserve_threshold=reserve_ratio,
                                      recovery_threshold=reserve_ratio + 0.3)

    def should_sprint(self, stamina_ratio: float, danger_level: float = 0.0) -> bool:
        if danger_level > 0.5:
            return False  # Save stamina for dodging
        return stamina_ratio > self._reserve + 0.1

    def update(self, stamina_ratio: float, in_combat: bool,
               near_obstacle: bool) -> MovementDecision:
        self._stamina.current_ratio = stamina_ratio

        if in_combat or near_obstacle:
            return MovementDecision("move", keys=("w",), duration_ms=100,
                                    reason="no_sprint_save_stamina")

        if self.should_sprint(stamina_ratio):
            return MovementDecision("move", keys=("w", "shift"), duration_ms=200,
                                    reason="sprinting")

        if self._stamina.should_recover:
            return MovementDecision("move", keys=("w",), duration_ms=200,
                                    reason="walk_to_recover_stamina")

        return MovementDecision("move", keys=("w",), duration_ms=100,
                                reason="walking")


class ElementalSightController:
    """Controls elemental vision mode for finding hidden objects (N-11).

    Toggles elemental sight and scans for highlighted interactables.
    """

    def __init__(self) -> None:
        self._state = ElementalSightState()

    @property
    def state(self) -> ElementalSightState:
        return self._state

    def activate(self) -> MovementDecision:
        self._state.is_active = True
        self._state.scan_complete = False
        return MovementDecision("use_sight", keys=("mouse_middle_hold",),
                                duration_ms=2000, reason="activate_elemental_sight")

    def deactivate(self) -> MovementDecision:
        self._state.is_active = False
        self._state.scan_complete = True
        return MovementDecision("move", keys=(), duration_ms=100,
                                reason="deactivate_sight")

    def detect_objects(self, highlighted_positions: list[tuple[float, float, str]],
                       ) -> list[tuple[float, float, str]]:
        """Record objects found during elemental sight scan."""
        self._state.objects_detected = highlighted_positions
        return highlighted_positions


class VehicleController:
    """Handles special vehicles and transformations (N-12).

    Natlan Saurian possession, Waverider, Four-Leaf Sigil grappling.
    """

    def __init__(self) -> None:
        self._state = VehicleState()

    @property
    def state(self) -> VehicleState:
        return self._state

    def activate_vehicle(self, vehicle_type: str) -> MovementDecision:
        self._state.vehicle_type = vehicle_type
        self._state.is_active = True
        return MovementDecision("use_vehicle", keys=("f",), duration_ms=500,
                                reason=f"activate_{vehicle_type}")

    def deactivate(self) -> MovementDecision:
        self._state.is_active = False
        return MovementDecision("move", keys=(), duration_ms=100,
                                reason="exit_vehicle")

    def use_ability(self) -> MovementDecision:
        if self._state.ability_cooldown > 0:
            return MovementDecision("wait", keys=(), duration_ms=500,
                                    reason="ability_on_cooldown")
        self._state.ability_cooldown = 5.0
        return MovementDecision("use_vehicle", keys=("e",), duration_ms=300,
                                reason=f"use_{self._state.vehicle_type}_ability")

    def update_cooldown(self, dt: float) -> None:
        self._state.ability_cooldown = max(0, self._state.ability_cooldown - dt)


# Four-Leaf Sigil positions (region → list of sigil positions)
FOUR_LEAF_SIGIL_POSITIONS: dict[str, list[tuple[float, float, float]]] = {
    "sumeru": [],
    "fontaine": [],
}


class UndergroundNavigator:
    """Navigates underground/cave areas with multi-layer support (N-13).

    Manages cave entry/exit, layer tracking, and darkness handling.
    """

    def __init__(self) -> None:
        self._state = UndergroundState()

    @property
    def state(self) -> UndergroundState:
        return self._state

    def enter_underground(self, layer: int = 1) -> MovementDecision:
        self._state.is_underground = True
        self._state.layer = layer
        return MovementDecision("move", keys=("w",), duration_ms=200,
                                reason=f"enter_underground_layer_{layer}")

    def exit_underground(self) -> MovementDecision:
        self._state.is_underground = False
        self._state.layer = 0
        return MovementDecision("move", keys=("w",), duration_ms=200,
                                reason="exit_to_overworld")

    def change_layer(self, target_layer: int) -> MovementDecision:
        self._state.layer = target_layer
        return MovementDecision("move", keys=("w",), duration_ms=200,
                                reason=f"descend_to_layer_{target_layer}")

    def activate_light(self) -> MovementDecision:
        self._state.light_source_active = True
        return MovementDecision("move", keys=(), duration_ms=100,
                                reason="activate_light_source")


# Warm-up locations per hazard type
_HAZARD_SHELTERS: dict[EnvironmentHazardType, list[str]] = {
    EnvironmentHazardType.SHEER_COLD: [
        "statue_of_seven", "teleport_waypoint", "warming_seelie",
        "scarlet_quartz", "ruins_torch", "goulash",
    ],
    EnvironmentHazardType.BALETHUNDER: [
        "statue_of_seven", "electro_crystal", "thunder_barrier_exit",
    ],
    EnvironmentHazardType.PHLOGISTON: [
        "phlogiston_fountain", "statue_of_seven", "tribal_bonfire",
    ],
    EnvironmentHazardType.DARKNESS: [
        "ruin_brazier", "lumenstone_charge", "statue_of_seven",
    ],
}


class EnvironmentHazardAvoidance:
    """Avoids environmental hazards during navigation (N-14).

    Monitors environment gauges and triggers retreat/recovery
    when hazard levels become dangerous.
    """

    def __init__(self) -> None:
        self._current_hazard = EnvironmentHazardType.NONE
        self._hazard_level: float = 0.0

    @property
    def current_hazard(self) -> EnvironmentHazardType:
        return self._current_hazard

    @property
    def hazard_level(self) -> float:
        return self._hazard_level

    def update(self, gauge_type: str, hazard_level: float) -> MovementDecision:
        """Update hazard state from perception EnvironmentGauge."""
        self._hazard_level = hazard_level
        try:
            self._current_hazard = EnvironmentHazardType(gauge_type)
        except ValueError:
            self._current_hazard = EnvironmentHazardType.NONE
            return MovementDecision("move", keys=("w",), duration_ms=100,
                                    reason="no_hazard")

        if gauge_type == "none":
            return MovementDecision("move", keys=("w",), duration_ms=100,
                                    reason="no_hazard")

        if hazard_level > 0.85:
            return MovementDecision("retreat", keys=(), duration_ms=100,
                                    reason=f"critical_{gauge_type}")

        if hazard_level > 0.6:
            shelters = _HAZARD_SHELTERS.get(self._current_hazard, [])
            nearest = shelters[0] if shelters else "statue_of_seven"
            return MovementDecision("warm_up", keys=(), duration_ms=100,
                                    reason=f"seeking_{nearest}")

        return MovementDecision("move", keys=("w",), duration_ms=100,
                                reason=f"low_{gauge_type}_safe_to_proceed")

    def get_nearest_shelter(self) -> str:
        shelters = _HAZARD_SHELTERS.get(self._current_hazard, [])
        return shelters[0] if shelters else "statue_of_seven"


class SpecialMovementController:
    """Unified controller that manages all special movement modes.

    Delegates to specific controllers based on current movement mode.
    Integrates with existing navigation and perception systems.
    """

    def __init__(self) -> None:
        self.climbing = ClimbingController()
        self.swimming = SwimmingController()
        self.gliding = GlidingController()
        self.sprint = SprintManager()
        self.elemental_sight = ElementalSightController()
        self.vehicle = VehicleController()
        self.underground = UndergroundNavigator()
        self.hazard_avoidance = EnvironmentHazardAvoidance()

    def detect_mode(self, is_climbing: bool, is_swimming: bool,
                    is_airborne: bool, is_underground: bool,
                    stamina_visible: bool) -> MovementMode:
        """Detect current movement mode from screen state indicators."""
        if is_climbing:
            return MovementMode.CLIMBING
        if is_airborne and stamina_visible:
            return MovementMode.GLIDING
        if is_swimming:
            return MovementMode.SWIMMING
        if is_underground:
            return MovementMode.WALKING
        return MovementMode.WALKING

    def evaluate(self, mode: MovementMode, **kwargs: float | bool | str) -> MovementDecision:
        """Evaluate current movement state and return action decision."""
        # Priority: environmental hazard overrides everything
        if self.hazard_avoidance.current_hazard != EnvironmentHazardType.NONE:
            if self.hazard_avoidance.hazard_level > 0.6:
                return self.hazard_avoidance.update(
                    self.hazard_avoidance.current_hazard.value,
                    self.hazard_avoidance.hazard_level,
                )

        if mode == MovementMode.CLIMBING:
            return self.climbing.update(
                stamina_ratio=kwargs.get("stamina_ratio", 1.0),  # type: ignore[arg-type]
                is_visible=kwargs.get("stamina_visible", False),  # type: ignore[arg-type]
                wall_ahead=kwargs.get("wall_ahead", True),  # type: ignore[arg-type]
                at_top=kwargs.get("at_top", False),  # type: ignore[arg-type]
            )
        if mode == MovementMode.SWIMMING:
            return self.swimming.update(
                stamina_ratio=kwargs.get("stamina_ratio", 1.0),  # type: ignore[arg-type]
                is_underwater=kwargs.get("is_underwater", False),  # type: ignore[arg-type]
                target_direction=kwargs.get("target_direction", (0.0, -1.0)),  # type: ignore[arg-type]
                near_shore=kwargs.get("near_shore", False),  # type: ignore[arg-type]
            )
        if mode == MovementMode.GLIDING:
            return self.gliding.update(
                is_airborne=kwargs.get("is_airborne", True),  # type: ignore[arg-type]
                target_direction=kwargs.get("target_direction", (0.0, -1.0)),  # type: ignore[arg-type]
                altitude=kwargs.get("altitude", 50.0),  # type: ignore[arg-type]
                near_ground=kwargs.get("near_ground", False),  # type: ignore[arg-type]
            )
        return self.sprint.update(
            stamina_ratio=kwargs.get("stamina_ratio", 1.0),  # type: ignore[arg-type]
            in_combat=kwargs.get("in_combat", False),  # type: ignore[arg-type]
            near_obstacle=kwargs.get("near_obstacle", False),  # type: ignore[arg-type]
        )
