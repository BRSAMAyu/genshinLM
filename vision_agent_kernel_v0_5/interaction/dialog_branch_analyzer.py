"""Dialog branch analysis with consequence tracking.

Analyzes dialog choices, recommends selections, and tracks the downstream
consequences of each choice for quest progression replay/debugging.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Keywords that indicate "accept" actions in dialog choices
_ACCEPT_KEYWORDS = {"接受", "同意", "好的", "没问题", "当然", "是", "愿意", "我来", "一起"}
_REJECT_KEYWORDS = {"拒绝", "不了", "不用", "算了", "取消"}


@dataclass(frozen=True, slots=True)
class DialogChoice:
    """A recorded dialog choice at a branch point."""
    quest_id: str
    npc_name: str
    dialog_text: str
    options: tuple[str, ...]
    selected_index: int
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class DialogConsequence:
    """The observed consequence of a dialog choice."""
    quest_id: str
    choice_hash: str
    outcome: str  # "quest_accepted", "quest_declined", "new_info", "combat_triggered", "branch_locked"
    details: str = ""
    timestamp: float = 0.0


@dataclass(slots=True)
class ConsequenceTracker:
    """Track dialog choices and their observed consequences.

    Enables:
    - Recording which choices were made and what happened after
    - Querying past choices for a quest to inform future decisions
    - Building a replay log for debugging
    """

    max_history: int = 200
    _choices: list[DialogChoice] = field(default_factory=list)
    _consequences: list[DialogConsequence] = field(default_factory=list)

    def record_choice(
        self,
        quest_id: str,
        npc_name: str,
        dialog_text: str,
        options: list[str],
        selected_index: int,
    ) -> str:
        """Record a dialog choice and return a hash for consequence linking."""
        choice = DialogChoice(
            quest_id=quest_id,
            npc_name=npc_name,
            dialog_text=dialog_text,
            options=tuple(options),
            selected_index=selected_index,
            timestamp=time.perf_counter(),
        )
        self._choices.append(choice)
        self._trim(self._choices)
        return self._choice_hash(choice)

    def record_consequence(
        self,
        quest_id: str,
        choice_hash: str,
        outcome: str,
        details: str = "",
    ) -> None:
        """Record the observed consequence of a prior choice."""
        cons = DialogConsequence(
            quest_id=quest_id,
            choice_hash=choice_hash,
            outcome=outcome,
            details=details,
            timestamp=time.perf_counter(),
        )
        self._consequences.append(cons)
        self._trim(self._consequences)

    def get_quest_choices(self, quest_id: str) -> list[DialogChoice]:
        return [c for c in self._choices if c.quest_id == quest_id]

    def get_consequences(self, quest_id: str) -> list[DialogConsequence]:
        return [c for c in self._consequences if c.quest_id == quest_id]

    def get_last_choice_hash(self, quest_id: str) -> str | None:
        choices = self.get_quest_choices(quest_id)
        if not choices:
            return None
        return self._choice_hash(choices[-1])

    def stats(self) -> dict[str, int]:
        return {
            "total_choices": len(self._choices),
            "total_consequences": len(self._consequences),
        }

    @staticmethod
    def _choice_hash(choice: DialogChoice) -> str:
        return f"{choice.quest_id}_{hash(choice.dialog_text)}_{choice.selected_index}"

    def _trim(self, lst: list) -> None:
        if len(lst) > self.max_history:
            del lst[: len(lst) - self.max_history]


class DialogBranchAnalyzer:
    """Analyze dialog choices, recommend selections, and track consequences.

    Usage::

        tracker = ConsequenceTracker()
        analyzer = DialogBranchAnalyzer(tracker=tracker)

        # When dialog appears:
        idx = analyzer.analyze_choices(["接受委托", "拒绝"], context={"quest_id": "q001"})
        # analyzer automatically records the choice

        # When outcome is observed:
        tracker.record_consequence("q001", hash, "quest_accepted")
    """

    def __init__(self, tracker: ConsequenceTracker | None = None) -> None:
        self._tracker = tracker

    def analyze_choices(
        self,
        choice_texts: list[str],
        context: dict | None = None,
    ) -> int:
        """Return recommended choice index (0-based).

        For Genshin main storyline, dialog choices don't affect story outcome,
        so default to first choice unless we detect specific keywords.
        """
        if not choice_texts:
            return 0

        # Check for accept/reject keywords
        for i, text in enumerate(choice_texts):
            text_lower = text.lower().strip()
            for kw in _ACCEPT_KEYWORDS:
                if kw in text_lower:
                    self._maybe_record(choice_texts, i, context)
                    return i

        # Default: first option (safest for main storyline)
        self._maybe_record(choice_texts, 0, context)
        return 0

    def _maybe_record(
        self,
        options: list[str],
        selected: int,
        context: dict | None,
    ) -> None:
        if self._tracker is None or not context:
            return
        quest_id = context.get("quest_id", "")
        npc_name = context.get("npc_name", "")
        dialog_text = context.get("dialog_text", "")
        self._tracker.record_choice(
            quest_id=quest_id,
            npc_name=npc_name,
            dialog_text=dialog_text,
            options=options,
            selected_index=selected,
        )
