from __future__ import annotations

from combat.combat_action_state import CombatActionState


class CombatFallbackPolicy:
    def choose(self, state: CombatActionState, failures: int) -> str:
        # Action-level fallback: a single step failed but the combo can continue.
        if failures <= 1 and state.actor_state not in {"hitstun", "knocked_back"} and state.resources.hp_ratio >= 0.35:
            return "action_retry_then_skip"
        # Combo-level fallback: interruption requires checkpoint recovery.
        if state.actor_state in {"hitstun", "knocked_back"}:
            return "combo_resume_from_checkpoint"
        # Tactical-level fallback: resources/danger require a defensive branch.
        if state.resources.hp_ratio < 0.35:
            return "tactical_defend_or_heal"
        # Mission-level fallback: repeated failures leave the local runtime.
        if failures >= 3:
            return "mission_skip_or_request_user"
        return "action_retry_then_skip"
