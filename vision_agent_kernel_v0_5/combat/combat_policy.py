from __future__ import annotations

from combat.combat_context import CombatContext


class CombatPolicy:
    def choose_node(self, context: CombatContext) -> str:
        if context.danger_priority >= 0.8:
            return "dodge_if_danger"
        if context.hp_ratio < 0.35:
            return "heal_if_low_hp"
        if context.target_visible:
            return "basic_attack_loop"
        return "maintain_lock"
