from __future__ import annotations

from agentic.action_proposer import ActionProposer
from agentic.confidence_gate import ConfidenceGate
from agentic.visual_grounding import VisualGrounding
from dataclasses import asdict


class UIExplorer:
    def __init__(self) -> None:
        self._grounding = VisualGrounding()
        self._proposer = ActionProposer()
        self._gate = ConfidenceGate()

    def explore_once(self, ocr_items: list[dict], real_execution: bool = False) -> list[dict[str, object]]:
        decisions = []
        for element in self._grounding.ground(ocr_items):
            action = self._proposer.propose(element)
            decisions.append({"element": asdict(element), "action": asdict(action), "gate": self._gate.decide(action, real_execution)})
        return decisions
