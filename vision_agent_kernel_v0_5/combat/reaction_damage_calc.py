"""Elemental reaction damage calculation system.

Implements C-46: Elemental Reaction Damage Calculation
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.types import TargetTrack

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C-46: Reaction Damage Calculator
# ---------------------------------------------------------------------------

class Element(str, Enum):
    """Element types in Genshin."""
    PYRO = "pyro"
    HYDRO = "hydro"
    ELECTRO = "electro"
    CRYO = "cryo"
    ANEMO = "anemo"
    GEO = "geo"
    DENDRO = "dendro"
    NONE = "none"


class ReactionType(str, Enum):
    """Elemental reaction types."""
    VAPORIZE = "vaporize"
    MELT = "melt"
    OVERLOADED = "overloaded"
    ELECTRO_CHARGED = "electro_charged"
    SUPERCONDUCT = "superconduct"
    SWIRL = "swirl"
    CRYSTALLIZE = "crystallize"
    FREEZE = "freeze"
    BURN = "burn"
    BLOOM = "bloom"
    HYPERBLOOM = "hyperbloom"
    BURGEON = "burgeon"
    QUICKEN = "quicken"
    AGGRAVATE = "aggravate"
    SPREAD = "spread"
    SPRAY = "spray"
    DRIP = "drip"


@dataclass(frozen=True, slots=True)
class ReactionConfig:
    """Configuration for an elemental reaction."""
    reaction_type: ReactionType
    trigger_element: Element
    base_element: Element
    base_damage: float
    scaling_ratio: float  # EM scaling ratio
    damage_key: str       # "vaporize", "melt", etc.
    aoe_radius: float
    shared_cd_ms: float    # Shared ICD in milliseconds
    is_transformative: bool  # Transformative vs ampliative


@dataclass(frozen=True, slots=True)
class CharacterStats:
    """Character combat stats for damage calculation."""
    level: int
    base_attack: float
    elemental_mastery: float
    crit_rate: float
    crit_damage: float
    elemental_burst_dmg_bonus: float = 0.0
    skill_dmg_bonus: float = 0.0


@dataclass(frozen=True, slots=True)
class ReactionDamageResult:
    """Result of reaction damage calculation."""
    reaction_type: ReactionType
    base_damage: float
    scaled_damage: float
    final_damage: float
    is_critical: bool
    elemental_mastery_bonus: float
    aoe_mult: float


# Reaction configurations
_REACTION_CONFIGS: dict[ReactionType, ReactionConfig] = {
    # Ampliative reactions (scale with ATK)
    ReactionType.VAPORIZE: ReactionConfig(
        reaction_type=ReactionType.VAPORIZE,
        trigger_element=Element.PYRO,
        base_element=Element.HYDRO,
        base_damage=0.0,  # Base damage from ATK scaling
        scaling_ratio=1.0,
        damage_key="vaporize",
        aoe_radius=0.0,
        shared_cd_ms=0.0,
        is_transformative=False,
    ),
    ReactionType.MELT: ReactionConfig(
        reaction_type=ReactionType.MELT,
        trigger_element=Element.PYRO,
        base_element=Element.CRYO,
        base_damage=0.0,
        scaling_ratio=1.0,
        damage_key="melt",
        aoe_radius=0.0,
        shared_cd_ms=0.0,
        is_transformative=False,
    ),
    # Transformative reactions (scale with Level + EM)
    ReactionType.OVERLOADED: ReactionConfig(
        reaction_type=ReactionType.OVERLOADED,
        trigger_element=Element.PYRO,
        base_element=Element.ELECTRO,
        base_damage=120.0,  # Base at level 1, scales with level
        scaling_ratio=3.2,
        damage_key="overloaded",
        aoe_radius=5.0,
        shared_cd_ms=0.0,
        is_transformative=True,
    ),
    ReactionType.SUPERCONDUCT: ReactionConfig(
        reaction_type=ReactionType.SUPERCONDUCT,
        trigger_element=Element.CRYO,
        base_element=Element.ELECTRO,
        base_damage=80.0,
        scaling_ratio=3.2,
        damage_key="superconduct",
        aoe_radius=5.0,
        shared_cd_ms=0.0,
        is_transformative=True,
    ),
    ReactionType.ELECTRO_CHARGED: ReactionConfig(
        reaction_type=ReactionType.ELECTRO_CHARGED,
        trigger_element=Element.ELECTRO,
        base_element=Element.HYDRO,
        base_damage=100.0,
        scaling_ratio=3.2,
        damage_key="electro_charged",
        aoe_radius=3.0,
        shared_cd_ms=0.0,
        is_transformative=True,
    ),
    ReactionType.SWIRL: ReactionConfig(
        reaction_type=ReactionType.SWIRL,
        trigger_element=Element.ANEMO,
        base_element=Element.NONE,  # Swirl absorbs any element
        base_damage=80.0,
        scaling_ratio=2.4,
        damage_key="swirl",
        aoe_radius=5.0,
        shared_cd_ms=0.0,
        is_transformative=True,
    ),
    ReactionType.CRYSTALLIZE: ReactionConfig(
        reaction_type=ReactionType.CRYSTALLIZE,
        trigger_element=Element.GEO,
        base_element=Element.NONE,
        base_damage=0.0,
        scaling_ratio=0.0,
        damage_key="crystallize",
        aoe_radius=0.0,
        shared_cd_ms=0.0,
        is_transformative=True,
    ),
    ReactionType.FREEZE: ReactionConfig(
        reaction_type=ReactionType.FREEZE,
        trigger_element=Element.CRYO,
        base_element=Element.HYDRO,
        base_damage=0.0,
        scaling_ratio=0.0,
        damage_key="freeze",
        aoe_radius=0.0,
        shared_cd_ms=0.0,
        is_transformative=True,
    ),
    ReactionType.BURN: ReactionConfig(
        reaction_type=ReactionType.BURN,
        trigger_element=Element.PYRO,
        base_element=Element.DENDRO,
        base_damage=40.0,
        scaling_ratio=1.5,
        damage_key="burn",
        aoe_radius=2.0,
        shared_cd_ms=0.0,
        is_transformative=True,
    ),
    ReactionType.BLOOM: ReactionConfig(
        reaction_type=ReactionType.BLOOM,
        trigger_element=Element.DENDRO,
        base_element=Element.HYDRO,
        base_damage=100.0,
        scaling_ratio=2.4,
        damage_key="bloom",
        aoe_radius=5.0,
        shared_cd_ms=0.0,
        is_transformative=True,
    ),
    ReactionType.HYPERBLOOM: ReactionConfig(
        reaction_type=ReactionType.HYPERBLOOM,
        trigger_element=Element.ELECTRO,
        base_element=Element.DENDRO,  # Triggered by electro on bloom seed
        base_damage=160.0,
        scaling_ratio=4.0,
        damage_key="hyperbloom",
        aoe_radius=3.0,
        shared_cd_ms=0.0,
        is_transformative=True,
    ),
    ReactionType.BURGEON: ReactionConfig(
        reaction_type=ReactionType.BURGEON,
        trigger_element=Element.PYRO,
        base_element=Element.DENDRO,  # Triggered by pyro on bloom seed
        base_damage=160.0,
        scaling_ratio=4.0,
        damage_key="burgeon",
        aoe_radius=5.0,
        shared_cd_ms=0.0,
        is_transformative=True,
    ),
    ReactionType.QUICKEN: ReactionConfig(
        reaction_type=ReactionType.QUICKEN,
        trigger_element=Element.ELECTRO,
        base_element=Element.DENDRO,
        base_damage=0.0,
        scaling_ratio=0.0,
        damage_key="quicken",
        aoe_radius=0.0,
        shared_cd_ms=0.0,
        is_transformative=True,
    ),
    ReactionType.AGGRAVATE: ReactionConfig(
        reaction_type=ReactionType.AGGRAVATE,
        trigger_element=Element.ELECTRO,
        base_element=Element.NONE,  # Quicken aura
        base_damage=0.0,  # Aggravate adds flat damage
        scaling_ratio=0.0,
        damage_key="aggravate",
        aoe_radius=0.0,
        shared_cd_ms=0.0,
        is_transformative=False,
    ),
    ReactionType.SPREAD: ReactionConfig(
        reaction_type=ReactionType.SPREAD,
        trigger_element=Element.DENDRO,
        base_element=Element.NONE,  # Quicken aura
        base_damage=0.0,
        scaling_ratio=0.0,
        damage_key="spread",
        aoe_radius=0.0,
        shared_cd_ms=0.0,
        is_transformative=False,
    ),
}


# Multiplier tables (simplified)
_VAPORIZE_MELT_MULT = {
    "pyro_trigger": 2.0,   # Pyro trigger on hydro/cryo base
    "hydro_trigger": 1.5,   # Hydro trigger on pyro base
    "cryo_trigger": 2.0,    # Cryo trigger on pyro base (reverse melt)
}

# Level-based base damage for transformative reactions
_TRANSFORMATIVE_BASE_DAMAGE = {
    1: 40, 20: 80, 40: 120, 60: 160, 80: 200, 90: 240,
}


class ReactionDamageCalculator:
    """Calculates elemental reaction damage.

    Two types of reactions:
    1. Ampliative (Vaporize, Melt, Aggravate, Spread): Scale with ATK, affected by damage%
    2. Transformative (Overloaded, Superconduct, etc.): Scale with Level + EM, fixed hit

    Damage formula:
    - Transformative: Base(Level) * (1 + EM * ScalingRatio / 1000)
    - Ampliative: SourceDamage * Multiplier (vaporize/melt only)
    """

    def __init__(self) -> None:
        self._elemental_aura_tracker: dict[str, float] = {}  # target_id -> aura_time
        self._last_reaction_time: dict[ReactionType, float] = {}

    def calculate_reaction_damage(
        self,
        reaction_type: ReactionType,
        trigger_element: Element,
        base_element: Element,
        source_damage: float,
        character_stats: CharacterStats,
        target_level: int,
        aura_duration_ms: float = 0.0,
    ) -> ReactionDamageResult:
        """Calculate damage for an elemental reaction.

        Args:
            reaction_type: Type of reaction.
            trigger_element: Element that triggered.
            base_element: Element on target before trigger.
            source_damage: Damage of triggering skill.
            character_stats: Character stats for scaling.
            target_level: Level of target enemy.
            aura_duration_ms: Remaining aura duration.

        Returns:
            ReactionDamageResult with calculated damage.
        """
        config = _REACTION_CONFIGS.get(reaction_type)
        if config is None:
            return self._empty_result(reaction_type)

        # Get base damage for level
        base_dmg = self._get_transformative_base(target_level, config.base_damage)

        # Calculate EM bonus
        em = character_stats.elemental_mastery
        em_bonus = self._calculate_em_bonus(em, config.scaling_ratio)

        # Determine final damage
        if config.is_transformative:
            # Transformative reactions
            scaled = base_dmg * (1 + em_bonus)
            final = scaled
            aoe_mult = 1.0 if config.aoe_radius <= 0 else 0.5  # AoE is 50% damage
        else:
            # Ampliative reactions (vaporize/melt)
            if reaction_type == ReactionType.VAPORIZE:
                mult = _VAPORIZE_MELT_MULT["pyro_trigger"] if trigger_element == Element.PYRO else 1.5
            elif reaction_type == ReactionType.MELT:
                mult = _VAPORIZE_MELT_MULT["cryo_trigger"] if trigger_element == Element.CRYO else 1.5
            else:
                mult = 1.0

            # Apply mult to source damage, then EM bonus
            scaled = source_damage * mult
            final = scaled * (1 + em_bonus * 0.5)  # EM has less effect on ampliative
            aoe_mult = 1.0

        # Check if critical (crit doesn't apply to transformative)
        is_crit = not config.is_transformative and (character_stats.crit_rate > 0.9)
        if is_crit:
            final *= (1 + character_stats.crit_damage)

        return ReactionDamageResult(
            reaction_type=reaction_type,
            base_damage=base_dmg,
            scaled_damage=scaled,
            final_damage=math.ceil(final),
            is_critical=is_crit,
            elemental_mastery_bonus=em_bonus,
            aoe_mult=aoe_mult,
        )

    def _get_transformative_base(self, level: int, default_base: float) -> float:
        """Get base damage for transformative reactions based on level."""
        # Find closest level in table
        levels = sorted(_TRANSFORMATIVE_BASE_DAMAGE.keys())
        for i, lvl in enumerate(levels):
            if level <= lvl:
                return float(_TRANSFORMATIVE_BASE_DAMAGE[lvl])
        return default_base

    def _calculate_em_bonus(self, elemental_mastery: float, scaling_ratio: float) -> float:
        """Calculate elemental mastery bonus.

        Formula: EM / (EM + 1000) * scaling_ratio
        At 100 EM: ~9.1% bonus (for 3.2 scaling)
        At 200 EM: ~17.6% bonus
        At 300 EM: ~24.9% bonus
        """
        if scaling_ratio <= 0:
            return 0.0

        return (elemental_mastery / (elemental_mastery + 1000)) * (scaling_ratio / 100)

    def _empty_result(self, reaction_type: ReactionType) -> ReactionDamageResult:
        """Return empty result for unknown reaction."""
        return ReactionDamageResult(
            reaction_type=reaction_type,
            base_damage=0.0,
            scaled_damage=0.0,
            final_damage=0.0,
            is_critical=False,
            elemental_mastery_bonus=0.0,
            aoe_mult=1.0,
        )

    def detect_reaction(
        self,
        trigger_element: Element,
        target_id: str,
        current_aura: Element | None,
        aura_duration_ms: float,
    ) -> ReactionType | None:
        """Detect if a reaction occurred.

        Args:
            trigger_element: Element of triggering attack.
            target_id: ID of target enemy.
            current_aura: Current elemental aura on target.
            aura_duration_ms: Remaining aura duration.

        Returns:
            Detected ReactionType, or None if no reaction.
        """
        if current_aura is None or current_aura == Element.NONE:
            return None

        # Map element pairs to reactions
        reaction_map: dict[tuple[Element, Element], ReactionType] = {
            (Element.PYRO, Element.HYDRO): ReactionType.VAPORIZE,
            (Element.HYDRO, Element.PYRO): ReactionType.VAPORIZE,
            (Element.PYRO, Element.CRYO): ReactionType.MELT,
            (Element.CRYO, Element.PYRO): ReactionType.MELT,
            (Element.PYRO, Element.ELECTRO): ReactionType.OVERLOADED,
            (Element.ELECTRO, Element.PYRO): ReactionType.OVERLOADED,
            (Element.CRYO, Element.ELECTRO): ReactionType.SUPERCONDUCT,
            (Element.ELECTRO, Element.CRYO): ReactionType.SUPERCONDUCT,
            (Element.HYDRO, Element.ELECTRO): ReactionType.ELECTRO_CHARGED,
            (Element.ELECTRO, Element.HYDRO): ReactionType.ELECTRO_CHARGED,
            (Element.ANEMO, Element.PYRO): ReactionType.SWIRL,
            (Element.ANEMO, Element.HYDRO): ReactionType.SWIRL,
            (Element.ANEMO, Element.ELECTRO): ReactionType.SWIRL,
            (Element.ANEMO, Element.CRYO): ReactionType.SWIRL,
            (Element.GEO, Element.PYRO): ReactionType.CRYSTALLIZE,
            (Element.GEO, Element.HYDRO): ReactionType.CRYSTALLIZE,
            (Element.CRYO, Element.HYDRO): ReactionType.FREEZE,
            (Element.HYDRO, Element.CRYO): ReactionType.FREEZE,
            (Element.PYRO, Element.DENDRO): ReactionType.BURN,
            (Element.DENDRO, Element.PYRO): ReactionType.BURN,
            (Element.DENDRO, Element.HYDRO): ReactionType.BLOOM,
            (Element.HYDRO, Element.DENDRO): ReactionType.BLOOM,
            (Element.ELECTRO, Element.DENDRO): ReactionType.HYPERBLOOM,
            (Element.DENDRO, Element.ELECTRO): ReactionType.QUICKEN,
            (Element.PYRO, Element.DENDRO): ReactionType.BURGEON,  # On bloom seed
            (Element.ELECTRO, Element.QUICKEN): ReactionType.AGGRAVATE,
            (Element.DENDRO, Element.QUICKEN): ReactionType.SPREAD,
        }

        key = (trigger_element, current_aura)
        return reaction_map.get(key)

    def update_aura(
        self,
        target_id: str,
        element: Element,
        duration_ms: float,
        timestamp: float | None = None,
    ) -> None:
        """Update elemental aura on target."""
        now = timestamp if timestamp is not None else 0.0  # Use relative time
        self._elemental_aura_tracker[target_id] = element

    def clear_aura(self, target_id: str) -> None:
        """Clear aura on target after reaction."""
        self._elemental_aura_tracker.pop(target_id, None)

    def get_current_aura(self, target_id: str) -> Element | None:
        """Get current aura element on target."""
        return self._elemental_aura_tracker.get(target_id)

    def estimate_team_dps_with_reactions(
        self,
        team_elements: list[str],
        character_stats: list[CharacterStats],
        target_level: int,
    ) -> float:
        """Estimate team DPS including reaction damage.

        Args:
            team_elements: List of character elements.
            character_stats: List of character stats.
            target_level: Enemy level.

        Returns:
            Estimated DPS with reactions.
        """
        # Find possible reactions
        element_set = set(team_elements)
        possible_reactions = self._find_possible_reactions(element_set)

        total_dps = 0.0

        for char_elem, stats in zip(team_elements, character_stats):
            # Base damage (simplified)
            base_dps = stats.base_attack * 0.5  # Rough estimate

            # Add reaction damage contribution
            for reaction in possible_reactions:
                config = _REACTION_CONFIGS.get(reaction)
                if config is None:
                    continue

                # Check if element matches
                if char_elem != config.trigger_element.value:
                    continue

                result = self.calculate_reaction_damage(
                    reaction,
                    Element(char_elem),
                    Element.NONE,
                    base_dps,
                    stats,
                    target_level,
                )

                # Assume reaction triggers every 3 seconds
                reaction_dps = result.final_damage / 3.0
                total_dps += reaction_dps

        return total_dps

    def _find_possible_reactions(
        self,
        element_set: set[str],
    ) -> list[ReactionType]:
        """Find reactions possible with given elements."""
        possible: list[ReactionType] = []
        for reaction_type, config in _REACTION_CONFIGS.items():
            if config.trigger_element.value in element_set:
                # At least trigger element needed
                # For 2-element reactions, would need to check base
                if config.base_element == Element.NONE or config.base_element.value in element_set:
                    possible.append(reaction_type)
        return possible

    def reset(self) -> None:
        """Reset calculator state."""
        self._elemental_aura_tracker.clear()
        self._last_reaction_time.clear()