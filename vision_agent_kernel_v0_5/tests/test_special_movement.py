"""Tests for navigation special movement controllers (N-07~N-14)."""
from __future__ import annotations

import pytest

from navigation.special_movement import (
    ClimbingController,
    ClimbingState,
    ElementalSightController,
    ElementalSightState,
    EnvironmentHazardAvoidance,
    EnvironmentHazardType,
    GlidingController,
    GlidingState,
    MovementDecision,
    MovementMode,
    SpecialMovementController,
    SprintManager,
    StaminaBudget,
    SwimmingController,
    SwimmingState,
    UndergroundNavigator,
    UndergroundState,
    VehicleController,
    VehicleState,
    _direction_to_keys,
)


# ---------------------------------------------------------------------------
# StaminaBudget
# ---------------------------------------------------------------------------
class TestStaminaBudget:
    def test_default_can_spend(self) -> None:
        sb = StaminaBudget()
        assert sb.can_spend

    def test_cannot_spend_below_reserve(self) -> None:
        sb = StaminaBudget(current_ratio=0.1, reserve_threshold=0.2)
        assert not sb.can_spend

    def test_should_recover(self) -> None:
        sb = StaminaBudget(current_ratio=0.5, recovery_threshold=0.8)
        assert sb.should_recover

    def test_should_not_recover(self) -> None:
        sb = StaminaBudget(current_ratio=0.9, recovery_threshold=0.8)
        assert not sb.should_recover


# ---------------------------------------------------------------------------
# ClimbingController
# ---------------------------------------------------------------------------
class TestClimbingController:
    def test_start_climbing(self) -> None:
        ctrl = ClimbingController()
        dec = ctrl.start_climbing("up")
        assert dec.action == "climb"
        assert "w" in dec.keys
        assert ctrl.state.is_climbing

    def test_start_climbing_left(self) -> None:
        ctrl = ClimbingController()
        dec = ctrl.start_climbing("left")
        assert "a" in dec.keys

    def test_reached_top(self) -> None:
        ctrl = ClimbingController()
        ctrl.start_climbing()
        dec = ctrl.update(stamina_ratio=0.8, is_visible=True, wall_ahead=True, at_top=True)
        assert dec.action == "move"
        assert dec.reason == "reached_top"
        assert not ctrl.state.is_climbing

    def test_stamina_low_recovery(self) -> None:
        ctrl = ClimbingController()
        ctrl.start_climbing()
        dec = ctrl.update(stamina_ratio=0.1, is_visible=True, wall_ahead=True, at_top=False)
        assert dec.action == "recover"
        assert ctrl.state.is_exhausted

    def test_exhausted_recovers_at_60_percent(self) -> None:
        ctrl = ClimbingController()
        ctrl.start_climbing()
        ctrl.update(stamina_ratio=0.1, is_visible=True, wall_ahead=True, at_top=False)
        assert ctrl.state.is_exhausted
        ctrl.update(stamina_ratio=0.7, is_visible=True, wall_ahead=True, at_top=False)
        assert not ctrl.state.is_exhausted

    def test_exhausted_stays_in_recovery_until_60_percent(self) -> None:
        ctrl = ClimbingController()
        ctrl.start_climbing()
        ctrl.update(stamina_ratio=0.1, is_visible=True, wall_ahead=True, at_top=False)
        assert ctrl.state.is_exhausted
        # At 0.4 stamina, can_spend is True (above 0.25 reserve) but still exhausted
        dec = ctrl.update(stamina_ratio=0.4, is_visible=True, wall_ahead=True, at_top=False)
        assert dec.action == "recover"
        assert ctrl.state.is_exhausted

    def test_no_wall_advance(self) -> None:
        ctrl = ClimbingController()
        ctrl.start_climbing()
        dec = ctrl.update(stamina_ratio=0.9, is_visible=True, wall_ahead=False, at_top=False)
        assert dec.action == "move"
        assert dec.reason == "no_wall_advance"

    def test_normal_climbing(self) -> None:
        ctrl = ClimbingController()
        ctrl.start_climbing()
        dec = ctrl.update(stamina_ratio=0.8, is_visible=True, wall_ahead=True, at_top=False)
        assert dec.action == "climb"
        assert "w" in dec.keys


