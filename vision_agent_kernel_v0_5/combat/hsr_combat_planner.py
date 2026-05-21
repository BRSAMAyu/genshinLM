from __future__ import annotations

from dataclasses import dataclass, field

from combat.hsr_weakness_table import VALID_ELEMENTS, get_break_effect


@dataclass(frozen=True, slots=True)
class HSRTurnAction:
    action: str           # "basic_attack", "skill", "ultimate"
    character_pos: int    # 1-4 party position
    target_index: int     # which enemy to target
    sp_cost: int          # 0 for basic, 1 for skill, 0 for ultimate
    sp_gain: int          # 1 for basic, 0 for skill/ultimate
    element: str          # element applied
    thought: str = ""


@dataclass(slots=True)
class HSRCombatPlan:
    plan_id: str
    team: list[str] = field(default_factory=list)
    enemy_weaknesses: list[str] = field(default_factory=list)
    turn_rotation: list[HSRTurnAction] = field(default_factory=list)
    ultimate_interrupts: list[HSRTurnAction] = field(default_factory=list)
    sp_budget: dict[str, int] = field(default_factory=dict)
    fallback_strategy: str = ""


@dataclass(frozen=True, slots=True)
class HSRCharacterState:
    character_id: str
    position: int        # 1-4
    element: str
    path: str            # destruction, hunt, erudition, harmony, nihility, preservation, abundance
    hp_ratio: float = 1.0
    skill_ready: bool = True
    ultimate_ready: bool = False


# Path priorities for SP spending
_PATH_SP_PRIORITY: dict[str, int] = {
    "abundance": 100,     # Healers get priority when allies are low
    "preservation": 80,   # Shields/mitigation
    "harmony": 60,        # Buffers before DPS
    "destruction": 50,    # DPS
    "hunt": 50,           # Single-target DPS
    "erudition": 40,      # AoE DPS
    "nihility": 30,       # Debuffers
}

# Paths that should use skill even at low SP when allies need healing
_HEALER_PATHS = frozenset({"abundance", "preservation"})


class HSRCombatPlanner:
    """Generate turn-based combat plans with SP management and weakness exploitation."""

    def generate_plan(
        self,
        team: list[HSRCharacterState],
        enemy_weaknesses: list[str],
        current_sp: int = 3,
        max_sp: int = 5,
        current_wave: int = 1,
        total_waves: int = 1,
    ) -> HSRCombatPlan:
        team_ids = [c.character_id for c in team]
        rotation: list[HSRTurnAction] = []
        ultimate_interrupts: list[HSRTurnAction] = []
        sp = current_sp
        sp_budget: dict[str, int] = {}

        # Sort team by action priority
        sorted_team = sorted(team, key=lambda c: self._action_priority(c, enemy_weaknesses, team))

        for char in sorted_team:
            # Check if character hits any weakness
            hits_weakness = char.element in enemy_weaknesses

            # Decide action based on SP state and character role
            action, sp_change = self._decide_action(
                char=char,
                sp=sp,
                max_sp=max_sp,
                hits_weakness=hits_weakness,
                team_hp_ratios=[c.hp_ratio for c in team],
                current_wave=current_wave,
                total_waves=total_waves,
            )

            sp += sp_change
            sp_budget[char.character_id] = -sp_change if sp_change < 0 else 0

            rotation.append(HSRTurnAction(
                action=action,
                character_pos=char.position,
                target_index=0,
                sp_cost=1 if action == "skill" else 0,
                sp_gain=1 if action == "basic_attack" else 0,
                element=char.element,
                thought=f"{char.character_id}: {action} (SP={sp}, weakness={'yes' if hits_weakness else 'no'})",
            ))

            # Add ultimate interrupts for characters with ultimate ready
            if char.ultimate_ready:
                ultimate_interrupts.append(HSRTurnAction(
                    action="ultimate",
                    character_pos=char.position,
                    target_index=0,
                    sp_cost=0,
                    sp_gain=0,
                    element=char.element,
                    thought=f"{char.character_id}: ultimate interrupt",
                ))

        # Build fallback
        if sp <= 1:
            fallback = "prioritize_basic_attacks_for_sp_recovery"
        elif current_wave < total_waves:
            fallback = "conserve_sp_for_later_waves"
        else:
            fallback = "full_rotation"

        return HSRCombatPlan(
            plan_id=f"hsr_plan_{current_wave}_{len(team)}",
            team=team_ids,
            enemy_weaknesses=enemy_weaknesses,
            turn_rotation=rotation,
            ultimate_interrupts=ultimate_interrupts,
            sp_budget=sp_budget,
            fallback_strategy=fallback,
        )

    def _decide_action(
        self,
        char: HSRCharacterState,
        sp: int,
        max_sp: int,
        hits_weakness: bool,
        team_hp_ratios: list[float],
        current_wave: int,
        total_waves: int,
    ) -> tuple[str, int]:
        """Decide action for a character. Returns (action, sp_change)."""
        any_low_hp = any(r < 0.5 for r in team_hp_ratios)

        # Healers must use skill when allies are low HP
        if char.path in _HEALER_PATHS and any_low_hp:
            if sp >= 1:
                return "skill", -1
            return "basic_attack", +1

        # Characters hitting weakness get priority for skill usage
        if hits_weakness:
            if sp >= 2:
                return "skill", -1
            if sp >= 1 and current_wave >= total_waves:
                return "skill", -1
            return "basic_attack", +1

        # Non-weakness characters
        if sp >= max_sp - 1:
            return "skill", -1
        if sp >= 3 and char.path in ("harmony", "nihility"):
            return "skill", -1

        return "basic_attack", +1

    def _action_priority(
        self,
        char: HSRCharacterState,
        enemy_weaknesses: list[str],
        team: list[HSRCharacterState],
    ) -> int:
        """Lower number = acts earlier in plan."""
        any_low_hp = any(c.hp_ratio < 0.5 for c in team)

        # Healers act first when allies are low
        if char.path in _HEALER_PATHS and any_low_hp:
            return 0

        # Weakness hitters get priority
        if char.element in enemy_weaknesses:
            return 10 + _PATH_SP_PRIORITY.get(char.path, 50)

        return 100 + _PATH_SP_PRIORITY.get(char.path, 50)
