from __future__ import annotations

import logging
from dataclasses import dataclass, field

_log = logging.getLogger("HSRNavigator")


@dataclass(frozen=True, slots=True)
class HSRNavigationStep:
    input_type: str   # "press_key", "click_at", "wait_screen"
    target: str       # key name, coordinate label, or screen state
    label: str = ""
    timeout_ms: int = 3000


@dataclass(slots=True)
class HSRNavigationPlan:
    destination: str
    steps: list[HSRNavigationStep] = field(default_factory=list)
    requires_teleport: bool = False


class HSRNavigator:
    """HSR map-based navigation using the in-game teleport system."""

    def plan_teleport(self, from_location: str, to_location: str) -> HSRNavigationPlan:
        steps = [
            HSRNavigationStep("press_key", "M", "open_map", 3000),
            HSRNavigationStep("wait_screen", "map_screen", "wait_for_map_load", 5000),
            HSRNavigationStep("click_at", f"map_pin_{to_location}", f"select_{to_location}", 2000),
            HSRNavigationStep("click_at", "teleport_button", "confirm_teleport", 2000),
            HSRNavigationStep("wait_screen", "overworld", "wait_for_arrival", 15000),
        ]
        return HSRNavigationPlan(
            destination=to_location,
            steps=steps,
            requires_teleport=True,
        )

    def plan_walk(self, direction: str, distance: float) -> list[HSRNavigationStep]:
        key_map = {"north": "W", "south": "S", "east": "D", "west": "A"}
        key = key_map.get(direction, "W")
        steps = [
            HSRNavigationStep("press_key", key, f"walk_{direction}", 500),
        ]
        return steps

    def plan_interact(self) -> list[HSRNavigationStep]:
        return [
            HSRNavigationStep("press_key", "F", "interact", 2000),
            HSRNavigationStep("wait_screen", "dialog", "wait_for_dialog", 3000),
        ]