# ---------------------------------------------------------------------------
# SwimmingController
# ---------------------------------------------------------------------------
class TestSwimmingController:
    def test_start_swimming(self) -> None:
        ctrl = SwimmingController()
        dec = ctrl.start_swimming((0.0, -1.0))
        assert dec.action == "swim"
        assert ctrl.state.is_swimming
        assert not ctrl.state.is_diving

    def test_start_diving(self) -> None:
        ctrl = SwimmingController()
        ctrl.start_swimming((0.0, -1.0))
        dec = ctrl.start_diving()
        assert dec.action == "dive"
        assert ctrl.state.is_diving
        assert not ctrl.state.is_swimming

    def test_surface(self) -> None:
        ctrl = SwimmingController()
        ctrl.start_diving()
        dec = ctrl.surface()
        assert dec.action == "surface"
        assert ctrl.state.is_swimming
        assert not ctrl.state.is_diving

    def test_near_shore_exits(self) -> None:
        ctrl = SwimmingController()
        ctrl.start_swimming((0.0, -1.0))
        dec = ctrl.update(stamina_ratio=0.9, is_underwater=False,
                          target_direction=(0.0, -1.0), near_shore=True)
        assert dec.action == "move"
        assert dec.reason == "reached_shore"
        assert not ctrl.state.is_swimming

    def test_stamina_exhausted(self) -> None:
        ctrl = SwimmingController()
        ctrl.start_swimming((0.0, -1.0))
        dec = ctrl.update(stamina_ratio=0.05, is_underwater=False,
                          target_direction=(0.0, -1.0), near_shore=False)
        assert dec.action == "recover"
        assert ctrl.state.is_exhausted

    def test_underwater_uses_dive(self) -> None:
        ctrl = SwimmingController()
        ctrl.start_swimming((0.0, -1.0))
        dec = ctrl.update(stamina_ratio=0.9, is_underwater=True,
                          target_direction=(0.0, -1.0), near_shore=False)
        assert dec.action == "dive"

    def test_direction_to_keys(self) -> None:
        assert "w" in _direction_to_keys((0.0, -1.0))
        assert "s" in _direction_to_keys((0.0, 1.0))
        assert "a" in _direction_to_keys((-1.0, 0.0))
        assert "d" in _direction_to_keys((1.0, 0.0))

    def test_direction_to_keys_default_forward(self) -> None:
        keys = _direction_to_keys((0.0, 0.0))
        assert keys == ("w",)


# ---------------------------------------------------------------------------
# GlidingController
# ---------------------------------------------------------------------------
class TestGlidingController:
    def test_takeoff(self) -> None:
        ctrl = GlidingController()
        dec = ctrl.takeoff()
        assert dec.action == "glide"
        assert ctrl.state.is_gliding

    def test_land(self) -> None:
        ctrl = GlidingController()
        ctrl.takeoff()
        dec = ctrl.land()
        assert dec.action == "land"
        assert not ctrl.state.is_gliding

    def test_grounded_when_not_airborne(self) -> None:
        ctrl = GlidingController()
        dec = ctrl.update(is_airborne=False, target_direction=(0.0, -1.0),
                          altitude=0.0, near_ground=True)
        assert dec.action == "move"
        assert dec.reason == "grounded"

    def test_auto_land_near_ground(self) -> None:
        ctrl = GlidingController()
        dec = ctrl.update(is_airborne=True, target_direction=(0.0, -1.0),
                          altitude=3.0, near_ground=True)
        assert dec.action == "land"

    def test_gliding_towards_target(self) -> None:
        ctrl = GlidingController()
        dec = ctrl.update(is_airborne=True, target_direction=(0.0, -1.0),
                          altitude=100.0, near_ground=False)
        assert dec.action == "glide"
        assert "w" in dec.keys


# ---------------------------------------------------------------------------
# SprintManager
# ---------------------------------------------------------------------------
class TestSprintManager:
    def test_should_sprint_high_stamina(self) -> None:
        mgr = SprintManager(reserve_ratio=0.3)
        assert mgr.should_sprint(0.8)

    def test_should_not_sprint_low_stamina(self) -> None:
        mgr = SprintManager(reserve_ratio=0.3)
        assert not mgr.should_sprint(0.3)

    def test_should_not_sprint_in_danger(self) -> None:
        mgr = SprintManager(reserve_ratio=0.3)
        assert not mgr.should_sprint(0.9, danger_level=0.6)

    def test_update_sprinting(self) -> None:
        mgr = SprintManager(reserve_ratio=0.3)
        dec = mgr.update(stamina_ratio=0.8, in_combat=False, near_obstacle=False)
        assert "shift" in dec.keys
        assert dec.reason == "sprinting"

    def test_update_no_sprint_in_combat(self) -> None:
        mgr = SprintManager(reserve_ratio=0.3)
        dec = mgr.update(stamina_ratio=0.9, in_combat=True, near_obstacle=False)
        assert "shift" not in dec.keys

    def test_update_walk_to_recover(self) -> None:
        mgr = SprintManager(reserve_ratio=0.3)
        dec = mgr.update(stamina_ratio=0.4, in_combat=False, near_obstacle=False)
        assert dec.reason == "walk_to_recover_stamina"
        assert "shift" not in dec.keys


