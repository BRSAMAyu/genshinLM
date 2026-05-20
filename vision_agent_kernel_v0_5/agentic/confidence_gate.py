from __future__ import annotations

from agentic.action_proposer import ProposedAction


class ConfidenceGate:
    def decide(self, action: ProposedAction, real_execution: bool = False) -> dict[str, object]:
        if action.reason == "destructive semantic blacklist":
            return {"allow": False, "level": "HUMAN_OVERRIDE_REQUIRED", "reason": action.reason}
        if real_execution and action.requires_confirmation:
            return {"allow": False, "level": "CONFIRM_REQUIRED", "reason": action.reason}
        if action.confidence < 0.65:
            return {"allow": False, "level": "REQUEST_DEMONSTRATION", "reason": action.reason}
        return {"allow": True, "level": "DRY_RUN_ONLY" if not real_execution else "CONFIRMED_SAFE_WINDOW", "reason": action.reason}

