from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CombatContext:
    target_visible: bool = True
    hp_ratio: float = 1.0
    stamina_ratio: float = 1.0
    danger_priority: float = 0.0
    current_combo_step: str | None = None
