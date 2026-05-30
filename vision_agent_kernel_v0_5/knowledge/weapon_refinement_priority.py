"""Multi-character weapon refinement priority system.

Determines optimal refinement rank for weapons shared between characters,
balancing damage gains against investment costs. Covers R-38.

Integrates with:
- knowledge/genshin_f2p_builds.py for build data
- planning/character_build_planner.py for build planning
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from knowledge.genshin_f2p_builds import CharacterBuild


# ---------------------------------------------------------------------------
# Refinement tier definitions
# ---------------------------------------------------------------------------

class RefinementTier(str, Enum):
    R1 = "r1"
    R2 = "r2"
    R3 = "r3"
    R4 = "r4"
    R5 = "r5"


@dataclass(slots=True, frozen=True)
class RefinementBonus:
    """Bonus percentage at each refinement rank."""
    passive_name: str
    r1_percent: float = 0.0
    r2_percent: float = 0.0
    r3_percent: float = 0.0
    r4_percent: float = 0.0
    r5_percent: float = 0.0

    def at_rank(self, rank: int) -> float:
        rank = min(max(rank, 1), 5)
        return getattr(self, f"r{rank}_percent", 0.0)

    def gain_from_rank(self, from_rank: int, to_rank: int) -> float:
        return self.at_rank(to_rank) - self.at_rank(from_rank)


# Standard weapon passive bonuses (approximate)
WEAPON_PASSIVE_DB: dict[str, RefinementBonus] = {
    "the_catch": RefinementBonus(
        passive_name="潮流",
        r1_percent=12.0, r2_percent=15.0, r3_percent=18.0, r4_percent=21.0, r5_percent=24.0,
    ),
    "sacrificial_sword": RefinementBonus(
        passive_name="涌动",
        r1_percent=16.0, r2_percent=20.0, r3_percent=24.0, r4_percent=28.0, r5_percent=32.0,
    ),
    "favonius_sword": RefinementBonus(
        passive_name="凛冽",
        r1_percent=20.0, r2_percent=25.0, r3_percent=30.0, r4_percent=35.0, r5_percent=40.0,
    ),
    "amenoma_kageuchi": RefinementBonus(
        passive_name="霞风",
        r1_percent=16.0, r2_percent=20.0, r3_percent=24.0, r4_percent=28.0, r5_percent=32.0,
    ),
    "harbinger_of_dawn": RefinementBonus(
        passive_name="展翅",
        r1_percent=14.0, r2_percent=17.5, r3_percent=21.0, r4_percent=24.5, r5_percent=28.0,
    ),
    "dragons_bane": RefinementBonus(
        passive_name="撕风",
        r1_percent=20.0, r2_percent=24.0, r3_percent=28.0, r4_percent=32.0, r5_percent=36.0,
    ),
    "kitain_cross_spear": RefinementBonus(
        passive_name="刺破",
        r1_percent=12.0, r2_percent=15.0, r3_percent=18.0, r4_percent=21.0, r5_percent=24.0,
    ),
    "whiteblind": RefinementBonus(
        passive_name="粉碎",
        r1_percent=15.0, r2_percent=18.75, r3_percent=22.5, r4_percent=26.25, r5_percent=30.0,
    ),
    "prototype_archaic": RefinementBonus(
        passive_name="破碎",
        r1_percent=20.0, r2_percent=25.0, r3_percent=30.0, r4_percent=35.0, r5_percent=40.0,
    ),
    "the_stringless": RefinementBonus(
        passive_name="绝弦",
        r1_percent=16.0, r2_percent=20.0, r3_percent=24.0, r4_percent=28.0, r5_percent=32.0,
    ),
    "favonius_warbow": RefinementBonus(
        passive_name="疾步",
        r1_percent=20.0, r2_percent=25.0, r3_percent=30.0, r4_percent=35.0, r5_percent=40.0,
    ),
    "rust": RefinementBonus(
        passive_name="热诚",
        r1_percent=20.0, r2_percent=25.0, r3_percent=30.0, r4_percent=35.0, r5_percent=40.0,
    ),
    "thrilling_tales": RefinementBonus(
        passive_name="守护",
        r1_percent=15.0, r2_percent=18.0, r3_percent=21.0, r4_percent=24.0, r5_percent=27.0,
    ),
    "prototype_amber": RefinementBonus(
        passive_name="催化",
        r1_percent=12.0, r2_percent=15.0, r3_percent=18.0, r4_percent=21.0, r5_percent=24.0,
    ),
    "mappa_mare": RefinementBonus(
        passive_name="轻风",
        r1_percent=16.0, r2_percent=20.0, r3_percent=24.0, r4_percent=28.0, r5_percent=32.0,
    ),
    "sapwood_blade": RefinementBonus(
        passive_name="绿叶",
        r1_percent=10.0, r2_percent=12.5, r3_percent=15.0, r4_percent=17.5, r5_percent=20.0,
    ),
    "prototype_rancour": RefinementBonus(
        passive_name="精工",
        r1_percent=16.0, r2_percent=20.0, r3_percent=24.0, r4_percent=28.0, r5_percent=32.0,
    ),
}


# Refinement costs (mora per rank)
REFINE_MORA_COST: dict[int, int] = {
    2: 5000,
    3: 15000,
    4: 35000,
    5: 75000,
}


# ---------------------------------------------------------------------------
# Shared weapon data
# ---------------------------------------------------------------------------

# Weapons that can be shared between multiple characters
SHARED_WEAPONS: dict[str, tuple[str, ...]] = {
    "The Catch": ("xiangling", "raiden", "fischl"),
    "Sacrificial Sword": ("xingqiu", "lisa"),
    "Favonius Sword": ("bennett", "kaeya", "kuki"),
    "Amenoma Kageuchi": ("kaeya", "ayaka", "keqing"),
    "Dragon's Bane": ("xiangling", "hu_tao", "thoma"),
    "Whiteblind": ("noelle", "itto"),
    "The Stringless": ("fischl", "venti", "tartaglia"),
    "Favonius Warbow": ("diona", "ganyu", "fischl"),
    "Prototype Archaic": ("beidou", "xinyan", "diluc"),
}


# Characters who benefit most from each weapon (for refinement priority)
WEAPON_PRIORITY_CHARS: dict[str, tuple[str, ...]] = {
    "the_catch": ("xiangling", "raiden", "fischl"),
    "sacrificial_sword": ("xingqiu", "lisa"),
    "favonius_sword": ("bennett", "kaeya"),
    "amenoma_kageuchi": ("kaeya", "ayaka"),
    "dragons_bane": ("xiangling", "hu_tao"),
    "whiteblind": ("noelle", "itto"),
    "the_stringless": ("fischl", "venti"),
    "favonius_warbow": ("diona", "ganyu"),
    "prototype_archaic": ("beidou", "diluc"),
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CharacterWeaponState:
    """Current state of a character's weapon."""
    character_id: str
    weapon_name: str
    current_refinement: int = 1
    is_best_option: bool = False  # Is this the character's best weapon option?


