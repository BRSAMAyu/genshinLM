from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


class QuestObjectiveDetector:
    """Detect quest objective completion from screen frames."""

    def __init__(self, classifier: Any) -> None:
        self._classifier = classifier

    def detect_objective_status(self, frame: np.ndarray, objective: str) -> str:
        """Returns: 'completed' | 'in_progress' | 'not_started' | 'unknown'"""
        state = self._classifier.classify(frame)

        if objective == "dialog_complete":
            return self._check_dialog_complete(state)
        elif objective.startswith("combat_complete"):
            return self._check_combat_complete(state)
        elif objective.startswith("reached_"):
            return self._check_reached(state)
        elif objective == "item_collected":
            return self._check_item_collected(state)
        elif objective.startswith("entered_"):
            return self._check_entered(state)
        else:
            return "unknown"

    def _check_dialog_complete(self, state) -> str:
        if state.state not in ("dialog",):
            return "completed"
        return "in_progress"

    def _check_combat_complete(self, state) -> str:
        if state.state in ("world_hud", "overworld") and not state.indicators.get("combat", False):
            return "completed"
        if state.state in ("combat", "boss_fight"):
            return "in_progress"
        return "unknown"

    def _check_reached(self, state) -> str:
        if state.state in ("world_hud", "overworld"):
            return "completed"
        if state.state in ("loading_screen",):
            return "in_progress"
        return "unknown"

    def _check_item_collected(self, state) -> str:
        if state.state in ("reward_screen",):
            return "completed"
        return "unknown"

    def _check_entered(self, state) -> str:
        if state.state in ("domain_entrance",):
            return "completed"
        if state.state in ("loading_screen",):
            return "in_progress"
        return "unknown"
