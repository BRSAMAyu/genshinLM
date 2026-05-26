from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from planning.screen_state_claim import ScreenStateClaim

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QuestState:
    active_quest_id: str
    objective_text: str
    tracked_target: str
    is_blocked: bool
    failure_count: int


class QuestStateTracker:
    """Fuses OCR and VLM data to track active quest line objectives.

    Part of Phase 3 of the Unified Execution Plan.
    """

    def __init__(self) -> None:
        self._current_state = QuestState("unknown", "", "", False, 0)

    def update_state(self, claim: ScreenStateClaim) -> QuestState:
        """Parses screen claims to extract quest titles, objectives, and blocked status."""
        active_quest_id = "unknown"
        objective_text = ""
        tracked_target = ""
        is_blocked = False
        failure_count = self._current_state.failure_count

        # 1. Compile OCR text block candidates
        ocr_lines = list(claim.raw_ocr_texts)
        for element in claim.ui_elements:
            if element.text:
                ocr_lines.append(element.text)

        # 2. Extract quest line or task objectives using regex patterns
        # Look for English (Quest, Task, Track) and Chinese (任务, 委托, 目标, 追踪) keywords
        quest_patterns = [
            r"(?:quest|task|track|objective)\s*:\s*(.*)",
            r"(?:任务|委托|目标|追踪)\s*:\s*(.*)",
            r"委托\s*(.*)",
            r"追踪\s*(.*)",
        ]

        # First sweep: Check for blocked indicators across all lines
        for line in ocr_lines:
            if re.search(r"(?:blocked|stuck|failed|cannot|无法|卡住|障碍)", line.strip(), re.IGNORECASE):
                is_blocked = True

        # Second sweep: Match quest objective
        for line in ocr_lines:
            line_str = line.strip()
            for pattern in quest_patterns:
                match = re.search(pattern, line_str, re.IGNORECASE)
                if match:
                    objective_text = match.group(1).strip()
                    active_quest_id = f"quest_{abs(hash(objective_text)) % 10000}"
                    break
            if objective_text:
                break

        # Fallback 1: Extract from scene description if VLM provided one
        if not objective_text and claim.scene_description:
            vlm_match = re.search(r"(?:quest|task|objective|goal is)\s*([a-zA-Z0-9\s]+)", claim.scene_description, re.IGNORECASE)
            if vlm_match:
                objective_text = vlm_match.group(1).strip()
                active_quest_id = f"quest_{abs(hash(objective_text)) % 10000}"

        # Fallback 2: Default to first text line with "委" or "任" or just first text element
        if not objective_text:
            for line in ocr_lines:
                if any(kw in line for kw in ("委托", "任务", "目标", "Quest", "Task")):
                    objective_text = line.strip()
                    active_quest_id = f"quest_{abs(hash(objective_text)) % 10000}"
                    break

        # Check if the quest goal changed from previous state. If blocked, increment failure_count
        if is_blocked:
            failure_count += 1
        elif self._current_state.objective_text != objective_text:
            # Objective changed, reset failure count
            failure_count = 0

        self._current_state = QuestState(
            active_quest_id=active_quest_id,
            objective_text=objective_text or self._current_state.objective_text or "No active quest",
            tracked_target=tracked_target,
            is_blocked=is_blocked,
            failure_count=failure_count,
        )
        return self._current_state

    def get_current_state(self) -> QuestState:
        return self._current_state
