from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ActorStateName = Literal["idle", "moving", "attacking", "casting_skill", "dodging", "hitstun", "knocked_back", "recovering", "dead"]
TargetStateName = Literal["visible", "lost", "attacking", "stunned", "dead"]


@dataclass(frozen=True, slots=True)
class CooldownState:
    ready: bool
    remaining_ms: int
    confidence: float


@dataclass(frozen=True, slots=True)
class CombatResources:
    hp_ratio: float = 1.0
    stamina_estimate: float = 1.0
    dodge_available: bool = True


@dataclass(frozen=True, slots=True)
class CombatActionState:
    actor_state: ActorStateName = "idle"
    target_state: TargetStateName = "visible"
    resources: CombatResources = field(default_factory=CombatResources)
    cooldowns: dict[str, CooldownState] = field(default_factory=dict)

