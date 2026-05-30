"""Environmental interaction handler for combat.

Implements C-47: Environmental Interaction Handling
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from core.state_bus import StateBus

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C-47: Environmental Interaction Handler
# ---------------------------------------------------------------------------

class TerrainType(str, Enum):
    """Types of terrain that affect combat."""
    NORMAL = "normal"              # Standard terrain
    WATER = "water"                # Water bodies
    GRASS = "grass"               # Grasslands (dendro resonance)
    MUD = "mud"                    # Mud (slows movement)
    LAVA = "lava"                 # Lava (damage over time)
    ICE = "ice"                   # Ice (slippery)
    SAND = "sand"                 # Sand (slower movement)
    ELECTRIC = "electric"          # Electro anomaly (conducts)
    PYRO = "pyro"                 # Burning terrain
    ELEMENTAL_FIELD = "elemental"  # Elemental object interaction


class TerrainEffect(str, Enum):
    """Effects of terrain on combat."""
    SLOW = "slow"                 # Movement speed reduced
    DOT = "dot"                   # Damage over time
    BUFF = "buff"                 # Stat buff
    DEBUFF = "debuff"             # Stat debuff
    ELEMENTAL = "elemental"       # Elemental reaction chance
    HEAL = "heal"                 # Healing
    UNSTABLE = "unstable"         # Can cause elemental reactions


@dataclass(frozen=True, slots=True)
class TerrainInfo:
    """Information about current terrain."""
    terrain_type: TerrainType
    position: tuple[float, float]
    radius: float
    duration_sec: float | None
    elemental_type: str | None  # "hydro", "pyro", etc.
    effects: tuple[TerrainEffect, ...]
    danger_level: float  # 0.0-1.0


@dataclass(frozen=True, slots=True)
class TerrainInteraction:
    """Interaction between character and terrain."""
    terrain: TerrainInfo
    exposure_duration_sec: float
    current_effects: tuple[TerrainEffect, ...]
    recommended_action: str


@dataclass(frozen=True, slots=True)
class EnvironmentCombatStrategy:
    """Combat strategy based on environment."""
    terrain_type: TerrainType
    combat_modifiers: tuple[str, ...]  # "move_speed:-30%", "dps:+20%"
    danger_zones: tuple[tuple[float, float], ...]
    safe_zones: tuple[tuple[float, float], ...]
    recommended_position: tuple[float, float]
    elemental_considerations: tuple[str, ...]


class EnvironmentalInteractionHandler:
    """Handles terrain and environmental effects on combat.

    Environment affects combat in several ways:
    - Water: Swimming speed, electro conduction
    - Grass: Dendro reactions, burning DOT
    - Lava: High damage DOT, positioning critical
    - Ice: Sliding, reduced friction
    - Elemental fields: Object interactions

    Strategic considerations:
    - Position near beneficial terrain (healing, buffs)
    - Avoid dangerous terrain (lava, deep water)
    - Use elemental terrain for reactions
    """

    def __init__(self) -> None:
        self._now_fn = time.perf_counter
        self._detected_terrain: list[TerrainInfo] = []
        self._active_interactions: list[TerrainInteraction] = []
        self._terrain_history: list[tuple[float, TerrainInfo]] = []  # (time, terrain)

    def detect_terrain(
        self,
        frame: np.ndarray | None,
        character_position: tuple[float, float],
        nearby_objects: list[str],
        timestamp: float | None = None,
    ) -> list[TerrainInfo]:
        """Detect terrain types in current area.

        Args:
            frame: Frame for visual detection.
            character_position: Current character position.
            nearby_objects: Detected objects (water, grass, etc.).
            timestamp: Current time.

        Returns:
            List of detected terrain.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        terrain_list: list[TerrainInfo] = []

        # Detect based on nearby objects
        object_terrain_map: dict[str, TerrainType] = {
            "water": TerrainType.WATER,
            "pond": TerrainType.WATER,
            "lake": TerrainType.WATER,
            "grass": TerrainType.GRASS,
            "meadow": TerrainType.GRASS,
            "mud": TerrainType.MUD,
            "lava": TerrainType.LAVA,
            "magma": TerrainType.LAVA,
            "ice": TerrainType.ICE,
            "snow": TerrainType.ICE,
            "sand": TerrainType.SAND,
            "dune": TerrainType.SAND,
        }

        for obj in nearby_objects:
            obj_lower = obj.lower()
            for keyword, terrain_type in object_terrain_map.items():
                if keyword in obj_lower:
                    effects = self._get_terrain_effects(terrain_type)
                    danger = self._calculate_danger(terrain_type)

                    terrain_list.append(TerrainInfo(
                        terrain_type=terrain_type,
                        position=character_position,  # Approximate
                        radius=10.0,  # Default radius
                        duration_sec=None,
                        elemental_type=self._get_elemental_type(terrain_type),
                        effects=tuple(effects),
                        danger_level=danger,
                    ))
                    break

        self._detected_terrain = terrain_list
        return terrain_list

    def _get_terrain_effects(self, terrain_type: TerrainType) -> list[TerrainEffect]:
        """Get effects associated with terrain type."""
        effect_map: dict[TerrainType, list[TerrainEffect]] = {
            TerrainType.WATER: [TerrainEffect.SLOW, TerrainEffect.ELEMENTAL],
            TerrainType.GRASS: [TerrainEffect.BUFF, TerrainEffect.ELEMENTAL],
            TerrainType.MUD: [TerrainEffect.SLOW, TerrainEffect.DEBUFF],
            TerrainType.LAVA: [TerrainEffect.DOT, TerrainEffect.DANGER],
            TerrainType.ICE: [TerrainEffect.UNSTABLE],
            TerrainType.SAND: [TerrainEffect.SLOW],
            TerrainType.ELECTRIC: [TerrainEffect.DOT, TerrainEffect.ELEMENTAL],
            TerrainType.PYRO: [TerrainEffect.DOT, TerrainEffect.UNSTABLE],
            TerrainType.NORMAL: [],
            TerrainType.ELEMENTAL_FIELD: [TerrainEffect.ELEMENTAL, TerrainEffect.BUFF],
        }
        return effect_map.get(terrain_type, [])

    def _get_elemental_type(self, terrain_type: TerrainType) -> str | None:
        """Get elemental type for terrain if applicable."""
        elemental_map: dict[TerrainType, str] = {
            TerrainType.WATER: "hydro",
            TerrainType.PYRO: "pyro",
            TerrainType.ELECTRIC: "electro",
            TerrainType.ICE: "cryo",
            TerrainType.GRASS: "dendro",
        }
        return elemental_map.get(terrain_type)

    def _calculate_danger(self, terrain_type: TerrainType) -> float:
        """Calculate danger level of terrain."""
        danger_map: dict[TerrainType, float] = {
            TerrainType.LAVA: 0.9,
            TerrainType.ELECTRIC: 0.7,
            TerrainType.PYRO: 0.6,
            TerrainType.ICE: 0.5,
            TerrainType.MUD: 0.4,
            TerrainType.WATER: 0.3,
            TerrainType.SAND: 0.2,
            TerrainType.GRASS: 0.1,
            TerrainType.NORMAL: 0.0,
            TerrainType.ELEMENTAL_FIELD: 0.1,
        }
        return danger_map.get(terrain_type, 0.0)

    def check_interaction(
        self,
        character_position: tuple[float, float],
        timestamp: float | None = None,
    ) -> TerrainInteraction | None:
        """Check if character is in terrain interaction.

        Args:
            character_position: Current character position.
            timestamp: Current time.

        Returns:
            TerrainInteraction if in terrain, None otherwise.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        for terrain in self._detected_terrain:
            # Check if position is within terrain
            dx = character_position[0] - terrain.position[0]
            dy = character_position[1] - terrain.position[1]
            dist = (dx * dx + dy * dy) ** 0.5

            if dist <= terrain.radius:
                # Calculate exposure duration
                history_entry = next(
                    ((now - t) for t, t_info in self._terrain_history if t_info == terrain),
                    0.0,
                )

                interaction = TerrainInteraction(
                    terrain=terrain,
                    exposure_duration_sec=history_entry,
                    current_effects=terrain.effects,
                    recommended_action=self._recommend_action(terrain),
                )

                self._active_interactions.append(interaction)
                return interaction

        return None

    def _recommend_action(self, terrain: TerrainInfo) -> str:
        """Recommend action based on terrain."""
        if terrain.danger_level >= 0.8:
            return "exit_terrain_immediately"
        elif terrain.danger_level >= 0.5:
            return "minimize_exposure"
        elif TerrainEffect.HEAL in terrain.effects:
            return "stay_for_healing"
        elif TerrainEffect.BUFF in terrain.effects:
            return "position_for_buff"
        elif TerrainEffect.ELEMENTAL in terrain.effects:
            return "exploit_elemental"
        else:
            return "normal_combat"

    def create_combat_strategy(
        self,
        character_position: tuple[float, float],
        enemy_positions: list[tuple[float, float]],
        terrain_list: list[TerrainInfo],
        timestamp: float | None = None,
    ) -> EnvironmentCombatStrategy:
        """Create combat strategy based on environment.

        Args:
            character_position: Current character position.
            enemy_positions: Positions of enemies.
            terrain_list: Detected terrain in area.
            timestamp: Current time.

        Returns:
            EnvironmentCombatStrategy with positioning recommendations.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        if not terrain_list:
            return EnvironmentCombatStrategy(
                terrain_type=TerrainType.NORMAL,
                combat_modifiers=(),
                danger_zones=(),
                safe_zones=(),
                recommended_position=character_position,
                elemental_considerations=(),
            )

        # Determine dominant terrain (most relevant)
        dominant = self._select_dominant_terrain(terrain_list, character_position)

        # Calculate modifiers based on terrain
        modifiers = self._calculate_modifiers(dominant)

        # Find danger and safe zones
        danger_zones = self._find_danger_zones(terrain_list)
        safe_zones = self._find_safe_zones(terrain_list, character_position)

        # Recommend position
        recommended = self._recommend_position(
            character_position, enemy_positions, terrain_list
        )

        # Elemental considerations
        elemental = self._get_elemental_considerations(dominant)

        return EnvironmentCombatStrategy(
            terrain_type=dominant.terrain_type,
            combat_modifiers=tuple(modifiers),
            danger_zones=tuple(danger_zones),
            safe_zones=tuple(safe_zones),
            recommended_position=recommended,
            elemental_considerations=tuple(elemental),
        )

    def _select_dominant_terrain(
        self,
        terrain_list: list[TerrainInfo],
        char_pos: tuple[float, float],
    ) -> TerrainInfo:
        """Select most relevant terrain for current position."""
        # Find terrain closest to character
        closest = min(
            terrain_list,
            key=lambda t: ((t.position[0] - char_pos[0])**2 +
                          (t.position[1] - char_pos[1])**2)**0.5
        )
        return closest

    def _calculate_modifiers(self, terrain: TerrainInfo) -> list[str]:
        """Calculate combat modifiers from terrain."""
        mods: list[str] = []

        for effect in terrain.effects:
            if effect == TerrainEffect.SLOW:
                mods.append("move_speed:-30%")
            elif effect == TerrainEffect.DOT:
                mods.append("hp_drain:10/s")
            elif effect == TerrainEffect.BUFF:
                mods.append("atk:+15%")
            elif effect == TerrainEffect.DEBUFF:
                mods.append("def:-20%")
            elif effect == TerrainEffect.ELEMENTAL:
                if terrain.elemental_type:
                    mods.append(f"reaction_enabled:{terrain.elemental_type}")
            elif effect == TerrainEffect.HEAL:
                mods.append("hp_regen:5/s")

        # Add danger modifier
        if terrain.danger_level > 0.7:
            mods.append("high_danger")
        elif terrain.danger_level > 0.4:
            mods.append("moderate_danger")

        return mods

    def _find_danger_zones(
        self,
        terrain_list: list[TerrainInfo],
    ) -> list[tuple[float, float]]:
        """Find danger zone positions."""
        zones: list[tuple[float, float]] = []
        for terrain in terrain_list:
            if terrain.danger_level >= 0.6:
                zones.append(terrain.position)
        return zones

    def _find_safe_zones(
        self,
        terrain_list: list[TerrainInfo],
        char_pos: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """Find safe zone positions."""
        zones: list[tuple[float, float]] = []
        for terrain in terrain_list:
            if terrain.danger_level < 0.3 and TerrainEffect.BUFF in terrain.effects:
                zones.append(terrain.position)
        return zones

    def _recommend_position(
        self,
        char_pos: tuple[float, float],
        enemy_positions: list[tuple[float, float]],
        terrain_list: list[TerrainInfo],
    ) -> tuple[float, float]:
        """Recommend optimal position considering terrain."""
        # Default to current position
        recommended = char_pos

        # Check for safe zones with buffs
        safe_buff_zones = [
            t.position for t in terrain_list
            if t.danger_level < 0.3 and TerrainEffect.BUFF in t.effects
        ]

        if safe_buff_zones:
            # Pick closest safe buff zone
            recommended = min(
                safe_buff_zones,
                key=lambda p: ((p[0] - char_pos[0])**2 +
                             (p[1] - char_pos[1])**2)**0.5
            )

        return recommended

    def _get_elemental_considerations(self, terrain: TerrainInfo) -> list[str]:
        """Get elemental considerations for terrain."""
        considerations: list[str] = []

        if terrain.elemental_type:
            considerations.append(f"{terrain.elemental_type}_field_present")

            # Add specific considerations
            if terrain.elemental_type == "hydro":
                considerations.append("can_trigger_vaporize_with_pyro")
                considerations.append("electro_charged_possible")
            elif terrain.elemental_type == "dendro":
                considerations.append("can_trigger_bloom")
                considerations.append("burgeon/hyperbloom_chain_possible")
            elif terrain.elemental_type == "pyro":
                considerations.append("burning_damage_active")
                considerations.append("melt/vaporize_trigger")

        return considerations

    def trigger_elemental_reaction(
        self,
        terrain: TerrainInfo,
        character_element: str,
    ) -> str | None:
        """Attempt to trigger elemental reaction with terrain.

        Args:
            terrain: Terrain to interact with.
            character_element: Character's current element.

        Returns:
            Reaction name if triggered, None otherwise.
        """
        if terrain.elemental_type is None:
            return None

        element_pair = (character_element, terrain.elemental_type)

        reaction_map: dict[tuple[str, str], str] = {
            ("pyro", "hydro"): "vaporize",
            ("hydro", "pyro"): "vaporize",
            ("pyro", "dendro"): "burning",
            ("electro", "hydro"): "electro_charged",
            ("cryo", "electro"): "superconduct",
            ("pyro", "electro"): "overloaded",
            ("anemo", "pyro"): "swirl_pyro",
            ("anemo", "hydro"): "swirl_hydro",
            ("anemo", "cryo"): "swirl_cryo",
            ("anemo", "electro"): "swirl_electro",
            ("dendro", "hydro"): "bloom",
            ("electro", "dendro"): "quicken",
        }

        return reaction_map.get(element_pair)

    def reset(self) -> None:
        """Reset handler state."""
        self._detected_terrain.clear()
        self._active_interactions.clear()
        self._terrain_history.clear()