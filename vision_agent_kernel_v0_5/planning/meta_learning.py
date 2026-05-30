"""Meta-learning system: combat experience, boss pattern learning, strategy iteration.

Implements learning loops that improve combat performance over time by recording
fight outcomes, identifying patterns, and adjusting strategies.
Covers L-01 through L-08.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Experience record types
# ---------------------------------------------------------------------------

class Outcome(Enum):
    WIN = "win"
    LOSS = "loss"
    TIMEOUT = "timeout"
    RETREAT = "retreat"


@dataclass(slots=True, frozen=True)
class FightRecord:
    """Record of a single combat encounter."""
    encounter_id: str
    enemy_type: str          # "boss", "elite", "mob", "domain"
    enemy_name: str
    team: tuple[str, ...]    # character IDs
    outcome: Outcome
    duration_sec: float
    damage_dealt: float = 0.0
    damage_taken: float = 0.0
    deaths: int = 0
    food_used: int = 0
    burst_uses: tuple[int, ...] = ()  # burst use count per character
    phase_reached: int = 1
    key_events: tuple[str, ...] = ()


@dataclass(slots=True)
class EnemyProfile:
    """Accumulated knowledge about a specific enemy type."""
    enemy_name: str
    total_encounters: int = 0
    wins: int = 0
    avg_duration_sec: float = 0.0
    best_duration_sec: float = 0.0
    best_team: tuple[str, ...] = ()
    element_weaknesses: tuple[str, ...] = ()
    element_resistances: tuple[str, ...] = ()
    attack_patterns_learned: list[str] = field(default_factory=list)
    phase_transitions: dict[int, str] = field(default_factory=dict)
    recommended_strategy: str = ""

    @property
    def win_rate(self) -> float:
        if self.total_encounters == 0:
            return 0.0
        return self.wins / self.total_encounters


@dataclass(slots=True, frozen=True)
class StrategyAdjustment:
    """Recommended strategy change based on fight history."""
    adjustment_type: str     # "change_team", "change_rotation", "change_food", "gear_up", "learn_mechanics"
    reason: str
    specifics: dict[str, Any] = field(default_factory=dict)
    priority: int = 100      # lower = higher priority


# ---------------------------------------------------------------------------
# Meta-learning engine
# ---------------------------------------------------------------------------

class MetaLearningEngine:
    """Accumulates combat experience and generates strategy improvements.

    Integrates with:
    - BAGEL belief system for persistent knowledge
    - BossMechanismLearner for boss-specific learning
    - CombatSurvivalEngine for real-time decisions
    """

    def __init__(self) -> None:
        self._records: list[FightRecord] = []
        self._profiles: dict[str, EnemyProfile] = {}
        self._strategy_history: list[StrategyAdjustment] = []

    def record_fight(self, record: FightRecord) -> None:
        """Record a fight outcome and update enemy profiles."""
        self._records.append(record)
        profile = self._profiles.setdefault(record.enemy_name, EnemyProfile(record.enemy_name))
        profile.total_encounters += 1

        if record.outcome == Outcome.WIN:
            profile.wins += 1
            total_win_time = (
                (profile.avg_duration_sec * (profile.wins - 1)) + record.duration_sec
            ) / profile.wins
            profile.avg_duration_sec = total_win_time
            if profile.best_duration_sec == 0 or record.duration_sec < profile.best_duration_sec:
                profile.best_duration_sec = record.duration_sec
            # Update best team if this was a fast win
            if record.duration_sec <= profile.best_duration_sec:
                profile.best_team = record.team
        elif record.outcome == Outcome.RETREAT:
            # Track retreat reasons
            pass

        # Learn patterns from key events
        for event in record.key_events:
            if event not in profile.attack_patterns_learned:
                profile.attack_patterns_learned.append(event)

    def get_profile(self, enemy_name: str) -> EnemyProfile | None:
        return self._profiles.get(enemy_name)

    def analyze_performance(self) -> list[StrategyAdjustment]:
        """Analyze overall combat performance and recommend improvements."""
        adjustments: list[StrategyAdjustment] = []

        if not self._records:
            return adjustments

        recent = self._records[-20:]  # last 20 fights
        wins = sum(1 for r in recent if r.outcome == Outcome.WIN)
        losses = sum(1 for r in recent if r.outcome == Outcome.LOSS)
        avg_deaths = sum(r.deaths for r in recent) / max(1, len(recent))

        # Check win rate
        win_rate = wins / max(1, len(recent))
        if win_rate < 0.3:
            adjustments.append(StrategyAdjustment(
                "gear_up", f"Win rate {win_rate:.0%} is too low. Focus on character building.",
                {"priority_order": ["weapon_level", "talent_level", "character_level"]},
                priority=0,
            ))
        elif win_rate < 0.5:
            adjustments.append(StrategyAdjustment(
                "change_strategy", f"Win rate {win_rate:.0%} suggests team/strategy issues.",
                priority=10,
            ))

        # Check death frequency
        if avg_deaths > 1.5:
            adjustments.append(StrategyAdjustment(
                "change_food", f"Average {avg_deaths:.1f} deaths per fight. Bring more healing food.",
                {"recommended_foods": ["sweet_madame", "mondstadt_hash_brown"]},
                priority=5,
            ))

        # Check for recurring enemy issues
        for name, profile in self._profiles.items():
            if profile.total_encounters >= 3 and profile.win_rate < 0.4:
                adjustments.append(StrategyAdjustment(
                    "change_team",
                    f"{name}: {profile.total_encounters} fights, {profile.win_rate:.0%} win rate. "
                    f"Best team was {profile.best_team}.",
                    {"enemy": name, "best_team": list(profile.best_team)},
                    priority=15,
                ))

        # Check for timeout issues
        timeouts = sum(1 for r in recent if r.outcome == Outcome.TIMEOUT)
        if timeouts > 2:
            adjustments.append(StrategyAdjustment(
                "change_rotation",
                f"{timeouts} timeout fights in last {len(recent)}. Optimize DPS rotation.",
                priority=8,
            ))

        adjustments.sort(key=lambda a: a.priority)
        self._strategy_history.extend(adjustments)
        return adjustments

    def get_cross_boss_knowledge(self, enemy_name: str) -> dict[str, Any]:
        """Transfer knowledge from similar bosses (L-07: cross-boss transfer).

        Find bosses with similar characteristics and share learned patterns.
        """
        target = self._profiles.get(enemy_name)
        if target is None:
            return {"status": "no_data", "enemy": enemy_name}

        # Find similar enemies (same element_weaknesses or attack patterns)
        similar: list[tuple[str, float]] = []
        for name, profile in self._profiles.items():
            if name == enemy_name:
                continue
            similarity = 0.0
            # Shared attack patterns increase similarity
            shared = set(target.attack_patterns_learned) & set(profile.attack_patterns_learned)
            if shared:
                similarity += len(shared) * 0.3
            # Shared element weaknesses
            shared_elem = set(target.element_weaknesses) & set(profile.element_weaknesses)
            if shared_elem:
                similarity += len(shared_elem) * 0.2
            if similarity > 0:
                similar.append((name, similarity))

        similar.sort(key=lambda x: -x[1])

        transferable: dict[str, Any] = {"target": enemy_name}
        if similar:
            best_match, score = similar[0]
            source_profile = self._profiles[best_match]
            transferable["source"] = best_match
            transferable["similarity"] = score
            transferable["transferable_strategies"] = {
                "best_team": list(source_profile.best_team),
                "attack_patterns": source_profile.attack_patterns_learned[:5],
                "recommended_strategy": source_profile.recommended_strategy,
            }

        return transferable

    def get_online_guide_integration(self, enemy_name: str) -> dict[str, Any]:
        """Prepare search queries for online guide lookup (L-08).

        Returns search terms and expected information to extract.
        """
        profile = self._profiles.get(enemy_name)
        queries: list[str] = [
            f"Genshin Impact {enemy_name} boss guide F2P",
            f"Genshin {enemy_name} best team composition",
        ]
        if profile and profile.win_rate < 0.5:
            queries.append(f"Genshin {enemy_name} how to beat F2P")

        return {
            "enemy": enemy_name,
            "search_queries": queries,
            "extract_targets": [
                "recommended_team",
                "elemental_weaknesses",
                "attack_patterns",
                "phase_mechanics",
                "food_recommendations",
            ],
        }

    @property
    def total_fights(self) -> int:
        return len(self._records)

    @property
    def profiles(self) -> dict[str, EnemyProfile]:
        return self._profiles
