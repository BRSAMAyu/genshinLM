from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WeaknessBreakEffect:
    element: str
    break_multiplier: float
    effect: str
    duration_turns: int
    tactical_value: str


BREAK_EFFECTS: dict[str, WeaknessBreakEffect] = {
    "physical": WeaknessBreakEffect("physical", 1.5, "bleed", 2, "Medium"),
    "fire": WeaknessBreakEffect("fire", 2.0, "burn", 2, "High"),
    "ice": WeaknessBreakEffect("ice", 1.0, "freeze", 1, "High"),
    "lightning": WeaknessBreakEffect("lightning", 1.0, "shock", 2, "Medium"),
    "wind": WeaknessBreakEffect("wind", 1.5, "wind_shear", 2, "Medium"),
    "quantum": WeaknessBreakEffect("quantum", 1.5, "entanglement", 1, "High"),
    "imaginary": WeaknessBreakEffect("imaginary", 1.0, "imprisonment", 1, "High"),
}

VALID_ELEMENTS = frozenset(BREAK_EFFECTS.keys())


def get_break_effect(element: str) -> WeaknessBreakEffect | None:
    return BREAK_EFFECTS.get(element)


def get_counter_elements(element: str) -> list[str]:
    """Return elements that are tactically strong against the given element."""
    counter_map: dict[str, list[str]] = {
        "physical": ["fire", "ice"],
        "fire": ["ice", "water"],
        "ice": ["fire", "lightning"],
        "lightning": ["ice", "wind"],
        "wind": ["lightning", "quantum"],
        "quantum": ["wind", "imaginary"],
        "imaginary": ["quantum", "physical"],
    }
    return counter_map.get(element, [])
