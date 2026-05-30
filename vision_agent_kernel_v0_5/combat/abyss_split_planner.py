"""Spiral Abyss team separation and investment balance planning.

S-29: AbyssTeamSplitPlanner - Upper/lower half separation planning

This module extends spiral_abyss.py with:
- Upper and lower half separation planning
- Diversity vs vertical investment balance
- Team composition optimization for both halves
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# S-29: Abyss Team Split Planning
# ---------------------------------------------------------------------------

class InvestmentStrategy(str, Enum):
    """Strategy for team investment balance."""
    VERTICAL = "vertical"      # Deep investment in one team
    HORIZONTAL = "horizontal"  # Spread investment across both teams
    HYBRID = "hybrid"          # One team deep, one team adequate
    FOCUS_FLOOR = "focus_floor"  # Optimize for specific floor


@dataclass(frozen=True, slots=True)
class HalfRequirements:
    """Requirements analysis for one half of Abyss."""
    half_id: int               # 1 = first half, 2 = second half
    recommended_elements: tuple[str, ...]
    recommended_roles: tuple[str, ...]
    estimated_difficulty: float  # 1.0-10.0
    key_enemies: tuple[str, ...]
    recommended_dps_range: tuple[int, int]  # min-max level


@dataclass(frozen=True, slots=True)
class SplitAnalysis:
    """Analysis of team split strategy."""
    upper_half: HalfRequirements
    lower_half: HalfRequirements
    recommended_strategy: InvestmentStrategy
    diversity_score: float     # 0.0-1.0, variety of coverage
    vertical_score: float      # 0.0-1.0, depth of investment
    team1_recommendation: str
    team2_recommendation: str
    investment_split: tuple[float, float]  # % for team1, team2


@dataclass(frozen=True, slots=True)
class CharacterInvestorProfile:
    """Investment profile for a character."""
    name: str
    current_level: int
    current_talent: int
    artifact_score: float       # 0.0-1.0
    weapon_level: int
    role_flexibility: tuple[str, ...]  # Roles this char can fill
    synergy_score: float        # 0.0-1.0, team fit


@dataclass(frozen=True, slots=True)
class SplitPlan:
    """Complete team split plan for Abyss."""
    floor_target: int
    strategy: InvestmentStrategy
    team1_composition: tuple[str, ...]  # Character names
    team2_composition: tuple[str, ...]
    team1_roles: tuple[str, ...]
    team2_roles: tuple[str, ...]
    investment_allocation: tuple[tuple[str, float], ...]  # char -> % of investment
    priority_order: tuple[str, ...]  # Priority for investment
    expected_stars: tuple[int, int]  # realistic, optimistic


class AbyssTeamSplitPlanner:
    """Plans Spiral Abyss team splitting with investment balance.

    S-29: Separates upper/lower half teams and balances diversity vs
    vertical investment for optimal Abyss progression.
    """

    # Floor difficulty estimates
    FLOOR_DIFFICULTY: dict[int, tuple[float, float]] = {
        9: (3.0, 5.0),
        10: (4.0, 6.0),
        11: (5.5, 7.0),
        12: (7.0, 10.0),
    }

    # Common Abyss enemy elemental resistances
    ELEMENTAL_WEAKNESSES: dict[str, str] = {
        "pyro_Slime": "hydro",
        "hydro_slime": "pyro",
        "electro_slime": "pyro",
        "cryo_slime": "pyro",
        "pyro_hilichurl": "hydro",
        "hilichurl": "pyro",
        "abyss_mage": "pyro",
        "fatui_agent": "hydro",
        "fatui_cipher": "pyro",
        "ruin_guard": "geo",
        "primo_geovishap": "cryo",
    }

    def __init__(self) -> None:
        self._half_analyses: dict[int, tuple[HalfRequirements, HalfRequirements]] = {}

    def analyze_floor_requirements(
        self,
        floor_number: int,
        chamber_enemies: dict[int, dict[str, list[str]]] | None = None,
    ) -> tuple[HalfRequirements, HalfRequirements]:
        """Analyze requirements for upper and lower halves of a floor."""
        difficulty_range = self.FLOOR_DIFFICULTY.get(
            floor_number, (5.0, 7.0)
        )

        # Default analysis for standard Abyss floors
        if floor_number <= 9:
            upper_elements = ("pyro", "hydro", "electro")
            lower_elements = ("pyro", "cryo", "electro")
        elif floor_number <= 11:
            upper_elements = ("pyro", "cryo", "electro")
            lower_elements = ("pyro", "hydro", "geo")
        else:
            upper_elements = ("pyro", "hydro", "cryo", "electro")
            lower_elements = ("pyro", "cryo", "geo", "anemo")

        upper = HalfRequirements(
            half_id=1,
            recommended_elements=upper_elements,
            recommended_roles=("main_dps", "sub_dps", "support", "healer"),
            estimated_difficulty=difficulty_range[0],
            key_enemies=("abyss_mage", "fatui", "hilichurl"),
            recommended_dps_range=(60, 80),
        )

        lower = HalfRequirements(
            half_id=2,
            recommended_elements=lower_elements,
            recommended_roles=("main_dps", "sub_dps", "support", "healer"),
            estimated_difficulty=difficulty_range[1],
            key_enemies=("ruin_guard", "fatui_elite", "abyss_lector"),
            recommended_dps_range=(70, 90),
        )

        return upper, lower

    def analyze_split_strategy(
        self,
        available_characters: Sequence[CharacterInvestorProfile],
        floor_target: int,
        total_investment_points: float,
    ) -> SplitAnalysis:
        """Analyze optimal split strategy for given roster and floor."""
        upper, lower = self.analyze_floor_requirements(floor_target)
        diff_avg = (upper.estimated_difficulty + lower.estimated_difficulty) / 2

        # Count characters by element and role
        element_counts: dict[str, int] = {}
        high_investment_count = 0
        flex_chars: list[CharacterInvestorProfile] = []

        for char in available_characters:
            if char.current_level >= 80:
                high_investment_count += 1

            for elem in upper.recommended_elements + lower.recommended_elements:
                if elem in char.name.lower() or any(
                    elem in role for role in char.role_flexibility
                ):
                    element_counts[elem] = element_counts.get(elem, 0) + 1

            if len(char.role_flexibility) >= 3:
                flex_chars.append(char)

        # Calculate diversity score
        unique_elements = len(element_counts)
        diversity_score = min(1.0, unique_elements / 4)

        # Calculate vertical score
        vertical_score = min(1.0, high_investment_count / 4)

        # Determine strategy
        if high_investment_count >= 6:
            strategy = InvestmentStrategy.HYBRID
            investment_split = (0.55, 0.45)
            team1_rec = "Focus investment on main DPS, adequate support"
            team2_rec = "Secondary DPS with flexible characters"
        elif high_investment_count >= 4:
            strategy = InvestmentStrategy.FOCUS_FLOOR
            investment_split = (0.65, 0.35)
            team1_rec = "Deep investment in primary team"
            team2_rec = "Budget build for secondary team"
        elif high_investment_count >= 2:
            strategy = InvestmentStrategy.VERTICAL
            investment_split = (0.80, 0.20)
            team1_rec = "Concentrate all resources in one team"
            team2_rec = "Minimal investment, just passable"
        else:
            strategy = InvestmentStrategy.HORIZONTAL
            investment_split = (0.50, 0.50)
            team1_rec = "Spread investment evenly"
            team2_rec = "Build balanced secondary team"

        # Adjust for difficulty
        if diff_avg >= 8.0:
            # Floor 12: need more investment variety
            investment_split = (
                investment_split[0] * 0.8 + 0.1,
                investment_split[1] * 0.8 + 0.1,
            )

        return SplitAnalysis(
            upper_half=upper,
            lower_half=lower,
            recommended_strategy=strategy,
            diversity_score=diversity_score,
            vertical_score=vertical_score,
            team1_recommendation=team1_rec,
            team2_recommendation=team2_rec,
            investment_split=tuple(investment_split),
        )

    def create_split_plan(
        self,
        roster: Sequence[CharacterInvestorProfile],
        floor_target: int,
        total_investment_points: float,
    ) -> SplitPlan:
        """Create complete team split plan."""
        analysis = self.analyze_split_strategy(
            roster, floor_target, total_investment_points
        )

        # Sort characters by investment for team assignment
        sorted_chars = sorted(
            roster,
            key=lambda c: (
                c.current_level + c.artifact_score * 10,
                -len(c.role_flexibility)  # Prefer specialists
            ),
            reverse=True,
        )

        # Assign to teams based on strategy
        if analysis.strategy in (InvestmentStrategy.VERTICAL, InvestmentStrategy.HYBRID):
            team1_chars = sorted_chars[:4]
            team2_chars = sorted_chars[4:8] if len(sorted_chars) >= 8 else sorted_chars[4:]
        else:
            # Split evenly but respect element needs
            team1_chars = []
            team2_chars = []
            for i, char in enumerate(sorted_chars):
                if i % 2 == 0:
                    team1_chars.append(char)
                else:
                    team2_chars.append(char)

        # Generate role assignments
        team1_roles = self._assign_roles(
            team1_chars, analysis.upper_half.recommended_roles
        )
        team2_roles = self._assign_roles(
            team2_chars, analysis.lower_half.recommended_roles
        )

        # Generate investment allocation
        investment_allocation: list[tuple[str, float]] = []
        investment_points = list(analysis.investment_split)

        for i, char in enumerate(team1_chars):
            pct = investment_points[0] / len(team1_chars) if team1_chars else 0.0
            investment_allocation.append((char.name, pct))

        for i, char in enumerate(team2_chars):
            pct = investment_points[1] / len(team2_chars) if team2_chars else 0.0
            investment_allocation.append((char.name, pct))

        # Priority order
        priority_order = tuple(c.name for c in team1_chars) + tuple(
            c.name for c in team2_chars
        )

        # Expected stars
        if analysis.strategy == InvestmentStrategy.VERTICAL:
            expected = (6, 9)  # Team 1 carries, Team 2 struggles
        elif analysis.strategy == InvestmentStrategy.HORIZONTAL:
            expected = (9, 9)  # Both teams adequate
        else:
            expected = (8, 9)  # Balanced

        return SplitPlan(
            floor_target=floor_target,
            strategy=analysis.recommended_strategy,
            team1_composition=tuple(c.name for c in team1_chars),
            team2_composition=tuple(c.name for c in team2_chars),
            team1_roles=team1_roles,
            team2_roles=team2_roles,
            investment_allocation=tuple(investment_allocation),
            priority_order=priority_order,
            expected_stars=expected,
        )

    def _assign_roles(
        self,
        characters: list[CharacterInvestorProfile],
        recommended_roles: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Assign roles to characters based on flexibility and level."""
        if not characters:
            return ()

        assigned: list[str] = []
        available_roles = list(recommended_roles)

        # Priority: level, then flexibility
        sorted_chars = sorted(
            characters,
            key=lambda c: (c.current_level, -len(c.role_flexibility)),
            reverse=True,
        )

        for char in sorted_chars:
            # Find best matching role
            role = "support"  # Default
            for preferred in ("main_dps", "sub_dps", "healer", "support"):
                if preferred in char.role_flexibility:
                    role = preferred
                    break

            assigned.append(role)

        return tuple(assigned)


# ---------------------------------------------------------------------------
# S-29 Integration: Extend spiral_abyss.py
# ---------------------------------------------------------------------------

def create_abyss_split_state(
    floor_state: object,
    split_plan: SplitPlan,
) -> dict[str, object]:
    """Extend AbyssFloorState with split planning info."""
    return {
        "split_plan": split_plan,
        "strategy": split_plan.strategy.value,
        "investment_split": split_plan.investment_allocation,
        "expected_stars": split_plan.expected_stars,
    }