# ---------------------------------------------------------------------------
# ElementalSightController
# ---------------------------------------------------------------------------
class TestElementalSightController:
    def test_activate(self) -> None:
        ctrl = ElementalSightController()
        dec = ctrl.activate()
        assert dec.action == "use_sight"
        assert ctrl.state.is_active
        assert not ctrl.state.scan_complete

    def test_deactivate(self) -> None:
        ctrl = ElementalSightController()
        ctrl.activate()
        dec = ctrl.deactivate()
        assert not ctrl.state.is_active
        assert ctrl.state.scan_complete

    def test_detect_objects(self) -> None:
        ctrl = ElementalSightController()
        objects = [(100.0, 200.0, "chest"), (300.0, 400.0, "ore")]
        result = ctrl.detect_objects(objects)
        assert len(result) == 2
        assert ctrl.state.objects_detected == objects


# ---------------------------------------------------------------------------
# VehicleController
# ---------------------------------------------------------------------------
class TestVehicleController:
    def test_activate_vehicle(self) -> None:
        ctrl = VehicleController()
        dec = ctrl.activate_vehicle("saurian")
        assert dec.action == "use_vehicle"
        assert ctrl.state.is_active
        assert ctrl.state.vehicle_type == "saurian"

    def test_deactivate(self) -> None:
        ctrl = VehicleController()
        ctrl.activate_vehicle("waverider")
        dec = ctrl.deactivate()
        assert not ctrl.state.is_active

    def test_use_ability(self) -> None:
        ctrl = VehicleController()
        ctrl.activate_vehicle("saurian")
        dec = ctrl.use_ability()
        assert dec.action == "use_vehicle"
        assert "e" in dec.keys
        assert ctrl.state.ability_cooldown == 5.0

    def test_ability_on_cooldown(self) -> None:
        ctrl = VehicleController()
        ctrl.activate_vehicle("saurian")
        ctrl.use_ability()
        dec = ctrl.use_ability()
        assert dec.action == "wait"
        assert dec.reason == "ability_on_cooldown"

    def test_cooldown_decreases(self) -> None:
        ctrl = VehicleController()
        ctrl.activate_vehicle("saurian")
        ctrl.use_ability()
        ctrl.update_cooldown(2.0)
        assert ctrl.state.ability_cooldown == pytest.approx(3.0)

    def test_cooldown_floor_zero(self) -> None:
        ctrl = VehicleController()
        ctrl.activate_vehicle("saurian")
        ctrl.use_ability()
        ctrl.update_cooldown(10.0)
        assert ctrl.state.ability_cooldown == 0.0


# ---------------------------------------------------------------------------
# UndergroundNavigator
# ---------------------------------------------------------------------------
class TestUndergroundNavigator:
    def test_enter_underground(self) -> None:
        nav = UndergroundNavigator()
        dec = nav.enter_underground(layer=1)
        assert nav.state.is_underground
        assert nav.state.layer == 1
        assert "layer_1" in dec.reason

    def test_exit_underground(self) -> None:
        nav = UndergroundNavigator()
        nav.enter_underground(layer=2)
        dec = nav.exit_underground()
        assert not nav.state.is_underground
        assert nav.state.layer == 0

    def test_change_layer(self) -> None:
        nav = UndergroundNavigator()
        nav.enter_underground(layer=1)
        dec = nav.change_layer(2)
        assert nav.state.layer == 2

    def test_activate_light(self) -> None:
        nav = UndergroundNavigator()
        dec = nav.activate_light()
        assert nav.state.light_source_active


# ---------------------------------------------------------------------------
# EnvironmentHazardAvoidance
# ---------------------------------------------------------------------------
class TestEnvironmentHazardAvoidance:
    def test_no_hazard(self) -> None:
        avoid = EnvironmentHazardAvoidance()
        dec = avoid.update("none", 0.0)
        assert dec.action == "move"
        assert dec.reason == "no_hazard"

    def test_unknown_gauge(self) -> None:
        avoid = EnvironmentHazardAvoidance()
        dec = avoid.update("unknown_gauge", 0.5)
        assert avoid.current_hazard == EnvironmentHazardType.NONE

    def test_low_hazard_safe(self) -> None:
        avoid = EnvironmentHazardAvoidance()
        dec = avoid.update("sheer_cold", 0.3)
        assert dec.action == "move"
        assert "safe_to_proceed" in dec.reason

    def test_medium_hazard_seek_shelter(self) -> None:
        avoid = EnvironmentHazardAvoidance()
        dec = avoid.update("balethunder", 0.7)
        assert dec.action == "warm_up"
        assert "seeking" in dec.reason

    def test_critical_hazard_retreat(self) -> None:
        avoid = EnvironmentHazardAvoidance()
        dec = avoid.update("phlogiston", 0.9)
        assert dec.action == "retreat"
        assert "critical" in dec.reason

    def test_get_nearest_shelter_sheer_cold(self) -> None:
        avoid = EnvironmentHazardAvoidance()
        avoid.update("sheer_cold", 0.5)
        assert avoid.get_nearest_shelter() == "statue_of_seven"

    def test_get_nearest_shelter_no_hazard(self) -> None:
        avoid = EnvironmentHazardAvoidance()
        assert avoid.get_nearest_shelter() == "statue_of_seven"


