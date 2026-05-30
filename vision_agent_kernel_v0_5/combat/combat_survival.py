"""Combat survival and enhancement: food usage, death recovery, boss mechanism learning.

Extends the existing combat system with survival mechanics and boss-specific strategies.
Covers C-06, C-09, C-10, C-11, C-14, C-15, C-16, C-17, C-18, C-19, C-20, C-21,
C-22, C-32, C-33, C-34.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Elemental shield weakness table (C-11)
# ---------------------------------------------------------------------------

class ShieldElement(Enum):
    PYRO = "Pyro"
    HYDRO = "Hydro"
    ELECTRO = "Electro"
    CRYO = "Cryo"
    ANEMO = "Anemo"
    GEO = "Geo"
    DENDRO = "Dendro"
    PHYSICAL = "Physical"


# Shield element -> most effective counter element(s)
SHIELD_COUNTERS: dict[ShieldElement, tuple[str, ...]] = {
    ShieldElement.PYRO:      ("Hydro",),               # Vaporize breaks fastest
    ShieldElement.HYDRO:     ("Electro", "Cryo"),       # Electro-Charged / Freeze
    ShieldElement.ELECTRO:   ("Pyro", "Cryo"),          # Overloaded / Superconduct
    ShieldElement.CRYO:      ("Pyro",),                 # Melt
    ShieldElement.GEO:       ("Claymore", "Plunge"),    # Physical break
    ShieldElement.ANEMO:     (),                        # Swirl-spreads, no direct counter
    ShieldElement.DENDRO:    ("Pyro", "Electro"),       # Burning / Quicken
    ShieldElement.PHYSICAL:  ("Geo", "Claymore"),       # Elemental damage or heavy attacks
}


def get_shield_counter(shield_element: str) -> tuple[str, ...]:
    """Return the best element(s) to break a given shield type."""
    for se in ShieldElement:
        if se.value.lower() == shield_element.lower():
            return SHIELD_COUNTERS.get(se, ())
    return ()


# ---------------------------------------------------------------------------
# Boss mechanism knowledge (C-19, C-20, C-21, C-22)
# ---------------------------------------------------------------------------

class CombatBossPhase(Enum):
    IDLE = "idle"
    AGGRESSIVE = "aggressive"
    INVULNERABLE = "invulnerable"
    STUNNED = "stunned"
    TRANSITION = "transition"
    ENRAGED = "enraged"


@dataclass(slots=True, frozen=True)
class BossAttackPattern:
    """A recognizable boss attack with dodge/counter strategy."""
    pattern_id: str
    name: str
    visual_cue: str           # description of telegraph animation
    damage_type: str          # "aoe", "single_target", "cone", "line", "dot"
    dodge_window_ms: int      # milliseconds to dodge after visual cue
    recommended_action: str   # "dash", "burst_iframe", "shield", "move_away"
    phase_restriction: CombatBossPhase | None = None


@dataclass(slots=True, frozen=True)
class BossPhaseInfo:
    """Boss behavior in a specific phase."""
    phase_id: str
    boss_name: str
    phase_number: int
    hp_threshold: float         # 0.0-1.0 HP percentage
    vulnerable_elements: tuple[str, ...] = ()
    immune_elements: tuple[str, ...] = ()
    attack_patterns: tuple[str, ...] = ()
    special_mechanics: str = ""
    damage_window_after: str = ""  # description of when to deal damage


@dataclass(slots=True)
class BossFightRecord:
    """Record of a boss fight for learning."""
    boss_name: str
    attempts: int = 0
    wins: int = 0
    deaths: int = 0
    avg_time_sec: float = 0.0
    best_time_sec: float = 0.0
    learned_patterns: list[str] = field(default_factory=list)
    failed_phases: list[int] = field(default_factory=list)
    effective_strategies: list[str] = field(default_factory=list)


# Known boss patterns from existing knowledge
BOSS_PHASES: dict[str, tuple[BossPhaseInfo, ...]] = {
    "dvalin": (
        BossPhaseInfo("dvalin_fly", "Dvalin", 1, 1.0,
                      immune_elements=("Anemo",),
                      special_mechanics="Ranged attacks during aerial phase"),
        BossPhaseInfo("dvalin_platform", "Dvalin", 2, 0.5,
                      vulnerable_elements=("Pyro", "Electro"),
                      special_mechanics="Break shields on platforms"),
    ),
    "childe": (
        BossPhaseInfo("childe_hydro", "Childe", 1, 1.0,
                      vulnerable_elements=("Electro",),
                      attack_patterns=("ranged_hydro", "whale_drop")),
        BossPhaseInfo("childe_electro", "Childe", 2, 0.6,
                      vulnerable_elements=("Pyro", "Cryo"),
                      immune_elements=("Electro",),
                      attack_patterns=("electro_slash", "lightning_storm")),
        BossPhaseInfo("childe_dual", "Childe", 3, 0.3,
                      vulnerable_elements=("Cryo",),
                      attack_patterns=("whale_attack", "dual_element"),
                      damage_window_after="Post-whale recovery"),
    ),
    "signora": (
        BossPhaseInfo("signora_cryo", "Signora", 1, 1.0,
                      vulnerable_elements=("Pyro",),
                      special_mechanics="Collect Hearts of Flame to manage cold gauge"),
        BossPhaseInfo("signora_pyro", "Signora", 2, 0.5,
                      vulnerable_elements=("Cryo", "Hydro"),
                      special_mechanics="Collect Frostflame seeds to manage heat gauge"),
    ),
    "raiden_shogun": (
        BossPhaseInfo("raiden_story", "Raiden Shogun", 1, 1.0,
                      special_mechanics="Story fight: survive, not defeat. Dodge wide slashes."),
    ),
    "shouki_no_kami": (
        BossPhaseInfo("shouki_p1", "Shouki no Kami", 1, 1.0,
                      special_mechanics="Giant boss with elemental cores"),
        BossPhaseInfo("shouki_p2", "Shouki no Kami", 2, 0.5,
                      special_mechanics="Collect energy blocks, charge device to stun",
                      damage_window_after="After device activation stun"),
        BossPhaseInfo("shouki_p3", "Shouki no Kami", 3, 0.2,
                      attack_patterns=("mega_attack",),
                      damage_window_after="Post-mega-attack recovery"),
    ),
    "narwhal": (
        BossPhaseInfo("narwhal_p1", "Narwhal", 1, 1.0,
                      attack_patterns=("charge", "tail_slap", "water_blast")),
        BossPhaseInfo("narwhal_p2", "Narwhal", 2, 0.4,
                      attack_patterns=("mega_charge", "aoe_burst"),
                      damage_window_after="Post-charge recovery"),
    ),
}


# ---------------------------------------------------------------------------
# Combat food system (C-16, M-13)
# ---------------------------------------------------------------------------

class CombatFoodType(Enum):
    HEAL_INSTANT = "heal_instant"          # Immediate HP restore
    HEAL_OVER_TIME = "heal_ot"             # Regeneration
    REVIVE = "revive"                      # Revive fallen character
    ATK_BUFF = "atk_buff"                  # +ATK
    CRIT_BUFF = "crit_buff"                # +CRIT Rate
    DEF_BUFF = "def_buff"                  # +DEF
    STAMINA_BUFF = "stamina_buff"          # +Stamina
    ELEMENTAL_BUFF = "elemental_buff"      # +Elemental DMG


@dataclass(slots=True, frozen=True)
class CombatFood:
    name: str
    food_type: CombatFoodType
    potency: float         # 0.0-1.0 relative strength
    duration_sec: float    # 0 for instant effects
    cooldown_sec: float = 0.0


# Quick-access combat foods
COMBAT_FOODS: dict[str, CombatFood] = {
    "sweet_madame": CombatFood("Sweet Madame", CombatFoodType.HEAL_INSTANT, 0.3, 0.0),
    "mondstadt_hash_brown": CombatFood("Mondstadt Hash Brown", CombatFoodType.HEAL_INSTANT, 0.5, 0.0),
    "tea_break_pancake": CombatFood("Tea Break Pancake", CombatFoodType.REVIVE, 0.2, 0.0),
    "sticky_honey_roast": CombatFood("Sticky Honey Roast", CombatFoodType.ATK_BUFF, 0.15, 300.0),
    "crab_ham_veggie_bake": CombatFood("Crab Ham Veggie Bake", CombatFoodType.DEF_BUFF, 0.2, 300.0),
    "tianshu_meat": CombatFood("Tianshu Meat", CombatFoodType.ATK_BUFF, 0.25, 300.0),
}

FOOD_TYPE_COOLDOWNS: dict[CombatFoodType, float] = {
    CombatFoodType.HEAL_INSTANT: 0.0,
    CombatFoodType.HEAL_OVER_TIME: 0.0,
    CombatFoodType.REVIVE: 0.0,
    CombatFoodType.ATK_BUFF: 300.0,
    CombatFoodType.CRIT_BUFF: 300.0,
    CombatFoodType.DEF_BUFF: 300.0,
}


@dataclass(slots=True)
class CombatFoodState:
    """Tracks food cooldowns and usage during combat."""
    available_foods: dict[str, int] = field(default_factory=dict)  # food_name -> count
    active_buffs: dict[str, float] = field(default_factory=dict)   # buff_type -> expiry_time
    cooldowns: dict[str, float] = field(default_factory=dict)      # food_type -> expiry_time

    def can_use(self, food_name: str, now: float) -> bool:
        food = COMBAT_FOODS.get(food_name)
        if food is None:
            return False
        if self.available_foods.get(food_name, 0) <= 0:
            return False
        # Check food-type cooldown
        cd_expiry = self.cooldowns.get(food.food_type.value, 0.0)
        return now >= cd_expiry

    def use(self, food_name: str, now: float) -> bool:
        if not self.can_use(food_name, now):
            return False
        food = COMBAT_FOODS[food_name]
        self.available_foods[food_name] = self.available_foods.get(food_name, 0) - 1
        cd = FOOD_TYPE_COOLDOWNS.get(food.food_type, 0.0)
        if cd > 0:
            self.cooldowns[food.food_type.value] = now + cd
        if food.duration_sec > 0:
            self.active_buffs[food.food_type.value] = now + food.duration_sec
        return True

    def has_active_buff(self, buff_type: str, now: float) -> bool:
        expiry = self.active_buffs.get(buff_type, 0.0)
        return now < expiry


# ---------------------------------------------------------------------------
# Combat survival decision engine (C-14, C-15, C-17, C-18)
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class CombatSurvivalDecision:
    action: str             # "dash", "use_food", "switch", "burst_iframe", "retreat"
    priority: int           # 0 = immediate, higher = less urgent
    reason: str = ""
    target_slot: int | None = None  # for switch actions


class CombatSurvivalEngine:
    """Makes real-time survival decisions during combat.

    Integrates with:
    - danger_detector for incoming damage signals
    - reflex_evasion for dodge execution
    - food_manager for food usage
    - character_switch_manager for character switching
    """

    def __init__(self) -> None:
        self._food_state = CombatFoodState()
        self._dash_cooldown = 0.0
        self._burst_available = [True, True, True, True]

    @property
    def food_state(self) -> CombatFoodState:
        return self._food_state

    def evaluate(
        self,
        hp_ratios: tuple[float, ...],
        active_slot: int,
        danger_level: float,
        now: float,
        stamina_ratio: float = 1.0,
    ) -> CombatSurvivalDecision | None:
        """Evaluate combat state and return survival action if needed.

        Args:
            hp_ratios: HP ratios (0.0-1.0) for each party member.
            active_slot: Currently active character slot (0-3).
            danger_level: Danger signal strength (0.0-1.0).
            now: Current timestamp.
            stamina_ratio: Current stamina ratio (0.0-1.0).
        """
        active_hp = hp_ratios[active_slot] if active_slot < len(hp_ratios) else 1.0

        # P0: All dead -> need revival (but not empty party)
        if len(hp_ratios) > 0 and all(hp <= 0 for hp in hp_ratios):
            return CombatSurvivalDecision("retreat", 0, "all_dead")

        # P1: Active character near death
        if active_hp < 0.15 and danger_level > 0.5:
            if self._can_dash(now, stamina_ratio):
                self._consume_dash(now)
                return CombatSurvivalDecision("dash", 0, f"low_hp_{active_hp:.0%}")
            # Try burst iframe
            if self._burst_available[active_slot]:
                return CombatSurvivalDecision("burst_iframe", 1, "emergency_burst")
            # Switch to healthier character
            target = self._find_healthiest_slot(hp_ratios, exclude=active_slot)
            if target is not None:
                return CombatSurvivalDecision("switch", 1, "escape_low_hp", target_slot=target)
            # Last resort: food
            if self._food_state.can_use("mondstadt_hash_brown", now):
                return CombatSurvivalDecision("use_food", 2, "emergency_heal")

        # P2: Any character dead -> revive
        for i, hp in enumerate(hp_ratios):
            if hp <= 0:
                if self._food_state.can_use("tea_break_pancake", now):
                    return CombatSurvivalDecision("use_food", 5, f"revive_slot_{i}")

        # P3: Active HP low but not critical -> heal
        if active_hp < 0.4:
            heal_foods = ["mondstadt_hash_brown", "sweet_madame"]
            for food in heal_foods:
                if self._food_state.can_use(food, now):
                    return CombatSurvivalDecision("use_food", 10, "low_hp_heal")

        # P4: High danger -> dash
        if danger_level > 0.7 and self._can_dash(now, stamina_ratio):
            self._consume_dash(now)
            return CombatSurvivalDecision("dash", 8, "avoid_danger")

        # P5: Pre-boss food buffs
        if danger_level > 0.3 and not self._food_state.has_active_buff("atk_buff", now):
            if self._food_state.can_use("sticky_honey_roast", now):
                return CombatSurvivalDecision("use_food", 20, "pre_boss_atk_buff")

        return None

    def update_burst_availability(self, slot: int, available: bool) -> None:
        if 0 <= slot < 4:
            self._burst_available[slot] = available

    def _can_dash(self, now: float, stamina_ratio: float) -> bool:
        return now >= self._dash_cooldown and stamina_ratio > 0.2

    def _consume_dash(self, now: float) -> None:
        self._dash_cooldown = now + 0.6

    def _find_healthiest_slot(self, hp_ratios: tuple[float, ...], exclude: int) -> int | None:
        best: int | None = None
        best_hp = 0.0
        for i, hp in enumerate(hp_ratios):
            if i == exclude or hp <= 0:
                continue
            if hp > best_hp:
                best_hp = hp
                best = i
        return best


# ---------------------------------------------------------------------------
# Boss learning system (C-19, C-20, L-02, L-03, L-04)
# ---------------------------------------------------------------------------

class BossMechanismLearner:
    """Learns boss patterns from fight records and adapts strategy.

    Integrates with BAGEL belief system for persistent knowledge.
    """

    def __init__(self) -> None:
        self._records: dict[str, BossFightRecord] = {}

    def record_attempt(self, boss_name: str, won: bool, time_sec: float,
                       death_phase: int | None = None) -> None:
        record = self._records.setdefault(boss_name, BossFightRecord(boss_name=boss_name))
        record.attempts += 1
        if won:
            record.wins += 1
            if record.best_time_sec == 0 or time_sec < record.best_time_sec:
                record.best_time_sec = time_sec
            record.avg_time_sec = (
                (record.avg_time_sec * (record.wins - 1) + time_sec) / record.wins
            )
        else:
            record.deaths += 1
            if death_phase is not None:
                record.failed_phases.append(death_phase)

    def get_record(self, boss_name: str) -> BossFightRecord | None:
        return self._records.get(boss_name)

    def should_retreat(self, boss_name: str, max_attempts: int = 3) -> bool:
        """Determine if we should stop fighting and go gear up instead."""
        record = self._records.get(boss_name)
        if record is None:
            return False
        if record.attempts < max_attempts:
            return False
        win_rate = record.wins / record.attempts if record.attempts > 0 else 0
        # If win rate is very low after multiple attempts, retreat
        return win_rate < 0.2

    def get_failure_diagnosis(self, boss_name: str) -> str:
        """Analyze failure pattern and return likely cause."""
        record = self._records.get(boss_name)
        if record is None or record.attempts == 0:
            return "no_data"
        win_rate = record.wins / record.attempts
        if win_rate > 0.5:
            return "execution"  # winning sometimes, just need better execution
        # Check if dying to same phase repeatedly
        if record.failed_phases:
            phase_counts: dict[int, int] = {}
            for p in record.failed_phases:
                phase_counts[p] = phase_counts.get(p, 0) + 1
            worst_phase = max(phase_counts, key=phase_counts.get)
            if phase_counts[worst_phase] >= 2:
                return f"phase_{worst_phase}_mechanics"
        if record.avg_time_sec > 180:
            return "undergeared"  # taking too long = not enough DPS
        return "team_comp"  # default: wrong team composition

    def recommend_strategy_adjustment(self, boss_name: str) -> dict[str, Any]:
        """Generate strategy recommendations based on fight history."""
        record = self._records.get(boss_name)
        if record is None:
            return {"action": "fight", "reason": "no_previous_data"}
        diagnosis = self.get_failure_diagnosis(boss_name)
        recommendations: dict[str, Any] = {"diagnosis": diagnosis}
        if diagnosis == "undergeared":
            recommendations["action"] = "gear_up"
            recommendations["priority"] = "weapon_level > talent_level > artifacts"
        elif "mechanics" in diagnosis:
            recommendations["action"] = "learn_mechanics"
            recommendations["priority"] = "observe_boss_patterns"
        elif diagnosis == "team_comp":
            recommendations["action"] = "change_team"
            recommendations["priority"] = "consider_elemental_counters"
        elif diagnosis == "execution":
            recommendations["action"] = "retry"
            recommendations["priority"] = "optimize_rotation"
        else:
            recommendations["action"] = "fight"
        return recommendations
