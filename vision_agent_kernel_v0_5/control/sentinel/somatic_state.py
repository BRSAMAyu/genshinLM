"""SomaticState — the agent's embodied self-knowledge.

Tracks the agent's last-known-safe state so recovery recipes can
determine what went wrong and where to restore to.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class PositionEstimate:
    """Estimated position in game world."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    confidence: float = 0.0
    source: str = ""  # minimap, waypoint, gps_estimate


@dataclass(frozen=True, slots=True)
class TeamState:
    """Current team composition and HP."""
    active_character: str = ""
    characters: tuple[str, ...] = ()
    hp_ratios: tuple[float, ...] = ()
    energy_ratios: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class ResourceState:
    """Tracked resource levels."""
    resin: int = 0
    mora: int = 0
    primogems: int = 0


@dataclass(frozen=True, slots=True)
class SomaticState:
    """Agent's embodied self-knowledge snapshot.

    Immutable; use evolve() to create updated versions.
    Tracks last-known-safe state for recovery decisions.
    """
    active_quest_id: str = ""
    last_verified_checkpoint: str = ""
    last_safe_screen_state: str = "world_viewport"
    last_known_position: PositionEstimate | None = None
    last_map_anchor: str | None = None
    team_state: TeamState = field(default_factory=TeamState)
    resource_state: ResourceState = field(default_factory=ResourceState)
    active_mission_node: str = ""
    claim_graph_version: int = 0
    frame_id: int = 0
    timestamp: float = 0.0
    is_stuck: bool = False
    is_target_lost: bool = False
    is_loading: bool = False
    is_drifting: bool = False
    model_provider_failed: bool = False

    def evolve(self, **overrides: Any) -> SomaticState:
        return replace(self, **overrides)

    def is_healthy(self) -> bool:
        """Check if team has at least one living character."""
        if not self.team_state.hp_ratios:
            return True  # unknown = assume healthy
        return any(hp > 0.0 for hp in self.team_state.hp_ratios)

    def is_safe_screen(self) -> bool:
        return self.last_safe_screen_state in (
            "world_viewport", "dialogue", "map", "character_menu",
            "inventory", "quest_log", "settings",
        )