# ---------------------------------------------------------------------------
# SpecialMovementController (unified facade)
# ---------------------------------------------------------------------------
class TestSpecialMovementController:
    def test_detect_mode_climbing(self) -> None:
        ctrl = SpecialMovementController()
        mode = ctrl.detect_mode(is_climbing=True, is_swimming=False,
                                is_airborne=False, is_underground=False,
                                stamina_visible=True)
        assert mode == MovementMode.CLIMBING

    def test_detect_mode_gliding(self) -> None:
        ctrl = SpecialMovementController()
        mode = ctrl.detect_mode(is_climbing=False, is_swimming=False,
                                is_airborne=True, is_underground=False,
                                stamina_visible=True)
        assert mode == MovementMode.GLIDING

    def test_detect_mode_swimming(self) -> None:
        ctrl = SpecialMovementController()
        mode = ctrl.detect_mode(is_climbing=False, is_swimming=True,
                                is_airborne=False, is_underground=False,
                                stamina_visible=True)
        assert mode == MovementMode.SWIMMING

    def test_detect_mode_walking(self) -> None:
        ctrl = SpecialMovementController()
        mode = ctrl.detect_mode(is_climbing=False, is_swimming=False,
                                is_airborne=False, is_underground=False,
                                stamina_visible=False)
        assert mode == MovementMode.WALKING

    def test_detect_mode_underground_is_walking(self) -> None:
        ctrl = SpecialMovementController()
        mode = ctrl.detect_mode(is_climbing=False, is_swimming=False,
                                is_airborne=False, is_underground=True,
                                stamina_visible=False)
        assert mode == MovementMode.WALKING

    def test_evaluate_climbing(self) -> None:
        ctrl = SpecialMovementController()
        dec = ctrl.evaluate(MovementMode.CLIMBING, stamina_ratio=0.8,
                            stamina_visible=True, wall_ahead=True, at_top=False)
        assert dec.action == "climb"

    def test_evaluate_swimming(self) -> None:
        ctrl = SpecialMovementController()
        dec = ctrl.evaluate(MovementMode.SWIMMING, stamina_ratio=0.9,
                            is_underwater=False, target_direction=(0.0, -1.0),
                            near_shore=False)
        assert dec.action == "swim"

    def test_evaluate_gliding(self) -> None:
        ctrl = SpecialMovementController()
        dec = ctrl.evaluate(MovementMode.GLIDING, is_airborne=True,
                            target_direction=(0.0, -1.0), altitude=100.0,
                            near_ground=False)
        assert dec.action == "glide"

    def test_evaluate_walking_uses_sprint(self) -> None:
        ctrl = SpecialMovementController()
        dec = ctrl.evaluate(MovementMode.WALKING, stamina_ratio=0.9,
                            in_combat=False, near_obstacle=False)
        assert dec.action == "move"

    def test_evaluate_hazard_overrides(self) -> None:
        ctrl = SpecialMovementController()
        # Set up a critical hazard
        ctrl.hazard_avoidance.update("sheer_cold", 0.9)
        dec = ctrl.evaluate(MovementMode.WALKING, stamina_ratio=0.9,
                            in_combat=False, near_obstacle=False)
        assert dec.action == "retreat"

    def test_sub_controllers_initialized(self) -> None:
        ctrl = SpecialMovementController()
        assert isinstance(ctrl.climbing, ClimbingController)
        assert isinstance(ctrl.swimming, SwimmingController)
        assert isinstance(ctrl.gliding, GlidingController)
        assert isinstance(ctrl.sprint, SprintManager)
        assert isinstance(ctrl.elemental_sight, ElementalSightController)
        assert isinstance(ctrl.vehicle, VehicleController)
        assert isinstance(ctrl.underground, UndergroundNavigator)
        assert isinstance(ctrl.hazard_avoidance, EnvironmentHazardAvoidance)


# ---------------------------------------------------------------------------
# Dataclass slot tests
# ---------------------------------------------------------------------------
class TestDataclassSlots:
    def test_stamina_budget_slots(self) -> None:
        sb = StaminaBudget()
        assert hasattr(sb, "__slots__")

    def test_climbing_state_slots(self) -> None:
        cs = ClimbingState()
        assert hasattr(cs, "__slots__")

    def test_movement_decision_has_slots(self) -> None:
        md = MovementDecision(action="move")
        assert hasattr(md, "__slots__")
