from __future__ import annotations

from dataclasses import dataclass

from agentic.visual_grounding import GroundedElement


@dataclass(frozen=True, slots=True)
class ProposedAction:
    action_type: str
    target_label: str
    confidence: float
    requires_confirmation: bool
    reason: str


class ActionProposer:
    def propose(self, element: GroundedElement) -> ProposedAction:
        if element.destructive:
            return ProposedAction("blocked", element.label, 0.0, True, "destructive semantic blacklist")
        if element.confidence >= 0.85:
            return ProposedAction("dry_run_click_candidate", element.label, element.confidence, False, "high-confidence UI element")
        return ProposedAction("request_user_confirmation", element.label, element.confidence, True, "low-confidence visual grounding")

