"""Quest mechanism executor: translates MechanismDecisions into semantic actions.

Bridges QuestMechanismRouter's decision output to the unified semantic executor.
Each MechanismDecision.action maps to one or more executor calls.
"""
from __future__ import annotations

import logging
from typing import Any

from planning.quest_mechanism_router import (
    MechanismDecision,
    QuestMechanismType,
    QuestMechanismRouter,
)

log = logging.getLogger(__name__)

# Maps MechanismDecision.action to semantic executor action
_ACTION_MAP: dict[str, str] = {
    "proceed": "interact",
    "wait": "idle",
    "hide": "move_to_cover",
    "protect": "defend_target",
    "fight": "combat_encounter",
    "search": "explore_area",
    "exit": "interact",
    "follow_safe_path": "walk_to",
    "observe": "idle",
    "retreat": "move_to_cover",
    "resume_from_checkpoint": "quest_advance",
    "restart_quest": "quest_advance",
    "grind_ar": "quest_advance",
    "complete_prerequisite": "quest_advance",
    "escalate": "quest_advance",
    "auto_complete_no_domain": "quest_advance",
    "drive_dialog": "quest_drive_dialog",
    "select_branch": "quest_drive_dialog",
    "continue_dialog_default": "quest_drive_dialog",
    "heart_event_respond": "quest_drive_dialog",
    "advance_hangout_dialog": "quest_drive_dialog",
    "event_intro": "quest_advance",
    "event_finale": "quest_advance",
    "play_mini_game": "interact",
    "event_challenge": "combat_encounter",
}


class QuestMechanismExecutor:
    """Execute quest mechanism decisions through the semantic executor.

    Usage::

        router = QuestMechanismRouter()
        executor = QuestMechanismExecutor(router=router, executor=sem_exec)
        result = executor.route(mechanism_type="stealth")
    """

    def __init__(
        self,
        *,
        router: QuestMechanismRouter,
        executor: Any,
    ) -> None:
        self._router = router
        self._executor = executor

    def route(self, mechanism_type: str = "standard", **kwargs: Any) -> bool:
        """Route a mechanism type to decision → semantic action.

        Args:
            mechanism_type: String matching QuestMechanismType value.
            **kwargs: Additional context passed to state updates.

        Returns:
            True if the semantic action succeeded.
        """
        try:
            mtype = QuestMechanismType(mechanism_type)
        except ValueError:
            log.warning("[QuestMechanismExecutor] unknown mechanism type: %s", mechanism_type)
            return False

        decision = self._router.route(mtype)
        success = self._execute_decision(decision)

        if not success:
            log.warning(
                "[QuestMechanismExecutor] mechanism %s → action %s failed",
                mechanism_type, decision.action,
            )
        return success

    def _execute_decision(self, decision: MechanismDecision) -> bool:
        """Translate a MechanismDecision into a semantic executor call."""
        semantic_action = _ACTION_MAP.get(decision.action)
        if semantic_action is None:
            log.debug("[QuestMechanismExecutor] unmapped action: %s", decision.action)
            semantic_action = "interact"

        target = ""
        if decision.target is not None:
            target = f"{decision.target[0]:.0f},{decision.target[1]:.0f}"

        context: dict[str, Any] = dict(decision.params) if decision.params else {}
        context["mechanism_reason"] = decision.reason
        context["mechanism_priority"] = decision.priority

        return self._executor.execute_semantic(
            action=semantic_action,
            target=target,
            context=context,
        )
