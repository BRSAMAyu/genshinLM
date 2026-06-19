from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from knowledge.genshin_archon_quests import ArchonQuest, QuestStep

log = logging.getLogger(__name__)


class QuestStateMachine:
    """Manage mainline quest chain progression state."""

    def __init__(self, quest_chain: list[ArchonQuest] | None = None) -> None:
        self._chain: list[ArchonQuest] = quest_chain or []
        self._current_quest_idx: int = 0
        self._current_step_idx: int = 0
        self._completed: set[str] = set()

    @property
    def current_quest(self) -> ArchonQuest | None:
        if self._current_quest_idx < len(self._chain):
            return self._chain[self._current_quest_idx]
        return None

    @property
    def current_step(self) -> QuestStep | None:
        quest = self.current_quest
        if quest is None:
            return None
        if self._current_step_idx < len(quest.steps):
            return quest.steps[self._current_step_idx]
        return None

    @property
    def progress(self) -> tuple[int, int]:
        """Return (completed_steps, total_steps) across all quests."""
        total = sum(len(q.steps) for q in self._chain)
        completed = len(self._completed)
        return (completed, total)

    def advance(self, evidence: str = "") -> QuestStep | None:
        """Complete current step, move to next. Returns next step or None."""
        step = self.current_step
        if step is None:
            return None
        self._completed.add(step.step_id)
        log.info("[QuestSM] completed step %s: %s (evidence: %s)", step.step_id, step.description, evidence)

        self._current_step_idx += 1
        quest = self.current_quest
        if quest and self._current_step_idx >= len(quest.steps):
            # Current quest done, advance to next
            self._completed.add(quest.quest_id)
            log.info("[QuestSM] completed quest %s: %s", quest.quest_id, quest.title)
            self._current_quest_idx += 1
            self._current_step_idx = 0

        return self.current_step

    def check_prerequisites(self, current_ar: int = 0) -> bool:
        """Check if prerequisites for current step are met."""
        step = self.current_step
        if step is None:
            return False
        if step.prereq_ar > current_ar:
            log.info("[QuestSM] AR %d < required %d", current_ar, step.prereq_ar)
            return False
        if step.prereq_quest and step.prereq_quest not in self._completed:
            log.info("[QuestSM] prereq quest %s not completed", step.prereq_quest)
            return False
        return True

    def skip_to_quest(self, quest_id: str) -> bool:
        """Skip ahead to a specific quest. Marks all prior as completed."""
        for i, quest in enumerate(self._chain):
            if quest.quest_id == quest_id:
                for j in range(i):
                    for step in self._chain[j].steps:
                        self._completed.add(step.step_id)
                    self._completed.add(self._chain[j].quest_id)
                self._current_quest_idx = i
                self._current_step_idx = 0
                return True
        return False

    def is_mainline_complete(self) -> bool:
        return self._current_quest_idx >= len(self._chain)

    def save_state(self) -> dict:
        return {
            "current_quest_idx": self._current_quest_idx,
            "current_step_idx": self._current_step_idx,
            "completed": sorted(self._completed),
        }

    def load_state(self, state: dict) -> None:
        self._current_quest_idx = state.get("current_quest_idx", 0)
        self._current_step_idx = state.get("current_step_idx", 0)
        self._completed = set(state.get("completed", []))