@dataclass(slots=True)
class RefinementRecommendation:
    """A recommendation for weapon refinement."""
    weapon_name: str
    target_rank: int
    priority_characters: tuple[str, ...]
    damage_gain_pct: float
    mora_cost: int
    roi_score: float  # damage_gain / mora_cost * 1000


@dataclass(slots=True)
class MultiCharacterRefinementPlan:
    """Plan for refining weapons across multiple characters."""
    recommendations: list[RefinementRecommendation] = field(default_factory=list)
    total_mora_cost: int = 0
    priority_order: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Refinement Priority Calculator
# ---------------------------------------------------------------------------

class RefinementPriorityCalculator:
    """Calculates optimal refinement priorities for multi-character weapon allocation.

    Determines which character should receive the weapon at which refinement rank
    to maximize overall team damage while minimizing investment costs.
    """

    # Characters sorted by how much they benefit from refinement (off-field > on-field)
    # Off-field DPS characters benefit more from refinement (their buffs/debuffs scale with it)
    OFF_FIELD_BENEFIT_SCORE: dict[str, float] = {
        "xiangling": 1.0,   # Highest: benefits from R5 The Catch
        "xingqiu": 0.9,     # Off-field hydro application
        "bennett": 0.7,     # Buffing atk% benefits from refinement
        "kaeya": 0.6,      # Off-field cryo
        "fischl": 0.85,     # Off-field electro
        "diona": 0.5,       # Off-field shield/heal
    }

    def calculate_multi_char_priority(
        self,
        weapon_name: str,
        characters: list[CharacterWeaponState],
        available_duplicates: int,
        mora_budget: int,
    ) -> MultiCharacterRefinementPlan:
        """Calculate optimal refinement plan for a weapon shared between characters.

        Args:
            weapon_name: Name of the weapon
            characters: List of characters using this weapon
            available_duplicates: Number of duplicate weapons available
            mora_budget: Available mora for refinement

        Returns:
            MultiCharacterRefinementPlan with recommended refinement order
        """
        plan = MultiCharacterRefinementPlan()
        weapon_lower = weapon_name.lower()

        # Get passive data
        passive = WEAPON_PASSIVE_DB.get(weapon_lower)
        if passive is None:
            return plan

        # Score each character's benefit from refinement
        char_scores: list[tuple[CharacterWeaponState, float]] = []
        for char in characters:
            benefit_score = self.OFF_FIELD_BENEFIT_SCORE.get(char.character_id, 0.5)
            # Characters who need refinement more get priority
            current_rank = char.current_refinement
            remaining_gap = 5 - current_rank
            # Weight by how much room for improvement
            gap_bonus = remaining_gap / 5.0
            priority_score = benefit_score * (1.0 + gap_bonus)
            char_scores.append((char, priority_score))

        # Sort by priority score
        char_scores.sort(key=lambda x: x[1], reverse=True)

        # Calculate recommendations
        remaining_duplicates = available_duplicates
        current_rank = 1
        total_mora = 0

        for char, score in char_scores:
            if remaining_duplicates <= 0:
                break
            if current_rank >= 5:
                break

            # Calculate ROI for each potential refinement rank
            best_rank = current_rank
            best_roi = 0.0
            for target_rank in range(current_rank + 1, 6):
                if remaining_duplicates < (target_rank - current_rank):
                    continue
                gain = passive.gain_from_rank(current_rank, target_rank)
                cost = sum(
                    REFINE_MORA_COST.get(r, 0)
                    for r in range(current_rank + 1, target_rank + 1)
                )
                if cost > mora_budget - total_mora:
                    continue
                roi = gain / max(cost, 1) * 1000
                if roi > best_roi:
                    best_roi = roi
                    best_rank = target_rank

            if best_rank > current_rank:
                gain = passive.gain_from_rank(current_rank, best_rank)
                cost = sum(
                    REFINE_MORA_COST.get(r, 0)
                    for r in range(current_rank + 1, best_rank + 1)
                )

                plan.recommendations.append(RefinementRecommendation(
                    weapon_name=weapon_name,
                    target_rank=best_rank,
                    priority_characters=(char.character_id,),
                    damage_gain_pct=gain,
                    mora_cost=cost,
                    roi_score=best_roi,
                ))
                plan.priority_order.append(char.character_id)
                total_mora += cost
                remaining_duplicates -= best_rank - current_rank
                current_rank = best_rank

        plan.total_mora_cost = total_mora
        plan.recommendations.sort(key=lambda x: x.roi_score, reverse=True)

        return plan

    def get_optimal_refinement_rank(
        self,
        weapon_name: str,
        character_id: str,
        current_rank: int,
        available_duplicates: int,
    ) -> int:
        """Determine optimal refinement rank for a single character.

        Uses a simple ROI calculation to decide whether refinement is worth it.
        """
        weapon_lower = weapon_name.lower()
        passive = WEAPON_PASSIVE_DB.get(weapon_lower)
        if passive is None:
            return current_rank

        if available_duplicates <= 0:
            return current_rank

        benefit = self.OFF_FIELD_BENEFIT_SCORE.get(character_id, 0.5)
        target_rank = min(current_rank + available_duplicates, 5)
        gain = passive.gain_from_rank(current_rank, target_rank)

        # Threshold: only refine if damage gain exceeds 5% at current level
        if gain >= 5.0 * benefit:
            return target_rank

        # For high-value characters (benefit > 0.8), accept lower thresholds
        if benefit >= 0.8 and gain >= 3.0:
            return target_rank

        return current_rank

    def recommend_refinement_priority(
        self,
        weapons_inventory: dict[str, int],  # weapon_name -> duplicate count
        characters: list[CharacterWeaponState],
        mora_budget: int,
    ) -> list[RefinementRecommendation]:
        """Recommend which weapons to refine and in what order.

        Returns a priority-ordered list of refinement recommendations.
        """
        recommendations: list[RefinementRecommendation] = []

        # Group characters by weapon
        weapon_chars: dict[str, list[CharacterWeaponState]] = {}
        for char in characters:
            wpn = char.weapon_name
            weapon_chars.setdefault(wpn, []).append(char)

        # Calculate priority for each weapon
        for weapon_name, chars in weapon_chars.items():
            duplicates = weapons_inventory.get(weapon_name, 0)
            if duplicates <= 0:
                continue

            plan = self.calculate_multi_char_priority(
                weapon_name, chars, duplicates, mora_budget
            )
            recommendations.extend(plan.recommendations)

        # Sort by ROI score
        recommendations.sort(key=lambda x: x.roi_score, reverse=True)
        return recommendations

    @staticmethod
    def get_refinement_cost(from_rank: int, to_rank: int) -> int:
        """Calculate mora cost for refining from one rank to another."""
        return sum(
            REFINE_MORA_COST.get(r, 0)
            for r in range(from_rank + 1, to_rank + 1)
        )

    @staticmethod
    def is_worth_refining(
        weapon_name: str,
        current_rank: int,
        target_rank: int,
        character_role: str,
    ) -> bool:
        """Quick check if refinement is worth the investment.

        Args:
            weapon_name: Weapon being refined
            current_rank: Current refinement rank (1-5)
            target_rank: Target refinement rank
            character_role: DPS/support/healer role

        Returns:
            True if the refinement is worth the investment
        """
        if target_rank <= current_rank:
            return False
        if target_rank > 5:
            return False

        weapon_lower = weapon_name.lower()
        passive = WEAPON_PASSIVE_DB.get(weapon_lower)
        if passive is None:
            return False

        gain = passive.gain_from_rank(current_rank, target_rank)

        # DPS characters benefit more from refinement
        if character_role in ("main_dps", "off_field_dps"):
            return gain >= 4.0
        if character_role == "support":
            return gain >= 6.0
        return gain >= 8.0